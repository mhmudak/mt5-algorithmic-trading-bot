import MetaTrader5 as mt5
import pandas as pd

from config.settings import SYMBOL, EMA_PERIOD, ATR_PERIOD, ATR_MIN, ATR_MAX
from src.indicators import calculate_ema, calculate_atr


IFVG_LOOKBACK = 45

MIN_FVG_SIZE_ATR = 0.10
MIN_DISPLACEMENT_BODY_ATR = 0.30
MIN_RETEST_BODY_ATR = 0.18

IFVG_RETEST_BUFFER_ATR = 0.25
MAX_ENTRY_EXTENSION_ATR = 0.80

LIQUIDITY_LOOKBACK = 20
LIQUIDITY_SWEEP_BUFFER_ATR = 0.10

OB_LOOKBACK = 8
OB_OVERLAP_BUFFER_ATR = 0.25

HTF_TIMEFRAMES = [
    ("H1", mt5.TIMEFRAME_H1),
    ("H4", mt5.TIMEFRAME_H4),
]

HTF_BARS = 160
HTF_IFVG_DISTANCE_ATR = 0.80

SL_ATR_BUFFER = 0.20
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 5.0

TARGET_ATR_MIN = 1.5
TARGET_ATR_MAX = 3.5


def _fetch_htf_df(timeframe):
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, HTF_BARS)

    if rates is None or len(rates) < 60:
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)

    return df


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, fvg_size):
    return min(
        max(fvg_size * 2.0, atr * TARGET_ATR_MIN),
        atr * TARGET_ATR_MAX,
    )


def _find_recent_bullish_fvg(df, atr):
    closed = df.iloc[:-1].reset_index(drop=True)

    for i in range(len(closed) - 4, max(2, len(closed) - IFVG_LOOKBACK), -1):
        c1 = closed.iloc[i - 2]
        c2 = closed.iloc[i - 1]
        c3 = closed.iloc[i]

        body_c2 = abs(c2["close"] - c2["open"])

        fvg_bottom = c1["high"]
        fvg_top = c3["low"]
        fvg_size = fvg_top - fvg_bottom

        if (
            fvg_size > atr * MIN_FVG_SIZE_ATR
            and c2["close"] > c2["open"]
            and body_c2 > atr * MIN_DISPLACEMENT_BODY_ATR
        ):
            return {
                "type": "BULLISH_FVG",
                "fvg_top": fvg_top,
                "fvg_bottom": fvg_bottom,
                "fvg_mid": (fvg_top + fvg_bottom) / 2,
                "fvg_size": fvg_size,
                "created_index": i,
            }

    return None


def _find_recent_bearish_fvg(df, atr):
    closed = df.iloc[:-1].reset_index(drop=True)

    for i in range(len(closed) - 4, max(2, len(closed) - IFVG_LOOKBACK), -1):
        c1 = closed.iloc[i - 2]
        c2 = closed.iloc[i - 1]
        c3 = closed.iloc[i]

        body_c2 = abs(c2["close"] - c2["open"])

        fvg_top = c1["low"]
        fvg_bottom = c3["high"]
        fvg_size = fvg_top - fvg_bottom

        if (
            fvg_size > atr * MIN_FVG_SIZE_ATR
            and c2["close"] < c2["open"]
            and body_c2 > atr * MIN_DISPLACEMENT_BODY_ATR
        ):
            return {
                "type": "BEARISH_FVG",
                "fvg_top": fvg_top,
                "fvg_bottom": fvg_bottom,
                "fvg_mid": (fvg_top + fvg_bottom) / 2,
                "fvg_size": fvg_size,
                "created_index": i,
            }

    return None


def _recent_close_below(df, level, bars=8):
    recent = df.iloc[-(bars + 2):-2]
    return any(recent["close"] < level)


def _recent_close_above(df, level, bars=8):
    recent = df.iloc[-(bars + 2):-2]
    return any(recent["close"] > level)


def _liquidity_sweep_context(df, signal, atr):
    recent = df.iloc[-(LIQUIDITY_LOOKBACK + 2):-2]

    if recent.empty:
        return False, None

    recent_high = recent["high"].max()
    recent_low = recent["low"].min()
    entry = df.iloc[-2]

    if signal == "BUY":
        swept_low = entry["low"] < recent_low - atr * LIQUIDITY_SWEEP_BUFFER_ATR
        reclaimed = entry["close"] > recent_low
        return swept_low and reclaimed, recent_low

    if signal == "SELL":
        swept_high = entry["high"] > recent_high + atr * LIQUIDITY_SWEEP_BUFFER_ATR
        rejected = entry["close"] < recent_high
        return swept_high and rejected, recent_high

    return False, None


