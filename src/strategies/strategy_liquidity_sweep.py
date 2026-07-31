import hashlib
from config.settings import (
    ATR_MIN,
    ATR_MAX,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
)



PHASE6P3B_SMC_LIQUIDITY_STANDARDIZATION = True
PHASE6P3B_STRATEGY_NAME = "LIQUIDITY_SWEEP"
PHASE6P3B_FALLBACK_PHASE_NAME = "PHASE_6P3B_LIQUIDITY_SWEEP_STANDARDIZED_COMPLETION"
PHASE6P3B_SETUP_PREFIX = "LSW"
PHASE6P3B_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

LIQUIDITY_SWEEP_SL_ATR_MULTIPLIER = 0.20
LIQUIDITY_SWEEP_MIN_SL_BUFFER = 2.0
LIQUIDITY_SWEEP_MAX_SL_BUFFER = 5.0


def _sl_buffer(atr):
    return min(
        max(atr * LIQUIDITY_SWEEP_SL_ATR_MULTIPLIER, LIQUIDITY_SWEEP_MIN_SL_BUFFER),
        LIQUIDITY_SWEEP_MAX_SL_BUFFER,
    )


def _score_setup(base_score, conf_body, atr, wick_strength, close_aligned):
    score = base_score

    if conf_body > atr * 0.40:
        score += 2

    if conf_body > atr * 0.60:
        score += 2

    if wick_strength:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def _phase6p3b_generate_signal_raw(df):
    if len(df) < BREAKOUT_LOOKBACK + 8:
        return None

    confirmation = df.iloc[-2]
    sweep = df.iloc[-3]

    atr = confirmation["atr_14"]
    price = confirmation["close"]
    ema = confirmation["ema_20"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 5):-3]
    resistance = recent_data["high"].max()
    support = recent_data["low"].min()
    range_height = resistance - support

    if range_height <= 0:
        return None

    sweep_body = abs(sweep["close"] - sweep["open"])
    sweep_range = sweep["high"] - sweep["low"]
    conf_body = abs(confirmation["close"] - confirmation["open"])

    if sweep_range <= 0 or conf_body <= 0:
        return None

    upper_wick = sweep["high"] - max(sweep["open"], sweep["close"])
    lower_wick = min(sweep["open"], sweep["close"]) - sweep["low"]

    bullish_confirmation = confirmation["close"] > confirmation["open"]
    bearish_confirmation = confirmation["close"] < confirmation["open"]

    displacement = conf_body > atr * 0.30
    sl_buffer = _sl_buffer(atr)

    # =========================
    # SELL: sweep highs then reject
    # =========================
    if (
        sweep["high"] > resistance + BREAKOUT_BUFFER
        and sweep["close"] < resistance
        and upper_wick > sweep_body * 1.2
        and bearish_confirmation
        and displacement
        and confirmation["close"] < (sweep["open"] + sweep["close"]) / 2
        and price < ema
    ):
        sl_reference = round(sweep["high"] + sl_buffer, 2)

        if support < confirmation["close"]:
            tp_reference = support
            target_model = "OPPOSITE_RANGE_LOW"
        else:
            tp_reference = confirmation["close"] - max(range_height, atr * 1.5)
            target_model = "MEASURED_SWEEP_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=90,
            conf_body=conf_body,
            atr=atr,
            wick_strength=upper_wick > sweep_body * 1.8,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "LIQUIDITY_SWEEP",
            "entry_model": "LIQUIDITY_SWEEP_REVERSAL",
            "sweep_high": sweep["high"],
            "sweep_low": sweep["low"],
            "range_high": resistance,
            "range_low": support,
            "pattern_height": range_height,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_sweep_rejection",
            "direction_context": "price_below_ema",
            "reason": (
                f"ICT bearish liquidity sweep -> took highs above {round(resistance, 2)} -> "
                f"sweep high {round(sweep['high'], 2)} -> rejection confirmed -> "
                f"SL above sweep high {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
            ),
        }

    # =========================
    # BUY: sweep lows then reject
    # =========================
    if (
        sweep["low"] < support - BREAKOUT_BUFFER
        and sweep["close"] > support
        and lower_wick > sweep_body * 1.2
        and bullish_confirmation
        and displacement
        and confirmation["close"] > (sweep["open"] + sweep["close"]) / 2
        and price > ema
    ):
        sl_reference = round(sweep["low"] - sl_buffer, 2)

        if resistance > confirmation["close"]:
            tp_reference = resistance
            target_model = "OPPOSITE_RANGE_HIGH"
        else:
            tp_reference = confirmation["close"] + max(range_height, atr * 1.5)
            target_model = "MEASURED_SWEEP_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=90,
            conf_body=conf_body,
            atr=atr,
            wick_strength=lower_wick > sweep_body * 1.8,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "LIQUIDITY_SWEEP",
            "entry_model": "LIQUIDITY_SWEEP_REVERSAL",
            "sweep_high": sweep["high"],
            "sweep_low": sweep["low"],
            "range_high": resistance,
            "range_low": support,
            "pattern_height": range_height,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_sweep_rejection",
            "direction_context": "price_above_ema",
            "reason": (
                f"ICT bullish liquidity sweep -> took lows below {round(support, 2)} -> "
                f"sweep low {round(sweep['low'], 2)} -> rejection confirmed -> "
                f"SL below sweep low {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price above EMA"
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

