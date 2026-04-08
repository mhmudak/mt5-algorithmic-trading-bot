import requests
from config.settings import TELEGRAM_ENABLED, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID


def send_telegram_message(text: str):
    if not TELEGRAM_ENABLED:
        print("[NOTIFIER] Telegram disabled")
        return False

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[NOTIFIER] Missing Telegram credentials")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": text,
    }

    try:
        response = requests.post(url, json=payload, timeout=5)

        if response.status_code != 200:
            print(f"[NOTIFIER] HTTP Error: {response.status_code} | {response.text}")
            return False

        data = response.json()

        if not data.get("ok"):
            print(f"[NOTIFIER] Telegram API error: {data}")
            return False

        print("[NOTIFIER] Message sent successfully")
        return True

    except requests.exceptions.Timeout:
        print("[NOTIFIER] Timeout error while sending message")
        return False

    except requests.exceptions.RequestException as e:
        print(f"[NOTIFIER] Request error: {e}")
        return False
    
def notify_trade_execution(signal, price, sl, tp):
    message = f"""
📊 *Trade Executed*
Signal: {signal}
Entry: {price}
SL: {sl}
TP: {tp}
"""
    send_telegram_message(message)