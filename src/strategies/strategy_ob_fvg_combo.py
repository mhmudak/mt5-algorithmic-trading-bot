from config.settings import ATR_MIN, ATR_MAX


OB_FVG_SL_ATR_MULTIPLIER = 0.20
OB_FVG_MIN_SL_BUFFER = 2.0
OB_FVG_MAX_SL_BUFFER = 5.0


def _sl_buffer(atr):
    return min(
        max(atr * OB_FVG_SL_ATR_MULTIPLIER, OB_FVG_MIN_SL_BUFFER),
        OB_FVG_MAX_SL_BUFFER,
    )


def _score_setup(base_score, body, atr, sweep_confirmed, close_aligned):
    score = base_score

    if body > atr * 0.35:
        score += 2

    if body > atr * 0.55:
        score += 2

    if sweep_confirmed:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < 40:
        return None

    # candles
    c1 = df.iloc[-5]
    c2 = df.iloc[-4]  # OB candle
    c3 = df.iloc[-3]  # displacement candle
    c4 = df.iloc[-2]  # entry / reaction candle

    atr = c4["atr_14"]
    ema = c4["ema_20"]
    price = c4["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body = abs(c4["close"] - c4["open"])
    displacement_body = abs(c3["close"] - c3["open"])

    if body <= 0 or displacement_body <= 0:
        return None

    # Order block body zone
    ob_high = max(c2["open"], c2["close"])
    ob_low = min(c2["open"], c2["close"])
    ob_range = ob_high - ob_low

    if ob_range <= 0:
        return None

    # Structure / liquidity
    recent = df.iloc[-20:-4]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    sl_buffer = _sl_buffer(atr)

    # =========================================================
    # Bullish OB + FVG Combo
    # =========================================================
    bullish_displacement = (
        c3["close"] > c3["open"]
        and displacement_body > atr * 0.35
    )

    bullish_fvg = c2["high"] < c4["low"]
    bullish_fvg_top = c4["low"]
    bullish_fvg_bottom = c2["high"]
    bullish_fvg_size = bullish_fvg_top - bullish_fvg_bottom

    bullish_overlap = (
        bullish_fvg
        and bullish_fvg_size > atr * 0.15
        and bullish_fvg_bottom <= ob_high
        and bullish_fvg_top >= ob_low
    )

    sweep_low = c4["low"] < recent_low

    bullish_reaction = (
        c4["low"] <= bullish_fvg_top
        and c4["close"] > c4["open"]
        and body > atr * 0.25
        and price > ema
    )

    if (
        bullish_displacement
        and bullish_overlap
        and sweep_low
        and bullish_reaction
    ):
        pattern_height = max(bullish_fvg_size, ob_range)
        sl_reference = round(min(ob_low, bullish_fvg_bottom, c4["low"]) - sl_buffer, 2)

        if recent_high > c4["close"]:
            tp_reference = recent_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = c4["close"] + max(pattern_height * 2, atr * 1.5)
            target_model = "MEASURED_OB_FVG_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=96,
            body=body,
            atr=atr,
            sweep_confirmed=sweep_low,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "OB_FVG_COMBO",
            "entry_model": "OB_FVG_RETEST_REACTION",
            "pattern_height": pattern_height,
            "ob_high": ob_high,
            "ob_low": ob_low,
            "fvg_top": bullish_fvg_top,
            "fvg_bottom": bullish_fvg_bottom,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_displacement_ob_fvg_reaction",
            "direction_context": "price_above_ema",
            "reason": (
                f"OB+FVG bullish -> overlap zone {round(ob_low, 2)}-{round(ob_high, 2)} -> "
                f"liquidity sweep below {round(recent_low, 2)} -> reaction confirmed -> "
                f"SL below confluence zone {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> EMA aligned"
            ),
        }

    # =========================================================
    # Bearish OB + FVG Combo
    # =========================================================
    bearish_displacement = (
        c3["close"] < c3["open"]
        and displacement_body > atr * 0.35
    )

    bearish_fvg = c2["low"] > c4["high"]
    bearish_fvg_top = c2["low"]
    bearish_fvg_bottom = c4["high"]
    bearish_fvg_size = bearish_fvg_top - bearish_fvg_bottom

    bearish_overlap = (
        bearish_fvg
        and bearish_fvg_size > atr * 0.15
        and bearish_fvg_top >= ob_low
        and bearish_fvg_bottom <= ob_high
    )

    sweep_high = c4["high"] > recent_high

    bearish_reaction = (
        c4["high"] >= bearish_fvg_bottom
        and c4["close"] < c4["open"]
        and body > atr * 0.25
        and price < ema
    )

    if (
        bearish_displacement
        and bearish_overlap
        and sweep_high
        and bearish_reaction
    ):
        pattern_height = max(bearish_fvg_size, ob_range)
        sl_reference = round(max(ob_high, bearish_fvg_top, c4["high"]) + sl_buffer, 2)

        if recent_low < c4["close"]:
            tp_reference = recent_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = c4["close"] - max(pattern_height * 2, atr * 1.5)
            target_model = "MEASURED_OB_FVG_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=96,
            body=body,
            atr=atr,
            sweep_confirmed=sweep_high,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "OB_FVG_COMBO",
            "entry_model": "OB_FVG_RETEST_REACTION",
            "pattern_height": pattern_height,
            "ob_high": ob_high,
            "ob_low": ob_low,
            "fvg_top": bearish_fvg_top,
            "fvg_bottom": bearish_fvg_bottom,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_displacement_ob_fvg_reaction",
            "direction_context": "price_below_ema",
            "reason": (
                f"OB+FVG bearish -> overlap zone {round(ob_low, 2)}-{round(ob_high, 2)} -> "
                f"liquidity sweep above {round(recent_high, 2)} -> reaction confirmed -> "
                f"SL above confluence zone {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> EMA aligned"
            ),
        }

    return None