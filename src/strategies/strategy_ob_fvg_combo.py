from config.settings import ATR_MIN, ATR_MAX


def generate_signal(df):
    if len(df) < 40:
        return None

    # candles
    c1 = df.iloc[-5]
    c2 = df.iloc[-4]
    c3 = df.iloc[-3]
    c4 = df.iloc[-2]  # entry

    atr = c4["atr_14"]
    ema = c4["ema_20"]
    price = c4["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    # =========================================================
    # 1) DETECT ORDER BLOCK
    # =========================================================
    ob_high = max(c2["open"], c2["close"])
    ob_low = min(c2["open"], c2["close"])

    # must be strong displacement after OB
    displacement = abs(c3["close"] - c3["open"]) > atr * 0.35

    # =========================================================
    # 2) DETECT FVG
    # =========================================================
    fvg_top = c4["low"]
    fvg_bottom = c2["high"]

    bullish_fvg = c2["high"] < c4["low"]
    fvg_size = fvg_top - fvg_bottom

    # =========================================================
    # 3) OVERLAP (CRITICAL)
    # =========================================================
    ob_fvg_overlap = (
        fvg_bottom <= ob_high and
        fvg_top >= ob_low
    )

    # =========================================================
    # 4) LIQUIDITY SWEEP
    # =========================================================
    recent_high = df.iloc[-15:-3]["high"].max()
    recent_low = df.iloc[-15:-3]["low"].min()

    sweep_low = c4["low"] < recent_low
    sweep_high = c4["high"] > recent_high

    # =========================================================
    # 5) REACTION
    # =========================================================
    body = abs(c4["close"] - c4["open"])

    bullish_reaction = (
        c4["low"] <= fvg_top
        and c4["close"] > c4["open"]
        and body > atr * 0.25
    )

    bearish_reaction = (
        c4["high"] >= fvg_bottom
        and c4["close"] < c4["open"]
        and body > atr * 0.25
    )

    # =========================================================
    # 🔥 BULLISH COMBO
    # =========================================================
    if (
        bullish_fvg
        and fvg_size > atr * 0.15
        and displacement
        and ob_fvg_overlap
        and sweep_low
        and bullish_reaction
        and price > ema
    ):
        pattern_height = abs(c4["high"] - c4["low"])

        return {
            "signal": "BUY",
            "score": 96,
            "strategy": "OB_FVG_COMBO",
            "pattern_height": pattern_height,
            "ob_high": ob_high,
            "ob_low": ob_low,
            "fvg_top": fvg_top,
            "fvg_bottom": fvg_bottom,
            "sl_reference": ob_low,
            "reason": (
                f"OB+FVG bullish -> overlap zone {round(ob_low,2)}-{round(ob_high,2)} -> "
                f"liquidity sweep below {round(recent_low,2)} -> reaction confirmed -> EMA aligned"
            ),
        }

    # =========================================================
    # 🔥 BEARISH COMBO
    # =========================================================
    bearish_fvg = c2["low"] > c4["high"]
    fvg_top = c2["low"]
    fvg_bottom = c4["high"]

    ob_fvg_overlap = (
        fvg_top >= ob_low and
        fvg_bottom <= ob_high
    )

    if (
        bearish_fvg
        and fvg_size > atr * 0.15
        and displacement
        and ob_fvg_overlap
        and sweep_high
        and bearish_reaction
        and price < ema
    ):
        pattern_height = abs(c4["high"] - c4["low"])

        return {
            "signal": "SELL",
            "score": 96,
            "strategy": "OB_FVG_COMBO",
            "pattern_height": pattern_height,
            "ob_high": ob_high,
            "ob_low": ob_low,
            "fvg_top": fvg_top,
            "fvg_bottom": fvg_bottom,
            "sl_reference": ob_high,
            "reason": (
                f"OB+FVG bearish -> overlap zone {round(ob_low,2)}-{round(ob_high,2)} -> "
                f"liquidity sweep above {round(recent_high,2)} -> reaction confirmed -> EMA aligned"
            ),
        }

    return None