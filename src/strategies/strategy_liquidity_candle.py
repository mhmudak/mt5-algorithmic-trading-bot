import hashlib
from config.settings import ATR_MIN, ATR_MAX



PHASE6P3C_REMAINING_LEGACY_STANDARDIZATION = True
PHASE6P3C_STRATEGY_NAME = "LIQUIDITY_CANDLE"
PHASE6P3C_FALLBACK_PHASE_NAME = "PHASE_6P3C_LIQUIDITY_CANDLE_STANDARDIZED_COMPLETION"
PHASE6P3C_SETUP_PREFIX = "LC"
PHASE6P3C_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

LIQUIDITY_CANDLE_SL_ATR_MULTIPLIER = 0.20
LIQUIDITY_CANDLE_MIN_SL_BUFFER = 2.0
LIQUIDITY_CANDLE_MAX_SL_BUFFER = 5.0


def _sl_buffer(atr):
    return min(
        max(atr * LIQUIDITY_CANDLE_SL_ATR_MULTIPLIER, LIQUIDITY_CANDLE_MIN_SL_BUFFER),
        LIQUIDITY_CANDLE_MAX_SL_BUFFER,
    )


def _score_setup(base_score, entry_body, atr, breakout_strength, close_aligned):
    score = base_score

    if entry_body > atr * 0.30:
        score += 2

    if entry_body > atr * 0.50:
        score += 2

    if breakout_strength > atr * 0.20:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def _phase6p3c_generate_signal_raw(df):
    if len(df) < 30:
        return None

    # candles
    entry = df.iloc[-2]
    liquidity = df.iloc[-3]
    prev = df.iloc[-4]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    # basic measures
    liquidity_range = liquidity["high"] - liquidity["low"]
    liquidity_body = abs(liquidity["close"] - liquidity["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if liquidity_range <= 0 or entry_body <= 0:
        return None

    upper_wick = liquidity["high"] - max(liquidity["open"], liquidity["close"])
    lower_wick = min(liquidity["open"], liquidity["close"]) - liquidity["low"]

    structure = df.iloc[-24:-4]
    recent_high = structure["high"].max()
    recent_low = structure["low"].min()

    sl_buffer = _sl_buffer(atr)

    # =========================================================
    # ANTI LATE ENTRY FILTER
    # =========================================================
    extension_up = abs(entry["close"] - liquidity["high"])
    extension_down = abs(entry["close"] - liquidity["low"])

    if extension_up > atr * 0.60 or extension_down > atr * 0.60:
        return None

    # =========================================================
    # BREAKOUT STRENGTH FILTER
    # =========================================================
    breakout_up_strength = entry["close"] - liquidity["high"]
    breakout_down_strength = liquidity["low"] - entry["close"]

    # =========================================================
    # SMT-LIKE BEHAVIOR
    # =========================================================
    failed_continuation_up = (
        prev["high"] < liquidity["high"]
        and entry["close"] < liquidity["high"] + atr * 0.05
    )

    failed_continuation_down = (
        prev["low"] > liquidity["low"]
        and entry["close"] > liquidity["low"] - atr * 0.05
    )

    # =========================================================
    # BULLISH SETUP
    # =========================================================
    bullish_liquidity = (
        lower_wick > liquidity_body * 1.5
        and liquidity_range > atr * 0.60
    )

    bullish_confirmation = (
        entry["close"] > entry["open"]
        and entry["close"] > liquidity["high"]
        and price > ema
        and entry_body > atr * 0.20
        and breakout_up_strength > atr * 0.10
        and not failed_continuation_up
    )

    if bullish_liquidity and bullish_confirmation:
        risk_height = entry["close"] - liquidity["low"]

        if risk_height <= 0:
            return None

        sl_reference = round(liquidity["low"] - sl_buffer, 2)

        if recent_high > entry["close"]:
            tp_reference = recent_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = entry["close"] + max(risk_height * 1.5, atr * 1.5)
            target_model = "MEASURED_LIQUIDITY_CANDLE_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=90,
            entry_body=entry_body,
            atr=atr,
            breakout_strength=breakout_up_strength,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "LIQUIDITY_CANDLE",
            "entry_model": "LIQUIDITY_CANDLE_BREAKOUT_RECLAIM",
            "pattern_height": risk_height,
            "liquidity_high": liquidity["high"],
            "liquidity_low": liquidity["low"],
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_liquidity_reclaim",
            "direction_context": "price_above_ema",
            "reason": (
                f"Bullish liquidity candle -> strong rejection from "
                f"{round(liquidity['low'], 2)} -> validated breakout above "
                f"{round(liquidity['high'], 2)} -> SL below liquidity low "
                f"{sl_reference} -> TP {target_model} {tp_reference} -> EMA aligned"
            ),
        }

    # =========================================================
    # BEARISH SETUP
    # =========================================================
    bearish_liquidity = (
        upper_wick > liquidity_body * 1.5
        and liquidity_range > atr * 0.60
    )

    bearish_confirmation = (
        entry["close"] < entry["open"]
        and entry["close"] < liquidity["low"]
        and price < ema
        and entry_body > atr * 0.20
        and breakout_down_strength > atr * 0.10
        and not failed_continuation_down
    )

    if bearish_liquidity and bearish_confirmation:
        risk_height = liquidity["high"] - entry["close"]

        if risk_height <= 0:
            return None

        sl_reference = round(liquidity["high"] + sl_buffer, 2)

        if recent_low < entry["close"]:
            tp_reference = recent_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = entry["close"] - max(risk_height * 1.5, atr * 1.5)
            target_model = "MEASURED_LIQUIDITY_CANDLE_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=90,
            entry_body=entry_body,
            atr=atr,
            breakout_strength=breakout_down_strength,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "LIQUIDITY_CANDLE",
            "entry_model": "LIQUIDITY_CANDLE_BREAKDOWN_RECLAIM",
            "pattern_height": risk_height,
            "liquidity_high": liquidity["high"],
            "liquidity_low": liquidity["low"],
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_liquidity_reclaim",
            "direction_context": "price_below_ema",
            "reason": (
                f"Bearish liquidity candle -> strong rejection from "
                f"{round(liquidity['high'], 2)} -> validated breakdown below "
                f"{round(liquidity['low'], 2)} -> SL above liquidity high "
                f"{sl_reference} -> TP {target_model} {tp_reference} -> EMA aligned"
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

