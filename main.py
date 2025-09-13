import os
import time
import math
import json
import threading
import traceback
from collections import defaultdict

import requests
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

# try import ccxt
try:
    import ccxt
except Exception as e:
    raise ImportError("ccxt is required. Install: pip install ccxt") from e

# ----------------- CONFIG -----------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
PORT = int(os.getenv("PORT", 10000))

POLL_INTERVAL = 30                 # seconds between full scans (default 30)
SPREAD_THRESHOLD = 0.001           # minimal relative spread to alert (0.001 == 0.1%)
MAX_SPREAD = 0.10                  # ignore spreads > 10% as likely fake
MIN_LIQUIDITY_USD = 1000.0         # minimal USD depth on both sides (if orderbook available)
ALERT_COOLDOWN = 300               # seconds to suppress duplicate alerts
ORDERBOOK_LEVELS = 5               # top levels to sum for liquidity checks

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) arbit-bot/1.0"}

# Exchange ids we will try to instantiate (ccxt ids / common names)
EXCHANGE_IDS = [
    "binance", "huobipro", "bybit", "okx", "kucoin", "gateio", "mexc",
    "bitget", "coinbasepro", "kraken", "bitstamp", "bithumb",
    "bitfinex", "poloniex", "whitebit", "lbank", "coinex", "bittrex"
]

# Default fees: set to 0.0 (not hardcoded). You can set per-exchange at runtime via /setfee
FEES = defaultdict(lambda: 0.0)

# 40 USDT pairs
TRADING_PAIRS = [
    "BTC/USDT","ETH/USDT","BNB/USDT","SOL/USDT","XRP/USDT",
    "DOGE/USDT","TON/USDT","TRX/USDT","ADA/USDT","MATIC/USDT",
    "AVAX/USDT","DOT/USDT","SHIB/USDT","LTC/USDT","BCH/USDT",
    "UNI/USDT","LINK/USDT","ATOM/USDT","XLM/USDT","NEAR/USDT",
    "APT/USDT","OP/USDT","ARB/USDT","FIL/USDT","ETC/USDT",
    "ICP/USDT","HBAR/USDT","SAND/USDT","AXS/USDT","FLOW/USDT",
    "CHZ/USDT","EOS/USDT","RUNE/USDT","ALGO/USDT","MANA/USDT",
    "DYDX/USDT","GRT/USDT","CRV/USDT","1INCH/USDT","MKR/USDT"
]

# ----------------- State -----------------
last_alerts = {}   # key -> timestamp
running = True
exchange_instances = {}  # id -> ccxt instance

# ----------------- Flask -----------------
app = Flask(__name__)

# ----------------- Telegram -----------------
def telegram_send(text, parse_mode=None, chat_id=None):
    token = TELEGRAM_BOT_TOKEN
    cid = chat_id or TELEGRAM_CHAT_ID
    if not token or not cid:
        print("[telegram] token or chat_id missing")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": cid, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        requests.post(url, json=payload, timeout=8)
    except Exception as e:
        print("[telegram] send error:", e)

# ----------------- Helpers -----------------
def safe_fetch_ticker(exchange, pair):
    """
    Try fetch_ticker for the pair using ccxt exchange instance.
    Returns (bid, ask) or (None, None)
    """
    try:
        if not exchange:
            return None, None
        if not exchange.has.get('fetchTicker', False):
            return None, None
        ticker = exchange.fetch_ticker(pair)
        if not ticker:
            return None, None
        bid = ticker.get('bid')
        ask = ticker.get('ask')
        if bid is None and 'last' in ticker:
            bid = ticker.get('last')
        if ask is None and 'last' in ticker:
            ask = ticker.get('last')
        if bid is None or ask is None:
            return None, None
        return float(bid), float(ask)
    except Exception:
        return None, None

def safe_fetch_orderbook_usd(exchange, pair, depth=ORDERBOOK_LEVELS, side='bid'):
    """
    Return estimated USD value available on given side (bid or ask) summing top 'depth' levels.
    If not available or error -> None
    """
    try:
        if not exchange or not exchange.has.get('fetchOrderBook', False):
            return None
        ob = exchange.fetch_order_book(pair, depth)
        levels = ob.get('bids') if side == 'bid' else ob.get('asks')
        if not levels:
            return None
        usd = 0.0
        for price, amount in levels[:depth]:
            usd += float(price) * float(amount)
        return usd
    except Exception:
        return None

