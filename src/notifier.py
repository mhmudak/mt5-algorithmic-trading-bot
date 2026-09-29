import requests
from config.settings import TELEGRAM_ENABLED, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from src.universal_tp_ladder import format_tp_plan_from_levels


def _should_suppress_micro_momentum_routine(text: str) -> bool:
    try:
        from config import settings as runtime_settings

        enabled = bool(
            getattr(
                runtime_settings,
                "MICRO_MOMENTUM_TELEGRAM_ROUTINE_NOTIFICATIONS",
                True,
            )
        )
    except Exception:
        enabled = True

    if enabled:
        return False

    message = str(text or "")
    upper = message.upper()

    is_micro = (
        "INTRABAR_MICRO_MOMENTUM" in upper
        or "MICRO MOMENTUM" in upper
    )
    if not is_micro:
        return False

    routine_markers = (
        "SIGNAL DETECTED",
        "SETUP DETECTED",
        "TRADE EXECUTED",
        "LIVE EXECUTE",
        "EXECUTED",
    )

    return any(marker in upper for marker in routine_markers)


def _strategy_for_position_id(position_id):
    try:
        import json
        from src.account_context import get_account_file

        path = get_account_file("trades.json")
        if not path.exists():
            return None

        payload = json.loads(
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )

        if not isinstance(payload, dict):
            return None

        trade = payload.get(str(position_id))
        if not isinstance(trade, dict):
            return None

        return str(trade.get("strategy") or "").upper() or None
    except Exception:
        return None


def _suppress_micro_momentum_routine_telegram(text):
    try:
        from config import settings as runtime_settings

        routine_enabled = bool(
            getattr(
                runtime_settings,
                "MICRO_MOMENTUM_TELEGRAM_ROUTINE_NOTIFICATIONS",
                True,
            )
        )
    except Exception:
        return False

    if routine_enabled:
        return False

    normalized = str(text or "").upper()

    if "LOW-MAE MOMENTUM RUNNER PROMOTED" in normalized:
        return True

    routine_position_markers = (
        "MAIN TP1 REACHED",
        "MAIN TP2 REACHED",
        "MAIN TP3 REACHED",
        "MAIN TRADE STAGE 1",
        "MAIN TRADE STAGE 2",
        "MAIN TRADE STAGE 3",
        "MAIN RUNNER MODE ACTIVATED",
        "PARTIAL CLOSE",
    )

    if not any(marker in normalized for marker in routine_position_markers):
        return False

    import re

    match = re.search(
        r"(?im)^\s*Position:\s*(\d+)\s*$",
        str(text or ""),
    )
    if not match:
        return False

    strategy = _strategy_for_position_id(match.group(1))
    return strategy == "INTRABAR_MICRO_MOMENTUM"




def _suppress_all_micro_momentum_telegram(text):
    try:
        from config import settings as runtime_settings
        enabled = bool(
            getattr(
                runtime_settings,
                "MICRO_MOMENTUM_TELEGRAM_ENABLED",
                False,
            )
        )
    except Exception:
        enabled = False

    if enabled:
        return False

    import re

    normalized = str(text or "").upper()

    direct_markers = (
        "INTRABAR_MICRO_MOMENTUM",
        "MICRO MOMENTUM",
        "MICRO-MOMENTUM",
        "LOW-MAE MOMENTUM RUNNER",
        "LOW MAE MOMENTUM RUNNER",
    )

    if any(marker in normalized for marker in direct_markers):
        return True

    if re.search(
        r"(?<![A-Z0-9])#?IMM-(?:BUY|SELL)-[A-Z0-9._:-]+",
        normalized,
    ):
        return True

    return False


def send_telegram_message(text: str) -> bool:
    if _suppress_all_micro_momentum_telegram(text):
        print("[NOTIFIER] Micro Momentum Telegram suppressed")
        return True

    if _suppress_micro_momentum_routine_telegram(text):
        print("[NOTIFIER] Routine Micro Momentum Telegram suppressed")
        return True

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
# ============================================================
# Setup-selection statistical advisory integration
# DISPLAY ONLY / FAIL OPEN / NO EXECUTION AUTHORITY
# ============================================================

def build_setup_selection_advisory_block(
    data: dict,
    *,
    account_name=None,
) -> str:
    """
    Build the historical setup-selection badge shown in setup notifications.

    DISPLAY ONLY:
    - never blocks or permits execution
    - never changes score, RR, risk, SL, TP, lot, or order parameters
    - fails open to an empty string if research artifacts are unavailable
    """
    try:
        from src.setup_selection_advisory import (
            format_setup_selection_advisory,
            resolve_setup_selection_advisory,
        )

        payload = data if isinstance(data, dict) else {}

        advisory = resolve_setup_selection_advisory(
            strategy=payload.get("strategy"),
            direction=payload.get("direction") or payload.get("signal"),
            entry_model=payload.get("entry_model"),
            session=payload.get("session") or payload.get("session_name"),
            market_condition=payload.get("market_condition"),
            stage=payload.get("stage"),
            account_name=account_name,
        )

        if not advisory:
            return ""

        # Production display rule:
        # A strategy with no historical selection evidence should not add a
        # noisy NO_DATA / N/A block to Telegram. Keep NO_DATA available
        # internally via the resolver for diagnostics, but suppress it here.
        if str(advisory.get("badge") or "").upper() == "NO_DATA":
            return ""

        # Safety invariant: this integration is informational only.
        advisory["live_authority"] = False
        advisory["decision_impact"] = "NONE"

        return format_setup_selection_advisory(advisory)

    except Exception:
        # Notification enrichment must never affect the trading loop.
        return ""


def _append_setup_selection_advisory(message, data, *, account_name=None):
    base = str(message or "").rstrip()
    if "[SETUP SELECTION]" in base:
        return base

    block = build_setup_selection_advisory_block(
        data,
        account_name=account_name,
    )
    if not block:
        return base

    return f"{base}\n\n{block}" if base else block


# Preserve the pre-existing formatters and enrich their output only.
_PRE_SETUP_SELECTION_BUILD_TRADE_MESSAGE = build_trade_message
_PRE_SETUP_SELECTION_BUILD_SETUP_QUALITY_ALERT_BLOCK = build_setup_quality_alert_block


def build_trade_message(data: dict) -> str:
    message = _PRE_SETUP_SELECTION_BUILD_TRADE_MESSAGE(data)
    return _append_setup_selection_advisory(message, data)


def build_setup_quality_alert_block(
    data: dict,
    status=None,
) -> str:
    message = _PRE_SETUP_SELECTION_BUILD_SETUP_QUALITY_ALERT_BLOCK(
        data,
        status=status,
    )

    payload = dict(data or {})
    if status is not None and not payload.get("stage"):
        payload["stage"] = status

    return _append_setup_selection_advisory(message, payload)
