import os
import threading
import time
import requests
from flask import Flask
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

# ================== ENV ==================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=BOT_TOKEN)

# ================== FLASK (KEEP ALIVE) ==================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running", 200

# ================== BOT CONTROL ==================
running = False
worker_thread = None

def arbitrage_loop():
    global running
    while running:
        # Placeholder (your arbitrage logic already works)
        bot.send_message(chat_id=CHAT_ID, text="🤖 Arbitrage bot running...")
        time.sleep(30)

# ================== TELEGRAM ==================
def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("▶️ Start Bot", callback_data="start")],
        [InlineKeyboardButton("⏹ Stop Bot", callback_data="stop")]
    ]
    update.message.reply_text(
        "Arbitrage Bot Control",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def button_handler(update: Update, context: CallbackContext):
    global running, worker_thread
    query = update.callback_query
    query.answer()

    if query.data == "start" and not running:
        running = True
        worker_thread = threading.Thread(target=arbitrage_loop, daemon=True)
        worker_thread.start()
        query.edit_message_text("✅ Bot started")

    elif query.data == "stop":
        running = False
        query.edit_message_text("⏹ Bot stopped")

# ================== MAIN ==================
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()

    # Run Flask for Render
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

if __name__ == "__main__":
    main()
