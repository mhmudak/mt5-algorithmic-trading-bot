import hashlib
from config.settings import (
    ATR_MIN,
    ATR_MAX,
    ORB_SL_RANGE_PCT_BY_ENTRY_MODEL,
)


PHASE6P3A_PRIORITY_LEGACY_STANDARDIZATION = True
PHASE6P3A_STRATEGY_NAME = "ORB"
PHASE6P3A_FALLBACK_PHASE_NAME = "PHASE_6P3A_ORB_STANDARDIZED_COMPLETION"
PHASE6P3A_SETUP_PREFIX = "ORB"
PHASE6P3A_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

ORB_WINDOW = 15

ORB_MIN_BODY_ATR = 0.30
ORB_FAST_BODY_ATR = 0.38

ORB_CLOSE_STRENGTH = 0.65
ORB_FAST_CLOSE_STRENGTH = 0.72

ORB_TP_EXTENSION_MULTIPLIER = 0.75
ORB_MIN_TP_ATR_MULTIPLIER = 1.2
ORB_MAX_TP_ATR_MULTIPLIER = 3.0


def _sl_buffer(orb_width, entry_model):
    if orb_width is None or orb_width <= 0:
        return 0.0

    model = str(
        entry_model or "BREAKOUT"
    ).upper()

    pct = float(
        ORB_SL_RANGE_PCT_BY_ENTRY_MODEL.get(
            model,
            ORB_SL_RANGE_PCT_BY_ENTRY_MODEL["BREAKOUT"],
        )
    )

    return float(orb_width) * pct / 100.0


def _target_distance(atr, orb_width):
    return min(
        max(orb_width * ORB_TP_EXTENSION_MULTIPLIER, atr * ORB_MIN_TP_ATR_MULTIPLIER),
        atr * ORB_MAX_TP_ATR_MULTIPLIER,
    )


def _score_setup(base_score, body, atr, close_strength, ema_aligned, entry_model):
    score = base_score

    if body > atr * 0.40:
        score += 2

    if body > atr * 0.60:
        score += 2

    if close_strength >= 0.75:
        score += 2

    if close_strength >= 0.85:
        score += 2

    if ema_aligned:
        score += 2

    if entry_model == "WAIT_RETEST":
        score += 2

    if entry_model == "FAST_CONTINUATION":
        score += 3

    return min(score, 99)


def _is_fast_continuation(body, atr, close_strength, breakout_distance, max_immediate):
    return (
        breakout_distance <= max_immediate
        and body >= atr * ORB_FAST_BODY_ATR
        and close_strength >= ORB_FAST_CLOSE_STRENGTH
    )


