import hashlib
from config.settings import (
    VWAP_RANGE_LOOKBACK_BARS,
    VWAP_RANGE_EDGE_ZONE_PCT,
    VWAP_RANGE_MIN_DEVIATION_ATR,
    VWAP_RANGE_SL_BUFFER_PRICE,
    VWAP_RANGE_MEAN_REVERSION_BASE_MIN_SCORE,
)



PHASE6P3C_REMAINING_LEGACY_STANDARDIZATION = True
PHASE6P3C_STRATEGY_NAME = "VWAP_RANGE_MEAN_REVERSION"
PHASE6P3C_FALLBACK_PHASE_NAME = "PHASE_6P3C_VWAP_RANGE_MEAN_REVERSION_STANDARDIZED_COMPLETION"
PHASE6P3C_SETUP_PREFIX = "VRMR"
PHASE6P3C_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

def _calculate_vwap(window):
    typical_price = (window["high"] + window["low"] + window["close"]) / 3

    if "tick_volume" in window.columns:
        volume = window["tick_volume"].replace(0, 1)
    elif "real_volume" in window.columns:
        volume = window["real_volume"].replace(0, 1)
    else:
        volume = 1

    try:
        return float((typical_price * volume).sum() / volume.sum())
    except Exception:
        return float(typical_price.mean())


def _range_context(df):
    if len(df) < VWAP_RANGE_LOOKBACK_BARS + 5:
        return None

    closed_window = df.iloc[-VWAP_RANGE_LOOKBACK_BARS - 1:-1]
    signal_candle = df.iloc[-2]

    range_window = closed_window.iloc[:-1]

    range_high = float(range_window["high"].max())
    range_low = float(range_window["low"].min())
    range_mid = (range_high + range_low) / 2
    range_width = range_high - range_low

    if range_width <= 0:
        return None

    atr = float(signal_candle["atr_14"])

    if atr <= 0:
        return None

    vwap = _calculate_vwap(closed_window)

    return {
        "signal_candle": signal_candle,
        "range_high": range_high,
        "range_low": range_low,
        "range_mid": range_mid,
        "range_width": range_width,
        "atr": atr,
        "vwap": vwap,
    }


def _phase6p3c_generate_signal_raw(df):
    context = _range_context(df)

    if context is None:
        return None

    candle = context["signal_candle"]
    range_high = context["range_high"]
    range_low = context["range_low"]
    range_mid = context["range_mid"]
    range_width = context["range_width"]
    atr = context["atr"]
    vwap = context["vwap"]

    open_price = float(candle["open"])
    high = float(candle["high"])
    low = float(candle["low"])
    close = float(candle["close"])

    upper_edge = range_high - range_width * VWAP_RANGE_EDGE_ZONE_PCT
    lower_edge = range_low + range_width * VWAP_RANGE_EDGE_ZONE_PCT

    min_deviation = atr * VWAP_RANGE_MIN_DEVIATION_ATR
    sl_buffer = max(VWAP_RANGE_SL_BUFFER_PRICE, atr * 0.15)

    body = abs(close - open_price)
    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low

    # =========================
    # BUY: lower range + below VWAP + bullish rejection
    # =========================
    buy_location = low <= lower_edge
    buy_deviation = close < vwap - min_deviation
    buy_rejection = close > open_price and lower_wick >= max(body * 0.35, atr * 0.08)

    if buy_location and buy_deviation and buy_rejection:
        tp_reference = round(vwap, 2)

        if tp_reference <= close:
            tp_reference = round(range_mid, 2)

        if tp_reference <= close:
            return None

        sl_reference = round(low - sl_buffer, 2)

        score = VWAP_RANGE_MEAN_REVERSION_BASE_MIN_SCORE

        if low <= range_low + atr * 0.30:
            score += 5

        if lower_wick >= atr * 0.25:
            score += 4

        score = min(score, 100)

        return {
            "signal": "BUY",
            "score": score,
            "entry_model": "VWAP_RANGE_MEAN_REVERSION_BUY",
            "sl_model": "RANGE_REJECTION_SL",
            "tp_model": "VWAP_REVERSION_TP",
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "vwap": round(vwap, 2),
            "range_high": round(range_high, 2),
            "range_low": round(range_low, 2),
            "range_mid": round(range_mid, 2),
            "reason": (
                f"VWAP Range Mean Reversion BUY -> price at lower range edge "
                f"and below VWAP {round(vwap, 2)} with bullish rejection -> "
                f"SL {sl_reference} -> TP VWAP/mean {tp_reference}"
            ),
        }

    # =========================
    # SELL: upper range + above VWAP + bearish rejection
    # =========================
    sell_location = high >= upper_edge
    sell_deviation = close > vwap + min_deviation
    sell_rejection = close < open_price and upper_wick >= max(body * 0.35, atr * 0.08)

    if sell_location and sell_deviation and sell_rejection:
        tp_reference = round(vwap, 2)

        if tp_reference >= close:
            tp_reference = round(range_mid, 2)

        if tp_reference >= close:
            return None

        sl_reference = round(high + sl_buffer, 2)

        score = VWAP_RANGE_MEAN_REVERSION_BASE_MIN_SCORE

        if high >= range_high - atr * 0.30:
            score += 5

        if upper_wick >= atr * 0.25:
            score += 4

        score = min(score, 100)

        return {
            "signal": "SELL",
            "score": score,
            "entry_model": "VWAP_RANGE_MEAN_REVERSION_SELL",
            "sl_model": "RANGE_REJECTION_SL",
            "tp_model": "VWAP_REVERSION_TP",
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "vwap": round(vwap, 2),
            "range_high": round(range_high, 2),
            "range_low": round(range_low, 2),
            "range_mid": round(range_mid, 2),
            "reason": (
                f"VWAP Range Mean Reversion SELL -> price at upper range edge "
                f"and above VWAP {round(vwap, 2)} with bearish rejection -> "
                f"SL {sl_reference} -> TP VWAP/mean {tp_reference}"
            ),
        }

    return None


