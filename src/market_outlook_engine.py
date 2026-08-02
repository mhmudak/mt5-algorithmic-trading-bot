
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import hashlib
import json
import math

import pandas as pd


PHASE = "PHASE_6S1_HTF_MARKET_OUTLOOK"
DEFAULT_SYMBOL = "XAUUSD"
DEFAULT_TIMEZONE = "Asia/Beirut"

REPORT_DIR = Path("data/reports/market_outlook")


@dataclass(frozen=True)
class OutlookConfig:
    symbol: str = DEFAULT_SYMBOL
    timezone: str = DEFAULT_TIMEZONE
    decision_impact: str = "NONE"
    auto_trade_allowed: bool = False
    can_execute: bool = False
    can_influence_decision: bool = False
    news_mode: str = "TECHNICAL_PLUS_NEWS_PLACEHOLDER"


def _round_price(value: Any, digits: int = 2) -> float | None:
    try:
        value = float(value)
    except Exception:
        return None

    if not math.isfinite(value):
        return None

    return round(value, digits)


def _safe_last_close(df: pd.DataFrame) -> float | None:
    if df is None or df.empty or "close" not in df:
        return None
    return _round_price(df.iloc[-1]["close"])


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.astype(float).ewm(span=period, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return tr.rolling(period).mean()


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    if "time" in out.columns:
        out["time"] = pd.to_datetime(out["time"], errors="coerce")

    for col in ["open", "high", "low", "close"]:
        out[col] = out[col].astype(float)

    out["ema_20"] = _ema(out["close"], 20)
    out["ema_50"] = _ema(out["close"], 50)
    out["atr_14"] = _atr(out, 14)

    return out.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def _trend_state(df: pd.DataFrame) -> dict[str, Any]:
    if df is None or len(df) < 55:
        return {
            "bias": "UNKNOWN",
            "reason": "not_enough_htf_data",
            "close": None,
            "ema_20": None,
            "ema_50": None,
            "atr_14": None,
        }

    last = df.iloc[-1]
    close = float(last["close"])
    ema20 = float(last["ema_20"])
    ema50 = float(last["ema_50"])
    atr = float(last["atr_14"]) if not pd.isna(last["atr_14"]) else None

    if close > ema20 > ema50:
        bias = "BULLISH"
        reason = "close_above_ema20_and_ema50"
    elif close < ema20 < ema50:
        bias = "BEARISH"
        reason = "close_below_ema20_and_ema50"
    else:
        bias = "MIXED"
        reason = "ema_structure_mixed"

    return {
        "bias": bias,
        "reason": reason,
        "close": _round_price(close),
        "ema_20": _round_price(ema20),
        "ema_50": _round_price(ema50),
        "atr_14": _round_price(atr),
    }


def _levels(df: pd.DataFrame, lookback: int) -> dict[str, Any]:
    if df is None or df.empty:
        return {
            "support": None,
            "resistance": None,
            "midpoint": None,
            "range_height": None,
            "position_in_range": None,
        }

    sample = df.tail(min(len(df), lookback)).copy()
    support = float(sample["low"].min())
    resistance = float(sample["high"].max())
    midpoint = (support + resistance) / 2.0
    height = resistance - support
    close = float(sample.iloc[-1]["close"])

    if height <= 0:
        position = None
    else:
        position = (close - support) / height

    return {
        "support": _round_price(support),
        "resistance": _round_price(resistance),
        "midpoint": _round_price(midpoint),
        "range_height": _round_price(height),
        "position_in_range": round(position, 3) if position is not None else None,
    }


def _range_zone(position: float | None) -> str:
    if position is None:
        return "UNKNOWN"
    if position <= 0.25:
        return "DISCOUNT_SUPPORT_SIDE"
    if position >= 0.75:
        return "PREMIUM_RESISTANCE_SIDE"
    return "MIDDLE_OF_RANGE"


def _combine_bias(w1: str, d1: str, h4: str, h1: str) -> str:
    bullish = [w1, d1, h4, h1].count("BULLISH")
    bearish = [w1, d1, h4, h1].count("BEARISH")

    if bullish >= 3:
        return "BULLISH"
    if bearish >= 3:
        return "BEARISH"
    if bullish > bearish:
        return "MIXED_BULLISH"
    if bearish > bullish:
        return "MIXED_BEARISH"
    return "MIXED"


def _favored_strategies(bias: str, zone: str) -> list[str]:
    if zone == "MIDDLE_OF_RANGE":
        return [
            "RANGE_SWEEP_RECLAIM",
            "FAILED_BREAKOUT_REVERSAL",
            "VWAP_RANGE_MEAN_REVERSION",
        ]

    if "BULLISH" in bias:
        return [
            "MICRO_SR_SWEEP_RECLAIM",
            "SESSION_ORB_RETEST",
            "FAILED_BREAKOUT_REVERSAL",
            "HTF_TREND_PULLBACK",
        ]

    if "BEARISH" in bias:
        return [
            "MICRO_SR_SWEEP_RECLAIM",
            "FAILED_FVG_REVERSAL",
            "FAILED_BREAKOUT_REVERSAL",
            "FCR_M1_FVG",
        ]

    return [
        "MICRO_SR_SWEEP_RECLAIM",
        "FAILED_BREAKOUT_REVERSAL",
        "RANGE_SWEEP_RECLAIM",
    ]


def _avoid_notes(zone: str) -> list[str]:
    notes = [
        "Do not execute from this report alone.",
        "M15/M5 confirmation and valid RR are required.",
    ]

    if zone == "MIDDLE_OF_RANGE":
        notes.append("Avoid chasing in the middle of the H1/H4 range.")

    notes.append("FCR_M1_FVG should not be trusted immediately after restart without fresh candle confirmation.")

    return notes


def _scenario_status(last_price: float | None, level: float | None, direction: str, tolerance: float) -> str:
    if last_price is None or level is None:
        return "UNKNOWN"

    distance = abs(last_price - level)

    if distance <= tolerance:
        return "AT_TRIGGER_ZONE"

    if direction == "BUY" and last_price > level:
        return "WAIT_FOR_SWEEP_OR_PULLBACK"

    if direction == "SELL" and last_price < level:
        return "WAIT_FOR_SWEEP_OR_REJECTION"

    return "APPROACHING"


def _scenario_closer(last_price: float | None, support: float | None, resistance: float | None) -> str:
    if last_price is None or support is None or resistance is None:
        return "UNKNOWN"

    distance_to_support = abs(last_price - support)
    distance_to_resistance = abs(resistance - last_price)

    if distance_to_support < distance_to_resistance:
        return "BUY_SCENARIO_CLOSER_SUPPORT_SWEEP_RECLAIM"
    if distance_to_resistance < distance_to_support:
        return "SELL_SCENARIO_CLOSER_RESISTANCE_REJECTION"
    return "BALANCED_NO_CLEAR_CLOSEST_SCENARIO"


def _session_name_from_hour(hour: int) -> str:
    # Beirut/session-planning model used by the bot:
    # ASIA 03:00-10:00, LONDON 10:00-15:00, NEWYORK 15:00-23:00.
    # OFF_HOURS is still tracked but not used as a main liquidity anchor.
    if 3 <= hour < 10:
        return "ASIA"
    if 10 <= hour < 15:
        return "LONDON"
    if 15 <= hour < 23:
        return "NEWYORK"
    return "OFF_HOURS"


def _range_summary(sample: pd.DataFrame, *, status: str) -> dict[str, Any]:
    if sample is None or sample.empty:
        return {
            "status": "UNAVAILABLE",
            "high": None,
            "low": None,
            "midpoint": None,
            "range_height": None,
            "candles": 0,
            "start_time": None,
            "end_time": None,
        }

    high = float(sample["high"].max())
    low = float(sample["low"].min())
    midpoint = (high + low) / 2.0

    start_time = sample.iloc[0].get("time")
    end_time = sample.iloc[-1].get("time")

    return {
        "status": status,
        "date": str(sample.iloc[-1].get("session_date", "")),
        "high": _round_price(high),
        "low": _round_price(low),
        "midpoint": _round_price(midpoint),
        "range_height": _round_price(high - low),
        "candles": int(len(sample)),
        "start_time": str(start_time) if start_time is not None else None,
        "end_time": str(end_time) if end_time is not None else None,
    }


def _session_liquidity_levels(m15_df: pd.DataFrame | None) -> dict[str, Any]:
    base = {
        "status": "UNAVAILABLE",
        "timeframe": "M15",
        "timezone_assumption": DEFAULT_TIMEZONE,
        "note": "Session ranges are derived from MT5 candle timestamps using Beirut session windows.",
        "current_session": None,
        "sessions": {},
        "previous_day": {
            "status": "UNAVAILABLE",
            "high": None,
            "low": None,
            "midpoint": None,
        },
    }

    if m15_df is None or m15_df.empty or "time" not in m15_df.columns:
        base["status"] = "M15_NOT_PROVIDED"
        return base

    df = m15_df.copy()
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time", "high", "low", "close"]).copy()

    if df.empty:
        base["status"] = "NO_VALID_M15_TIME_DATA"
        return base

    df["session_date"] = df["time"].dt.date.astype(str)
    df["session_hour"] = df["time"].dt.hour.astype(int)
    df["session_name"] = df["session_hour"].apply(_session_name_from_hour)

    last = df.iloc[-1]
    current_session = str(last["session_name"])
    current_date = str(last["session_date"])

    base["status"] = "AVAILABLE"
    base["current_session"] = {
        "name": current_session,
        "date": current_date,
        "time": str(last["time"]),
    }

    tradable = df[df["session_name"].isin(["ASIA", "LONDON", "NEWYORK"])].copy()

    for session_name in ["ASIA", "LONDON", "NEWYORK"]:
        s = tradable[tradable["session_name"] == session_name].copy()

        if s.empty:
            base["sessions"][session_name] = _range_summary(s, status="UNAVAILABLE")
            continue

        grouped = list(s.groupby("session_date"))
        latest_date, latest_sample = grouped[-1]

        if latest_date == current_date and session_name == current_session:
            status = "CURRENT_SESSION"
        else:
            status = "LATEST_OBSERVED_SESSION"

        summary = _range_summary(latest_sample, status=status)

        if len(grouped) >= 2:
            _previous_date, previous_sample = grouped[-2]
            summary["previous"] = _range_summary(previous_sample, status="PREVIOUS_OBSERVED_SESSION")
        else:
            summary["previous"] = {
                "status": "UNAVAILABLE",
                "high": None,
                "low": None,
                "midpoint": None,
            }

        base["sessions"][session_name] = summary

    all_dates = sorted(df["session_date"].unique())

    previous_dates = [d for d in all_dates if d < current_date]

    if previous_dates:
        previous_day = previous_dates[-1]
        sample = df[df["session_date"] == previous_day]
        base["previous_day"] = _range_summary(sample, status="PREVIOUS_DAY")

    return base


def _candidate_level(label: str, level_type: str, level: Any, last_price: float | None) -> dict[str, Any] | None:
    price = _round_price(level)

    if price is None or last_price is None:
        return None

    return {
        "label": label,
        "type": level_type,
        "price": price,
        "distance": _round_price(abs(float(last_price) - price)),
        "side": "ABOVE" if price >= float(last_price) else "BELOW",
    }


def _scenario_closer_with_session_liquidity(
    *,
    last_price: float | None,
    h1_levels: dict[str, Any],
    h4_levels: dict[str, Any],
    session_liquidity: dict[str, Any],
) -> dict[str, Any]:
    if last_price is None:
        return {
            "scenario_closer": "UNKNOWN",
            "nearest_liquidity": {},
        }

    buy_candidates = []
    sell_candidates = []

    for label, level in [
        ("H1_SUPPORT", h1_levels.get("support")),
        ("H4_SUPPORT", h4_levels.get("support")),
    ]:
        item = _candidate_level(label, "BUY_LIQUIDITY_BELOW", level, last_price)
        if item:
            buy_candidates.append(item)

    for label, level in [
        ("H1_RESISTANCE", h1_levels.get("resistance")),
        ("H4_RESISTANCE", h4_levels.get("resistance")),
    ]:
        item = _candidate_level(label, "SELL_LIQUIDITY_ABOVE", level, last_price)
        if item:
            sell_candidates.append(item)

    sessions = (session_liquidity or {}).get("sessions") or {}

    for session_name, session_data in sessions.items():
        low_item = _candidate_level(
            f"{session_name}_LOW",
            "BUY_SESSION_LIQUIDITY_LOW",
            session_data.get("low"),
            last_price,
        )
        high_item = _candidate_level(
            f"{session_name}_HIGH",
            "SELL_SESSION_LIQUIDITY_HIGH",
            session_data.get("high"),
            last_price,
        )

        if low_item:
            buy_candidates.append(low_item)
        if high_item:
            sell_candidates.append(high_item)

    previous_day = (session_liquidity or {}).get("previous_day") or {}

    prev_low = _candidate_level(
        "PREVIOUS_DAY_LOW",
        "BUY_PREVIOUS_DAY_LIQUIDITY_LOW",
        previous_day.get("low"),
        last_price,
    )
    prev_high = _candidate_level(
        "PREVIOUS_DAY_HIGH",
        "SELL_PREVIOUS_DAY_LIQUIDITY_HIGH",
        previous_day.get("high"),
        last_price,
    )

    if prev_low:
        buy_candidates.append(prev_low)
    if prev_high:
        sell_candidates.append(prev_high)

    nearest_buy = min(buy_candidates, key=lambda item: item["distance"]) if buy_candidates else None
    nearest_sell = min(sell_candidates, key=lambda item: item["distance"]) if sell_candidates else None

    if nearest_buy and nearest_sell:
        if nearest_buy["distance"] < nearest_sell["distance"]:
            closer = f"BUY_SCENARIO_CLOSER_NEAR_{nearest_buy['label']}"
        elif nearest_sell["distance"] < nearest_buy["distance"]:
            closer = f"SELL_SCENARIO_CLOSER_NEAR_{nearest_sell['label']}"
        else:
            closer = "BALANCED_SESSION_LIQUIDITY_DISTANCE"
    elif nearest_buy:
        closer = f"BUY_SCENARIO_CLOSER_NEAR_{nearest_buy['label']}"
    elif nearest_sell:
        closer = f"SELL_SCENARIO_CLOSER_NEAR_{nearest_sell['label']}"
    else:
        closer = _scenario_closer(
            last_price,
            h1_levels.get("support"),
            h1_levels.get("resistance"),
        )

    return {
        "scenario_closer": closer,
        "nearest_liquidity": {
            "buy": nearest_buy,
            "sell": nearest_sell,
            "buy_candidates_count": len(buy_candidates),
            "sell_candidates_count": len(sell_candidates),
        },
    }


def _clamp_score(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _distance_maturity_score(distance: float | None, reference_range: float | None) -> int:
    if distance is None:
        return 0

    try:
        distance = float(distance)
        reference_range = float(reference_range or 10.0)
    except Exception:
        return 0

    if reference_range <= 0:
        reference_range = 10.0

    # Close to liquidity = higher scenario maturity.
    # 0 distance => 45 points. Farther than 35% of range => near 0.
    ratio = distance / max(reference_range * 0.35, 1.0)
    return _clamp_score(45 * (1.0 - min(ratio, 1.0)))


def _bias_maturity_score(direction: str, combined_bias: str) -> int:
    combined_bias = str(combined_bias or "").upper()

    if direction == "BUY":
        if "BULLISH" in combined_bias:
            return 20
        if "BEARISH" in combined_bias:
            return 5
        return 12

    if direction == "SELL":
        if "BEARISH" in combined_bias:
            return 20
        if "BULLISH" in combined_bias:
            return 5
        return 12

    return 0


def _zone_maturity_score(direction: str, range_zone: str) -> int:
    range_zone = str(range_zone or "").upper()

    if direction == "BUY":
        if range_zone == "DISCOUNT_SUPPORT_SIDE":
            return 20
        if range_zone == "MIDDLE_OF_RANGE":
            return 7
        return 3

    if direction == "SELL":
        if range_zone == "PREMIUM_RESISTANCE_SIDE":
            return 20
        if range_zone == "MIDDLE_OF_RANGE":
            return 7
        return 3

    return 0


def _status_maturity_score(status: str) -> int:
    status = str(status or "").upper()

    if status == "AT_TRIGGER_ZONE":
        return 15
    if status == "APPROACHING":
        return 10
    if status.startswith("WAIT_FOR"):
        return 5

    return 0


def _action_state_from_maturity(status: str, maturity: int) -> str:
    status = str(status or "").upper()

    if status == "AT_TRIGGER_ZONE" and maturity >= 70:
        return "CONFIRMATION_PENDING"

    if status == "AT_TRIGGER_ZONE":
        return "AT_TRIGGER_ZONE"

    if maturity >= 70:
        return "SETUP_POSSIBLE_IF_CONFIRMATION_APPEARS"

    if maturity >= 45:
        return "APPROACHING"

    return "WAITING"


def _apply_scenario_maturity(
    *,
    scenarios: list[dict[str, Any]],
    combined_bias: str,
    range_zone: str,
    nearest_liquidity: dict[str, Any],
    h1_levels: dict[str, Any],
) -> dict[str, Any]:
    reference_range = h1_levels.get("range_height") or 10.0
    buy_nearest = (nearest_liquidity or {}).get("buy") or {}
    sell_nearest = (nearest_liquidity or {}).get("sell") or {}

    score_summary: dict[str, Any] = {
        "BUY": {
            "score": 0,
            "state": "WAITING",
            "nearest_level": buy_nearest,
        },
        "SELL": {
            "score": 0,
            "state": "WAITING",
            "nearest_level": sell_nearest,
        },
    }

    for scenario in scenarios:
        direction = str(scenario.get("direction") or "NONE").upper()

        if direction not in {"BUY", "SELL"}:
            scenario["maturity_score"] = 0
            scenario["action_state"] = "NO_TRADE"
            continue

        nearest = buy_nearest if direction == "BUY" else sell_nearest
        distance = nearest.get("distance")

        score = (
            _distance_maturity_score(distance, reference_range)
            + _bias_maturity_score(direction, combined_bias)
            + _zone_maturity_score(direction, range_zone)
            + _status_maturity_score(str(scenario.get("status")))
        )

        score = _clamp_score(score)
        action_state = _action_state_from_maturity(str(scenario.get("status")), score)

        scenario["maturity_score"] = score
        scenario["action_state"] = action_state
        scenario["nearest_liquidity_level"] = nearest

        score_summary[direction] = {
            "score": score,
            "state": action_state,
            "nearest_level": nearest,
        }

    buy_score = score_summary["BUY"]["score"]
    sell_score = score_summary["SELL"]["score"]

    if buy_score > sell_score:
        leader = "BUY"
    elif sell_score > buy_score:
        leader = "SELL"
    else:
        leader = "BALANCED"

    score_summary["leader"] = leader
    return score_summary



def _build_scenarios(
    *,
    symbol: str,
    last_price: float | None,
    h4_levels: dict[str, Any],
    h1_levels: dict[str, Any],
    combined_bias: str,
) -> list[dict[str, Any]]:
    support = h1_levels.get("support") or h4_levels.get("support")
    resistance = h1_levels.get("resistance") or h4_levels.get("resistance")
    atr_proxy = h1_levels.get("range_height") or h4_levels.get("range_height") or 10.0
    tolerance = max(1.0, float(atr_proxy) * 0.08)

    buy_status = _scenario_status(last_price, support, "BUY", tolerance)
    sell_status = _scenario_status(last_price, resistance, "SELL", tolerance)

    return [
        {
            "scenario_id": f"{symbol}-BUY-SUPPORT-SWEEP-RECLAIM",
            "direction": "BUY",
            "title": "Support sweep and reclaim",
            "level": support,
            "status": buy_status,
            "trigger_condition": f"Price sweeps below {support} then reclaims with M15/M5 confirmation",
            "confirmation_needed": [
                "liquidity sweep below support",
                "reclaim back above level",
                "M15/M5 structure shift",
                "valid SL/TP/RR from execution strategy",
            ],
            "applicable_strategies": [
                "MICRO_SR_SWEEP_RECLAIM",
                "FAILED_BREAKOUT_REVERSAL",
                "RANGE_SWEEP_RECLAIM",
            ],
            "can_become_setup": True,
        },
        {
            "scenario_id": f"{symbol}-SELL-RESISTANCE-REJECTION",
            "direction": "SELL",
            "title": "Resistance rejection or sweep failure",
            "level": resistance,
            "status": sell_status,
            "trigger_condition": f"Price sweeps/rejects {resistance} then breaks/reclaims lower structure",
            "confirmation_needed": [
                "liquidity sweep or rejection at resistance",
                "M15/M5 bearish structure shift",
                "valid SL/TP/RR from execution strategy",
            ],
            "applicable_strategies": [
                "FAILED_FVG_REVERSAL",
                "FAILED_BREAKOUT_REVERSAL",
                "MICRO_SR_SWEEP_RECLAIM",
                "FCR_M1_FVG",
            ],
            "can_become_setup": True,
        },
        {
            "scenario_id": f"{symbol}-NO-TRADE-MIDDLE-RANGE",
            "direction": "NONE",
            "title": "Middle-range no-trade condition",
            "level": h1_levels.get("midpoint"),
            "status": "ACTIVE_IF_PRICE_INSIDE_MIDDLE_RANGE",
            "trigger_condition": "Price remains between support and resistance without sweep/reclaim confirmation",
            "confirmation_needed": [
                "avoid low-quality middle-range continuation",
            ],
            "applicable_strategies": [],
            "can_become_setup": False,
        },
    ]


def build_market_outlook(
    frames: dict[str, pd.DataFrame],
    *,
    report_type: str = "daily",
    symbol: str = DEFAULT_SYMBOL,
    generated_at: datetime | None = None,
    news_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now()
    normalized = {}

    for timeframe, df in frames.items():
        normalized[timeframe.upper()] = _normalize_df(df)

    required = ["W1", "D1", "H4", "H1"]
    missing = [tf for tf in required if tf not in normalized or normalized[tf].empty]

    if missing:
        raise ValueError(f"Missing HTF data for: {missing}")

    w1_trend = _trend_state(normalized["W1"])
    d1_trend = _trend_state(normalized["D1"])
    h4_trend = _trend_state(normalized["H4"])
    h1_trend = _trend_state(normalized["H1"])

    combined_bias = _combine_bias(
        w1_trend["bias"],
        d1_trend["bias"],
        h4_trend["bias"],
        h1_trend["bias"],
    )

    h4_levels = _levels(normalized["H4"], 60)
    h1_levels = _levels(normalized["H1"], 48)
    session_liquidity = _session_liquidity_levels(normalized.get("M15"))

    last_price = _safe_last_close(normalized["H1"])
    zone = _range_zone(h1_levels.get("position_in_range"))

    scenarios = _build_scenarios(
        symbol=symbol,
        last_price=last_price,
        h4_levels=h4_levels,
        h1_levels=h1_levels,
        combined_bias=combined_bias,
    )

    closer_info = _scenario_closer_with_session_liquidity(
        last_price=last_price,
        h1_levels=h1_levels,
        h4_levels=h4_levels,
        session_liquidity=session_liquidity,
    )
    closer = closer_info["scenario_closer"]

    scenario_maturity = _apply_scenario_maturity(
        scenarios=scenarios,
        combined_bias=combined_bias,
        range_zone=zone,
        nearest_liquidity=closer_info.get("nearest_liquidity") or {},
        h1_levels=h1_levels,
    )

    news_events = news_events or []
    news_status = "MANUAL_REVIEW_REQUIRED" if not news_events else "NEWS_EVENTS_PROVIDED"

    outlook = {
        "phase": PHASE,
        "report_type": report_type.upper(),
        "symbol": symbol,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "decision_impact": "NONE",
        "auto_trade_allowed": False,
        "can_execute": False,
        "can_influence_decision": False,
        "last_price": last_price,
        "combined_htf_bias": combined_bias,
        "timeframe_bias": {
            "W1": w1_trend,
            "D1": d1_trend,
            "H4": h4_trend,
            "H1": h1_trend,
        },
        "levels": {
            "H4": h4_levels,
            "H1": h1_levels,
        },
        "session_liquidity": session_liquidity,
        "range_zone": zone,
        "scenario_closer": closer,
        "nearest_liquidity": closer_info.get("nearest_liquidity"),
        "scenario_maturity": scenario_maturity,
        "likely_scenarios": scenarios,
        "favored_strategies": _favored_strategies(combined_bias, zone),
        "avoid_notes": _avoid_notes(zone),
        "news_filter": {
            "status": news_status,
            "mode": "technical_report_with_news_placeholder",
            "events": news_events,
            "note": "Do not invent news. Connect a real economic calendar feed later or provide manual events.",
        },
    }

    outlook["fingerprint"] = market_outlook_fingerprint(outlook)
    return outlook


def market_outlook_fingerprint(outlook: dict[str, Any]) -> str:
    stable = {
        "symbol": outlook.get("symbol"),
        "report_type": outlook.get("report_type"),
        "combined_htf_bias": outlook.get("combined_htf_bias"),
        "range_zone": outlook.get("range_zone"),
        "scenario_closer": outlook.get("scenario_closer"),
        "levels": outlook.get("levels"),
        "session_liquidity": outlook.get("session_liquidity"),
        "nearest_liquidity": outlook.get("nearest_liquidity"),
        "scenario_maturity": outlook.get("scenario_maturity"),
        "likely_scenarios": [
            {
                "scenario_id": item.get("scenario_id"),
                "status": item.get("status"),
                "level": item.get("level"),
            }
            for item in outlook.get("likely_scenarios", [])
        ],
        "news_filter_status": (outlook.get("news_filter") or {}).get("status"),
    }

    raw = json.dumps(stable, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def format_market_outlook_telegram(outlook: dict[str, Any]) -> str:
    symbol = outlook.get("symbol", DEFAULT_SYMBOL)
    report_type = outlook.get("report_type", "DAILY")
    bias = outlook.get("combined_htf_bias", "UNKNOWN")
    last_price = outlook.get("last_price")
    zone = outlook.get("range_zone", "UNKNOWN")
    closer = outlook.get("scenario_closer", "UNKNOWN")

    h1 = (outlook.get("levels") or {}).get("H1", {})
    h4 = (outlook.get("levels") or {}).get("H4", {})

    session_liquidity = outlook.get("session_liquidity") or {}
    sessions = session_liquidity.get("sessions") or {}
    asia = sessions.get("ASIA") or {}
    london = sessions.get("LONDON") or {}
    newyork = sessions.get("NEWYORK") or {}
    previous_day = session_liquidity.get("previous_day") or {}

    nearest_liquidity = outlook.get("nearest_liquidity") or {}
    nearest_buy = nearest_liquidity.get("buy") or {}
    nearest_sell = nearest_liquidity.get("sell") or {}

    scenario_maturity = outlook.get("scenario_maturity") or {}
    buy_maturity = scenario_maturity.get("BUY") or {}
    sell_maturity = scenario_maturity.get("SELL") or {}

    scenarios = outlook.get("likely_scenarios") or []
    favored = outlook.get("favored_strategies") or []
    avoid_notes = outlook.get("avoid_notes") or []
    news_filter = outlook.get("news_filter") or {}

    lines = [
        f"📊 {report_type} HTF MARKET OUTLOOK",
        f"Symbol: {symbol}",
        f"Phase: {outlook.get('phase')}",
        "",
        f"Last Price: {last_price}",
        f"HTF Bias: {bias}",
        f"Range Zone: {zone}",
        f"Scenario Closer: {closer}",
        f"Scenario Leader: {scenario_maturity.get('leader')}",
        f"BUY Maturity: {buy_maturity.get('score')} / 100 | State: {buy_maturity.get('state')}",
        f"SELL Maturity: {sell_maturity.get('score')} / 100 | State: {sell_maturity.get('state')}",
        "",
        "Key Levels:",
        f"H1 Support: {h1.get('support')} | H1 Resistance: {h1.get('resistance')} | Mid: {h1.get('midpoint')}",
        f"H4 Support: {h4.get('support')} | H4 Resistance: {h4.get('resistance')} | Mid: {h4.get('midpoint')}",
        "",
        "Session Liquidity:",
        f"Current Session: {(session_liquidity.get('current_session') or {}).get('name')} | Time: {(session_liquidity.get('current_session') or {}).get('time')}",
        f"Asia High/Low: {asia.get('high')} / {asia.get('low')} [{asia.get('status')}]",
        f"London High/Low: {london.get('high')} / {london.get('low')} [{london.get('status')}]",
        f"New York High/Low: {newyork.get('high')} / {newyork.get('low')} [{newyork.get('status')}]",
        f"Previous Day High/Low: {previous_day.get('high')} / {previous_day.get('low')}",
        f"Nearest BUY Liquidity: {nearest_buy.get('label')} @ {nearest_buy.get('price')} distance={nearest_buy.get('distance')}",
        f"Nearest SELL Liquidity: {nearest_sell.get('label')} @ {nearest_sell.get('price')} distance={nearest_sell.get('distance')}",
        "",
        "Likely Scenarios:",
    ]

    for index, scenario in enumerate(scenarios, start=1):
        lines += [
            f"{index}. {scenario.get('title')} [{scenario.get('direction')}]",
            f"   Level: {scenario.get('level')}",
            f"   Status: {scenario.get('status')}",
            f"   Maturity: {scenario.get('maturity_score')} / 100",
            f"   Action State: {scenario.get('action_state')}",
            f"   Trigger: {scenario.get('trigger_condition')}",
            f"   Can Become Setup: {scenario.get('can_become_setup')}",
        ]

    lines += [
        "",
        "Favored Strategies:",
        ", ".join(favored) if favored else "None",
        "",
        "Avoid / Safety:",
    ]

    for note in avoid_notes:
        lines.append(f"- {note}")

    lines += [
        "",
        "News Filter:",
        f"Status: {news_filter.get('status')}",
        f"Note: {news_filter.get('note')}",
        "",
        "Decision Impact: NONE",
        "Auto Trade Allowed: False",
        "Execution: NO — setup confirmation still required.",
        "",
        f"Fingerprint: {outlook.get('fingerprint')}",
    ]

    return "\n".join(lines)



def save_market_outlook(outlook: dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    symbol = str(outlook.get("symbol", DEFAULT_SYMBOL)).replace("/", "_")
    report_type = str(outlook.get("report_type", "DAILY")).lower()
    timestamp = str(outlook.get("generated_at", datetime.now().isoformat(timespec="seconds")))
    safe_timestamp = timestamp.replace(":", "").replace("-", "").replace("T", "_").split(".")[0]

    path = REPORT_DIR / f"{symbol}_{report_type}_{safe_timestamp}.json"
    latest_path = REPORT_DIR / f"{symbol}_{report_type}_latest.json"

    text = json.dumps(outlook, indent=2, ensure_ascii=False, default=str)
    path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")

    return path


def load_latest_market_outlook(symbol: str, report_type: str) -> dict[str, Any] | None:
    symbol = symbol.replace("/", "_")
    latest_path = REPORT_DIR / f"{symbol}_{report_type.lower()}_latest.json"

    if not latest_path.exists():
        return None

    try:
        return json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def outlook_changed(previous: dict[str, Any] | None, current: dict[str, Any]) -> bool:
    if not previous:
        return True

    return previous.get("fingerprint") != current.get("fingerprint")
