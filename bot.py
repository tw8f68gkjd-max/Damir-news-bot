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
    print(f"Web server started on port {port}")
    server.serve_forever()


def translate_titles(titles):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print("GEMINI_API_KEY missing")
        return None

    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{GEMINI_MODEL}:generateContent"
    )

    prompt = (
        "Переведи каждый заголовок новости на естественный русский язык.\n"
        "Правила:\n"
        "- ничего не добавляй от себя;\n"
        "- не сокращай важные факты;\n"
        "- точно сохраняй имена, страны, даты и числа;\n"
        "- верни переводы строго в исходном порядке.\n\n"
        "Заголовки:\n"
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
                    "responseFormat": {
                        "text": {
                            "mimeType": "application/json",
                            "schema": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "minItems": len(titles),
                                "maxItems": len(titles)
                            }
                        }
                    }
                }
            },
            timeout=40,
        )

        if response.status_code != 200:
            print(
                "Gemini HTTP error:",
                response.status_code,
                response.text[:1000]
            )
            return None

        data = response.json()

        raw_text = (
            data["candidates"][0]
            ["content"]["parts"][0]["text"]
        )

        translated = json.loads(raw_text)

        if (
            isinstance(translated, list)
            and len(translated) == len(titles)
        ):
            return translated

        print("Gemini returned unexpected result:", raw_text)
        return None

    except Exception as e:
        print("Gemini exception:", repr(e))
        return None


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
            "❌ Не удалось получить новости."
        )
        return

    titles = [
        article["title"]
        for article in articles
    ]

    translated_titles = translate_titles(titles)

    if translated_titles is None:
        await status.edit_text(
            "⚠️ Новости получены, но перевод Gemini сейчас не удался."
        )
        return

    try:
        await status.delete()
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

        await update.message.reply_text(message)


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

    print("Telegram bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
