import os
import re
import html
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, HTTPServer

import feedparser
import requests
from telegram import Update, ReplyKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# ==========================================
# НАСТРОЙКИ
# ==========================================

GEMINI_MODEL = "gemini-3.8-flash"


NEWS_FEEDS = [

    # 🇰🇿 КАЗАХСТАН
    {
        "region": "🇰🇿 Казахстан",
        "source": "Kazinform",
        "url": "https://qazinform.com/rss/en.xml"
    },

    {
        "region": "🇰🇿 Казахстан",
        "source": "The Astana Times",
        "url": "https://astanatimes.com/feed/"
    },


    # 🇺🇸 США
    {
        "region": "🇺🇸 США",
        "source": "NPR",
        "url": "https://feeds.npr.org/1003/rss.xml"
    },

    {
        "region": "🇺🇸 США",
        "source": "BBC",
        "url": "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml"
    },


    # 🇪🇺 ЕВРОПА
    {
        "region": "🇪🇺 Европа",
        "source": "Euronews",
        "url": "https://euronews.com/rss?format=mrss&level=vertical&name=my-europe"
    },

    {
        "region": "🇪🇺 Европа",
        "source": "BBC",
        "url": "https://feeds.bbci.co.uk/news/world/europe/rss.xml"
    },


    # 🇨🇳 КИТАЙ
    {
        "region": "🇨🇳 Китай",
        "source": "China News Service",
        "url": "https://www.chinanews.com.cn/rss/china.xml"
    },

    {
        "region": "🇨🇳 Китай",
        "source": "BBC",
        "url": "https://feeds.bbci.co.uk/news/world/asia/china/rss.xml"
    },


    # 🇷🇺 РОССИЯ
    {
        "region": "🇷🇺 Россия",
        "source": "Интерфакс",
        "url": "https://www.interfax.ru/rss.asp"
    },

    {
        "region": "🇷🇺 Россия",
        "source": "Meduza",
        "url": "https://meduza.io/rss2/all"
    },


    # 🌍 МИР
    {
        "region": "🌍 Мир",
        "source": "Euronews",
        "url": "https://www.euronews.com/rss?format=mrss&level=theme&name=news"
    },

    {
        "region": "🌍 Мир",
        "source": "BBC",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml"
    },


    # 🤖 AI / ТЕХНОЛОГИИ
    {
        "region": "🤖 AI / технологии",
        "source": "TechCrunch",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/"
    },

    {
        "region": "🤖 AI / технологии",
        "source": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml"
    },
]


# ==========================================
# КНОПКИ
# ==========================================

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


# ==========================================
# WEB-СЕРВЕР ДЛЯ RENDER
# ==========================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-type",
            "text/plain"
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
        HealthHandler
    )

    print(
        f"Web server started on port {port}"
    )

    server.serve_forever()


# ==========================================
# ОЧИСТКА ТЕКСТА
# ==========================================

