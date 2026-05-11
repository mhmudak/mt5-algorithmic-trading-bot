from src.logger import logger


SD_LOOKBACK = 60
SD_MIN_DISPLACEMENT_ATR = 0.40
SD_MAX_ZONE_HEIGHT_ATR = 2.50
SD_MIN_ZONE_HEIGHT_ATR = 0.15
SD_RETEST_BUFFER_ATR = 0.25

MAX_ZONE_AGE_BARS = 40


def _zone_height(zone):
    return abs(zone["zone_high"] - zone["zone_low"])


def _valid_zone_size(zone, atr):
    height = _zone_height(zone)

    return (
        height >= atr * SD_MIN_ZONE_HEIGHT_ATR
        and height <= atr * SD_MAX_ZONE_HEIGHT_ATR
    )


def _find_supply_demand_zones(df):
    """
    Dynamic supply / demand zone detection using closed candles.

    Demand:
    last bearish/base candle before bullish displacement.

    Supply:
    last bullish/base candle before bearish displacement.
    """
    if len(df) < SD_LOOKBACK + 5:
        return []

    closed = df.iloc[:-1].reset_index(drop=True)
    data = closed.iloc[-SD_LOOKBACK:].reset_index(drop=True)

    zones = []

    for i in range(2, len(data) - 2):
        base = data.iloc[i - 1]
        displacement = data.iloc[i]

        atr = displacement["atr_14"]
        body = abs(displacement["close"] - displacement["open"])

        if atr <= 0:
            continue

        if body < atr * SD_MIN_DISPLACEMENT_ATR:
            continue

        # =========================
        # Demand zone
        # =========================
        if (
            base["close"] < base["open"]
            and displacement["close"] > displacement["open"]
            and displacement["close"] > base["high"]
        ):
            zone = {
                "type": "DEMAND",
                "zone_low": base["low"],
                "zone_high": base["high"],
                "created_index": i,
                "created_time": base.get("time"),
                "displacement_close": displacement["close"],
                "atr": atr,
                "fresh": True,
            }

            if _valid_zone_size(zone, atr):
                zones.append(zone)

        # =========================
        # Supply zone
        # =========================
        if (
            base["close"] > base["open"]
            and displacement["close"] < displacement["open"]
            and displacement["close"] < base["low"]
        ):
            zone = {
                "type": "SUPPLY",
                "zone_low": base["low"],
                "zone_high": base["high"],
                "created_index": i,
                "created_time": base.get("time"),
                "displacement_close": displacement["close"],
                "atr": atr,
                "fresh": True,
            }

            if _valid_zone_size(zone, atr):
                zones.append(zone)

    return zones


def _invalidate_zones(df, zones):
    """
    Removes zones that have been fully violated or are too old.
    """
    if not zones:
        return []

    closed = df.iloc[:-1].reset_index(drop=True)
    current_index = len(closed) - 1
    valid_zones = []

    for zone in zones:
        zone_age = current_index - zone["created_index"]

        if zone_age > MAX_ZONE_AGE_BARS:
            continue

        # Demand invalidated if closed below zone low
        if zone["type"] == "DEMAND":
            closes_after = closed.iloc[zone["created_index"] + 1:]["close"]
            if not closes_after.empty and closes_after.min() < zone["zone_low"]:
                continue

        # Supply invalidated if closed above zone high
        if zone["type"] == "SUPPLY":
            closes_after = closed.iloc[zone["created_index"] + 1:]["close"]
            if not closes_after.empty and closes_after.max() > zone["zone_high"]:
                continue

        valid_zones.append(zone)

    return valid_zones


def _nearest_zone(price, zones, zone_type=None):
    filtered = [
        zone for zone in zones
        if zone_type is None or zone["type"] == zone_type
    ]

    if not filtered:
        return None

    return min(
        filtered,
        key=lambda zone: min(
            abs(price - zone["zone_low"]),
            abs(price - zone["zone_high"]),
        ),
    )


def analyze_supply_demand_context(df):
    """
    Returns dynamic supply/demand context:
    - nearest demand
    - nearest supply
    - bias if price is reacting from a zone
    """
    if len(df) < SD_LOOKBACK + 5:
        return None

    zones = _find_supply_demand_zones(df)
    zones = _invalidate_zones(df, zones)

    if not zones:
        logger.info("[SUPPLY DEMAND] No valid zones")
        return None

    entry = df.iloc[-2]
    atr = entry["atr_14"]
    price = entry["close"]

    if atr <= 0:
        return None

    demand = _nearest_zone(price, zones, "DEMAND")
    supply = _nearest_zone(price, zones, "SUPPLY")

    buffer = atr * SD_RETEST_BUFFER_ATR

    bias = "NEUTRAL"
    active_zone = None
    reasons = []

    if demand:
        demand_touched = (
            entry["low"] <= demand["zone_high"] + buffer
            and entry["close"] > demand["zone_low"]
        )

        if demand_touched:
            bias = "BUY"
            active_zone = demand
            reasons.append("demand_zone_retest")

    if supply:
        supply_touched = (
            entry["high"] >= supply["zone_low"] - buffer
            and entry["close"] < supply["zone_high"]
        )

        if supply_touched:
            bias = "SELL"
            active_zone = supply
            reasons.append("supply_zone_retest")

    return {
        "bias": bias,
        "active_zone": active_zone,
        "nearest_demand": demand,
        "nearest_supply": supply,
        "zones": zones,
        "reasons": reasons,
    }


def apply_supply_demand_confirmation(signal_data, context):
    """
    Soft confirmation layer.
    Boosts if signal agrees with active zone.
    Penalizes if it conflicts.
    """
    if not signal_data or context is None:
        return 0, []

    signal = signal_data.get("signal")
    strategy = signal_data.get("strategy")

    if signal not in ["BUY", "SELL"]:
        return 0, []

    if strategy == "SUPPLY_DEMAND_RETEST":
        return 0, []

    bias = context.get("bias")
    reasons = context.get("reasons", [])

    if bias == signal:
        return 3, ["supply_demand_aligned", *reasons]

    if bias in ["BUY", "SELL"] and bias != signal:
        return -2, [f"supply_demand_conflict_{bias.lower()}"]

    return 0, []