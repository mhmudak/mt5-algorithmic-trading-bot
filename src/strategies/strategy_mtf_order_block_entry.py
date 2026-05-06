import MetaTrader5 as mt5
import pandas as pd

from config.settings import SYMBOL, ATR_MIN, ATR_MAX, EMA_PERIOD, ATR_PERIOD
from src.indicators import calculate_ema, calculate_atr
from src.logger import logger


HTF_TIMEFRAME = mt5.TIMEFRAME_H4
CONFIRM_TIMEFRAME = mt5.TIMEFRAME_M15
ENTRY_TIMEFRAME = mt5.TIMEFRAME_M1

HTF_BARS = 120
CONFIRM_BARS = 120
ENTRY_BARS = 120

HTF_OB_LOOKBACK = 40

ZONE_ATR_BUFFER = 0.25
MIN_DISPLACEMENT_ATR = 0.35
MIN_ENTRY_BODY_ATR = 0.15

SL_ATR_BUFFER = 0.25
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 7.0

TARGET_ATR_MIN = 1.5
TARGET_ATR_MAX = 4.0


def _fetch_df(timeframe, bars):
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, bars)

    if rates is None or len(rates) < 50:
        logger.error(f"[MTF_OB_ENTRY] Failed to fetch rates | timeframe={timeframe}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)

    return df


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, zone_height):
    return min(max(zone_height * 2, atr * TARGET_ATR_MIN), atr * TARGET_ATR_MAX)


def _find_htf_order_block(htf_df):
    """
    Detects the most recent 4H demand/supply zone based on displacement.
    Uses closed candles only.
    """
    closed = htf_df.iloc[:-1].reset_index(drop=True)

    if len(closed) < HTF_OB_LOOKBACK:
        return None

    recent = closed.iloc[-HTF_OB_LOOKBACK:].reset_index(drop=True)

    for i in range(len(recent) - 3, 3, -1):
        base = recent.iloc[i - 1]
        displacement = recent.iloc[i]

        atr = displacement["atr_14"]
        body = abs(displacement["close"] - displacement["open"])

        if atr <= 0 or body < atr * MIN_DISPLACEMENT_ATR:
            continue

        # Bullish OB: last bearish candle before bullish displacement
        if (
            base["close"] < base["open"]
            and displacement["close"] > displacement["open"]
            and displacement["close"] > base["high"]
        ):
            return {
                "direction": "BUY",
                "zone_low": base["low"],
                "zone_high": base["high"],
                "zone_time": base.get("time"),
                "displacement_close": displacement["close"],
                "atr": atr,
            }

        # Bearish OB: last bullish candle before bearish displacement
        if (
            base["close"] > base["open"]
            and displacement["close"] < displacement["open"]
            and displacement["close"] < base["low"]
        ):
            return {
                "direction": "SELL",
                "zone_low": base["low"],
                "zone_high": base["high"],
                "zone_time": base.get("time"),
                "displacement_close": displacement["close"],
                "atr": atr,
            }

    return None


def _price_in_zone(price, zone_low, zone_high, atr):
    buffer = atr * ZONE_ATR_BUFFER
    return zone_low - buffer <= price <= zone_high + buffer


def _confirm_m15(confirm_df, direction, zone_low, zone_high):
    """
    M15 confirmation: price reaches HTF zone and shows BOS/displacement away.
    """
    closed = confirm_df.iloc[:-1].reset_index(drop=True)

    if len(closed) < 10:
        return None

    entry = closed.iloc[-1]
    prev = closed.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    body = abs(entry["close"] - entry["open"])

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    if body < atr * MIN_DISPLACEMENT_ATR:
        return None

    touched_zone = entry["low"] <= zone_high and entry["high"] >= zone_low

    if not touched_zone:
        return None

    if direction == "BUY":
        bullish_shift = (
            entry["close"] > entry["open"]
            and entry["close"] > prev["high"]
            and entry["close"] > ema
        )

        if bullish_shift:
            return {
                "confirm_level": entry["high"],
                "confirm_low": entry["low"],
                "confirm_high": entry["high"],
                "momentum": "m15_bullish_bos",
            }

    if direction == "SELL":
        bearish_shift = (
            entry["close"] < entry["open"]
            and entry["close"] < prev["low"]
            and entry["close"] < ema
        )

        if bearish_shift:
            return {
                "confirm_level": entry["low"],
                "confirm_low": entry["low"],
                "confirm_high": entry["high"],
                "momentum": "m15_bearish_bos",
            }

    return None


