import hashlib
from config.settings import ATR_MIN, ATR_MAX



PHASE6P3B_SMC_LIQUIDITY_STANDARDIZATION = True
PHASE6P3B_STRATEGY_NAME = "AMD_FVG"
PHASE6P3B_FALLBACK_PHASE_NAME = "PHASE_6P3B_AMD_FVG_STANDARDIZED_COMPLETION"
PHASE6P3B_SETUP_PREFIX = "AMD"
PHASE6P3B_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

AMD_LOOKBACK = 32
ACCUMULATION_BARS = 10

MAX_ACCUMULATION_RANGE_ATR = 2.8
MIN_ACCUMULATION_RANGE_ATR = 0.6

MIN_MANIPULATION_ATR = 0.15
MAX_MANIPULATION_ATR = 1.8

MIN_DISPLACEMENT_BODY_ATR = 0.35
FVG_MIN_SIZE_ATR = 0.10

MAX_ENTRY_EXTENSION_ATR = 0.80

SL_ATR_BUFFER = 0.20
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 5.0

TARGET_ATR_MIN = 1.5
TARGET_ATR_MAX = 3.0


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, accumulation_range):
    return min(
        max(accumulation_range * 1.0, atr * TARGET_ATR_MIN),
        atr * TARGET_ATR_MAX,
    )


def _score_setup(
    base_score,
    displacement_body,
    atr,
    manipulation_depth,
    fvg_size,
    close_back_inside,
    reclaim_quality,
):
    score = base_score

    if manipulation_depth > atr * 0.30:
        score += 2

    if displacement_body > atr * 0.50:
        score += 2

    if displacement_body > atr * 0.75:
        score += 2

    if fvg_size > atr * 0.20:
        score += 2

    if close_back_inside:
        score += 2

    if reclaim_quality:
        score += 2

    return min(score, 99)


