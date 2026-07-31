import hashlib
from config.settings import ATR_MIN, ATR_MAX



PHASE6P3B_SMC_LIQUIDITY_STANDARDIZATION = True
PHASE6P3B_STRATEGY_NAME = "FVG"
PHASE6P3B_FALLBACK_PHASE_NAME = "PHASE_6P3B_FVG_STANDARDIZED_COMPLETION"
PHASE6P3B_SETUP_PREFIX = "FVG"
PHASE6P3B_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

FVG_SL_ATR_MULTIPLIER = 0.15
FVG_MIN_SL_BUFFER = 1.0
FVG_MAX_SL_BUFFER = 4.0


def _sl_buffer(atr):
    return min(
        max(atr * FVG_SL_ATR_MULTIPLIER, FVG_MIN_SL_BUFFER),
        FVG_MAX_SL_BUFFER,
    )


def _score_setup(base_score, displacement_body, reaction_body, atr, close_aligned):
    score = base_score

    if displacement_body > atr * 0.50:
        score += 2

    if displacement_body > atr * 0.70:
        score += 2

    if reaction_body > atr * 0.30:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def _phase6p3b_generate_signal_raw(df):
    if len(df) < 30:
        return None

    # candles
    c1 = df.iloc[-4]  # origin candle before imbalance
    c2 = df.iloc[-3]  # displacement candle
    c3 = df.iloc[-2]  # reaction / entry candle

    atr = c3["atr_14"]
    ema = c3["ema_20"]
    price = c3["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body_c2 = abs(c2["close"] - c2["open"])
    body_c3 = abs(c3["close"] - c3["open"])

    if body_c2 <= 0 or body_c3 <= 0:
        return None

    structure = df.iloc[-24:-4]
    recent_high = structure["high"].max()
    recent_low = structure["low"].min()

    sl_buffer = _sl_buffer(atr)

    # =========================================================
    # BULLISH FVG
    # =========================================================
    bullish_gap_exists = c1["high"] < c3["low"]
    fvg_top = c3["low"]
    fvg_bottom = c1["high"]
    gap_size = fvg_top - fvg_bottom

    bullish_displacement = (
        c2["close"] > c2["open"]
        and body_c2 > atr * 0.35
        and c2["close"] > c1["high"]
    )

    bullish_context = price > ema

    in_fvg_zone = (
        c3["low"] <= fvg_top
        and c3["high"] >= fvg_bottom
    )

    reaction = (
        c3["low"] <= fvg_top
        and c3["close"] > c3["open"]
        and body_c3 > atr * 0.20
    )

    extension = abs(c3["close"] - fvg_top)
    if extension > atr * 0.50:
        return None

    weak_structure = c3["close"] < fvg_bottom

    if (
        bullish_gap_exists
        and gap_size > atr * 0.15
        and bullish_displacement
        and bullish_context
        and in_fvg_zone
        and reaction
        and not weak_structure
    ):
        sl_reference = round(fvg_bottom - sl_buffer, 2)

        if recent_high > c3["close"]:
            tp_reference = recent_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = c3["close"] + max(gap_size * 2, atr * 1.2)
            target_model = "MEASURED_FVG_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=90,
            displacement_body=body_c2,
            reaction_body=body_c3,
            atr=atr,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "FVG",
            "entry_model": "FVG_RETRACE_REACTION",
            "pattern_height": gap_size,
            "fvg_top": fvg_top,
            "fvg_bottom": fvg_bottom,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_displacement_reaction",
            "direction_context": "price_above_ema",
            "reason": (
                f"Bullish FVG -> retrace into gap "
                f"{round(fvg_bottom, 2)}-{round(fvg_top, 2)} -> "
                f"reaction confirmed -> SL below FVG {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> EMA aligned"
            ),
        }

    # =========================================================
    # BEARISH FVG
    # =========================================================
    bearish_gap_exists = c1["low"] > c3["high"]
    fvg_top = c1["low"]
    fvg_bottom = c3["high"]
    gap_size = fvg_top - fvg_bottom

    bearish_displacement = (
        c2["close"] < c2["open"]
        and body_c2 > atr * 0.35
        and c2["close"] < c1["low"]
    )

    bearish_context = price < ema

    in_fvg_zone = (
        c3["high"] >= fvg_bottom
        and c3["low"] <= fvg_top
    )

    reaction = (
        c3["high"] >= fvg_bottom
        and c3["close"] < c3["open"]
        and body_c3 > atr * 0.20
    )

    extension = abs(c3["close"] - fvg_bottom)
    if extension > atr * 0.50:
        return None

    weak_structure = c3["close"] > fvg_top

    if (
        bearish_gap_exists
        and gap_size > atr * 0.15
        and bearish_displacement
        and bearish_context
        and in_fvg_zone
        and reaction
        and not weak_structure
    ):
        sl_reference = round(fvg_top + sl_buffer, 2)

        if recent_low < c3["close"]:
            tp_reference = recent_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = c3["close"] - max(gap_size * 2, atr * 1.2)
            target_model = "MEASURED_FVG_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=90,
            displacement_body=body_c2,
            reaction_body=body_c3,
            atr=atr,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "FVG",
            "entry_model": "FVG_RETRACE_REACTION",
            "pattern_height": gap_size,
            "fvg_top": fvg_top,
            "fvg_bottom": fvg_bottom,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_displacement_reaction",
            "direction_context": "price_below_ema",
            "reason": (
                f"Bearish FVG -> retrace into gap "
                f"{round(fvg_bottom, 2)}-{round(fvg_top, 2)} -> "
                f"reaction confirmed -> SL above FVG {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> EMA aligned"
            ),
        }

    return None


