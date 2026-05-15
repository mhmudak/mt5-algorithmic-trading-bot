import MetaTrader5 as mt5
import pandas as pd

from config.settings import SYMBOL, EMA_PERIOD, ATR_PERIOD, ATR_MIN, ATR_MAX
from src.indicators import calculate_ema, calculate_atr
from src.logger import logger


HTF_TIMEFRAMES = [
    ("H1", mt5.TIMEFRAME_H1),
    ("H2", mt5.TIMEFRAME_H2),
    ("H3", mt5.TIMEFRAME_H3),
    ("H4", mt5.TIMEFRAME_H4),
]

HTF_BARS = 160
LOOKBACK_SWINGS = 80

SR_TOLERANCE_ATR = 0.35
MIN_CLUSTER_COUNT = 2

MIN_FVG_SIZE_ATR = 0.12
FVG_DISTANCE_ATR = 0.60

MIN_CONFIRM_BODY_ATR = 0.20
MIN_REJECTION_WICK_BODY = 0.80

SL_ATR_BUFFER = 0.25
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 6.0

TARGET_ATR_MIN = 1.5
TARGET_ATR_MAX = 3.5


def _fetch_df(timeframe, bars):
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, bars)

    if rates is None or len(rates) < 50:
        logger.info(f"[MTF_SR_FVG] Not enough data for timeframe={timeframe}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)

    return df


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, zone_height):
    return min(
        max(zone_height * 2.0, atr * TARGET_ATR_MIN),
        atr * TARGET_ATR_MAX,
    )


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


def _swing_levels(df, label):
    closed = df.iloc[:-1].reset_index(drop=True)
    recent = closed.iloc[-LOOKBACK_SWINGS:].reset_index(drop=True)

    supports = []
    resistances = []

    for i in range(2, len(recent) - 2):
        low = recent.iloc[i]["low"]
        high = recent.iloc[i]["high"]

        if (
            low < recent.iloc[i - 1]["low"]
            and low < recent.iloc[i + 1]["low"]
        ):
            supports.append(
                {
                    "timeframe": label,
                    "price": low,
                    "type": "SUPPORT",
                }
            )

        if (
            high > recent.iloc[i - 1]["high"]
            and high > recent.iloc[i + 1]["high"]
        ):
            resistances.append(
                {
                    "timeframe": label,
                    "price": high,
                    "type": "RESISTANCE",
                }
            )

    return supports, resistances


def _cluster_levels(levels, atr):
    if not levels:
        return []

    tolerance = atr * SR_TOLERANCE_ATR
    sorted_levels = sorted(levels, key=lambda item: item["price"])

    clusters = []

    for level in sorted_levels:
        added = False

        for cluster in clusters:
            if abs(level["price"] - cluster["center"]) <= tolerance:
                cluster["levels"].append(level)
                cluster["center"] = sum(item["price"] for item in cluster["levels"]) / len(cluster["levels"])
                added = True
                break

        if not added:
            clusters.append(
                {
                    "center": level["price"],
                    "levels": [level],
                    "type": level["type"],
                }
            )

    valid_clusters = []

    for cluster in clusters:
        if len(cluster["levels"]) >= MIN_CLUSTER_COUNT:
            prices = [item["price"] for item in cluster["levels"]]

            valid_clusters.append(
                {
                    "type": cluster["type"],
                    "center": sum(prices) / len(prices),
                    "zone_low": min(prices),
                    "zone_high": max(prices),
                    "count": len(cluster["levels"]),
                    "timeframes": sorted(list(set(item["timeframe"] for item in cluster["levels"]))),
                }
            )

    return valid_clusters


def _find_recent_htf_fvg(df, direction, atr):
    closed = df.iloc[:-1].reset_index(drop=True)

    for i in range(len(closed) - 4, max(2, len(closed) - 50), -1):
        c1 = closed.iloc[i - 2]
        c2 = closed.iloc[i - 1]
        c3 = closed.iloc[i]

        body_c2 = abs(c2["close"] - c2["open"])

        if direction == "BUY":
            fvg_bottom = c1["high"]
            fvg_top = c3["low"]
            fvg_size = fvg_top - fvg_bottom

            if (
                fvg_size > atr * MIN_FVG_SIZE_ATR
                and c2["close"] > c2["open"]
                and body_c2 > atr * 0.30
            ):
                return {
                    "fvg_bottom": fvg_bottom,
                    "fvg_top": fvg_top,
                    "fvg_mid": (fvg_bottom + fvg_top) / 2,
                    "fvg_size": fvg_size,
                }

        if direction == "SELL":
            fvg_top = c1["low"]
            fvg_bottom = c3["high"]
            fvg_size = fvg_top - fvg_bottom

            if (
                fvg_size > atr * MIN_FVG_SIZE_ATR
                and c2["close"] < c2["open"]
                and body_c2 > atr * 0.30
            ):
                return {
                    "fvg_bottom": fvg_bottom,
                    "fvg_top": fvg_top,
                    "fvg_mid": (fvg_bottom + fvg_top) / 2,
                    "fvg_size": fvg_size,
                }

    return None


