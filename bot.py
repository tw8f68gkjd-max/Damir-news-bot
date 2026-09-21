import os
import re
import html
import time
import uuid
import threading
import calendar
import xml.etree.ElementTree as ET

from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urljoin

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
# АКТУАЛЬНОСТЬ И КАЧЕСТВО
# =========================================================

# Берём до 8 свежих публикаций с каждой RSS.
# Но в итог они попадают НЕ по порядку RSS.
ARTICLES_PER_FEED = 8

# Новости старше 24 часов не показываем.
FRESH_HOURS = 24

# Ограничение одного AI-запроса.
MAX_AI_ARTICLES = 36

# Сколько итоговых карточек показываем.
MAX_NEWS_EVENTS = 15
MAX_REGION_EVENTS = 10
MAX_SPORT_EVENTS = 12


# =========================================================
# ИСТОЧНИКИ
# =========================================================

# publisher = независимая редакция.
# Например:
# BBC Sport + BBC Football = одна редакция BBC Sport.
#
# Поэтому бот не будет писать "2 источника",
# если событие найдено в двух RSS одного СМИ.

NEWS_FEEDS = [

    # -------------------------
    # КАЗАХСТАН
    # -------------------------

    {
        "region": "🇰🇿 Казахстан",
        "source": "Kazinform",
        "publisher": "Kazinform",
        "url": "https://qazinform.com/rss/en.xml",
    },

    {
        "region": "🇰🇿 Казахстан",
        "source": "The Astana Times",
        "publisher": "The Astana Times",
        "url": "https://astanatimes.com/feed/",
    },


    # -------------------------
    # США
    # -------------------------

    {
        "region": "🇺🇸 США",
        "source": "NPR",
        "publisher": "NPR",
        "url": "https://feeds.npr.org/1003/rss.xml",
    },

    {
        "region": "🇺🇸 США",
        "source": "BBC",
        "publisher": "BBC",
        "url": "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
    },


    # -------------------------
    # ЕВРОПА
    # -------------------------

    {
        "region": "🇪🇺 Европа",
        "source": "Euronews",
        "publisher": "Euronews",
        "url": "https://www.euronews.com/rss?format=mrss&level=vertical&name=my-europe",
    },

    {
        "region": "🇪🇺 Европа",
        "source": "BBC",
        "publisher": "BBC",
        "url": "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
    },


    # -------------------------
    # КИТАЙ
    # -------------------------

    {
        "region": "🇨🇳 Китай",
        "source": "China News Service",
        "publisher": "China News Service",
        "url": "https://www.chinanews.com.cn/rss/china.xml",
    },

    {
        "region": "🇨🇳 Китай",
        "source": "BBC",
        "publisher": "BBC",
        "url": "https://feeds.bbci.co.uk/news/world/asia/china/rss.xml",
    },


    # -------------------------
    # РОССИЯ
    # -------------------------

    {
        "region": "🇷🇺 Россия",
        "source": "Интерфакс",
        "publisher": "Интерфакс",
        "url": "https://www.interfax.ru/rss.asp",
    },

    {
        "region": "🇷🇺 Россия",
        "source": "Meduza",
        "publisher": "Meduza",
        "url": "https://meduza.io/rss2/all",
    },


    # -------------------------
    # МИР
    # -------------------------

    {
        "region": "🌍 Мир",
        "source": "Euronews",
        "publisher": "Euronews",
        "url": "https://www.euronews.com/rss?format=mrss&level=theme&name=news",
    },

    {
        "region": "🌍 Мир",
        "source": "BBC",
        "publisher": "BBC",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
    },


    # -------------------------
    # AI / ТЕХНОЛОГИИ
    # -------------------------

    {
        "region": "🤖 AI / технологии",
        "source": "TechCrunch",
        "publisher": "TechCrunch",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
    },

    {
        "region": "🤖 AI / технологии",
        "source": "The Verge",
        "publisher": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
    },


    # =====================================================
    # СПОРТ
    # =====================================================

    # Общий BBC Sport
    {
        "region": "🏆 Спорт",
        "source": "BBC Sport",
        "publisher": "BBC Sport",
        "url": "https://feeds.bbci.co.uk/sport/rss.xml",
    },

    # Футбол BBC
    {
        "region": "🏆 Спорт",
        "source": "BBC Sport • Football",
        "publisher": "BBC Sport",
        "url": "https://feeds.bbci.co.uk/sport/football/rss.xml",
    },

    # Общий Guardian Sport
    {
        "region": "🏆 Спорт",
        "source": "The Guardian Sport",
        "publisher": "The Guardian",
        "url": "https://www.theguardian.com/sport/rss",
    },

    # Футбол Guardian
    {
        "region": "🏆 Спорт",
        "source": "The Guardian Football",
        "publisher": "The Guardian",
        "url": "https://www.theguardian.com/football/rss",
    },

    # Общий CBS
    {
        "region": "🏆 Спорт",
        "source": "CBS Sports",
        "publisher": "CBS Sports",
        "url": "https://www.cbssports.com/rss/headlines/",
    },

    # Футбол CBS
    {
        "region": "🏆 Спорт",
        "source": "CBS Sports • Soccer",
        "publisher": "CBS Sports",
        "url": "https://www.cbssports.com/rss/headlines/soccer",
    },

    # NBA
    {
        "region": "🏆 Спорт",
        "source": "CBS Sports • NBA",
        "publisher": "CBS Sports",
        "url": "https://www.cbssports.com/rss/headlines/nba",
    },

    # Теннис
    {
        "region": "🏆 Спорт",
        "source": "CBS Sports • Tennis",
        "publisher": "CBS Sports",
        "url": "https://www.cbssports.com/rss/headlines/tennis",
    },
]


# =========================================================
# ГЛАВНОЕ МЕНЮ
# =========================================================

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["🔥 Главное", "⚡ Кратко"],

        ["📰 Все новости", "🏆 Спорт"],

        ["💰 Финансы"],

        ["🇰🇿 Казахстан", "🇺🇸 США"],

        ["🇪🇺 Европа", "🇨🇳 Китай"],

        ["🇷🇺 Россия", "🌍 Мир"],

        ["🤖 AI / технологии"],
    ],

    resize_keyboard=True,
)


# =========================================================
# МЕНЮ СПОРТА
# =========================================================

SPORT_MENU = ReplyKeyboardMarkup(
    [
        ["🏆 Весь спорт"],

        ["⚽ Футбол", "🏎 F1"],

        ["🏀 Баскетбол", "🎾 Теннис"],

        ["⬅️ Главное меню"],
    ],

    resize_keyboard=True,
)


REGION_BUTTONS = {

    "🇰🇿 Казахстан",
    "🇺🇸 США",
    "🇪🇺 Европа",
    "🇨🇳 Китай",
    "🇷🇺 Россия",
    "🌍 Мир",
    "🤖 AI / технологии",
}


COMMAND_TO_REGION = {

    "kz":
        "🇰🇿 Казахстан",

    "usa":
        "🇺🇸 США",

    "europe":
        "🇪🇺 Европа",

    "china":
        "🇨🇳 Китай",

    "russia":
        "🇷🇺 Россия",

    "world":
        "🌍 Мир",

    "ai":
        "🤖 AI / технологии",
}


