import os
import re
import html
import time
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, HTTPServer

import feedparser
import requests

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    BotCommand,
)

from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# =========================================================
# AI
# =========================================================

GROQ_MODEL = "qwen/qwen3.6-27b"
GEMINI_MODEL = "gemini-3.8-flash"


# =========================================================
# ИСТОЧНИКИ НОВОСТЕЙ
# =========================================================

NEWS_FEEDS = [

    # 🇰🇿 КАЗАХСТАН
    {
        "region": "🇰🇿 Казахстан",
        "source": "Kazinform",
        "url": "https://qazinform.com/rss/en.xml",
    },

    {
        "region": "🇰🇿 Казахстан",
        "source": "The Astana Times",
        "url": "https://astanatimes.com/feed/",
    },


    # 🇺🇸 США
    {
        "region": "🇺🇸 США",
        "source": "NPR",
        "url": "https://feeds.npr.org/1003/rss.xml",
    },

    {
        "region": "🇺🇸 США",
        "source": "BBC",
        "url": "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
    },


    # 🇪🇺 ЕВРОПА
    {
        "region": "🇪🇺 Европа",
        "source": "Euronews",
        "url": "https://euronews.com/rss?format=mrss&level=vertical&name=my-europe",
    },

    {
        "region": "🇪🇺 Европа",
        "source": "BBC",
        "url": "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
    },


    # 🇨🇳 КИТАЙ
    {
        "region": "🇨🇳 Китай",
        "source": "China News Service",
        "url": "https://www.chinanews.com.cn/rss/china.xml",
    },

    {
        "region": "🇨🇳 Китай",
        "source": "BBC",
        "url": "https://feeds.bbci.co.uk/news/world/asia/china/rss.xml",
    },


    # 🇷🇺 РОССИЯ
    {
        "region": "🇷🇺 Россия",
        "source": "Интерфакс",
        "url": "https://www.interfax.ru/rss.asp",
    },

    {
        "region": "🇷🇺 Россия",
        "source": "Meduza",
        "url": "https://meduza.io/rss2/all",
    },


    # 🌍 МИР
    {
        "region": "🌍 Мир",
        "source": "Euronews",
        "url": "https://www.euronews.com/rss?format=mrss&level=theme&name=news",
    },

    {
        "region": "🌍 Мир",
        "source": "BBC",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
    },


    # 🤖 AI / ТЕХНОЛОГИИ
    {
        "region": "🤖 AI / технологии",
        "source": "TechCrunch",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
    },

    {
        "region": "🤖 AI / технологии",
        "source": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
    },
]


# =========================================================
# МЕНЮ
# =========================================================

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["🔥 Главное", "📰 Все новости"],
        ["🇰🇿 Казахстан", "🇺🇸 США"],
        ["🇪🇺 Европа", "🇨🇳 Китай"],
        ["🇷🇺 Россия", "🌍 Мир"],
        ["🤖 AI / технологии"],
    ],
    resize_keyboard=True,
)


BUTTON_TO_REGION = {
    "🇰🇿 Казахстан": "🇰🇿 Казахстан",
    "🇺🇸 США": "🇺🇸 США",
    "🇪🇺 Европа": "🇪🇺 Европа",
    "🇨🇳 Китай": "🇨🇳 Китай",
    "🇷🇺 Россия": "🇷🇺 Россия",
    "🌍 Мир": "🌍 Мир",
    "🤖 AI / технологии": "🤖 AI / технологии",
}


COMMAND_TO_REGION = {
    "kz": "🇰🇿 Казахстан",
    "usa": "🇺🇸 США",
    "europe": "🇪🇺 Европа",
    "china": "🇨🇳 Китай",
    "russia": "🇷🇺 Россия",
    "world": "🌍 Мир",
    "ai": "🤖 AI / технологии",
}


IMPACT_RANK = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
}


# =========================================================
# WEB SERVER ДЛЯ RENDER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header(
            "Content-type",
            "text/plain",
        )
        self.end_headers()
        self.wfile.write(
            b"Bot is running"
        )

    def log_message(
        self,
        format,
        *args
    ):
        return


def run_web_server():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler,
    )

    print(
        f"Web server started on port {port}"
    )

    server.serve_forever()


# =========================================================
# ОЧИСТКА ТЕКСТА
# =========================================================

