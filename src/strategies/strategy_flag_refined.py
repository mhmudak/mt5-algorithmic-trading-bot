import hashlib
from config.settings import ATR_MIN, ATR_MAX



PHASE6O2_OUTPUT_STANDARDIZED = True
PHASE6O2_STRATEGY_NAME = "FLAG_REFINED"
PHASE6O2_PHASE_NAME = "PHASE_6O2_EXISTING_FLAG_REFINED_STANDARDIZED"
PHASE6O2_MIN_SCORE = 94
PHASE6O2_SETUP_PREFIX = "FLAGR"

FLAG_REFINED_SL_ATR_MULTIPLIER = 0.20
FLAG_REFINED_MIN_SL_BUFFER = 2.0
FLAG_REFINED_MAX_SL_BUFFER = 5.0

FLAG_REFINED_MIN_POLE_ATR = 0.70
FLAG_REFINED_MIN_ENTRY_BODY_ATR = 0.25
FLAG_REFINED_MAX_EXTENSION_ATR = 0.80


def _sl_buffer(atr):
    return min(
        max(atr * FLAG_REFINED_SL_ATR_MULTIPLIER, FLAG_REFINED_MIN_SL_BUFFER),
        FLAG_REFINED_MAX_SL_BUFFER,
    )


def _score_setup(base_score, pole_body, entry_body, atr, close_aligned):
    score = base_score

    if pole_body > atr * 0.90:
        score += 2

    if pole_body > atr * 1.20:
        score += 2

    if entry_body > atr * 0.35:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def _generate_signal_raw(df):
    if len(df) < 20:
        return None

    # Structure:
    # - strong pole around -6
    # - 3-candle flag around -5, -4, -3
    # - confirmation candle at -2
    pole = df.iloc[-6]
    f1 = df.iloc[-5]
    f2 = df.iloc[-4]
    f3 = df.iloc[-3]
    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    pole_body = abs(pole["close"] - pole["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if pole_body < atr * FLAG_REFINED_MIN_POLE_ATR:
        return None

    if entry_body < atr * FLAG_REFINED_MIN_ENTRY_BODY_ATR:
        return None

    flag_high = max(f1["high"], f2["high"], f3["high"])
    flag_low = min(f1["low"], f2["low"], f3["low"])
    flag_height = flag_high - flag_low

    if flag_height <= 0:
        return None

    sl_buffer = _sl_buffer(atr)

    recent = df.iloc[-20:-6]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    # =========================
    # Descending flag -> bullish continuation
    # =========================
    bullish_pole = pole["close"] > pole["open"]

    descending_flag = (
        f1["high"] >= f2["high"] >= f3["high"]
        and f1["low"] >= f2["low"] >= f3["low"]
    )

    breakout_distance = entry["close"] - flag_high

    bullish_break = (
        entry["close"] > entry["open"]
        and entry["close"] > flag_high
        and price > ema
        and breakout_distance >= 0
        and breakout_distance <= atr * FLAG_REFINED_MAX_EXTENSION_ATR
    )

    if bullish_pole and descending_flag and bullish_break:
        measured_move = entry["close"] + max(pole_body, flag_height * 2, atr * 1.5)

        if recent_high > entry["close"]:
            tp_reference = max(recent_high, measured_move)
            target_model = "RECENT_HIGH_OR_MEASURED_FLAG_MOVE"
        else:
            tp_reference = measured_move
            target_model = "MEASURED_FLAG_MOVE"

        sl_reference = round(flag_low - sl_buffer, 2)
        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=84,
            pole_body=pole_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "FLAG_REFINED",
            "entry_model": "REFINED_FLAG_BREAKOUT_CONTINUATION",
            "pattern_height": max(pole_body, flag_height),
            "flag_high": flag_high,
            "flag_low": flag_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_flag_breakout",
            "direction_context": "price_above_ema",
            "reason": (
                f"Descending flag bullish continuation -> strong pole near {round(pole['close'], 2)} -> "
                f"flag range {round(flag_low, 2)} to {round(flag_high, 2)} -> "
                f"breakout above {round(flag_high, 2)} -> "
                f"SL below flag low {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # Ascending flag -> bearish continuation
    # =========================
    bearish_pole = pole["close"] < pole["open"]

    ascending_flag = (
        f1["high"] <= f2["high"] <= f3["high"]
        and f1["low"] <= f2["low"] <= f3["low"]
    )

    breakdown_distance = flag_low - entry["close"]

    bearish_break = (
        entry["close"] < entry["open"]
        and entry["close"] < flag_low
        and price < ema
        and breakdown_distance >= 0
        and breakdown_distance <= atr * FLAG_REFINED_MAX_EXTENSION_ATR
    )

    if bearish_pole and ascending_flag and bearish_break:
        measured_move = entry["close"] - max(pole_body, flag_height * 2, atr * 1.5)

        if recent_low < entry["close"]:
            tp_reference = min(recent_low, measured_move)
            target_model = "RECENT_LOW_OR_MEASURED_FLAG_MOVE"
        else:
            tp_reference = measured_move
            target_model = "MEASURED_FLAG_MOVE"

        sl_reference = round(flag_high + sl_buffer, 2)
        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=84,
            pole_body=pole_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "FLAG_REFINED",
            "entry_model": "REFINED_FLAG_BREAKDOWN_CONTINUATION",
            "pattern_height": max(pole_body, flag_height),
            "flag_high": flag_high,
            "flag_low": flag_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_flag_breakdown",
            "direction_context": "price_below_ema",
            "reason": (
                f"Ascending flag bearish continuation -> strong pole near {round(pole['close'], 2)} -> "
                f"flag range {round(flag_low, 2)} to {round(flag_high, 2)} -> "
                f"breakdown below {round(flag_low, 2)} -> "
                f"SL above flag high {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
            ),
        }

    return None


def _phase6o2_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _phase6o2_entry_reference(df, payload):
    for key in ("entry_reference", "entry_price", "entry", "price"):
        value = _phase6o2_float(payload.get(key))

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


def _phase6o2_risk_reward(signal, entry_reference, sl_reference, tp_reference):
    entry_reference = _phase6o2_float(entry_reference)
    sl_reference = _phase6o2_float(sl_reference)
    tp_reference = _phase6o2_float(tp_reference)

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


def _phase6o2_setup_id(payload, entry_reference):
    signal = payload.get("signal", "NA")
    entry_model = payload.get("entry_model", "NA")
    sl_reference = payload.get("sl_reference", "")
    tp_reference = payload.get("tp_reference", "")
    pattern_height = payload.get("pattern_height", "")

    raw = (
        f"{PHASE6O2_STRATEGY_NAME}:{signal}:{entry_model}:"
        f"{round(float(entry_reference), 2)}:{sl_reference}:{tp_reference}:{pattern_height}"
    )
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]

    return f"{PHASE6O2_SETUP_PREFIX}-{signal}-{digest}"


def _phase6o2_standardize_signal(payload, df):
    if not payload:
        return payload

    signal = payload.get("signal")
    entry_reference = _phase6o2_entry_reference(df, payload)

    if entry_reference is None:
        return payload

    rr = _phase6o2_risk_reward(
        signal=signal,
        entry_reference=entry_reference,
        sl_reference=payload.get("sl_reference"),
        tp_reference=payload.get("tp_reference"),
    )

    payload.setdefault("phase", PHASE6O2_PHASE_NAME)
    payload.setdefault("strategy", PHASE6O2_STRATEGY_NAME)
    payload.setdefault("setup_id", _phase6o2_setup_id(payload, entry_reference))
    payload.setdefault("entry_reference", round(float(entry_reference), 2))
    payload.setdefault("min_required_score", PHASE6O2_MIN_SCORE)

    if rr is not None:
        payload.setdefault("rr", rr)
        payload.setdefault("risk_reward", rr)

    payload.setdefault("auto_trade_allowed", True)
    payload.setdefault("decision_impact", "MAIN_BOT_RUNTIME_CONTROLLED")
    payload.setdefault("duplicate_policy", "setup_id_by_entry_model_entry_sl_tp_pattern_height")
    payload.setdefault("orderflow_status", "NOT_REQUIRED_FOR_EXISTING_CHART_PATTERN")

    return payload


def generate_signal(df):
    return _phase6o2_standardize_signal(_generate_signal_raw(df), df)

