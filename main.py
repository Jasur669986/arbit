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
