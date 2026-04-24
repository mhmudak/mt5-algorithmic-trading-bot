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


def _next_above_level(current_name, current_level, ordered_levels):
    found_current = False

    for name, level in ordered_levels:
        if found_current:
            return name, level

        if name == current_name and level == current_level:
            found_current = True

    return None


def _previous_below_level(current_level, ordered_levels):
    previous = None

    for name, level in ordered_levels:
        if level < current_level:
            previous = (name, level)

    return previous


def _dynamic_score(base_score, wt_cross, extreme_zone, body, atr, close_quality):
    score = base_score

    if wt_cross:
        score += 3

    if extreme_zone:
        score += 2

    if body > atr * 0.30:
        score += 3

    if close_quality:
        score += 2

    return min(score, 99)


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

    # Avoid dead market / weak scalp conditions
    if atr < 1.2:
        return None

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return None

    upper_wick = entry["high"] - max(entry["open"], entry["close"])
    lower_wick = min(entry["open"], entry["close"]) - entry["low"]

    close_buy_quality = entry["close"] >= entry["low"] + candle_range * 0.60
    close_sell_quality = entry["close"] <= entry["high"] - candle_range * 0.60

    momentum_ok = body > atr * 0.25

    below, above = _nearest_levels(price, ordered_levels)

    if below is None or above is None:
        return None

    support_name, support_level = below
    resistance_name, resistance_level = above

    # =========================
    # NO MIDDLE-ZONE TRADING
    # =========================
    distance_to_support = abs(price - support_level)
    distance_to_resistance = abs(price - resistance_level)

    in_middle_zone = (
        distance_to_support > atr * 0.60
        and distance_to_resistance > atr * 0.60
    )

    if in_middle_zone:
        return None

    ema_slope = df["ema_20"].iloc[-2] - df["ema_20"].iloc[-5]

    # =========================================================
    # BUY rejection from pivot/support
    # =========================================================
    touched_support = entry["low"] <= support_level + PIVOT_PROXIMITY_BUFFER

    rejected_up = (
        lower_wick > body * 1.2
        and entry["close"] > support_level
        and entry["close"] > entry["open"]
    )

    bullish_cross = prev_wt1 <= prev_wt2 and wt1 > wt2
    oversold = wt1 <= WAVETREND_OVERSOLD or wt2 <= WAVETREND_OVERSOLD

    extension_from_support = entry["close"] - support_level
    not_late = extension_from_support <= atr * 0.45

    buy_trend_ok = (
        ema_slope > 0
        or price > ema
        or abs(price - ema) <= atr * 0.20
    )

    if (
        touched_support
        and rejected_up
        and bullish_cross
        and oversold
        and not_late
        and close_buy_quality
        and momentum_ok
        and buy_trend_ok
    ):
        score = _dynamic_score(
            base_score=90,
            wt_cross=bullish_cross,
            extreme_zone=oversold,
            body=body,
            atr=atr,
            close_quality=close_buy_quality,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "WAVETREND_PIVOT",
            "entry_model": "PIVOT_REJECTION_PRECISION",
            "pivot_support_name": support_name,
            "pivot_support_level": support_level,
            "pivot_target_name": resistance_name,
            "pivot_target_level": resistance_level,
            "sl_reference": round(support_level - max(atr * 0.15, 0.5), 2),
            "reason": (
                f"WaveTrend precision BUY -> wick touched {support_name} {round(support_level, 2)} -> "
                f"bullish rejection -> WT bullish cross from oversold -> "
                f"momentum confirmed -> target {resistance_name} {round(resistance_level, 2)}"
            ),
        }

    # =========================================================
    # SELL rejection from pivot/resistance
    # =========================================================
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

    sell_trend_ok = (
        ema_slope < 0
        or price < ema
        or abs(price - ema) <= atr * 0.20
    )

    if (
        touched_resistance
        and rejected_down
        and bearish_cross
        and overbought
        and not_late
        and close_sell_quality
        and momentum_ok
        and sell_trend_ok
    ):
        score = _dynamic_score(
            base_score=90,
            wt_cross=bearish_cross,
            extreme_zone=overbought,
            body=body,
            atr=atr,
            close_quality=close_sell_quality,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "WAVETREND_PIVOT",
            "entry_model": "PIVOT_REJECTION_PRECISION",
            "pivot_resistance_name": resistance_name,
            "pivot_resistance_level": resistance_level,
            "pivot_target_name": support_name,
            "pivot_target_level": support_level,
            "sl_reference": round(resistance_level + max(atr * 0.15, 0.5), 2),
            "reason": (
                f"WaveTrend precision SELL -> wick touched {resistance_name} {round(resistance_level, 2)} -> "
                f"bearish rejection -> WT bearish cross from overbought -> "
                f"momentum confirmed -> target {support_name} {round(support_level, 2)}"
            ),
        }

    # =========================================================
    # BUY breakout + hold above pivot/resistance
    # =========================================================
    breakout_name, breakout_level = resistance_name, resistance_level

    fake_break_up = entry["high"] > breakout_level and entry["close"] < breakout_level
    if fake_break_up:
        return None

    broke_up = entry["close"] > breakout_level + PIVOT_BREAK_BUFFER
    bullish_wt = wt1 > wt2 and wt1 > 0
    bullish_body = body > atr * 0.25
    held_above = entry["low"] >= breakout_level - PIVOT_BREAK_BUFFER * 0.5
    breakout_close_quality = entry["close"] >= entry["low"] + candle_range * 0.70

    extension = entry["close"] - breakout_level
    not_overextended = extension <= atr * 0.70

    next_above = _next_above_level(breakout_name, breakout_level, ordered_levels)

    if (
        broke_up
        and bullish_wt
        and bullish_body
        and held_above
        and breakout_close_quality
        and not_overextended
        and momentum_ok
        and ema_slope >= 0
        and next_above is not None
    ):
        target_name, target_level = next_above

        score = _dynamic_score(
            base_score=91,
            wt_cross=bullish_wt,
            extreme_zone=wt1 > 0,
            body=body,
            atr=atr,
            close_quality=breakout_close_quality,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "WAVETREND_PIVOT",
            "entry_model": "PIVOT_BREAKOUT_PRECISION",
            "pivot_break_name": breakout_name,
            "pivot_break_level": breakout_level,
            "pivot_target_name": target_name,
            "pivot_target_level": target_level,
            "sl_reference": round(breakout_level - max(atr * 0.15, 0.5), 2),
            "reason": (
                f"WaveTrend precision breakout BUY -> strong hold above {breakout_name} {round(breakout_level, 2)} -> "
                f"WT bullish continuation -> no fake break -> target {target_name} {round(target_level, 2)}"
            ),
        }

    # =========================================================
    # SELL breakout + hold below pivot/support
    # =========================================================
    breakdown_name, breakdown_level = support_name, support_level

    fake_break_down = entry["low"] < breakdown_level and entry["close"] > breakdown_level
    if fake_break_down:
        return None

    broke_down = entry["close"] < breakdown_level - PIVOT_BREAK_BUFFER
    bearish_wt = wt1 < wt2 and wt1 < 0
    bearish_body = body > atr * 0.25
    held_below = entry["high"] <= breakdown_level + PIVOT_BREAK_BUFFER * 0.5
    breakdown_close_quality = entry["close"] <= entry["high"] - candle_range * 0.70

    extension = breakdown_level - entry["close"]
    not_overextended = extension <= atr * 0.70

    previous_below = _previous_below_level(breakdown_level, ordered_levels)

    if (
        broke_down
        and bearish_wt
        and bearish_body
        and held_below
        and breakdown_close_quality
        and not_overextended
        and momentum_ok
        and ema_slope <= 0
        and previous_below is not None
    ):
        target_name, target_level = previous_below

        score = _dynamic_score(
            base_score=91,
            wt_cross=bearish_wt,
            extreme_zone=wt1 < 0,
            body=body,
            atr=atr,
            close_quality=breakdown_close_quality,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "WAVETREND_PIVOT",
            "entry_model": "PIVOT_BREAKOUT_PRECISION",
            "pivot_break_name": breakdown_name,
            "pivot_break_level": breakdown_level,
            "pivot_target_name": target_name,
            "pivot_target_level": target_level,
            "sl_reference": round(breakdown_level + max(atr * 0.15, 0.5), 2),
            "reason": (
                f"WaveTrend precision breakout SELL -> strong hold below {breakdown_name} {round(breakdown_level, 2)} -> "
                f"WT bearish continuation -> no fake break -> target {target_name} {round(target_level, 2)}"
            ),
        }

    return None