def _phase6p3b_generate_signal_raw(df):
    if len(df) < AMD_LOOKBACK + 5:
        return None

    # Closed-candle structure
    accumulation = df.iloc[-(ACCUMULATION_BARS + 5):-5]
    manipulation = df.iloc[-4]
    displacement = df.iloc[-3]
    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    accumulation_high = accumulation["high"].max()
    accumulation_low = accumulation["low"].min()
    accumulation_range = accumulation_high - accumulation_low

    if accumulation_range <= 0:
        return None

    if accumulation_range > atr * MAX_ACCUMULATION_RANGE_ATR:
        return None

    if accumulation_range < atr * MIN_ACCUMULATION_RANGE_ATR:
        return None

    manipulation_body = abs(manipulation["close"] - manipulation["open"])
    displacement_body = abs(displacement["close"] - displacement["open"])
    entry_body = abs(entry["close"] - entry["open"])
    entry_range = entry["high"] - entry["low"]

    if entry_range <= 0:
        return None

    if displacement_body < atr * MIN_DISPLACEMENT_BODY_ATR:
        return None

    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, accumulation_range)

    # =========================================================
    # BUY AMD
    # Accumulation -> sell-side manipulation -> close back inside -> bullish displacement + FVG
    # =========================================================
    swept_low = manipulation["low"] < accumulation_low
    manipulation_depth = accumulation_low - manipulation["low"]

    valid_manipulation_depth = (
        manipulation_depth >= atr * MIN_MANIPULATION_ATR
        and manipulation_depth <= atr * MAX_MANIPULATION_ATR
    )

    close_back_inside = (
        manipulation["close"] > accumulation_low
        and manipulation["close"] < accumulation_high
    )

    bullish_displacement = (
        displacement["close"] > displacement["open"]
        and displacement["close"] > accumulation_high
        and displacement_body > atr * MIN_DISPLACEMENT_BODY_ATR
        and price > ema
    )

    bullish_fvg_exists = manipulation["high"] < entry["low"]
    bullish_fvg_bottom = manipulation["high"]
    bullish_fvg_top = entry["low"]
    bullish_fvg_size = bullish_fvg_top - bullish_fvg_bottom

    bullish_reclaim = (
        entry["close"] > entry["open"]
        and entry["close"] > bullish_fvg_top
        and entry_body > atr * 0.20
        and entry["close"] >= entry["low"] + entry_range * 0.60
    )

    entry_extension = entry["close"] - accumulation_high
    not_late = entry_extension <= atr * MAX_ENTRY_EXTENSION_ATR

    if (
        swept_low
        and valid_manipulation_depth
        and close_back_inside
        and bullish_displacement
        and bullish_fvg_exists
        and bullish_fvg_size > atr * FVG_MIN_SIZE_ATR
        and bullish_reclaim
        and not_late
    ):
        sl_reference = round(manipulation["low"] - sl_buffer, 2)

        if accumulation_high > entry["close"]:
            tp_reference = accumulation_high
            target_model = "ACCUMULATION_HIGH"
        else:
            tp_reference = entry["close"] + target_distance
            target_model = "AMD_MEASURED_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            displacement_body=displacement_body,
            atr=atr,
            manipulation_depth=manipulation_depth,
            fvg_size=bullish_fvg_size,
            close_back_inside=close_back_inside,
            reclaim_quality=entry["close"] > displacement["high"],
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "AMD_FVG",
            "entry_model": "AMD_SELLSIDE_SWEEP_BULLISH_FVG_RECLAIM",
            "pattern_height": abs(tp_reference - entry["close"]),
            "accumulation_high": accumulation_high,
            "accumulation_low": accumulation_low,
            "manipulation_low": manipulation["low"],
            "manipulation_close": manipulation["close"],
            "fvg_bottom": bullish_fvg_bottom,
            "fvg_top": bullish_fvg_top,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_displacement_after_sellside_sweep",
            "direction_context": "amd_bullish_reversal_close_back_inside_range",
            "reason": (
                f"AMD FVG BUY -> accumulation {round(accumulation_low, 2)}-{round(accumulation_high, 2)} -> "
                f"sell-side manipulation {round(manipulation['low'], 2)} -> "
                f"closed back inside range -> bullish displacement + FVG "
                f"{round(bullish_fvg_bottom, 2)}-{round(bullish_fvg_top, 2)} -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
            ),
        }

    # =========================================================
    # SELL AMD
    # Accumulation -> buy-side manipulation -> close back inside -> bearish displacement + FVG
    # =========================================================
    swept_high = manipulation["high"] > accumulation_high
    manipulation_depth = manipulation["high"] - accumulation_high

    valid_manipulation_depth = (
        manipulation_depth >= atr * MIN_MANIPULATION_ATR
        and manipulation_depth <= atr * MAX_MANIPULATION_ATR
    )

    close_back_inside = (
        manipulation["close"] < accumulation_high
        and manipulation["close"] > accumulation_low
    )

    bearish_displacement = (
        displacement["close"] < displacement["open"]
        and displacement["close"] < accumulation_low
        and displacement_body > atr * MIN_DISPLACEMENT_BODY_ATR
        and price < ema
    )

    bearish_fvg_exists = manipulation["low"] > entry["high"]
    bearish_fvg_top = manipulation["low"]
    bearish_fvg_bottom = entry["high"]
    bearish_fvg_size = bearish_fvg_top - bearish_fvg_bottom

    bearish_reclaim = (
        entry["close"] < entry["open"]
        and entry["close"] < bearish_fvg_bottom
        and entry_body > atr * 0.20
        and entry["close"] <= entry["high"] - entry_range * 0.60
    )

    entry_extension = accumulation_low - entry["close"]
    not_late = entry_extension <= atr * MAX_ENTRY_EXTENSION_ATR

    if (
        swept_high
        and valid_manipulation_depth
        and close_back_inside
        and bearish_displacement
        and bearish_fvg_exists
        and bearish_fvg_size > atr * FVG_MIN_SIZE_ATR
        and bearish_reclaim
        and not_late
    ):
        sl_reference = round(manipulation["high"] + sl_buffer, 2)

        if accumulation_low < entry["close"]:
            tp_reference = accumulation_low
            target_model = "ACCUMULATION_LOW"
        else:
            tp_reference = entry["close"] - target_distance
            target_model = "AMD_MEASURED_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            displacement_body=displacement_body,
            atr=atr,
            manipulation_depth=manipulation_depth,
            fvg_size=bearish_fvg_size,
            close_back_inside=close_back_inside,
            reclaim_quality=entry["close"] < displacement["low"],
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "AMD_FVG",
            "entry_model": "AMD_BUYSIDE_SWEEP_BEARISH_FVG_RECLAIM",
            "pattern_height": abs(entry["close"] - tp_reference),
            "accumulation_high": accumulation_high,
            "accumulation_low": accumulation_low,
            "manipulation_high": manipulation["high"],
            "manipulation_close": manipulation["close"],
            "fvg_bottom": bearish_fvg_bottom,
            "fvg_top": bearish_fvg_top,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_displacement_after_buyside_sweep",
            "direction_context": "amd_bearish_reversal_close_back_inside_range",
            "reason": (
                f"AMD FVG SELL -> accumulation {round(accumulation_low, 2)}-{round(accumulation_high, 2)} -> "
                f"buy-side manipulation {round(manipulation['high'], 2)} -> "
                f"closed back inside range -> bearish displacement + FVG "
                f"{round(bearish_fvg_bottom, 2)}-{round(bearish_fvg_top, 2)} -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
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

