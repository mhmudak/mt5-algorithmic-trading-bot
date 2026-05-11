from config.settings import ATR_MIN, ATR_MAX
from src.supply_demand_context import analyze_supply_demand_context


SD_MIN_BODY_ATR = 0.20
SD_MIN_WICK_BODY_RATIO = 0.90

SL_ATR_BUFFER = 0.20
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 5.0

TARGET_ATR_MIN = 1.5
TARGET_ATR_MAX = 3.0


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, zone_height):
    return min(
        max(zone_height * 2.0, atr * TARGET_ATR_MIN),
        atr * TARGET_ATR_MAX,
    )


def _score_setup(base_score, body, atr, rejection_quality, zone_fresh=True):
    score = base_score

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.50:
        score += 2

    if rejection_quality:
        score += 3

    if zone_fresh:
        score += 2

    return min(score, 99)


def generate_signal(df):
    context = analyze_supply_demand_context(df)

    if context is None:
        return None

    active_zone = context.get("active_zone")

    if not active_zone:
        return None

    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return None

    if body < atr * SD_MIN_BODY_ATR:
        return None

    upper_wick = entry["high"] - max(entry["open"], entry["close"])
    lower_wick = min(entry["open"], entry["close"]) - entry["low"]

    zone_low = active_zone["zone_low"]
    zone_high = active_zone["zone_high"]
    zone_height = zone_high - zone_low

    if zone_height <= 0:
        return None

    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, zone_height)

    # =========================
    # BUY from demand zone
    # =========================
    if active_zone["type"] == "DEMAND":
        bullish_rejection = (
            entry["close"] > entry["open"]
            and entry["close"] > zone_high
            and lower_wick > body * SD_MIN_WICK_BODY_RATIO
            and price > ema
        )

        if not bullish_rejection:
            return None

        sl_reference = round(min(entry["low"], zone_low) - sl_buffer, 2)
        tp_reference = round(entry["close"] + target_distance, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            body=body,
            atr=atr,
            rejection_quality=lower_wick > body * 1.2,
            zone_fresh=active_zone.get("fresh", True),
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "SUPPLY_DEMAND_RETEST",
            "entry_model": "DEMAND_ZONE_RETEST_RECLAIM",
            "pattern_height": abs(tp_reference - entry["close"]),
            "zone_type": active_zone["type"],
            "zone_low": zone_low,
            "zone_high": zone_high,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "DEMAND_ZONE_EXTENSION",
            "momentum": "bullish_demand_retest_reclaim",
            "direction_context": "demand_zone_retest_price_above_ema",
            "reason": (
                f"Demand zone BUY -> zone {round(zone_low, 2)}-{round(zone_high, 2)} "
                f"retested and reclaimed -> SL {sl_reference} -> TP {tp_reference}"
            ),
        }

    # =========================
    # SELL from supply zone
    # =========================
    if active_zone["type"] == "SUPPLY":
        bearish_rejection = (
            entry["close"] < entry["open"]
            and entry["close"] < zone_low
            and upper_wick > body * SD_MIN_WICK_BODY_RATIO
            and price < ema
        )

        if not bearish_rejection:
            return None

        sl_reference = round(max(entry["high"], zone_high) + sl_buffer, 2)
        tp_reference = round(entry["close"] - target_distance, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            body=body,
            atr=atr,
            rejection_quality=upper_wick > body * 1.2,
            zone_fresh=active_zone.get("fresh", True),
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "SUPPLY_DEMAND_RETEST",
            "entry_model": "SUPPLY_ZONE_RETEST_REJECT",
            "pattern_height": abs(entry["close"] - tp_reference),
            "zone_type": active_zone["type"],
            "zone_low": zone_low,
            "zone_high": zone_high,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "SUPPLY_ZONE_EXTENSION",
            "momentum": "bearish_supply_retest_rejection",
            "direction_context": "supply_zone_retest_price_below_ema",
            "reason": (
                f"Supply zone SELL -> zone {round(zone_low, 2)}-{round(zone_high, 2)} "
                f"retested and rejected -> SL {sl_reference} -> TP {tp_reference}"
            ),
        }

    return None