SPORT_FILTERS = {

    "⚽ Футбол":
        "⚽ Футбол",

    "🏎 F1":
        "🏎 F1",

    "🏀 Баскетбол":
        "🏀 Баскетбол",

    "🎾 Теннис":
        "🎾 Теннис",
}


SPORT_COMMANDS = {

    "football":
        "⚽ Футбол",

    "f1":
        "🏎 F1",

    "basketball":
        "🏀 Баскетбол",

    "tennis":
        "🎾 Теннис",
}


# =========================================================
# КОДЫ КАТЕГОРИЙ ОТ AI
# =========================================================

REGION_CODE_TO_LABEL = {

    "KZ":
        "🇰🇿 Казахстан",

    "US":
        "🇺🇸 США",

    "EUROPE":
        "🇪🇺 Европа",

    "CHINA":
        "🇨🇳 Китай",

    "RUSSIA":
        "🇷🇺 Россия",

    "WORLD":
        "🌍 Мир",

    "AI":
        "🤖 AI / технологии",

    "SPORT_FOOTBALL":
        "⚽ Футбол",

    "SPORT_F1":
        "🏎 F1",

    "SPORT_BASKETBALL":
        "🏀 Баскетбол",

    "SPORT_TENNIS":
        "🎾 Теннис",

    "SPORT_OTHER":
        "🏆 Другой спорт",
}


SPORT_LABELS = {

    "⚽ Футбол",

    "🏎 F1",

    "🏀 Баскетбол",

    "🎾 Теннис",

    "🏆 Другой спорт",
}


IMPACT_RANK = {

    "LOW": 1,

    "MEDIUM": 2,

    "HIGH": 3,
}


# =========================================================
# КОМПЛИМЕНТЫ ДЛЯ ЗАРИНЫ
# =========================================================

ALMATY_TZ = ZoneInfo(
    "Asia/Almaty"
)


COMPLIMENTS = [

    "Зарина, у тебя редкое сочетание любопытства "
    "и умения доводить идеи до результата.",

    "Зарина, ты умеешь замечать детали, "
    "которые другие легко пропускают.",

    "Зарина, твоя настойчивость — тихая суперсила: "
    "если тебе что-то действительно нужно, "
    "ты докопаешься до работающего решения.",

    "Зарина, у тебя есть талант превращать сырую идею "
    "в вещь, которой реально хочется пользоваться.",

    "Зарина, у тебя отлично получается не соглашаться "
    "на «и так сойдёт» — и именно поэтому "
    "результат становится лучше.",

    "Зарина, ты умеешь сочетать здравый смысл "
    "с фантазией — редкая и очень полезная смесь.",

    "Зарина, у тебя хороший внутренний радар "
    "на то, что можно сделать удобнее, "
    "понятнее и интереснее.",

    "Зарина, твоя требовательность к качеству — "
    "это уважение к собственному времени.",

    "Зарина, у тебя есть вкус к хорошим идеям — "
    "и ещё более ценный навык быстро отсеивать плохие.",

    "Зарина, ты умеешь задать именно тот вопрос, "
    "после которого всё начинает складываться.",

    "Зарина, ты умеешь быстро переходить "
    "от «а что если?» к «так, давай сделаем».",

    "Зарина, у тебя классный баланс между "
    "«хочу красиво» и «должно нормально работать».",

    "Зарина, сегодня тебе полагается официальный "
    "комплимент: ты заметно интереснее "
    "среднестатистического понедельника 😄",
]


# =========================================================
# КАРТИНКИ
# =========================================================

BAD_IMAGE_WORDS = (

    "logo",
    "favicon",
    "icon",
    "avatar",
    "sprite",
    "badge",
    "advert",
    "/ads/",
    "placeholder",
    "default-image",
    "1x1",
)


# =========================================================
# WEB SERVER ДЛЯ RENDER
# =========================================================

class HealthHandler(
    BaseHTTPRequestHandler
):

    def do_GET(
        self
    ):

        self.send_response(
            200
        )

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
            10000,
        )
    )

    server = HTTPServer(
        (
            "0.0.0.0",
            port,
        ),

        HealthHandler,
    )

    print(
        f"Web server started on port {port}"
    )

    server.serve_forever()


# =========================================================
# ОЧИСТКА ТЕКСТА
# =========================================================

def clean_text(
    text
):

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

    return " ".join(
        text
        .replace(
            "\n",
            " ",
        )
        .split()
    )


# =========================================================
# ЗАЩИТА ИМЁН И БРЕНДОВ
# =========================================================

def protected_terms(
    text
):

    tokens = re.findall(
        r"\b[A-Za-z0-9][A-Za-z0-9.+#&'_-]*\b",
        text or "",
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
                and
                token.isupper()
            )
        )

        if (
            special
            and
            token not in result
        ):

            result.append(
                token
            )

    return result[:14]


# =========================================================
# КАРТИНКИ
# =========================================================

def normalize_image_url(
    url,
    base_url=""
):

    if not url:

        return None

    url = html.unescape(
        str(url)
    ).strip()

    if url.startswith(
        "//"
    ):

        url = (
            "https:"
            + url
        )

    elif base_url:

        url = urljoin(
            base_url,
            url,
        )

    if not url.startswith(
        (
            "http://",
            "https://",
        )
    ):

        return None

    if any(
        word in url.lower()

        for word in BAD_IMAGE_WORDS
    ):

        return None

    return url


def image_from_feed_entry(
    entry,
    article_url=""
):

    candidates = []

    for item in (
        entry.get(
            "media_content",
            [],
        )
        or
        []
    ):

        if isinstance(
            item,
            dict,
        ):

            candidates.append(
                item.get(
                    "url"
                )
            )

    for item in (
        entry.get(
            "media_thumbnail",
            [],
        )
        or
        []
    ):

        if isinstance(
            item,
            dict,
        ):

            candidates.append(
                item.get(
                    "url"
                )
            )

    for item in (
        entry.get(
            "enclosures",
            [],
        )
        or
        []
    ):

        if not isinstance(
            item,
            dict,
        ):

            continue

        media_type = (
            item.get(
                "type"
            )
            or
            ""
        ).lower()

        if media_type.startswith(
            "image/"
        ):

            candidates.append(
                item.get(
                    "href"
                )
                or
                item.get(
                    "url"
                )
            )

    for candidate in candidates:

        image_url = (
            normalize_image_url(
                candidate,
                article_url,
            )
        )

        if image_url:

            return image_url

    return None


def image_from_article_page(
    article_url
):

    if (
        not article_url

        or

        not article_url.startswith(
            (
                "http://",
                "https://",
            )
        )
    ):

        return None

    try:

        response = requests.get(
            article_url,

            headers={
                "User-Agent":
                    "Mozilla/5.0 NewsBot/1.0"
            },

            timeout=10,
        )

        response.raise_for_status()

        page = (
            response.text[
                :600000
            ]
        )

        patterns = [

            r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image|twitter:image:src)["\'][^>]+content=["\']([^"\']+)["\']',

            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image|twitter:image:src)["\']',
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                page,
                flags=re.IGNORECASE,
            )

            if match:

                image_url = (
                    normalize_image_url(
                        match.group(1),
                        article_url,
                    )
                )

                if image_url:

                    return image_url

    except Exception as error:

        print(
            "Image page error:",
            repr(error),
        )

    return None


