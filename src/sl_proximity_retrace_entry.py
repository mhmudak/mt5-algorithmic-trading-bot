import json
from datetime import datetime, timedelta

import MetaTrader5 as mt5
import pandas as pd

from config.settings import (
    ENABLE_SL_PROXIMITY_RETRACE_ENTRY,
    SL_PROXIMITY_RETRACE_STRATEGY_MAP,
    SL_PROXIMITY_RETRACE_EXPIRY_MINUTES,
    SL_PROXIMITY_RETRACE_CONFIRMATION_TIMEFRAME,
    SL_PROXIMITY_RETRACE_BARS,
    SL_PROXIMITY_RETRACE_MIN_BODY_ATR,
    SL_PROXIMITY_RETRACE_REQUIRE_EMA_ALIGNMENT,
)
from src.account_context import get_account_file
from src.logger import logger
from src.market_price import get_current_execution_price
from src.notifier import send_telegram_message


def get_sl_proximity_file():
    return get_account_file("pending_sl_proximity_retrace_entries.json")


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


def load_sl_proximity_entries():
    file_path = get_sl_proximity_file()

    if not file_path.exists() or file_path.stat().st_size == 0:
        return {}

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[SL PROXIMITY] Failed to load file: {e}")
        return {}


def save_sl_proximity_entries(entries):
    file_path = get_sl_proximity_file()
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(_json_safe(entries), f, indent=2, ensure_ascii=False)

        temp_path.replace(file_path)
    except Exception as e:
        logger.error(f"[SL PROXIMITY] Failed to save file: {e}")


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


def build_target_entry(signal, original_sl, distance_before_sl):
    if signal == "BUY":
        return round(original_sl + distance_before_sl, 2)

    if signal == "SELL":
        return round(original_sl - distance_before_sl, 2)

    return None


def target_reached(signal, current_price, target_entry):
    if signal == "BUY":
        return current_price <= target_entry

    if signal == "SELL":
        return current_price >= target_entry

    return False


def original_sl_crossed(signal, current_price, original_sl):
    if signal == "BUY":
        return current_price <= original_sl

    if signal == "SELL":
        return current_price >= original_sl

    return True


def build_rebased_plan(pending, current_price):
    trade_plan = pending["trade_plan"].copy()
    signal = pending["signal"]

    original_sl = float(pending["original_sl"])
    original_tp = float(pending["original_tp"])
    original_stop_distance = float(pending["original_stop_distance"])
    min_rebuilt_rr = float(pending["min_rebuilt_rr"])

    new_entry = round(float(current_price), 2)

    if original_sl_crossed(signal, new_entry, original_sl):
        return None, "original_sl_crossed"

    if signal == "BUY":
        new_sl = round(new_entry - original_stop_distance, 2)
    elif signal == "SELL":
        new_sl = round(new_entry + original_stop_distance, 2)
    else:
        return None, "invalid_signal"

    rr = calculate_rr(
        signal=signal,
        entry=new_entry,
        sl=new_sl,
        tp=original_tp,
    )

    if rr is None or rr < min_rebuilt_rr:
        return None, f"rebuilt_rr_too_low {rr}/{min_rebuilt_rr}"

    trade_plan["entry_price"] = new_entry
    trade_plan["stop_loss"] = new_sl
    trade_plan["take_profit"] = round(original_tp, 2)
    trade_plan["stop_distance"] = round(abs(new_entry - new_sl), 2)
    trade_plan["rr"] = rr
    trade_plan["is_sl_proximity_retrace_entry"] = True
    trade_plan["sl_proximity_pending_id"] = pending["pending_id"]

    trade_plan["reason"] = (
        f"{trade_plan.get('reason', '')} | "
        f"SL_PROXIMITY_RETRACE_ENTRY target={pending['target_entry']} rr={rr}"
    )

    return trade_plan, "ready"


def build_m5_dataframe(symbol):
    rates = mt5.copy_rates_from_pos(
        symbol,
        SL_PROXIMITY_RETRACE_CONFIRMATION_TIMEFRAME,
        0,
        SL_PROXIMITY_RETRACE_BARS,
    )

    if rates is None or len(rates) < 25:
        return None

    df = pd.DataFrame(rates)
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()

    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr_14"] = true_range.rolling(14).mean()

    return df


def m5_confirmation_ok(symbol, signal):
    df = build_m5_dataframe(symbol)

    if df is None or len(df) < 25:
        return False, "not_enough_m5_data"

    candle = df.iloc[-2]

    atr = float(candle.get("atr_14", 0.0) or 0.0)
    ema = float(candle.get("ema_20", 0.0) or 0.0)
    open_price = float(candle["open"])
    close_price = float(candle["close"])
    body = abs(close_price - open_price)

    if atr <= 0:
        return False, "invalid_m5_atr"

    if body < atr * SL_PROXIMITY_RETRACE_MIN_BODY_ATR:
        return False, "m5_body_too_small"

    if signal == "BUY":
        if close_price <= open_price:
            return False, "m5_not_bullish"

        if SL_PROXIMITY_RETRACE_REQUIRE_EMA_ALIGNMENT and close_price < ema:
            return False, "m5_buy_below_ema"

        return True, "m5_bullish_confirmation"

    if signal == "SELL":
        if close_price >= open_price:
            return False, "m5_not_bearish"

        if SL_PROXIMITY_RETRACE_REQUIRE_EMA_ALIGNMENT and close_price > ema:
            return False, "m5_sell_above_ema"

        return True, "m5_bearish_confirmation"

    return False, "invalid_signal"


