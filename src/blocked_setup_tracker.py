import json
from datetime import datetime, timedelta

from src.account_context import get_account_file
from src.logger import logger


ENABLE_BLOCKED_SETUP_OUTCOME_TRACKING = True
BLOCKED_SETUP_OUTCOME_HORIZON_MINUTES = 180
BLOCKED_SETUP_OUTCOME_SNAPSHOT_MINUTES = [60, 120, 180]


def get_blocked_setup_file():
    return get_account_file("blocked_setups.json")


def load_blocked_setups():
    file_path = get_blocked_setup_file()

    if not file_path.exists():
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[BLOCKED OUTCOME] Failed to load blocked setups: {e}")
        return {}


def save_blocked_setups(data):
    file_path = get_blocked_setup_file()

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[BLOCKED OUTCOME] Failed to save blocked setups: {e}")


def _safe_float(value):
    try:
        if value is None:
            return None

        return float(value)
    except Exception:
        return None


def _get_price_fields(setup_data, trade_plan=None, tick=None):
    trade_plan = trade_plan or {}

    signal = setup_data.get("signal")
    entry = _safe_float(
        trade_plan.get("entry_price")
        or setup_data.get("entry_price")
        or setup_data.get("entry")
    )

    sl = _safe_float(
        trade_plan.get("stop_loss")
        or setup_data.get("stop_loss")
        or setup_data.get("sl_reference")
    )

    tp = _safe_float(
        trade_plan.get("take_profit")
        or setup_data.get("take_profit")
        or setup_data.get("tp_reference")
    )

    if entry is None and tick is not None:
        if signal == "BUY":
            entry = _safe_float(tick.ask)
        elif signal == "SELL":
            entry = _safe_float(tick.bid)

    return entry, sl, tp


def register_blocked_setup(setup_data, reason, event_name, trade_plan=None, tick=None):
    if not ENABLE_BLOCKED_SETUP_OUTCOME_TRACKING:
        return

    if not setup_data:
        return

    signal = setup_data.get("signal")
    strategy = setup_data.get("strategy", "UNKNOWN")

    if signal not in ["BUY", "SELL"]:
        return

    entry, sl, tp = _get_price_fields(setup_data, trade_plan=trade_plan, tick=tick)

    if entry is None or sl is None or tp is None:
        logger.info(
            f"[BLOCKED OUTCOME] Skipped tracking | "
            f"strategy={strategy} signal={signal} reason=missing_entry_sl_tp"
        )
        return

    setup_id = setup_data.get("setup_id") or f"{strategy}-{signal}-{int(datetime.now().timestamp())}"
    record_id = f"{setup_id}:{event_name}:{reason}"

    data = load_blocked_setups()

    if record_id in data:
        return

    data[record_id] = {
        "record_id": record_id,
        "setup_id": setup_id,
        "strategy": strategy,
        "signal": signal,
        "event_name": event_name,
        "blocked_reason": str(reason),
        "entry_price": round(entry, 2),
        "stop_loss": round(sl, 2),
        "take_profit": round(tp, 2),
        "blocked_at": datetime.now().isoformat(),
        "status": "TRACKING",
        "outcome": None,
        "hit_at": None,
        "hit_price": None,
        "max_favorable_move": 0.0,
        "max_adverse_move": 0.0,
        "snapshots": {},
    }

    save_blocked_setups(data)

    logger.info(
        f"[BLOCKED OUTCOME] Tracking blocked setup | "
        f"strategy={strategy} signal={signal} event={event_name} reason={reason}"
    )


def _current_close_price(record, tick):
    if record["signal"] == "BUY":
        return _safe_float(tick.bid)

    if record["signal"] == "SELL":
        return _safe_float(tick.ask)

    return None


def _calculate_moves(record, current_price):
    entry = float(record["entry_price"])

    if record["signal"] == "BUY":
        favorable = current_price - entry
        adverse = entry - current_price
    else:
        favorable = entry - current_price
        adverse = current_price - entry

    return round(favorable, 2), round(adverse, 2)


def _tp_hit(record, current_price):
    tp = float(record["take_profit"])

    if record["signal"] == "BUY":
        return current_price >= tp

    return current_price <= tp


def _sl_hit(record, current_price):
    sl = float(record["stop_loss"])

    if record["signal"] == "BUY":
        return current_price <= sl

    return current_price >= sl


def update_blocked_setup_outcomes(symbol, tick):
    if not ENABLE_BLOCKED_SETUP_OUTCOME_TRACKING:
        return

    if tick is None:
        return

    data = load_blocked_setups()

    if not data:
        return

    changed = False
    now = datetime.now()

    for record_id, record in data.items():
        if record.get("status") != "TRACKING":
            continue

        current_price = _current_close_price(record, tick)

        if current_price is None:
            continue

        favorable, adverse = _calculate_moves(record, current_price)

        record["max_favorable_move"] = round(
            max(float(record.get("max_favorable_move", 0.0)), favorable),
            2,
        )

        record["max_adverse_move"] = round(
            max(float(record.get("max_adverse_move", 0.0)), adverse),
            2,
        )

        blocked_at = datetime.fromisoformat(record["blocked_at"])
        elapsed_minutes = int((now - blocked_at).total_seconds() / 60)

        snapshots = record.get("snapshots", {})

        for snapshot_minute in BLOCKED_SETUP_OUTCOME_SNAPSHOT_MINUTES:
            key = f"{snapshot_minute}m"

            if elapsed_minutes >= snapshot_minute and key not in snapshots:
                snapshots[key] = {
                    "price": round(current_price, 2),
                    "max_favorable_move": record["max_favorable_move"],
                    "max_adverse_move": record["max_adverse_move"],
                }
                changed = True

        record["snapshots"] = snapshots

        if _tp_hit(record, current_price):
            record["status"] = "FINISHED"
            record["outcome"] = "WOULD_HAVE_HIT_TP"
            record["hit_at"] = now.isoformat()
            record["hit_price"] = round(current_price, 2)
            changed = True

            logger.info(
                f"[BLOCKED OUTCOME] Blocked setup would have hit TP | "
                f"strategy={record.get('strategy')} signal={record.get('signal')} "
                f"reason={record.get('blocked_reason')}"
            )
            continue

        if _sl_hit(record, current_price):
            record["status"] = "FINISHED"
            record["outcome"] = "BLOCK_SAVED_SL"
            record["hit_at"] = now.isoformat()
            record["hit_price"] = round(current_price, 2)
            changed = True

            logger.info(
                f"[BLOCKED OUTCOME] Block saved SL | "
                f"strategy={record.get('strategy')} signal={record.get('signal')} "
                f"reason={record.get('blocked_reason')}"
            )
            continue

        if elapsed_minutes >= BLOCKED_SETUP_OUTCOME_HORIZON_MINUTES:
            record["status"] = "FINISHED"
            record["outcome"] = "EXPIRED_NO_TP_OR_SL"
            record["hit_at"] = now.isoformat()
            record["hit_price"] = round(current_price, 2)
            changed = True

    if changed:
        save_blocked_setups(data)