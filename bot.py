import os
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import feedparser
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


NEWS_FEEDS = {
    "🌍 Мир": "https://subscribe.stripes.com/rss/top-news.xml",
    "🇺🇸 США": "https://subscribe.stripes.com/rss/us.xml",
    "🇪🇺 Европа": "https://subscribe.stripes.com/rss/europe.xml",
    "🇨🇳 Китай": "https://www.chinanews.com.cn/rss/china.xml",
}

GEMINI_MODEL = "gemini-3.8-flash"


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
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


def translate_titles(titles):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        return titles

    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{GEMINI_MODEL}:generateContent"
    )

    prompt = (
        "Переведи все заголовки новостей на естественный русский язык.\n"
        "Не добавляй никаких новых фактов.\n"
        "Сохрани имена, даты, числа и смысл точно.\n"
        "Верни переводы строго в том же порядке.\n\n"
        + json.dumps(titles, ensure_ascii=False)
    )

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
                            {"text": prompt}
                        ]
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": {
                        "type": "ARRAY",
                        "items": {
                            "type": "STRING"
                        }
                    }
                }
            },
            timeout=40,
        )

        if response.status_code != 200:
            return titles

        data = response.json()

        text = (
            data["candidates"][0]
            ["content"]["parts"][0]["text"]
        )

        translated = json.loads(text)

        if (
            isinstance(translated, list)
            and len(translated) == len(titles)
        ):
            return translated

    except Exception:
        pass

    return titles


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "📰 /news — последние новости на русском"
    )


async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = await update.message.reply_text(
        "🔎 Собираю и перевожу новости..."
    )

    articles = []

    for category, url in NEWS_FEEDS.items():
        feed = feedparser.parse(url)

        if not feed.entries:
            continue

        article = feed.entries[0]

        articles.append({
            "category": category,
            "title": article.get("title", "Без заголовка"),
            "link": article.get("link", ""),
            "source": feed.feed.get("title", "Источник"),
        })

    if not articles:
        await status.edit_text(
            "Не удалось получить новости."
        )
        return

    original_titles = [
        article["title"]
        for article in articles
    ]

    translated_titles = translate_titles(original_titles)

    for article, translated_title in zip(
        articles,
        translated_titles
    ):
        message = (
            f"{article['category']}\n\n"
            f"📰 {translated_title}\n\n"
            f"🗞 {article['source']}\n"
            f"🔗 {article['link']}"
        )

        await update.message.reply_text(message)

    try:
        await status.delete()
    except Exception:
        pass


def main():
    threading.Thread(
        target=run_web_server,
        daemon=True
    ).start()

    token = os.environ["TELEGRAM_BOT_TOKEN"]

    app = Application.builder().token(token).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("news", news)
    )

    app.run_polling()


if __name__ == "__main__":
    main()
