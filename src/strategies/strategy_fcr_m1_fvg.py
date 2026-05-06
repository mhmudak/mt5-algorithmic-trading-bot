import MetaTrader5 as mt5
import pandas as pd

from config.settings import SYMBOL, EMA_PERIOD, ATR_PERIOD, ATR_MIN, ATR_MAX
from src.indicators import calculate_ema, calculate_atr
from src.logger import logger


FCR_TIMEFRAME = mt5.TIMEFRAME_M5
ENTRY_TIMEFRAME = mt5.TIMEFRAME_M1

FCR_BARS = 80
ENTRY_BARS = 120

# FCR candle quality
FCR_MIN_RANGE_ATR = 0.80
FCR_MIN_BODY_ATR = 0.35

# M1 entry quality
MIN_M1_BODY_ATR = 0.15
MAX_EXTENSION_ATR = 1.20

# FVG quality
FVG_MIN_SIZE_ATR = 0.08

# Risk
SL_ATR_BUFFER = 0.15
MIN_SL_BUFFER = 1.0
MAX_SL_BUFFER = 4.0

TARGET_R_MULTIPLIER = 3.0


def _fetch_df(timeframe, bars):
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, bars)

    if rates is None or len(rates) < 30:
        logger.error(f"[FCR_M1_FVG] Failed to fetch rates | timeframe={timeframe}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)

    return df


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _score_setup(base_score, body, atr, has_fvg, engulfing, fcr_quality):
    score = base_score

    if body > atr * 0.25:
        score += 2

    if body > atr * 0.40:
        score += 2

    if has_fvg:
        score += 3

    if engulfing:
        score += 3

    if fcr_quality:
        score += 2

    return min(score, 99)


def _detect_bullish_fvg(c1, c3, atr):
    gap_bottom = c1["high"]
    gap_top = c3["low"]
    gap_size = gap_top - gap_bottom

    if gap_size > atr * FVG_MIN_SIZE_ATR:
        return gap_bottom, gap_top, gap_size

    return None


def _detect_bearish_fvg(c1, c3, atr):
    gap_top = c1["low"]
    gap_bottom = c3["high"]
    gap_size = gap_top - gap_bottom

    if gap_size > atr * FVG_MIN_SIZE_ATR:
        return gap_bottom, gap_top, gap_size

    return None


def generate_signal(df):
    """
    FCR + M1 FVG precision model.

    M5:
    - use the last closed M5 candle as the FCR reference candle
    - mark its high and low

    M1:
    - break above/below the FCR high/low
    - create FVG / gap
    - confirm with engulfing / reclaim
    - SL beyond FVG / micro structure
    - TP = 3R
    """

    m5_df = _fetch_df(FCR_TIMEFRAME, FCR_BARS)
    m1_df = _fetch_df(ENTRY_TIMEFRAME, ENTRY_BARS)

    if m5_df is None or m1_df is None:
        return None

    # Closed candles only
    m5_closed = m5_df.iloc[:-1].copy()
    m1_closed = m1_df.iloc[:-1].copy()

    if len(m5_closed) < 10 or len(m1_closed) < 10:
        return None

    # =========================================================
    # M5 FCR candle
    # =========================================================
    fcr = m5_closed.iloc[-1]

    fcr_high = fcr["high"]
    fcr_low = fcr["low"]
    fcr_range = fcr_high - fcr_low
    fcr_body = abs(fcr["close"] - fcr["open"])
    fcr_atr = fcr["atr_14"]

    if fcr_range <= 0 or fcr_atr <= 0:
        return None

    # avoid weak FCR candle
    if fcr_range < fcr_atr * FCR_MIN_RANGE_ATR:
        return None

    if fcr_body < fcr_atr * FCR_MIN_BODY_ATR:
        return None

    # =========================================================
    # M1 candles after FCR
    # =========================================================
    c1 = m1_closed.iloc[-4]
    c2 = m1_closed.iloc[-3]
    c3 = m1_closed.iloc[-2]
    entry = m1_closed.iloc[-1]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return None

    if body < atr * MIN_M1_BODY_ATR:
        return None

    sl_buffer = _sl_buffer(atr)

    # =========================
    # BUY: M1 breaks M5 FCR high, FVG, engulfing/reclaim
    # =========================
    broke_high = (
        c2["close"] > fcr_high
        or c3["close"] > fcr_high
    )

    bullish_fvg = _detect_bullish_fvg(c1, c3, atr)

    bullish_engulfing = (
        entry["close"] > entry["open"]
        and entry["close"] > c3["high"]
        and entry["open"] <= c3["close"]
    )

    bullish_reclaim = (
        entry["close"] > fcr_high
        and price > ema
    )

    extension = entry["close"] - fcr_high
    not_chasing = extension >= 0 and extension <= atr * MAX_EXTENSION_ATR

    if broke_high and bullish_fvg and bullish_engulfing and bullish_reclaim and not_chasing:
        gap_bottom, gap_top, gap_size = bullish_fvg

        sl_reference = round(min(gap_bottom, c3["low"], entry["low"]) - sl_buffer, 2)
        stop_distance = entry["close"] - sl_reference
        tp_reference = round(entry["close"] + (stop_distance * TARGET_R_MULTIPLIER), 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=93,
            body=body,
            atr=atr,
            has_fvg=True,
            engulfing=bullish_engulfing,
            fcr_quality=True,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "FCR_M1_FVG",
            "entry_model": "M5_FCR_HIGH_BREAK_M1_FVG_ENGULF",
            "pattern_height": stop_distance * TARGET_R_MULTIPLIER,
            "fcr_high": fcr_high,
            "fcr_low": fcr_low,
            "fcr_range": fcr_range,
            "fcr_time": fcr.get("time"),
            "fvg_bottom": gap_bottom,
            "fvg_top": gap_top,
            "fvg_size": gap_size,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "FIXED_3R_AFTER_M1_FVG",
            "momentum": "bullish_m1_fvg_engulfing",
            "direction_context": "m5_fcr_high_break_m1_reclaim",
            "reason": (
                f"FCR M1 FVG BUY -> M5 FCR high {round(fcr_high, 2)} broken -> "
                f"M1 bullish FVG {round(gap_bottom, 2)}-{round(gap_top, 2)} -> "
                f"engulfing/reclaim confirmed -> SL {sl_reference} -> TP 3R {tp_reference}"
            ),
        }

    # =========================
    # SELL: M1 breaks M5 FCR low, FVG, engulfing/reclaim
    # =========================
    broke_low = (
        c2["close"] < fcr_low
        or c3["close"] < fcr_low
    )

    bearish_fvg = _detect_bearish_fvg(c1, c3, atr)

    bearish_engulfing = (
        entry["close"] < entry["open"]
        and entry["close"] < c3["low"]
        and entry["open"] >= c3["close"]
    )

    bearish_reclaim = (
        entry["close"] < fcr_low
        and price < ema
    )

    extension = fcr_low - entry["close"]
    not_chasing = extension >= 0 and extension <= atr * MAX_EXTENSION_ATR

    if broke_low and bearish_fvg and bearish_engulfing and bearish_reclaim and not_chasing:
        gap_bottom, gap_top, gap_size = bearish_fvg

        sl_reference = round(max(gap_top, c3["high"], entry["high"]) + sl_buffer, 2)
        stop_distance = sl_reference - entry["close"]
        tp_reference = round(entry["close"] - (stop_distance * TARGET_R_MULTIPLIER), 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=93,
            body=body,
            atr=atr,
            has_fvg=True,
            engulfing=bearish_engulfing,
            fcr_quality=True,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "FCR_M1_FVG",
            "entry_model": "M5_FCR_LOW_BREAK_M1_FVG_ENGULF",
            "pattern_height": stop_distance * TARGET_R_MULTIPLIER,
            "fcr_high": fcr_high,
            "fcr_low": fcr_low,
            "fcr_range": fcr_range,
            "fcr_time": fcr.get("time"),
            "fvg_bottom": gap_bottom,
            "fvg_top": gap_top,
            "fvg_size": gap_size,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "FIXED_3R_AFTER_M1_FVG",
            "momentum": "bearish_m1_fvg_engulfing",
            "direction_context": "m5_fcr_low_break_m1_reclaim",
            "reason": (
                f"FCR M1 FVG SELL -> M5 FCR low {round(fcr_low, 2)} broken -> "
                f"M1 bearish FVG {round(gap_bottom, 2)}-{round(gap_top, 2)} -> "
                f"engulfing/reclaim confirmed -> SL {sl_reference} -> TP 3R {tp_reference}"
            ),
        }

    return None