def clean_text(text):

    if not text:
        return ""

    text = html.unescape(
        str(text)
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = " ".join(
        text
        .replace("\n", " ")
        .split()
    )

    return text


# =========================================================
# ЗАГРУЗКА RSS
# =========================================================

def collect_articles(
    region_filter=None
):

    articles = []

    for feed_info in NEWS_FEEDS:

        if (
            region_filter
            and
            feed_info["region"] != region_filter
        ):
            continue

        try:

            response = requests.get(
                feed_info["url"],
                headers={
                    "User-Agent":
                    "Mozilla/5.0 NewsBot/1.0"
                },
                timeout=15,
            )

            response.raise_for_status()

            feed = feedparser.parse(
                response.content
            )

            if not feed.entries:

                print(
                    "No articles from:",
                    feed_info["source"],
                )

                continue

            article = feed.entries[0]

            title = clean_text(
                article.get(
                    "title",
                    ""
                )
            )

            description = clean_text(
                article.get(
                    "summary",
                    article.get(
                        "description",
                        ""
                    )
                )
            )

            link = article.get(
                "link",
                ""
            )

            if not title:
                continue

            articles.append({
                "region":
                    feed_info["region"],

                "source":
                    feed_info["source"],

                "title":
                    title,

                "description":
                    description,

                "link":
                    link,
            })

        except Exception as error:

            print(
                f"RSS error "
                f"{feed_info['source']}:",
                repr(error),
            )

    return articles


# =========================================================
# СОЗДАЁМ PROMPT ДЛЯ AI
# =========================================================

def make_ai_prompt(articles):

    blocks = []

    for index, article in enumerate(
        articles
    ):

        description = clean_text(
            article.get(
                "description",
                ""
            )
        )[:700]

        blocks.append(
            f"""
NEWS_{index}
REGION: {article['region']}
SOURCE: {article['source']}
TITLE: {article['title']}
DESCRIPTION: {description}
""".strip()
        )

    articles_text = "\n\n".join(
        blocks
    )

    return f"""
Ты редактор русскоязычного новостного агрегатора.

Обработай КАЖДУЮ публикацию ниже.

Для каждого NEWS_:

1. Переведи заголовок на естественный русский язык.

2. Напиши короткое описание события:
максимум 1–2 предложения.

3. Используй только информацию из TITLE и DESCRIPTION.
Ничего не выдумывай.

4. Точно сохраняй имена людей, компании, страны,
даты, суммы, проценты и другие числа.

5. Если несколько публикаций описывают одно и то же
КОНКРЕТНОЕ событие, присвой им одинаковый EVENT_ID.

6. Если это похожая тема, но разные события,
EVENT_ID должен быть разным.

7. Если сомневаешься — НЕ объединяй события.

8. Определи масштаб события:

HIGH =
крупное событие с широким национальным
или международным значением,
серьёзной угрозой безопасности,
существенным экономическим эффектом
или значимым решением государственных
или международных институтов.

MEDIUM =
заметное событие более ограниченного масштаба.

LOW =
локальная, узкая или нишевая новость.

Не повышай важность из-за эмоционального заголовка,
политической позиции или мнения СМИ.

9. Не представляй заявление, обвинение,
предположение или прогноз как установленный факт.

Верни РОВНО одну строку для каждого NEWS_.

Формат строго:

NEWS_0|||EVENT_1|||HIGH|||РУССКИЙ ЗАГОЛОВОК|||КРАТКОЕ ОПИСАНИЕ

Допустимые уровни:

HIGH
MEDIUM
LOW

Не используй Markdown.
Не используй JSON.
Не пиши никаких объяснений.
Не пропускай NEWS_.

Публикации:

{articles_text}
"""


# =========================================================
# GROQ — ОСНОВНОЙ AI
# =========================================================

def call_groq(prompt):

    api_key = os.environ.get(
        "GROQ_API_KEY"
    )

    if not api_key:

        print(
            "GROQ_API_KEY missing"
        )

        return None

    url = (
        "https://api.groq.com/"
        "openai/v1/chat/completions"
    )

    # Две попытки
    for attempt in range(2):

        try:

            response = requests.post(
                url,
                headers={
                    "Authorization":
                        f"Bearer {api_key}",

                    "Content-Type":
                        "application/json",
                },
                json={
                    "model":
                        GROQ_MODEL,

                    "messages": [
                        {
                            "role": "system",
                            "content":
                                "Ты точный редактор "
                                "и переводчик новостей."
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],

                    "temperature": 0.1,

                    "max_completion_tokens":
                        6000,

                    # Для Qwen убираем
                    # лишние reasoning-токены.
                    "reasoning_effort":
                        "none",
                },
                timeout=60,
            )

            if response.status_code == 200:

                data = response.json()

                text = (
                    data["choices"][0]
                    ["message"]["content"]
                )

                if text:

                    print(
                        "AI provider: GROQ"
                    )

                    return text.strip()

            print(
                "Groq error:",
                response.status_code,
                response.text[:1000],
            )

            # На rate limit / серверных ошибках
            # пробуем ещё раз.
            if (
                response.status_code == 429
                or
                response.status_code >= 500
            ):

                time.sleep(
                    2 + attempt * 2
                )

                continue

            break

        except Exception as error:

            print(
                "Groq exception:",
                repr(error),
            )

            time.sleep(
                2 + attempt * 2
            )

    return None


# =========================================================
# GEMINI — РЕЗЕРВ
# =========================================================

def call_gemini(prompt):

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:

        print(
            "GEMINI_API_KEY missing"
        )

        return None

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )

    try:

        response = requests.post(
            url,
            headers={
                "Content-Type":
                    "application/json",

                "x-goog-api-key":
                    api_key,
            },
            json={
                "contents": [
                    {
                        "parts": [
                            {
                                "text":
                                    prompt
                            }
                        ]
                    }
                ],

                "generationConfig": {
                    "temperature":
                        0.1,

                    "maxOutputTokens":
                        6000,
                },
            },
            timeout=70,
        )

        if response.status_code != 200:

            print(
                "Gemini error:",
                response.status_code,
                response.text[:1000],
            )

            return None

        data = response.json()

        candidates = data.get(
            "candidates",
            []
        )

        if not candidates:

            return None

        parts = (
            candidates[0]
            .get("content", {})
            .get("parts", [])
        )

        text = "\n".join(
            part.get(
                "text",
                ""
            )

            for part in parts

            if part.get(
                "text"
            )
        ).strip()

        if text:

            print(
                "AI provider: GEMINI FALLBACK"
            )

            return text

    except Exception as error:

        print(
            "Gemini exception:",
            repr(error),
        )

    return None


# =========================================================
# ЧИТАЕМ ОТВЕТ AI
# =========================================================

def parse_ai_response(
    raw_text,
    article_count
):

    processed = {}

    if not raw_text:
        return processed

    for line in raw_text.splitlines():

        line = line.strip()

        if not line.startswith(
            "NEWS_"
        ):
            continue

        pieces = line.split(
            "|||",
            4
        )

        if len(pieces) != 5:
            continue

        news_id = (
            pieces[0].strip()
        )

        event_id = (
            pieces[1].strip()
        )

        impact = (
            pieces[2]
            .strip()
            .upper()
        )

        title_ru = (
            pieces[3].strip()
        )

        summary_ru = (
            pieces[4].strip()
        )

        try:

            index = int(
                news_id.replace(
                    "NEWS_",
                    ""
                )
            )

        except ValueError:

            continue

        if not (
            0 <= index < article_count
        ):

            continue

        if impact not in IMPACT_RANK:

            impact = "MEDIUM"

        processed[index] = {
            "event_id":
                event_id,

            "impact":
                impact,

            "title_ru":
                title_ru,

            "summary_ru":
                summary_ru,
        }

    return processed


# =========================================================
# GROQ -> GEMINI
# =========================================================

def process_articles_with_ai(
    articles
):

    prompt = make_ai_prompt(
        articles
    )

    # 1. GROQ
    groq_text = call_groq(
        prompt
    )

    groq_result = parse_ai_response(
        groq_text,
        len(articles),
    )

    # Если Groq обработал всё —
    # Gemini вообще не тратим.
    if (
        len(groq_result)
        ==
        len(articles)
    ):

        return groq_result, "Groq"


    if groq_text:

        print(
            "Groq returned partial result:",
            len(groq_result),
            "/",
            len(articles),
        )


    # 2. GEMINI FALLBACK
    gemini_text = call_gemini(
        prompt
    )

    gemini_result = parse_ai_response(
        gemini_text,
        len(articles),
    )


    if (
        len(gemini_result)
        >=
        len(groq_result)
        and
        gemini_result
    ):

        return (
            gemini_result,
            "Gemini"
        )


    if groq_result:

        return (
            groq_result,
            "Groq partial"
        )


    return None, None


# =========================================================
# РЕЗЕРВ БЕЗ AI
# =========================================================

def fallback_processed(
    articles
):

    result = {}

    for index, article in enumerate(
        articles
    ):

        result[index] = {
            "event_id":
                f"FALLBACK_{index}",

            "impact":
                "MEDIUM",

            "title_ru":
                article["title"],

            "summary_ru":
                "",
        }

    return result


# =========================================================
# ОБЪЕДИНЕНИЕ ДУБЛЕЙ
# =========================================================

def group_articles(
    articles,
    processed
):

    events = OrderedDict()

    for index, article in enumerate(
        articles
    ):

        data = processed.get(
            index,
            {}
        )

        event_id = data.get(
            "event_id",
            f"FALLBACK_{index}",
        )

        title_ru = data.get(
            "title_ru",
            article["title"],
        )

        summary_ru = data.get(
            "summary_ru",
            "",
        )

        impact = data.get(
            "impact",
            "MEDIUM",
        )

        if event_id not in events:

            events[event_id] = {
                "region":
                    article["region"],

                "title":
                    title_ru,

                "summary":
                    summary_ru,

                "impact":
                    impact,

                "sources":
                    [],
            }

        else:

            old_impact = (
                events[event_id]
                ["impact"]
            )

            if (
                IMPACT_RANK[impact]
                >
                IMPACT_RANK[old_impact]
            ):

                events[event_id][
                    "impact"
                ] = impact

        events[event_id][
            "sources"
        ].append({
            "name":
                article["source"],

            "link":
                article["link"],
        })

    return list(
        events.values()
    )


# =========================================================
# УБИРАЕМ ПОВТОРНЫЕ ССЫЛКИ
# =========================================================

def unique_sources(sources):

    result = []
    seen = set()

    for source in sources:

        key = (
            source.get(
                "name",
                ""
            ),

            source.get(
                "link",
                ""
            ),
        )

        if key in seen:
            continue

        seen.add(key)

        result.append(source)

    return result


# =========================================================
# ОТПРАВКА СОБЫТИЙ
# =========================================================

async def send_events(
    update,
    events
):

    for event in events:

        sources = unique_sources(
            event["sources"]
        )

        source_names = []

        for source in sources:

            if (
                source["name"]
                not in source_names
            ):

                source_names.append(
                    source["name"]
                )

        if len(source_names) == 1:

            sources_text = (
                f"🗞 Источник: "
                f"{source_names[0]}"
            )

        else:

            sources_text = (
                f"🗞 Источников: "
                f"{len(source_names)} — "
                + " • ".join(
                    source_names
                )
            )

        message = (
            f"{event['region']}\n\n"
            f"📰 {event['title']}\n"
        )

        if event["summary"]:

            message += (
                f"\nКоротко: "
                f"{event['summary']}\n"
            )

        message += (
            f"\n{sources_text}\n"
        )

        for source in sources:

            message += (
                f"\n🔗 "
                f"{source['name']}: "
                f"{source['link']}"
            )

        try:

            await update.message.reply_text(
                message,
                disable_web_page_preview=True,
            )

        except Exception as error:

            print(
                "Telegram send error:",
                repr(error),
            )


# =========================================================
# ОСНОВНОЙ ЗАПРОС НОВОСТЕЙ
# =========================================================

async def run_news_request(
    update,
    region_filter=None,
    important_only=False,
):

    if important_only:

        status_text = (
            "🔥 Ищу главное...\n"
            "🌍 Проверяю источники\n"
            "🧠 Анализирую события\n"
            "🇷🇺 Готовлю на русском"
        )

    elif region_filter:

        status_text = (
            f"🔎 Собираю: "
            f"{region_filter}\n"
            f"🇷🇺 Перевожу "
            f"и объединяю дубли"
        )

    else:

        status_text = (
            "🔎 Собираю новости...\n"
            "🌍 Проверяю источники\n"
            "🇷🇺 Перевожу\n"
            "🧠 Объединяю одинаковые события"
        )

    status_message = (
        await update.message.reply_text(
            status_text
        )
    )

    articles = collect_articles(
        region_filter=region_filter
    )

    if not articles:

        await status_message.edit_text(
            "❌ Сейчас не удалось "
            "получить новости."
        )

        return


    processed, provider = (
        process_articles_with_ai(
            articles
        )
    )


    ai_failed = (
        processed is None
    )


    if (
        ai_failed
        and
        important_only
    ):

        await status_message.edit_text(
            "⚠️ Groq и Gemini сейчас "
            "не ответили.\n"
            "Без AI я не буду "
            "угадывать, какие новости "
            "главные."
        )

        return


    if ai_failed:

        processed = fallback_processed(
            articles
        )


    events = group_articles(
        articles,
        processed,
    )


    if important_only:

        events = [
            event
            for event in events
            if event["impact"] == "HIGH"
        ]

        # Максимум 5
        events = events[:5]


    try:

        await status_message.delete()

    except Exception:

        pass


    if (
        important_only
        and
        not events
    ):

        await update.message.reply_text(
            "Среди найденных публикаций "
            "сейчас нет событий, "
            "которые AI отнёс "
            "к высокой важности."
        )

        return


    if ai_failed:

        await update.message.reply_text(
            "⚠️ Groq и Gemini временно "
            "не ответили.\n"
            "Показываю обычные RSS."
        )


    await send_events(
        update,
        events,
    )


# =========================================================
# /START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Я собираю новости из разных источников, "
        "перевожу их на русский "
        "и объединяю одинаковые события.\n\n"
        "Выбирай раздел 👇",
        reply_markup=MAIN_MENU,
    )


