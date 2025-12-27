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

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

bot = Bot(token=BOT_TOKEN)

# ================== SETTINGS ==================
MIN_DIFF = 0.5          # USD difference
CHECK_INTERVAL = 30     # seconds (safe for Bybit)
ALERT_COOLDOWN = 300    # seconds per coin
API_ALERT_COOLDOWN = 600

running = False
worker_thread = None

sent_cache = {}         # coin -> timestamp
api_alert_cache = {}   # exchange -> timestamp

# ================== FLASK ==================
app = Flask(__name__)

@app.route("/")
def home():
    return "Arbitrage bot running", 200

# ================== UTIL ==================
def api_block_alert(exchange, message):
    now = time.time()
    last = api_alert_cache.get(exchange, 0)

    if now - last < API_ALERT_COOLDOWN:
        return

    bot.send_message(
        chat_id=CHAT_ID,
        text=f"⚠️ *{exchange} API ISSUE*\n\n{message}",
        parse_mode="Markdown"
    )

    api_alert_cache[exchange] = now

# ================== EXCHANGE FETCH ==================
def fetch_bybit_spot():
    print("[CRAWL] Fetching Bybit spot tickers...")
    url = "https://api.bybit.com/v5/market/tickers?category=spot"

    try:
        r = requests.get(url, timeout=10)
    except Exception as e:
        print("[ERROR] Bybit request failed:", e)
        api_block_alert("Bybit", "Request failed / network error")
        return {}

    if r.status_code != 200:
        print("[ERROR] Bybit HTTP:", r.status_code)
        api_block_alert("Bybit", f"HTTP {r.status_code}")
        return {}

    try:
        data = r.json()
    except Exception:
        print("[ERROR] Bybit returned non-JSON (blocked or rate-limited)")
        api_block_alert("Bybit", "Returned non-JSON response (rate-limit or block)")
        return {}

    prices = {}
    for item in data.get("result", {}).get("list", []):
        symbol = item.get("symbol", "")
        if symbol.endswith("USDT"):
            prices[symbol] = float(item["lastPrice"])

    print(f"[OK] Bybit fetched {len(prices)} coins")
    return prices


def fetch_bitget_spot():
    print("[CRAWL] Fetching Bitget spot tickers...")
    url = "https://api.bitget.com/api/v2/spot/market/tickers"

    try:
        r = requests.get(url, timeout=10)
    except Exception as e:
        print("[ERROR] Bitget request failed:", e)
        api_block_alert("Bitget", "Request failed / network error")
        return {}

    if r.status_code != 200:
        print("[ERROR] Bitget HTTP:", r.status_code)
        api_block_alert("Bitget", f"HTTP {r.status_code}")
        return {}

    try:
        data = r.json()
    except Exception:
        print("[ERROR] Bitget returned non-JSON")
        api_block_alert("Bitget", "Returned non-JSON response")
        return {}

    prices = {}
    for item in data.get("data", []):
        symbol = item.get("symbol", "")
        if symbol.endswith("USDT"):
            prices[symbol] = float(item["lastPr"])

    print(f"[OK] Bitget fetched {len(prices)} coins")
    return prices

# ================== ARBITRAGE LOOP ==================
def arbitrage_loop():
    global running

    print("[BOT] Arbitrage loop started")

    while running:
        try:
            bybit = fetch_bybit_spot()
            bitget = fetch_bitget_spot()

            common = set(bybit) & set(bitget)

            for coin in common:
                p1 = bybit[coin]
                p2 = bitget[coin]
                diff = abs(p1 - p2)

                if diff < MIN_DIFF:
                    continue

                now = time.time()
                if now - sent_cache.get(coin, 0) < ALERT_COOLDOWN:
                    continue

                buy = "Bybit" if p1 < p2 else "Bitget"
                sell = "Bitget" if buy == "Bybit" else "Bybit"

                msg = (
                    "🚨 *SPOT ARBITRAGE FOUND*\n\n"
                    f"🪙 `{coin}`\n\n"
                    f"📉 Buy: *{buy}*\n"
                    f"📈 Sell: *{sell}*\n\n"
                    f"💰 Bybit: `{p1}`\n"
                    f"💰 Bitget: `{p2}`\n\n"
                    f"📊 Diff: *${diff:.2f}*"
                )

                bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
                sent_cache[coin] = now

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print("[ERROR] Arbitrage loop error:", e)
            time.sleep(5)

    print("[BOT] Arbitrage loop stopped")

# ================== TELEGRAM UI ==================
def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Start Bot", callback_data="start")],
        [InlineKeyboardButton("⏹ Stop Bot", callback_data="stop")]
    ])

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🤖 *Arbitrage Bot Control Panel*",
        reply_markup=menu_keyboard(),
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
        query.edit_message_text("✅ Bot started", reply_markup=menu_keyboard())

    elif query.data == "stop":
        running = False
        query.edit_message_text("⏹ Bot stopped", reply_markup=menu_keyboard())

# ================== MAIN ==================
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()
    print("[BOT] Telegram polling started")

    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

if __name__ == "__main__":
    main()
