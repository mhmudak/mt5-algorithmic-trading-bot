import numpy as np


VP_LOOKBACK = 120
VP_BINS = 48

LVN_THRESHOLD_RATIO = 0.35
HVN_THRESHOLD_RATIO = 0.75

VALUE_AREA_PERCENT = 0.70


def _get_volume_column(df):
    if "real_volume" in df.columns and df["real_volume"].sum() > 0:
        return "real_volume"

    if "tick_volume" in df.columns and df["tick_volume"].sum() > 0:
        return "tick_volume"

    return None


def build_volume_profile(df, lookback=VP_LOOKBACK, bins=VP_BINS):
    """
    Approximate volume profile using MT5 candle volume.

    For many CFD/spot symbols, tick_volume is used as the available proxy.
    """
    if df is None or len(df) < lookback:
        return None

    closed = df.iloc[:-1].copy()
    profile_df = closed.iloc[-lookback:].copy()

    volume_col = _get_volume_column(profile_df)
    if volume_col is None:
        return None

    price_low = profile_df["low"].min()
    price_high = profile_df["high"].max()

    if price_high <= price_low:
        return None

    edges = np.linspace(price_low, price_high, bins + 1)
    volumes = np.zeros(bins)

    for _, row in profile_df.iterrows():
        typical_price = (row["high"] + row["low"] + row["close"]) / 3
        volume = row[volume_col]

        idx = np.searchsorted(edges, typical_price, side="right") - 1
        idx = max(0, min(idx, bins - 1))

        volumes[idx] += volume

    max_volume = volumes.max()
    total_volume = volumes.sum()

    if max_volume <= 0 or total_volume <= 0:
        return None

    centers = (edges[:-1] + edges[1:]) / 2
    poc_index = int(np.argmax(volumes))
    poc = centers[poc_index]

    lvn_levels = []
    hvn_levels = []

    for i, volume in enumerate(volumes):
        ratio = volume / max_volume

        level_data = {
            "price": round(float(centers[i]), 2),
            "volume": float(volume),
            "ratio": round(float(ratio), 3),
            "low": round(float(edges[i]), 2),
            "high": round(float(edges[i + 1]), 2),
        }

        if ratio <= LVN_THRESHOLD_RATIO:
            lvn_levels.append(level_data)

        if ratio >= HVN_THRESHOLD_RATIO:
            hvn_levels.append(level_data)

    # Value area approximation around POC
    target_volume = total_volume * VALUE_AREA_PERCENT
    selected_volume = volumes[poc_index]
    low_idx = poc_index
    high_idx = poc_index

    while selected_volume < target_volume and (low_idx > 0 or high_idx < bins - 1):
        next_low_volume = volumes[low_idx - 1] if low_idx > 0 else -1
        next_high_volume = volumes[high_idx + 1] if high_idx < bins - 1 else -1

        if next_high_volume >= next_low_volume:
            high_idx += 1
            selected_volume += volumes[high_idx]
        else:
            low_idx -= 1
            selected_volume += volumes[low_idx]

    return {
        "poc": round(float(poc), 2),
        "value_area_low": round(float(edges[low_idx]), 2),
        "value_area_high": round(float(edges[high_idx + 1]), 2),
        "lvn_levels": lvn_levels,
        "hvn_levels": hvn_levels,
        "price_low": round(float(price_low), 2),
        "price_high": round(float(price_high), 2),
        "volume_source": volume_col,
    }


def find_nearest_lvn(price, profile, max_distance):
    if profile is None:
        return None

    candidates = []

    for node in profile.get("lvn_levels", []):
        distance = abs(price - node["price"])

        if distance <= max_distance:
            candidates.append((distance, node))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def find_target_hvn_or_poc(signal, entry_price, profile):
    if profile is None:
        return None, None

    poc = profile.get("poc")

    if signal == "BUY":
        hvn_above = [
            node for node in profile.get("hvn_levels", [])
            if node["price"] > entry_price
        ]

        if hvn_above:
            target = min(hvn_above, key=lambda node: node["price"])
            return target["price"], "NEAREST_HVN_ABOVE"

        if poc and poc > entry_price:
            return poc, "POC_TARGET"

    if signal == "SELL":
        hvn_below = [
            node for node in profile.get("hvn_levels", [])
            if node["price"] < entry_price
        ]

        if hvn_below:
            target = max(hvn_below, key=lambda node: node["price"])
            return target["price"], "NEAREST_HVN_BELOW"

        if poc and poc < entry_price:
            return poc, "POC_TARGET"

    return None, None