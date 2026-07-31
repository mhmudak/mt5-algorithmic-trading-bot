import hashlib
from config.settings import (
    RANGE_SWEEP_LOOKBACK_BARS,
    RANGE_SWEEP_BUFFER_PRICE,
    RANGE_SWEEP_RECLAIM_BUFFER_PRICE,
    RANGE_SWEEP_SL_BUFFER_PRICE,
    RANGE_SWEEP_MIN_RANGE_ATR,
    RANGE_SWEEP_MAX_RANGE_ATR,
    RANGE_SWEEP_RECLAIM_BASE_MIN_SCORE,
)



PHASE6P3C_REMAINING_LEGACY_STANDARDIZATION = True
PHASE6P3C_STRATEGY_NAME = "RANGE_SWEEP_RECLAIM"
PHASE6P3C_FALLBACK_PHASE_NAME = "PHASE_6P3C_RANGE_SWEEP_RECLAIM_STANDARDIZED_COMPLETION"
PHASE6P3C_SETUP_PREFIX = "RSR"
PHASE6P3C_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

def _valid_range(range_high, range_low, atr):
    if atr is None or atr <= 0:
        return False

    range_width = range_high - range_low

    if range_width <= 0:
        return False

    range_atr = range_width / atr

    return RANGE_SWEEP_MIN_RANGE_ATR <= range_atr <= RANGE_SWEEP_MAX_RANGE_ATR


def _range_context(df):
    if len(df) < RANGE_SWEEP_LOOKBACK_BARS + 5:
        return None

    signal_candle = df.iloc[-2]
    range_window = df.iloc[-RANGE_SWEEP_LOOKBACK_BARS - 2:-2]

    range_high = float(range_window["high"].max())
    range_low = float(range_window["low"].min())
    range_mid = (range_high + range_low) / 2
    atr = float(signal_candle["atr_14"])

    if not _valid_range(range_high, range_low, atr):
        return None

    return {
        "signal_candle": signal_candle,
        "range_high": range_high,
        "range_low": range_low,
        "range_mid": range_mid,
        "atr": atr,
    }


def _phase6p3c_generate_signal_raw(df):
    context = _range_context(df)

    if context is None:
        return None

    candle = context["signal_candle"]
    range_high = context["range_high"]
    range_low = context["range_low"]
    range_mid = context["range_mid"]
    atr = context["atr"]

    open_price = float(candle["open"])
    high = float(candle["high"])
    low = float(candle["low"])
    close = float(candle["close"])

    sweep_buffer = max(RANGE_SWEEP_BUFFER_PRICE, atr * 0.10)
    reclaim_buffer = max(RANGE_SWEEP_RECLAIM_BUFFER_PRICE, atr * 0.05)
    sl_buffer = max(RANGE_SWEEP_SL_BUFFER_PRICE, atr * 0.15)

    lower_wick = min(open_price, close) - low
    upper_wick = high - max(open_price, close)
    body = abs(close - open_price)

    # =========================
    # BUY: Spring below range low then reclaim
    # =========================
    buy_sweep = low < range_low - sweep_buffer
    buy_reclaim = close > range_low + reclaim_buffer
    buy_rejection = close > open_price and lower_wick >= max(body * 0.40, atr * 0.08)

    if buy_sweep and buy_reclaim and buy_rejection:
        score = RANGE_SWEEP_RECLAIM_BASE_MIN_SCORE

        if close > range_low + (range_high - range_low) * 0.15:
            score += 4

        if lower_wick >= atr * 0.25:
            score += 4

        score = min(score, 100)

        sl_reference = round(low - sl_buffer, 2)
        tp_reference = round(range_mid, 2)

        return {
            "signal": "BUY",
            "score": score,
            "entry_model": "RANGE_SWEEP_RECLAIM_BUY",
            "sl_model": "SWEEP_WICK_SL",
            "tp_model": "RANGE_MIDPOINT_TP",
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "range_high": round(range_high, 2),
            "range_low": round(range_low, 2),
            "range_mid": round(range_mid, 2),
            "sweep_low": round(low, 2),
            "reason": (
                f"Range Sweep Reclaim BUY -> price swept below range low "
                f"{round(range_low, 2)} then closed back inside range -> "
                f"SL below sweep wick {sl_reference} -> TP range midpoint {tp_reference}"
            ),
        }

    # =========================
    # SELL: Upthrust above range high then reject
    # =========================
    sell_sweep = high > range_high + sweep_buffer
    sell_reclaim = close < range_high - reclaim_buffer
    sell_rejection = close < open_price and upper_wick >= max(body * 0.40, atr * 0.08)

    if sell_sweep and sell_reclaim and sell_rejection:
        score = RANGE_SWEEP_RECLAIM_BASE_MIN_SCORE

        if close < range_high - (range_high - range_low) * 0.15:
            score += 4

        if upper_wick >= atr * 0.25:
            score += 4

        score = min(score, 100)

        sl_reference = round(high + sl_buffer, 2)
        tp_reference = round(range_mid, 2)

        return {
            "signal": "SELL",
            "score": score,
            "entry_model": "RANGE_SWEEP_RECLAIM_SELL",
            "sl_model": "SWEEP_WICK_SL",
            "tp_model": "RANGE_MIDPOINT_TP",
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "range_high": round(range_high, 2),
            "range_low": round(range_low, 2),
            "range_mid": round(range_mid, 2),
            "sweep_high": round(high, 2),
            "reason": (
                f"Range Sweep Reclaim SELL -> price swept above range high "
                f"{round(range_high, 2)} then closed back inside range -> "
                f"SL above sweep wick {sl_reference} -> TP range midpoint {tp_reference}"
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

