import os
import re
import html
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, HTTPServer

import feedparser
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


# ==========================================
# ИСТОЧНИКИ НОВОСТЕЙ
# ==========================================

NEWS_FEEDS = {
    # 🇰🇿 КАЗАХСТАН
    "🇰🇿 Казахстан • Kazinform":
        "https://qazinform.com/rss/en.xml",

    "🇰🇿 Казахстан • The Astana Times":
        "https://astanatimes.com/feed/",


    # 🇺🇸 США
    "🇺🇸 США • NPR":
        "https://feeds.npr.org/1003/rss.xml",

    "🇺🇸 США • BBC":
        "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",


    # 🇪🇺 ЕВРОПА
    "🇪🇺 Европа • Euronews":
        "https://euronews.com/rss?format=mrss&level=vertical&name=my-europe",

    "🇪🇺 Европа • BBC":
        "https://feeds.bbci.co.uk/news/world/europe/rss.xml",


    # 🇨🇳 КИТАЙ
    "🇨🇳 Китай • China News Service":
        "https://www.chinanews.com.cn/rss/china.xml",

    "🇨🇳 Китай • BBC":
        "https://feeds.bbci.co.uk/news/world/asia/china/rss.xml",


    # 🇷🇺 РОССИЯ
    "🇷🇺 Россия • Интерфакс":
        "https://www.interfax.ru/rss.asp",

    "🇷🇺 Россия • Meduza":
        "https://meduza.io/rss2/all",


    # 🌍 МИР
    "🌍 Мир • Euronews":
        "https://www.euronews.com/rss?format=mrss&level=theme&name=news",

    "🌍 Мир • BBC":
        "https://feeds.bbci.co.uk/news/world/rss.xml",


    # 🤖 AI / ТЕХНОЛОГИИ
    "🤖 AI • TechCrunch":
        "https://techcrunch.com/category/artificial-intelligence/feed/",

    "🤖 AI / технологии • The Verge":
        "https://www.theverge.com/rss/index.xml",
}


# Эта модель у тебя уже успешно работает
GEMINI_MODEL = "gemini-3.8-flash"


# ==========================================
# WEB-СЕРВЕР ДЛЯ RENDER
# ==========================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def log_message(self, format, *args):
        return


def run_web_server():
    port = int(os.environ.get("PORT", 10000))

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    print(f"Web server started on port {port}")

    server.serve_forever()


# ==========================================
# ОЧИСТКА RSS-ТЕКСТА
# ==========================================

def clean_text(text):
    if not text:
        return ""

    text = html.unescape(str(text))

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = " ".join(
        text.replace("\n", " ").split()
    )

    return text


# ==========================================
# GEMINI
# ПЕРЕВОД + КРАТКО + ОБЪЕДИНЕНИЕ ДУБЛЕЙ
# ==========================================

