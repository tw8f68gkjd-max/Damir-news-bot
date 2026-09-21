import os
import re
import html
import time
import uuid
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, HTTPServer

import feedparser
import requests

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)


# =========================================================
# AI
# =========================================================

GROQ_MODEL = "openai/gpt-oss-20b"
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
        "url": "https://www.euronews.com/rss?format=mrss&level=vertical&name=my-europe",
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
        ["🔥 Главное", "⚡ Кратко"],
        ["📰 Все новости"],
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
# RSS
# =========================================================

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
# PROMPT ДЛЯ ОБРАБОТКИ НОВОСТЕЙ
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
        )[:600]

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

Обработай КАЖДУЮ публикацию.

Для каждого NEWS_:

1. Переведи заголовок на естественный русский язык.

2. Напиши краткое описание:
максимум 1–2 предложения.

3. Используй только TITLE и DESCRIPTION.
Ничего не выдумывай.

4. Точно сохраняй имена, страны,
компании, даты, суммы, проценты и числа.

5. Если несколько публикаций описывают
одно и то же КОНКРЕТНОЕ событие,
дай им одинаковый EVENT_ID.

6. Если события разные —
EVENT_ID должен быть разным.

7. Если сомневаешься —
не объединяй.

8. Определи масштаб:

HIGH =
крупное событие национального
или международного значения,
важное решение,
серьёзный экономический эффект
или значимая угроза безопасности.

MEDIUM =
заметное событие ограниченного масштаба.

LOW =
локальная или нишевая новость.

Не повышай важность из-за
эмоционального заголовка
или политической позиции источника.

Не представляй заявление,
обвинение, предположение
или прогноз как установленный факт.

Верни ровно одну строку
для каждого NEWS_.

Формат:

NEWS_0|||EVENT_1|||HIGH|||РУССКИЙ ЗАГОЛОВОК|||КРАТКОЕ ОПИСАНИЕ

Допустимые уровни:
HIGH
MEDIUM
LOW

Не используй Markdown.
Не используй JSON.
Не пиши пояснений.

Публикации:

