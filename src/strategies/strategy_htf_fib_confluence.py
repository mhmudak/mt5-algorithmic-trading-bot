import MetaTrader5 as mt5
import pandas as pd

from config.settings import SYMBOL, EMA_PERIOD, ATR_PERIOD, ATR_MIN, ATR_MAX
from src.indicators import calculate_ema, calculate_atr
from src.logger import logger


FIB_HTF_TIMEFRAME = mt5.TIMEFRAME_H4
FIB_DAILY_TIMEFRAME = mt5.TIMEFRAME_D1
FIB_WEEKLY_TIMEFRAME = mt5.TIMEFRAME_W1

FIB_HTF_BARS = 180
FIB_DAILY_BARS = 120
FIB_WEEKLY_BARS = 80

FIB_SWING_LOOKBACK = 80

FIB_LEVELS = {
    "38.2": 0.382,
    "50.0": 0.500,
    "61.8": 0.618,
}

FIB_ENTRY_BUFFER_ATR = 0.25
FIB_MIN_BODY_ATR = 0.20
FIB_MIN_REJECTION_WICK_BODY = 0.80

FIB_SL_ATR_BUFFER = 0.25
FIB_MIN_SL_BUFFER = 2.0
FIB_MAX_SL_BUFFER = 6.0

FIB_EXTENSION_MULTIPLIER = 0.272
FIB_MIN_EXTENSION_ATR = 1.5
FIB_MAX_EXTENSION_ATR = 3.5


