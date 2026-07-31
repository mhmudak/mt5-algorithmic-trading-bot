import hashlib
from config.settings import ATR_MIN, ATR_MAX



PHASE6P3B_SMC_LIQUIDITY_STANDARDIZATION = True
PHASE6P3B_STRATEGY_NAME = "ORDER_BLOCK"
PHASE6P3B_FALLBACK_PHASE_NAME = "PHASE_6P3B_ORDER_BLOCK_STANDARDIZED_COMPLETION"
PHASE6P3B_SETUP_PREFIX = "OB"
PHASE6P3B_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

ORDER_BLOCK_SL_ATR_MULTIPLIER = 0.20
ORDER_BLOCK_MIN_SL_BUFFER = 2.0
ORDER_BLOCK_MAX_SL_BUFFER = 5.0


def _sl_buffer(atr):
    return min(
        max(atr * ORDER_BLOCK_SL_ATR_MULTIPLIER, ORDER_BLOCK_MIN_SL_BUFFER),
        ORDER_BLOCK_MAX_SL_BUFFER,
    )


def _score_setup(base_score, trigger_body, entry_body, atr, close_aligned):
    score = base_score

    if trigger_body > atr * 0.60:
        score += 2

    if trigger_body > atr * 0.80:
        score += 2

    if entry_body > atr * 0.30:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def _phase6p3b_generate_signal_raw(df):
    if len(df) < 30:
        return None

    # Logic:
    # - detect displacement candle
    # - take the last opposite candle before displacement as order block
    # - require revisit / respect of zone
    # - confirmation on latest closed candle

    entry = df.iloc[-2]
    trigger = df.iloc[-3]
    ob_candle = df.iloc[-4]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    trigger_body = abs(trigger["close"] - trigger["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if trigger_body <= 0 or entry_body <= 0:
        return None

    ob_high = ob_candle["high"]
    ob_low = ob_candle["low"]
    zone_height = ob_high - ob_low

    if zone_height <= 0:
        return None

    structure = df.iloc[-24:-4]
    recent_high = structure["high"].max()
    recent_low = structure["low"].min()

    sl_buffer = _sl_buffer(atr)

    # =========================
    # Bullish Order Block
    # Last bearish candle before strong bullish displacement
    # =========================
    bearish_ob = ob_candle["close"] < ob_candle["open"]

    bullish_displacement = (
        trigger["close"] > trigger["open"]
        and trigger_body > atr * 0.50
        and trigger["close"] > ob_high
    )

    revisited_bullish_ob = (
        entry["low"] <= ob_high
        and entry["close"] >= ob_low
    )

    bullish_confirmation = (
        entry["close"] > entry["open"]
        and price > ema
        and entry_body > atr * 0.20
    )

    if (
        bearish_ob
        and bullish_displacement
        and revisited_bullish_ob
        and bullish_confirmation
    ):
        sl_reference = round(ob_low - sl_buffer, 2)

        if recent_high > entry["close"]:
            tp_reference = recent_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = entry["close"] + max(zone_height * 2, atr * 1.2)
            target_model = "MEASURED_ORDER_BLOCK_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=89,
            trigger_body=trigger_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "ORDER_BLOCK",
            "entry_model": "OB_RETEST_CONTINUATION",
            "pattern_height": zone_height,
            "ob_high": ob_high,
            "ob_low": ob_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_displacement_retest",
            "direction_context": "price_above_ema",
            "reason": (
                f"Bullish order block -> bearish base candle zone "
                f"{round(ob_low, 2)} to {round(ob_high, 2)} -> "
                f"bullish displacement confirmed -> revisit respected -> "
                f"SL below OB low {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # Bearish Order Block
    # Last bullish candle before strong bearish displacement
    # =========================
    bullish_ob = ob_candle["close"] > ob_candle["open"]

    bearish_displacement = (
        trigger["close"] < trigger["open"]
        and trigger_body > atr * 0.50
        and trigger["close"] < ob_low
    )

    revisited_bearish_ob = (
        entry["high"] >= ob_low
        and entry["close"] <= ob_high
    )

    bearish_confirmation = (
        entry["close"] < entry["open"]
        and price < ema
        and entry_body > atr * 0.20
    )

    if (
        bullish_ob
        and bearish_displacement
        and revisited_bearish_ob
        and bearish_confirmation
    ):
        sl_reference = round(ob_high + sl_buffer, 2)

        if recent_low < entry["close"]:
            tp_reference = recent_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = entry["close"] - max(zone_height * 2, atr * 1.2)
            target_model = "MEASURED_ORDER_BLOCK_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=89,
            trigger_body=trigger_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "ORDER_BLOCK",
            "entry_model": "OB_RETEST_CONTINUATION",
            "pattern_height": zone_height,
            "ob_high": ob_high,
            "ob_low": ob_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_displacement_retest",
            "direction_context": "price_below_ema",
            "reason": (
                f"Bearish order block -> bullish base candle zone "
                f"{round(ob_low, 2)} to {round(ob_high, 2)} -> "
                f"bearish displacement confirmed -> revisit respected -> "
                f"SL above OB high {sl_reference} -> "
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

