import os, time, threading, requests, json
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
WEBHOOK_URL        = os.getenv("WEBHOOK_URL")

EXCHANGES      = ["binance", "htx", "bybit", "okx", "kucoin", "gate", "mexc"]
TRADING_PAIRS  = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
SPREAD_THRESHOLD = 0.001  # 0.1 %

FEES = {          # % maker / taker (средние значения)
    "binance": 0.1, "htx": 0.2, "bybit": 0.1, "okx": 0.1,
    "kucoin": 0.1,  "gate": 0.2, "mexc": 0.1
}

# ----------------------------------------------------------------------
# 🎯 1.  Реальные цены с бирж
# ----------------------------------------------------------------------
def get_prices(exchange: str) -> dict[str, dict[str, float]]:
    """
    Возвращает: { "BTC/USDT": {"ask": ..., "bid": ...}, ... }
    """
    try:
        if exchange == "binance":
            return _binance()
        if exchange == "htx":
            return _htx()
        if exchange == "bybit":
            return _bybit()
        if exchange == "okx":
            return _okx()
        if exchange == "kucoin":
            return _kucoin()
        if exchange == "gate":
            return _gate()
        if exchange == "mexc":
            return _mexc()
    except Exception as e:
        print(f"{exchange.upper()} API error:", e)
    return {}

# --- Binance ----------------------------------------------------------
def _binance():
    url = "https://api.binance.com/api/v3/ticker/bookTicker"
    data = requests.get(url, timeout=5).json()
    symbols = {"BTCUSDT": "BTC/USDT", "ETHUSDT": "ETH/USDT", "SOLUSDT": "SOL/USDT"}
    return {
        symbols[i["symbol"]]: {"ask": float(i["askPrice"]), "bid": float(i["bidPrice"])}
        for i in data if i["symbol"] in symbols
    }

# --- HTX (Huobi) ------------------------------------------------------
def _htx():
    url  = "https://api.huobi.pro/market/tickers"
    resp = requests.get(url, timeout=5).json()
    mapping = {"btcusdt": "BTC/USDT", "ethusdt": "ETH/USDT", "solusdt": "SOL/USDT"}
    return {
        mapping[i["symbol"]]: {"ask": float(i["ask"]), "bid": float(i["bid"])}
        for i in resp.get("data", []) if i["symbol"] in mapping
    }

# --- Bybit ------------------------------------------------------------
def _bybit():
    res = {}
    for sym, pair in [("BTCUSDT", "BTC/USDT"), ("ETHUSDT", "ETH/USDT"), ("SOLUSDT", "SOL/USDT")]:
        url  = f"https://api.bybit.com/v2/public/tickers?symbol={sym}"
        j    = requests.get(url, timeout=5).json()
        itm  = j["result"][0]
        res[pair] = {"ask": float(itm["ask_price"]), "bid": float(itm["bid_price"])}
    return res

# --- OKX --------------------------------------------------------------
def _okx():
    url  = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
    tick = {i["instId"]: i for i in requests.get(url, timeout=5).json()["data"]}
    def conv(inst):
        d = tick[inst]; return {"ask": float(d["askPx"]), "bid": float(d["bidPx"])}
    return {
        "BTC/USDT": conv("BTC-USDT"),
        "ETH/USDT": conv("ETH-USDT"),
        "SOL/USDT": conv("SOL-USDT")
    }

# --- KuCoin -----------------------------------------------------------
def _kucoin():
    def get(symbol):
        url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}"
        d   = requests.get(url, timeout=5).json()["data"]
        return {"ask": float(d["price"]), "bid": float(d["bestBid"])}
    return {
        "BTC/USDT": get("BTC-USDT"),
        "ETH/USDT": get("ETH-USDT"),
        "SOL/USDT": get("SOL-USDT")
    }

# --- Gate.io ----------------------------------------------------------
def _gate():
    res = {}
    for cp, pair in [
        ("BTC_USDT", "BTC/USDT"),
        ("ETH_USDT", "ETH/USDT"),
        ("SOL_USDT", "SOL/USDT"),
    ]:
        url = f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={cp}"
        d   = requests.get(url, timeout=5).json()[0]
        res[pair] = {
        "ask": float(d["lowest_ask"]),
            "bid": float(d["highest_bid"])
        }
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
                    if ex_buy == ex_sell: continue
                    try:
                        buy  = market_data[ex_buy][pair]["ask"]
                        sell = market_data[ex_sell][pair]["bid"]
                        fee_b = FEES[ex_buy]  / 100
                        fee_s = FEES[ex_sell] / 100
                        spread = ((sell*(1-fee_s)) - (buy*(1+fee_b))) / (buy*(1+fee_b))
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
    keyboard = {
        "inline_keyboard": [
            [{"text": "📊 Статус",   "callback_data": "status"}],
            [{"text": "🪙 Пары",     "callback_data": "pairs"}],
            [{"text": "⚙️ Порог",   "callback_data": "threshold"}]
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
            send_telegram("✅ Бот работает.Мониторинг активен.", chat_id)
        elif data == "pairs":
            send_telegram("🪙 Отслеживаемые пары:\n" + "\n".join(TRADING_PAIRS), chat_id)
        elif data == "threshold":
            send_telegram(f"⚙️ Порог: {SPREAD_THRESHOLD*100:.2f} %", chat_id)

    return "", 200

# ----------------------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=check_arbitrage, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
