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
MIN_DIFF = 0.5
MIN_VOLUME = 1_000_000
CHECK_INTERVAL = 15

running = False
worker_thread = None
sent_cache = {}

# ================== FLASK ==================
app = Flask(__name__)

@app.route("/")
def home():
    return "Arbitrage bot running", 200

# ================== UI ==================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Start Bot", callback_data="start")],
        [InlineKeyboardButton("⏹ Stop Bot", callback_data="stop")]
    ])

def back_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ])

# ================== EXCHANGE FETCH ==================
def fetch_bybit_spot():
    print("[CRAWL] Fetching Bybit spot tickers...")
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

        prices[symbol] = float(item["lastPrice"])

    print(f"[CRAWL] Bybit valid pairs: {len(prices)}")
    return prices


def fetch_bitget_spot():
    print("[CRAWL] Fetching Bitget spot tickers...")
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

        prices[symbol] = float(item["lastPr"])

    print(f"[CRAWL] Bitget valid pairs: {len(prices)}")
    return prices

# ================== ARBITRAGE LOOP ==================
def arbitrage_loop():
    global running, sent_cache

    print("[BOT] Arbitrage loop started")

    while running:
        try:
            bybit = fetch_bybit_spot()
            bitget = fetch_bitget_spot()

            common_coins = set(bybit.keys()) & set(bitget.keys())
            print(f"[SCAN] Common coins: {len(common_coins)}")

            found = 0
            for coin in common_coins:
                p1 = bybit[coin]
                p2 = bitget[coin]
                diff = abs(p1 - p2)

                if diff < MIN_DIFF:
                    continue

                now = time.time()
                if now - sent_cache.get(coin, 0) < 300:
                    continue

                buy = "Bybit" if p1 < p2 else "Bitget"
                sell = "Bitget" if buy == "Bybit" else "Bybit"

                message = (
                    "🚨 *SPOT ARBITRAGE OPPORTUNITY*\n\n"
                    f"🪙 `{coin}`\n"
                    f"📉 Buy: *{buy}*\n"
                    f"📈 Sell: *{sell}*\n\n"
                    f"💰 Bybit: `{p1}`\n"
                    f"💰 Bitget: `{p2}`\n"
                    f"📊 Difference: *${diff:.2f}*"
                )

                bot.send_message(
                    chat_id=CHAT_ID,
                    text=message,
                    parse_mode="Markdown",
                    reply_markup=back_menu()
                )

                sent_cache[coin] = now
                found += 1

            print(f"[SCAN] Opportunities found: {found}")
            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print("[ERROR] Arbitrage error:", e)
            time.sleep(5)

    print("[BOT] Arbitrage loop stopped")

# ================== TELEGRAM ==================
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🤖 *Arbitrage Bot Control Panel*",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

def button_handler(update: Update, context: CallbackContext):
    global running, worker_thread
    query = update.callback_query
    query.answer()

    if query.data == "start" and not running:
        running = True
        worker_thread = threading.Thread(target=arbitrage_loop, daemon=True)
        worker_thread.start()
        query.edit_message_text("✅ Arbitrage bot started", reply_markup=main_menu())

    elif query.data == "stop":
        running = False
        query.edit_message_text("⏹ Arbitrage bot stopped", reply_markup=main_menu())

    elif query.data == "back":
        query.edit_message_text(
            "🤖 *Arbitrage Bot Control Panel*",
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )

# ================== MAIN ==================
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()
    print("[BOT] Telegram polling started")

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 10000))
    )

if __name__ == "__main__":
    main()
