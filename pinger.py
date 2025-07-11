import time
import requests
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

URL_TO_PING = os.getenv("URL_TO_PING", "https://arbit-crxz.onrender.com")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8190525418:AAF-glDovTcw5YP4Yah9c_F-OhSrdY_kryo")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "323838150")
LOG_FILE = "ping.log"
INTERVAL_SECONDS = 300  # 5 минут

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[{timestamp}] {message}")

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": text}
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        log(f"❌ Failed to send Telegram message: {e}")

def ping():
    try:
        res = requests.get(URL_TO_PING, timeout=10)
        if res.status_code == 200:
            log(f"✅ Ping OK: {res.status_code}")
        else:
            log(f"⚠️ Ping warning: {res.status_code}")
            send_telegram(f"⚠️ Бот ответил с кодом {res.status_code}")
    except Exception as e:
        log(f"❌ Ping failed: {e}")
        send_telegram(f"❌ Бот недоступен! Ошибка: {e}")

if name == "__main__":
    while True:
        ping()
        time.sleep(INTERVAL_SECONDS)