def process_articles_with_gemini(articles):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print("GEMINI_API_KEY missing")
        return None

    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{GEMINI_MODEL}:generateContent"
    )

    article_lines = []

    for index, article in enumerate(articles):

        title = clean_text(
            article["title"]
        )

        description = clean_text(
            article.get(
                "description",
                ""
            )
        )

        # Не отправляем слишком длинные тексты
        description = description[:700]

        article_lines.append(
            f"""
NEWS_{index}
REGION: {article['region']}
SOURCE: {article['source']}
TITLE: {title}
DESCRIPTION: {description}
""".strip()
        )

    articles_text = "\n\n".join(
        article_lines
    )

    prompt = f"""
Ты работаешь как редактор русскоязычного новостного агрегатора.

Перед тобой публикации разных СМИ.

Для КАЖДОЙ публикации:

1. Переведи заголовок на естественный русский язык.

2. Напиши краткое описание новости на русском:
максимум 1–2 коротких предложения.

3. Используй ТОЛЬКО информацию из TITLE и DESCRIPTION.
Ничего не выдумывай.

4. Сохраняй точно:
имена людей,
названия компаний,
страны,
даты,
суммы,
проценты
и другие числа.

5. Если две или несколько публикаций описывают
одно и то же КОНКРЕТНОЕ событие,
дай им одинаковый EVENT_ID.

6. Если публикации просто относятся к похожей теме,
но события разные — EVENT_ID должен быть разным.

7. Если сомневаешься, объединять ли публикации,
НЕ объединяй их.

8. Для публикаций об одном событии
используй максимально похожий русский заголовок
и одинаковую суть.

9. Не представляй мнение, обвинение,
предположение или заявление источника
как установленный факт.

Верни РОВНО по одной строке для каждого NEWS_.

Формат строго такой:

NEWS_0|||EVENT_1|||РУССКИЙ ЗАГОЛОВОК|||КРАТКОЕ ОПИСАНИЕ
NEWS_1|||EVENT_2|||РУССКИЙ ЗАГОЛОВОК|||КРАТКОЕ ОПИСАНИЕ

Если NEWS_2 и NEWS_3 говорят об одном событии:

NEWS_2|||EVENT_3|||РУССКИЙ ЗАГОЛОВОК|||КРАТКОЕ ОПИСАНИЕ
NEWS_3|||EVENT_3|||РУССКИЙ ЗАГОЛОВОК|||КРАТКОЕ ОПИСАНИЕ

Не используй Markdown.
Не используй JSON.
Не используй ``` .
Не пиши объяснений.
Не пропускай NEWS_.

Вот публикации:

{articles_text}
"""

    try:
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json={
                "contents": [
                    {
                        "parts": [
                            {
                                "text": prompt
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 5000
                }
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
            part.get("text", "")
            for part in parts
            if part.get("text")
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
                3
            )

            if len(pieces) != 4:
                continue

            news_id = pieces[0].strip()
            event_id = pieces[1].strip()
            title_ru = pieces[2].strip()
            summary_ru = pieces[3].strip()

            try:
                index = int(
                    news_id.replace(
                        "NEWS_",
                        ""
                    )
                )

            except ValueError:
                continue

            processed[index] = {
                "event_id": event_id,
                "title_ru": title_ru,
                "summary_ru": summary_ru,
            }

        return processed

    except Exception as error:

        print(
            "Gemini processing exception:",
            repr(error)
        )

        return None


# ==========================================
# ОБЪЕДИНЕНИЕ ОДИНАКОВЫХ СОБЫТИЙ
# ==========================================

def group_articles(
    articles,
    processed
):
    events = OrderedDict()

    for index, article in enumerate(
        articles
    ):

        gemini_data = processed.get(
            index,
            {}
        )

        event_id = gemini_data.get(
            "event_id",
            f"FALLBACK_{index}"
        )

        title_ru = gemini_data.get(
            "title_ru",
            article["title"]
        )

        summary_ru = gemini_data.get(
            "summary_ru",
            ""
        )

        if event_id not in events:

            events[event_id] = {
                "region": article["region"],
                "title": title_ru,
                "summary": summary_ru,
                "sources": []
            }

        events[event_id]["sources"].append({
            "name": article["source"],
            "link": article["link"]
        })

    return list(
        events.values()
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
        "Я собираю свежие новости из разных источников, "
        "перевожу их на русский и объединяю одинаковые события.\n\n"
        "📰 /news — получить свежие новости"
    )


# ==========================================
# ПАСХАЛКА /MANUTD 😈
# ==========================================

async def manutd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "Муха Лох! 😂"
    )


# ==========================================
# /NEWS
# ==========================================

async def news(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    status_message = (
        await update.message.reply_text(
            "🔎 Собираю новости...\n"
            "🌍 Проверяю источники\n"
            "🇷🇺 Перевожу на русский\n"
            "🧠 Ищу одинаковые события"
        )
    )

    articles = []

    for category, url in NEWS_FEEDS.items():

        try:
            feed = feedparser.parse(
                url
            )

            if not feed.entries:

                print(
                    f"No articles from: {category}"
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

            source_name = (
                feed.feed.get(
                    "title",
                    category
                    .split("•")[-1]
                    .strip()
                )
            )

            if not title:
                continue

            region = (
                category
                .split("•")[0]
                .strip()
            )

            articles.append({
                "region": region,
                "title": title,
                "description": description,
                "link": link,
                "source": source_name,
            })

        except Exception as error:

            print(
                f"RSS error {category}:",
                repr(error)
            )


    if not articles:

        await status_message.edit_text(
            "❌ Сейчас не удалось получить новости."
        )

        return


    processed = (
        process_articles_with_gemini(
            articles
        )
    )


    if processed is None:

        await status_message.edit_text(
            "⚠️ Новости получены, "
            "но Gemini сейчас не смог их обработать."
        )

        return


    events = group_articles(
        articles,
        processed
    )


    try:
        await status_message.delete()

    except Exception:
        pass


    await update.message.reply_text(
        f"📰 Публикаций найдено: {len(articles)}\n"
        f"🧠 Отдельных событий: {len(events)}"
    )


    for event in events:

        unique_sources = []
        seen_links = set()

        for source in event["sources"]:

            link = source["link"]

            if link in seen_links:
                continue

            seen_links.add(
                link
            )

            unique_sources.append(
                source
            )


        source_names = []

        for source in unique_sources:

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


        for source in unique_sources:

            message += (
                f"\n🔗 {source['name']}: "
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
# ЗАПУСК БОТА
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
        .token(telegram_token)
        .build()
    )


    app.add_handler(
        CommandHandler(
            "start",
            start
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
            "manutd",
            manutd
        )
    )


    print(
        "Telegram bot started"
    )


    app.run_polling()


if __name__ == "__main__":
    main()
