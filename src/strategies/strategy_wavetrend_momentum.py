import MetaTrader5 as mt5
import pandas as pd

from config.settings import (
    SYMBOL,
    EMA_PERIOD,
    ATR_PERIOD,
    ATR_MIN,
    ATR_MAX,
    WT_CHANNEL_LENGTH,
    WT_AVERAGE_LENGTH,
    WAVETREND_MOMENTUM_EXTRA_SL_PRICE,
)

from src.indicators import calculate_ema, calculate_atr
from src.wavetrend import calculate_wavetrend
from src.strategy_debug import reject_strategy
from src.logger import logger


WT_MOMENTUM_TIMEFRAME = mt5.TIMEFRAME_M5
WT_MOMENTUM_BARS = 240

WT_MOMENTUM_MIN_MAX_STOP_DISTANCE = 6.0
WT_MOMENTUM_MAX_STOP_ATR_MULTIPLIER = 2.0

MIN_MOMENTUM_ATR = 0.8
MIN_BODY_ATR_RATIO = 0.18

MAX_EMA_EXTENSION_ATR = 1.35

SL_ATR_BUFFER = 0.25
MIN_SL_BUFFER = 1.5
MAX_SL_BUFFER = 5.0

TARGET_ATR_MIN = 1.5
TARGET_ATR_MAX = 3.0


def _fetch_m5_data():
    rates = mt5.copy_rates_from_pos(
        SYMBOL,
        WT_MOMENTUM_TIMEFRAME,
        0,
        WT_MOMENTUM_BARS,
    )

    if rates is None or len(rates) < 80:
        logger.error(f"[WAVETREND_MOMENTUM] Failed to fetch M5 data: {mt5.last_error()}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)

    return df


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, structure_range):
    return min(
        max(structure_range * 0.60, atr * TARGET_ATR_MIN),
        atr * TARGET_ATR_MAX,
    )


def _score_setup(base_score, wt_cross, trend_aligned, body, atr, close_quality):
    score = base_score

    if wt_cross:
        score += 3

    if trend_aligned:
        score += 2

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.45:
        score += 2

    if close_quality:
        score += 2

    return min(score, 99)


