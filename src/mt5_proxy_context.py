from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional


PROXY_CONTEXT_MODE = "OBSERVE_ONLY"
PROXY_CONTEXT_FAMILY = "MT5_PROXY_CONTEXT"


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _timeframe_map(mt5):
    return {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
    }


def fetch_mt5_rates(symbol: str = "XAUUSD", timeframe_name: str = "M15", bars: int = 500):
    try:
        import MetaTrader5 as mt5
    except Exception as exc:
        return None, f"MetaTrader5 import failed: {exc}"

    timeframe = _timeframe_map(mt5).get(str(timeframe_name).upper(), mt5.TIMEFRAME_M15)

    if not mt5.initialize():
        return None, f"mt5.initialize failed: {mt5.last_error()}"

    try:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
        if rates is None:
            return None, f"copy_rates_from_pos failed: {mt5.last_error()}"
        return list(rates), None
    finally:
        mt5.shutdown()


def build_tick_volume_profile(rates, bin_size: float = 0.50) -> Optional[Dict[str, Any]]:
    volume_by_price = defaultdict(float)

    for row in rates or []:
        try:
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            volume = float(row["tick_volume"])
        except Exception:
            continue

        typical_price = (high + low + close) / 3.0
        price_bin = round(round(typical_price / bin_size) * bin_size, 2)
        volume_by_price[price_bin] += volume

    if not volume_by_price:
        return None

    sorted_bins = sorted(volume_by_price.items())
    total_volume = sum(v for _, v in sorted_bins)
    poc_price, poc_volume = max(sorted_bins, key=lambda item: item[1])

    target_value_area_volume = total_volume * 0.70
    selected = {poc_price}
    selected_volume = poc_volume

    price_to_volume = dict(sorted_bins)
    prices = [p for p, _ in sorted_bins]
    poc_index = prices.index(poc_price)

    left = poc_index - 1
    right = poc_index + 1

    while selected_volume < target_value_area_volume and (left >= 0 or right < len(prices)):
        left_volume = price_to_volume.get(prices[left], -1) if left >= 0 else -1
        right_volume = price_to_volume.get(prices[right], -1) if right < len(prices) else -1

        if right_volume >= left_volume:
            selected.add(prices[right])
            selected_volume += right_volume
            right += 1
        else:
            selected.add(prices[left])
            selected_volume += left_volume
            left -= 1

    return {
        "poc": poc_price,
        "poc_volume": round(poc_volume, 2),
        "value_area_low": min(selected),
        "value_area_high": max(selected),
        "total_tick_volume": round(total_volume, 2),
        "bin_size": bin_size,
        "bins_count": len(sorted_bins),
        "top_tick_volume_bins": [
            {"price": p, "tick_volume": round(v, 2)}
            for p, v in sorted(sorted_bins, key=lambda item: item[1], reverse=True)[:20]
        ],
    }


def classify_price_vs_value_area(price: Optional[float], profile: Optional[Dict[str, Any]]) -> str:
    if price is None or not profile:
        return "UNKNOWN"

    poc = profile["poc"]
    val = profile["value_area_low"]
    vah = profile["value_area_high"]
    bin_size = profile["bin_size"]

    if price < val:
        return "BELOW_VALUE_AREA"

    if price > vah:
        return "ABOVE_VALUE_AREA"

    if abs(price - poc) <= bin_size:
        return "NEAR_PROXY_POC"

    return "INSIDE_VALUE_AREA"


