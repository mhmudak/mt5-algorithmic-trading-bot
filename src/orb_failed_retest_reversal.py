import json
from datetime import datetime, timedelta

import MetaTrader5 as mt5
import pandas as pd

from config.settings import (
    ENABLE_ORB_FAILED_RETEST_OPPOSITE_SCALP,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_STRATEGIES,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_EXPIRY_MINUTES,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_MIN_SCORE,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_ZONE_WIDTH_PRICE,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_TRIGGER_BUFFER_PRICE,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_FIXED_SL_PRICE,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_FIXED_TP_PRICE,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_LOT_MULTIPLIER,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_PROTECT_AFTER_PROFIT_PRICE,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_PROTECT_SL_TO_ENTRY,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_REQUIRE_M5_CONFIRMATION,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_CONFIRMATION_TIMEFRAME,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_CONFIRMATION_BARS,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_MIN_BODY_ATR,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_REQUIRE_EMA_ALIGNMENT,
    ORB_FAILED_RETEST_OPPOSITE_SCALP_SMC_MOVE_PRICE,
)
from src.account_context import get_account_file
from src.logger import logger
from src.market_price import get_current_execution_price
from src.notifier import send_telegram_message


COMMENT = "OrbOppScalp"


def get_pending_file():
    return get_account_file("pending_orb_failed_retest_opposite_scalps.json")


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


def load_pending_scalps():
    file_path = get_pending_file()

    if not file_path.exists() or file_path.stat().st_size == 0:
        return {}

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[ORB OPP SCALP] Failed to load file: {e}")
        return {}


def save_pending_scalps(entries):
    file_path = get_pending_file()
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(_json_safe(entries), f, indent=2, ensure_ascii=False)

        temp_path.replace(file_path)
    except Exception as e:
        logger.error(f"[ORB OPP SCALP] Failed to save file: {e}")


def opposite_signal(signal):
    if signal == "BUY":
        return "SELL"

    if signal == "SELL":
        return "BUY"

    return None


def build_trigger_price(signal, trade_plan, signal_data, source_reason):
    source = str(source_reason or "").upper()

    original_entry = float(trade_plan.get("entry_price", 0.0) or 0.0)

    # =========================
    # SMC FAILED
    # Wait for price to move WITH the original setup direction by 3 USD.
    #
    # Original SELL → price moves down → opposite BUY scalp.
    # Original BUY  → price moves up   → opposite SELL scalp.
    # =========================
    if "SMC_FAILED" in source:
        if original_entry <= 0:
            return None, None

        if signal == "SELL":
            return (
                round(
                    original_entry - ORB_FAILED_RETEST_OPPOSITE_SCALP_SMC_MOVE_PRICE,
                    2,
                ),
                "SAME_DIRECTION_MOVE",
            )

        if signal == "BUY":
            return (
                round(
                    original_entry + ORB_FAILED_RETEST_OPPOSITE_SCALP_SMC_MOVE_PRICE,
                    2,
                ),
                "SAME_DIRECTION_MOVE",
            )

        return None, None

    # =========================
    # WAIT_RETEST NOT CONFIRMED
    # Do NOT wait for retest zone.
    # Execute opposite scalp from setup entry area, after M5 confirmation.
    # =========================
    if "ORB_RETEST_REJECTION_NOT_CONFIRMED" in source:
        if original_entry <= 0:
            return None, None

        return round(original_entry, 2), "IMMEDIATE_ENTRY_TRIGGER"

    return None, None


def trigger_reached(trigger_model, original_signal, current_price, trigger_price):
    # =========================
    # WAIT_RETEST not confirmed
    # No zone wait. Setup is already eligible.
    # =========================
    if trigger_model == "IMMEDIATE_ENTRY_TRIGGER":
        return True

    # =========================
    # SMC_FAILED model
    # Price must move WITH original direction first.
    # =========================
    if trigger_model == "SAME_DIRECTION_MOVE":
        if original_signal == "SELL":
            return current_price <= trigger_price

        if original_signal == "BUY":
            return current_price >= trigger_price

        return False

    return False


