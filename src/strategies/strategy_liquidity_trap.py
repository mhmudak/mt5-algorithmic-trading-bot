import hashlib
from config.settings import ATR_MIN, ATR_MAX



PHASE6P3B_SMC_LIQUIDITY_STANDARDIZATION = True
PHASE6P3B_STRATEGY_NAME = "LIQUIDITY_TRAP"
PHASE6P3B_FALLBACK_PHASE_NAME = "PHASE_6P3B_LIQUIDITY_TRAP_STANDARDIZED_COMPLETION"
PHASE6P3B_SETUP_PREFIX = "LTRAP"
PHASE6P3B_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

LIQUIDITY_TRAP_SL_ATR_MULTIPLIER = 0.20
LIQUIDITY_TRAP_MIN_SL_BUFFER = 2.0
LIQUIDITY_TRAP_MAX_SL_BUFFER = 5.0


def _sl_buffer(atr):
    return min(
        max(atr * LIQUIDITY_TRAP_SL_ATR_MULTIPLIER, LIQUIDITY_TRAP_MIN_SL_BUFFER),
        LIQUIDITY_TRAP_MAX_SL_BUFFER,
    )


def _score_setup(base_score, confirm_body, atr, wick_strength, close_aligned):
    score = base_score

    if confirm_body > atr * 0.35:
        score += 2

    if confirm_body > atr * 0.50:
        score += 2

    if wick_strength:
        score += 2

    if close_aligned:
        score += 1

    return min(score, 99)


def _phase6p3b_generate_signal_raw(df):
    if len(df) < 35:
        return None

    trap = df.iloc[-3]
    confirm = df.iloc[-2]

    atr = confirm["atr_14"]
    ema = confirm["ema_20"]
    price = confirm["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    recent = df.iloc[-18:-3]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()
    pattern_height = abs(recent_high - recent_low)

    if pattern_height <= 0:
        return None

    trap_body = abs(trap["close"] - trap["open"])
    trap_range = trap["high"] - trap["low"]
    confirm_body = abs(confirm["close"] - confirm["open"])

    if trap_range <= 0:
        return None

    upper_wick = trap["high"] - max(trap["open"], trap["close"])
    lower_wick = min(trap["open"], trap["close"]) - trap["low"]

    sl_buffer = _sl_buffer(atr)

    # =========================================================
    # Bearish liquidity trap
    # take highs -> fail -> confirm down
    # =========================================================
    took_highs = trap["high"] > recent_high
    failed_breakout = trap["close"] < recent_high
    upper_rejection = upper_wick > trap_body * 1.2

    bearish_confirmation = (
        confirm["close"] < confirm["open"]
        and confirm["close"] < trap["low"]
        and confirm_body > atr * 0.25
        and price < ema
    )

    if (
        took_highs
        and failed_breakout
        and upper_rejection
        and bearish_confirmation
    ):
        sl_reference = round(trap["high"] + sl_buffer, 2)

        # Prefer the opposite side of the range.
        # If price is already below it, use measured move fallback.
        if recent_low < confirm["close"]:
            tp_reference = recent_low
            target_model = "OPPOSITE_RANGE_LOW"
        else:
            tp_reference = confirm["close"] - pattern_height
            target_model = "MEASURED_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=94,
            confirm_body=confirm_body,
            atr=atr,
            wick_strength=upper_wick > trap_body * 1.8,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "LIQUIDITY_TRAP",
            "entry_model": "LIQUIDITY_TRAP_REVERSAL",
            "pattern_height": pattern_height,
            "trap_high": trap["high"],
            "trap_low": trap["low"],
            "range_high": recent_high,
            "range_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_trap_confirmation",
            "direction_context": "price_below_ema",
            "reason": (
                f"Liquidity trap bearish -> highs above {round(recent_high, 2)} taken -> "
                f"failed breakout -> bearish confirmation below {round(trap['low'], 2)} -> "
                f"SL above trap high {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
            ),
        }

    # =========================================================
    # Bullish liquidity trap
    # take lows -> fail -> confirm up
    # =========================================================
    took_lows = trap["low"] < recent_low
    failed_breakdown = trap["close"] > recent_low
    lower_rejection = lower_wick > trap_body * 1.2

    bullish_confirmation = (
        confirm["close"] > confirm["open"]
        and confirm["close"] > trap["high"]
        and confirm_body > atr * 0.25
        and price > ema
    )

    if (
        took_lows
        and failed_breakdown
        and lower_rejection
        and bullish_confirmation
    ):
        sl_reference = round(trap["low"] - sl_buffer, 2)

        # Prefer the opposite side of the range.
        # If price is already above it, use measured move fallback.
        if recent_high > confirm["close"]:
            tp_reference = recent_high
            target_model = "OPPOSITE_RANGE_HIGH"
        else:
            tp_reference = confirm["close"] + pattern_height
            target_model = "MEASURED_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=94,
            confirm_body=confirm_body,
            atr=atr,
            wick_strength=lower_wick > trap_body * 1.8,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "LIQUIDITY_TRAP",
            "entry_model": "LIQUIDITY_TRAP_REVERSAL",
            "pattern_height": pattern_height,
            "trap_high": trap["high"],
            "trap_low": trap["low"],
            "range_high": recent_high,
            "range_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_trap_confirmation",
            "direction_context": "price_above_ema",
            "reason": (
                f"Liquidity trap bullish -> lows below {round(recent_low, 2)} taken -> "
                f"failed breakdown -> bullish confirmation above {round(trap['high'], 2)} -> "
                f"SL below trap low {sl_reference} -> "
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

