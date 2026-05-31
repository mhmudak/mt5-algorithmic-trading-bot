import json
from datetime import datetime, timedelta

import MetaTrader5 as mt5

from config.settings import (
    MAX_SLIPPAGE,
    ENABLE_PENDING_BETTER_ENTRY_AFTER_BLOCK,
    PENDING_BETTER_ENTRY_AFTER_BLOCK_STRATEGIES,
    PENDING_BETTER_ENTRY_MIN_SCORE,
    PENDING_BETTER_ENTRY_MIN_RR,
    PENDING_BETTER_ENTRY_RETRACE_PRICE,
    PENDING_BETTER_ENTRY_EXPIRY_MINUTES,
    PENDING_BETTER_ENTRY_SPLIT_ENABLED,
    PENDING_BETTER_ENTRY_FIRST_SPLIT_PCT,
    PENDING_BETTER_ENTRY_MIN_ORIGINAL_RR,
)
from src.account_context import get_account_file
from src.logger import logger
from src.notifier import send_telegram_message


def get_pending_better_entry_file():
    return get_account_file("pending_better_entries.json")


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


def load_pending_entries():
    file_path = get_pending_better_entry_file()

    if not file_path.exists() or file_path.stat().st_size == 0:
        return {}

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[PENDING BETTER ENTRY] Failed to load file: {e}")
        return {}


def save_pending_entries(entries):
    file_path = get_pending_better_entry_file()
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(_json_safe(entries), f, indent=2, ensure_ascii=False)

        temp_path.replace(file_path)
    except Exception as e:
        logger.error(f"[PENDING BETTER ENTRY] Failed to save file: {e}")


def calculate_rr(signal, entry, sl, tp):
    if signal == "BUY":
        risk = entry - sl
        reward = tp - entry
    elif signal == "SELL":
        risk = sl - entry
        reward = entry - tp
    else:
        return None

    if risk <= 0 or reward <= 0:
        return None

    return round(reward / risk, 2)


def get_current_price(symbol, signal):
    tick = mt5.symbol_info_tick(symbol)

    if tick is None:
        return None

    if signal == "BUY":
        return float(tick.ask)

    if signal == "SELL":
        return float(tick.bid)

    return None


def build_better_entry_target(signal, entry_price, current_price):
    reference_price = current_price if current_price is not None else entry_price

    if signal == "BUY":
        return round(reference_price - PENDING_BETTER_ENTRY_RETRACE_PRICE, 2)

    if signal == "SELL":
        return round(reference_price + PENDING_BETTER_ENTRY_RETRACE_PRICE, 2)

    return None


def is_target_reached(signal, current_price, target_price):
    if signal == "BUY":
        return current_price <= target_price

    if signal == "SELL":
        return current_price >= target_price

    return False


def register_pending_better_entry(
    *,
    symbol,
    signal,
    trade_plan,
    block_reason,
    current_price=None,
):
    if not ENABLE_PENDING_BETTER_ENTRY_AFTER_BLOCK:
        return False

    strategy = str(trade_plan.get("strategy", "UNKNOWN")).upper()
    score = float(trade_plan.get("score", 0) or 0)

    if strategy not in PENDING_BETTER_ENTRY_AFTER_BLOCK_STRATEGIES:
        return False

    if score < PENDING_BETTER_ENTRY_MIN_SCORE:
        return False

    entry_price = float(trade_plan.get("entry_price", 0.0) or 0.0)
    
    original_sl = float(trade_plan.get("stop_loss", 0.0) or 0.0)
    original_tp = float(trade_plan.get("take_profit", 0.0) or 0.0)
    
    original_rr = calculate_rr(
        signal=signal,
        entry=entry_price,
        sl=original_sl,
        tp=original_tp,
    )
    
    if block_reason == "HIGH_SLIPPAGE":
        if original_rr is None or original_rr < PENDING_BETTER_ENTRY_MIN_ORIGINAL_RR:
            logger.info(
                f"[PENDING BETTER ENTRY] Skipped high-slippage setup | "
                f"rr={original_rr} min={PENDING_BETTER_ENTRY_MIN_ORIGINAL_RR}"
            )
            return False

    if entry_price <= 0:
        return False

    target_price = build_better_entry_target(
        signal=signal,
        entry_price=entry_price,
        current_price=current_price,
    )

    if target_price is None:
        return False

    setup_id = str(trade_plan.get("setup_id", f"PENDING-{strategy}-{datetime.now().timestamp()}"))
    pending_id = f"{setup_id}-{block_reason}"

    entries = load_pending_entries()

    if pending_id in entries:
        return False

    expires_at = datetime.now() + timedelta(minutes=PENDING_BETTER_ENTRY_EXPIRY_MINUTES)

    entries[pending_id] = {
        "pending_id": pending_id,
        "setup_id": setup_id,
        "status": "WAITING_BETTER_ENTRY",
        "created_at": datetime.now().isoformat(),
        "expires_at": expires_at.isoformat(),
        "symbol": symbol,
        "signal": signal,
        "strategy": strategy,
        "score": score,
        "block_reason": block_reason,
        "original_entry": round(entry_price, 2),
        "target_entry": target_price,
        "trade_plan": _json_safe(trade_plan),
    }

    save_pending_entries(entries)

    logger.info(
        f"[PENDING BETTER ENTRY] Registered | "
        f"strategy={strategy} signal={signal} target={target_price} reason={block_reason}"
    )

    send_telegram_message(
        f"⏳ Pending Better Entry Registered\n"
        f"Symbol: {symbol}\n"
        f"Signal: {signal}\n"
        f"Strategy: {strategy}\n"
        f"Reason: {block_reason}\n"
        f"Original Entry: {round(entry_price, 2)}\n"
        f"Target Entry: {target_price}\n"
        f"Expiry: {expires_at.strftime('%H:%M:%S')}"
    )

    return True