def _nearest_cluster(price, clusters, cluster_type):
    filtered = [cluster for cluster in clusters if cluster["type"] == cluster_type]

    if not filtered:
        return None

    return min(
        filtered,
        key=lambda cluster: abs(price - cluster["center"]),
    )


def _fvg_near_cluster(fvg, cluster, atr):
    if fvg is None or cluster is None:
        return False

    fvg_mid = fvg["fvg_mid"]
    cluster_center = cluster["center"]

    return abs(fvg_mid - cluster_center) <= atr * FVG_DISTANCE_ATR


def _score_setup(base_score, body, atr, cluster_count, fvg_size, rejection_quality, h4_aligned):
    score = base_score

    if cluster_count >= 3:
        score += 2

    if cluster_count >= 4:
        score += 2

    if fvg_size > atr * 0.25:
        score += 2

    if body > atr * 0.35:
        score += 2

    if rejection_quality:
        score += 3

    if h4_aligned:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if df is None or len(df) < 40:
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

    if candle_range <= 0 or body < atr * MIN_CONFIRM_BODY_ATR:
        return None

    all_supports = []
    all_resistances = []
    htf_data = {}

    for label, timeframe in HTF_TIMEFRAMES:
        htf_df = _fetch_df(timeframe, HTF_BARS)

        if htf_df is None:
            continue

        htf_data[label] = htf_df

        supports, resistances = _swing_levels(htf_df, label)
        all_supports.extend(supports)
        all_resistances.extend(resistances)

    if not htf_data:
        return None

    support_clusters = _cluster_levels(all_supports, atr)
    resistance_clusters = _cluster_levels(all_resistances, atr)

    h4_df = htf_data.get("H4")
    h4_bias = _detect_bias(h4_df)

    sl_buffer = _sl_buffer(atr)

    lower_wick = min(entry["open"], entry["close"]) - entry["low"]
    upper_wick = entry["high"] - max(entry["open"], entry["close"])

    # =========================================================
    # BUY: MTF support cluster + HTF bullish FVG + M15 reclaim
    # =========================================================
    support_cluster = _nearest_cluster(price, support_clusters, "SUPPORT")

    if support_cluster is not None:
        bullish_fvg = None

        for label in ["H4", "H3", "H2", "H1"]:
            htf_df = htf_data.get(label)
            if htf_df is None:
                continue

            candidate_fvg = _find_recent_htf_fvg(htf_df, "BUY", atr)

            if _fvg_near_cluster(candidate_fvg, support_cluster, atr):
                bullish_fvg = candidate_fvg
                break

        price_in_support_zone = (
            entry["low"] <= support_cluster["zone_high"] + atr * 0.25
            and entry["close"] > support_cluster["zone_low"]
        )

        bullish_reclaim = (
            entry["close"] > entry["open"]
            and entry["close"] > prev["high"]
            and entry["close"] > ema
            and lower_wick > body * MIN_REJECTION_WICK_BODY
        )

        if price_in_support_zone and bullish_fvg and bullish_reclaim:
            sl_reference = round(min(entry["low"], support_cluster["zone_low"], bullish_fvg["fvg_bottom"]) - sl_buffer, 2)

            target_distance = _target_distance(atr, support_cluster["zone_high"] - support_cluster["zone_low"])

            tp_reference = round(entry["close"] + target_distance, 2)
            target_model = "MTF_SUPPORT_FVG_EXTENSION"

            if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
                return None

            score = _score_setup(
                base_score=93,
                body=body,
                atr=atr,
                cluster_count=support_cluster["count"],
                fvg_size=bullish_fvg["fvg_size"],
                rejection_quality=lower_wick > body * 1.2,
                h4_aligned=h4_bias in ["BUY", "NEUTRAL"],
            )

            return {
                "signal": "BUY",
                "score": score,
                "strategy": "MTF_SR_FVG_RECLAIM",
                "entry_model": "MTF_SUPPORT_FVG_RECLAIM",
                "pattern_height": abs(tp_reference - entry["close"]),
                "cluster_type": "SUPPORT",
                "cluster_center": round(support_cluster["center"], 2),
                "cluster_zone_low": round(support_cluster["zone_low"], 2),
                "cluster_zone_high": round(support_cluster["zone_high"], 2),
                "cluster_timeframes": support_cluster["timeframes"],
                "fvg_bottom": bullish_fvg["fvg_bottom"],
                "fvg_top": bullish_fvg["fvg_top"],
                "fvg_mid": bullish_fvg["fvg_mid"],
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": target_model,
                "momentum": "bullish_mtf_support_fvg_reclaim",
                "direction_context": "mtf_support_cluster_h4_fvg",
                "reason": (
                    f"MTF SR FVG BUY -> support cluster {round(support_cluster['zone_low'], 2)}-"
                    f"{round(support_cluster['zone_high'], 2)} "
                    f"timeframes={','.join(support_cluster['timeframes'])} -> "
                    f"HTF bullish FVG {round(bullish_fvg['fvg_bottom'], 2)}-"
                    f"{round(bullish_fvg['fvg_top'], 2)} -> "
                    f"M15 reclaim confirmed -> SL {sl_reference} -> TP {tp_reference}"
                ),
            }

    # =========================================================
    # SELL: MTF resistance cluster + HTF bearish FVG + M15 rejection
    # =========================================================
    resistance_cluster = _nearest_cluster(price, resistance_clusters, "RESISTANCE")

    if resistance_cluster is not None:
        bearish_fvg = None

        for label in ["H4", "H3", "H2", "H1"]:
            htf_df = htf_data.get(label)
            if htf_df is None:
                continue

            candidate_fvg = _find_recent_htf_fvg(htf_df, "SELL", atr)

            if _fvg_near_cluster(candidate_fvg, resistance_cluster, atr):
                bearish_fvg = candidate_fvg
                break

        price_in_resistance_zone = (
            entry["high"] >= resistance_cluster["zone_low"] - atr * 0.25
            and entry["close"] < resistance_cluster["zone_high"]
        )

        bearish_rejection = (
            entry["close"] < entry["open"]
            and entry["close"] < prev["low"]
            and entry["close"] < ema
            and upper_wick > body * MIN_REJECTION_WICK_BODY
        )

        if price_in_resistance_zone and bearish_fvg and bearish_rejection:
            sl_reference = round(max(entry["high"], resistance_cluster["zone_high"], bearish_fvg["fvg_top"]) + sl_buffer, 2)

            target_distance = _target_distance(atr, resistance_cluster["zone_high"] - resistance_cluster["zone_low"])

            tp_reference = round(entry["close"] - target_distance, 2)
            target_model = "MTF_RESISTANCE_FVG_EXTENSION"

            if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
                return None

            score = _score_setup(
                base_score=93,
                body=body,
                atr=atr,
                cluster_count=resistance_cluster["count"],
                fvg_size=bearish_fvg["fvg_size"],
                rejection_quality=upper_wick > body * 1.2,
                h4_aligned=h4_bias in ["SELL", "NEUTRAL"],
            )

            return {
                "signal": "SELL",
                "score": score,
                "strategy": "MTF_SR_FVG_RECLAIM",
                "entry_model": "MTF_RESISTANCE_FVG_REJECT",
                "pattern_height": abs(entry["close"] - tp_reference),
                "cluster_type": "RESISTANCE",
                "cluster_center": round(resistance_cluster["center"], 2),
                "cluster_zone_low": round(resistance_cluster["zone_low"], 2),
                "cluster_zone_high": round(resistance_cluster["zone_high"], 2),
                "cluster_timeframes": resistance_cluster["timeframes"],
                "fvg_bottom": bearish_fvg["fvg_bottom"],
                "fvg_top": bearish_fvg["fvg_top"],
                "fvg_mid": bearish_fvg["fvg_mid"],
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": target_model,
                "momentum": "bearish_mtf_resistance_fvg_reject",
                "direction_context": "mtf_resistance_cluster_h4_fvg",
                "reason": (
                    f"MTF SR FVG SELL -> resistance cluster {round(resistance_cluster['zone_low'], 2)}-"
                    f"{round(resistance_cluster['zone_high'], 2)} "
                    f"timeframes={','.join(resistance_cluster['timeframes'])} -> "
                    f"HTF bearish FVG {round(bearish_fvg['fvg_bottom'], 2)}-"
                    f"{round(bearish_fvg['fvg_top'], 2)} -> "
                    f"M15 rejection confirmed -> SL {sl_reference} -> TP {tp_reference}"
                ),
            }

    return None