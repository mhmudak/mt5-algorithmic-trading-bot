import hashlib
from config.settings import ATR_MIN, ATR_MAX



PHASE6P3A_PRIORITY_LEGACY_STANDARDIZATION = True
PHASE6P3A_STRATEGY_NAME = "FAILED_FVG_REVERSAL"
PHASE6P3A_FALLBACK_PHASE_NAME = "PHASE_6P3A_FAILED_FVG_REVERSAL_STANDARDIZED_COMPLETION"
PHASE6P3A_SETUP_PREFIX = "FFVG"
PHASE6P3A_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

FAILED_FVG_LOOKBACK = 30

MIN_FVG_SIZE_ATR = 0.12
MIN_FAILURE_BODY_ATR = 0.25
MIN_DISPLACEMENT_BODY_ATR = 0.35

SL_ATR_BUFFER = 0.20
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 5.0

TARGET_ATR_MIN = 1.5
TARGET_ATR_MAX = 3.0


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, fvg_size):
    return min(
        max(fvg_size * 2.0, atr * TARGET_ATR_MIN),
        atr * TARGET_ATR_MAX,
    )


def _score_setup(base_score, body, atr, fvg_size, displacement_ok, close_quality):
    score = base_score

    if body > atr * 0.35:
        score += 2

    if body > atr * 0.55:
        score += 2

    if fvg_size > atr * 0.20:
        score += 2

    if displacement_ok:
        score += 3

    if close_quality:
        score += 2

    return min(score, 99)


def _find_recent_bullish_fvg(df, atr):
    """
    Bullish FVG:
    c1 high < c3 low.
    """
    closed = df.iloc[:-1].reset_index(drop=True)

    for i in range(len(closed) - 4, max(2, len(closed) - FAILED_FVG_LOOKBACK), -1):
        c1 = closed.iloc[i - 2]
        c2 = closed.iloc[i - 1]
        c3 = closed.iloc[i]

        body_c2 = abs(c2["close"] - c2["open"])

        fvg_bottom = c1["high"]
        fvg_top = c3["low"]
        fvg_size = fvg_top - fvg_bottom

        if (
            fvg_size > atr * MIN_FVG_SIZE_ATR
            and c2["close"] > c2["open"]
            and body_c2 > atr * MIN_DISPLACEMENT_BODY_ATR
        ):
            return {
                "fvg_top": fvg_top,
                "fvg_bottom": fvg_bottom,
                "fvg_mid": (fvg_top + fvg_bottom) / 2,
                "fvg_size": fvg_size,
            }

    return None


def _find_recent_bearish_fvg(df, atr):
    """
    Bearish FVG:
    c1 low > c3 high.
    """
    closed = df.iloc[:-1].reset_index(drop=True)

    for i in range(len(closed) - 4, max(2, len(closed) - FAILED_FVG_LOOKBACK), -1):
        c1 = closed.iloc[i - 2]
        c2 = closed.iloc[i - 1]
        c3 = closed.iloc[i]

        body_c2 = abs(c2["close"] - c2["open"])

        fvg_top = c1["low"]
        fvg_bottom = c3["high"]
        fvg_size = fvg_top - fvg_bottom

        if (
            fvg_size > atr * MIN_FVG_SIZE_ATR
            and c2["close"] < c2["open"]
            and body_c2 > atr * MIN_DISPLACEMENT_BODY_ATR
        ):
            return {
                "fvg_top": fvg_top,
                "fvg_bottom": fvg_bottom,
                "fvg_mid": (fvg_top + fvg_bottom) / 2,
                "fvg_size": fvg_size,
            }

    return None