def _ob_breaker_overlap(df, signal, fvg, atr):
    zone_low = fvg["fvg_bottom"]
    zone_high = fvg["fvg_top"]
    buffer = atr * OB_OVERLAP_BUFFER_ATR

    recent = df.iloc[-(OB_LOOKBACK + 2):-2]

    for _, candle in recent.iterrows():
        candle_high = candle["high"]
        candle_low = candle["low"]

        overlap = (
            candle_low <= zone_high + buffer
            and candle_high >= zone_low - buffer
        )

        if not overlap:
            continue

        if signal == "BUY" and candle["close"] < candle["open"]:
            return True, "DEMAND_OB_OVERLAP"

        if signal == "SELL" and candle["close"] > candle["open"]:
            return True, "SUPPLY_OB_OVERLAP"

    return False, None


def _htf_ifvg_context(signal, price, atr):
    for label, timeframe in HTF_TIMEFRAMES:
        htf_df = _fetch_htf_df(timeframe)

        if htf_df is None:
            continue

        if signal == "BUY":
            bearish_fvg = _find_recent_bearish_fvg(htf_df, htf_df.iloc[-2]["atr_14"])

            if bearish_fvg is None:
                continue

            failed = _recent_close_above(htf_df, bearish_fvg["fvg_top"], bars=12)

            if not failed:
                continue

            distance = abs(price - bearish_fvg["fvg_top"])

            if distance <= atr * HTF_IFVG_DISTANCE_ATR:
                return True, f"{label}_BEARISH_FVG_INVERTED"

        if signal == "SELL":
            bullish_fvg = _find_recent_bullish_fvg(htf_df, htf_df.iloc[-2]["atr_14"])

            if bullish_fvg is None:
                continue

            failed = _recent_close_below(htf_df, bullish_fvg["fvg_bottom"], bars=12)

            if not failed:
                continue

            distance = abs(price - bullish_fvg["fvg_bottom"])

            if distance <= atr * HTF_IFVG_DISTANCE_ATR:
                return True, f"{label}_BULLISH_FVG_INVERTED"

    return False, None


def _score_setup(base_score, body, atr, retest_quality, liquidity_ok, ob_overlap, htf_ifvg):
    score = base_score

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.50:
        score += 2

    if retest_quality:
        score += 3

    if liquidity_ok:
        score += 3

    if ob_overlap:
        score += 2

    if htf_ifvg:
        score += 3

    return min(score, 99)