def generate_signal(df):
    """
    M5 WaveTrend momentum strategy.

    This does not require daily pivot levels.
    It is designed to catch clean M5 momentum when WaveTrend, EMA slope,
    candle body, and close quality all agree.
    """
    m5_df = _fetch_m5_data()

    if m5_df is None:
        return reject_strategy("WAVETREND_MOMENTUM", "m5_data_unavailable")

    m5_df = calculate_wavetrend(
        m5_df.copy(),
        channel_length=WT_CHANNEL_LENGTH,
        average_length=WT_AVERAGE_LENGTH,
    )

    if len(m5_df) < 80:
        return reject_strategy(
            "WAVETREND_MOMENTUM",
            "not_enough_wavetrend_data",
            bars=len(m5_df),
        )

    entry = m5_df.iloc[-2]
    prev = m5_df.iloc[-3]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return reject_strategy("WAVETREND_MOMENTUM", "atr_out_of_range", atr=round(atr, 2))

    if atr < MIN_MOMENTUM_ATR:
        return reject_strategy("WAVETREND_MOMENTUM", "atr_too_low", atr=round(atr, 2))

    wt1 = entry["wt1"]
    wt2 = entry["wt2"]
    prev_wt1 = prev["wt1"]
    prev_wt2 = prev["wt2"]

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return reject_strategy("WAVETREND_MOMENTUM", "invalid_candle_range")

    if body < atr * MIN_BODY_ATR_RATIO:
        return reject_strategy(
            "WAVETREND_MOMENTUM",
            "body_too_small",
            body=round(body, 2),
            required=round(atr * MIN_BODY_ATR_RATIO, 2),
        )

    recent = m5_df.iloc[-35:-2]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()
    structure_range = recent_high - recent_low

    if structure_range <= 0:
        return reject_strategy("WAVETREND_MOMENTUM", "invalid_structure_range")

    ema_slope = m5_df["ema_20"].iloc[-2] - m5_df["ema_20"].iloc[-8]
    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, structure_range)

    close_buy_quality = entry["close"] >= entry["low"] + candle_range * 0.65
    close_sell_quality = entry["close"] <= entry["high"] - candle_range * 0.65

    # =========================================================
    # BUY momentum
    # =========================================================
    bullish_cross = prev_wt1 <= prev_wt2 and wt1 > wt2
    bullish_continuation = wt1 > wt2 and wt1 > 0

    bullish_trend = price > ema and ema_slope >= 0
    not_overextended = price - ema <= atr * MAX_EMA_EXTENSION_ATR

    bullish_momentum = (
        entry["close"] > entry["open"]
        and close_buy_quality
        and body >= atr * MIN_BODY_ATR_RATIO
    )

    if (
        bullish_trend
        and not_overextended
        and bullish_momentum
        and (bullish_cross or bullish_continuation)
    ):
        micro_sl = min(entry["low"], prev["low"])
        structure_sl = recent_low

        # Prefer micro-structure SL first
        sl_reference = round(micro_sl - sl_buffer, 2)

        # If micro SL is invalid, fallback to wider structure SL
        if sl_reference >= entry["close"]:
            sl_reference = round(structure_sl - sl_buffer, 2)
        
        sl_reference = round(sl_reference - WAVETREND_MOMENTUM_EXTRA_SL_PRICE, 2)
            
        stop_distance = entry["close"] - sl_reference

        max_stop_distance = max(
            WT_MOMENTUM_MIN_MAX_STOP_DISTANCE,
            atr * WT_MOMENTUM_MAX_STOP_ATR_MULTIPLIER,
        )
        
        if stop_distance > max_stop_distance:
            return reject_strategy(
                "WAVETREND_MOMENTUM",
                "stop_distance_too_wide",
                stop_distance=round(stop_distance, 2),
                max_allowed=round(max_stop_distance, 2),
            )

        if recent_high > entry["close"]:
            tp_reference = recent_high
            target_model = "RECENT_M5_STRUCTURE_HIGH"
        else:
            tp_reference = entry["close"] + target_distance
            target_model = "WT_MOMENTUM_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return reject_strategy(
                "WAVETREND_MOMENTUM",
                "invalid_buy_sl_tp",
                entry=round(entry["close"], 2),
                sl=sl_reference,
                tp=tp_reference,
            )

        entry_model = "WT_M5_BULLISH_CROSS" if bullish_cross else "WT_M5_BULLISH_CONTINUATION"

        score = _score_setup(
            base_score=91,
            wt_cross=bullish_cross,
            trend_aligned=bullish_trend,
            body=body,
            atr=atr,
            close_quality=close_buy_quality,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "WAVETREND_MOMENTUM",
            "entry_model": entry_model,
            "pattern_height": abs(tp_reference - entry["close"]),
            "recent_high": recent_high,
            "recent_low": recent_low,
            "wt1": wt1,
            "wt2": wt2,
            "ema_value": ema,
            "ema_slope": round(ema_slope, 4),
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "wavetrend_m5_bullish_momentum",
            "direction_context": "m5_price_above_ema_wt_bullish",
            "reason": (
                f"WaveTrend Momentum BUY -> {entry_model} -> "
                f"price above EMA {round(ema, 2)} -> "
                f"WT1 {round(wt1, 2)} WT2 {round(wt2, 2)} -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
            ),
        }

    # =========================================================
    # SELL momentum
    # =========================================================
    bearish_cross = prev_wt1 >= prev_wt2 and wt1 < wt2
    bearish_continuation = wt1 < wt2 and wt1 < 0

    bearish_trend = price < ema and ema_slope <= 0
    not_overextended = ema - price <= atr * MAX_EMA_EXTENSION_ATR

    bearish_momentum = (
        entry["close"] < entry["open"]
        and close_sell_quality
        and body >= atr * MIN_BODY_ATR_RATIO
    )

    if (
        bearish_trend
        and not_overextended
        and bearish_momentum
        and (bearish_cross or bearish_continuation)
    ):
        micro_sl = max(entry["high"], prev["high"])
        structure_sl = recent_high
        
        # Prefer micro-structure SL first
        sl_reference = round(micro_sl + sl_buffer, 2)
        
        # If micro SL is invalid, fallback to wider structure SL
        if sl_reference <= entry["close"]:
            sl_reference = round(structure_sl + sl_buffer, 2)
            
        sl_reference = round(sl_reference + WAVETREND_MOMENTUM_EXTRA_SL_PRICE, 2)
            
        stop_distance = sl_reference - entry["close"]

        max_stop_distance = max(
            WT_MOMENTUM_MIN_MAX_STOP_DISTANCE,
            atr * WT_MOMENTUM_MAX_STOP_ATR_MULTIPLIER,
        )
        
        if stop_distance > max_stop_distance:
            return reject_strategy(
                "WAVETREND_MOMENTUM",
                "stop_distance_too_wide",
                stop_distance=round(stop_distance, 2),
                max_allowed=round(max_stop_distance, 2),
            )

        if recent_low < entry["close"]:
            tp_reference = recent_low
            target_model = "RECENT_M5_STRUCTURE_LOW"
        else:
            tp_reference = entry["close"] - target_distance
            target_model = "WT_MOMENTUM_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return reject_strategy(
                "WAVETREND_MOMENTUM",
                "invalid_sell_sl_tp",
                entry=round(entry["close"], 2),
                sl=sl_reference,
                tp=tp_reference,
            )

        entry_model = "WT_M5_BEARISH_CROSS" if bearish_cross else "WT_M5_BEARISH_CONTINUATION"

        score = _score_setup(
            base_score=91,
            wt_cross=bearish_cross,
            trend_aligned=bearish_trend,
            body=body,
            atr=atr,
            close_quality=close_sell_quality,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "WAVETREND_MOMENTUM",
            "entry_model": entry_model,
            "pattern_height": abs(entry["close"] - tp_reference),
            "recent_high": recent_high,
            "recent_low": recent_low,
            "wt1": wt1,
            "wt2": wt2,
            "ema_value": ema,
            "ema_slope": round(ema_slope, 4),
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "wavetrend_m5_bearish_momentum",
            "direction_context": "m5_price_below_ema_wt_bearish",
            "reason": (
                f"WaveTrend Momentum SELL -> {entry_model} -> "
                f"price below EMA {round(ema, 2)} -> "
                f"WT1 {round(wt1, 2)} WT2 {round(wt2, 2)} -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
            ),
        }

    return reject_strategy(
        "WAVETREND_MOMENTUM",
        "no_valid_wavetrend_momentum_setup",
        price=round(price, 2),
        ema=round(ema, 2),
        ema_slope=round(ema_slope, 4),
        wt1=round(wt1, 2),
        wt2=round(wt2, 2),
        bullish_cross=bullish_cross,
        bearish_cross=bearish_cross,
    )