import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я работаю.\n\n"
        "Скоро здесь будут новости в реальном времени 🌍"
    )


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))

    print("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
