import os, time, threading, requests, json
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()
UPTIME_TOKEN = os.getenv("UPTIME_TOKEN")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
WEBHOOK_URL        = os.getenv("WEBHOOK_URL")

EXCHANGES = [
    "binance", "htx", "bybit", "okx", "kucoin", "gate", "mexc",
    "bitget", "coinbase", "kraken", "bitstamp", "bithumb",
    "bitfinex", "poloniex", "whitebit", "lbank", "crypto"
]

TRADING_PAIRS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT",
    "MATIC/USDT", "LTC/USDT", "TRX/USDT", "TON/USDT", "SHIB/USDT",
    "ATOM/USDT", "NEAR/USDT", "OP/USDT", "APT/USDT", "FIL/USDT",
    "PEPE/USDT", "ARB/USDT", "SUI/USDT", "UNI/USDT", "ETC/USDT",
    "INJ/USDT", "RUNE/USDT", "TIA/USDT", "SEI/USDT", "STX/USDT",
    "BCH/USDT", "GALA/USDT", "IMX/USDT", "AAVE/USDT", "DYDX/USDT",
    "HBAR/USDT", "EOS/USDT", "CRV/USDT", "FLOW/USDT", "MKR/USDT"
]

SPREAD_THRESHOLD = 0.001  # 0.1%
FEES = {ex: 0.1 for ex in EXCHANGES}
FEES.update({"htx":0.2, "gate":0.2, "bithumb":0.25})

last_alerts = {}  # защита от дубликатов

def get_prices(exchange):
    try:
        func = globals().get(f"_{exchange}")
        return func() if func else {}
    except Exception as e:
        print(f"[{exchange}] API error:", e)
        return {}

# ------------------------ биржевые функции ------------------------

def _binance():
    res = {}
    data = requests.get("https://api.binance.com/api/v3/ticker/bookTicker", timeout=5).json()
    for d in data:
        sym = d["symbol"]
        for p in TRADING_PAIRS:
            if sym == p.replace("/", ""):
                res[p] = {"ask":float(d["askPrice"]), "bid":float(d["bidPrice"])}
    return res

def _htx():
    res = {}
    for p in TRADING_PAIRS:
        sym = p.replace("/", "").lower()
        j = requests.get(f"https://api.huobi.pro/market/detail/merged?symbol={sym}", timeout=5).json()
        t = j.get("tick")
        if t:
            res[p] = {"ask":float(t["ask"][0]), "bid":float(t["bid"][0])}
    return res

def _bybit():
    res = {}
    j = requests.get("https://api.bybit.com/v2/public/tickers", timeout=5).json()["result"]
    for d in j:
        sym = d["symbol"]
        for p in TRADING_PAIRS:
            if sym == p.replace("/", ""):
                res[p] = {"ask":float(d["ask_price"]), "bid":float(d["bid_price"])}
    return res

def _okx():
    res = {}
    for p in TRADING_PAIRS:
        inst = p.replace("/", "-")
        j = requests.get(f"https://www.okx.com/api/v5/market/ticker?instId={inst}", timeout=5).json()
        d = j.get("data")
        if d:
            ask, bid = float(d[0]["askPx"]), float(d[0]["bidPx"])
            res[p] = {"ask":ask, "bid":bid}
    return res

def _kucoin():
    res = {}
    j = requests.get("https://api.kucoin.com/api/v1/market/allTickers", timeout=5).json()["data"]["ticker"]
    for d in j:
        sym = d["symbol"]
        for p in TRADING_PAIRS:
            if sym == p.replace("/", "-"):
                res[p] = {"ask":float(d["sell"]), "bid":float(d["buy"])}
    return res

def _gate():
    res = {}
    j = requests.get("https://api.gate.io/api2/1/tickers", timeout=5).json()
    for p in TRADING_PAIRS:
        key = p.replace("/", "_").lower()
        o = j.get(key)
        if o:
            res[p] = {"ask":float(o["lowestAsk"]), "bid":float(o["highestBid"])}
    return res