{articles_text}
""".strip()


# =========================================================
# GROQ
# =========================================================

def call_groq(prompt):

    api_key = os.environ.get(
        "GROQ_API_KEY"
    )

    if not api_key:
        return None

    url = (
        "https://api.groq.com/"
        "openai/v1/chat/completions"
    )

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
                            "role": "user",
                            "content": prompt,
                        }
                    ],

                    "temperature":
                        0.2,

                    "max_completion_tokens":
                        5000,

                    "reasoning_effort":
                        "low",

                    "include_reasoning":
                        False,

                    "stream":
                        False,
                },

                timeout=70,
            )

            if response.status_code == 200:

                data = response.json()

                text = (
                    data["choices"][0]
                    ["message"]
                    .get(
                        "content",
                        ""
                    )
                )

                if text and text.strip():

                    print(
                        "AI provider: GROQ"
                    )

                    return text.strip()

            print(
                "Groq error:",
                response.status_code,
                response.text[:1000],
            )

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
        return None

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )

    for attempt in range(2):

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
                            0.2,

                        "maxOutputTokens":
                            5000,
                    },
                },

                timeout=80,
            )

            if response.status_code == 200:

                data = response.json()

                candidates = data.get(
                    "candidates",
                    []
                )

                if candidates:

                    parts = (
                        candidates[0]
                        .get(
                            "content",
                            {}
                        )
                        .get(
                            "parts",
                            []
                        )
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

            print(
                "Gemini error:",
                response.status_code,
                response.text[:1000],
            )

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
                "Gemini exception:",
                repr(error),
            )

            time.sleep(
                2 + attempt * 2
            )

    return None


# =========================================================
# ЛЮБОЙ AI-ЗАПРОС:
# GROQ -> GEMINI
# =========================================================

def ask_ai(prompt):

    answer = call_groq(
        prompt
    )

    if answer:
        return answer

    answer = call_gemini(
        prompt
    )

    return answer


# =========================================================
# РАЗБОР НОВОСТНОГО ОТВЕТА AI
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

        news_id = pieces[0].strip()
        event_id = pieces[1].strip()
        impact = pieces[2].strip().upper()
        title_ru = pieces[3].strip()
        summary_ru = pieces[4].strip()

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
                event_id
                or
                f"EVENT_{index}",

            "impact":
                impact,

            "title_ru":
                title_ru,

            "summary_ru":
                summary_ru,
        }

    return processed


# =========================================================
# AI ОБРАБОТКА НОВОСТЕЙ
# =========================================================

def process_articles_with_ai(
    articles
):

    prompt = make_ai_prompt(
        articles
    )

    groq_text = call_groq(
        prompt
    )

    groq_result = parse_ai_response(
        groq_text,
        len(articles),
    )

    if (
        len(groq_result)
        ==
        len(articles)
    ):
        return groq_result


    gemini_text = call_gemini(
        prompt
    )

    gemini_result = parse_ai_response(
        gemini_text,
        len(articles),
    )

    if (
        len(gemini_result)
        ==
        len(articles)
    ):
        return gemini_result


    merged = dict(
        groq_result
    )

    for index, item in (
        gemini_result.items()
    ):

        if index not in merged:
            merged[index] = item


    if merged:
        return merged

    return None


# =========================================================
# FALLBACK
# =========================================================

def fallback_processed(
    articles,
    existing=None
):

    result = dict(
        existing or {}
    )

    for index, article in enumerate(
        articles
    ):

        if index in result:
            continue

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
# ГРУППИРОВКА СОБЫТИЙ
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
# УНИКАЛЬНЫЕ ИСТОЧНИКИ
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

        seen.add(
            key
        )

        result.append(
            source
        )

    return result


# =========================================================
# СОХРАНЕНИЕ КАРТОЧЕК ДЛЯ INLINE-КНОПОК
# =========================================================

def save_event_card(
    application,
    event
):

    event_id = uuid.uuid4().hex[:12]

    cards = application.bot_data.setdefault(
        "event_cards",
        {}
    )

    cards[event_id] = event


    # Чтобы память не росла бесконечно
    while len(cards) > 300:

        oldest_key = next(
            iter(cards)
        )

        cards.pop(
            oldest_key,
            None
        )

    return event_id


# =========================================================
# КНОПКИ ПОД НОВОСТЬЮ
# =========================================================

def make_news_keyboard(
    event_id
):

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📖 Подробнее",
                    callback_data=
                        f"d:{event_id}",
                ),

                InlineKeyboardButton(
                    "💡 Почему важно?",
                    callback_data=
                        f"w:{event_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🗞 Источники",
                    callback_data=
                        f"s:{event_id}",
                ),
            ],
        ]
    )


# =========================================================
# ОТПРАВКА СОБЫТИЙ
# =========================================================

async def send_events(
    update,
    context,
    events
):

    for event in events:

        sources = unique_sources(
            event["sources"]
        )

        event["sources"] = sources

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
            f"\n{sources_text}"
        )


        card_id = save_event_card(
            context.application,
            event
        )


        try:

            await update.message.reply_text(
                message,
                disable_web_page_preview=True,
                reply_markup=
                    make_news_keyboard(
                        card_id
                    ),
            )

        except Exception as error:

            print(
                "Telegram send error:",
                repr(error),
            )


# =========================================================
# INLINE: ПОДРОБНЕЕ
# =========================================================

def make_details_prompt(event):

    sources = ", ".join(
        source["name"]
        for source in event["sources"]
    )

    return f"""
Ты объясняешь новостное событие пользователю.

Заголовок:
{event['title']}

Краткое описание:
{event['summary']}

Источники:
{sources}

Напиши более подробное объяснение
на русском языке.

Правила:

- максимум 5 коротких предложений;
- используй только информацию,
которая уже содержится в карточке;
- не выдумывай новые факты;
- сохраняй нейтральный тон;
- если данных мало, прямо скажи,
что подробностей пока недостаточно;
- заявления и обвинения
не представляй как доказанный факт;
- не советуй пользователю,
какую политическую позицию занимать.

Ответь только текстом.
""".strip()


# =========================================================
# INLINE: ПОЧЕМУ ВАЖНО
# =========================================================

def make_why_prompt(event):

    return f"""
Объясни нейтрально,
почему это новостное событие
может иметь значение.

Заголовок:
{event['title']}

Описание:
{event['summary']}

Уровень масштаба:
{event['impact']}

Правила:

- 2–4 коротких предложения;
- не выдумывай новых фактов;
- не драматизируй;
- не агитируй;
- не говори пользователю,
что он должен думать;
- если последствия пока неизвестны,
прямо скажи об этом;
- отделяй факты
от возможных последствий.

