import os
import threading
import html
from http.server import BaseHTTPRequestHandler, HTTPServer

import feedparser
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


NEWS_FEEDS = {
    "🌍 Мир": {
        "url": "https://subscribe.stripes.com/rss/top-news.xml",
        "lang": "en"
    },
    "🇺🇸 США": {
        "url": "https://subscribe.stripes.com/rss/us.xml",
        "lang": "en"
    },
    "🇪🇺 Европа": {
        "url": "https://subscribe.stripes.com/rss/europe.xml",
        "lang": "en"
    },
    "🇨🇳 Китай": {
        "url": "https://www.chinanews.com.cn/rss/china.xml",
        "lang": "zh-CN"
    },
}


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


def translate_to_russian(text, source_lang):
    try:
        response = requests.get(
            "https://api.mymemory.translated.net/get",
            params={
                "q": text,
                "langpair": f"{source_lang}|ru"
            },
            timeout=15
        )

        response.raise_for_status()
        data = response.json()

        translated = data.get("responseData", {}).get("translatedText")

        if translated:
            return html.unescape(translated)

    except Exception as e:
        print(f"Translation error: {e}")

    # Если переводчик временно недоступен,
    # бот всё равно покажет оригинальный заголовок.
    return text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я работаю.\n\n"
        "Команда /news — последние новости на русском 🌍"
    )


async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_message = await update.message.reply_text(
        "🔎 Собираю и перевожу свежие новости..."
    )

    found = 0

    for category, source in NEWS_FEEDS.items():

        feed = feedparser.parse(source["url"])

        if not feed.entries:
            continue

        article = feed.entries[0]

        original_title = article.get("title", "Без заголовка")
        link = article.get("link", "")

        russian_title = translate_to_russian(
            original_title,
            source["lang"]
        )

        source_name = feed.feed.get("title", "Источник")

        message = (
            f"{category}\n\n"
            f"📰 {russian_title}\n\n"
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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("news", news))

    print("Telegram bot started")

    app.run_polling()


if __name__ == "__main__":
    main()



