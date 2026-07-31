import hashlib
from config.settings import ATR_MIN, ATR_MAX



PHASE6P3C_REMAINING_LEGACY_STANDARDIZATION = True
PHASE6P3C_STRATEGY_NAME = "VWAP_RECLAIM"
PHASE6P3C_FALLBACK_PHASE_NAME = "PHASE_6P3C_VWAP_RECLAIM_STANDARDIZED_COMPLETION"
PHASE6P3C_SETUP_PREFIX = "VWAP"
PHASE6P3C_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

VWAP_LOOKBACK = 40

VWAP_MIN_DISTANCE_ATR = 0.60
VWAP_MAX_DISTANCE_ATR = 2.50

VWAP_MIN_BODY_ATR = 0.20
VWAP_MIN_REJECTION_WICK_BODY = 1.00

VWAP_SL_ATR_MULTIPLIER = 0.20
VWAP_MIN_SL_BUFFER = 2.0
VWAP_MAX_SL_BUFFER = 5.0

VWAP_FALLBACK_TARGET_ATR = 1.50


def _sl_buffer(atr):
    return min(
        max(atr * VWAP_SL_ATR_MULTIPLIER, VWAP_MIN_SL_BUFFER),
        VWAP_MAX_SL_BUFFER,
    )


def _calculate_vwap(df):
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    volume = df.get("tick_volume")

    if volume is None or volume.sum() <= 0:
        return typical_price.mean()

    return (typical_price * volume).sum() / volume.sum()


def _score_setup(base_score, body, atr, wick_ratio, reclaim_strength):
    score = base_score

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.50:
        score += 2

    if wick_ratio >= 1.5:
        score += 2

    if reclaim_strength:
        score += 3

    return min(score, 99)


def _phase6p3c_generate_signal_raw(df):
    if len(df) < VWAP_LOOKBACK + 5:
        return None

    closed = df.iloc[:-1]
    vwap_data = closed.iloc[-VWAP_LOOKBACK:]

    entry = df.iloc[-2]
    prev = df.iloc[-3]

    atr = entry["atr_14"]
    ema = entry["ema_20"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    vwap = _calculate_vwap(vwap_data)

    open_price = entry["open"]
    close_price = entry["close"]
    high = entry["high"]
    low = entry["low"]

    body = abs(close_price - open_price)
    candle_range = high - low

    if body <= 0 or candle_range <= 0 or atr <= 0:
        return None

    distance_from_vwap = abs(close_price - vwap)

    if distance_from_vwap < atr * VWAP_MIN_DISTANCE_ATR:
        return None

    if distance_from_vwap > atr * VWAP_MAX_DISTANCE_ATR:
        return None

    recent = closed.iloc[-20:]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    upper_wick = high - max(open_price, close_price)
    lower_wick = min(open_price, close_price) - low

    sl_buffer = _sl_buffer(atr)

    # =========================
    # BUY: stretched below VWAP, sweep low, reclaim upward
    # =========================
    stretched_below_vwap = close_price < vwap

    swept_low = (
        low < recent_low
        or prev["low"] < recent_low
    )

    bullish_reclaim = (
        close_price > open_price
        and close_price > low + candle_range * 0.60
        and lower_wick > body * VWAP_MIN_REJECTION_WICK_BODY
    )

    reclaim_strength = close_price > ema or close_price > prev["high"]

    if (
        stretched_below_vwap
        and swept_low
        and bullish_reclaim
        and body > atr * VWAP_MIN_BODY_ATR
    ):
        sl_reference = round(min(low, prev["low"]) - sl_buffer, 2)

        if vwap > close_price:
            tp_reference = vwap
            target_model = "VWAP_RECLAIM_TARGET"
        else:
            tp_reference = close_price + atr * VWAP_FALLBACK_TARGET_ATR
            target_model = "VWAP_FALLBACK_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference >= close_price or tp_reference <= close_price:
            return None

        wick_ratio = lower_wick / body if body > 0 else 0

        score = _score_setup(
            base_score=90,
            body=body,
            atr=atr,
            wick_ratio=wick_ratio,
            reclaim_strength=reclaim_strength,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "VWAP_RECLAIM",
            "entry_model": "VWAP_MEAN_REVERSION_RECLAIM",
            "pattern_height": abs(tp_reference - close_price),
            "vwap": vwap,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sweep_low": min(low, prev["low"]),
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_vwap_reclaim",
            "direction_context": "mean_reversion_from_below_vwap",
            "reason": (
                f"VWAP reclaim BUY -> price stretched below VWAP {round(vwap, 2)} -> "
                f"sell-side sweep/rejection confirmed -> "
                f"SL below sweep {sl_reference} -> "
                f"TP {target_model} {tp_reference}"
            ),
        }

    # =========================
    # SELL: stretched above VWAP, sweep high, reclaim downward
    # =========================
    stretched_above_vwap = close_price > vwap

    swept_high = (
        high > recent_high
        or prev["high"] > recent_high
    )

    bearish_reclaim = (
        close_price < open_price
        and close_price < high - candle_range * 0.60
        and upper_wick > body * VWAP_MIN_REJECTION_WICK_BODY
    )

    reclaim_strength = close_price < ema or close_price < prev["low"]

    if (
        stretched_above_vwap
        and swept_high
        and bearish_reclaim
        and body > atr * VWAP_MIN_BODY_ATR
    ):
        sl_reference = round(max(high, prev["high"]) + sl_buffer, 2)

        if vwap < close_price:
            tp_reference = vwap
            target_model = "VWAP_RECLAIM_TARGET"
        else:
            tp_reference = close_price - atr * VWAP_FALLBACK_TARGET_ATR
            target_model = "VWAP_FALLBACK_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference <= close_price or tp_reference >= close_price:
            return None

        wick_ratio = upper_wick / body if body > 0 else 0

        score = _score_setup(
            base_score=90,
            body=body,
            atr=atr,
            wick_ratio=wick_ratio,
            reclaim_strength=reclaim_strength,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "VWAP_RECLAIM",
            "entry_model": "VWAP_MEAN_REVERSION_REJECT",
            "pattern_height": abs(close_price - tp_reference),
            "vwap": vwap,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sweep_high": max(high, prev["high"]),
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_vwap_reclaim",
            "direction_context": "mean_reversion_from_above_vwap",
            "reason": (
                f"VWAP reclaim SELL -> price stretched above VWAP {round(vwap, 2)} -> "
                f"buy-side sweep/rejection confirmed -> "
                f"SL above sweep {sl_reference} -> "
                f"TP {target_model} {tp_reference}"
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