def _phase6p3a_generate_signal_raw(df):
    if len(df) < ORB_WINDOW + 5:
        return None

    data = df.iloc[-(ORB_WINDOW + 5):-2]

    orb_high = data["high"].max()
    orb_low = data["low"].min()
    orb_width = orb_high - orb_low

    if orb_width <= 0:
        return None

    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return None

    if body < atr * ORB_MIN_BODY_ATR:
        return None

    close_from_low = (entry["close"] - entry["low"]) / candle_range
    close_from_high = (entry["high"] - entry["close"]) / candle_range

    target_distance = _target_distance(atr, orb_width)

    max_immediate = min(atr * 0.35, orb_width * 0.20)
    max_retest = min(atr * 0.80, orb_width * 0.45)

    # =========================
    # BUY ORB
    # =========================
    if price > orb_high and price > ema:
        breakout_distance = price - orb_high

        if breakout_distance > max_retest:
            return None

        bullish_momentum = (
            entry["close"] > entry["open"]
            and close_from_low >= ORB_CLOSE_STRENGTH
        )

        if not bullish_momentum:
            return None

        if _is_fast_continuation(
            body=body,
            atr=atr,
            close_strength=close_from_low,
            breakout_distance=breakout_distance,
            max_immediate=max_immediate,
        ):
            entry_model = "FAST_CONTINUATION"
        elif breakout_distance <= max_immediate:
            entry_model = "BREAKOUT"
        else:
            entry_model = "WAIT_RETEST"

        sl_buffer = _sl_buffer(
            orb_width,
            entry_model,
        )
        sl_reference = round(
            orb_high - sl_buffer,
            2,
        )
        tp_reference = round(orb_high + target_distance, 2)

        if sl_reference >= price:
            return None

        if tp_reference <= price:
            return None

        score = _score_setup(
            base_score=92,
            body=body,
            atr=atr,
            close_strength=close_from_low,
            ema_aligned=price > ema,
            entry_model=entry_model,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "ORB",
            "entry_model": entry_model,
            "pattern_height": orb_width,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "breakout_distance": breakout_distance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "ORB_RANGE_EXTENSION",
            "momentum": "bullish_orb_breakout",
            "direction_context": "price_above_ema",
            "reason": (
                f"ORB BUY ({entry_model}) -> range {round(orb_low, 2)}-{round(orb_high, 2)} -> "
                f"breakout distance {round(breakout_distance, 2)} -> "
                f"SL below breakout level {sl_reference} -> "
                f"TP ORB extension {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # SELL ORB
    # =========================
    if price < orb_low and price < ema:
        breakout_distance = orb_low - price

        if breakout_distance > max_retest:
            return None

        bearish_momentum = (
            entry["close"] < entry["open"]
            and close_from_high >= ORB_CLOSE_STRENGTH
        )

        if not bearish_momentum:
            return None

        if _is_fast_continuation(
            body=body,
            atr=atr,
            close_strength=close_from_high,
            breakout_distance=breakout_distance,
            max_immediate=max_immediate,
        ):
            entry_model = "FAST_CONTINUATION"
        elif breakout_distance <= max_immediate:
            entry_model = "BREAKOUT"
        else:
            entry_model = "WAIT_RETEST"

        sl_buffer = _sl_buffer(
            orb_width,
            entry_model,
        )
        sl_reference = round(
            orb_low + sl_buffer,
            2,
        )
        tp_reference = round(orb_low - target_distance, 2)

        if sl_reference <= price:
            return None

        if tp_reference >= price:
            return None

        score = _score_setup(
            base_score=92,
            body=body,
            atr=atr,
            close_strength=close_from_high,
            ema_aligned=price < ema,
            entry_model=entry_model,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "ORB",
            "entry_model": entry_model,
            "pattern_height": orb_width,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "breakout_distance": breakout_distance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "ORB_RANGE_EXTENSION",
            "momentum": "bearish_orb_breakout",
            "direction_context": "price_below_ema",
            "reason": (
                f"ORB SELL ({entry_model}) -> range {round(orb_low, 2)}-{round(orb_high, 2)} -> "
                f"breakout distance {round(breakout_distance, 2)} -> "
                f"SL above breakout level {sl_reference} -> "
                f"TP ORB extension {tp_reference} -> price below EMA"
            ),
        }

    return None


def _phase6p3a_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _phase6p3a_entry_reference(df, payload):
    for key in ("entry_reference", "entry_price", "entry", "price"):
        value = _phase6p3a_float(payload.get(key))

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


def _phase6p3a_risk_reward(signal, entry_reference, sl_reference, tp_reference):
    entry_reference = _phase6p3a_float(entry_reference)
    sl_reference = _phase6p3a_float(sl_reference)
    tp_reference = _phase6p3a_float(tp_reference)

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


def _phase6p3a_setup_id(payload, entry_reference):
    signal = payload.get("signal", "NA")
    entry_model = payload.get("entry_model", payload.get("type", "NA"))
    sl_reference = payload.get("sl_reference", payload.get("stop_loss", ""))
    tp_reference = payload.get("tp_reference", payload.get("take_profit", ""))

    raw = (
        f"{PHASE6P3A_STRATEGY_NAME}:{signal}:{entry_model}:"
        f"{round(float(entry_reference), 2)}:{sl_reference}:{tp_reference}"
    )
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]

    return f"{PHASE6P3A_SETUP_PREFIX}-{signal}-{digest}"


def _phase6p3a_standardize_signal(payload, df):
    if not payload:
        return payload

    signal = payload.get("signal")
    entry_reference = _phase6p3a_entry_reference(df, payload)

    if entry_reference is None:
        return payload

    existing_rr = _phase6p3a_float(payload.get("rr"))
    existing_risk_reward = _phase6p3a_float(payload.get("risk_reward"))

    computed_rr = _phase6p3a_risk_reward(
        signal=signal,
        entry_reference=entry_reference,
        sl_reference=payload.get("sl_reference", payload.get("stop_loss")),
        tp_reference=payload.get("tp_reference", payload.get("take_profit")),
    )

    final_rr = existing_rr if existing_rr is not None else existing_risk_reward
    final_rr = final_rr if final_rr is not None else computed_rr

    payload.setdefault("strategy", PHASE6P3A_STRATEGY_NAME)
    payload.setdefault("phase", PHASE6P3A_FALLBACK_PHASE_NAME)
    payload.setdefault("setup_id", _phase6p3a_setup_id(payload, entry_reference))
    payload.setdefault("entry_reference", round(float(entry_reference), 2))

    if final_rr is not None:
        payload.setdefault("rr", final_rr)
        payload.setdefault("risk_reward", final_rr)

    payload.setdefault("auto_trade_allowed", True)
    payload.setdefault("decision_impact", "MAIN_BOT_RUNTIME_CONTROLLED")
    payload.setdefault("duplicate_policy", PHASE6P3A_DUPLICATE_POLICY)

    return payload


def generate_signal(df):
    return _phase6p3a_standardize_signal(_phase6p3a_generate_signal_raw(df), df)