# =========================================================
# ВРЕМЯ ПУБЛИКАЦИИ
# =========================================================

def parse_entry_timestamp(
    entry
):

    for key in (

        "published_parsed",

        "updated_parsed",

        "created_parsed",
    ):

        parsed = (
            entry.get(
                key
            )
        )

        if parsed:

            try:

                return float(
                    calendar.timegm(
                        parsed
                    )
                )

            except Exception:

                pass

    for key in (

        "published",

        "updated",

        "created",
    ):

        raw = (
            entry.get(
                key
            )
        )

        if not raw:

            continue

        try:

            dt = (
                parsedate_to_datetime(
                    str(raw)
                )
            )

            if dt.tzinfo is None:

                dt = dt.replace(
                    tzinfo=
                        timezone.utc
                )

            return (
                dt.timestamp()
            )

        except Exception:

            pass

        try:

            dt = (
                datetime.fromisoformat(
                    str(raw)
                    .replace(
                        "Z",
                        "+00:00",
                    )
                )
            )

            if dt.tzinfo is None:

                dt = dt.replace(
                    tzinfo=
                        timezone.utc
                )

            return (
                dt.timestamp()
            )

        except Exception:

            pass

    return None


# =========================================================
# ЗАГРУЗКА ОДНОГО RSS
# =========================================================

