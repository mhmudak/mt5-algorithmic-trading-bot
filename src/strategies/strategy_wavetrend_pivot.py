import MetaTrader5 as mt5
import pandas as pd

from config.settings import (
    SYMBOL,
    EMA_PERIOD,
    ATR_PERIOD,
    ATR_MIN,
    ATR_MAX,
    WAVETREND_PIVOT_TIMEFRAME,
    WAVETREND_PIVOT_BARS,
    WT_CHANNEL_LENGTH,
    WT_AVERAGE_LENGTH,
    PIVOT_PROXIMITY_BUFFER,
    PIVOT_BREAK_BUFFER,
    WAVETREND_OVERBOUGHT,
    WAVETREND_OVERSOLD,
)

from src.indicators import calculate_ema, calculate_atr
from src.wavetrend import calculate_wavetrend
from src.pivots import calculate_daily_pivots
from src.logger import logger


MIN_ATR_FOR_M5_SCALP = 1.2
MIN_BODY_ATR_RATIO = 0.20
MAX_MIDDLE_ZONE_ATR = 0.60
MAX_LATE_ENTRY_ATR = 0.45

SL_ATR_BUFFER = 0.15
MIN_SL_BUFFER = 0.8
MAX_SL_BUFFER = 4.0


def _fetch_m5_data():
    rates = mt5.copy_rates_from_pos(
        SYMBOL,
        WAVETREND_PIVOT_TIMEFRAME,
        0,
        WAVETREND_PIVOT_BARS,
    )

    if rates is None or len(rates) < 120:
        logger.error(f"[WAVETREND_PIVOT] Failed to fetch M5 data: {mt5.last_error()}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)

    return df


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


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


def _dynamic_score(base_score, wt_cross, extreme_zone, body, atr, close_quality, entry_model):
    score = base_score

    if wt_cross:
        score += 3

    if extreme_zone:
        score += 2

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.45:
        score += 2

    if close_quality:
        score += 2

    if entry_model == "PIVOT_REJECTION_PRECISION":
        score += 2

    return min(score, 99)


def generate_signal(df):
    """
    Uses internal M5 data even if the main bot runs on M15.
    The main df is accepted only for compatibility with live_bot's strategy interface.
    """
    m5_df = _fetch_m5_data()

    if m5_df is None:
        return None

    m5_df = calculate_wavetrend(
        m5_df.copy(),
        channel_length=WT_CHANNEL_LENGTH,
        average_length=WT_AVERAGE_LENGTH,
    )

    pivots = calculate_daily_pivots(m5_df)
    if pivots is None:
        return None

    ordered_levels = pivots.get("ordered")
    if not ordered_levels:
        return None

    entry = m5_df.iloc[-2]
    prev = m5_df.iloc[-3]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    if atr < MIN_ATR_FOR_M5_SCALP:
        return None

    wt1 = entry["wt1"]
    wt2 = entry["wt2"]
    prev_wt1 = prev["wt1"]
    prev_wt2 = prev["wt2"]

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return None

    if body < atr * MIN_BODY_ATR_RATIO:
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

    distance_to_support = abs(price - support_level)
    distance_to_resistance = abs(price - resistance_level)

    in_middle_zone = (
        distance_to_support > atr * MAX_MIDDLE_ZONE_ATR
        and distance_to_resistance > atr * MAX_MIDDLE_ZONE_ATR
    )

    if in_middle_zone:
        return None

    ema_slope = m5_df["ema_20"].iloc[-2] - m5_df["ema_20"].iloc[-5]
    sl_buffer = _sl_buffer(atr)

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
    not_late = extension_from_support <= atr * MAX_LATE_ENTRY_ATR

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
        sl_reference = round(min(entry["low"], support_level) - sl_buffer, 2)
        tp_reference = round(resistance_level, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _dynamic_score(
            base_score=90,
            wt_cross=bullish_cross,
            extreme_zone=oversold,
            body=body,
            atr=atr,
            close_quality=close_buy_quality,
            entry_model="PIVOT_REJECTION_PRECISION",
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "WAVETREND_PIVOT",
            "entry_model": "PIVOT_REJECTION_PRECISION",
            "pattern_height": abs(tp_reference - entry["close"]),
            "pivot_support_name": support_name,
            "pivot_support_level": support_level,
            "pivot_target_name": resistance_name,
            "pivot_target_level": resistance_level,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "NEXT_DAILY_PIVOT_LEVEL",
            "momentum": "wavetrend_bullish_cross_from_oversold",
            "direction_context": "support_rejection_m5_precision",
            "reason": (
                f"WaveTrend M5 BUY -> wick touched {support_name} {round(support_level, 2)} -> "
                f"bullish rejection + WT cross from oversold -> "
                f"SL below support {sl_reference} -> "
                f"TP next pivot {resistance_name} {tp_reference}"
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
    not_late = extension_from_resistance <= atr * MAX_LATE_ENTRY_ATR

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
        sl_reference = round(max(entry["high"], resistance_level) + sl_buffer, 2)
        tp_reference = round(support_level, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _dynamic_score(
            base_score=90,
            wt_cross=bearish_cross,
            extreme_zone=overbought,
            body=body,
            atr=atr,
            close_quality=close_sell_quality,
            entry_model="PIVOT_REJECTION_PRECISION",
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "WAVETREND_PIVOT",
            "entry_model": "PIVOT_REJECTION_PRECISION",
            "pattern_height": abs(entry["close"] - tp_reference),
            "pivot_resistance_name": resistance_name,
            "pivot_resistance_level": resistance_level,
            "pivot_target_name": support_name,
            "pivot_target_level": support_level,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "NEXT_DAILY_PIVOT_LEVEL",
            "momentum": "wavetrend_bearish_cross_from_overbought",
            "direction_context": "resistance_rejection_m5_precision",
            "reason": (
                f"WaveTrend M5 SELL -> wick touched {resistance_name} {round(resistance_level, 2)} -> "
                f"bearish rejection + WT cross from overbought -> "
                f"SL above resistance {sl_reference} -> "
                f"TP next pivot {support_name} {tp_reference}"
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

        sl_reference = round(breakout_level - sl_buffer, 2)
        tp_reference = round(target_level, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _dynamic_score(
            base_score=91,
            wt_cross=bullish_wt,
            extreme_zone=wt1 > 0,
            body=body,
            atr=atr,
            close_quality=breakout_close_quality,
            entry_model="PIVOT_BREAKOUT_PRECISION",
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "WAVETREND_PIVOT",
            "entry_model": "PIVOT_BREAKOUT_PRECISION",
            "pattern_height": abs(tp_reference - entry["close"]),
            "pivot_break_name": breakout_name,
            "pivot_break_level": breakout_level,
            "pivot_target_name": target_name,
            "pivot_target_level": target_level,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "NEXT_DAILY_PIVOT_LEVEL",
            "momentum": "wavetrend_bullish_continuation",
            "direction_context": "pivot_breakout_hold_m5",
            "reason": (
                f"WaveTrend M5 breakout BUY -> strong hold above {breakout_name} {round(breakout_level, 2)} -> "
                f"WT bullish continuation -> SL below break {sl_reference} -> "
                f"TP next pivot {target_name} {tp_reference}"
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

        sl_reference = round(breakdown_level + sl_buffer, 2)
        tp_reference = round(target_level, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _dynamic_score(
            base_score=91,
            wt_cross=bearish_wt,
            extreme_zone=wt1 < 0,
            body=body,
            atr=atr,
            close_quality=breakdown_close_quality,
            entry_model="PIVOT_BREAKOUT_PRECISION",
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "WAVETREND_PIVOT",
            "entry_model": "PIVOT_BREAKOUT_PRECISION",
            "pattern_height": abs(entry["close"] - tp_reference),
            "pivot_break_name": breakdown_name,
            "pivot_break_level": breakdown_level,
            "pivot_target_name": target_name,
            "pivot_target_level": target_level,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "NEXT_DAILY_PIVOT_LEVEL",
            "momentum": "wavetrend_bearish_continuation",
            "direction_context": "pivot_breakdown_hold_m5",
            "reason": (
                f"WaveTrend M5 breakout SELL -> strong hold below {breakdown_name} {round(breakdown_level, 2)} -> "
                f"WT bearish continuation -> SL above break {sl_reference} -> "
                f"TP next pivot {target_name} {tp_reference}"
            ),
        }

    return None