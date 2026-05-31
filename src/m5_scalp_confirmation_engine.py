import json
from datetime import datetime, timedelta

import MetaTrader5 as mt5
import pandas as pd

from config.settings import (
    SYMBOL,
    ENABLE_M5_SCALP_CONFIRMATION_ENGINE,
    M5_SCALP_CONFIRMATION_TIMEFRAME,
    M5_SCALP_CONFIRMATION_BARS,
    M5_SCALP_CONFIRMATION_EXPIRY_MINUTES,
    M5_SCALP_CONFIRMATION_MIN_BODY_ATR,
    M5_SCALP_CONFIRMATION_REQUIRE_EMA_ALIGNMENT,
    M5_SCALP_CONFIRMATION_MIN_SCORE,
    M5_SCALP_CONFIRMATION_MIN_RR,
    M5_SCALP_CONFIRMATION_STRATEGIES,
)
from src.account_context import get_account_file
from src.logger import logger
from src.market_price import get_current_execution_price
from src.notifier import send_telegram_message


def get_m5_scalp_file():
    return get_account_file("pending_m5_scalp_setups.json")


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


def load_m5_scalp_setups():
    file_path = get_m5_scalp_file()

    if not file_path.exists() or file_path.stat().st_size == 0:
        return {}

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[M5 SCALP] Failed to load pending file: {e}")
        return {}


def save_m5_scalp_setups(setups):
    file_path = get_m5_scalp_file()
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(_json_safe(setups), f, indent=2, ensure_ascii=False)

        temp_path.replace(file_path)
    except Exception as e:
        logger.error(f"[M5 SCALP] Failed to save pending file: {e}")


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


def register_m5_scalp_confirmation_setup(
    *,
    symbol,
    signal,
    scalp_trade_plan,
    source_reason,
):
    if not ENABLE_M5_SCALP_CONFIRMATION_ENGINE:
        return False

    strategy = str(scalp_trade_plan.get("strategy", "UNKNOWN")).upper()
    score = float(scalp_trade_plan.get("score", 0) or 0)
    rr = float(scalp_trade_plan.get("scalp_rr", 0) or 0)

    if strategy not in M5_SCALP_CONFIRMATION_STRATEGIES:
        return False

    if score < M5_SCALP_CONFIRMATION_MIN_SCORE:
        return False

    if rr < M5_SCALP_CONFIRMATION_MIN_RR:
        return False

    setup_id = str(scalp_trade_plan.get("setup_id", f"M5SCALP-{strategy}-{datetime.now().timestamp()}"))
    pending_id = f"{setup_id}-M5-SCALP"

    setups = load_m5_scalp_setups()

    if pending_id in setups:
        return False

    expires_at = datetime.now() + timedelta(minutes=M5_SCALP_CONFIRMATION_EXPIRY_MINUTES)

    setups[pending_id] = {
        "pending_id": pending_id,
        "setup_id": setup_id,
        "status": "WAITING_M5_CONFIRMATION",
        "created_at": datetime.now().isoformat(),
        "expires_at": expires_at.isoformat(),
        "symbol": symbol,
        "signal": signal,
        "strategy": strategy,
        "score": score,
        "source_reason": source_reason,
        "scalp_trade_plan": _json_safe(scalp_trade_plan),
    }

    save_m5_scalp_setups(setups)

    logger.info(
        f"[M5 SCALP] Registered pending confirmation | "
        f"strategy={strategy} signal={signal} setup_id={setup_id}"
    )

    send_telegram_message(
        f"⏳ M5 Scalp Confirmation Pending\n"
        f"Symbol: {symbol}\n"
        f"Strategy: {strategy}\n"
        f"Signal: {signal}\n"
        f"Setup: {setup_id}\n"
        f"Reason: {source_reason}\n"
        f"Expiry: {expires_at.strftime('%H:%M:%S')}"
    )

    return True