def _phase6p3a_generate_signal_raw(df):
    if len(df) < FAILED_FVG_LOOKBACK + 5:
        return None

    entry = df.iloc[-2]
    prev = df.iloc[-3]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return None

    if body < atr * MIN_FAILURE_BODY_ATR:
        return None

    recent = df.iloc[-25:-2]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    sl_buffer = _sl_buffer(atr)

    # =========================================================
    # SELL: bullish FVG fails
    # =========================================================
    bullish_fvg = _find_recent_bullish_fvg(df, atr)

    if bullish_fvg is not None:
        fvg_top = bullish_fvg["fvg_top"]
        fvg_bottom = bullish_fvg["fvg_bottom"]
        fvg_mid = bullish_fvg["fvg_mid"]
        fvg_size = bullish_fvg["fvg_size"]

        fvg_failed = (
            entry["close"] < fvg_bottom
            and prev["low"] <= fvg_top
        )

        bearish_displacement = (
            entry["close"] < entry["open"]
            and entry["close"] < prev["low"]
            and body > atr * MIN_DISPLACEMENT_BODY_ATR
        )

        ema_context = price < ema
        close_quality = entry["close"] <= entry["high"] - candle_range * 0.65

        if fvg_failed and bearish_displacement and close_quality:
            sl_reference = round(max(entry["high"], fvg_top) + sl_buffer, 2)

            if recent_low < entry["close"]:
                tp_reference = recent_low
                target_model = "RECENT_STRUCTURE_LOW"
            else:
                tp_reference = entry["close"] - _target_distance(atr, fvg_size)
                target_model = "FAILED_FVG_EXTENSION"

            tp_reference = round(tp_reference, 2)

            if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
                return None

            score = _score_setup(
                base_score=92,
                body=body,
                atr=atr,
                fvg_size=fvg_size,
                displacement_ok=bearish_displacement,
                close_quality=close_quality,
            )

            return {
                "signal": "SELL",
                "score": score,
                "strategy": "FAILED_FVG_REVERSAL",
                "entry_model": "FAILED_BULLISH_FVG_REVERSAL",
                "pattern_height": abs(entry["close"] - tp_reference),
                "failed_fvg_top": fvg_top,
                "failed_fvg_bottom": fvg_bottom,
                "failed_fvg_mid": fvg_mid,
                "recent_high": recent_high,
                "recent_low": recent_low,
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": target_model,
                "momentum": "bearish_failed_bullish_fvg",
                "direction_context": (
                    "price_below_ema" if ema_context else "counter_ema_failed_fvg"
                ),
                "reason": (
                    f"Failed bullish FVG SELL -> bullish FVG "
                    f"{round(fvg_bottom, 2)}-{round(fvg_top, 2)} failed -> "
                    f"bearish displacement confirmed -> "
                    f"SL {sl_reference} -> TP {target_model} {tp_reference}"
                ),
            }

    # =========================================================
    # BUY: bearish FVG fails
    # =========================================================
    bearish_fvg = _find_recent_bearish_fvg(df, atr)

    if bearish_fvg is not None:
        fvg_top = bearish_fvg["fvg_top"]
        fvg_bottom = bearish_fvg["fvg_bottom"]
        fvg_mid = bearish_fvg["fvg_mid"]
        fvg_size = bearish_fvg["fvg_size"]

        fvg_failed = (
            entry["close"] > fvg_top
            and prev["high"] >= fvg_bottom
        )

        bullish_displacement = (
            entry["close"] > entry["open"]
            and entry["close"] > prev["high"]
            and body > atr * MIN_DISPLACEMENT_BODY_ATR
        )

        ema_context = price > ema
        close_quality = entry["close"] >= entry["low"] + candle_range * 0.65

        if fvg_failed and bullish_displacement and close_quality:
            sl_reference = round(min(entry["low"], fvg_bottom) - sl_buffer, 2)

            if recent_high > entry["close"]:
                tp_reference = recent_high
                target_model = "RECENT_STRUCTURE_HIGH"
            else:
                tp_reference = entry["close"] + _target_distance(atr, fvg_size)
                target_model = "FAILED_FVG_EXTENSION"

            tp_reference = round(tp_reference, 2)

            if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
                return None

            score = _score_setup(
                base_score=92,
                body=body,
                atr=atr,
                fvg_size=fvg_size,
                displacement_ok=bullish_displacement,
                close_quality=close_quality,
            )

            return {
                "signal": "BUY",
                "score": score,
                "strategy": "FAILED_FVG_REVERSAL",
                "entry_model": "FAILED_BEARISH_FVG_REVERSAL",
                "pattern_height": abs(tp_reference - entry["close"]),
                "failed_fvg_top": fvg_top,
                "failed_fvg_bottom": fvg_bottom,
                "failed_fvg_mid": fvg_mid,
                "recent_high": recent_high,
                "recent_low": recent_low,
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": target_model,
                "momentum": "bullish_failed_bearish_fvg",
                "direction_context": (
                    "price_above_ema" if ema_context else "counter_ema_failed_fvg"
                ),
                "reason": (
                    f"Failed bearish FVG BUY -> bearish FVG "
                    f"{round(fvg_bottom, 2)}-{round(fvg_top, 2)} failed -> "
                    f"bullish displacement confirmed -> "
                    f"SL {sl_reference} -> TP {target_model} {tp_reference}"
                ),
            }

    return None


