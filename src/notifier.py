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
    
    

def build_trade_message(data):
    signal = data.get("signal")
    strategy = data.get("strategy")
    entry_model = data.get("entry_model", "N/A")

    entry = data.get("entry")
    sl = data.get("sl")
    tp = data.get("tp")

    score = data.get("score", 0)
    session = data.get("session", "N/A")

    pivot_support = data.get("pivot_support_level")
    pivot_resistance = data.get("pivot_resistance_level")
    pivot_target = data.get("pivot_target_level")

    reason = data.get("reason", "")

    rr = "N/A"
    try:
        if signal == "BUY":
            rr_val = (tp - entry) / (entry - sl)
        else:
            rr_val = (entry - tp) / (sl - entry)
        rr = round(rr_val, 2)
    except:
        pass

    message = f"""
📡 SIGNAL DETECTED

🔹 Strategy: {strategy}
🔹 Type: {entry_model}
🔹 Signal: {signal}
🔹 Score: {score}
🔹 Session: {session}

📍 Entry: {entry}
🛑 SL: {sl}
🎯 TP: {tp}
📊 RR: {rr}

"""

    if pivot_support:
        message += f"🟢 Support: {round(pivot_support,2)}\n"
    if pivot_resistance:
        message += f"🔴 Resistance: {round(pivot_resistance,2)}\n"
    if pivot_target:
        message += f"🎯 Target Level: {round(pivot_target,2)}\n"

    message += f"\n🧠 Reason:\n{reason}"

    return message