import os, re, html, time, uuid, threading
import xml.etree.ElementTree as ET
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, HTTPServer

import feedparser, requests
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

    {
        "region": "🇪🇺 Европа",
        "source": "Euronews",
        "url": "https://www.euronews.com/rss?format=mrss&level=vertical&name=my-europe"
    },
    {
        "region": "🇪🇺 Европа",
        "source": "BBC",
        "url": "https://feeds.bbci.co.uk/news/world/europe/rss.xml"
    },

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


# =========================================================
# ГЛАВНОЕ МЕНЮ
# =========================================================

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["🔥 Главное", "⚡ Кратко"],
        ["📰 Все новости", "💰 Финансы"],
        ["🇰🇿 Казахстан", "🇺🇸 США"],
        ["🇪🇺 Европа", "🇨🇳 Китай"],
        ["🇷🇺 Россия", "🌍 Мир"],
        ["🤖 AI / технологии"],
    ],
    resize_keyboard=True,
)


BUTTON_TO_REGION = {
    x: x
    for x in [
        "🇰🇿 Казахстан",
        "🇺🇸 США",
        "🇪🇺 Европа",
        "🇨🇳 Китай",
        "🇷🇺 Россия",
        "🌍 Мир",
        "🤖 AI / технологии",
    ]
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


REGION_CODE_TO_LABEL = {
    "KZ": "🇰🇿 Казахстан",
    "US": "🇺🇸 США",
    "EUROPE": "🇪🇺 Европа",
    "CHINA": "🇨🇳 Китай",
    "RUSSIA": "🇷🇺 Россия",
    "WORLD": "🌍 Мир",
    "AI": "🤖 AI / технологии",
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


# =========================================================
# ТЕКСТ
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
        text
    )

    return " ".join(
        text
        .replace("\n", " ")
        .split()
    )


def protected_terms(text):

    tokens = re.findall(
        r"\b[A-Za-z0-9][A-Za-z0-9.+#&'_-]*\b",
        text or ""
    )

    result = []

    for token in tokens:

        special = (
            any(
                ch.isupper()
                for ch in token[1:]
            )
            or
            any(
                ch.isdigit()
                for ch in token
            )
            or
            (
                len(token) >= 2
                and token.isupper()
            )
        )

        if (
            special
            and token not in result
        ):
            result.append(
                token
            )

    return result[:12]


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

            articles.append(
                {
                    "source_region":
                        feed_info["region"],

                    "source":
                        feed_info["source"],

                    "title":
                        title,

                    "description":
                        description,

                    "link":
                        link,

                    "protected":
                        protected_terms(
                            title
                            + " "
                            + description
                        ),
                }
            )

        except Exception as error:

            print(
                f"RSS error "
                f"{feed_info['source']}:",
                repr(error)
            )

    return articles


# =========================================================
# PROMPT ДЛЯ AI
# =========================================================

def make_ai_prompt(
    articles
):

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

        protected = ", ".join(
            article.get(
                "protected",
                []
            )
        ) or "нет"

        blocks.append(
            f"""
NEWS_{index}
SOURCE_BUCKET: {article['source_region']}
SOURCE: {article['source']}
TITLE: {article['title']}
DESCRIPTION: {description}
PROTECTED_TERMS: {protected}
""".strip()
        )

    articles_text = "\n\n".join(
        blocks
    )

    return f"""
Ты редактор русскоязычного новостного агрегатора.

SOURCE_BUCKET — только технический раздел RSS.
Он НЕ означает место события.

Для каждого NEWS_:

1. Переведи заголовок на естественный русский.

2. Дай краткое описание:
максимум 1–2 предложения.

3. Используй только TITLE и DESCRIPTION.
Ничего не выдумывай.

4. Никогда не заменяй человека,
компанию, бренд или продукт на другого.

PROTECTED_TERMS сохраняй ТОЧНО.

Например:
MrBeast нельзя превращать в Microsoft.

5. Определи реальную категорию:

KZ = Казахстан
US = США
EUROPE = Европа
CHINA = Китай
RUSSIA = Россия
AI = AI / технологии
WORLD = всё остальное,
другая страна
или международное событие

6. Если публикации описывают
одно и то же конкретное событие,
дай им одинаковый EVENT_ID.

Если сомневаешься —
не объединяй.

7. Оцени масштаб:

HIGH
MEDIUM
LOW

8. Заявления,
обвинения,
предположения
и прогнозы
не представляй
как установленный факт.

Верни ровно одну строку
для каждого NEWS_.

Формат:

NEWS_0|||EVENT_1|||HIGH|||WORLD|||РУССКИЙ ЗАГОЛОВОК|||КРАТКОЕ ОПИСАНИЕ

Не используй Markdown.
Не используй JSON.
Не пиши пояснений.

Публикации:

{articles_text}
""".strip()


# =========================================================
# GROQ
# =========================================================

def call_groq(
    prompt
):

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
                            "role":
                                "user",

                            "content":
                                prompt,
                        }
                    ],

                    "temperature":
                        0.1,

                    "max_completion_tokens":
                        5000,

                    "reasoning_effort":
                        "low",

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
                    .strip()
                )

                if text:

                    print(
                        "AI provider: GROQ"
                    )

                    return text

            print(
                "Groq error:",
                response.status_code,
                response.text[:800],
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
                repr(error)
            )

            time.sleep(
                2 + attempt * 2
            )

    return None