def register_sl_proximity_retrace_entry(
    *,
    symbol,
    signal,
    trade_plan,
):
    if not ENABLE_SL_PROXIMITY_RETRACE_ENTRY:
        return False

    strategy = str(trade_plan.get("strategy", "UNKNOWN")).upper()

    if strategy not in SL_PROXIMITY_RETRACE_STRATEGY_MAP:
        return False

    config = SL_PROXIMITY_RETRACE_STRATEGY_MAP[strategy]

    distance_before_sl = float(config.get("distance_before_sl", 1.0))
    min_rebuilt_rr = float(config.get("min_rebuilt_rr", 1.2))

    original_entry = float(trade_plan.get("entry_price", 0.0) or 0.0)
    original_sl = float(trade_plan.get("stop_loss", 0.0) or 0.0)
    original_tp = float(trade_plan.get("take_profit", 0.0) or 0.0)

    if original_entry <= 0 or original_sl <= 0 or original_tp <= 0:
        return False

    original_stop_distance = abs(original_entry - original_sl)

    if original_stop_distance <= 0:
        return False

    target_entry = build_target_entry(
        signal=signal,
        original_sl=original_sl,
        distance_before_sl=distance_before_sl,
    )

    if target_entry is None:
        return False

    setup_id = str(
        trade_plan.get(
            "setup_id",
            f"SLPROX-{strategy}-{datetime.now().timestamp()}",
        )
    )

    pending_id = f"{setup_id}-SL-PROXIMITY"

    entries = load_sl_proximity_entries()

    if pending_id in entries:
        return False

    expires_at = datetime.now() + timedelta(
        minutes=SL_PROXIMITY_RETRACE_EXPIRY_MINUTES
    )

    entries[pending_id] = {
        "pending_id": pending_id,
        "setup_id": setup_id,
        "status": "WAITING_SL_PROXIMITY_RETRACE",
        "created_at": datetime.now().isoformat(),
        "expires_at": expires_at.isoformat(),
        "symbol": symbol,
        "signal": signal,
        "strategy": strategy,
        "original_entry": round(original_entry, 2),
        "original_sl": round(original_sl, 2),
        "original_tp": round(original_tp, 2),
        "original_stop_distance": round(original_stop_distance, 2),
        "target_entry": target_entry,
        "distance_before_sl": distance_before_sl,
        "min_rebuilt_rr": min_rebuilt_rr,
        "trade_plan": _json_safe(trade_plan),
    }

    save_sl_proximity_entries(entries)

    logger.info(
        f"[SL PROXIMITY] Registered | "
        f"strategy={strategy} signal={signal} target={target_entry}"
    )

    send_telegram_message(
        f"⏳ SL Proximity Retrace Pending\n"
        f"Symbol: {symbol}\n"
        f"Strategy: {strategy}\n"
        f"Signal: {signal}\n"
        f"Original Entry: {round(original_entry, 2)}\n"
        f"Original SL: {round(original_sl, 2)}\n"
        f"Target Entry: {target_entry}\n"
        f"Expiry: {expires_at.strftime('%H:%M:%S')}"
    )

    return True


def get_ready_sl_proximity_retrace_entries(symbol):
    entries = load_sl_proximity_entries()
    ready = []
    changed = False
    now = datetime.now()

    for pending_id, pending in list(entries.items()):
        if pending.get("symbol") != symbol:
            continue

        if pending.get("status") != "WAITING_SL_PROXIMITY_RETRACE":
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
        current_price = get_current_execution_price(symbol, signal)

        if current_price is None:
            continue

        current_price = round(float(current_price), 2)
        target_entry = float(pending.get("target_entry", 0.0) or 0.0)
        original_sl = float(pending.get("original_sl", 0.0) or 0.0)

        if original_sl_crossed(signal, current_price, original_sl):
            pending["status"] = "INVALIDATED_ORIGINAL_SL_CROSSED"
            changed = True
            continue

        if not target_reached(signal, current_price, target_entry):
            continue

        confirmed, confirmation_reason = m5_confirmation_ok(symbol, signal)

        if not confirmed:
            logger.info(
                f"[SL PROXIMITY] Target reached but M5 not confirmed | "
                f"id={pending_id} reason={confirmation_reason}"
            )
            continue

        trade_plan, rebase_reason = build_rebased_plan(
            pending=pending,
            current_price=current_price,
        )

        if trade_plan is None:
            logger.info(
                f"[SL PROXIMITY] Rebuild refused | "
                f"id={pending_id} reason={rebase_reason}"
            )
            continue

        pending["status"] = "READY_TO_EXECUTE"
        pending["ready_at"] = now.isoformat()
        pending["ready_price"] = current_price
        pending["confirmation_reason"] = confirmation_reason
        changed = True

        ready.append(
            {
                "pending_id": pending_id,
                "symbol": symbol,
                "signal": signal,
                "trade_plan": trade_plan,
            }
        )

    if changed:
        save_sl_proximity_entries(entries)

    return ready


def mark_sl_proximity_retrace_executed(pending_id):
    entries = load_sl_proximity_entries()

    if pending_id not in entries:
        return

    entries[pending_id]["status"] = "EXECUTED"
    entries[pending_id]["executed_at"] = datetime.now().isoformat()

    save_sl_proximity_entries(entries)