def create_exchange_instance(ccxt_name):
    """
    Instantiate ccxt exchange by name (tries some aliases).
    """
    cls = None
    if hasattr(ccxt, ccxt_name):
        cls = getattr(ccxt, ccxt_name)
    else:
        # try some fallbacks
        alt_map = {
            "huobipro": "huobi",
            "gateio": "gateio",
            "coinbasepro": "coinbasepro",
            "mexc": "mexc",
            "bittrex": "bittrex",
            "whitebit": "whitebit",
            "lbank": "lbank",
        }
        if ccxt_name in alt_map and hasattr(ccxt, alt_map[ccxt_name]):
            cls = getattr(ccxt, alt_map[ccxt_name])
        else:
            name_try = ccxt_name.replace("-", "").replace("_", "")
            for attr in dir(ccxt):
                if attr.lower() == name_try.lower():
                    cls = getattr(ccxt, attr)
                    break
    if not cls:
        return None
    try:
        inst = cls({'enableRateLimit': True})
        try:
            inst.headers.update(HEADERS)
        except Exception:
            pass
        try:
            inst.load_markets()
        except Exception:
            pass
        return inst
    except Exception:
        return None

def init_exchanges():
    for ex_id in EXCHANGE_IDS:
        inst = create_exchange_instance(ex_id)
        if inst:
            exchange_instances[ex_id] = inst
            print(f"[init] loaded: {ex_id} (ccxt id: {getattr(inst, 'id', 'unknown')})")
        else:
            print(f"[init] failed to load: {ex_id}")

# ----------------- Core arbitrage check -----------------
def check_arbitrage_once():
    global last_alerts
    markets = {}  # exchange -> pair -> {bid,ask}
    # fetch tickers
    for ex_name, ex_inst in exchange_instances.items():
        markets[ex_name] = {}
        for pair in TRADING_PAIRS:
            try:
                bid, ask = safe_fetch_ticker(ex_inst, pair)
                if bid and ask:
                    markets[ex_name][pair] = {"bid": float(bid), "ask": float(ask)}
            except Exception:
                pass

    checked = 0
    found = []
    for pair in TRADING_PAIRS:
        for e_buy in exchange_instances.keys():
            for e_sell in exchange_instances.keys():
                if e_buy == e_sell:
                    continue
                b_obj = markets.get(e_buy, {}).get(pair)
                s_obj = markets.get(e_sell, {}).get(pair)
                if not b_obj or not s_obj:
                    continue
                try:
                    buy_price = float(b_obj["ask"])   # price to buy on buy-exchange
                    sell_price = float(s_obj["bid"])  # price to sell on sell-exchange
                    fb = FEES.get(e_buy, 0.0) / 100.0
                    fs = FEES.get(e_sell, 0.0) / 100.0
                    effective_buy = buy_price * (1 + fb)
                    effective_sell = sell_price * (1 - fs)
                    spread = (effective_sell - effective_buy) / effective_buy  # relative
                    checked += 1
                    if spread >= SPREAD_THRESHOLD and spread <= MAX_SPREAD:
                        buy_liq = safe_fetch_orderbook_usd(exchange_instances[e_buy], pair, side='ask') or 0.0
                        sell_liq = safe_fetch_orderbook_usd(exchange_instances[e_sell], pair, side='bid') or 0.0
                        if (buy_liq and buy_liq < MIN_LIQUIDITY_USD) or (sell_liq and sell_liq < MIN_LIQUIDITY_USD):
                            print(f"[liquidity-skip] {pair} {e_buy}->{e_sell} spread={spread*100:.2f}% buy_liq={buy_liq} sell_liq={sell_liq}")
                            continue
                        key = f"{pair}:{e_buy}:{e_sell}:{round(spread,6)}"
                        last_time = last_alerts.get(key, 0)
                        if time.time() - last_time < ALERT_COOLDOWN:
                            continue
                        last_alerts[key] = time.time()
                        profit_pct = spread * 100
                        msg = (
                            "🔁 *Arbitrage Opportunity!*\n"
                            f"*Pair:* `{pair}`\n"
                            f"*Buy:* {e_buy} at {buy_price} (fee {FEES.get(e_buy,0.0)}%)\n"
                            f"*Sell:* {e_sell} at {sell_price} (fee {FEES.get(e_sell,0.0)}%)\n"
                            f"*Profit (after fees):* `{profit_pct:.2f}%`\n"
                            f"*Buy liquidity(top {ORDERBOOK_LEVELS}):* {buy_liq:.2f} USD\n"
                            f"*Sell liquidity(top {ORDERBOOK_LEVELS}):* {sell_liq:.2f} USD\n"
                        )
                        telegram_send(msg, parse_mode="Markdown")
                        found.append((pair, e_buy, e_sell, profit_pct))
                except Exception as e:
                    # don't spam logs
                    print(f"[compare error] {pair} {e_buy}->{e_sell}: {e}")
    print(f"✅ Checked {checked} comparisons, found {len(found)} opportunities")
    return found