# =========================================================
# GEMINI FALLBACK
# =========================================================

def call_gemini(
    prompt
):

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:
        return None

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent"
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
                            0.1,

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
                            "AI provider: "
                            "GEMINI FALLBACK"
                        )

                        return text

            print(
                "Gemini error:",
                response.status_code,
                response.text[:800],
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
                repr(error)
            )

            time.sleep(
                2 + attempt * 2
            )

    return None


def ask_ai(
    prompt
):

    return (
        call_groq(prompt)
        or
        call_gemini(prompt)
    )


# =========================================================
# РАЗБОР AI
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
            5
        )

        if len(pieces) != 6:
            continue

        try:

            index = int(
                pieces[0]
                .replace(
                    "NEWS_",
                    ""
                )
            )

        except ValueError:

            continue

        if not (
            0
            <= index
            < article_count
        ):
            continue

        impact = (
            pieces[2]
            .strip()
            .upper()
        )

        region = (
            pieces[3]
            .strip()
            .upper()
        )

        if impact not in IMPACT_RANK:

            impact = "MEDIUM"

        processed[index] = {

            "event_id":
                pieces[1].strip()
                or
                f"EVENT_{index}",

            "impact":
                impact,

            "display_region":
                REGION_CODE_TO_LABEL.get(
                    region,
                    "🌍 Мир"
                ),

            "title_ru":
                pieces[4].strip(),

            "summary_ru":
                pieces[5].strip(),
        }

    return processed


def process_articles_with_ai(
    articles
):

    prompt = make_ai_prompt(
        articles
    )

    groq_result = parse_ai_response(
        call_groq(prompt),
        len(articles)
    )

    if (
        len(groq_result)
        ==
        len(articles)
    ):

        return groq_result

    gemini_result = parse_ai_response(
        call_gemini(prompt),
        len(articles)
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

        merged.setdefault(
            index,
            item
        )

    return merged or None


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

        result.setdefault(
            index,
            {
                "event_id":
                    f"FALLBACK_{index}",

                "impact":
                    "MEDIUM",

                "display_region":
                    article["source_region"],

                "title_ru":
                    article["title"],

                "summary_ru":
                    "",
            }
        )

    return result


# =========================================================
# ОБЪЕДИНЕНИЕ СОБЫТИЙ
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
            f"FALLBACK_{index}"
        )

        if event_id not in events:

            events[event_id] = {

                "region":
                    data.get(
                        "display_region",
                        article["source_region"]
                    ),

                "title":
                    data.get(
                        "title_ru",
                        article["title"]
                    ),

                "summary":
                    data.get(
                        "summary_ru",
                        ""
                    ),

                "impact":
                    data.get(
                        "impact",
                        "MEDIUM"
                    ),

                "sources":
                    [],
            }

        events[event_id][
            "sources"
        ].append(
            {
                "name":
                    article["source"],

                "link":
                    article["link"],
            }
        )

    return list(
        events.values()
    )


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

        if key not in seen:

            seen.add(
                key
            )

            result.append(
                source
            )

    return result


# =========================================================
# КНОПКИ ПОД НОВОСТЬЮ
# =========================================================

def save_event_card(
    application,
    event
):

    card_id = (
        uuid.uuid4()
        .hex[:12]
    )

    cards = (
        application.bot_data
        .setdefault(
            "event_cards",
            {}
        )
    )

    cards[card_id] = event

    while len(cards) > 300:

        cards.pop(
            next(
                iter(cards)
            ),
            None
        )

    return card_id


