import os
import time
import threading
import requests
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

EXCHANGES = ["binance", "htx", "bybit", "okx", "kucoin", "gate", "mexc"]
TRADING_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
SPREAD_THRESHOLD = 0.001

FEES = {
    "binance": 0.1, "htx": 0.2, "bybit": 0.1, "okx": 0.1,
    "kucoin": 0.1, "gate": 0.2, "mexc": 0.1
}

def get_prices(exchange):
    return {
        "BTC/USDT": {"ask": 63000.0, "bid": 63200.0},
        "ETH/USDT": {"ask": 3500.0, "bid": 3550.0},
        "SOL/USDT": {"ask": 140.0, "bid": 145.0}
    }

def check_arbitrage():
    while True:
        market_data = {ex: get_prices(ex) for ex in EXCHANGES}
        checked, found = 0, 0
        for pair in TRADING_PAIRS:
            for ex1 in EXCHANGES:
                for ex2 in EXCHANGES:
                    if ex1 == ex2:
                        continue
                    try:
                        buy = market_data[ex1][pair]["ask"]
                        sell = market_data[ex2][pair]["bid"]
                        fee_buy = FEES[ex1] / 100
                        fee_sell = FEES[ex2] / 100
                        spread = ((sell * (1 - fee_sell)) - (buy * (1 + fee_buy))) / (buy * (1 + fee_buy))
                        checked += 1
                        if spread >= SPREAD_THRESHOLD:
                            found += 1
                            msg = f"🔁 Arbitrage Opportunity!\n"                                   f"Pair: {pair}\n"                                   f"Buy on: {ex1.upper()} at {buy}\n"                                   f"Sell on: {ex2.upper()} at {sell}\n"                                   f"Profit: {spread*100:.2f}%"
                            send_telegram(msg)
                        else:
                            print(f"[{pair}] {ex1}->{ex2}: spread={spread*100:.4f}%")
                    except Exception as e:
                        print(f"Error: {e}")
        print(f"✅ Проверено {checked}, найдено {found}.")
        time.sleep(20)

def send_telegram(message, chat_id=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": chat_id or TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=data, timeout=5)
    except Exception as e:
        print("Telegram Error:", e)

def check_bot():
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
        res = requests.get(url).json()
        print("🤖 Telegram Bot Info:", res)
    except Exception as e:
        print("Telegram Bot Error:", e)

def set_webhook():
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
        res = requests.post(url, data={"url": f"{WEBHOOK_URL}"})
        print("🌐 Webhook set:", res.json())
    except Exception as e:
        print("Webhook Error:", e)

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Arbitrage bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    print("📥 Incoming:", update)

    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "").strip()

        if text == "/start":
            send_telegram("👋 Привет! Я арбитражный бот. Я уведомлю тебя о выгодных сделках!", chat_id)
        elif text == "/status":
            send_telegram("✅ Бот работает. Мониторинг арбитражных возможностей активен.", chat_id)
        else:
            send_telegram(f"📡 Вы написали: {text}", chat_id)

    return '', 200

if __name__ == "__main__":
    check_bot()
    set_webhook()
    threading.Thread(target=check_arbitrage).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    json()[0]
        res[pair] = {"ask": float(d["lowest_ask"]), "bid": float(d["highest_bid"])}
    return res

# --- MEXC -------------------------------------------------------------
def _mexc():
    res = {}
    for sym, pair in [("BTCUSDT", "BTC/USDT"), ("ETHUSDT", "ETH/USDT"), ("SOLUSDT", "SOL/USDT")]:
        url = f"https://api.mexc.com/api/v3/ticker/bookTicker?symbol={sym}"
        d   = requests.get(url, timeout=5).json()
        res[pair] = {"ask": float(d["askPrice"]), "bid": float(d["bidPrice"])}
    return res

# ----------------------------------------------------------------------
# 🎯 2.  Арбитраж и Telegram
# ----------------------------------------------------------------------
def check_arbitrage():
    while True:
        market_data = {ex: get_prices(ex) for ex in EXCHANGES}
        checked = found = 0
        for pair in TRADING_PAIRS:
            for ex_buy in EXCHANGES:
                for ex_sell in EXCHANGES:
                    if ex_buy == ex_sell:
                        continue
                    try:
                        buy  = market_data[ex_buy][pair]["ask"]
                        sell = market_data[ex_sell][pair]["bid"]
                        fee_b = FEES[ex_buy]  / 100
                        fee_s = FEES[ex_sell] / 100
                        spread = ((sell * (1 - fee_s)) - (buy * (1 + fee_b))) / (buy * (1 + fee_b))
                        checked += 1
                        if spread >= SPREAD_THRESHOLD:
                            found += 1
                            msg = (
                                "🔁 *Arbitrage Opportunity!*\n"
                                f"*Pair:* `{pair}`\n"
                                f"*Buy on:* {ex_buy.upper()} at `{buy}`\n"
                                f"*Sell on:* {ex_sell.upper()} at `{sell}`\n"
                                f"*Profit:* `{spread*100:.2f}%`"
                            )
                            send_telegram(msg, parse_mode="Markdown")
                    except KeyError:
                        # цена не получена с одной из бирж
                        continue
                    except Exception as e:
                        print("Calc error:", e)
        print(f"✅ Checked {checked}, found {found} opportunities.")
        time.sleep(20)

# ----------------------------------------------------------------------
# Telegram helpers
# ----------------------------------------------------------------------
def send_telegram(text, chat_id=None, parse_mode=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id or TELEGRAM_CHAT_ID, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print("Telegram send error:", e)

def send_start_buttons(chat_id):
    # inline-кнопки
    keyboard = {
        "inline_keyboard": [
            [{"text": "📊 Статус",   "callback_data": "status"}],
            [{"text": "🪙 Пары",      "callback_data": "pairs"}],
            [{"text": "⚙️ Порог",    "callback_data": "threshold"}]
        ]
    }
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "👋 Привет! Выберите действие:",
        "reply_markup": json.dumps(keyboard)
    }
    requests.post(url, json=payload, timeout=5)

# ----------------------------------------------------------------------
# Flask
# ----------------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Arbitrage bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    # print(json.dumps(update, indent=2, ensure_ascii=False))
    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text    = update["message"].get("text", "").strip()

        if text == "/start":
            send_start_buttons(chat_id)

    elif "callback_query" in update:
        q       = update["callback_query"]
        chat_id = q["message"]["chat"]["id"]
        data    = q["data"]

        if data == "status":
            send_telegram("✅ Бот работает. Мониторинг активен.", chat_id)
        elif data == "pairs":
            send_telegram("🪙 Отслеживаемые пары:\n" + "\n".join(TRADING_PAIRS), chat_id)
        elif data == "threshold":
            send_telegram(f"⚙️ Порог: {SPREAD_THRESHOLD*100:.2f} %", chat_id)

    return "", 200

# ----------------------------------------------------------------------
if name == "__main__":
    # запустить бот
    threading.Thread(target=check_arbitrage, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