def fetch_feed_articles(
    feed_info
):

    result = []

    try:

        response = requests.get(
            feed_info[
                "url"
            ],

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

        now_ts = (
            time.time()
        )

        max_age = (
            FRESH_HOURS
            *
            3600
        )

        for entry in (
            feed.entries[
                :ARTICLES_PER_FEED
            ]
        ):

            title = clean_text(
                entry.get(
                    "title",
                    "",
                )
            )

            if not title:

                continue

            published_ts = (
                parse_entry_timestamp(
                    entry
                )
            )

            # Если RSS вообще не сообщает
            # время публикации,
            # не называем материал свежим наугад.
            if published_ts is None:

                continue

            age = (
                now_ts
                -
                published_ts
            )

            # Старше 24 часов.
            if age > max_age:

                continue

            # Защита от неправильной даты
            # сильно из будущего.
            if age < (
                -6
                *
                3600
            ):

                continue

            description = (
                clean_text(
                    entry.get(
                        "summary",

                        entry.get(
                            "description",
                            "",
                        ),
                    )
                )
            )

            link = (
                entry.get(
                    "link",
                    "",
                )
            )

            result.append(
                {
                    "source_region":
                        feed_info[
                            "region"
                        ],

                    "source":
                        feed_info[
                            "source"
                        ],

                    "publisher":
                        feed_info.get(
                            "publisher",

                            feed_info[
                                "source"
                            ],
                        ),

                    "title":
                        title,

                    "description":
                        description,

                    "link":
                        link,

                    "published_ts":
                        published_ts,

                    "image_url":
                        image_from_feed_entry(
                            entry,
                            link,
                        ),

                    "protected":
                        protected_terms(
                            title
                            +
                            " "
                            +
                            description
                        ),
                }
            )

    except Exception as error:

        print(
            f"RSS error "
            f"{feed_info['source']}:",
            repr(error),
        )

    return result


# =========================================================
# СОБИРАЕМ ВСЕ RSS
# =========================================================

def collect_articles(
    region_filter=None
):

    feeds = [

        feed

        for feed in NEWS_FEEDS

        if (
            not region_filter

            or

            feed[
                "region"
            ]
            ==
            region_filter
        )
    ]

    if not feeds:

        return []

    articles = []

    # Все RSS загружаем параллельно.
    with ThreadPoolExecutor(
        max_workers=
            min(
                10,
                len(feeds),
            )
    ) as executor:

        futures = [

            executor.submit(
                fetch_feed_articles,
                feed,
            )

            for feed in feeds
        ]

        for future in (
            as_completed(
                futures
            )
        ):

            try:

                articles.extend(
                    future.result()
                )

            except Exception as error:

                print(
                    "RSS worker error:",
                    repr(error),
                )

    # Убираем точные дубликаты.
    unique = []

    seen = set()

    for article in articles:

        key = (
            article.get(
                "link"
            )

            or

            (
                article.get(
                    "publisher"
                ),

                article.get(
                    "title"
                ),
            )
        )

        if key in seen:

            continue

        seen.add(
            key
        )

        unique.append(
            article
        )

    # На вход AI сначала идут свежие.
    unique.sort(

        key=lambda item:
            item.get(
                "published_ts",
                0,
            ),

        reverse=True,
    )

    return unique


# =========================================================
# ОТБОР КАНДИДАТОВ ДЛЯ AI
# =========================================================

def select_articles_for_ai(
    articles
):

    # Не даём одной редакции
    # заполнить весь AI-запрос.

    by_publisher = defaultdict(
        list
    )

    for article in articles:

        publisher = (
            article.get(
                "publisher",

                article.get(
                    "source"
                ),
            )
        )

        by_publisher[
            publisher
        ].append(
            article
        )

    selected = []

    used = set()

    # Сначала до 3 свежих материалов
    # от каждой независимой редакции.
    for round_index in range(
        3
    ):

        for publisher in sorted(
            by_publisher
        ):

            items = (
                by_publisher[
                    publisher
                ]
            )

            if (
                round_index
                >=
                len(
                    items
                )
            ):

                continue

            article = (
                items[
                    round_index
                ]
            )

            key = (
                article.get(
                    "link"
                )

                or

                id(
                    article
                )
            )

            if key in used:

                continue

            selected.append(
                article
            )

            used.add(
                key
            )

            if (
                len(
                    selected
                )
                >=
                MAX_AI_ARTICLES
            ):

                selected.sort(

                    key=lambda item:
                        item.get(
                            "published_ts",
                            0,
                        ),

                    reverse=True,
                )

                return selected

    # Оставшиеся места —
    # самые свежие статьи,
    # которые ещё не выбраны.
    for article in articles:

        key = (
            article.get(
                "link"
            )

            or

            id(
                article
            )
        )

        if key in used:

            continue

        selected.append(
            article
        )

        used.add(
            key
        )

        if (
            len(
                selected
            )
            >=
            MAX_AI_ARTICLES
        ):

            break

    selected.sort(

        key=lambda item:
            item.get(
                "published_ts",
                0,
            ),

        reverse=True,
    )

    return selected


# =========================================================
# PROMPT AI
# =========================================================

def make_ai_prompt(
    articles
):

    blocks = []

    for (
        index,
        article,
    ) in enumerate(
        articles
    ):

        protected = ", ".join(
            article.get(
                "protected",
                [],
            )
        ) or "нет"

        description = (
            clean_text(
                article.get(
                    "description",
                    "",
                )
            )[
                :700
            ]
        )

        blocks.append(
            f"""
NEWS_{index}
SOURCE_BUCKET: {article['source_region']}
SOURCE: {article['source']}
PUBLISHER: {article['publisher']}
TITLE: {article['title']}
DESCRIPTION: {description}
PROTECTED_TERMS: {protected}
""".strip()
        )

    articles_text = (
        "\n\n".join(
            blocks
        )
    )

    return f"""
Ты редактор русскоязычного новостного агрегатора.

ВАЖНО:
порядок статьи в RSS НЕ означает,
что она важнее других.

Нужно оценивать само событие.

Для каждого NEWS_:

1. Переведи заголовок
на естественный русский язык.

2. Дай краткое описание
максимум в 1–2 предложениях.

3. Используй только TITLE и DESCRIPTION.
Ничего не выдумывай.

4. Никогда не заменяй
человека,
спортсмена,
команду,
компанию,
бренд
или продукт на другого.

PROTECTED_TERMS сохраняй точно.

Если русское написание имени неоднозначно,
оставь его латиницей.

5. Определи реальную категорию события.

Допустимые коды:

KZ
= Казахстан

US
= США

EUROPE
= Европа

CHINA
= Китай

RUSSIA
= Россия

AI
= AI / технологии

SPORT_FOOTBALL
= футбол

SPORT_F1
= Formula 1 / F1

SPORT_BASKETBALL
= баскетбол / NBA

SPORT_TENNIS
= теннис

SPORT_OTHER
= любой другой спорт

WORLD
= всё остальное

Если главная суть публикации —
матч,
гонка,
турнир,
спортсмен,
команда,
трансфер,
чемпионат,
рекорд,
результат,
травма спортсмена
или спортивная организация,
выбирай соответствующую SPORT-категорию.

6. Если несколько публикаций
описывают ОДНО И ТО ЖЕ
конкретное событие,
дай им одинаковый EVENT_ID.

Похожие темы
не объединяй.

Если сомневаешься —
не объединяй.

7. Оцени значимость события:

HIGH =
крупное событие национального
или международного масштаба,
финал,
чемпионство,
важный матч,
крупный рекорд,
значимый трансфер,
важное решение,
кризис
или событие большого масштаба.

MEDIUM =
заметное событие
более узкого масштаба.

LOW =
рутинная,
нишевая
или малозначимая публикация.

8. Не повышай важность
из-за кликбейтного заголовка.

9. Слухи,
обвинения,
заявления
и прогнозы
не представляй
как установленный факт.

Верни РОВНО одну строку
на каждый NEWS_.

Формат:

NEWS_0|||EVENT_1|||HIGH|||SPORT_FOOTBALL|||РУССКИЙ ЗАГОЛОВОК|||КРАТКОЕ ОПИСАНИЕ

Не используй Markdown.
Не используй JSON.
Не пиши никаких пояснений.

Публикации:

{articles_text}
""".strip()


# =========================================================
# GROQ
# =========================================================

def call_groq(
    prompt
):

    api_key = (
        os.environ.get(
            "GROQ_API_KEY"
        )
    )

    if not api_key:

        return None

    url = (
        "https://api.groq.com/"
        "openai/v1/chat/completions"
    )

    for attempt in range(
        2
    ):

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
                        6500,

                    "reasoning_effort":
                        "low",

                    "include_reasoning":
                        False,

                    "stream":
                        False,
                },

                timeout=80,
            )

            if (
                response.status_code
                ==
                200
            ):

                data = (
                    response.json()
                )

                text = (
                    data[
                        "choices"
                    ][0][
                        "message"
                    ]
                    .get(
                        "content",
                        "",
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
                response.status_code
                ==
                429

                or

                response.status_code
                >=
                500
            ):

                time.sleep(
                    2
                    +
                    attempt
                    *
                    2
                )

                continue

            break

        except Exception as error:

            print(
                "Groq exception:",
                repr(error),
            )

            time.sleep(
                2
                +
                attempt
                *
                2
            )

    return None


# =========================================================
# GEMINI FALLBACK
# =========================================================

def call_gemini(
    prompt
):

    api_key = (
        os.environ.get(
            "GEMINI_API_KEY"
        )
    )

    if not api_key:

        return None

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )

    for attempt in range(
        2
    ):

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
                            6500,
                    },
                },

                timeout=90,
            )

            if (
                response.status_code
                ==
                200
            ):

                candidates = (
                    response.json()
                    .get(
                        "candidates",
                        [],
                    )
                )

                if candidates:

                    parts = (
                        candidates[0]
                        .get(
                            "content",
                            {},
                        )
                        .get(
                            "parts",
                            [],
                        )
                    )

                    text = "\n".join(

                        part.get(
                            "text",
                            "",
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
                response.status_code
                ==
                429

                or

                response.status_code
                >=
                500
            ):

                time.sleep(
                    2
                    +
                    attempt
                    *
                    2
                )

                continue

            break

        except Exception as error:

            print(
                "Gemini exception:",
                repr(error),
            )

            time.sleep(
                2
                +
                attempt
                *
                2
            )

    return None


def ask_ai(
    prompt
):

    return (
        call_groq(
            prompt
        )

        or

        call_gemini(
            prompt
        )
    )


# =========================================================
# РАЗБОР ОТВЕТА AI
# =========================================================

def parse_ai_response(
    raw_text,
    article_count
):

    processed = {}

    if not raw_text:

        return processed

    for line in (
        raw_text.splitlines()
    ):

        line = (
            line.strip()
        )

        if not line.startswith(
            "NEWS_"
        ):

            continue

        pieces = (
            line.split(
                "|||",
                5,
            )
        )

        if (
            len(
                pieces
            )
            !=
            6
        ):

            continue

        try:

            index = int(
                pieces[0]
                .replace(
                    "NEWS_",
                    "",
                )
            )

        except ValueError:

            continue

        if not (
            0
            <=
            index
            <
            article_count
        ):

            continue

        impact = (
            pieces[2]
            .strip()
            .upper()
        )

        code = (
            pieces[3]
            .strip()
            .upper()
        )

        if impact not in IMPACT_RANK:

            impact = (
                "MEDIUM"
            )

        processed[
            index
        ] = {

            "event_id":
                pieces[1]
                .strip()

                or

                f"EVENT_{index}",

            "impact":
                impact,

            "display_region":
                REGION_CODE_TO_LABEL.get(
                    code,
                    "🌍 Мир",
                ),

            "title_ru":
                pieces[4]
                .strip(),

            "summary_ru":
                pieces[5]
                .strip(),
        }

    return processed


# =========================================================
# AI ОБРАБОТКА
# =========================================================

def process_articles_with_ai(
    articles
):

    if not articles:

        return None

    prompt = (
        make_ai_prompt(
            articles
        )
    )

    groq_result = (
        parse_ai_response(
            call_groq(
                prompt
            ),

            len(
                articles
            ),
        )
    )

    if (
        len(
            groq_result
        )
        ==
        len(
            articles
        )
    ):

        return groq_result

    gemini_result = (
        parse_ai_response(
            call_gemini(
                prompt
            ),

            len(
                articles
            ),
        )
    )

    if (
        len(
            gemini_result
        )
        ==
        len(
            articles
        )
    ):

        return gemini_result

    merged = dict(
        groq_result
    )

    for (
        index,
        item,
    ) in (
        gemini_result.items()
    ):

        merged.setdefault(
            index,
            item,
        )

    return (
        merged

        or

        None
    )


# =========================================================
# FALLBACK
# =========================================================

def fallback_processed(
    articles,
    existing=None
):

    result = dict(
        existing
        or
        {}
    )

    for (
        index,
        article,
    ) in enumerate(
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
                    article[
                        "source_region"
                    ],

                "title_ru":
                    article[
                        "title"
                    ],

                "summary_ru":
                    "",
            },
        )

    return result