def _mexc():
    res = {}
    j = requests.get("https://api.mexc.com/api/v3/ticker/bookTicker", timeout=5).json()
    for d in j:
        for p in TRADING_PAIRS:
            if d["symbol"] == p.replace("/", ""):
                res[p] = {"ask":float(d["askPrice"]), "bid":float(d["bidPrice"])}
    return res

def _bitget():
    res = {}
    for p in TRADING_PAIRS:
        s = p.replace("/", "").lower()
        j = requests.get(f"https://api.bitget.com/api/spot/v3/public/ticker/{s}", timeout=5).json()
        d = j.get("data")
        if d:
            res[p] = {"ask":float(d["sell"]), "bid":float(d["buy"])}
    return res

def _coinbase():
    res = {}
    for p in TRADING_PAIRS:
        s = p.replace("/", "-")
        r = requests.get(f"https://api.exchange.coinbase.com/products/{s}/ticker", timeout=5)
        if r.ok:
            o = r.json()
            res[p] = {"ask":float(o["ask"]), "bid":float(o["bid"])}
    return res

def _kraken():
    res = {}
    j = requests.get("https://api.kraken.com/0/public/Ticker?pair=" + ",".join([p.replace("/", "USDT") for p in TRADING_PAIRS]), timeout=5).json().get("result", {})
    for k, v in j.items():
        if "a" in v and "b" in v:
            if k.endswith("USDT"):
                p = k[:-4] + "/USDT"
                if p in TRADING_PAIRS:
                    res[p] = {"ask":float(v["a"][0]), "bid":float(v["b"][0])}
    return res

def _bitstamp():
    res = {}
    for p in TRADING_PAIRS:
        s = p.replace("/", "").lower()
        j = requests.get(f"https://www.bitstamp.net/api/v2/ticker/{s}/", timeout=5).json()
        res[p] = {"ask":float(j["ask"]), "bid":float(j["bid"])}
    return res

def _bithumb():
    res = {}
    for p in TRADING_PAIRS:
        s = p.replace("/", "").lower()
        j = requests.get(f"https://api.bithumb.com/public/ticker/{s}", timeout=5).json()
        d = j.get("data")
        if d:
            res[p] = {"ask":float(d["sell_price"]), "bid":float(d["buy_price"])}
    return res

def _bitfinex():
    res = {}
    for p in TRADING_PAIRS:
        s = p.replace("/", "").upper()
        j = requests.get(f"https://api-pub.bitfinex.com/v2/ticker/t{s}", timeout=5).json()
        res[p] = {"ask":float(j[2]), "bid":float(j[0])}
    return res

def _poloniex():
    res = {}
    j = requests.get("https://poloniex.com/public?command=returnTicker", timeout=5).json()
    for p in TRADING_PAIRS:
        s = p.replace("/", "")
        key = f"USDT_{s}"
        o = j.get(key)
        if o:
            res[p] = {"ask":float(o["lowestAsk"]), "bid":float(o["highestBid"])}
    return res

def _whitebit():
    res = {}
    for p in TRADING_PAIRS:
        s = p.replace("/", "_")
        j = requests.get(f"https://whitebit.com/api/v4/public/ticker/{s}", timeout=5).json()
        if "ask" in j and "bid" in j:
            res[p] = {"ask":float(j["ask"]), "bid":float(j["bid"])}
    return res

def _lbank():
    res = {}
    j = requests.get("https://api.lbkex.com/v2/ticker/24hr.do?symbol=all", timeout=5).json()
    for o in j.get("data", []):
        sym = o["symbol"].upper().replace("_", "/")
        if sym in TRADING_PAIRS:
            res[sym] = {"ask":float(o["ticker"]["high"]), "bid":float(o["ticker"]["low"])}
    return res

def _crypto():
    res = {}
    for p in TRADING_PAIRS:
        s = p.replace("/", "_")
        j = requests.get(f"https://api.crypto.com/v2/public/get-ticker?instrument_name={s}", timeout=5).json()
        d = j.get("result", {}).get("data", {})
        if d:
            res[p] = {"ask":float(d["a"]), "bid":float(d["b"])}
    return res

