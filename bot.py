import os
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


def gemini_translate(text):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print("GEMINI_API_KEY is missing")
        return None

    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{GEMINI_MODEL}:generateContent"
    )

    prompt = f"""
Переведи следующий заголовок новости на естественный русский язык.

Правила:
- передай смысл максимально точно;
- не добавляй фактов от себя;
- имена, страны, компании, даты и числа не искажай;
- не объясняй перевод;
- не используй кавычки вокруг всего ответа;
- верни ТОЛЬКО русский заголовок.

Заголовок:
{text}
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
                            {"text": prompt}
                        ]
                    }
                ]
            },
            timeout=30,
        )

        if response.status_code != 200:
            print(
                "Gemini error:",
                response.status_code,
                response.text[:500],
            )
            return None

        data = response.json()

        translated = (
            data["candidates"][0]
            ["content"]["parts"][0]["text"]
            .strip()
        )

        return translated

    except Exception as e:
        print(f"Gemini translation error: {e}")
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я работаю.\n\n"
        "📰 /news — последние новости\n"
        "🧪 /testai — проверить перевод через Gemini"
    )


async def test_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧪 Проверяю Gemini..."
    )

    original = "Major technology companies announce new AI investments"

    translated = gemini_translate(original)

    if translated:
        await update.message.reply_text(
            f"✅ Gemini работает!\n\n"
            f"🇷🇺 {translated}"
        )
    else:
        await update.message.reply_text(
            "❌ Gemini пока не отвечает.\n"
            "Посмотрим логи Render."
        )


async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_message = await update.message.reply_text(
        "🔎 Собираю и перевожу свежие новости..."
    )

    found = 0

    for category, url in NEWS_FEEDS.items():
        feed = feedparser.parse(url)

        if not feed.entries:
            continue

        article = feed.entries[0]

        original_title = article.get(
            "title",
            "Без заголовка"
        )

        link = article.get("link", "")
        source_name = feed.feed.get(
            "title",
            "Источник"
        )

        russian_title = gemini_translate(
            original_title
        )

        if russian_title:
            title_to_show = russian_title
        else:
            title_to_show = (
                f"{original_title}\n"
                "⚠️ Перевод временно недоступен"
            )

        message = (
            f"{category}\n\n"
            f"📰 {title_to_show}\n\n"
            f"🗞 {source_name}\n"
            f"🔗 {link}"
        )

        await update.message.reply_text(message)
        found += 1

    if found == 0:
        await update.message.reply_text(
            "Не удалось получить новости. Попробуй позже."
        )

    try:
        await status_message.delete()
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

    app.add_handler(
        CommandHandler("testai", test_ai)
    )

    print("Telegram bot started")

    app.run_polling()


if __name__ == "__main__":
    main()