def _build_m5_dataframe(symbol):
    rates = mt5.copy_rates_from_pos(
        symbol,
        M5_SCALP_CONFIRMATION_TIMEFRAME,
        0,
        M5_SCALP_CONFIRMATION_BARS,
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
    df = _build_m5_dataframe(symbol)

    if df is None or len(df) < 25:
        return False, "not_enough_m5_data"

    # latest closed M5 candle
    candle = df.iloc[-2]

    atr = float(candle.get("atr_14", 0.0) or 0.0)
    ema = float(candle.get("ema_20", 0.0) or 0.0)
    open_price = float(candle["open"])
    close_price = float(candle["close"])
    body = abs(close_price - open_price)

    if atr <= 0:
        return False, "invalid_m5_atr"

    if body < atr * M5_SCALP_CONFIRMATION_MIN_BODY_ATR:
        return False, "m5_body_too_small"

    if signal == "BUY":
        if close_price <= open_price:
            return False, "m5_not_bullish"

        if M5_SCALP_CONFIRMATION_REQUIRE_EMA_ALIGNMENT and close_price < ema:
            return False, "m5_buy_below_ema"

        return True, "m5_bullish_confirmation"

    if signal == "SELL":
        if close_price >= open_price:
            return False, "m5_not_bearish"

        if M5_SCALP_CONFIRMATION_REQUIRE_EMA_ALIGNMENT and close_price > ema:
            return False, "m5_sell_above_ema"

        return True, "m5_bearish_confirmation"

    return False, "invalid_signal"


def rebase_scalp_plan_to_current_price(symbol, signal, scalp_trade_plan):
    current_price = get_current_execution_price(symbol, signal)

    if current_price is None:
        return None, "invalid_current_price"

    current_price = round(float(current_price), 2)

    stop_distance = float(scalp_trade_plan.get("scalp_stop_distance", 0.0) or 0.0)
    target_distance = float(scalp_trade_plan.get("scalp_target_distance", 0.0) or 0.0)

    if stop_distance <= 0 or target_distance <= 0:
        return None, "invalid_scalp_distances"

    rebased = scalp_trade_plan.copy()
    rebased["entry_price"] = current_price

    if signal == "BUY":
        rebased["stop_loss"] = round(current_price - stop_distance, 2)
        rebased["take_profit"] = round(current_price + target_distance, 2)
    elif signal == "SELL":
        rebased["stop_loss"] = round(current_price + stop_distance, 2)
        rebased["take_profit"] = round(current_price - target_distance, 2)
    else:
        return None, "invalid_signal"

    rr = calculate_rr(
        signal=signal,
        entry=rebased["entry_price"],
        sl=rebased["stop_loss"],
        tp=rebased["take_profit"],
    )

    if rr is None or rr < M5_SCALP_CONFIRMATION_MIN_RR:
        return None, f"rr_invalid_after_rebase {rr}/{M5_SCALP_CONFIRMATION_MIN_RR}"

    rebased["scalp_rr"] = rr
    rebased["reason"] = (
        f"{rebased.get('reason', '')} | "
        f"M5_SCALP_CONFIRMATION_REBASED rr={rr}"
    )

    return rebased, "ready"


def get_ready_m5_scalp_setups(symbol=SYMBOL):
    setups = load_m5_scalp_setups()
    ready = []
    changed = False
    now = datetime.now()

    for pending_id, setup in list(setups.items()):
        if setup.get("symbol") != symbol:
            continue

        if setup.get("status") != "WAITING_M5_CONFIRMATION":
            continue

        try:
            expires_at = datetime.fromisoformat(setup["expires_at"])
        except Exception:
            setup["status"] = "EXPIRED"
            changed = True
            continue

        if now > expires_at:
            setup["status"] = "EXPIRED"
            changed = True
            continue

        signal = setup.get("signal")

        confirmed, reason = m5_confirmation_ok(symbol, signal)

        if not confirmed:
            logger.info(
                f"[M5 SCALP] Still waiting | id={pending_id} reason={reason}"
            )
            continue

        rebased_plan, rebase_reason = rebase_scalp_plan_to_current_price(
            symbol=symbol,
            signal=signal,
            scalp_trade_plan=setup["scalp_trade_plan"],
        )

        if rebased_plan is None:
            logger.info(
                f"[M5 SCALP] Confirmation passed but plan not ready | "
                f"id={pending_id} reason={rebase_reason}"
            )
            continue

        setup["status"] = "READY_TO_EXECUTE"
        setup["ready_at"] = now.isoformat()
        setup["confirmation_reason"] = reason
        changed = True

        ready.append(
            {
                "pending_id": pending_id,
                "symbol": symbol,
                "signal": signal,
                "trade_plan": rebased_plan,
            }
        )

    if changed:
        save_m5_scalp_setups(setups)

    return ready


def mark_m5_scalp_executed(pending_id):
    setups = load_m5_scalp_setups()

    if pending_id not in setups:
        return

    setups[pending_id]["status"] = "EXECUTED"
    setups[pending_id]["executed_at"] = datetime.now().isoformat()

    save_m5_scalp_setups(setups)