# ------------------------ арбитраж и Telegram ------------------------

def check_arbitrage():
    global last_alerts
    while True:
        md = {ex: get_prices(ex) for ex in EXCHANGES}
        checked = found = 0
        for p in TRADING_PAIRS:
            for e1 in EXCHANGES:
                for e2 in EXCHANGES:
                    if e1 == e2: continue
                    try:
                        b = md[e1][p]["ask"]
                        s = md[e2][p]["bid"]
                        fb, fs = FEES[e1]/100, FEES[e2]/100
                        spread = ((s*(1-fs)) - (b*(1+fb))) / (b*(1+fb))
                        checked += 1
                        if spread >= SPREAD_THRESHOLD:
                            key = f"{p}:{e1}:{e2}"
                            if key in last_alerts and time.time()-last_alerts[key] < 300:
                                continue
                            last_alerts[key] = time.time()
                            found += 1
                            msg = (
                            "🔁 *Arbitrage Opportunity!*\n"
                                f"*Pair:* `{p}`\n"
                                f"*Buy:* {e1} at `{b}`\n"
                                f"*Sell:* {e2} at `{s}`\n"
                                f"*Profit:* {spread*100:.2f}%"
                            )
                            send_telegram(msg, parse_mode="Markdown")
                    except: pass
        print(f"✅ Checked {checked}, found {found}")
        time.sleep(20)

def send_telegram(text, chat_id=None, parse_mode=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id or TELEGRAM_CHAT_ID, "text": text}
    if parse_mode: data["parse_mode"] = parse_mode
    try: requests.post(url, json=data, timeout=5)
    except: pass

def send_start_buttons(chat_id):
    kb = {"inline_keyboard":[
        [{"text":"📊 Статус","callback_data":"status"}],
        [{"text":"🪙 Пары","callback_data":"pairs"}],
        [{"text":"⚙️ Порог","callback_data":"threshold"}]
    ]}
    payload = {"chat_id":chat_id,"text":"👋 Выберите:","reply_markup":json.dumps(kb)}
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json=payload)

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home(): return "✅ Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    global SPREAD_THRESHOLD
    u = request.get_json()
    if "message" in u:
        cid = u["message"]["chat"]["id"]
        t = u["message"].get("text","").strip()
        if t=="/start": send_start_buttons(cid)
        elif t=="/status": send_telegram("✅ Работаю", cid)
        elif t=="/pairs": send_telegram("🪙 "+"\n".join(TRADING_PAIRS), cid)
        elif t.startswith("/setthreshold"):
            try:
                SPREAD_THRESHOLD = float(t.split()[1])/100
                send_telegram(f"✅ Новый порог: {SPREAD_THRESHOLD*100:.2f}%", cid)
            except:
                send_telegram("❌ Формат: /setthreshold 0.3", cid)
    elif "callback_query" in u:
        d = u["callback_query"]
        cid = d["message"]["chat"]["id"]; v = d["data"]
        if v=="status": send_telegram("✅ Работаю", cid)
        elif v=="pairs": send_telegram("🪙 "+"\n".join(TRADING_PAIRS), cid)
        elif v=="threshold": send_telegram(f"⚙️ {SPREAD_THRESHOLD*100:.2f}%", cid)
    return "", 200

@app.route("/uptimerobot", methods=["POST"])
def uptimerobot():
    if request.args.get("token") != UPTIME_TOKEN:
        return "❌ Invalid token", 403
    alert = request.get_json(silent=True) or {}
    alert_type = alert.get("alert_type_friendly", "Unknown Alert")
    monitor_name = alert.get("monitor_friendly_name", "No Name")
    message = alert.get("alert_details", "No details provided")
    text = f"⚠️ *{alert_type}*\n🖥 *{monitor_name}*\n📄 {message}"
    send_telegram(text)
    return "✅ Alert received", 200

if name == "__main__":
    threading.Thread(target=check_arbitrage, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