def _phase6p3a_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _phase6p3a_entry_reference(df, payload):
    for key in ("entry_reference", "entry_price", "entry", "price"):
        value = _phase6p3a_float(payload.get(key))

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


def _phase6p3a_risk_reward(signal, entry_reference, sl_reference, tp_reference):
    entry_reference = _phase6p3a_float(entry_reference)
    sl_reference = _phase6p3a_float(sl_reference)
    tp_reference = _phase6p3a_float(tp_reference)

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


def _phase6p3a_setup_id(payload, entry_reference):
    signal = payload.get("signal", "NA")
    entry_model = payload.get("entry_model", payload.get("type", "NA"))
    sl_reference = payload.get("sl_reference", payload.get("stop_loss", ""))
    tp_reference = payload.get("tp_reference", payload.get("take_profit", ""))

    raw = (
        f"{PHASE6P3A_STRATEGY_NAME}:{signal}:{entry_model}:"
        f"{round(float(entry_reference), 2)}:{sl_reference}:{tp_reference}"
    )
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]

    return f"{PHASE6P3A_SETUP_PREFIX}-{signal}-{digest}"


def _phase6p3a_standardize_signal(payload, df):
    if not payload:
        return payload

    signal = payload.get("signal")
    entry_reference = _phase6p3a_entry_reference(df, payload)

    if entry_reference is None:
        return payload

    existing_rr = _phase6p3a_float(payload.get("rr"))
    existing_risk_reward = _phase6p3a_float(payload.get("risk_reward"))

    computed_rr = _phase6p3a_risk_reward(
        signal=signal,
        entry_reference=entry_reference,
        sl_reference=payload.get("sl_reference", payload.get("stop_loss")),
        tp_reference=payload.get("tp_reference", payload.get("take_profit")),
    )

    final_rr = existing_rr if existing_rr is not None else existing_risk_reward
    final_rr = final_rr if final_rr is not None else computed_rr

    payload.setdefault("strategy", PHASE6P3A_STRATEGY_NAME)
    payload.setdefault("phase", PHASE6P3A_FALLBACK_PHASE_NAME)
    payload.setdefault("setup_id", _phase6p3a_setup_id(payload, entry_reference))
    payload.setdefault("entry_reference", round(float(entry_reference), 2))

    if final_rr is not None:
        payload.setdefault("rr", final_rr)
        payload.setdefault("risk_reward", final_rr)

    payload.setdefault("auto_trade_allowed", True)
    payload.setdefault("decision_impact", "MAIN_BOT_RUNTIME_CONTROLLED")
    payload.setdefault("duplicate_policy", PHASE6P3A_DUPLICATE_POLICY)

    return payload


def generate_signal(df):
    return _phase6p3a_standardize_signal(_phase6p3a_generate_signal_raw(df), df)

