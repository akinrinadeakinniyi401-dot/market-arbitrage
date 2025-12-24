import os
import time
import threading
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ================== ENV ==================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BYBIT_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_SECRET = os.getenv("BYBIT_API_SECRET")

BITGET_KEY = os.getenv("BITGET_API_KEY")
BITGET_SECRET = os.getenv("BITGET_API_SECRET")
BITGET_PASSPHRASE = os.getenv("BITGET_PASSPHRASE")

# ================== SETTINGS ==================
MIN_DIFF = 0.5          # USD
MIN_VOLUME = 1_000_000  # USDT
CHECK_INTERVAL = 10     # seconds

running = False
worker_thread = None

# ================== API FETCH ==================
def fetch_bybit_prices():
    url = "https://api.bybit.com/v5/market/tickers?category=spot"
    data = requests.get(url, timeout=10).json()
    prices = {}

    for item in data.get("result", {}).get("list", []):
        symbol = item["symbol"]
        if symbol.endswith("USDT"):
            volume = float(item.get("turnover24h", 0))
            if volume >= MIN_VOLUME:
                prices[symbol] = float(item["lastPrice"])

    return prices


def fetch_bitget_prices():
    url = "https://api.bitget.com/api/v2/spot/market/tickers"
    data = requests.get(url, timeout=10).json()
    prices = {}

    for item in data.get("data", []):
        symbol = item["symbol"]
        if symbol.endswith("USDT"):
            volume = float(item.get("usdtVolume", 0))
            if volume >= MIN_VOLUME:
                prices[symbol] = float(item["lastPr"])

    return prices

# ================== ARBITRAGE LOOP ==================
def arbitrage_loop(app):
    global running

    while running:
        try:
            bybit = fetch_bybit_prices()
            bitget = fetch_bitget_prices()

            common = set(bybit.keys()) & set(bitget.keys())

            for coin in common:
                price1 = bybit[coin]
                price2 = bitget[coin]
                diff = abs(price1 - price2)

                if diff >= MIN_DIFF:
                    buy = "Bybit" if price1 < price2 else "Bitget"
                    sell = "Bitget" if buy == "Bybit" else "Bybit"

                    message = (
                        "🚨 *SPOT ARBITRAGE ALERT*\n\n"
                        f"🪙 Coin: `{coin}`\n"
                        f"📉 Buy on: *{buy}*\n"
                        f"📈 Sell on: *{sell}*\n\n"
                        f"💰 Bybit: `{price1}`\n"
                        f"💰 Bitget: `{price2}`\n\n"
                        f"📊 Difference: *${diff:.2f}*\n"
                        f"⏱ Interval: {CHECK_INTERVAL}s"
                    )

                    app.bot.send_message(
                        chat_id=CHAT_ID,
                        text=message,
                        parse_mode="Markdown"
                    )

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print("Error:", e)
            time.sleep(5)

# ================== TELEGRAM COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("▶️ Start Bot", callback_data="start_bot")],
        [InlineKeyboardButton("⏹ Stop Bot", callback_data="stop_bot")]
    ]
    await update.message.reply_text(
        "🤖 *Arbitrage Bot Control*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global running, worker_thread

    query = update.callback_query
    await query.answer()

    if query.data == "start_bot" and not running:
        running = True
        worker_thread = threading.Thread(
            target=arbitrage_loop,
            args=(context.application,),
            daemon=True
        )
        worker_thread.start()
        await query.edit_message_text("✅ Arbitrage bot started")

    elif query.data == "stop_bot":
        running = False
        await query.edit_message_text("⏹ Arbitrage bot stopped")

# ================== MAIN ==================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