def _confirm_m1_entry(entry_df, direction, confirm_data):
    """
    M1 entry: micro pullback/reclaim after M15 confirmation.
    """
    closed = entry_df.iloc[:-1].reset_index(drop=True)

    if len(closed) < 10:
        return None

    entry = closed.iloc[-1]
    prev = closed.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0 or body < atr * MIN_ENTRY_BODY_ATR:
        return None

    if direction == "BUY":
        reclaim = (
            entry["close"] > entry["open"]
            and entry["close"] > prev["high"]
            and entry["close"] > ema
        )

        if reclaim:
            return {
                "entry_low": entry["low"],
                "entry_high": entry["high"],
                "entry_close": entry["close"],
                "entry_model": "M1_BULLISH_RECLAIM_AFTER_M15_BOS",
            }

    if direction == "SELL":
        rejection = (
            entry["close"] < entry["open"]
            and entry["close"] < prev["low"]
            and entry["close"] < ema
        )

        if rejection:
            return {
                "entry_low": entry["low"],
                "entry_high": entry["high"],
                "entry_close": entry["close"],
                "entry_model": "M1_BEARISH_REJECTION_AFTER_M15_BOS",
            }

    return None


def generate_signal(df):
    """
    df is not the main source here. This strategy fetches 4H, 15m, and 1m internally.
    """
    htf_df = _fetch_df(HTF_TIMEFRAME, HTF_BARS)
    confirm_df = _fetch_df(CONFIRM_TIMEFRAME, CONFIRM_BARS)
    entry_df = _fetch_df(ENTRY_TIMEFRAME, ENTRY_BARS)

    if htf_df is None or confirm_df is None or entry_df is None:
        return None

    htf_ob = _find_htf_order_block(htf_df)
    if htf_ob is None:
        return None

    direction = htf_ob["direction"]
    zone_low = htf_ob["zone_low"]
    zone_high = htf_ob["zone_high"]
    zone_height = zone_high - zone_low

    if zone_height <= 0:
        return None

    latest_price = df.iloc[-2]["close"]

    if not _price_in_zone(latest_price, zone_low, zone_high, htf_ob["atr"]):
        return None

    m15_confirm = _confirm_m15(confirm_df, direction, zone_low, zone_high)
    if m15_confirm is None:
        return None

    m1_entry = _confirm_m1_entry(entry_df, direction, m15_confirm)
    if m1_entry is None:
        return None

    entry_close = m1_entry["entry_close"]
    atr = df.iloc[-2]["atr_14"]

    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, zone_height)

    if direction == "BUY":
        sl_reference = round(min(zone_low, m15_confirm["confirm_low"], m1_entry["entry_low"]) - sl_buffer, 2)
        tp_reference = round(entry_close + target_distance, 2)

        if sl_reference >= entry_close or tp_reference <= entry_close:
            return None

        return {
            "signal": "BUY",
            "score": 94,
            "strategy": "MTF_OB_ENTRY",
            "entry_model": m1_entry["entry_model"],
            "pattern_height": target_distance,
            "htf_zone_low": zone_low,
            "htf_zone_high": zone_high,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "HTF_OB_MEASURED_TARGET",
            "momentum": m15_confirm["momentum"],
            "direction_context": "4h_demand_15m_bos_1m_reclaim",
            "reason": (
                f"MTF OB BUY -> 4H demand zone {round(zone_low, 2)}-{round(zone_high, 2)} -> "
                f"15m bullish BOS -> 1m reclaim -> "
                f"SL below HTF zone {sl_reference} -> TP {tp_reference}"
            ),
        }

    if direction == "SELL":
        sl_reference = round(max(zone_high, m15_confirm["confirm_high"], m1_entry["entry_high"]) + sl_buffer, 2)
        tp_reference = round(entry_close - target_distance, 2)

        if sl_reference <= entry_close or tp_reference >= entry_close:
            return None

        return {
            "signal": "SELL",
            "score": 94,
            "strategy": "MTF_OB_ENTRY",
            "entry_model": m1_entry["entry_model"],
            "pattern_height": target_distance,
            "htf_zone_low": zone_low,
            "htf_zone_high": zone_high,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "HTF_OB_MEASURED_TARGET",
            "momentum": m15_confirm["momentum"],
            "direction_context": "4h_supply_15m_bos_1m_rejection",
            "reason": (
                f"MTF OB SELL -> 4H supply zone {round(zone_low, 2)}-{round(zone_high, 2)} -> "
                f"15m bearish BOS -> 1m rejection -> "
                f"SL above HTF zone {sl_reference} -> TP {tp_reference}"
            ),
        }

    return None