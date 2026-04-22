from config.settings import (
    ATR_MIN,
    ATR_MAX,
    WT_CHANNEL_LENGTH,
    WT_AVERAGE_LENGTH,
    PIVOT_PROXIMITY_BUFFER,
    PIVOT_BREAK_BUFFER,
    WAVETREND_OVERBOUGHT,
    WAVETREND_OVERSOLD,
)

from src.wavetrend import calculate_wavetrend
from src.pivots import calculate_daily_pivots


def _nearest_levels(price, ordered_levels):
    below = None
    above = None

    for name, level in ordered_levels:
        if level <= price:
            below = (name, level)
        elif level > price and above is None:
            above = (name, level)

    return below, above


def generate_signal(df):
    if len(df) < 120:
        return None

    df = calculate_wavetrend(
        df.copy(),
        channel_length=WT_CHANNEL_LENGTH,
        average_length=WT_AVERAGE_LENGTH,
    )

    pivots = calculate_daily_pivots(df)
    if pivots is None:
        return None

    ordered_levels = pivots["ordered"]

    entry = df.iloc[-2]
    prev = df.iloc[-3]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    wt1 = entry["wt1"]
    wt2 = entry["wt2"]
    prev_wt1 = prev["wt1"]
    prev_wt2 = prev["wt2"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None
    
    # avoid dead market / weak scalp conditions
    if atr < 1.2:
        return None

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]
    if candle_range <= 0:
        return None

    upper_wick = entry["high"] - max(entry["open"], entry["close"])
    lower_wick = min(entry["open"], entry["close"]) - entry["low"]

    below, above = _nearest_levels(price, ordered_levels)

    # =========================================================
    # BUY rejection from pivot/support
    # wick touches level, close rejects upward
    # =========================================================
    if below is not None and above is not None:
        support_name, support_level = below
        resistance_name, resistance_level = above

        touched_support = entry["low"] <= support_level + PIVOT_PROXIMITY_BUFFER
        rejected_up = (
            lower_wick > body * 1.2
            and entry["close"] > support_level
            and entry["close"] > entry["open"]
        )

        bullish_cross = prev_wt1 <= prev_wt2 and wt1 > wt2
        oversold = wt1 <= WAVETREND_OVERSOLD or wt2 <= WAVETREND_OVERSOLD

        # anti-chase: do not buy if candle closed too far from support
        extension_from_support = entry["close"] - support_level
        not_late = extension_from_support <= atr * 0.45

        # anti-fake: must not close weakly near candle low
        close_quality = entry["close"] >= entry["low"] + candle_range * 0.6

        trend_ok = price > ema or abs(price - ema) <= atr * 0.2

        if (
            touched_support
            and rejected_up
            and bullish_cross
            and oversold
            and not_late
            and close_quality
            and trend_ok
        ):
            return {
                "signal": "BUY",
                "score": 97,
                "strategy": "WAVETREND_PIVOT",
                "entry_model": "PIVOT_REJECTION_PRECISION",
                "pivot_support_name": support_name,
                "pivot_support_level": support_level,
                "pivot_target_name": resistance_name,
                "pivot_target_level": resistance_level,
                "sl_reference": round(support_level - max(atr * 0.15, 0.5), 2),
                "reason": (
                    f"WaveTrend precision BUY -> wick touched {support_name} {round(support_level,2)} -> "
                    f"bullish rejection close -> WT bullish cross from oversold -> "
                    f"target {resistance_name} {round(resistance_level,2)}"
                ),
            }

    # =========================================================
    # SELL rejection from pivot/resistance
    # wick touches level, close rejects downward
    # =========================================================
    if below is not None and above is not None:
        support_name, support_level = below
        resistance_name, resistance_level = above

        touched_resistance = entry["high"] >= resistance_level - PIVOT_PROXIMITY_BUFFER
        rejected_down = (
            upper_wick > body * 1.2
            and entry["close"] < resistance_level
            and entry["close"] < entry["open"]
        )

        bearish_cross = prev_wt1 >= prev_wt2 and wt1 < wt2
        overbought = wt1 >= WAVETREND_OVERBOUGHT or wt2 >= WAVETREND_OVERBOUGHT

        extension_from_resistance = resistance_level - entry["close"]
        not_late = extension_from_resistance <= atr * 0.45

        close_quality = entry["close"] <= entry["high"] - candle_range * 0.6

        trend_ok = price < ema or abs(price - ema) <= atr * 0.2

        if (
            touched_resistance
            and rejected_down
            and bearish_cross
            and overbought
            and not_late
            and close_quality
            and trend_ok
        ):
            return {
                "signal": "SELL",
                "score": 97,
                "strategy": "WAVETREND_PIVOT",
                "entry_model": "PIVOT_REJECTION_PRECISION",
                "pivot_resistance_name": resistance_name,
                "pivot_resistance_level": resistance_level,
                "pivot_target_name": support_name,
                "pivot_target_level": support_level,
                "sl_reference": round(resistance_level + max(atr * 0.15, 0.5), 2),
                "reason": (
                    f"WaveTrend precision SELL -> wick touched {resistance_name} {round(resistance_level,2)} -> "
                    f"bearish rejection close -> WT bearish cross from overbought -> "
                    f"target {support_name} {round(support_level,2)}"
                ),
            }

    # =========================================================
    # BUY breakout + hold above pivot/resistance
    # =========================================================
    if above is not None:
        breakout_name, breakout_level = above

        broke_up = entry["close"] > breakout_level + PIVOT_BREAK_BUFFER
        bullish_wt = wt1 > wt2 and wt1 > 0
        bullish_body = body > atr * 0.2

        held_above = entry["low"] >= breakout_level - PIVOT_BREAK_BUFFER * 0.5
        close_quality = entry["close"] >= entry["low"] + candle_range * 0.7

        extension = entry["close"] - breakout_level
        not_overextended = extension <= atr * 0.7

        next_above = None
        found_current = False
        for name, level in ordered_levels:
            if found_current:
                next_above = (name, level)
                break
            if name == breakout_name and level == breakout_level:
                found_current = True

        if (
            broke_up
            and bullish_wt
            and bullish_body
            and held_above
            and close_quality
            and not_overextended
            and next_above is not None
        ):
            target_name, target_level = next_above
            return {
                "signal": "BUY",
                "score": 98,
                "strategy": "WAVETREND_PIVOT",
                "entry_model": "PIVOT_BREAKOUT_PRECISION",
                "pivot_break_name": breakout_name,
                "pivot_break_level": breakout_level,
                "pivot_target_name": target_name,
                "pivot_target_level": target_level,
                "sl_reference": round(breakout_level - max(atr * 0.15, 0.5), 2),
                "reason": (
                    f"WaveTrend precision breakout BUY -> strong hold above {breakout_name} {round(breakout_level,2)} -> "
                    f"WT bullish continuation -> target {target_name} {round(target_level,2)}"
                ),
            }

    # =========================================================
    # SELL breakout + hold below pivot/support
    # =========================================================
    if below is not None:
        breakdown_name, breakdown_level = below

        broke_down = entry["close"] < breakdown_level - PIVOT_BREAK_BUFFER
        bearish_wt = wt1 < wt2 and wt1 < 0
        bearish_body = body > atr * 0.2

        held_below = entry["high"] <= breakdown_level + PIVOT_BREAK_BUFFER * 0.5
        close_quality = entry["close"] <= entry["high"] - candle_range * 0.7

        extension = breakdown_level - entry["close"]
        not_overextended = extension <= atr * 0.7

        previous_below = None
        for name, level in ordered_levels:
            if level < breakdown_level:
                previous_below = (name, level)

        if (
            broke_down
            and bearish_wt
            and bearish_body
            and held_below
            and close_quality
            and not_overextended
            and previous_below is not None
        ):
            target_name, target_level = previous_below
            return {
                "signal": "SELL",
                "score": 98,
                "strategy": "WAVETREND_PIVOT",
                "entry_model": "PIVOT_BREAKOUT_PRECISION",
                "pivot_break_name": breakdown_name,
                "pivot_break_level": breakdown_level,
                "pivot_target_name": target_name,
                "pivot_target_level": target_level,
                "sl_reference": round(breakdown_level + max(atr * 0.15, 0.5), 2),
                "reason": (
                    f"WaveTrend precision breakout SELL -> strong hold below {breakdown_name} {round(breakdown_level,2)} -> "
                    f"WT bearish continuation -> target {target_name} {round(target_level,2)}"
                ),
            }

    return None