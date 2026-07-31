import hashlib
from config.settings import ATR_MIN, ATR_MAX



PHASE6P3B_SMC_LIQUIDITY_STANDARDIZATION = True
PHASE6P3B_STRATEGY_NAME = "BREAKER_BLOCK"
PHASE6P3B_FALLBACK_PHASE_NAME = "PHASE_6P3B_BREAKER_BLOCK_STANDARDIZED_COMPLETION"
PHASE6P3B_SETUP_PREFIX = "BRK"
PHASE6P3B_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

BREAKER_LOOKBACK = 35

BREAKER_MIN_DISPLACEMENT_ATR = 0.35
BREAKER_MIN_REACTION_BODY_ATR = 0.20

BREAKER_RETEST_ATR_BUFFER = 0.30
BREAKER_MIN_RETEST_BUFFER = 1.0

BREAKER_SL_ATR_MULTIPLIER = 0.20
BREAKER_MIN_SL_BUFFER = 2.0
BREAKER_MAX_SL_BUFFER = 5.0

# Dynamic max risk cap:
# not blind fixed 18; it adapts to ATR but stays bounded.
BREAKER_MIN_MAX_RISK = 12.0
BREAKER_MAX_MAX_RISK = 18.0
BREAKER_MAX_RISK_ATR_MULTIPLIER = 1.5

BREAKER_TARGET_ATR_MIN = 1.5
BREAKER_TARGET_ATR_MAX = 3.0


def _sl_buffer(atr):
    return min(
        max(atr * BREAKER_SL_ATR_MULTIPLIER, BREAKER_MIN_SL_BUFFER),
        BREAKER_MAX_SL_BUFFER,
    )


def _max_allowed_risk(atr):
    return max(
        BREAKER_MIN_MAX_RISK,
        min(BREAKER_MAX_MAX_RISK, atr * BREAKER_MAX_RISK_ATR_MULTIPLIER),
    )


def _target_distance(atr, zone_height, structure_range):
    return min(
        max(zone_height * 2, structure_range * 0.50, atr * BREAKER_TARGET_ATR_MIN),
        atr * BREAKER_TARGET_ATR_MAX,
    )


def _choose_buy_sl(entry_price, zone_low, retest_low, sl_buffer, max_risk):
    full_structure_sl = round(zone_low - sl_buffer, 2)
    retest_structure_sl = round(retest_low - sl_buffer, 2)

    full_risk = entry_price - full_structure_sl
    retest_risk = entry_price - retest_structure_sl

    if full_structure_sl < entry_price and full_risk <= max_risk:
        return full_structure_sl, "FULL_BREAKER_STRUCTURE_SL", full_risk

    if retest_structure_sl < entry_price and retest_risk <= max_risk:
        return retest_structure_sl, "RETEST_CANDLE_STRUCTURE_SL", retest_risk

    return None, "SL_TOO_WIDE_SKIP", None


def _choose_sell_sl(entry_price, zone_high, retest_high, sl_buffer, max_risk):
    full_structure_sl = round(zone_high + sl_buffer, 2)
    retest_structure_sl = round(retest_high + sl_buffer, 2)

    full_risk = full_structure_sl - entry_price
    retest_risk = retest_structure_sl - entry_price

    if full_structure_sl > entry_price and full_risk <= max_risk:
        return full_structure_sl, "FULL_BREAKER_STRUCTURE_SL", full_risk

    if retest_structure_sl > entry_price and retest_risk <= max_risk:
        return retest_structure_sl, "RETEST_CANDLE_STRUCTURE_SL", retest_risk

    return None, "SL_TOO_WIDE_SKIP", None


def _score_setup(base_score, displacement_body, reaction_body, atr, clean_retest, close_aligned, sl_model):
    score = base_score

    if displacement_body > atr * 0.50:
        score += 2

    if displacement_body > atr * 0.75:
        score += 2

    if reaction_body > atr * 0.30:
        score += 2

    if clean_retest:
        score += 2

    if close_aligned:
        score += 2

    # Full structure SL is more robust than tight retest SL.
    if sl_model == "FULL_BREAKER_STRUCTURE_SL":
        score += 1

    return min(score, 99)


