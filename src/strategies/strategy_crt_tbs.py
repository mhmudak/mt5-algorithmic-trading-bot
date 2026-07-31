import hashlib
from config.settings import ATR_MIN, ATR_MAX



PHASE6P3C_REMAINING_LEGACY_STANDARDIZATION = True
PHASE6P3C_STRATEGY_NAME = "CRT_TBS"
PHASE6P3C_FALLBACK_PHASE_NAME = "PHASE_6P3C_CRT_TBS_STANDARDIZED_COMPLETION"
PHASE6P3C_SETUP_PREFIX = "CRT"
PHASE6P3C_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

CRT_TBS_SL_ATR_MULTIPLIER = 0.20
CRT_TBS_MIN_SL_BUFFER = 2.0
CRT_TBS_MAX_SL_BUFFER = 5.0


def _sl_buffer(atr):
    return min(
        max(atr * CRT_TBS_SL_ATR_MULTIPLIER, CRT_TBS_MIN_SL_BUFFER),
        CRT_TBS_MAX_SL_BUFFER,
    )


def _score_setup(base_score, confirm_body, atr, close_aligned):
    score = base_score

    if confirm_body > atr * 0.35:
        score += 2

    if confirm_body > atr * 0.50:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def _phase6p3c_generate_signal_raw(df):
    if len(df) < 30:
        return None

    trap = df.iloc[-3]      # liquidity / trap candle
    confirm = df.iloc[-2]   # confirmation candle

    atr = confirm["atr_14"]
    ema = confirm["ema_20"]
    price = confirm["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    recent = df.iloc[-15:-3]
    range_high = recent["high"].max()
    range_low = recent["low"].min()
    pattern_height = abs(range_high - range_low)

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
    # Bearish CRT / TBS
    # trap above range -> rejection -> bearish confirmation
    # =========================================================
    trapped_high = trap["high"] > range_high
    close_back_inside = trap["close"] < range_high
    upper_rejection = upper_wick > trap_body * 1.2

    bearish_confirmation = (
        confirm["close"] < confirm["open"]
        and confirm["close"] < trap["low"]
        and confirm_body > atr * 0.25
        and price < ema
    )

    if (
        trapped_high
        and close_back_inside
        and upper_rejection
        and bearish_confirmation
    ):
        sl_reference = round(trap["high"] + sl_buffer, 2)

        # Prefer opposite side of the range as structural TP.
        # If already below it, use measured move fallback.
        if range_low < confirm["close"]:
            tp_reference = range_low
            target_model = "OPPOSITE_RANGE_LOW"
        else:
            tp_reference = confirm["close"] - pattern_height
            target_model = "MEASURED_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=93,
            confirm_body=confirm_body,
            atr=atr,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "CRT_TBS",
            "entry_model": "CRT_TBS_TRAP_REVERSAL",
            "pattern_height": pattern_height,
            "range_high": range_high,
            "range_low": range_low,
            "trap_high": trap["high"],
            "trap_low": trap["low"],
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_confirmation_displacement",
            "direction_context": "price_below_ema",
            "reason": (
                f"CRT/TBS bearish -> trap above range {round(range_high, 2)} -> "
                f"close back inside -> bearish break below {round(trap['low'], 2)} -> "
                f"SL above trap high {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
            ),
        }

    # =========================================================
    # Bullish CRT / TBS
    # trap below range -> rejection -> bullish confirmation
    # =========================================================
    trapped_low = trap["low"] < range_low
    close_back_inside = trap["close"] > range_low
    lower_rejection = lower_wick > trap_body * 1.2

    bullish_confirmation = (
        confirm["close"] > confirm["open"]
        and confirm["close"] > trap["high"]
        and confirm_body > atr * 0.25
        and price > ema
    )

    if (
        trapped_low
        and close_back_inside
        and lower_rejection
        and bullish_confirmation
    ):
        sl_reference = round(trap["low"] - sl_buffer, 2)

        # Prefer opposite side of the range as structural TP.
        # If already above it, use measured move fallback.
        if range_high > confirm["close"]:
            tp_reference = range_high
            target_model = "OPPOSITE_RANGE_HIGH"
        else:
            tp_reference = confirm["close"] + pattern_height
            target_model = "MEASURED_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=93,
            confirm_body=confirm_body,
            atr=atr,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "CRT_TBS",
            "entry_model": "CRT_TBS_TRAP_REVERSAL",
            "pattern_height": pattern_height,
            "range_high": range_high,
            "range_low": range_low,
            "trap_high": trap["high"],
            "trap_low": trap["low"],
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_confirmation_displacement",
            "direction_context": "price_above_ema",
            "reason": (
                f"CRT/TBS bullish -> trap below range {round(range_low, 2)} -> "
                f"close back inside -> bullish break above {round(trap['high'], 2)} -> "
                f"SL below trap low {sl_reference} -> "
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

