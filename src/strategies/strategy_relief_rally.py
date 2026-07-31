import hashlib
from config.settings import ATR_MIN, ATR_MAX



PHASE6P3C_REMAINING_LEGACY_STANDARDIZATION = True
PHASE6P3C_STRATEGY_NAME = "RELIEF_RALLY"
PHASE6P3C_FALLBACK_PHASE_NAME = "PHASE_6P3C_RELIEF_RALLY_STANDARDIZED_COMPLETION"
PHASE6P3C_SETUP_PREFIX = "RRL"
PHASE6P3C_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

RELIEF_SL_ATR_MULTIPLIER = 0.20
RELIEF_MIN_SL_BUFFER = 2.0
RELIEF_MAX_SL_BUFFER = 5.0


def _sl_buffer(atr):
    return min(
        max(atr * RELIEF_SL_ATR_MULTIPLIER, RELIEF_MIN_SL_BUFFER),
        RELIEF_MAX_SL_BUFFER,
    )


def _score_setup(base_score, entry_body, atr, continuation_strength, close_aligned):
    score = base_score

    if entry_body > atr * 0.35:
        score += 2

    if entry_body > atr * 0.50:
        score += 2

    if continuation_strength:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def _phase6p3c_generate_signal_raw(df):
    if len(df) < 35:
        return None

    # trend leg, relief leg, continuation confirm
    trend_anchor = df.iloc[-8]
    relief_1 = df.iloc[-5]
    relief_2 = df.iloc[-4]
    relief_3 = df.iloc[-3]
    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    entry_body = abs(entry["close"] - entry["open"])
    if entry_body <= 0:
        return None

    structure = df.iloc[-24:-8]
    recent_high = structure["high"].max()
    recent_low = structure["low"].min()

    sl_buffer = _sl_buffer(atr)

    relief_high = max(relief_1["high"], relief_2["high"], relief_3["high"])
    relief_low = min(relief_1["low"], relief_2["low"], relief_3["low"])

    # =========================================================
    # Bearish relief rally
    # overall bearish trend, short-term rebound, then continuation down
    # =========================================================
    bearish_trend_context = trend_anchor["close"] < trend_anchor["ema_20"]

    relief_up = (
        relief_1["close"] > relief_1["open"]
        and relief_2["close"] > relief_2["open"]
    )

    stalled_relief = relief_3["high"] <= max(relief_1["high"], relief_2["high"]) + atr * 0.15

    bearish_resume = (
        entry["close"] < entry["open"]
        and entry["close"] < relief_3["low"]
        and price < ema
        and entry_body > atr * 0.25
    )

    if bearish_trend_context and relief_up and stalled_relief and bearish_resume:
        pattern_height = abs(relief_high - entry["close"])
        sl_reference = round(relief_high + sl_buffer, 2)

        if recent_low < entry["close"]:
            tp_reference = recent_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = entry["close"] - max(pattern_height, atr * 1.5)
            target_model = "MEASURED_CONTINUATION_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=92,
            entry_body=entry_body,
            atr=atr,
            continuation_strength=entry["close"] < relief_low,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "RELIEF_RALLY",
            "entry_model": "RELIEF_CONTINUATION",
            "pattern_height": pattern_height,
            "relief_high": relief_high,
            "relief_low": relief_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_continuation_resume",
            "direction_context": "bearish_trend_price_below_ema",
            "reason": (
                f"Relief rally bearish -> temporary rebound stalled near {round(relief_high, 2)} -> "
                f"trend resumed down -> SL above relief high {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
            ),
        }

    # =========================================================
    # Bullish relief drop
    # overall bullish trend, short-term drop, then continuation up
    # =========================================================
    bullish_trend_context = trend_anchor["close"] > trend_anchor["ema_20"]

    relief_down = (
        relief_1["close"] < relief_1["open"]
        and relief_2["close"] < relief_2["open"]
    )

    stalled_drop = relief_3["low"] >= min(relief_1["low"], relief_2["low"]) - atr * 0.15

    bullish_resume = (
        entry["close"] > entry["open"]
        and entry["close"] > relief_3["high"]
        and price > ema
        and entry_body > atr * 0.25
    )

    if bullish_trend_context and relief_down and stalled_drop and bullish_resume:
        pattern_height = abs(entry["close"] - relief_low)
        sl_reference = round(relief_low - sl_buffer, 2)

        if recent_high > entry["close"]:
            tp_reference = recent_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = entry["close"] + max(pattern_height, atr * 1.5)
            target_model = "MEASURED_CONTINUATION_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=92,
            entry_body=entry_body,
            atr=atr,
            continuation_strength=entry["close"] > relief_high,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "RELIEF_RALLY",
            "entry_model": "RELIEF_CONTINUATION",
            "pattern_height": pattern_height,
            "relief_high": relief_high,
            "relief_low": relief_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_continuation_resume",
            "direction_context": "bullish_trend_price_above_ema",
            "reason": (
                f"Relief drop bullish -> temporary pullback stalled near {round(relief_low, 2)} -> "
                f"trend resumed up -> SL below relief low {sl_reference} -> "
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