def _phase6p3b_generate_signal_raw(df):
    if len(df) < BREAKER_LOOKBACK + 5:
        return None

    # Closed candles only
    zone_candle = df.iloc[-5]     # former zone / block candle
    break_candle = df.iloc[-4]    # displacement candle breaking the zone
    retest_candle = df.iloc[-3]   # first return toward zone
    entry = df.iloc[-2]           # rejection / confirmation candle

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    displacement_body = abs(break_candle["close"] - break_candle["open"])
    reaction_body = abs(entry["close"] - entry["open"])
    entry_range = entry["high"] - entry["low"]

    if displacement_body <= 0 or reaction_body <= 0 or entry_range <= 0:
        return None

    if displacement_body < atr * BREAKER_MIN_DISPLACEMENT_ATR:
        return None

    if reaction_body < atr * BREAKER_MIN_REACTION_BODY_ATR:
        return None

    zone_high = max(zone_candle["open"], zone_candle["close"], zone_candle["high"])
    zone_low = min(zone_candle["open"], zone_candle["close"], zone_candle["low"])
    zone_height = zone_high - zone_low

    if zone_height <= 0:
        return None

    recent = df.iloc[-BREAKER_LOOKBACK:-5]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()
    structure_range = recent_high - recent_low

    if structure_range <= 0:
        return None

    retest_buffer = max(atr * BREAKER_RETEST_ATR_BUFFER, BREAKER_MIN_RETEST_BUFFER)
    sl_buffer = _sl_buffer(atr)
    max_risk = _max_allowed_risk(atr)
    target_distance = _target_distance(atr, zone_height, structure_range)

    # =========================
    # BUY breaker block
    # Former resistance/supply zone breaks upward, then acts as support
    # =========================
    bullish_break = (
        break_candle["close"] > zone_high
        and break_candle["close"] > break_candle["open"]
    )

    retest_zone_from_above = (
        retest_candle["low"] <= zone_high + retest_buffer
        or entry["low"] <= zone_high + retest_buffer
    )

    bullish_reclaim = (
        entry["close"] > entry["open"]
        and entry["close"] > zone_high
        and price > ema
        and entry["close"] >= entry["low"] + entry_range * 0.60
    )

    if bullish_break and retest_zone_from_above and bullish_reclaim:
        entry_price = entry["close"]

        sl_reference, sl_model, sl_risk = _choose_buy_sl(
            entry_price=entry_price,
            zone_low=zone_low,
            retest_low=min(entry["low"], retest_candle["low"]),
            sl_buffer=sl_buffer,
            max_risk=max_risk,
        )

        if sl_reference is None:
            return None

        if recent_high > entry_price:
            tp_reference = recent_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = entry_price + target_distance
            target_model = "BREAKER_MEASURED_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if tp_reference <= entry_price:
            return None

        score = _score_setup(
            base_score=93,
            displacement_body=displacement_body,
            reaction_body=reaction_body,
            atr=atr,
            clean_retest=retest_zone_from_above,
            close_aligned=price > ema,
            sl_model=sl_model,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "BREAKER_BLOCK",
            "entry_model": "BULLISH_BREAKER_RETEST",
            "pattern_height": target_distance,
            "zone_high": zone_high,
            "zone_low": zone_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "sl_model": sl_model,
            "sl_risk": round(sl_risk, 2),
            "max_allowed_risk": round(max_risk, 2),
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_breaker_retest_reclaim",
            "direction_context": "price_above_ema",
            "reason": (
                f"Bullish breaker block -> zone {round(zone_low, 2)}-{round(zone_high, 2)} "
                f"broken upward then retested -> "
                f"SL {sl_model} {sl_reference} risk={round(sl_risk, 2)} max={round(max_risk, 2)} -> "
                f"TP {target_model} {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # SELL breaker block
    # Former support/demand zone breaks downward, then acts as resistance
    # =========================
    bearish_break = (
        break_candle["close"] < zone_low
        and break_candle["close"] < break_candle["open"]
    )

    retest_zone_from_below = (
        retest_candle["high"] >= zone_low - retest_buffer
        or entry["high"] >= zone_low - retest_buffer
    )

    bearish_reject = (
        entry["close"] < entry["open"]
        and entry["close"] < zone_low
        and price < ema
        and entry["close"] <= entry["high"] - entry_range * 0.60
    )

    if bearish_break and retest_zone_from_below and bearish_reject:
        entry_price = entry["close"]

        sl_reference, sl_model, sl_risk = _choose_sell_sl(
            entry_price=entry_price,
            zone_high=zone_high,
            retest_high=max(entry["high"], retest_candle["high"]),
            sl_buffer=sl_buffer,
            max_risk=max_risk,
        )

        if sl_reference is None:
            return None

        if recent_low < entry_price:
            tp_reference = recent_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = entry_price - target_distance
            target_model = "BREAKER_MEASURED_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if tp_reference >= entry_price:
            return None

        score = _score_setup(
            base_score=93,
            displacement_body=displacement_body,
            reaction_body=reaction_body,
            atr=atr,
            clean_retest=retest_zone_from_below,
            close_aligned=price < ema,
            sl_model=sl_model,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "BREAKER_BLOCK",
            "entry_model": "BEARISH_BREAKER_RETEST",
            "pattern_height": target_distance,
            "zone_high": zone_high,
            "zone_low": zone_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "sl_model": sl_model,
            "sl_risk": round(sl_risk, 2),
            "max_allowed_risk": round(max_risk, 2),
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_breaker_retest_rejection",
            "direction_context": "price_below_ema",
            "reason": (
                f"Bearish breaker block -> zone {round(zone_low, 2)}-{round(zone_high, 2)} "
                f"broken downward then retested -> "
                f"SL {sl_model} {sl_reference} risk={round(sl_risk, 2)} max={round(max_risk, 2)} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
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

