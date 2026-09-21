import os
import threading
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


GEMINI_MODEL = "gemini-3.8-flash"


# ==========================================
# МАЛЕНЬКИЙ WEB-СЕРВЕР ДЛЯ RENDER
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
# ПЕРЕВОД ВСЕХ ЗАГОЛОВКОВ ЧЕРЕЗ GEMINI
# ==========================================

def translate_titles(titles):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print("GEMINI_API_KEY missing")
        return titles

    if not titles:
        return []

    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{GEMINI_MODEL}:generateContent"
    )

    # Убираем переносы строк внутри заголовков,
    # чтобы Gemini было проще вернуть правильный формат.
    clean_titles = []

    for title in titles:
        clean_title = " ".join(
            str(title).replace("\n", " ").split()
        )
        clean_titles.append(clean_title)

    numbered_titles = "\n".join(
        f"NEWS_{index}|||{title}"
        for index, title in enumerate(clean_titles)
    )

    prompt = f"""
Ты профессиональный переводчик новостей.

Переведи ВСЕ заголовки ниже на естественный русский язык.

СТРОГИЕ ПРАВИЛА:

1. Ничего не выдумывай.
2. Не добавляй фактов, которых нет в оригинале.
3. Не сокращай важные детали.
4. Точно сохраняй имена людей, компаний, стран, даты и числа.
5. Английские и китайские заголовки обязательно переводи на русский.
6. Даже если заголовок уже на русском — просто оставь его нормальным русским текстом.
7. Каждый перевод должен занимать ОДНУ строку.
8. Сохрани идентификатор NEWS_ перед каждой строкой.
9. Между идентификатором и переводом обязательно оставь |||.
10. Не используй Markdown.
11. Не используй ```json.
12. Не пиши никаких объяснений.
13. Верни ТОЛЬКО строки с переводами.

Пример:

NEWS_0|||Первый заголовок на русском
NEWS_1|||Второй заголовок на русском
NEWS_2|||Третий заголовок на русском

Вот заголовки:

{numbered_titles}
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
                    "maxOutputTokens": 3000
                }
            },
            timeout=60,
        )

        if response.status_code != 200:
            print(
                "Gemini HTTP error:",
                response.status_code,
                response.text[:1500]
            )

            return titles

        data = response.json()

        candidates = data.get("candidates", [])

        if not candidates:
            print("Gemini returned no candidates")
            return titles

        parts = (
            candidates[0]
            .get("content", {})
            .get("parts", [])
        )

        if not parts:
            print("Gemini returned no text")
            return titles

        raw_text = "\n".join(
            part.get("text", "")
            for part in parts
            if part.get("text")
        ).strip()

        print(
            "Gemini translation response:",
            raw_text[:2000]
        )

        translations = {}

        for line in raw_text.splitlines():
            line = line.strip()

            if "|||" not in line:
                continue

            identifier, translated = line.split(
                "|||",
                1
            )

            identifier = identifier.strip()
            translated = translated.strip()

            if not identifier.startswith("NEWS_"):
                continue

            try:
                index = int(
                    identifier.replace(
                        "NEWS_",
                        ""
                    )
                )
            except ValueError:
                continue

            if translated:
                translations[index] = translated

        result = []

        for index, original_title in enumerate(titles):

            translated_title = translations.get(
                index
            )

            if translated_title:
                result.append(
                    translated_title
                )
            else:
                # Если конкретно одна строка не распозналась,
                # остальные переводы всё равно сохраняются.
                result.append(
                    original_title
                )

        return result

    except Exception as error:
        print(
            "Gemini exception:",
            repr(error)
        )

        return titles


# ==========================================
# /START
# ==========================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Я собираю свежие новости и перевожу их на русский.\n\n"
        "📰 /news — получить последние новости"
    )


# ==========================================
# /NEWS
# ==========================================

async def news(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    status_message = await update.message.reply_text(
        "🔎 Собираю свежие новости...\n"
        "🌍 Проверяю источники\n"
        "🇷🇺 Перевожу на русский"
    )

    articles = []

    for category, url in NEWS_FEEDS.items():

        try:
            feed = feedparser.parse(url)

            if not feed.entries:
                print(
                    f"No articles from: {category}"
                )
                continue

            article = feed.entries[0]

            title = article.get(
                "title",
                ""
            )

            link = article.get(
                "link",
                ""
            )

            source_name = feed.feed.get(
                "title",
                category.split("•")[-1].strip()
            )

            if not title:
                continue

            articles.append({
                "category": category,
                "title": title,
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


    original_titles = [
        article["title"]
        for article in articles
    ]


    translated_titles = translate_titles(
        original_titles
    )


    try:
        await status_message.delete()
    except Exception:
        pass


    for article, russian_title in zip(
        articles,
        translated_titles
    ):

        message = (
            f"{article['category']}\n\n"
            f"📰 {russian_title}\n\n"
            f"🗞 {article['source']}\n"
            f"🔗 {article['link']}"
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

    print("Telegram bot started")

    app.run_polling()


if __name__ == "__main__":
    main()