# =========================================================
# ОБЪЕДИНЕНИЕ ОДИНАКОВЫХ СОБЫТИЙ
# =========================================================

def group_articles(
    articles,
    processed
):

    events = (
        OrderedDict()
    )

    for (
        index,
        article,
    ) in enumerate(
        articles
    ):

        data = (
            processed.get(
                index,
                {},
            )
        )

        event_id = (
            data.get(
                "event_id",

                f"FALLBACK_{index}",
            )
        )

        if (
            event_id
            not in
            events
        ):

            events[
                event_id
            ] = {

                "region":
                    data.get(
                        "display_region",

                        article[
                            "source_region"
                        ],
                    ),

                "title":
                    data.get(
                        "title_ru",

                        article[
                            "title"
                        ],
                    ),

                "summary":
                    data.get(
                        "summary_ru",
                        "",
                    ),

                "impact":
                    data.get(
                        "impact",
                        "MEDIUM",
                    ),

                "published_ts":
                    article.get(
                        "published_ts",
                        0,
                    ),

                "image_url":
                    article.get(
                        "image_url"
                    ),

                "sources":
                    [],
            }

        else:

            # Событие считается свежим
            # по самой новой публикации.
            events[
                event_id
            ][
                "published_ts"
            ] = max(

                events[
                    event_id
                ].get(
                    "published_ts",
                    0,
                ),

                article.get(
                    "published_ts",
                    0,
                ),
            )

            # Если один из источников
            # оценил событие выше,
            # сохраняем более высокий уровень.
            old_impact = (
                events[
                    event_id
                ].get(
                    "impact",
                    "MEDIUM",
                )
            )

            new_impact = (
                data.get(
                    "impact",
                    "MEDIUM",
                )
            )

            if (
                IMPACT_RANK.get(
                    new_impact,
                    0,
                )
                >
                IMPACT_RANK.get(
                    old_impact,
                    0,
                )
            ):

                events[
                    event_id
                ][
                    "impact"
                ] = new_impact

            if (
                not events[
                    event_id
                ].get(
                    "image_url"
                )

                and

                article.get(
                    "image_url"
                )
            ):

                events[
                    event_id
                ][
                    "image_url"
                ] = (
                    article[
                        "image_url"
                    ]
                )

        events[
            event_id
        ][
            "sources"
        ].append(
            {
                "name":
                    article[
                        "source"
                    ],

                "publisher":
                    article.get(
                        "publisher",

                        article[
                            "source"
                        ],
                    ),

                "link":
                    article[
                        "link"
                    ],
            }
        )

    return list(
        events.values()
    )


# =========================================================
# ИСТОЧНИКИ
# =========================================================

def unique_source_links(
    sources
):

    result = []

    seen = set()

    for source in sources:

        key = (

            source.get(
                "name",
                "",
            ),

            source.get(
                "link",
                "",
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


def unique_publishers(
    sources
):

    result = []

    seen = set()

    for source in sources:

        publisher = (

            source.get(
                "publisher"
            )

            or

            source.get(
                "name"
            )

            or

            "Источник"
        )

        if publisher in seen:

            continue

        seen.add(
            publisher
        )

        result.append(
            publisher
        )

    return result


# =========================================================
# КАЧЕСТВО / РАНЖИРОВАНИЕ
# =========================================================

def event_quality_key(
    event
):

    """
    Новости НЕ сортируются
    по позиции в RSS.

    Порядок:

    1. Значимость события.
    2. Количество независимых редакций.
    3. Свежесть публикации.
    """

    publishers_count = len(
        unique_publishers(
            event.get(
                "sources",
                [],
            )
        )
    )

    return (

        IMPACT_RANK.get(
            event.get(
                "impact",
                "MEDIUM",
            ),
            0,
        ),

        min(
            publishers_count,
            5,
        ),

        event.get(
            "published_ts",
            0,
        ),
    )


def rank_events(
    events
):

    return sorted(
        events,

        key=
            event_quality_key,

        reverse=True,
    )


# =========================================================
# ВОЗРАСТ НОВОСТИ
# =========================================================

def format_age(
    published_ts
):

    if not published_ts:

        return None

    seconds = max(
        0,

        time.time()
        -
        published_ts,
    )

    minutes = int(
        seconds
        //
        60
    )

    if minutes < 1:

        return (
            "только что"
        )

    if minutes < 60:

        return (
            f"{minutes} мин назад"
        )

    hours = int(
        minutes
        //
        60
    )

    return (
        f"{hours} ч назад"
    )


# =========================================================
# ФОТО СОБЫТИЯ
# =========================================================

def ensure_event_image(
    event
):

    if event.get(
        "image_url"
    ):

        return (
            event[
                "image_url"
            ]
        )

    sources = (
        unique_source_links(
            event.get(
                "sources",
                [],
            )
        )
    )

    for source in (
        sources[:2]
    ):

        image_url = (
            image_from_article_page(
                source.get(
                    "link",
                    "",
                )
            )
        )

        if image_url:

            event[
                "image_url"
            ] = image_url

            return image_url

    return None


# =========================================================
# КАРТОЧКИ
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
            {},
        )
    )

    cards[
        card_id
    ] = event

    while (
        len(
            cards
        )
        >
        300
    ):

        cards.pop(
            next(
                iter(
                    cards
                )
            ),

            None,
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
                        f"d:{card_id}",
                ),

                InlineKeyboardButton(
                    "💡 Почему важно?",

                    callback_data=
                        f"w:{card_id}",
                ),
            ],

            [
                InlineKeyboardButton(
                    "🗞 Источники",

                    callback_data=
                        f"s:{card_id}",
                )
            ],
        ]
    )


# =========================================================
# ТЕКСТ КАРТОЧКИ
# =========================================================

def make_event_text(
    event
):

    sources = (
        unique_source_links(
            event.get(
                "sources",
                [],
            )
        )
    )

    event[
        "sources"
    ] = sources

    publishers = (
        unique_publishers(
            sources
        )
    )

    age = (
        format_age(
            event.get(
                "published_ts"
            )
        )
    )

    message = (
        f"{event['region']}\n\n"
        f"📰 {event['title']}\n"
    )

    if event.get(
        "summary"
    ):

        message += (
            f"\nКоротко: "
            f"{event['summary']}\n"
        )

    if age:

        message += (
            f"\n🕒 "
            f"{age}"
        )

    # Считаем именно разные редакции,
    # а не количество RSS.
    if (
        len(
            publishers
        )
        ==
        1
    ):

        message += (
            f"\n🗞 Источник: "
            f"{publishers[0]}"
        )

    elif publishers:

        message += (
            f"\n🗞 Источников: "
            f"{len(publishers)} — "
            +
            " • ".join(
                publishers
            )
        )

    else:

        message += (
            "\n🗞 Источник не указан"
        )

    return message