def build_m5_dataframe(symbol):
    rates = mt5.copy_rates_from_pos(
        symbol,
        ORB_FAILED_RETEST_OPPOSITE_SCALP_CONFIRMATION_TIMEFRAME,
        0,
        ORB_FAILED_RETEST_OPPOSITE_SCALP_CONFIRMATION_BARS,
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
    if not ORB_FAILED_RETEST_OPPOSITE_SCALP_REQUIRE_M5_CONFIRMATION:
        return True, "m5_confirmation_disabled"

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

    if body < atr * ORB_FAILED_RETEST_OPPOSITE_SCALP_MIN_BODY_ATR:
        return False, "m5_body_too_small"

    if signal == "BUY":
        if close_price <= open_price:
            return False, "m5_not_bullish"

        if ORB_FAILED_RETEST_OPPOSITE_SCALP_REQUIRE_EMA_ALIGNMENT and close_price < ema:
            return False, "m5_buy_below_ema"

        return True, "m5_bullish_confirmation"

    if signal == "SELL":
        if close_price >= open_price:
            return False, "m5_not_bearish"

        if ORB_FAILED_RETEST_OPPOSITE_SCALP_REQUIRE_EMA_ALIGNMENT and close_price > ema:
            return False, "m5_sell_above_ema"

        return True, "m5_bearish_confirmation"

    return False, "invalid_signal"


def register_orb_failed_retest_opposite_scalp(
    *,
    symbol,
    signal,
    trade_plan,
    signal_data,
    source_reason,
):
    if not ENABLE_ORB_FAILED_RETEST_OPPOSITE_SCALP:
        return False

    strategy = str(signal_data.get("strategy", trade_plan.get("strategy", "UNKNOWN"))).upper()
    score = float(signal_data.get("score", trade_plan.get("score", 0)) or 0)

    if strategy not in ORB_FAILED_RETEST_OPPOSITE_SCALP_STRATEGIES:
        return False

    if score < ORB_FAILED_RETEST_OPPOSITE_SCALP_MIN_SCORE:
        return False

    opposite = opposite_signal(signal)

    if opposite is None:
        return False

    trigger_price, trigger_model = build_trigger_price(
        signal=signal,
        trade_plan=trade_plan,
        signal_data=signal_data,
        source_reason=source_reason,
    )

    if trigger_price is None or trigger_model is None:
        return False

    setup_id = str(
        trade_plan.get(
            "setup_id",
            signal_data.get("setup_id", f"ORBOPP-{strategy}-{datetime.now().timestamp()}"),
        )
    )

    pending_id = f"{setup_id}-OPPOSITE-SCALP"

    entries = load_pending_scalps()

    if pending_id in entries:
        return False

    expires_at = datetime.now() + timedelta(
        minutes=ORB_FAILED_RETEST_OPPOSITE_SCALP_EXPIRY_MINUTES
    )

    entries[pending_id] = {
        "pending_id": pending_id,
        "setup_id": setup_id,
        "status": "WAITING_TRIGGER",
        "created_at": datetime.now().isoformat(),
        "expires_at": expires_at.isoformat(),
        "symbol": symbol,
        "strategy": strategy,
        "original_signal": signal,
        "opposite_signal": opposite,
        "score": score,
        "source_reason": source_reason,
        "trigger_model": trigger_model,
        "trigger_price": trigger_price,
        "trade_plan": _json_safe(trade_plan),
        "signal_data": _json_safe(signal_data),
    }

    save_pending_scalps(entries)

    logger.info(
        f"[ORB OPP SCALP] Registered | "
        f"strategy={strategy} original={signal} opposite={opposite} "
        f"trigger={trigger_price} source={source_reason}"
    )

    send_telegram_message(
        f"⏳ ORB Opposite Scalp Pending\n"
        f"Symbol: {symbol}\n"
        f"Strategy: {strategy}\n"
        f"Original Signal: {signal}\n"
        f"Opposite Scalp: {opposite}\n"
        f"Trigger: {trigger_price}\n"
        f"Source: {source_reason}\n"
        f"Expiry: {expires_at.strftime('%H:%M:%S')}"
    )

    return True


def build_opposite_scalp_plan(symbol, pending):
    signal = pending["opposite_signal"]
    current_price = get_current_execution_price(symbol, signal)

    if current_price is None:
        return None, "invalid_current_price"

    entry = round(float(current_price), 2)
    original_plan = pending["trade_plan"]
    original_lot = float(original_plan.get("lot", 0.0) or 0.0)

    if original_lot <= 0:
        return None, "invalid_original_lot"

    lot = round(original_lot * ORB_FAILED_RETEST_OPPOSITE_SCALP_LOT_MULTIPLIER, 2)

    if lot <= 0:
        return None, "invalid_lot"

    if signal == "BUY":
        sl = round(entry - ORB_FAILED_RETEST_OPPOSITE_SCALP_FIXED_SL_PRICE, 2)
        tp = round(entry + ORB_FAILED_RETEST_OPPOSITE_SCALP_FIXED_TP_PRICE, 2)

    elif signal == "SELL":
        sl = round(entry + ORB_FAILED_RETEST_OPPOSITE_SCALP_FIXED_SL_PRICE, 2)
        tp = round(entry - ORB_FAILED_RETEST_OPPOSITE_SCALP_FIXED_TP_PRICE, 2)

    else:
        return None, "invalid_signal"

    trade_plan = original_plan.copy()
    trade_plan["signal"] = signal
    trade_plan["strategy"] = "ORB_FAILED_RETEST_OPPOSITE_SCALP"
    trade_plan["entry_model"] = "ORB_FAILED_RETEST_OPPOSITE_SCALP"
    trade_plan["entry_price"] = entry
    trade_plan["stop_loss"] = sl
    trade_plan["take_profit"] = tp
    trade_plan["stop_distance"] = ORB_FAILED_RETEST_OPPOSITE_SCALP_FIXED_SL_PRICE
    trade_plan["lot"] = lot
    trade_plan["comment"] = COMMENT
    trade_plan["setup_id"] = pending["pending_id"]
    trade_plan["is_orb_failed_retest_opposite_scalp"] = True
    trade_plan["protect_after_profit_price"] = (
        ORB_FAILED_RETEST_OPPOSITE_SCALP_PROTECT_AFTER_PROFIT_PRICE
    )
    trade_plan["reason"] = (
        f"ORB failed/retest-not-confirmed opposite scalp | "
        f"source={pending.get('source_reason')} | "
        f"original={pending.get('strategy')} {pending.get('original_signal')} | "
        f"trigger={pending.get('trigger_price')}"
    )

    return trade_plan, "ready"


def get_ready_orb_failed_retest_opposite_scalps(symbol):
    entries = load_pending_scalps()
    ready = []
    changed = False
    now = datetime.now()

    for pending_id, pending in list(entries.items()):
        if pending.get("symbol") != symbol:
            continue

        if pending.get("status") != "WAITING_TRIGGER":
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

        original_signal = pending.get("original_signal")
        opposite = pending.get("opposite_signal")
        trigger_model = pending.get("trigger_model")
        trigger_price = float(pending.get("trigger_price", 0.0) or 0.0)

        current_price = get_current_execution_price(symbol, opposite)

        if current_price is None:
            continue

        current_price = round(float(current_price), 2)

        if not trigger_reached(
            trigger_model=trigger_model,
            original_signal=original_signal,
            current_price=current_price,
            trigger_price=trigger_price,
        ):
            continue

        confirmed, confirmation_reason = m5_confirmation_ok(symbol, opposite)

        if not confirmed:
            logger.info(
                f"[ORB OPP SCALP] Trigger reached but confirmation failed | "
                f"id={pending_id} reason={confirmation_reason}"
            )
            continue

        trade_plan, plan_reason = build_opposite_scalp_plan(
            symbol=symbol,
            pending=pending,
        )

        if trade_plan is None:
            logger.info(
                f"[ORB OPP SCALP] Plan refused | "
                f"id={pending_id} reason={plan_reason}"
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
                "signal": opposite,
                "trade_plan": trade_plan,
            }
        )

    if changed:
        save_pending_scalps(entries)

    return ready