def _fetch_df(timeframe, bars):
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, bars)

    if rates is None or len(rates) < 50:
        logger.info(f"[HTF_FIB] Not enough data for timeframe={timeframe}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)

    return df


def _detect_bias(df):
    if df is None or len(df) < 10:
        return "NEUTRAL"

    closed = df.iloc[:-1]
    last = closed.iloc[-1]
    prev = closed.iloc[-5]

    close = last["close"]
    ema = last["ema_20"]
    ema_slope = last["ema_20"] - prev["ema_20"]

    if close > ema and ema_slope > 0:
        return "BUY"

    if close < ema and ema_slope < 0:
        return "SELL"

    return "NEUTRAL"


def _sl_buffer(atr):
    return min(max(atr * FIB_SL_ATR_BUFFER, FIB_MIN_SL_BUFFER), FIB_MAX_SL_BUFFER)


def _extension_target_distance(atr, swing_range):
    return min(
        max(swing_range * FIB_EXTENSION_MULTIPLIER, atr * FIB_MIN_EXTENSION_ATR),
        atr * FIB_MAX_EXTENSION_ATR,
    )


def _find_h4_swing(htf_df):
    """
    Finds the last clear H4 impulse using closed candles.
    Returns bullish swing if low occurs before high.
    Returns bearish swing if high occurs before low.
    """
    closed = htf_df.iloc[:-1].reset_index(drop=True)

    if len(closed) < FIB_SWING_LOOKBACK:
        return None

    window = closed.iloc[-FIB_SWING_LOOKBACK:].reset_index(drop=True)

    swing_low_idx = int(window["low"].idxmin())
    swing_high_idx = int(window["high"].idxmax())

    swing_low = window.iloc[swing_low_idx]["low"]
    swing_high = window.iloc[swing_high_idx]["high"]

    swing_range = swing_high - swing_low

    if swing_range <= 0:
        return None

    h4_bias = _detect_bias(htf_df)

    if swing_low_idx < swing_high_idx and h4_bias in ["BUY", "NEUTRAL"]:
        return {
            "direction": "BUY",
            "swing_low": swing_low,
            "swing_high": swing_high,
            "swing_range": swing_range,
            "swing_low_time": window.iloc[swing_low_idx].get("time"),
            "swing_high_time": window.iloc[swing_high_idx].get("time"),
        }

    if swing_high_idx < swing_low_idx and h4_bias in ["SELL", "NEUTRAL"]:
        return {
            "direction": "SELL",
            "swing_low": swing_low,
            "swing_high": swing_high,
            "swing_range": swing_range,
            "swing_low_time": window.iloc[swing_low_idx].get("time"),
            "swing_high_time": window.iloc[swing_high_idx].get("time"),
        }

    return None


def _fib_levels_for_swing(swing):
    direction = swing["direction"]
    low = swing["swing_low"]
    high = swing["swing_high"]
    swing_range = swing["swing_range"]

    if direction == "BUY":
        return {
            name: high - (ratio * swing_range)
            for name, ratio in FIB_LEVELS.items()
        }

    return {
        name: low + (ratio * swing_range)
        for name, ratio in FIB_LEVELS.items()
    }


def _nearest_fib_level(price, fib_levels):
    items = list(fib_levels.items())
    return min(items, key=lambda item: abs(price - item[1]))


def _score_setup(base_score, body, atr, fib_name, daily_aligned, weekly_aligned, rejection_quality):
    score = base_score

    if fib_name in ["50.0", "61.8"]:
        score += 2

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.50:
        score += 2

    if daily_aligned:
        score += 2

    if weekly_aligned:
        score += 1

    if rejection_quality:
        score += 2

    return min(score, 99)

def _local_confirmation(df, direction, atr):
    entry = df.iloc[-2]
    prev = df.iloc[-3]
    recent = df.iloc[-12:-2]

    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    reasons = []

    if direction == "BUY":
        liquidity_sweep = entry["low"] < recent_low and entry["close"] > recent_low
        bullish_bos = entry["close"] > prev["high"]
        ema_reclaim = entry["close"] > entry["ema_20"]

        if liquidity_sweep:
            reasons.append("sell_side_liquidity_sweep")
        if bullish_bos:
            reasons.append("bullish_bos")
        if ema_reclaim:
            reasons.append("ema_reclaim")

    else:
        liquidity_sweep = entry["high"] > recent_high and entry["close"] < recent_high
        bearish_bos = entry["close"] < prev["low"]
        ema_reject = entry["close"] < entry["ema_20"]

        if liquidity_sweep:
            reasons.append("buy_side_liquidity_sweep")
        if bearish_bos:
            reasons.append("bearish_bos")
        if ema_reject:
            reasons.append("ema_reject")

    return len(reasons) >= 2, reasons

def generate_signal(df):
    """
    HTF Fibonacci confluence strategy.

    H4: main Fib swing.
    D1/W1: directional context.
    M15: confirmation/rejection candle using main df.
    """
    if df is None or len(df) < 30:
        return None

    h4_df = _fetch_df(FIB_HTF_TIMEFRAME, FIB_HTF_BARS)
    d1_df = _fetch_df(FIB_DAILY_TIMEFRAME, FIB_DAILY_BARS)
    w1_df = _fetch_df(FIB_WEEKLY_TIMEFRAME, FIB_WEEKLY_BARS)

    if h4_df is None:
        return None

    swing = _find_h4_swing(h4_df)
    if swing is None:
        return None

    direction = swing["direction"]

    daily_bias = _detect_bias(d1_df)
    weekly_bias = _detect_bias(w1_df)

    # Daily should not strongly conflict.
    if daily_bias not in [direction, "NEUTRAL"]:
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

    if candle_range <= 0 or body < atr * FIB_MIN_BODY_ATR:
        return None

    fib_levels = _fib_levels_for_swing(swing)
    nearest_fib_name, nearest_fib_price = _nearest_fib_level(price, fib_levels)

    fib_zone_low = min(fib_levels.values())
    fib_zone_high = max(fib_levels.values())

    sl_buffer = _sl_buffer(atr)
    target_distance = _extension_target_distance(atr, swing["swing_range"])

    upper_wick = entry["high"] - max(entry["open"], entry["close"])
    lower_wick = min(entry["open"], entry["close"]) - entry["low"]

    # =========================
    # BUY Fib pullback confirmation
    # =========================
    if direction == "BUY":
        touched_fib_zone = (
            entry["low"] <= fib_zone_high + atr * FIB_ENTRY_BUFFER_ATR
            and entry["high"] >= fib_zone_low - atr * FIB_ENTRY_BUFFER_ATR
        )

        bullish_rejection = (
            entry["close"] > entry["open"]
            and entry["close"] > nearest_fib_price
            and lower_wick > body * FIB_MIN_REJECTION_WICK_BODY
            and entry["close"] >= entry["low"] + candle_range * 0.60
        )

        structure_reclaim = (
            entry["close"] > prev["high"]
            or entry["close"] > ema
        )

        if touched_fib_zone and bullish_rejection and structure_reclaim:
            local_confirmed, local_reasons = _local_confirmation(df, "BUY", atr)
            
            if not local_confirmed:
                return None
            
            sl_reference = round(min(entry["low"], fib_levels["61.8"]) - sl_buffer, 2)

            if swing["swing_high"] > entry["close"]:
                tp_reference = swing["swing_high"]
                target_model = "H4_SWING_HIGH"
            else:
                tp_reference = entry["close"] + target_distance
                target_model = "FIB_EXTENSION_TARGET"

            tp_reference = round(tp_reference, 2)

            if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
                return None

            score = _score_setup(
                base_score=92,
                body=body,
                atr=atr,
                fib_name=nearest_fib_name,
                daily_aligned=daily_bias == direction,
                weekly_aligned=weekly_bias == direction,
                rejection_quality=lower_wick > body * 1.2,
            )

            return {
                "signal": "BUY",
                "score": score,
                "strategy": "HTF_FIB_CONFLUENCE",
                "entry_model": "H4_FIB_RETRACE_M15_RECLAIM",
                "pattern_height": abs(tp_reference - entry["close"]),
                "fib_direction": direction,
                "fib_level_name": nearest_fib_name,
                "fib_level_price": round(nearest_fib_price, 2),
                "fib_382": round(fib_levels["38.2"], 2),
                "fib_500": round(fib_levels["50.0"], 2),
                "fib_618": round(fib_levels["61.8"], 2),
                "swing_low": swing["swing_low"],
                "swing_high": swing["swing_high"],
                "daily_bias": daily_bias,
                "weekly_bias": weekly_bias,
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": target_model,
                "momentum": "bullish_fib_rejection_reclaim",
                "direction_context": "h4_bullish_fib_daily_context",
                "local_confirmation": local_reasons,
                "reason": (
                    f"HTF Fib BUY -> H4 bullish swing "
                    f"{round(swing['swing_low'], 2)}-{round(swing['swing_high'], 2)} -> "
                    f"price rejected Fib {nearest_fib_name} at {round(nearest_fib_price, 2)} -> "
                    f"local confirmation={','.join(local_reasons)} -> "
                    f"SL {sl_reference} -> TP {target_model} {tp_reference}"
                ),
            }

    # =========================
    # SELL Fib pullback confirmation
    # =========================
    if direction == "SELL":
        touched_fib_zone = (
            entry["high"] >= fib_zone_low - atr * FIB_ENTRY_BUFFER_ATR
            and entry["low"] <= fib_zone_high + atr * FIB_ENTRY_BUFFER_ATR
        )

        bearish_rejection = (
            entry["close"] < entry["open"]
            and entry["close"] < nearest_fib_price
            and upper_wick > body * FIB_MIN_REJECTION_WICK_BODY
            and entry["close"] <= entry["high"] - candle_range * 0.60
        )

        structure_reject = (
            entry["close"] < prev["low"]
            or entry["close"] < ema
        )

        if touched_fib_zone and bearish_rejection and structure_reject:
            local_confirmed, local_reasons = _local_confirmation(df, "SELL", atr)

            if not local_confirmed:
                return None
            
            sl_reference = round(max(entry["high"], fib_levels["61.8"]) + sl_buffer, 2)

            if swing["swing_low"] < entry["close"]:
                tp_reference = swing["swing_low"]
                target_model = "H4_SWING_LOW"
            else:
                tp_reference = entry["close"] - target_distance
                target_model = "FIB_EXTENSION_TARGET"

            tp_reference = round(tp_reference, 2)

            if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
                return None

            score = _score_setup(
                base_score=92,
                body=body,
                atr=atr,
                fib_name=nearest_fib_name,
                daily_aligned=daily_bias == direction,
                weekly_aligned=weekly_bias == direction,
                rejection_quality=upper_wick > body * 1.2,
            )

            return {
                "signal": "SELL",
                "score": score,
                "strategy": "HTF_FIB_CONFLUENCE",
                "entry_model": "H4_FIB_RETRACE_M15_REJECT",
                "pattern_height": abs(entry["close"] - tp_reference),
                "fib_direction": direction,
                "fib_level_name": nearest_fib_name,
                "fib_level_price": round(nearest_fib_price, 2),
                "fib_382": round(fib_levels["38.2"], 2),
                "fib_500": round(fib_levels["50.0"], 2),
                "fib_618": round(fib_levels["61.8"], 2),
                "swing_low": swing["swing_low"],
                "swing_high": swing["swing_high"],
                "daily_bias": daily_bias,
                "weekly_bias": weekly_bias,
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": target_model,
                "momentum": "bearish_fib_rejection_reclaim",
                "direction_context": "h4_bearish_fib_daily_context",
                "local_confirmation": local_reasons,
                "reason": (
                    f"HTF Fib SELL -> H4 bearish swing "
                    f"{round(swing['swing_high'], 2)}-{round(swing['swing_low'], 2)} -> "
                    f"price rejected Fib {nearest_fib_name} at {round(nearest_fib_price, 2)} -> "
                    f"local confirmation={','.join(local_reasons)} -> "
                    f"SL {sl_reference} -> TP {target_model} {tp_reference}"
                ),
            }

    return None