# =========================================================
# ОТПРАВКА КАРТОЧЕК
# =========================================================

async def send_events(
    update,
    context,
    events,
    with_images=False
):

    for event in events:

        message = (
            make_event_text(
                event
            )
        )

        card_id = (
            save_event_card(
                context.application,
                event,
            )
        )

        keyboard = (
            make_news_keyboard(
                card_id
            )
        )

        if with_images:

            image_url = (
                ensure_event_image(
                    event
                )
            )

            if image_url:

                caption = (

                    message

                    if (
                        len(
                            message
                        )
                        <=
                        1000
                    )

                    else

                    message[
                        :997
                    ]
                    +
                    "..."
                )

                try:

                    await update.message.reply_photo(
                        photo=
                            image_url,

                        caption=
                            caption,

                        reply_markup=
                            keyboard,
                    )

                    continue

                except Exception as error:

                    print(
                        "Telegram photo error:",
                        repr(error),
                    )

        await update.message.reply_text(
            message,

            disable_web_page_preview=
                True,

            reply_markup=
                keyboard,
        )


# =========================================================
# ПОДРОБНЕЕ
# =========================================================

def make_details_prompt(
    event
):

    publishers = ", ".join(
        unique_publishers(
            event.get(
                "sources",
                [],
            )
        )
    )

    return (
        f"Заголовок: "
        f"{event['title']}\n"

        f"Описание: "
        f"{event['summary']}\n"

        f"Источники: "
        f"{publishers}\n\n"

        "Объясни событие подробнее "
        "на русском максимум "
        "в 5 коротких предложениях. "

        "Используй только данные карточки. "
        "Не выдумывай новые факты. "

        "Сохраняй нейтральный тон. "

        "Если данных мало — "
        "скажи об этом прямо."
    )


# =========================================================
# ПОЧЕМУ ВАЖНО
# =========================================================

def make_why_prompt(
    event
):

    return (
        f"Заголовок: "
        f"{event['title']}\n"

        f"Описание: "
        f"{event['summary']}\n\n"

        "Объясни нейтрально, "
        "почему это событие "
        "может иметь значение. "

        "2–4 коротких предложения. "

        "Не выдумывай факты "
        "и не драматизируй. "

        "Если последствия неизвестны — "
        "скажи об этом."
    )


# =========================================================
# INLINE-КНОПКИ
# =========================================================

async def news_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = (
        update.callback_query
    )

    await query.answer()

    try:

        action, card_id = (
            query.data.split(
                ":",
                1,
            )
        )

    except Exception:

        return

    event = (
        context.application
        .bot_data
        .get(
            "event_cards",
            {},
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


    # =====================================================
    # ИСТОЧНИКИ
    # =====================================================

    if action == "s":

        buttons = []

        sources = (
            unique_source_links(
                event.get(
                    "sources",
                    [],
                )
            )
        )

        for source in sources:

            link = (
                source.get(
                    "link",
                    "",
                )
            )

            if link.startswith(
                (
                    "http://",
                    "https://",
                )
            ):

                buttons.append(
                    [
                        InlineKeyboardButton(
                            "🔗 "
                            +
                            source.get(
                                "name",
                                "Источник",
                            ),

                            url=
                                link,
                        )
                    ]
                )

        if buttons:

            await query.message.reply_text(
                "🗞 Открыть источники:",

                reply_markup=
                    InlineKeyboardMarkup(
                        buttons
                    ),
            )

        else:

            await query.message.reply_text(
                "Для этой новости "
                "нет доступных ссылок."
            )

        return


    # =====================================================
    # ПОДРОБНЕЕ / ПОЧЕМУ ВАЖНО
    # =====================================================

    if action == "d":

        cache_key = (
            "_details"
        )

        title = (
            "📖 Подробнее"
        )

        wait_text = (
            "📖 Готовлю подробности..."
        )

        prompt = (
            make_details_prompt(
                event
            )
        )

    else:

        cache_key = (
            "_why"
        )

        title = (
            "💡 Почему это важно?"
        )

        wait_text = (
            "💡 Анализирую значение..."
        )

        prompt = (
            make_why_prompt(
                event
            )
        )

    if event.get(
        cache_key
    ):

        await query.message.reply_text(
            title
            +
            "\n\n"
            +
            event[
                cache_key
            ]
        )

        return

    wait_message = (
        await query.message.reply_text(
            wait_text
        )
    )

    answer = (
        ask_ai(
            prompt
        )
    )

    if not answer:

        await wait_message.edit_text(
            "⚠️ AI сейчас временно "
            "не смог подготовить ответ."
        )

        return

    event[
        cache_key
    ] = answer

    await wait_message.edit_text(
        title
        +
        "\n\n"
        +
        answer
    )


# =========================================================
# ФИНАНСЫ
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
            .split(
                "}"
            )[-1]
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

        str(
            value
        ).replace(
            " ",
            "",
        ),
    )

    if not match:

        return None

    try:

        return float(
            match.group(0)
            .replace(
                ",",
                ".",
            )
        )

    except ValueError:

        return None


# =========================================================
# КУРСЫ НБК
# =========================================================

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
            .split(
                "}"
            )[-1]
            .lower()
            !=
            "item"
        ):

            continue

        code = (
            xml_child_text(
                item,
                "title",
            )
            .upper()
            .strip()
        )

        if code not in wanted:

            continue

        value = (
            to_float(
                xml_child_text(
                    item,
                    "description",
                )
            )
        )

        quantity = (
            to_float(
                xml_child_text(
                    item,
                    "quant",
                )
            )

            or

            1.0
        )

        if value is None:

            continue

        rates[
            code
        ] = (
            value
            /
            max(
                quantity,
                1.0,
            )
        )

    return rates


# =========================================================
# КРИПТО
# =========================================================

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

    return (
        to_float(
            response.json()
            .get(
                "data",
                {},
            )
            .get(
                "amount"
            )
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
                " ",
            )
        )

    return (
        f"${value:,.2f}"
        .replace(
            ",",
            " ",
        )
    )


