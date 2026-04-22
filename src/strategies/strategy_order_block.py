from config.settings import ATR_MIN, ATR_MAX


def generate_signal(df):
    if len(df) < 25:
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

    # =========================
    # Bullish Order Block
    # Last bearish candle before strong bullish displacement
    # =========================
    bearish_ob = ob_candle["close"] < ob_candle["open"]
    bullish_displacement = (
        trigger["close"] > trigger["open"]
        and trigger_body > atr * 0.5
    )

    ob_high = ob_candle["high"]
    ob_low = ob_candle["low"]

    revisited_bullish_ob = (
        entry["low"] <= ob_high
        and entry["close"] >= ob_low
    )

    bullish_confirmation = (
        entry["close"] > entry["open"]
        and price > ema
        and entry_body > atr * 0.2
    )

    if bearish_ob and bullish_displacement and revisited_bullish_ob and bullish_confirmation:
        zone_height = ob_high - ob_low

        return {
            "signal": "BUY",
            "score": 89,
            "strategy": "ORDER_BLOCK",
            "pattern_height": zone_height,
            "ob_high": ob_high,
            "ob_low": ob_low,
            "reason": (
                f"Bullish order block -> bearish base candle zone {round(ob_low, 2)} to {round(ob_high, 2)} -> "
                f"bullish displacement confirmed -> revisit respected -> price above EMA"
            ),
        }

    # =========================
    # Bearish Order Block
    # Last bullish candle before strong bearish displacement
    # =========================
    bullish_ob = ob_candle["close"] > ob_candle["open"]
    bearish_displacement = (
        trigger["close"] < trigger["open"]
        and trigger_body > atr * 0.5
    )

    ob_high = ob_candle["high"]
    ob_low = ob_candle["low"]

    revisited_bearish_ob = (
        entry["high"] >= ob_low
        and entry["close"] <= ob_high
    )

    bearish_confirmation = (
        entry["close"] < entry["open"]
        and price < ema
        and entry_body > atr * 0.2
    )

    if bullish_ob and bearish_displacement and revisited_bearish_ob and bearish_confirmation:
        zone_height = ob_high - ob_low

        return {
            "signal": "SELL",
            "score": 89,
            "strategy": "ORDER_BLOCK",
            "pattern_height": zone_height,
            "ob_high": ob_high,
            "ob_low": ob_low,
            "reason": (
                f"Bearish order block -> bullish base candle zone {round(ob_low, 2)} to {round(ob_high, 2)} -> "
                f"bearish displacement confirmed -> revisit respected -> price below EMA"
            ),
        }

    return None