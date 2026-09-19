import requests
from config.settings import TELEGRAM_ENABLED, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from src.universal_tp_ladder import format_tp_plan_from_levels


def send_telegram_message(text: str) -> bool:
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


def notify_trade_execution(signal, price, sl, tp) -> bool:
    message = f"""
📊 Trade Executed
Signal: {signal}
Entry: {price}
SL: {sl}
TP: {tp}
"""
    return send_telegram_message(message)


def build_setup_quality_alert_block(
    data: dict,
    status=None,
) -> str:
    """
    Build an informational premium setup-quality block.

    DISPLAY ONLY:
    - cannot execute
    - cannot block
    - cannot change score
    - cannot change risk
    - cannot change entry / SL / TP
    """

    try:
        from src.setup_quality_grade import (
            build_setup_quality_grade,
            format_setup_quality_block,
        )

        result = build_setup_quality_grade(
            data
        )

        block = format_setup_quality_block(
            result
        )

        if not block:
            return ""

        if status:
            block = block.replace(
                " SETUP\n",
                " SETUP QUALITY\n",
                1,
            )

            block += (
                f"\nStatus: {status}"
            )

        return block

    except Exception:
        # Notification path must remain fail-open.
        return ""


def _build_setup_quality_block(
    data: dict,
    stage,
) -> str:
    if (
        "SETUP DETECTED"
        not in str(stage or "").upper()
    ):
        return ""

    return build_setup_quality_alert_block(
        data
    )


def build_trade_message(data: dict) -> str:
    def has_value(value):
        return value is not None and value != "N/A"

    signal = data.get("signal")
    strategy = data.get("strategy")
    entry_model = data.get("entry_model", "N/A")
    stage = data.get("stage", "SIGNAL DETECTED")

    setup_quality_block = (
        _build_setup_quality_block(
            data,
            stage,
        )
    )

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
        if (
            signal in ["BUY", "SELL"]
            and isinstance(entry, (int, float))
            and isinstance(sl, (int, float))
            and isinstance(tp, (int, float))
        ):
            if signal == "BUY" and (entry - sl) != 0:
                rr = round((tp - entry) / (entry - sl), 2)
            elif signal == "SELL" and (sl - entry) != 0:
                rr = round((entry - tp) / (sl - entry), 2)
    except Exception:
        rr = "N/A"

    message = f"""
📡 {stage}

🔹 Strategy: {strategy}
🔹 Signal: {signal}
🔹 Score: {score}
🔹 Session: {session}
"""

    if has_value(entry_model):
        message += f"🔹 Type: {entry_model}\n"

    if has_value(entry):
        message += f"\n📍 Entry: {entry}"

    if has_value(sl):
        message += f"\n🛑 SL: {sl}"

    if has_value(tp):
        tp_plan_text = format_tp_plan_from_levels(
            signal=signal,
            entry=entry,
            sl=sl,
            tp=tp,
        )

        message += (
            f"\n🎯 {tp_plan_text}"
        )

    if has_value(rr):
        message += (
            f"\n📊 Full RR (TP3): {rr}"
        )

    if pivot_support is not None:
        message += f"\n🟢 Support: {round(pivot_support, 2)}"

    if pivot_resistance is not None:
        message += f"\n🔴 Resistance: {round(pivot_resistance, 2)}"

    if pivot_target is not None:
        message += f"\n🎯 Target Level: {round(pivot_target, 2)}"

    if reason:
        message += f"\n\n🧠 Reason:\n{reason}"

    # Setup Historical Optimizer V1 — display only.
    try:
        from src.setup_historical_optimizer import (
            build_setup_historical_optimizer_block,
        )

        setup_historical_optimizer_block = (
            build_setup_historical_optimizer_block(
                data
            )
        )
    except Exception:
        setup_historical_optimizer_block = ""

    if setup_historical_optimizer_block:
        message = (
            f"{setup_historical_optimizer_block}\n"
            f"{message}"
        )

    if setup_quality_block:
        message = (
            f"{setup_quality_block}\n"
            f"{message}"
        )

    return message