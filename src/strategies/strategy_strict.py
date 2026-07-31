import hashlib
from config.settings import (
    ATR_MIN,
    ATR_MAX,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
)



PHASE6P3C_REMAINING_LEGACY_STANDARDIZATION = True
PHASE6P3C_STRATEGY_NAME = "STRICT"
PHASE6P3C_FALLBACK_PHASE_NAME = "PHASE_6P3C_STRICT_STANDARDIZED_COMPLETION"
PHASE6P3C_SETUP_PREFIX = "STR"
PHASE6P3C_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

STRICT_MIN_BREAKOUT_BODY_ATR = 0.50
STRICT_MIN_ENTRY_BODY_ATR = 0.25
STRICT_MAX_EXTENSION_ATR = 0.80

STRICT_SL_ATR_MULTIPLIER = 0.20
STRICT_MIN_SL_BUFFER = 1.5
STRICT_MAX_SL_BUFFER = 5.0

STRICT_TARGET_RANGE_MULTIPLIER = 0.75
STRICT_MIN_TARGET_ATR = 1.3
STRICT_MAX_TARGET_ATR = 3.0


def _sl_buffer(atr):
    return min(
        max(atr * STRICT_SL_ATR_MULTIPLIER, STRICT_MIN_SL_BUFFER),
        STRICT_MAX_SL_BUFFER,
    )


def _target_distance(atr, structure_range):
    return min(
        max(structure_range * STRICT_TARGET_RANGE_MULTIPLIER, atr * STRICT_MIN_TARGET_ATR),
        atr * STRICT_MAX_TARGET_ATR,
    )


def _score_setup(base_score, breakout_body, entry_body, atr, close_aligned):
    score = base_score

    if breakout_body > atr * 0.70:
        score += 2

    if breakout_body > atr * 1.00:
        score += 2

    if entry_body > atr * 0.35:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def _phase6p3c_generate_signal_raw(df):
    if len(df) < BREAKOUT_LOOKBACK + 8:
        return None

    entry = df.iloc[-2]
    breakout = df.iloc[-3]

    price = entry["close"]
    ema = entry["ema_20"]
    atr = entry["atr_14"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    if abs(price - ema) > atr * 1.5:
        return None

    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 3):-3]
    resistance = recent_data["high"].max()
    support = recent_data["low"].min()

    structure_range = resistance - support
    if structure_range <= 0:
        return None

    breakout_body = abs(breakout["close"] - breakout["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if breakout_body < atr * STRICT_MIN_BREAKOUT_BODY_ATR:
        return None

    if entry_body < atr * STRICT_MIN_ENTRY_BODY_ATR:
        return None

    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, structure_range)

    # =========================
    # BUY: strict breakout above resistance
    # =========================
    breakout_up = (
        breakout["close"] > resistance + BREAKOUT_BUFFER
        and breakout["close"] > breakout["open"]
    )

    bullish_entry = (
        entry["close"] > entry["open"]
        and entry["close"] > resistance
        and price > ema
    )

    extension = entry["close"] - resistance
    not_chasing = extension >= 0 and extension <= atr * STRICT_MAX_EXTENSION_ATR

    if breakout_up and bullish_entry and not_chasing:
        sl_reference = round(resistance - sl_buffer, 2)
        tp_reference = round(entry["close"] + target_distance, 2)

        if sl_reference >= entry["close"]:
            return None

        if tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=90,
            breakout_body=breakout_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "STRICT",
            "entry_model": "STRICT_BREAKOUT_CONTINUATION",
            "pattern_height": target_distance,
            "breakout_level": resistance,
            "support": support,
            "resistance": resistance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "STRICT_RANGE_EXTENSION",
            "momentum": "bullish_strict_breakout",
            "direction_context": "price_above_ema",
            "reason": (
                f"Strict BUY breakout -> resistance {round(resistance, 2)} broken -> "
                f"strong breakout body {round(breakout_body, 2)} -> "
                f"SL below breakout level {sl_reference} -> "
                f"TP strict extension {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # SELL: strict breakdown below support
    # =========================
    breakout_down = (
        breakout["close"] < support - BREAKOUT_BUFFER
        and breakout["close"] < breakout["open"]
    )

    bearish_entry = (
        entry["close"] < entry["open"]
        and entry["close"] < support
        and price < ema
    )

    extension = support - entry["close"]
    not_chasing = extension >= 0 and extension <= atr * STRICT_MAX_EXTENSION_ATR

    if breakout_down and bearish_entry and not_chasing:
        sl_reference = round(support + sl_buffer, 2)
        tp_reference = round(entry["close"] - target_distance, 2)

        if sl_reference <= entry["close"]:
            return None

        if tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=90,
            breakout_body=breakout_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "STRICT",
            "entry_model": "STRICT_BREAKDOWN_CONTINUATION",
            "pattern_height": target_distance,
            "breakout_level": support,
            "support": support,
            "resistance": resistance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "STRICT_RANGE_EXTENSION",
            "momentum": "bearish_strict_breakdown",
            "direction_context": "price_below_ema",
            "reason": (
                f"Strict SELL breakdown -> support {round(support, 2)} broken -> "
                f"strong breakout body {round(breakout_body, 2)} -> "
                f"SL above breakdown level {sl_reference} -> "
                f"TP strict extension {tp_reference} -> price below EMA"
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