Ответь только текстом.
""".strip()


# =========================================================
# ОБРАБОТКА INLINE-КНОПОК
# =========================================================

async def news_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()


    try:

        action, card_id = (
            query.data.split(
                ":",
                1
            )
        )

    except Exception:

        return


    cards = (
        context.application.bot_data
        .get(
            "event_cards",
            {}
        )
    )


    event = cards.get(
        card_id
    )


    if not event:

        await query.message.reply_text(
            "Эта карточка уже устарела 🙂\n"
            "Запроси новости заново."
        )

        return


    # =====================================
    # ПОДРОБНЕЕ
    # =====================================

    if action == "d":

        cached = event.get(
            "_details"
        )

        if cached:

            await query.message.reply_text(
                "📖 Подробнее\n\n"
                + cached
            )

            return


        wait_message = (
            await query.message.reply_text(
                "📖 Готовлю подробности..."
            )
        )


        answer = ask_ai(
            make_details_prompt(
                event
            )
        )


        if not answer:

            await wait_message.edit_text(
                "⚠️ AI сейчас временно "
                "не смог подготовить подробности."
            )

            return


        event["_details"] = answer


        await wait_message.edit_text(
            "📖 Подробнее\n\n"
            + answer
        )

        return


    # =====================================
    # ПОЧЕМУ ВАЖНО
    # =====================================

    if action == "w":

        cached = event.get(
            "_why"
        )

        if cached:

            await query.message.reply_text(
                "💡 Почему это важно?\n\n"
                + cached
            )

            return


        wait_message = (
            await query.message.reply_text(
                "💡 Анализирую значение..."
            )
        )


        answer = ask_ai(
            make_why_prompt(
                event
            )
        )


        if not answer:

            await wait_message.edit_text(
                "⚠️ AI сейчас временно "
                "не смог сделать объяснение."
            )

            return


        event["_why"] = answer


        await wait_message.edit_text(
            "💡 Почему это важно?\n\n"
            + answer
        )

        return


    # =====================================
    # ИСТОЧНИКИ
    # =====================================

    if action == "s":

        source_buttons = []

        for source in event["sources"]:

            link = source.get(
                "link",
                ""
            )

            if not (
                link.startswith(
                    "http://"
                )
                or
                link.startswith(
                    "https://"
                )
            ):
                continue


            source_buttons.append(
                [
                    InlineKeyboardButton(
                        "🔗 "
                        + source["name"],
                        url=link,
                    )
                ]
            )


        if not source_buttons:

            await query.message.reply_text(
                "Для этой новости "
                "нет доступных ссылок."
            )

            return


        await query.message.reply_text(
            "🗞 Открыть источники:",
            reply_markup=
                InlineKeyboardMarkup(
                    source_buttons
                ),
        )

        return


# =========================================================
# ОСНОВНОЙ ЗАПРОС НОВОСТЕЙ
# =========================================================

async def run_news_request(
    update,
    context,
    region_filter=None,
    important_only=False
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
            "🇷🇺 Перевожу "
            "и объединяю дубли"
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
        process_articles_with_ai(
            articles
        )
    )


    if (
        processed is None
        and
        important_only
    ):

        await status_message.edit_text(
            "⚠️ Groq и Gemini сейчас "
            "не ответили.\n"
            "Без AI я не буду угадывать, "
            "какие новости главные."
        )

        return


    ai_failed = (
        processed is None
    )


    processed = fallback_processed(
        articles,
        processed
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
        ][:5]


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
        context,
        events,
    )


# =========================================================
# /BRIEF
# =========================================================

async def brief(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    status_message = (
        await update.message.reply_text(
            "⚡ Собираю короткую сводку..."
        )
    )


    articles = collect_articles()


    if not articles:

        await status_message.edit_text(
            "❌ Сейчас не удалось "
            "получить новости."
        )

        return


    processed = (
        process_articles_with_ai(
            articles
        )
    )


    processed = fallback_processed(
        articles,
        processed
    )


    events = group_articles(
        articles,
        processed,
    )


    # Сначала HIGH, затем MEDIUM, затем LOW.
    # При одинаковой важности выше событие,
    # которое встретилось у большего числа источников.
    events.sort(
        key=lambda event: (
            IMPACT_RANK.get(
                event["impact"],
                0
            ),
            len(
                unique_sources(
                    event["sources"]
                )
            ),
        ),
        reverse=True,
    )


    top_events = events[:5]


    try:

        await status_message.delete()

    except Exception:
        pass


    if not top_events:

        await update.message.reply_text(
            "Пока нечего добавить "
            "в краткую сводку."
        )

        return


    lines = [
        "⚡ Коротко: 5 событий\n"
    ]


    for number, event in enumerate(
        top_events,
        start=1
    ):

        lines.append(
            f"{number}. "
            f"{event['region']} "
            f"{event['title']}"
        )


    await update.message.reply_text(
        "\n\n".join(
            lines
        )
    )


# =========================================================
# /START
# =========================================================

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
        "Выбирай раздел 👇",

        reply_markup=MAIN_MENU,
    )


# =========================================================
# /MENU
# =========================================================

async def menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
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
    context: ContextTypes.DEFAULT_TYPE
):

    await run_news_request(
        update,
        context,
    )


# =========================================================
# /IMPORTANT
# =========================================================

async def important(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await run_news_request(
        update,
        context,
        important_only=True,
    )


# =========================================================
# КОМАНДЫ СТРАН
# =========================================================

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
            context,
            region_filter=region,
        )


# =========================================================
# /MANUTD 😈
# =========================================================

async def manutd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "Муха лох.\n"
        "Слабый везде 🤣"
    )


# =========================================================
# /STATUS
# =========================================================

def test_groq_connection():

    api_key = os.environ.get(
        "GROQ_API_KEY"
    )

    if not api_key:

        return (
            False,
            "нет ключа"
        )

    try:

        response = requests.get(
            "https://api.groq.com/"
            "openai/v1/models",

            headers={
                "Authorization":
                    f"Bearer {api_key}",
            },

            timeout=15,
        )

        if response.status_code != 200:

            return (
                False,
                f"HTTP "
                f"{response.status_code}"
            )


        model_ids = {
            item.get(
                "id"
            )

            for item in (
                response.json()
                .get(
                    "data",
                    []
                )
            )
        }


        if GROQ_MODEL in model_ids:

            return (
                True,
                "API и модель доступны"
            )


        return (
            False,
            "API работает, "
            "но модель не найдена"
        )


    except Exception:

        return (
            False,
            "нет ответа"
        )


def test_gemini_connection():

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:

        return (
            False,
            "нет ключа"
        )


    try:

        response = requests.get(
            "https://generativelanguage.googleapis.com/"
            "v1beta/models",

            headers={
                "x-goog-api-key":
                    api_key
            },

            timeout=15,
        )


        if response.status_code != 200:

            return (
                False,
                f"HTTP "
                f"{response.status_code}"
            )


        model_names = {
            item.get(
                "name",
                ""
            ).replace(
                "models/",
                ""
            )

            for item in (
                response.json()
                .get(
                    "models",
                    []
                )
            )
        }


        if GEMINI_MODEL in model_names:

            return (
                True,
                "API и модель доступны"
            )


        return (
            False,
            "API работает, "
            "но модель не найдена"
        )


    except Exception:

        return (
            False,
            "нет ответа"
        )


async def status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = (
        await update.message.reply_text(
            "🔎 Проверяю AI-сервисы..."
        )
    )


    groq_ok, groq_info = (
        test_groq_connection()
    )


    gemini_ok, gemini_info = (
        test_gemini_connection()
    )


    await message.edit_text(
        "🤖 Статус AI\n\n"

        f"Groq: "
        f"{'✅' if groq_ok else '❌'} "
        f"{groq_info}\n"

        f"Gemini: "
        f"{'✅' if gemini_ok else '❌'} "
        f"{gemini_info}"
    )


# =========================================================
# КНОПКИ ГЛАВНОГО МЕНЮ
# =========================================================

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


    if text == "⚡ Кратко":

        await brief(
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
            context,
            region_filter=region,
        )

        return


    await update.message.reply_text(
        "Выбери раздел "
        "кнопками ниже 👇",

        reply_markup=MAIN_MENU,
    )


# =========================================================
# TELEGRAM COMMAND MENU
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
                "brief",
                "5 новостей коротко"
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
                "Проверить AI"
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
            "brief",
            brief,
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


    # Скрытая пасхалка 😈
    app.add_handler(
        CommandHandler(
            "manutd",
            manutd,
        )
    )


    # Inline-кнопки под новостями
    app.add_handler(
        CallbackQueryHandler(
            news_callback
        )
    )


    # Главное меню
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