# =========================================================
# /MARKETS
# =========================================================

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

        rates = (
            fetch_nbk_rates()
        )

    except Exception as error:

        print(
            "NBK error:",
            repr(error),
        )

        rates = {}

    try:

        btc = (
            fetch_coinbase_spot(
                "BTC-USD"
            )
        )

    except Exception:

        btc = None

    try:

        eth = (
            fetch_coinbase_spot(
                "ETH-USD"
            )
        )

    except Exception:

        eth = None

    lines = [

        "💰 Финансы",

        "",

        "💱 Официальный курс НБК",
    ]

    currencies = [

        (
            "USD",
            "🇺🇸",
            "доллар",
        ),

        (
            "EUR",
            "🇪🇺",
            "евро",
        ),

        (
            "GBP",
            "🇬🇧",
            "фунт стерлингов",
        ),

        (
            "CNY",
            "🇨🇳",
            "юань",
        ),

        (
            "RUB",
            "🇷🇺",
            "рубль",
        ),
    ]

    if rates:

        for (
            code,
            emoji,
            name,
        ) in currencies:

            value = (
                rates.get(
                    code
                )
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
            "Курсы сейчас недоступны"
        )

    lines += [

        "",

        "🪙 Крипто",

        "₿ BTC/USD ≈ "
        +
        format_usd_price(
            btc
        ),

        "◆ ETH/USD ≈ "
        +
        format_usd_price(
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
# ПРОВЕРКА: СПОРТИВНОЕ СОБЫТИЕ?
# =========================================================

def is_sport_event(
    event
):

    return (
        event.get(
            "region"
        )
        in
        SPORT_LABELS
    )


# =========================================================
# ФИЛЬТР СОБЫТИЙ
# =========================================================

def filter_events(
    events,
    region_filter=None,
    sport_filter=None
):

    # Например только футбол.
    if sport_filter:

        return [

            event

            for event in events

            if (
                event.get(
                    "region"
                )
                ==
                sport_filter
            )
        ]

    # Весь спорт:
    # футбол + F1 + баскетбол + теннис + другой спорт.
    if (
        region_filter
        ==
        "🏆 Спорт"
    ):

        return [

            event

            for event in events

            if (
                is_sport_event(
                    event
                )
            )
        ]

    # Обычный регион.
    if region_filter:

        return [

            event

            for event in events

            if (
                event.get(
                    "region"
                )
                ==
                region_filter
            )
        ]

    return events


# =========================================================
# ЗАПРОС НОВОСТЕЙ
# =========================================================

async def run_news_request(
    update,
    context,
    region_filter=None,
    sport_filter=None,
    important_only=False
):

    if important_only:

        status_text = (
            "🔥 Ищу главное "
            "за последние 24 часа...\n"

            "🧠 Сравниваю значимость, "
            "число источников и свежесть"
        )

    elif sport_filter:

        status_text = (
            f"🔎 Собираю "
            f"{sport_filter} "
            f"за последние "
            f"{FRESH_HOURS} часов..."
        )

    elif (
        region_filter
        ==
        "🏆 Спорт"
    ):

        status_text = (
            "🏆 Собираю спорт...\n"

            "🧠 Выбираю значимые события, "
            "а не первые строки RSS"
        )

    elif region_filter:

        status_text = (
            f"🔎 Собираю свежие новости: "
            f"{region_filter}"
        )

    else:

        status_text = (
            "🔎 Собираю свежие новости...\n"

            "🧠 Ранжирую по значимости, "
            "источникам и свежести"
        )

    status = (
        await update.message.reply_text(
            status_text
        )
    )

    # Если выбран футбол / F1 /
    # баскетбол / теннис,
    # сначала собираем ВСЕ спортивные RSS.
    if sport_filter:

        source_region = (
            "🏆 Спорт"
        )

    else:

        source_region = (
            region_filter
        )

    articles = (
        collect_articles(
            source_region
        )
    )

    if not articles:

        await status.edit_text(
            f"❌ Не нашёл свежих публикаций "
            f"за последние "
            f"{FRESH_HOURS} часов."
        )

        return

    # Выбираем качественный,
    # сбалансированный набор для AI.
    ai_articles = (
        select_articles_for_ai(
            articles
        )
    )

    processed = (
        process_articles_with_ai(
            ai_articles
        )
    )

    if (
        processed is None
        and
        important_only
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

    processed = (
        fallback_processed(
            ai_articles,
            processed,
        )
    )

    events = (
        group_articles(
            ai_articles,
            processed,
        )
    )

    # Если AI работает —
    # фильтруем уже по реальной
    # категории события.
    if not ai_failed:

        events = (
            filter_events(
                events,

                region_filter=
                    region_filter,

                sport_filter=
                    sport_filter,
            )
        )

    # =====================================================
    # ГЛАВНЫЕ НОВОСТИ
    # =====================================================

    if important_only:

        events = [

            event

            for event in events

            if (
                event.get(
                    "impact"
                )
                ==
                "HIGH"
            )
        ]

        events = (
            rank_events(
                events
            )[
                :5
            ]
        )

    # =====================================================
    # ОБЫЧНАЯ ВЫДАЧА
    # =====================================================

    else:

        # Главное изменение:
        #
        # НЕ порядок RSS.
        #
        # Сначала важность,
        # потом количество разных СМИ,
        # потом свежесть.
        events = (
            rank_events(
                events
            )
        )

        if (
            sport_filter

            or

            region_filter
            ==
            "🏆 Спорт"
        ):

            events = (
                events[
                    :MAX_SPORT_EVENTS
                ]
            )

        elif region_filter:

            events = (
                events[
                    :MAX_REGION_EVENTS
                ]
            )

        else:

            events = (
                events[
                    :MAX_NEWS_EVENTS
                ]
            )

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

            "Показываю свежие RSS "
            "без AI-ранжирования."
        )

    await send_events(
        update,
        context,
        events,

        # Картинки пока только
        # в «Главном».
        with_images=
            important_only,
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
            "⚡ Собираю короткую сводку "
            "за последние 24 часа..."
        )
    )

    articles = (
        collect_articles()
    )

    if not articles:

        await status.edit_text(
            "❌ Не нашёл свежих публикаций "
            "за последние 24 часа."
        )

        return

    ai_articles = (
        select_articles_for_ai(
            articles
        )
    )

    processed = (
        process_articles_with_ai(
            ai_articles
        )
    )

    if processed is None:

        await status.edit_text(
            "⚠️ AI сейчас не ответил.\n"

            "Без него не буду "
            "составлять сводку наугад."
        )

        return

    events = (
        group_articles(
            ai_articles,

            fallback_processed(
                ai_articles,
                processed,
            ),
        )
    )

    events = (
        rank_events(
            events
        )[
            :5
        ]
    )

    try:

        await status.delete()

    except Exception:

        pass

    lines = [

        "⚡ Коротко: "
        "5 важных событий "
        "за последние 24 часа"
    ]

    for (
        number,
        event,
    ) in enumerate(
        events,
        1,
    ):

        sources_count = (
            len(
                unique_publishers(
                    event.get(
                        "sources",
                        [],
                    )
                )
            )
        )

        lines.append(
            f"{number}. "
            f"{event['region']} "
            f"{event['title']} "
            f"· {sources_count} ист."
        )

    await update.message.reply_text(
        "\n\n".join(
            lines
        )
    )


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "👋 Привет!\n\n"

        "Я собираю свежие новости "
        "из нескольких редакций, "
        "сравниваю публикации, "
        "перевожу их на русский "
        "и объединяю одинаковые события.\n\n"

        "Выбирай раздел 👇",

        reply_markup=
            MAIN_MENU,
    )


# =========================================================
# ГЛАВНОЕ МЕНЮ
# =========================================================

async def menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "Выбирай раздел 👇",

        reply_markup=
            MAIN_MENU,
    )


# =========================================================
# МЕНЮ СПОРТА
# =========================================================

async def sport_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🏆 Что смотрим?",

        reply_markup=
            SPORT_MENU,
    )


# =========================================================
# ВСЕ НОВОСТИ
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
# ГЛАВНОЕ
# =========================================================

async def important(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await run_news_request(
        update,
        context,

        important_only=
            True,
    )


# =========================================================
# РЕГИОНАЛЬНЫЕ КОМАНДЫ
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
                region,
        )