def build_rebased_pending_plan(pending, current_price):
    trade_plan = pending["trade_plan"].copy()
    signal = pending["signal"]

    old_lot = float(trade_plan.get("lot", 0.0) or 0.0)
    old_sl = float(trade_plan.get("stop_loss", 0.0) or 0.0)
    old_tp = float(trade_plan.get("take_profit", 0.0) or 0.0)

    new_entry = round(float(current_price), 2)

    if old_sl <= 0 or old_tp <= 0:
        return None, "invalid_sl_or_tp"

    # Structure SL stays unchanged.
    # This means better entry improves RR naturally.
    new_sl = old_sl
    new_tp = old_tp

    rr = calculate_rr(
        signal=signal,
        entry=new_entry,
        sl=new_sl,
        tp=new_tp,
    )

    if rr is None or rr < PENDING_BETTER_ENTRY_MIN_RR:
        return None, f"rr_still_too_low {rr}/{PENDING_BETTER_ENTRY_MIN_RR}"

    if PENDING_BETTER_ENTRY_SPLIT_ENABLED:
        first_lot = round(old_lot * PENDING_BETTER_ENTRY_FIRST_SPLIT_PCT, 2)
    else:
        first_lot = old_lot

    if first_lot <= 0:
        return None, "invalid_split_lot"

    trade_plan["entry_price"] = new_entry
    trade_plan["stop_loss"] = round(new_sl, 2)
    trade_plan["take_profit"] = round(new_tp, 2)
    trade_plan["stop_distance"] = round(abs(new_entry - new_sl), 2)
    trade_plan["lot"] = first_lot
    trade_plan["rr"] = rr
    trade_plan["pending_better_entry_id"] = pending["pending_id"]
    trade_plan["is_pending_better_entry"] = True
    trade_plan["pending_original_lot"] = old_lot
    trade_plan["pending_first_split_lot"] = first_lot
    trade_plan["pending_remaining_lot"] = round(old_lot - first_lot, 2)

    trade_plan["reason"] = (
        f"{trade_plan.get('reason', '')} | "
        f"PENDING_BETTER_ENTRY_AFTER_{pending.get('block_reason')} "
        f"target={pending.get('target_entry')} rr={rr}"
    )

    return trade_plan, "ready"


def get_ready_pending_better_entries(symbol):
    entries = load_pending_entries()
    ready = []
    changed = False

    now = datetime.now()

    for pending_id, pending in list(entries.items()):
        if pending.get("symbol") != symbol:
            continue

        if pending.get("status") != "WAITING_BETTER_ENTRY":
            continue

        try:
            expires_at = datetime.fromisoformat(pending["expires_at"])
        except Exception:
            pending["status"] = "EXPIRED"
            changed = True
            continue

        if now > expires_at:
            pending["status"] = "EXPIRED"
            changed = True
            continue

        signal = pending.get("signal")
        current_price = get_current_price(symbol, signal)

        if current_price is None:
            continue

        target_price = float(pending.get("target_entry", 0.0) or 0.0)

        if not is_target_reached(signal, current_price, target_price):
            continue

        trade_plan, reason = build_rebased_pending_plan(
            pending=pending,
            current_price=current_price,
        )

        if trade_plan is None:
            logger.info(
                f"[PENDING BETTER ENTRY] Not ready | id={pending_id} reason={reason}"
            )
            continue

        pending["status"] = "READY_TO_EXECUTE_FIRST_SPLIT"
        pending["ready_at"] = now.isoformat()
        pending["ready_price"] = round(current_price, 2)
        changed = True

        ready.append(
            {
                "pending_id": pending_id,
                "trade_plan": trade_plan,
                "signal": signal,
                "symbol": symbol,
            }
        )

    if changed:
        save_pending_entries(entries)

    return ready


def mark_pending_first_split_executed(pending_id):
    entries = load_pending_entries()

    if pending_id not in entries:
        return

    entries[pending_id]["status"] = "FIRST_SPLIT_EXECUTED"
    entries[pending_id]["first_split_executed_at"] = datetime.now().isoformat()

    save_pending_entries(entries)