# ----------------- Loop worker -----------------
def loop_worker():
    while running:
        try:
            check_arbitrage_once()
        except Exception as e:
            print("Error in loop:", e)
            traceback.print_exc()
        time.sleep(POLL_INTERVAL)

# ----------------- Flask endpoints -----------------
@app.route("/", methods=["GET"])
def home():
    return "Arbitrage bot running"

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Telegram webhook handler.
    Commands:
      /start
      /stop
      /status
      /pairs
      /setthreshold <percent>  (e.g. /setthreshold 0.1  for 0.1%)
      /setfee <exchange> <percent> (e.g. /setfee binance 0.1)
      /setinterval <seconds>
    """
    global running, SPREAD_THRESHOLD, POLL_INTERVAL
    upd = request.get_json(silent=True) or {}
    if "message" in upd:
        m = upd["message"]
        chat_id = m["chat"]["id"]
        text = m.get("text", "").strip()
        if text == "/start":
            telegram_send("👋 Bot running. Commands: /status /pairs /setthreshold /setfee /setinterval", chat_id=chat_id)
        elif text == "/stop":
            running = False
            telegram_send("🛑 Bot stopped (background worker will exit).", chat_id=chat_id)
        elif text == "/status":
            telegram_send("✅ Bot is running" if running else "❌ Bot stopped", chat_id=chat_id)
            telegram_send(f"Monitoring {len(exchange_instances)} exchanges, {len(TRADING_PAIRS)} pairs. Poll every {POLL_INTERVAL}s.", chat_id=chat_id)
        elif text == "/pairs":
            telegram_send("Tracked pairs:\n" + ", ".join(TRADING_PAIRS), chat_id=chat_id)
        elif text.startswith("/setthreshold"):
            try:
                val = float(text.split()[1])
                SPREAD_THRESHOLD = val/100.0 if val > 1 else val
                telegram_send(f"✅ New spread threshold: {SPREAD_THRESHOLD*100:.6f}%", chat_id=chat_id)
            except Exception:
                telegram_send("❌ Usage: /setthreshold 0.1  (for 0.1%) or /setthreshold 0.001 (decimal)", chat_id=chat_id)
        elif text.startswith("/setfee"):
            try:
                parts = text.split()
                ex = parts[1].strip()
                per = float(parts[2])
                FEES[ex] = per
                telegram_send(f"✅ Fee for {ex} set to {per}%", chat_id=chat_id)
            except Exception:
                telegram_send("❌ Usage: /setfee <exchange> <percent>  e.g. /setfee binance 0.1", chat_id=chat_id)
        elif text.startswith("/setinterval"):
            try:
                sec = int(text.split()[1])
                if sec < 5:
                    telegram_send("❌ Interval too small; choose >=5s", chat_id=chat_id)
                else:
                    POLL_INTERVAL = sec
                    telegram_send(f"✅ Poll interval set to {POLL_INTERVAL}s", chat_id=chat_id)
            except Exception:
                telegram_send("❌ Usage: /setinterval <seconds>", chat_id=chat_id)
    return "", 200

# ----------------- Entrypoint -----------------
def start_bot():
    print("[start] initializing exchanges...")
    init_exchanges()
    print("[start] starting loop worker thread")
    t = threading.Thread(target=loop_worker, daemon=True)
    t.start()
    print("[start] starting flask app")
    app.run(host="0.0.0.0", port=PORT)

if name == "__main__":
    start_bot()
