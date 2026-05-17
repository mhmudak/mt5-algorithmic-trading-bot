import MetaTrader5 as mt5
import pandas as pd

from config.settings import (
    SYMBOL,
    EMA_PERIOD,
    ATR_PERIOD,
    ENABLE_ELLIOTT_FIB_CONTEXT,
    ELLIOTT_FIB_CONTEXT_BOOST,
    ELLIOTT_FIB_CONFLICT_PENALTY,
)
from src.indicators import calculate_ema, calculate_atr
from src.logger import logger


ELLIOTT_FIB_TIMEFRAMES = [
    ("H4", mt5.TIMEFRAME_H4),
    ("H1", mt5.TIMEFRAME_H1),
]

ELLIOTT_FIB_BARS = 160
ELLIOTT_SWING_LOOKBACK = 80

FIB_LEVELS = {
    "38.2": 0.382,
    "50.0": 0.500,
    "61.8": 0.618,
}

FIB_ZONE_BUFFER_ATR = 0.35
MIN_IMPULSE_ATR = 2.0


def _fetch_df(timeframe, bars):
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, bars)

    if rates is None or len(rates) < 50:
        logger.info(f"[ELLIOTT FIB] Not enough data for timeframe={timeframe}")
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


def _find_impulse_swing(df):
    closed = df.iloc[:-1].reset_index(drop=True)

    if len(closed) < ELLIOTT_SWING_LOOKBACK:
        return None

    window = closed.iloc[-ELLIOTT_SWING_LOOKBACK:].reset_index(drop=True)

    low_idx = int(window["low"].idxmin())
    high_idx = int(window["high"].idxmax())

    swing_low = window.iloc[low_idx]["low"]
    swing_high = window.iloc[high_idx]["high"]
    swing_range = swing_high - swing_low

    atr = window.iloc[-1]["atr_14"]

    if atr <= 0:
        return None

    if swing_range < atr * MIN_IMPULSE_ATR:
        return None

    if low_idx < high_idx:
        direction = "BUY"
    elif high_idx < low_idx:
        direction = "SELL"
    else:
        return None

    return {
        "direction": direction,
        "swing_low": swing_low,
        "swing_high": swing_high,
        "swing_range": swing_range,
        "atr": atr,
    }


def _fib_levels(swing):
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


def _price_near_fib_zone(price, fib_levels, atr):
    zone_low = min(fib_levels.values())
    zone_high = max(fib_levels.values())
    buffer = atr * FIB_ZONE_BUFFER_ATR

    return (
        zone_low - buffer <= price <= zone_high + buffer,
        zone_low,
        zone_high,
    )


def analyze_elliott_fib_context(df):
    if not ENABLE_ELLIOTT_FIB_CONTEXT:
        return None

    if df is None or len(df) < 20:
        return None

    current = df.iloc[-2]
    price = current["close"]

    contexts = []

    for label, timeframe in ELLIOTT_FIB_TIMEFRAMES:
        htf_df = _fetch_df(timeframe, ELLIOTT_FIB_BARS)

        if htf_df is None:
            continue

        swing = _find_impulse_swing(htf_df)

        if swing is None:
            continue

        bias = _detect_bias(htf_df)
        fibs = _fib_levels(swing)

        near_zone, zone_low, zone_high = _price_near_fib_zone(
            price,
            fibs,
            swing["atr"],
        )

        if not near_zone:
            continue

        if bias not in [swing["direction"], "NEUTRAL"]:
            continue

        contexts.append(
            {
                "timeframe": label,
                "bias": swing["direction"],
                "htf_bias": bias,
                "fib_382": round(fibs["38.2"], 2),
                "fib_500": round(fibs["50.0"], 2),
                "fib_618": round(fibs["61.8"], 2),
                "zone_low": round(zone_low, 2),
                "zone_high": round(zone_high, 2),
                "swing_low": round(swing["swing_low"], 2),
                "swing_high": round(swing["swing_high"], 2),
                "reasons": [
                    f"{label}_impulse_{swing['direction'].lower()}",
                    f"{label}_fib_golden_zone",
                ],
            }
        )

    if not contexts:
        logger.info("[ELLIOTT FIB] No active context")
        return None

    # Prefer H4 context if available
    contexts = sorted(
        contexts,
        key=lambda item: 0 if item["timeframe"] == "H4" else 1,
    )

    context = contexts[0]

    logger.info(
        f"[ELLIOTT FIB] context={context['bias']} "
        f"tf={context['timeframe']} "
        f"zone={context['zone_low']}-{context['zone_high']}"
    )

    return context


def apply_elliott_fib_confirmation(signal_data, context):
    if not ENABLE_ELLIOTT_FIB_CONTEXT:
        return 0, []

    if not signal_data or context is None:
        return 0, []

    signal = signal_data.get("signal")

    if signal not in ["BUY", "SELL"]:
        return 0, []

    bias = context.get("bias")
    reasons = context.get("reasons", [])

    if bias == signal:
        return ELLIOTT_FIB_CONTEXT_BOOST, [
            "elliott_fib_aligned",
            *reasons,
        ]

    if bias in ["BUY", "SELL"] and bias != signal:
        return -ELLIOTT_FIB_CONFLICT_PENALTY, [
            f"elliott_fib_conflict_{bias.lower()}",
        ]

    return 0, []