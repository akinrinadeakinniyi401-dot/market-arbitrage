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

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

BITGET_API_KEY = os.getenv("BITGET_API_KEY")
BITGET_API_SECRET = os.getenv("BITGET_API_SECRET")
BITGET_PASSPHRASE = os.getenv("BITGET_PASSPHRASE")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

bot = Bot(token=BOT_TOKEN)

# ================== SETTINGS ==================
MIN_DIFF = 0.5            # USD difference
MIN_VOLUME = 1_000_000    # USDT 24h volume
CHECK_INTERVAL = 15       # seconds
MAX_ALERTS_PER_COIN = 1   # prevent spam

running = False
worker_thread = None
sent_cache = {}  # coin -> last alert timestamp

# ================== FLASK ==================
app = Flask(__name__)

@app.route("/")
def home():
    return "Arbitrage bot running", 200

# ================== EXCHANGE FETCH ==================
def fetch_bybit_spot():
    url = "https://api.bybit.com/v5/market/tickers?category=spot"
    r = requests.get(url, timeout=10).json()

    prices = {}
    for item in r.get("result", {}).get("list", []):
        symbol = item["symbol"]
        if not symbol.endswith("USDT"):
            continue

        volume = float(item.get("turnover24h", 0))
        if volume < MIN_VOLUME:
            continue

        price = float(item["lastPrice"])
        prices[symbol] = price

    return prices


def fetch_bitget_spot():
    url = "https://api.bitget.com/api/v2/spot/market/tickers"
    r = requests.get(url, timeout=10).json()

    prices = {}
    for item in r.get("data", []):
        symbol = item["symbol"]
        if not symbol.endswith("USDT"):
            continue

        volume = float(item.get("usdtVolume", 0))
        if volume < MIN_VOLUME:
            continue

        price = float(item["lastPr"])
        prices[symbol] = price

    return prices

# ================== ARBITRAGE LOOP ==================
def arbitrage_loop():
    global running, sent_cache

    while running:
        try:
            bybit = fetch_bybit_spot()
            bitget = fetch_bitget_spot()

            common_coins = set(bybit.keys()) & set(bitget.keys())

            for coin in common_coins:
                p1 = bybit[coin]
                p2 = bitget[coin]
                diff = abs(p1 - p2)

                if diff < MIN_DIFF:
                    continue

                now = time.time()
                last_sent = sent_cache.get(coin, 0)

                # avoid repeated spam
                if now - last_sent < 300:
                    continue

                buy = "Bybit" if p1 < p2 else "Bitget"
                sell = "Bitget" if buy == "Bybit" else "Bybit"

                message = (
                    "🚨 *SPOT ARBITRAGE OPPORTUNITY*\n\n"
                    f"🪙 Coin: `{coin}`\n\n"
                    f"📉 Buy on: *{buy}*\n"
                    f"📈 Sell on: *{sell}*\n\n"
                    f"💰 Bybit Price: `{p1}`\n"
                    f"💰 Bitget Price: `{p2}`\n\n"
                    f"📊 Difference: *${diff:.2f}*\n"
                    f"⏱ Checked every {CHECK_INTERVAL}s"
                )

                bot.send_message(
                    chat_id=CHAT_ID,
                    text=message,
                    parse_mode="Markdown"
                )

                sent_cache[coin] = now

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print("Arbitrage error:", e)
            time.sleep(5)

# ================== TELEGRAM ==================
def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("▶️ Start Bot", callback_data="start")],
        [InlineKeyboardButton("⏹ Stop Bot", callback_data="stop")]
    ]
    update.message.reply_text(
        "🤖 *Arbitrage Bot Control Panel*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

def button_handler(update: Update, context: CallbackContext):
    global running, worker_thread
    query = update.callback_query
    query.answer()

    if query.data == "start" and not running:
        running = True
        worker_thread = threading.Thread(
            target=arbitrage_loop,
            daemon=True
        )
        worker_thread.start()
        query.edit_message_text("✅ Arbitrage bot started")

    elif query.data == "stop":
        running = False
        query.edit_message_text("⏹ Arbitrage bot stopped")

# ================== MAIN ==================
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 10000))
    )

if __name__ == "__main__":
    main()