def make_news_keyboard(
    card_id
):

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📖 Подробнее",
                    callback_data=
                        f"d:{card_id}"
                ),

                InlineKeyboardButton(
                    "💡 Почему важно?",
                    callback_data=
                        f"w:{card_id}"
                ),
            ],

            [
                InlineKeyboardButton(
                    "🗞 Источники",
                    callback_data=
                        f"s:{card_id}"
                )
            ],
        ]
    )


async def send_events(
    update,
    context,
    events
):

    for event in events:

        event["sources"] = (
            unique_sources(
                event["sources"]
            )
        )

        source_names = []

        for source in (
            event["sources"]
        ):

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
                +
                " • ".join(
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

        await update.message.reply_text(
            message,

            disable_web_page_preview=True,

            reply_markup=
                make_news_keyboard(
                    card_id
                ),
        )


# =========================================================
# ПОДРОБНЕЕ / ПОЧЕМУ ВАЖНО
# =========================================================

def make_details_prompt(
    event
):

    return (
        f"Заголовок: {event['title']}\n"
        f"Описание: {event['summary']}\n\n"

        "Объясни подробнее на русском "
        "максимум в 5 коротких предложениях. "

        "Используй только данные карточки. "
        "Ничего не выдумывай. "

        "Сохраняй нейтральный тон. "
        "Если данных мало — скажи об этом."
    )


def make_why_prompt(
    event
):

    return (
        f"Заголовок: {event['title']}\n"
        f"Описание: {event['summary']}\n\n"

        "Объясни нейтрально, "
        "почему событие может иметь значение. "

        "2–4 коротких предложения. "
        "Не выдумывай факты. "
        "Не драматизируй. "

        "Если последствия неизвестны — "
        "скажи об этом."
    )


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

    event = (
        context.application.bot_data
        .get(
            "event_cards",
            {}
        )
        .get(
            card_id
        )
    )

    if not event:

        await query.message.reply_text(
            "Эта карточка уже устарела 🙂\n"
            "Запроси новости заново."
        )

        return

    if action == "s":

        buttons = []

        for source in event["sources"]:

            link = source.get(
                "link",
                ""
            )

            if link.startswith(
                (
                    "http://",
                    "https://"
                )
            ):

                buttons.append(
                    [
                        InlineKeyboardButton(
                            "🔗 "
                            + source["name"],

                            url=link
                        )
                    ]
                )

        if buttons:

            await query.message.reply_text(
                "🗞 Открыть источники:",

                reply_markup=
                    InlineKeyboardMarkup(
                        buttons
                    )
            )

        else:

            await query.message.reply_text(
                "Для этой новости "
                "нет доступных ссылок."
            )

        return

    if action == "d":

        cache_key = "_details"
        title = "📖 Подробнее"
        wait_text = "📖 Готовлю подробности..."
        prompt = make_details_prompt(
            event
        )

    else:

        cache_key = "_why"
        title = "💡 Почему это важно?"
        wait_text = "💡 Анализирую значение..."
        prompt = make_why_prompt(
            event
        )

    if event.get(
        cache_key
    ):

        await query.message.reply_text(
            title
            + "\n\n"
            + event[cache_key]
        )

        return

    wait_message = (
        await query.message.reply_text(
            wait_text
        )
    )

    answer = ask_ai(
        prompt
    )

    if not answer:

        await wait_message.edit_text(
            "⚠️ AI сейчас временно "
            "не смог подготовить ответ."
        )

        return

    event[cache_key] = answer

    await wait_message.edit_text(
        title
        + "\n\n"
        + answer
    )


# =========================================================
# 💰 ФИНАНСЫ — БЕЗ AI
# =========================================================

def xml_child_text(
    item,
    name
):

    for child in list(
        item
    ):

        if (
            child.tag
            .split("}")[-1]
            .lower()
            ==
            name.lower()
        ):

            return (
                child.text
                or
                ""
            ).strip()

    return ""


def to_float(
    value
):

    if value is None:
        return None

    match = re.search(
        r"-?\d+(?:[.,]\d+)?",
        str(value)
        .replace(
            " ",
            ""
        )
    )

    if not match:
        return None

    try:

        return float(
            match.group(0)
            .replace(
                ",",
                "."
            )
        )

    except ValueError:

        return None


def fetch_nbk_rates():

    response = requests.get(

        "https://nationalbank.kz/"
        "rss/rates_all.xml",

        headers={
            "User-Agent":
                "Mozilla/5.0 NewsBot/1.0"
        },

        timeout=20,
    )

    response.raise_for_status()

    root = ET.fromstring(
        response.content
    )

    wanted = {
        "USD",
        "EUR",
        "GBP",
        "CNY",
        "RUB",
    }

    rates = {}

    for item in root.iter():

        if (
            item.tag
            .split("}")[-1]
            .lower()
            !=
            "item"
        ):

            continue

        code = (
            xml_child_text(
                item,
                "title"
            )
            .upper()
            .strip()
        )

        if code not in wanted:
            continue

        value = to_float(
            xml_child_text(
                item,
                "description"
            )
        )

        quantity = (
            to_float(
                xml_child_text(
                    item,
                    "quant"
                )
            )
            or
            1.0
        )

        if value is None:
            continue

        if quantity <= 0:
            quantity = 1.0

        # НБК иногда публикует курс
        # за несколько единиц валюты.
        # Пересчитываем на 1 единицу.
        rates[code] = (
            value
            /
            quantity
        )

    return rates


def fetch_coinbase_spot(
    pair
):

    response = requests.get(

        f"https://api.coinbase.com/"
        f"v2/prices/{pair}/spot",

        headers={
            "User-Agent":
                "Mozilla/5.0 NewsBot/1.0"
        },

        timeout=20,
    )

    response.raise_for_status()

    return to_float(
        response.json()
        .get(
            "data",
            {}
        )
        .get(
            "amount"
        )
    )


def format_usd_price(
    value
):

    if value is None:
        return "н/д"

    if value >= 1000:

        return (
            f"${value:,.0f}"
            .replace(
                ",",
                " "
            )
        )

    return (
        f"${value:,.2f}"
        .replace(
            ",",
            " "
        )
    )


async def markets(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = (
        await update.message.reply_text(
            "💰 Обновляю финансовые данные..."
        )
    )

    try:

        rates = fetch_nbk_rates()

    except Exception as error:

        print(
            "NBK error:",
            repr(error)
        )

        rates = {}

    try:

        btc = fetch_coinbase_spot(
            "BTC-USD"
        )

    except Exception as error:

        print(
            "BTC error:",
            repr(error)
        )

        btc = None

    try:

        eth = fetch_coinbase_spot(
            "ETH-USD"
        )

    except Exception as error:

        print(
            "ETH error:",
            repr(error)
        )

        eth = None

    lines = [
        "💰 Финансы",
        "",
    ]

    if rates:

        lines.append(
            "💱 Официальный курс НБК"
        )

        currencies = [
            (
                "USD",
                "🇺🇸",
                "доллар"
            ),

            (
                "EUR",
                "🇪🇺",
                "евро"
            ),

            (
                "GBP",
                "🇬🇧",
                "фунт стерлингов"
            ),

            (
                "CNY",
                "🇨🇳",
                "юань"
            ),

            (
                "RUB",
                "🇷🇺",
                "рубль"
            ),
        ]

        for (
            code,
            emoji,
            name
        ) in currencies:

            value = rates.get(
                code
            )

            if value is not None:

                lines.append(
                    f"{emoji} "
                    f"1 {code} "
                    f"({name}) = "
                    f"{value:.2f} ₸"
                )

    else:

        lines.append(
            "💱 Курсы НБК "
            "сейчас недоступны"
        )

    lines += [
        "",
        "🪙 Крипто",

        "₿ BTC/USD ≈ "
        + format_usd_price(
            btc
        ),

        "◆ ETH/USD ≈ "
        + format_usd_price(
            eth
        ),

        "",

        "🏦 Валюты — официальный курс "
        "Национального Банка Казахстана.",

        "🪙 Крипто — публичная "
        "spot-цена Coinbase.",

        "ℹ️ Курс НБК — не курс покупки/"
        "продажи в банке или обменнике.",
    ]

    await message.edit_text(
        "\n".join(
            lines
        )
    )


# =========================================================
# НОВОСТИ
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
            "🧠 Анализирую события"
        )

    elif region_filter:

        status_text = (
            f"🔎 Собираю: "
            f"{region_filter}"
        )

    else:

        status_text = (
            "🔎 Собираю новости..."
        )

    status = (
        await update.message.reply_text(
            status_text
        )
    )

    articles = collect_articles(
        region_filter
    )

    if not articles:

        await status.edit_text(
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
        and important_only
    ):

        await status.edit_text(
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
        processed
    )

    if (
        region_filter
        and
        not ai_failed
    ):

        events = [
            event

            for event in events

            if (
                event["region"]
                ==
                region_filter
            )
        ]

    if important_only:

        events = [
            event

            for event in events

            if (
                event["impact"]
                ==
                "HIGH"
            )

        ][:5]

    try:

        await status.delete()

    except Exception:

        pass

    if not events:

        await update.message.reply_text(
            "Подходящих свежих событий "
            "сейчас нет."
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
        events
    )


# =========================================================
# КРАТКО
# =========================================================

async def brief(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    status = (
        await update.message.reply_text(
            "⚡ Собираю короткую сводку..."
        )
    )

    articles = collect_articles()

    if not articles:

        await status.edit_text(
            "❌ Сейчас не удалось "
            "получить новости."
        )

        return

    processed = (
        process_articles_with_ai(
            articles
        )
    )

    if processed is None:

        await status.edit_text(
            "⚠️ AI сейчас не ответил.\n"
            "Без него не буду "
            "составлять сводку наугад."
        )

        return

    events = group_articles(

        articles,

        fallback_processed(
            articles,
            processed
        )
    )

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

        reverse=True
    )

    try:

        await status.delete()

    except Exception:

        pass

    top_events = events[:5]

    text = (
        "⚡ Коротко: 5 событий\n\n"
        +
        "\n\n".join(

            f"{number}. "
            f"{event['region']} "
            f"{event['title']}"

            for number, event
            in enumerate(
                top_events,
                1
            )
        )
    )

    await update.message.reply_text(
        text
    )


# =========================================================
# КОМАНДЫ
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

        reply_markup=
            MAIN_MENU,
    )