def calculate_recent_volume_context(rates, lookback: int = 50) -> Dict[str, Any]:
    if not rates:
        return {
            "latest_tick_volume": None,
            "average_tick_volume": None,
            "tick_volume_zscore": None,
            "volume_state": "UNKNOWN",
        }

    sample = rates[-lookback:] if len(rates) >= lookback else rates

    volumes: List[float] = []

    for row in sample:
        try:
            volumes.append(float(row["tick_volume"]))
        except Exception:
            pass

    if not volumes:
        return {
            "latest_tick_volume": None,
            "average_tick_volume": None,
            "tick_volume_zscore": None,
            "volume_state": "UNKNOWN",
        }

    latest = volumes[-1]
    avg = mean(volumes)
    sd = pstdev(volumes) if len(volumes) > 1 else 0.0

    zscore = 0.0 if sd == 0 else (latest - avg) / sd

    if zscore >= 2.0:
        state = "EXTREME_TICK_VOLUME"
    elif zscore >= 1.0:
        state = "HIGH_TICK_VOLUME"
    elif zscore <= -1.0:
        state = "LOW_TICK_VOLUME"
    else:
        state = "NORMAL_TICK_VOLUME"

    return {
        "latest_tick_volume": round(latest, 2),
        "average_tick_volume": round(avg, 2),
        "tick_volume_zscore": round(zscore, 3),
        "volume_state": state,
        "lookback": len(volumes),
    }


def calculate_latest_candle_context(rates) -> Dict[str, Any]:
    if not rates:
        return {
            "latest_close": None,
            "candle_direction": "UNKNOWN",
            "body_size": None,
            "range_size": None,
            "body_to_range_ratio": None,
        }

    row = rates[-1]

    open_price = _safe_float(row["open"])
    high = _safe_float(row["high"])
    low = _safe_float(row["low"])
    close = _safe_float(row["close"])

    if None in (open_price, high, low, close):
        return {
            "latest_close": close,
            "candle_direction": "UNKNOWN",
            "body_size": None,
            "range_size": None,
            "body_to_range_ratio": None,
        }

    body = abs(close - open_price)
    candle_range = max(0.0, high - low)
    ratio = None if candle_range == 0 else body / candle_range

    if close > open_price:
        direction = "BULLISH_CANDLE"
    elif close < open_price:
        direction = "BEARISH_CANDLE"
    else:
        direction = "DOJI_OR_FLAT"

    return {
        "latest_close": round(close, 2),
        "candle_direction": direction,
        "body_size": round(body, 2),
        "range_size": round(candle_range, 2),
        "body_to_range_ratio": round(ratio, 3) if ratio is not None else None,
    }


def build_mt5_proxy_context(
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    bars: int = 500,
    bin_size: float = 0.50,
) -> Dict[str, Any]:
    rates, error = fetch_mt5_rates(symbol=symbol, timeframe_name=timeframe, bars=bars)

    if error or not rates:
        return {
            "mode": PROXY_CONTEXT_MODE,
            "context_family": PROXY_CONTEXT_FAMILY,
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": bars,
            "available": False,
            "status": "MT5_PROXY_UNAVAILABLE",
            "is_real_order_flow": False,
            "data_quality": "PROXY_UNAVAILABLE",
            "decision_impact": "NONE",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "error": error,
            "warning": "MT5 proxy context is unavailable. This is not real COMEX order flow.",
            "profile": None,
            "volume_context": None,
            "candle_context": None,
            "price_vs_value_area": "UNKNOWN",
        }

    profile = build_tick_volume_profile(rates, bin_size=bin_size)
    volume_context = calculate_recent_volume_context(rates)
    candle_context = calculate_latest_candle_context(rates)
    latest_close = candle_context.get("latest_close")

    return {
        "mode": PROXY_CONTEXT_MODE,
        "context_family": PROXY_CONTEXT_FAMILY,
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": len(rates),
        "available": True,
        "status": "MT5_PROXY_AVAILABLE",
        "is_real_order_flow": False,
        "data_quality": "MT5_TICK_VOLUME_PROXY",
        "decision_impact": "NONE",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "error": None,
        "warning": (
            "This is MT5 tick-volume proxy context only. "
            "It is not real COMEX order flow, footprint, bid/ask delta, or DOM depth."
        ),
        "profile": profile,
        "volume_context": volume_context,
        "candle_context": candle_context,
        "price_vs_value_area": classify_price_vs_value_area(latest_close, profile),
    }