def generate_signal(df):
    if len(df) < IFVG_LOOKBACK + 8:
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

    if candle_range <= 0:
        return None

    if body < atr * MIN_RETEST_BODY_ATR:
        return None

    sl_buffer = _sl_buffer(atr)

    recent = df.iloc[-25:-2]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    lower_wick = min(entry["open"], entry["close"]) - entry["low"]
    upper_wick = entry["high"] - max(entry["open"], entry["close"])

    # =========================================================
    # SELL: bullish FVG fails, becomes IFVG resistance, retest/reject
    # =========================================================
    bullish_fvg = _find_recent_bullish_fvg(df, atr)

    if bullish_fvg is not None:
        fvg_top = bullish_fvg["fvg_top"]
        fvg_bottom = bullish_fvg["fvg_bottom"]
        fvg_mid = bullish_fvg["fvg_mid"]
        fvg_size = bullish_fvg["fvg_size"]

        fvg_inverted = _recent_close_below(df, fvg_bottom, bars=10)

        retest_into_ifvg = (
            entry["high"] >= fvg_bottom - atr * 0.25
            and entry["close"] < fvg_bottom
        )

        bearish_rejection = (
            entry["close"] < entry["open"]
            and entry["close"] < prev["low"]
            and price < ema
            and upper_wick > body * 0.70
            and entry["close"] <= entry["high"] - candle_range * 0.60
        )

        extension_from_ifvg = fvg_bottom - entry["close"]
        not_late = extension_from_ifvg <= atr * MAX_ENTRY_EXTENSION_ATR if "MAX_ENTRY_EXTENSION_ATR" in globals() else True

        if fvg_inverted and retest_into_ifvg and bearish_rejection and not_late:
            liquidity_ok, liquidity_level = _liquidity_sweep_context(df, "SELL", atr)
            ob_overlap, ob_context = _ob_breaker_overlap(df, "SELL", bullish_fvg, atr)
            htf_ok, htf_context = _htf_ifvg_context("SELL", price, atr)

            sl_reference = round(max(entry["high"], fvg_top) + sl_buffer, 2)

            if recent_low < entry["close"]:
                tp_reference = recent_low
                target_model = "RECENT_STRUCTURE_LOW"
            else:
                tp_reference = entry["close"] - _target_distance(atr, fvg_size)
                target_model = "IFVG_EXTENSION"

            tp_reference = round(tp_reference, 2)

            if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
                return None

            score = _score_setup(
                base_score=93,
                body=body,
                atr=atr,
                retest_quality=True,
                liquidity_ok=liquidity_ok,
                ob_overlap=ob_overlap,
                htf_ifvg=htf_ok,
            )

            return {
                "signal": "SELL",
                "score": score,
                "strategy": "IFVG_RETEST_CONFLUENCE",
                "entry_model": "BULLISH_FVG_INVERTED_RETEST_SELL",
                "pattern_height": abs(entry["close"] - tp_reference),
                "ifvg_top": fvg_top,
                "ifvg_bottom": fvg_bottom,
                "ifvg_mid": fvg_mid,
                "liquidity_confirmed": liquidity_ok,
                "liquidity_level": liquidity_level,
                "ob_overlap": ob_overlap,
                "ob_context": ob_context,
                "htf_ifvg": htf_ok,
                "htf_context": htf_context,
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": target_model,
                "momentum": "bearish_ifvg_retest_rejection",
                "direction_context": "inverted_bullish_fvg_resistance",
                "reason": (
                    f"IFVG SELL -> bullish FVG {round(fvg_bottom, 2)}-{round(fvg_top, 2)} "
                    f"inverted then retested -> bearish rejection -> "
                    f"liquidity={liquidity_ok} ob={ob_overlap} htf={htf_ok} -> "
                    f"SL {sl_reference} -> TP {target_model} {tp_reference}"
                ),
            }

    # =========================================================
    # BUY: bearish FVG fails, becomes IFVG support, retest/reclaim
    # =========================================================
    bearish_fvg = _find_recent_bearish_fvg(df, atr)

    if bearish_fvg is not None:
        fvg_top = bearish_fvg["fvg_top"]
        fvg_bottom = bearish_fvg["fvg_bottom"]
        fvg_mid = bearish_fvg["fvg_mid"]
        fvg_size = bearish_fvg["fvg_size"]

        fvg_inverted = _recent_close_above(df, fvg_top, bars=10)

        retest_into_ifvg = (
            entry["low"] <= fvg_top + atr * 0.25
            and entry["close"] > fvg_top
        )

        bullish_reclaim = (
            entry["close"] > entry["open"]
            and entry["close"] > prev["high"]
            and price > ema
            and lower_wick > body * 0.70
            and entry["close"] >= entry["low"] + candle_range * 0.60
        )

        extension_from_ifvg = entry["close"] - fvg_top
        not_late = extension_from_ifvg <= atr * MAX_ENTRY_EXTENSION_ATR if "MAX_ENTRY_EXTENSION_ATR" in globals() else True

        if fvg_inverted and retest_into_ifvg and bullish_reclaim and not_late:
            liquidity_ok, liquidity_level = _liquidity_sweep_context(df, "BUY", atr)
            ob_overlap, ob_context = _ob_breaker_overlap(df, "BUY", bearish_fvg, atr)
            htf_ok, htf_context = _htf_ifvg_context("BUY", price, atr)

            sl_reference = round(min(entry["low"], fvg_bottom) - sl_buffer, 2)

            if recent_high > entry["close"]:
                tp_reference = recent_high
                target_model = "RECENT_STRUCTURE_HIGH"
            else:
                tp_reference = entry["close"] + _target_distance(atr, fvg_size)
                target_model = "IFVG_EXTENSION"

            tp_reference = round(tp_reference, 2)

            if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
                return None

            score = _score_setup(
                base_score=93,
                body=body,
                atr=atr,
                retest_quality=True,
                liquidity_ok=liquidity_ok,
                ob_overlap=ob_overlap,
                htf_ifvg=htf_ok,
            )

            return {
                "signal": "BUY",
                "score": score,
                "strategy": "IFVG_RETEST_CONFLUENCE",
                "entry_model": "BEARISH_FVG_INVERTED_RETEST_BUY",
                "pattern_height": abs(tp_reference - entry["close"]),
                "ifvg_top": fvg_top,
                "ifvg_bottom": fvg_bottom,
                "ifvg_mid": fvg_mid,
                "liquidity_confirmed": liquidity_ok,
                "liquidity_level": liquidity_level,
                "ob_overlap": ob_overlap,
                "ob_context": ob_context,
                "htf_ifvg": htf_ok,
                "htf_context": htf_context,
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": target_model,
                "momentum": "bullish_ifvg_retest_reclaim",
                "direction_context": "inverted_bearish_fvg_support",
                "reason": (
                    f"IFVG BUY -> bearish FVG {round(fvg_bottom, 2)}-{round(fvg_top, 2)} "
                    f"inverted then retested -> bullish reclaim -> "
                    f"liquidity={liquidity_ok} ob={ob_overlap} htf={htf_ok} -> "
                    f"SL {sl_reference} -> TP {target_model} {tp_reference}"
                ),
            }

    return None