def clean_text(text):

    if not text:
        return ""

    text = html.unescape(
        str(text)
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = " ".join(
        text
        .replace("\n", " ")
        .split()
    )

    return text


# ==========================================
# ПОЛУЧЕНИЕ НОВОСТЕЙ
# ==========================================

def collect_articles(
    region_filter=None
):

    articles = []


    for feed_info in NEWS_FEEDS:

        if (
            region_filter
            and
            feed_info["region"]
            != region_filter
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
                    feed_info["source"]
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
                repr(error)
            )


    return articles


# ==========================================
# GEMINI
# перевод + описание + дубли + важность
# ==========================================

def process_articles_with_gemini(
    articles
):

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )


    if not api_key:

        print(
            "GEMINI_API_KEY missing"
        )

        return None


    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{GEMINI_MODEL}:generateContent"
    )


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


    prompt = f"""
Ты редактор русскоязычного новостного агрегатора.

Обработай каждую публикацию ниже.

Для каждой NEWS_:

1. Переведи заголовок на естественный русский язык.

2. Сделай короткое описание:
максимум 1–2 предложения.

3. Используй только информацию
из TITLE и DESCRIPTION.

Ничего не выдумывай.

4. Точно сохраняй:
имена,
названия компаний,
страны,
даты,
суммы,
проценты
и числа.

5. Если несколько публикаций
описывают одно и то же КОНКРЕТНОЕ событие,
дай им одинаковый EVENT_ID.

6. Если тема похожа,
но события разные,
EVENT_ID должен быть разным.

7. Если сомневаешься —
НЕ объединяй.

8. Определи масштаб события:

HIGH =
крупное событие с широким
международным или национальным влиянием,
серьёзной угрозой безопасности,
значительным экономическим эффектом
или важным решением государственных
или международных институтов.

MEDIUM =
заметное событие,
но более ограниченного масштаба.

LOW =
локальная,
узкая
или нишевая новость.

Не повышай важность
из-за политической позиции,
эмоционального тона
или мнения конкретного СМИ.

9. Не представляй
заявление,
обвинение,
мнение,
предположение
или прогноз
как установленный факт.


Формат каждой строки СТРОГО:

NEWS_0|||EVENT_1|||HIGH|||РУССКИЙ ЗАГОЛОВОК|||КРАТКОЕ ОПИСАНИЕ


Разрешённые уровни:

HIGH
MEDIUM
LOW


Верни ровно одну строку
для каждого NEWS_.

Не используй Markdown.
Не используй JSON.
Не пиши пояснений.
Не пропускай NEWS_.


Публикации:

{articles_text}
"""


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


            timeout=90,
        )


        if response.status_code != 200:

            print(
                "Gemini HTTP error:",
                response.status_code,
                response.text[:2000]
            )

            return None


        data = response.json()


        candidates = data.get(
            "candidates",
            []
        )


        if not candidates:

            print(
                "Gemini returned no candidates"
            )

            return None


        parts = (
            candidates[0]
            .get("content", {})
            .get("parts", [])
        )


        raw_text = "\n".join(

            part.get(
                "text",
                ""
            )

            for part in parts

            if part.get(
                "text"
            )

        ).strip()


        print(
            "Gemini processed articles:",
            raw_text[:3000]
        )


        processed = {}


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
                pieces[0]
                .strip()
            )

            event_id = (
                pieces[1]
                .strip()
            )

            impact = (
                pieces[2]
                .strip()
                .upper()
            )

            title_ru = (
                pieces[3]
                .strip()
            )

            summary_ru = (
                pieces[4]
                .strip()
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


    except Exception as error:

        print(
            "Gemini processing exception:",
            repr(error)
        )

        return None


# ==========================================
# РЕЗЕРВНЫЙ РЕЖИМ
# ==========================================

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


# ==========================================
# ОБЪЕДИНЕНИЕ ДУБЛЕЙ
# ==========================================

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
            f"FALLBACK_{index}"
        )


        title_ru = data.get(
            "title_ru",
            article["title"]
        )


        summary_ru = data.get(
            "summary_ru",
            ""
        )


        impact = data.get(
            "impact",
            "MEDIUM"
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
                IMPACT_RANK[
                    impact
                ]
                >
                IMPACT_RANK[
                    old_impact
                ]
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


# ==========================================
# УБИРАЕМ ПОВТОРЫ ССЫЛОК
# ==========================================

def unique_sources(
    sources
):

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
            )
        )


        if key in seen:
            continue


        seen.add(
            key
        )


        result.append(
            source
        )


    return result


# ==========================================
# ОТПРАВКА СОБЫТИЙ
# ==========================================

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
                disable_web_page_preview=True
            )


        except Exception as error:

            print(
                "Telegram send error:",
                repr(error)
            )


# ==========================================
# ОСНОВНАЯ ЛОГИКА НОВОСТЕЙ
# ==========================================

