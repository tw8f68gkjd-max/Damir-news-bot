import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import feedparser
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


# Первые источники для теста
NEWS_FEEDS = {
    "🌍 Мир": "https://subscribe.stripes.com/rss/top-news.xml",
    "🇺🇸 США": "https://subscribe.stripes.com/rss/us.xml",
    "🇪🇺 Европа": "https://subscribe.stripes.com/rss/europe.xml",
    "🇨🇳 Китай": "https://www.chinanews.com.cn/rss/china.xml",
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я работаю.\n\n"
        "Команда /news — последние новости 🌍"
    )


async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Собираю свежие новости...")

    found = 0

    for category, url in NEWS_FEEDS.items():
        feed = feedparser.parse(url)

        if not feed.entries:
            continue

        article = feed.entries[0]

        title = article.get("title", "Без заголовка")
        link = article.get("link", "")

        message = (
            f"{category}\n\n"
            f"📰 {title}\n\n"
            f"🔗 {link}"
        )

        await update.message.reply_text(message)
        found += 1

    if found == 0:
        await update.message.reply_text(
            "Не удалось получить новости. Попробуй позже."
        )


def main():
    threading.Thread(target=run_web_server, daemon=True).start()

    token = os.environ["TELEGRAM_BOT_TOKEN"]

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("news", news))

    print("Telegram bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
