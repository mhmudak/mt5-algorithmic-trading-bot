import json
from datetime import datetime, timedelta

import MetaTrader5 as mt5

from config.settings import (
    ENABLE_MTF_CONFLICT_OPPORTUNITY_TRACKER,
    MTF_CONFLICT_OPPORTUNITY_EXPIRY_MINUTES,
)
from src.account_context import get_account_file
from src.logger import logger


def get_mtf_conflict_opportunity_file():
    return get_account_file("mtf_conflict_opportunities.json")


def _json_safe(value):
    try:
        if hasattr(value, "item"):
            return value.item()
    except Exception:
        pass

    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_json_safe(v) for v in value]

    return value


def load_mtf_conflict_opportunities():
    file_path = get_mtf_conflict_opportunity_file()

    if not file_path.exists() or file_path.stat().st_size == 0:
        return {}

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[MTF CONFLICT TRACKER] Failed to load file: {e}")
        return {}


def save_mtf_conflict_opportunities(entries):
    file_path = get_mtf_conflict_opportunity_file()
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(_json_safe(entries), f, indent=2, ensure_ascii=False)

        temp_path.replace(file_path)
    except Exception as e:
        logger.error(f"[MTF CONFLICT TRACKER] Failed to save file: {e}")


def get_current_tracking_price(symbol, signal):
    tick = mt5.symbol_info_tick(symbol)

    if tick is None:
        return None

    if signal == "BUY":
        return float(tick.ask)

    if signal == "SELL":
        return float(tick.bid)

    return None


def calculate_tracking_moves(signal, start_price, current_price):
    if signal == "BUY":
        favorable = current_price - start_price
        adverse = start_price - current_price

    elif signal == "SELL":
        favorable = start_price - current_price
        adverse = current_price - start_price

    else:
        return 0.0, 0.0

    return round(max(favorable, 0.0), 2), round(max(adverse, 0.0), 2)


def register_mtf_conflict_opportunity(
    *,
    symbol,
    setup_id,
    strategy,
    signal,
    entry_model,
    score,
    session,
    market_condition,
    mtf_bias,
    rejection_reason,
    price_at_rejection,
    shadow_trade_plan=None,
    shadow_rr=None,
    shadow_required_rr=None,
    execution_mode="TRACK_ONLY",
    execution_allowed=False,
    execution_reason=None,
):
    if not ENABLE_MTF_CONFLICT_OPPORTUNITY_TRACKER:
        return False

    if not setup_id:
        return False

    entries = load_mtf_conflict_opportunities()

    if setup_id in entries and entries[setup_id].get("status") == "TRACKING":
        return False

    expires_at = datetime.now() + timedelta(
        minutes=MTF_CONFLICT_OPPORTUNITY_EXPIRY_MINUTES
    )

    entries[setup_id] = {
        "setup_id": setup_id,
        "status": "TRACKING",
        "created_at": datetime.now().isoformat(),
        "expires_at": expires_at.isoformat(),
        "symbol": symbol,
        "strategy": strategy,
        "signal": signal,
        "entry_model": entry_model,
        "score": score,
        "session": session,
        "market_condition": market_condition,
        "mtf_bias": mtf_bias,
        "rejection_reason": rejection_reason,
        "price_at_rejection": round(float(price_at_rejection), 2)
        if price_at_rejection is not None
        else None,
        "shadow_entry": shadow_trade_plan.get("entry_price")
        if shadow_trade_plan
        else None,
        "shadow_sl": shadow_trade_plan.get("stop_loss")
        if shadow_trade_plan
        else None,
        "shadow_tp": shadow_trade_plan.get("take_profit")
        if shadow_trade_plan
        else None,
        "shadow_rr": shadow_rr,
        "shadow_required_rr": shadow_required_rr,
        "execution_mode": execution_mode,
        "execution_allowed": execution_allowed,
        "execution_reason": execution_reason,
        "max_favorable_move": 0.0,
        "max_adverse_move": 0.0,
    }

    save_mtf_conflict_opportunities(entries)

    logger.info(
        f"[MTF CONFLICT TRACKER] Registered | "
        f"setup_id={setup_id} strategy={strategy} signal={signal} "
        f"mtf_bias={mtf_bias} mode={execution_mode} allowed={execution_allowed}"
    )

    return True


def mark_mtf_conflict_opportunity_executed(setup_id, executed_setup_id=None, execution_mode=None):
    entries = load_mtf_conflict_opportunities()

    if setup_id not in entries:
        return

    entries[setup_id]["status"] = "EXECUTED"
    entries[setup_id]["executed_at"] = datetime.now().isoformat()
    entries[setup_id]["executed_setup_id"] = executed_setup_id

    if execution_mode:
        entries[setup_id]["execution_mode"] = execution_mode

    save_mtf_conflict_opportunities(entries)


def mark_mtf_conflict_opportunity_failed(setup_id, reason):
    entries = load_mtf_conflict_opportunities()

    if setup_id not in entries:
        return

    entries[setup_id]["status"] = "TRACKING_EXECUTION_FAILED"
    entries[setup_id]["failed_at"] = datetime.now().isoformat()
    entries[setup_id]["failure_reason"] = reason

    save_mtf_conflict_opportunities(entries)


def update_mtf_conflict_opportunities(symbol):
    if not ENABLE_MTF_CONFLICT_OPPORTUNITY_TRACKER:
        return

    entries = load_mtf_conflict_opportunities()

    if not entries:
        return

    now = datetime.now()
    changed = False

    for setup_id, item in entries.items():
        if item.get("symbol") != symbol:
            continue

        if item.get("status") not in ["TRACKING", "TRACKING_EXECUTION_FAILED"]:
            continue

        try:
            expires_at = datetime.fromisoformat(item["expires_at"])
        except Exception:
            item["status"] = "COMPLETED"
            item["completed_at"] = now.isoformat()
            item["opportunity_result"] = "invalid_expiry"
            changed = True
            continue

        if now > expires_at:
            item["status"] = "COMPLETED"
            item["completed_at"] = now.isoformat()
            item["opportunity_result"] = "tracking_expired"
            changed = True
            continue

        signal = item.get("signal")
        start_price = item.get("price_at_rejection")
        current_price = get_current_tracking_price(symbol, signal)

        if start_price is None or current_price is None:
            continue

        favorable, adverse = calculate_tracking_moves(
            signal,
            float(start_price),
            float(current_price),
        )

        if favorable > float(item.get("max_favorable_move", 0.0) or 0.0):
            item["max_favorable_move"] = favorable
            changed = True

        if adverse > float(item.get("max_adverse_move", 0.0) or 0.0):
            item["max_adverse_move"] = adverse
            changed = True

    if changed:
        save_mtf_conflict_opportunities(entries)