async def run_news_request(
    update,
    region_filter=None,
    important_only=False
):


    if important_only:

        status_text = (
            "🔥 Ищу главное...\n"
            "🌍 Проверяю источники\n"
            "🧠 Сравниваю события\n"
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


    processed = (
        process_articles_with_gemini(
            articles
        )
    )


    if (
        processed is None
        and
        important_only
    ):

        await status_message.edit_text(
            "⚠️ Gemini сейчас недоступен, "
            "поэтому я не могу надёжно "
            "определить главное."
        )

        return


    ai_failed = (
        processed is None
    )


    if ai_failed:

        processed = fallback_processed(
            articles
        )


    events = group_articles(
        articles,
        processed
    )


    # ======================================
    # ГЛАВНЫЕ НОВОСТИ
    # ======================================

    if important_only:

        events = [

            event

            for event in events

            if event[
                "impact"
            ] == "HIGH"
        ]


        # Максимум 5 главных событий

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
            "сейчас нет событий "
            "высокой важности."
        )

        return


    if ai_failed:

        await update.message.reply_text(
            "⚠️ AI-обработка временно "
            "недоступна.\n"
            "Показываю новости без "
            "перевода и объединения."
        )


    await send_events(
        update,
        events
    )


# ==========================================
# /START
# ==========================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(

        "👋 Привет!\n\n"

        "Я собираю новости "
        "из разных источников, "
        "перевожу их на русский "
        "и объединяю одинаковые события.\n\n"

        "Выбирай раздел кнопками ниже 👇\n\n"

        "🔥 Главное — "
        "крупные события\n"

        "📰 Все новости — "
        "общая лента",

        reply_markup=MAIN_MENU,
    )


# ==========================================
# /MENU
# ==========================================

async def menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "Выбирай раздел 👇",
        reply_markup=MAIN_MENU,
    )


# ==========================================
# /NEWS
# ==========================================

async def news(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await run_news_request(
        update
    )


# ==========================================
# /IMPORTANT
# ==========================================

async def important(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await run_news_request(
        update,
        important_only=True
    )


# ==========================================
# КОМАНДЫ СТРАН
# ==========================================

async def region_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
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
            region_filter=region
        )


# ==========================================
# /MANUTD 😈
# ==========================================

async def manutd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "Муха лох.\n"
        "Слабый везде."
    )


# ==========================================
# НАЖАТИЯ НА КНОПКИ
# ==========================================

async def menu_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = (
        update.message.text
        .strip()
    )


    if text == "🔥 Главное":

        await important(
            update,
            context
        )

        return


    if text == "📰 Все новости":

        await news(
            update,
            context
        )

        return


    region = BUTTON_TO_REGION.get(
        text
    )


    if region:

        await run_news_request(
            update,
            region_filter=region
        )

        return


    await update.message.reply_text(
        "Выбери раздел "
        "кнопками ниже 👇",
        reply_markup=MAIN_MENU,
    )


# ==========================================
# СПИСОК TELEGRAM-КОМАНД
# ==========================================

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
        ]
    )


# ==========================================
# ЗАПУСК
# ==========================================

def main():

    threading.Thread(
        target=run_web_server,
        daemon=True
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


    # Основные команды

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )


    app.add_handler(
        CommandHandler(
            "menu",
            menu
        )
    )


    app.add_handler(
        CommandHandler(
            "news",
            news
        )
    )


    app.add_handler(
        CommandHandler(
            "important",
            important
        )
    )


    # Команды стран

    for command in COMMAND_TO_REGION:

        app.add_handler(
            CommandHandler(
                command,
                region_command
            )
        )


    # Секретная пасхалка 😈

    app.add_handler(
        CommandHandler(
            "manutd",
            manutd
        )
    )


    # Кнопки

    app.add_handler(

        MessageHandler(

            filters.TEXT
            &
            ~filters.COMMAND,

            menu_buttons
        )
    )


    print(
        "Telegram bot started"
    )


    app.run_polling()


if __name__ == "__main__":

    main()