def _phase6p3b_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _phase6p3b_entry_reference(df, payload):
    for key in ("entry_reference", "entry_price", "entry", "price"):
        value = _phase6p3b_float(payload.get(key))

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


def _phase6p3b_risk_reward(signal, entry_reference, sl_reference, tp_reference):
    entry_reference = _phase6p3b_float(entry_reference)
    sl_reference = _phase6p3b_float(sl_reference)
    tp_reference = _phase6p3b_float(tp_reference)

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


def _phase6p3b_setup_id(payload, entry_reference):
    signal = payload.get("signal", "NA")
    entry_model = payload.get("entry_model", payload.get("type", "NA"))
    sl_reference = payload.get("sl_reference", payload.get("stop_loss", ""))
    tp_reference = payload.get("tp_reference", payload.get("take_profit", ""))

    raw = (
        f"{PHASE6P3B_STRATEGY_NAME}:{signal}:{entry_model}:"
        f"{round(float(entry_reference), 2)}:{sl_reference}:{tp_reference}"
    )
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]

    return f"{PHASE6P3B_SETUP_PREFIX}-{signal}-{digest}"


def _phase6p3b_standardize_signal(payload, df):
    if not payload:
        return payload

    signal = payload.get("signal")
    entry_reference = _phase6p3b_entry_reference(df, payload)

    if entry_reference is None:
        return payload

    existing_rr = _phase6p3b_float(payload.get("rr"))
    existing_risk_reward = _phase6p3b_float(payload.get("risk_reward"))

    computed_rr = _phase6p3b_risk_reward(
        signal=signal,
        entry_reference=entry_reference,
        sl_reference=payload.get("sl_reference", payload.get("stop_loss")),
        tp_reference=payload.get("tp_reference", payload.get("take_profit")),
    )

    final_rr = existing_rr if existing_rr is not None else existing_risk_reward
    final_rr = final_rr if final_rr is not None else computed_rr

    payload.setdefault("strategy", PHASE6P3B_STRATEGY_NAME)
    payload.setdefault("phase", PHASE6P3B_FALLBACK_PHASE_NAME)
    payload.setdefault("setup_id", _phase6p3b_setup_id(payload, entry_reference))
    payload.setdefault("entry_reference", round(float(entry_reference), 2))

    if final_rr is not None:
        payload.setdefault("rr", final_rr)
        payload.setdefault("risk_reward", final_rr)

    payload.setdefault("auto_trade_allowed", True)
    payload.setdefault("decision_impact", "MAIN_BOT_RUNTIME_CONTROLLED")
    payload.setdefault("duplicate_policy", PHASE6P3B_DUPLICATE_POLICY)

    return payload


def generate_signal(df):
    return _phase6p3b_standardize_signal(_phase6p3b_generate_signal_raw(df), df)