# =========================================================
# КОМАНДЫ СПОРТА
# =========================================================

async def sport_command(
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

    sport_filter = (
        SPORT_COMMANDS.get(
            command
        )
    )

    if sport_filter:

        await run_news_request(
            update,
            context,

            sport_filter=
                sport_filter,
        )


# =========================================================
# ВЕСЬ СПОРТ
# =========================================================

async def all_sport(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await run_news_request(
        update,
        context,

        region_filter=
            "🏆 Спорт",
    )


# =========================================================
# СКРЫТАЯ /MANUTD
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
# СКРЫТАЯ /ZARINA
# =========================================================

async def zarina(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    today = (
        datetime.now(
            ALMATY_TZ
        )
        .date()
    )

    compliment = (

        COMPLIMENTS[
            today.toordinal()
            %
            len(
                COMPLIMENTS
            )
        ]
    )

    await update.message.reply_text(
        "💗 Комплимент дня для Зарины\n\n"

        +
        compliment

        +
        "\n\n✨ Возвращайся завтра "
        "за новым 😄"
    )


# =========================================================
# STATUS GROQ
# =========================================================

def test_groq_connection():

    api_key = (
        os.environ.get(
            "GROQ_API_KEY"
        )
    )

    if not api_key:

        return (
            False,
            "нет ключа",
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

        if (
            response.status_code
            !=
            200
        ):

            return (
                False,

                f"HTTP "
                f"{response.status_code}",
            )

        models = {

            item.get(
                "id"
            )

            for item in (
                response.json()
                .get(
                    "data",
                    [],
                )
            )
        }

        if GROQ_MODEL in models:

            return (
                True,
                "API и модель доступны",
            )

        return (
            False,
            "модель не найдена",
        )

    except Exception:

        return (
            False,
            "нет ответа",
        )


# =========================================================
# STATUS GEMINI
# =========================================================

def test_gemini_connection():

    api_key = (
        os.environ.get(
            "GEMINI_API_KEY"
        )
    )

    if not api_key:

        return (
            False,
            "нет ключа",
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

        if (
            response.status_code
            !=
            200
        ):

            return (
                False,

                f"HTTP "
                f"{response.status_code}",
            )

        models = {

            item.get(
                "name",
                "",
            )
            .replace(
                "models/",
                "",
            )

            for item in (
                response.json()
                .get(
                    "models",
                    [],
                )
            )
        }

        if GEMINI_MODEL in models:

            return (
                True,
                "API и модель доступны",
            )

        return (
            False,
            "модель не найдена",
        )

    except Exception:

        return (
            False,
            "нет ответа",
        )


# =========================================================
# /STATUS
# =========================================================

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
# ОБРАБОТКА КНОПОК
# =========================================================

async def menu_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = (
        update.message.text
        .strip()
    )


    # -------------------------
    # ГЛАВНОЕ
    # -------------------------

    if text == "🔥 Главное":

        return await important(
            update,
            context,
        )


    # -------------------------
    # КРАТКО
    # -------------------------

    if text == "⚡ Кратко":

        return await brief(
            update,
            context,
        )


    # -------------------------
    # ВСЕ НОВОСТИ
    # -------------------------

    if text == "📰 Все новости":

        return await news(
            update,
            context,
        )


    # -------------------------
    # ФИНАНСЫ
    # -------------------------

    if text == "💰 Финансы":

        return await markets(
            update,
            context,
        )


    # =====================================================
    # СПОРТ
    # =====================================================

    if text == "🏆 Спорт":

        return await sport_menu(
            update,
            context,
        )


    if text == "🏆 Весь спорт":

        return await all_sport(
            update,
            context,
        )


    if text in SPORT_FILTERS:

        return await run_news_request(
            update,
            context,

            sport_filter=
                SPORT_FILTERS[
                    text
                ],
        )


    # -------------------------
    # НАЗАД
    # -------------------------

    if text == "⬅️ Главное меню":

        return await menu(
            update,
            context,
        )


    # =====================================================
    # ОБЫЧНЫЕ РЕГИОНЫ
    # =====================================================

    if text in REGION_BUTTONS:

        return await run_news_request(
            update,
            context,

            region_filter=
                text,
        )


    await update.message.reply_text(
        "Выбери раздел "
        "кнопками ниже 👇",

        reply_markup=
            MAIN_MENU,
    )


# =========================================================
# TELEGRAM COMMAND MENU
# =========================================================

async def post_init(
    application: Application
):

    # /zarina и /manutd
    # здесь специально НЕТ.
    # Они скрытые.

    await application.bot.set_my_commands(
        [
            BotCommand(
                "news",
                "Все новости",
            ),

            BotCommand(
                "brief",
                "5 новостей коротко",
            ),

            BotCommand(
                "important",
                "Главные события",
            ),

            BotCommand(
                "markets",
                "Финансы",
            ),

            BotCommand(
                "sport",
                "Весь спорт",
            ),

            BotCommand(
                "football",
                "Футбол",
            ),

            BotCommand(
                "f1",
                "Formula 1",
            ),

            BotCommand(
                "basketball",
                "Баскетбол",
            ),

            BotCommand(
                "tennis",
                "Теннис",
            ),

            BotCommand(
                "kz",
                "Казахстан",
            ),

            BotCommand(
                "usa",
                "США",
            ),

            BotCommand(
                "europe",
                "Европа",
            ),

            BotCommand(
                "china",
                "Китай",
            ),

            BotCommand(
                "russia",
                "Россия",
            ),

            BotCommand(
                "world",
                "Мир",
            ),

            BotCommand(
                "ai",
                "AI и технологии",
            ),

            BotCommand(
                "menu",
                "Показать меню",
            ),

            BotCommand(
                "status",
                "Проверить AI",
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

        daemon=True,
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


    # =====================================================
    # ОСНОВНЫЕ КОМАНДЫ
    # =====================================================

    handlers = [

        (
            "start",
            start,
        ),

        (
            "menu",
            menu,
        ),

        (
            "news",
            news,
        ),

        (
            "brief",
            brief,
        ),

        (
            "important",
            important,
        ),

        (
            "markets",
            markets,
        ),

        (
            "sport",
            all_sport,
        ),

        (
            "status",
            status,
        ),


        # -------------------------
        # СКРЫТЫЕ
        # -------------------------

        (
            "manutd",
            manutd,
        ),

        (
            "zarina",
            zarina,
        ),
    ]


    for (
        command,
        function,
    ) in handlers:

        app.add_handler(
            CommandHandler(
                command,
                function,
            )
        )


    # =====================================================
    # РЕГИОНЫ
    # =====================================================

    for command in (
        COMMAND_TO_REGION
    ):

        app.add_handler(
            CommandHandler(
                command,
                region_command,
            )
        )


    # =====================================================
    # СПОРТИВНЫЕ КОМАНДЫ
    # =====================================================

    for command in (
        SPORT_COMMANDS
    ):

        app.add_handler(
            CommandHandler(
                command,
                sport_command,
            )
        )


    # =====================================================
    # INLINE-КНОПКИ
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            news_callback
        )
    )


    # =====================================================
    # ОБЫЧНЫЕ КНОПКИ
    # =====================================================

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
