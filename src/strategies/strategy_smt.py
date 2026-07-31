import hashlib
from config.settings import ATR_MIN, ATR_MAX



PHASE6P3C_REMAINING_LEGACY_STANDARDIZATION = True
PHASE6P3C_STRATEGY_NAME = "SMT"
PHASE6P3C_FALLBACK_PHASE_NAME = "PHASE_6P3C_SMT_STANDARDIZED_COMPLETION"
PHASE6P3C_SETUP_PREFIX = "SMT"
PHASE6P3C_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

SMT_SL_ATR_MULTIPLIER = 0.20
SMT_MIN_SL_BUFFER = 2.0
SMT_MAX_SL_BUFFER = 5.0


def _sl_buffer(atr):
    return min(
        max(atr * SMT_SL_ATR_MULTIPLIER, SMT_MIN_SL_BUFFER),
        SMT_MAX_SL_BUFFER,
    )


def _score_setup(base_score, body, atr, wick_strength, close_aligned):
    score = base_score

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.50:
        score += 2

    if wick_strength:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def _phase6p3c_generate_signal_raw(df):
    if len(df) < 45:
        return None

    closed = df.iloc[:-1].reset_index(drop=True)
    data = closed.iloc[-40:].reset_index(drop=True)

    entry = data.iloc[-1]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    highs = data["high"]
    lows = data["low"]

    recent_high_1 = highs.iloc[-12:-6].max()
    recent_high_2 = highs.iloc[-6:].max()

    recent_low_1 = lows.iloc[-12:-6].min()
    recent_low_2 = lows.iloc[-6:].min()

    structure_high = highs.iloc[-20:].max()
    structure_low = lows.iloc[-20:].min()

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if body <= 0 or candle_range <= 0:
        return None

    upper_wick = entry["high"] - max(entry["open"], entry["close"])
    lower_wick = min(entry["open"], entry["close"]) - entry["low"]

    sl_buffer = _sl_buffer(atr)

    # =========================================================
    # Bearish SMT
    # Fake higher high / failed continuation
    # =========================================================
    higher_high = recent_high_2 > recent_high_1

    weak_close = entry["close"] < recent_high_2 - atr * 0.20

    rejection = (
        entry["high"] >= recent_high_2
        and entry["close"] < entry["open"]
        and upper_wick > body * 1.0
    )

    bearish_context = price < ema
    bearish_momentum = body > atr * 0.20

    if higher_high and weak_close and rejection and bearish_context and bearish_momentum:
        pattern_height = abs(recent_high_2 - recent_low_2)

        if pattern_height <= 0:
            return None

        sl_reference = round(recent_high_2 + sl_buffer, 2)

        if structure_low < entry["close"]:
            tp_reference = structure_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = entry["close"] - max(pattern_height, atr * 1.5)
            target_model = "MEASURED_SMT_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=91,
            body=body,
            atr=atr,
            wick_strength=upper_wick > body * 1.5,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "SMT",
            "entry_model": "SMT_INTERNAL_DIVERGENCE_REVERSAL",
            "pattern_height": pattern_height,
            "recent_high_1": recent_high_1,
            "recent_high_2": recent_high_2,
            "recent_low_1": recent_low_1,
            "recent_low_2": recent_low_2,
            "structure_high": structure_high,
            "structure_low": structure_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_rejection_after_higher_high",
            "direction_context": "price_below_ema",
            "reason": (
                f"SMT bearish divergence -> higher high {round(recent_high_2, 2)} not sustained -> "
                f"SL above failed high {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
            ),
        }

    # =========================================================
    # Bullish SMT
    # Fake lower low / failed continuation
    # =========================================================
    lower_low = recent_low_2 < recent_low_1

    weak_close = entry["close"] > recent_low_2 + atr * 0.20

    rejection = (
        entry["low"] <= recent_low_2
        and entry["close"] > entry["open"]
        and lower_wick > body * 1.0
    )

    bullish_context = price > ema
    bullish_momentum = body > atr * 0.20

    if lower_low and weak_close and rejection and bullish_context and bullish_momentum:
        pattern_height = abs(recent_high_2 - recent_low_2)

        if pattern_height <= 0:
            return None

        sl_reference = round(recent_low_2 - sl_buffer, 2)

        if structure_high > entry["close"]:
            tp_reference = structure_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = entry["close"] + max(pattern_height, atr * 1.5)
            target_model = "MEASURED_SMT_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=91,
            body=body,
            atr=atr,
            wick_strength=lower_wick > body * 1.5,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "SMT",
            "entry_model": "SMT_INTERNAL_DIVERGENCE_REVERSAL",
            "pattern_height": pattern_height,
            "recent_high_1": recent_high_1,
            "recent_high_2": recent_high_2,
            "recent_low_1": recent_low_1,
            "recent_low_2": recent_low_2,
            "structure_high": structure_high,
            "structure_low": structure_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_rejection_after_lower_low",
            "direction_context": "price_above_ema",
            "reason": (
                f"SMT bullish divergence -> lower low {round(recent_low_2, 2)} not sustained -> "
                f"SL below failed low {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price above EMA"
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