# =========================================================
# /MENU
# =========================================================

async def menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "Выбирай раздел 👇",
        reply_markup=MAIN_MENU,
    )


# =========================================================
# /NEWS
# =========================================================

async def news(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await run_news_request(
        update
    )


# =========================================================
# /IMPORTANT
# =========================================================

async def important(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await run_news_request(
        update,
        important_only=True,
    )


# =========================================================
# /STATUS
# =========================================================

async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    groq_ok = bool(
        os.environ.get(
            "GROQ_API_KEY"
        )
    )

    gemini_ok = bool(
        os.environ.get(
            "GEMINI_API_KEY"
        )
    )

    await update.message.reply_text(
        "🤖 AI-настройки\n\n"
        f"Groq: "
        f"{'✅ подключён' if groq_ok else '❌ нет ключа'}\n"
        f"Gemini: "
        f"{'✅ подключён' if gemini_ok else '❌ нет ключа'}"
    )


# =========================================================
# КОМАНДЫ СТРАН
# =========================================================

async def region_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    command = (
        update.message.text
        .split()[0]
        .split("@")[0]
        .lstrip("/")
        .lower()
    )

    region = COMMAND_TO_REGION.get(
        command
    )

    if region:

        await run_news_request(
            update,
            region_filter=region,
        )


# =========================================================
# /MANUTD 😈
# =========================================================

async def manutd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "Муха лох.\n"
        "Слабый везде."
    )


# =========================================================
# КНОПКИ
# =========================================================

async def menu_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = (
        update.message.text
        .strip()
    )

    if text == "🔥 Главное":

        await important(
            update,
            context,
        )

        return


    if text == "📰 Все новости":

        await news(
            update,
            context,
        )

        return


    region = BUTTON_TO_REGION.get(
        text
    )

    if region:

        await run_news_request(
            update,
            region_filter=region,
        )

        return


    await update.message.reply_text(
        "Выбери раздел "
        "кнопками ниже 👇",
        reply_markup=MAIN_MENU,
    )


# =========================================================
# TELEGRAM-КОМАНДЫ
# =========================================================

async def post_init(
    application: Application
):

    await application.bot.set_my_commands(
        [
            BotCommand(
                "news",
                "Все новости"
            ),

            BotCommand(
                "important",
                "Главные события"
            ),

            BotCommand(
                "kz",
                "Казахстан"
            ),

            BotCommand(
                "usa",
                "США"
            ),

            BotCommand(
                "europe",
                "Европа"
            ),

            BotCommand(
                "china",
                "Китай"
            ),

            BotCommand(
                "russia",
                "Россия"
            ),

            BotCommand(
                "world",
                "Мир"
            ),

            BotCommand(
                "ai",
                "AI и технологии"
            ),

            BotCommand(
                "menu",
                "Показать меню"
            ),

            BotCommand(
                "status",
                "Статус AI"
            ),
        ]
    )


# =========================================================
# ЗАПУСК
# =========================================================

def main():

    threading.Thread(
        target=run_web_server,
        daemon=True,
    ).start()


    telegram_token = os.environ[
        "TELEGRAM_BOT_TOKEN"
    ]


    app = (
        Application.builder()
        .token(
            telegram_token
        )
        .post_init(
            post_init
        )
        .build()
    )


    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )


    app.add_handler(
        CommandHandler(
            "menu",
            menu,
        )
    )


    app.add_handler(
        CommandHandler(
            "news",
            news,
        )
    )


    app.add_handler(
        CommandHandler(
            "important",
            important,
        )
    )


    app.add_handler(
        CommandHandler(
            "status",
            status,
        )
    )


    for command in COMMAND_TO_REGION:

        app.add_handler(
            CommandHandler(
                command,
                region_command,
            )
        )


    # Скрытая команда
    app.add_handler(
        CommandHandler(
            "manutd",
            manutd,
        )
    )


    app.add_handler(
        MessageHandler(
            filters.TEXT
            &
            ~filters.COMMAND,
            menu_buttons,
        )
    )


    print(
        "Telegram bot started"
    )


    app.run_polling()


if __name__ == "__main__":
    main()