def _phase6p3c_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _phase6p3c_entry_reference(df, payload):
    for key in ("entry_reference", "entry_price", "entry", "price"):
        value = _phase6p3c_float(payload.get(key))

        if value is not None:
            return value

    try:
        if df is not None and len(df) >= 2:
            return float(df.iloc[-2]["close"])
    except Exception:
        pass

    try:
        if df is not None and len(df) >= 1:
            return float(df.iloc[-1]["close"])
    except Exception:
        pass

    return None


def _phase6p3c_risk_reward(signal, entry_reference, sl_reference, tp_reference):
    entry_reference = _phase6p3c_float(entry_reference)
    sl_reference = _phase6p3c_float(sl_reference)
    tp_reference = _phase6p3c_float(tp_reference)

    if entry_reference is None or sl_reference is None or tp_reference is None:
        return None

    if signal == "BUY":
        risk = entry_reference - sl_reference
        reward = tp_reference - entry_reference
    else:
        risk = sl_reference - entry_reference
        reward = entry_reference - tp_reference

    if risk <= 0:
        return None

    return round(reward / risk, 2)


def _phase6p3c_setup_id(payload, entry_reference):
    signal = payload.get("signal", "NA")
    entry_model = payload.get("entry_model", payload.get("type", "NA"))
    sl_reference = payload.get("sl_reference", payload.get("stop_loss", ""))
    tp_reference = payload.get("tp_reference", payload.get("take_profit", ""))

    raw = (
        f"{PHASE6P3C_STRATEGY_NAME}:{signal}:{entry_model}:"
        f"{round(float(entry_reference), 2)}:{sl_reference}:{tp_reference}"
    )
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]

    return f"{PHASE6P3C_SETUP_PREFIX}-{signal}-{digest}"


def _phase6p3c_standardize_signal(payload, df):
    if not payload:
        return payload

    signal = payload.get("signal")
    entry_reference = _phase6p3c_entry_reference(df, payload)

    if entry_reference is None:
        return payload

    existing_rr = _phase6p3c_float(payload.get("rr"))
    existing_risk_reward = _phase6p3c_float(payload.get("risk_reward"))

    computed_rr = _phase6p3c_risk_reward(
        signal=signal,
        entry_reference=entry_reference,
        sl_reference=payload.get("sl_reference", payload.get("stop_loss")),
        tp_reference=payload.get("tp_reference", payload.get("take_profit")),
    )

    final_rr = existing_rr if existing_rr is not None else existing_risk_reward
    final_rr = final_rr if final_rr is not None else computed_rr

    payload.setdefault("strategy", PHASE6P3C_STRATEGY_NAME)
    payload.setdefault("phase", PHASE6P3C_FALLBACK_PHASE_NAME)
    payload.setdefault("setup_id", _phase6p3c_setup_id(payload, entry_reference))
    payload.setdefault("entry_reference", round(float(entry_reference), 2))

    if final_rr is not None:
        payload.setdefault("rr", final_rr)
        payload.setdefault("risk_reward", final_rr)

    payload.setdefault("auto_trade_allowed", True)
    payload.setdefault("decision_impact", "MAIN_BOT_RUNTIME_CONTROLLED")
    payload.setdefault("duplicate_policy", PHASE6P3C_DUPLICATE_POLICY)

    return payload


def generate_signal(df):
    return _phase6p3c_standardize_signal(_phase6p3c_generate_signal_raw(df), df)

