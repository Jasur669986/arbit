import os, time, requests, datetime
from dotenv import load_dotenv

# ───────────────────────────────────────────────────────────
load_dotenv()                                    # .env рядом
BOT_TOKEN  = os.getenv("8190525418:AAF-glDovTcw5YP4Yah9c_F-OhSrdY_kryo")     # токен твоего бота
CHAT_ID    = os.getenv("323838150")       # ID чата (или группы)
URL        = os.getenv("https://arbit-crxz.onrender.com")               # https://arbit-crxz.onrender.com
INTERVAL   = int(os.getenv("PING_INTERVAL", 60)) # сек; по умолчанию 60
# ───────────────────────────────────────────────────────────

was_down = False          # флаг «вчера лежали ли мы»

def tg(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text}, timeout=5
        )
    except Exception as e:
        print("⚠️ Не смог отправить сообщение:", e)

while True:
    try:
        r = requests.get(URL, timeout=10)
        is_up = r.status_code == 200
    except Exception:
        is_up = False

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {URL} → {'UP' if is_up else 'DOWN'}")

    if is_up and was_down:
        tg("✅ Бот снова в сети.")
        was_down = False
    elif not is_up and not was_down:
        tg("❌ Бот недоступен!")
        was_down = True

    time.sleep(INTERVAL)
