from config.settings import ATR_MIN, ATR_MAX


FVG_CE_LOOKBACK = 30

MIN_DISPLACEMENT_BODY_ATR = 0.35
MIN_FVG_SIZE_ATR = 0.12
MIN_REACTION_BODY_ATR = 0.20

CE_TOUCH_BUFFER_ATR = 0.20

SL_ATR_BUFFER = 0.20
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 5.0

TARGET_ATR_MIN = 1.5
TARGET_ATR_MAX = 3.5


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, fvg_size):
    return min(
        max(fvg_size * 2.0, atr * TARGET_ATR_MIN),
        atr * TARGET_ATR_MAX,
    )


def _score_setup(base_score, body, atr, ce_touched, strong_reaction, clean_context):
    score = base_score

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.50:
        score += 2

    if ce_touched:
        score += 3

    if strong_reaction:
        score += 3

    if clean_context:
        score += 2

    return min(score, 99)


def _find_recent_bullish_fvg(df, atr):
    """
    Finds a recent bullish FVG:
    c1 high < c3 low.
    Returns the most recent valid gap.
    """
    closed = df.iloc[:-1].reset_index(drop=True)

    for i in range(len(closed) - 4, max(2, len(closed) - FVG_CE_LOOKBACK), -1):
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
                "created_index": i,
            }

    return None


def _find_recent_bearish_fvg(df, atr):
    """
    Finds a recent bearish FVG:
    c1 low > c3 high.
    Returns the most recent valid gap.
    """
    closed = df.iloc[:-1].reset_index(drop=True)

    for i in range(len(closed) - 4, max(2, len(closed) - FVG_CE_LOOKBACK), -1):
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
                "created_index": i,
            }

    return None


def generate_signal(df):
    if len(df) < FVG_CE_LOOKBACK + 5:
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

    if candle_range <= 0 or body < atr * MIN_REACTION_BODY_ATR:
        return None

    recent = df.iloc[-25:-2]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    sl_buffer = _sl_buffer(atr)

    # =========================================================
    # BUY: bullish FVG CE mitigation + reclaim
    # =========================================================
    bullish_fvg = _find_recent_bullish_fvg(df, atr)

    if bullish_fvg is not None:
        fvg_top = bullish_fvg["fvg_top"]
        fvg_bottom = bullish_fvg["fvg_bottom"]
        fvg_mid = bullish_fvg["fvg_mid"]
        fvg_size = bullish_fvg["fvg_size"]

        ce_touched = (
            entry["low"] <= fvg_mid + atr * CE_TOUCH_BUFFER_ATR
            and entry["high"] >= fvg_bottom
        )

        reclaimed_fvg = (
            entry["close"] > entry["open"]
            and entry["close"] > fvg_mid
            and price > ema
        )

        strong_reaction = (
            entry["close"] >= entry["low"] + candle_range * 0.60
            and entry["close"] > prev["high"]
        )

        if ce_touched and reclaimed_fvg and strong_reaction:
            sl_reference = round(min(entry["low"], fvg_bottom) - sl_buffer, 2)

            if recent_high > entry["close"]:
                tp_reference = recent_high
                target_model = "RECENT_STRUCTURE_HIGH"
            else:
                tp_reference = entry["close"] + _target_distance(atr, fvg_size)
                target_model = "FVG_CE_MEASURED_EXTENSION"

            tp_reference = round(tp_reference, 2)

            if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
                return None

            score = _score_setup(
                base_score=92,
                body=body,
                atr=atr,
                ce_touched=True,
                strong_reaction=True,
                clean_context=price > ema,
            )

            return {
                "signal": "BUY",
                "score": score,
                "strategy": "FVG_CE_MITIGATION",
                "entry_model": "BULLISH_FVG_CE_RECLAIM",
                "pattern_height": abs(tp_reference - entry["close"]),
                "fvg_top": fvg_top,
                "fvg_bottom": fvg_bottom,
                "fvg_mid": fvg_mid,
                "recent_high": recent_high,
                "recent_low": recent_low,
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": target_model,
                "momentum": "bullish_ce_reclaim",
                "direction_context": "bullish_fvg_mitigation_price_above_ema",
                "reason": (
                    f"FVG CE BUY -> bullish FVG {round(fvg_bottom, 2)}-{round(fvg_top, 2)} "
                    f"mitigated near CE {round(fvg_mid, 2)} -> reclaim confirmed -> "
                    f"SL {sl_reference} -> TP {target_model} {tp_reference}"
                ),
            }

    # =========================================================
    # SELL: bearish FVG CE mitigation + rejection
    # =========================================================
    bearish_fvg = _find_recent_bearish_fvg(df, atr)

    if bearish_fvg is not None:
        fvg_top = bearish_fvg["fvg_top"]
        fvg_bottom = bearish_fvg["fvg_bottom"]
        fvg_mid = bearish_fvg["fvg_mid"]
        fvg_size = bearish_fvg["fvg_size"]

        ce_touched = (
            entry["high"] >= fvg_mid - atr * CE_TOUCH_BUFFER_ATR
            and entry["low"] <= fvg_top
        )

        rejected_fvg = (
            entry["close"] < entry["open"]
            and entry["close"] < fvg_mid
            and price < ema
        )

        strong_reaction = (
            entry["close"] <= entry["high"] - candle_range * 0.60
            and entry["close"] < prev["low"]
        )

        if ce_touched and rejected_fvg and strong_reaction:
            sl_reference = round(max(entry["high"], fvg_top) + sl_buffer, 2)

            if recent_low < entry["close"]:
                tp_reference = recent_low
                target_model = "RECENT_STRUCTURE_LOW"
            else:
                tp_reference = entry["close"] - _target_distance(atr, fvg_size)
                target_model = "FVG_CE_MEASURED_EXTENSION"

            tp_reference = round(tp_reference, 2)

            if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
                return None

            score = _score_setup(
                base_score=92,
                body=body,
                atr=atr,
                ce_touched=True,
                strong_reaction=True,
                clean_context=price < ema,
            )

            return {
                "signal": "SELL",
                "score": score,
                "strategy": "FVG_CE_MITIGATION",
                "entry_model": "BEARISH_FVG_CE_REJECT",
                "pattern_height": abs(entry["close"] - tp_reference),
                "fvg_top": fvg_top,
                "fvg_bottom": fvg_bottom,
                "fvg_mid": fvg_mid,
                "recent_high": recent_high,
                "recent_low": recent_low,
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": target_model,
                "momentum": "bearish_ce_rejection",
                "direction_context": "bearish_fvg_mitigation_price_below_ema",
                "reason": (
                    f"FVG CE SELL -> bearish FVG {round(fvg_bottom, 2)}-{round(fvg_top, 2)} "
                    f"mitigated near CE {round(fvg_mid, 2)} -> rejection confirmed -> "
                    f"SL {sl_reference} -> TP {target_model} {tp_reference}"
                ),
            }

    return None