async def menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "Выбирай раздел 👇",

        reply_markup=
            MAIN_MENU
    )


async def news(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await run_news_request(
        update,
        context
    )


async def important(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await run_news_request(
        update,
        context,
        important_only=True
    )


async def manutd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "Муха лох.\n"
        "Слабый везде 🤣"
    )


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

    region = (
        COMMAND_TO_REGION.get(
            command
        )
    )

    if region:

        await run_news_request(
            update,
            context,
            region_filter=
                region
        )


# =========================================================
# STATUS
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
                    f"Bearer {api_key}"
            },

            timeout=15,
        )

        if response.status_code != 200:

            return (
                False,
                f"HTTP "
                f"{response.status_code}"
            )

        models = {
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

        if GROQ_MODEL in models:

            return (
                True,
                "API и модель доступны"
            )

        return (
            False,
            "модель не найдена"
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

        models = {

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

        if GEMINI_MODEL in models:

            return (
                True,
                "API и модель доступны"
            )

        return (
            False,
            "модель не найдена"
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
# КНОПКИ МЕНЮ
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

        return await important(
            update,
            context
        )

    if text == "⚡ Кратко":

        return await brief(
            update,
            context
        )

    if text == "📰 Все новости":

        return await news(
            update,
            context
        )

    if text == "💰 Финансы":

        return await markets(
            update,
            context
        )

    region = (
        BUTTON_TO_REGION.get(
            text
        )
    )

    if region:

        return await run_news_request(
            update,
            context,
            region_filter=
                region
        )

    await update.message.reply_text(
        "Выбери раздел кнопками ниже 👇",

        reply_markup=
            MAIN_MENU
    )


# =========================================================
# СПИСОК КОМАНД TELEGRAM
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
                "markets",
                "Финансы"
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
        target=
            run_web_server,

        daemon=True
    ).start()

    app = (
        Application.builder()

        .token(
            os.environ[
                "TELEGRAM_BOT_TOKEN"
            ]
        )

        .post_init(
            post_init
        )

        .build()
    )

    handlers = [
        (
            "start",
            start
        ),

        (
            "menu",
            menu
        ),

        (
            "news",
            news
        ),

        (
            "brief",
            brief
        ),

        (
            "important",
            important
        ),

        (
            "markets",
            markets
        ),

        (
            "status",
            status
        ),

        (
            "manutd",
            manutd
        ),
    ]

    for command, function in handlers:

        app.add_handler(
            CommandHandler(
                command,
                function
            )
        )

    for command in COMMAND_TO_REGION:

        app.add_handler(
            CommandHandler(
                command,
                region_command
            )
        )

    app.add_handler(
        CallbackQueryHandler(
            news_callback
        )
    )

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
