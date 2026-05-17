from datetime import datetime, timedelta

from config.settings import (
    ENABLE_PROTECTED_REENTRY,
    PROTECTED_REENTRY_MIN_PROFIT_PRICE,
    PROTECTED_REENTRY_LOOKBACK_MINUTES,
    PROTECTED_REENTRY_SCORE_BOOST,
    PROTECTED_REENTRY_CLOSE_REASONS,
    PROTECTED_REENTRY_STRATEGIES,
)
from src.logger import logger
from src.trade_tracker import load_trades


def _parse_time(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def get_protected_reentry_context():
    if not ENABLE_PROTECTED_REENTRY:
        return {}

    trades = load_trades()
    now = datetime.now()
    cutoff = now - timedelta(minutes=PROTECTED_REENTRY_LOOKBACK_MINUTES)

    context = {}

    for position_id, trade in trades.items():
        if trade.get("status") != "CLOSED":
            continue

        if trade.get("imported_manually", False):
            continue

        strategy = trade.get("strategy")
        signal = trade.get("signal")

        if strategy not in PROTECTED_REENTRY_STRATEGIES:
            continue

        close_reason = trade.get("close_reason")
        if close_reason not in PROTECTED_REENTRY_CLOSE_REASONS:
            continue

        max_profit = float(trade.get("max_profit_price", 0.0) or 0.0)
        if max_profit < PROTECTED_REENTRY_MIN_PROFIT_PRICE:
            continue

        close_time = _parse_time(trade.get("close_time"))
        if close_time is None or close_time < cutoff:
            continue

        key = f"{strategy}:{signal}"

        existing = context.get(key)

        item = {
            "position_id": position_id,
            "strategy": strategy,
            "signal": signal,
            "close_reason": close_reason,
            "max_profit_price": max_profit,
            "close_time": close_time.isoformat(),
            "setup_id": trade.get("setup_id"),
        }

        if existing is None:
            context[key] = item
            continue

        existing_time = _parse_time(existing.get("close_time"))
        if existing_time is None or close_time > existing_time:
            context[key] = item

    if context:
        logger.info(f"[PROTECTED REENTRY] Active contexts={context}")

    return context


def apply_protected_reentry_confirmation(signal_data, context):
    if not ENABLE_PROTECTED_REENTRY:
        return 0, []

    if not signal_data or not context:
        return 0, []

    strategy = signal_data.get("strategy")
    signal = signal_data.get("signal")

    if signal not in ["BUY", "SELL"]:
        return 0, []

    key = f"{strategy}:{signal}"
    match = context.get(key)

    if not match:
        return 0, []

    signal_data["protected_reentry"] = {
        "previous_position_id": match.get("position_id"),
        "previous_setup_id": match.get("setup_id"),
        "previous_close_reason": match.get("close_reason"),
        "previous_max_profit_price": match.get("max_profit_price"),
    }

    return PROTECTED_REENTRY_SCORE_BOOST, [
        "protected_reentry_context",
        f"previous_close={match.get('close_reason')}",
        f"previous_max_profit={match.get('max_profit_price')}",
    ]