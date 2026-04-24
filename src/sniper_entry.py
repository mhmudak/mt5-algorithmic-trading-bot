def sniper_entry_allowed(df, signal, signal_data, atr):
    """
    M5 sniper entry filter.
    Allows execution only if price confirms after a small pullback,
    instead of chasing the first impulse.
    """

    if len(df) < 5:
        return False, "not_enough_data"

    trigger = df.iloc[-2]
    prev = df.iloc[-3]

    body = abs(trigger["close"] - trigger["open"])
    candle_range = trigger["high"] - trigger["low"]

    if candle_range <= 0:
        return False, "invalid_candle_range"

    entry_model = signal_data.get("entry_model", "")
    pivot_support = signal_data.get("pivot_support_level")
    pivot_resistance = signal_data.get("pivot_resistance_level")
    pivot_break = signal_data.get("pivot_break_level")

    # =========================
    # BUY SNIPER
    # =========================
    if signal == "BUY":
        reference_level = pivot_support or pivot_break

        if reference_level is None:
            return False, "missing_buy_reference_level"

        pullback_touched = trigger["low"] <= reference_level + max(atr * 0.20, 0.5)

        bullish_reclaim = (
            trigger["close"] > trigger["open"]
            and trigger["close"] > reference_level
        )

        strong_close = trigger["close"] >= trigger["low"] + candle_range * 0.60
        momentum_ok = body >= atr * 0.15

        if (
            pullback_touched
            and bullish_reclaim
            and strong_close
            and momentum_ok
        ):
            return True, "buy_sniper_pullback_reclaim"

        return False, "buy_sniper_not_confirmed"

    # =========================
    # SELL SNIPER
    # =========================
    if signal == "SELL":
        reference_level = pivot_resistance or pivot_break

        if reference_level is None:
            return False, "missing_sell_reference_level"

        pullback_touched = trigger["high"] >= reference_level - max(atr * 0.20, 0.5)

        bearish_reclaim = (
            trigger["close"] < trigger["open"]
            and trigger["close"] < reference_level
        )

        strong_close = trigger["close"] <= trigger["high"] - candle_range * 0.60
        momentum_ok = body >= atr * 0.15

        if (
            pullback_touched
            and bearish_reclaim
            and strong_close
            and momentum_ok
        ):
            return True, "sell_sniper_pullback_reclaim"

        return False, "sell_sniper_not_confirmed"

    return False, "invalid_signal"