def mark_orb_failed_retest_opposite_scalp_executed(pending_id):
    entries = load_pending_scalps()

    if pending_id not in entries:
        return

    entries[pending_id]["status"] = "EXECUTED"
    entries[pending_id]["executed_at"] = datetime.now().isoformat()

    save_pending_scalps(entries)


def protect_orb_failed_retest_opposite_scalps(symbol):
    if not ENABLE_ORB_FAILED_RETEST_OPPOSITE_SCALP:
        return

    if not ORB_FAILED_RETEST_OPPOSITE_SCALP_PROTECT_SL_TO_ENTRY:
        return

    positions = mt5.positions_get(symbol=symbol)

    if positions is None:
        return

    symbol_info = mt5.symbol_info(symbol)

    if symbol_info is None:
        return

    digits = int(symbol_info.digits)
    tick = mt5.symbol_info_tick(symbol)

    if tick is None:
        return

    for position in positions:
        comment = str(getattr(position, "comment", "") or "")

        if COMMENT not in comment:
            continue

        position_type = int(position.type)
        entry = float(position.price_open)
        current_sl = float(position.sl or 0.0)
        current_tp = float(position.tp or 0.0)

        if position_type == mt5.POSITION_TYPE_BUY:
            current_price = float(tick.bid)
            profit_distance = current_price - entry

            if profit_distance < ORB_FAILED_RETEST_OPPOSITE_SCALP_PROTECT_AFTER_PROFIT_PRICE:
                continue

            new_sl = round(entry, digits)

            if current_sl >= new_sl:
                continue

        elif position_type == mt5.POSITION_TYPE_SELL:
            current_price = float(tick.ask)
            profit_distance = entry - current_price

            if profit_distance < ORB_FAILED_RETEST_OPPOSITE_SCALP_PROTECT_AFTER_PROFIT_PRICE:
                continue

            new_sl = round(entry, digits)

            if current_sl > 0 and current_sl <= new_sl:
                continue

        else:
            continue

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": position.ticket,
            "symbol": symbol,
            "sl": new_sl,
            "tp": current_tp,
        }

        result = mt5.order_send(request)

        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(
                f"[ORB OPP SCALP] Protected at entry | "
                f"ticket={position.ticket} entry={entry} sl={new_sl}"
            )
            send_telegram_message(
                f"🛡️ ORB Opposite Scalp Protected\n"
                f"Symbol: {symbol}\n"
                f"Ticket: {position.ticket}\n"
                f"SL moved to entry: {new_sl}"
            )
        else:
            logger.warning(
                f"[ORB OPP SCALP] Failed to protect | "
                f"ticket={position.ticket} result={result}"
            )