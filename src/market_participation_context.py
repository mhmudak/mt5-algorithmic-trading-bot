from __future__ import annotations

import json
import math
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, Optional

from src.logger import logger


SCHEMA_VERSION = 1
OBSERVATION_FILENAME = "market_participation_observations.jsonl"
MAX_TAPE_SECONDS = 90.0
MAX_TAPE_SAMPLES = 4096
MIN_SHORT_WINDOW_SAMPLES = 3

_TICK_TAPE = deque(maxlen=MAX_TAPE_SAMPLES)
_TICK_LOCK = threading.Lock()
_LAST_TICK_KEY = None
_RITHMIC_CACHE = {}
_RITHMIC_LOCK = threading.Lock()

# Notification-only participation alert state.
# These thresholds never affect trading decisions.
_HIGH_IMPACT_ALERT_LOCK = threading.Lock()
_LAST_HIGH_IMPACT_ALERT = {}

DEFAULT_HIGH_IMPACT_ALERT_COOLDOWN_SECONDS = 300.0
HIGH_IMPACT_MIN_5S_SAMPLES = 5
HIGH_IMPACT_MIN_OBSERVED_SPAN_SECONDS = 2.0
HIGH_IMPACT_MIN_DIRECTIONAL_IMBALANCE = 0.60


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        value = float(value)
        if not math.isfinite(value):
            return None
        return value
    except Exception:
        return None


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    value = str(value).strip()
    return value if value else default


def _json_safe(value: Any):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


def _tick_value(tick: Any, name: str, default=None):
    if isinstance(tick, dict):
        return tick.get(name, default)
    return getattr(tick, name, default)


def _tick_epoch(tick: Any, fallback: Optional[float] = None) -> float:
    time_msc = _safe_float(_tick_value(tick, "time_msc"))
    if time_msc is not None and time_msc > 0:
        return time_msc / 1000.0

    time_seconds = _safe_float(_tick_value(tick, "time"))
    if time_seconds is not None and time_seconds > 0:
        return time_seconds

    return float(fallback if fallback is not None else time.time())


def _prune_locked(now_epoch: float) -> None:
    cutoff = now_epoch - MAX_TAPE_SECONDS
    while _TICK_TAPE and _TICK_TAPE[0]["epoch"] < cutoff:
        _TICK_TAPE.popleft()


def record_mt5_tick(tick: Any, *, observed_at_epoch: Optional[float] = None) -> bool:
    """Record the latest MT5 quote observed by the bot loop.

    This is explicitly a bot-loop sampled quote tape, not a complete broker tick feed.
    It is research-only and never affects execution.
    """

    global _LAST_TICK_KEY

    try:
        if tick is None:
            return False

        bid = _safe_float(_tick_value(tick, "bid"))
        ask = _safe_float(_tick_value(tick, "ask"))

        if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
            return False

        epoch = _tick_epoch(tick, observed_at_epoch)
        mid = (bid + ask) / 2.0
        spread = ask - bid
        time_msc = _safe_float(_tick_value(tick, "time_msc"))

        key = (
            int(time_msc) if time_msc is not None else round(epoch, 3),
            round(bid, 8),
            round(ask, 8),
        )

        with _TICK_LOCK:
            if key == _LAST_TICK_KEY:
                _prune_locked(epoch)
                return False

            _TICK_TAPE.append(
                {
                    "epoch": float(epoch),
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                    "spread": spread,
                }
            )
            _LAST_TICK_KEY = key
            _prune_locked(epoch)

        return True
    except Exception as exc:
        logger.warning(
            "[MARKET PARTICIPATION] MT5 tick record failed open: "
            f"{exc}"
        )
        return False


def _window_snapshot(samples: list[dict], now_epoch: float, seconds: float) -> Dict[str, Any]:
    cutoff = now_epoch - seconds
    window = [row for row in samples if row["epoch"] >= cutoff]

    if not window:
        return {
            "seconds": seconds,
            "sample_count": 0,
            "observed_span_seconds": 0.0,
            "quote_change_rate_proxy_hz": None,
            "mid_move": None,
            "up_moves": 0,
            "down_moves": 0,
            "flat_moves": 0,
            "directional_imbalance": None,
            "median_spread": None,
        }

    mids = [row["mid"] for row in window]
    spreads = [row["spread"] for row in window]

    up = 0
    down = 0
    flat = 0

    for previous, current in zip(mids, mids[1:]):
        if current > previous:
            up += 1
        elif current < previous:
            down += 1
        else:
            flat += 1

    directional_total = up + down
    imbalance = (
        (up - down) / directional_total
        if directional_total > 0
        else 0.0
    )

    span = max(0.0, window[-1]["epoch"] - window[0]["epoch"])
    effective_span = max(span, min(seconds, 1.0))
    rate = len(window) / effective_span if effective_span > 0 else None

    return {
        "seconds": seconds,
        "sample_count": len(window),
        "observed_span_seconds": round(span, 3),
        "quote_change_rate_proxy_hz": round(rate, 3) if rate is not None else None,
        "mid_move": round(mids[-1] - mids[0], 6),
        "up_moves": up,
        "down_moves": down,
        "flat_moves": flat,
        "directional_imbalance": round(imbalance, 4),
        "median_spread": round(median(spreads), 6),
    }


def build_mt5_tick_participation_context(*, now_epoch: Optional[float] = None) -> Dict[str, Any]:
    now_epoch = float(now_epoch if now_epoch is not None else time.time())

    with _TICK_LOCK:
        _prune_locked(now_epoch)
        samples = list(_TICK_TAPE)

    w5 = _window_snapshot(samples, now_epoch, 5.0)
    w15 = _window_snapshot(samples, now_epoch, 15.0)
    w60 = _window_snapshot(samples, now_epoch, 60.0)

    short_rate = _safe_float(w5.get("quote_change_rate_proxy_hz"))
    baseline_rate = _safe_float(w60.get("quote_change_rate_proxy_hz"))
    acceleration_ratio = None

    if short_rate is not None and baseline_rate is not None and baseline_rate > 0:
        acceleration_ratio = short_rate / baseline_rate

    if w5["sample_count"] < MIN_SHORT_WINDOW_SAMPLES:
        activity_state = "INSUFFICIENT_MT5_TICK_SAMPLE"
    elif acceleration_ratio is not None and acceleration_ratio >= 1.50:
        activity_state = "ACCELERATING_QUOTE_ACTIVITY"
    elif acceleration_ratio is not None and acceleration_ratio >= 1.10:
        activity_state = "ELEVATED_QUOTE_ACTIVITY"
    else:
        activity_state = "NORMAL_OR_UNRESOLVED_QUOTE_ACTIVITY"

    move = _safe_float(w5.get("mid_move"))
    imbalance = _safe_float(w5.get("directional_imbalance"))

    if (
        move is not None
        and imbalance is not None
        and move > 0
        and imbalance >= 0.20
    ):
        pressure = "BUY_PRESSURE_PROXY"
    elif (
        move is not None
        and imbalance is not None
        and move < 0
        and imbalance <= -0.20
    ):
        pressure = "SELL_PRESSURE_PROXY"
    else:
        pressure = "NEUTRAL_OR_MIXED_PRESSURE_PROXY"

    current = samples[-1] if samples else None

    return {
        "available": bool(samples),
        "source": "MT5_BOT_LOOP_SAMPLED_QUOTES",
        "is_complete_tick_feed": False,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "activity_state": activity_state,
        "pressure_state": pressure,
        "quote_activity_acceleration_ratio": (
            round(acceleration_ratio, 4)
            if acceleration_ratio is not None
            else None
        ),
        "current_bid": round(current["bid"], 6) if current else None,
        "current_ask": round(current["ask"], 6) if current else None,
        "current_mid": round(current["mid"], 6) if current else None,
        "current_spread": round(current["spread"], 6) if current else None,
        "windows": {
            "5s": w5,
            "15s": w15,
            "60s": w60,
        },
        "warning": (
            "MT5 activity is a bot-loop sampled quote-change proxy. "
            "It does not identify participants and may miss multiple broker ticks between loops."
        ),
    }


def _classify_rithmic_direction(metrics: dict) -> str:
    imbalance = _safe_float(metrics.get("footprint_imbalance"))
    delta = _safe_float(metrics.get("delta"))

    if imbalance is not None and abs(imbalance) >= 0.05:
        return "BUY_AGGRESSION" if imbalance > 0 else "SELL_AGGRESSION"

    if delta is not None and delta != 0:
        return "BUY_AGGRESSION" if delta > 0 else "SELL_AGGRESSION"

    return "NEUTRAL_OR_UNRESOLVED_AGGRESSION"


def _classify_dom_direction(metrics: dict) -> str:
    dom = _safe_float(metrics.get("dom_depth_imbalance"))

    if dom is None or abs(dom) < 0.05:
        return "DOM_NEUTRAL_OR_UNAVAILABLE"

    return "BID_DEPTH_DOMINANT" if dom > 0 else "ASK_DEPTH_DOMINANT"


def _read_rithmic_participation_context(
    *,
    symbol: str,
    provider=None,
) -> Dict[str, Any]:
    """Read observe-only CME/Rithmic context.

    If provider is omitted, an explicit RITHMIC_SYMBOL must be configured. This
    avoids silently binding research to an expired futures contract.
    """

    try:
        configured_symbol = os.getenv("RITHMIC_SYMBOL", "").strip()

        if provider is None:
            if not configured_symbol:
                return {
                    "available": False,
                    "source": "RITHMIC",
                    "status": "RITHMIC_SYMBOL_NOT_CONFIGURED",
                    "decision_impact": "NONE",
                    "can_influence_decision": False,
                    "safe_for_execution": False,
                    "metrics": {},
                    "aggression_state": "UNAVAILABLE",
                    "dom_state": "UNAVAILABLE",
                    "warning": (
                        "Set RITHMIC_SYMBOL explicitly to the active CME gold contract "
                        "before using live Rithmic context."
                    ),
                }

            from src.order_flow_adapter import get_order_flow_provider

            provider = get_order_flow_provider("RITHMIC")

        snapshot = provider.get_latest_snapshot(symbol)
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        metrics = snapshot.get("metrics") or {}
        available = bool(snapshot.get("available"))

        return {
            "available": available,
            "source": _safe_text(snapshot.get("provider"), "RITHMIC"),
            "status": _safe_text(snapshot.get("status"), "UNKNOWN"),
            "rithmic_symbol": snapshot.get("symbol") or configured_symbol or None,
            "requested_symbol": snapshot.get("requested_symbol") or symbol,
            "exchange": snapshot.get("exchange"),
            "data_quality": snapshot.get("data_quality"),
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "safe_for_execution": False,
            "metrics": {
                "bid_volume": metrics.get("bid_volume"),
                "ask_volume": metrics.get("ask_volume"),
                "delta": metrics.get("delta"),
                "cumulative_delta": metrics.get("cumulative_delta"),
                "footprint_imbalance": metrics.get("footprint_imbalance"),
                "dom_bid_depth": metrics.get("dom_bid_depth"),
                "dom_ask_depth": metrics.get("dom_ask_depth"),
                "dom_depth_imbalance": metrics.get("dom_depth_imbalance"),
                "volume_profile_poc": metrics.get("volume_profile_poc"),
            },
            "aggression_state": _classify_rithmic_direction(metrics) if available else "UNAVAILABLE",
            "dom_state": _classify_dom_direction(metrics) if available else "UNAVAILABLE",
            "freshness": (snapshot.get("rithmic_status") or {}).get("freshness"),
            "warning": snapshot.get("warning"),
        }
    except Exception as exc:
        logger.warning(
            "[MARKET PARTICIPATION] Rithmic context failed open: "
            f"{exc}"
        )
        return {
            "available": False,
            "source": "RITHMIC",
            "status": "RITHMIC_CONTEXT_ERROR",
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "safe_for_execution": False,
            "metrics": {},
            "aggression_state": "UNAVAILABLE",
            "dom_state": "UNAVAILABLE",
            "error": str(exc),
        }


def refresh_rithmic_participation_context(
    *,
    symbol: str,
    provider=None,
    now_epoch: Optional[float] = None,
    min_refresh_interval_seconds: float = 1.0,
) -> Dict[str, Any]:
    """Refresh the observe-only Rithmic snapshot cache outside order-send latency."""

    now_epoch = float(now_epoch if now_epoch is not None else time.time())
    key = str(symbol).upper()

    if provider is None and min_refresh_interval_seconds > 0:
        with _RITHMIC_LOCK:
            cached = dict(_RITHMIC_CACHE.get(key) or {})
        cached_at = _safe_float(cached.get("cached_at_epoch"))
        context = cached.get("context")
        if isinstance(context, dict) and cached_at is not None:
            age = max(0.0, now_epoch - cached_at)
            if age < float(min_refresh_interval_seconds):
                result = dict(context)
                result["cache_age_seconds"] = round(age, 3)
                result["cache_status"] = "REFRESH_THROTTLED_FRESH_CACHE"
                return result

    context = _read_rithmic_participation_context(
        symbol=symbol,
        provider=provider,
    )

    with _RITHMIC_LOCK:
        _RITHMIC_CACHE[key] = {
            "cached_at_epoch": now_epoch,
            "context": context,
        }

    return context


def get_cached_rithmic_participation_context(
    *,
    symbol: str,
    max_age_seconds: float = 5.0,
    now_epoch: Optional[float] = None,
) -> Dict[str, Any]:
    now_epoch = float(now_epoch if now_epoch is not None else time.time())

    with _RITHMIC_LOCK:
        cached = dict(_RITHMIC_CACHE.get(str(symbol).upper()) or {})

    context = cached.get("context")
    cached_at = _safe_float(cached.get("cached_at_epoch"))

    if isinstance(context, dict) and cached_at is not None:
        age = max(0.0, now_epoch - cached_at)
        if age <= max_age_seconds:
            result = dict(context)
            result["cache_age_seconds"] = round(age, 3)
            result["cache_status"] = "FRESH_CACHE"
            return result

    return {
        "available": False,
        "source": "RITHMIC",
        "status": "RITHMIC_CONTEXT_CACHE_MISSING_OR_STALE",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "metrics": {},
        "aggression_state": "UNAVAILABLE",
        "dom_state": "UNAVAILABLE",
        "cache_status": "MISSING_OR_STALE",
    }


def _combined_state(mt5_context: dict, rithmic_context: dict) -> str:
    mt5_pressure = _safe_text(mt5_context.get("pressure_state"), "")
    rithmic_state = _safe_text(rithmic_context.get("aggression_state"), "")

    mt5_buy = mt5_pressure == "BUY_PRESSURE_PROXY"
    mt5_sell = mt5_pressure == "SELL_PRESSURE_PROXY"
    rithmic_buy = rithmic_state == "BUY_AGGRESSION"
    rithmic_sell = rithmic_state == "SELL_AGGRESSION"

    if not rithmic_context.get("available"):
        if mt5_buy:
            return "MT5_ONLY_BUY_PRESSURE_PROXY"
        if mt5_sell:
            return "MT5_ONLY_SELL_PRESSURE_PROXY"
        return "MT5_ONLY_NEUTRAL_OR_UNRESOLVED"

    move_5s = _safe_float(
        ((mt5_context.get("windows") or {}).get("5s") or {}).get("mid_move")
    )

    if rithmic_buy and move_5s is not None and move_5s <= 0:
        return "POTENTIAL_BUY_AGGRESSION_ABSORPTION"
    if rithmic_sell and move_5s is not None and move_5s >= 0:
        return "POTENTIAL_SELL_AGGRESSION_ABSORPTION"

    if mt5_buy and rithmic_buy:
        return "CROSS_MARKET_BUY_ALIGNED"
    if mt5_sell and rithmic_sell:
        return "CROSS_MARKET_SELL_ALIGNED"
    if (mt5_buy and rithmic_sell) or (mt5_sell and rithmic_buy):
        return "CROSS_MARKET_DIVERGENCE"
    if rithmic_buy:
        return "RITHMIC_BUY_AGGRESSION_MT5_UNRESOLVED"
    if rithmic_sell:
        return "RITHMIC_SELL_AGGRESSION_MT5_UNRESOLVED"

    return "CROSS_MARKET_NEUTRAL_OR_UNRESOLVED"


def _signal_relation(signal: str, combined_state: str) -> str:
    signal = _safe_text(signal).upper()

    buy_states = {
        "CROSS_MARKET_BUY_ALIGNED",
        "MT5_ONLY_BUY_PRESSURE_PROXY",
        "RITHMIC_BUY_AGGRESSION_MT5_UNRESOLVED",
    }
    sell_states = {
        "CROSS_MARKET_SELL_ALIGNED",
        "MT5_ONLY_SELL_PRESSURE_PROXY",
        "RITHMIC_SELL_AGGRESSION_MT5_UNRESOLVED",
    }

    if combined_state in buy_states:
        return "WITH_SIGNAL" if signal == "BUY" else "COUNTER_SIGNAL" if signal == "SELL" else "SIGNAL_UNKNOWN"
    if combined_state in sell_states:
        return "WITH_SIGNAL" if signal == "SELL" else "COUNTER_SIGNAL" if signal == "BUY" else "SIGNAL_UNKNOWN"
    if "ABSORPTION" in combined_state or "DIVERGENCE" in combined_state:
        return "MIXED_OR_TRANSITIONAL"
    return "UNRESOLVED"


def build_market_participation_context(
    *,
    symbol: str,
    signal: Optional[str] = None,
    tick: Any = None,
    provider=None,
    now_epoch: Optional[float] = None,
) -> Dict[str, Any]:
    """Build universal participation context for any detected setup or execution.

    This is an evidence layer, not a participant-identity detector. It cannot know
    whether a bank, company, fund, CTA, market maker, or retail trader caused flow.
    """

    now_epoch = float(now_epoch if now_epoch is not None else time.time())

    if tick is not None:
        record_mt5_tick(tick, observed_at_epoch=now_epoch)

    mt5_context = build_mt5_tick_participation_context(now_epoch=now_epoch)
    if provider is not None:
        rithmic_context = _read_rithmic_participation_context(
            symbol=symbol,
            provider=provider,
        )
    else:
        rithmic_context = get_cached_rithmic_participation_context(
            symbol=symbol,
            now_epoch=now_epoch,
        )
    combined_state = _combined_state(mt5_context, rithmic_context)

    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at": datetime.fromtimestamp(
            now_epoch,
            tz=timezone.utc,
        ).isoformat(),
        "symbol": symbol,
        "signal": _safe_text(signal, "UNKNOWN").upper(),
        "record_type": "MARKET_PARTICIPATION_CONTEXT",
        "identity_inference": "PARTICIPANT_IDENTITY_NOT_OBSERVABLE",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "source_coverage": (
            "MT5_PLUS_RITHMIC"
            if rithmic_context.get("available")
            else "MT5_ONLY"
        ),
        "combined_state": combined_state,
        "signal_relation": _signal_relation(signal or "", combined_state),
        "mt5": mt5_context,
        "rithmic": rithmic_context,
        "notes": [
            "This context estimates participation signatures; it does not identify companies or institutions.",
            "Rithmic is observe-only and has no execution authority.",
            "MT5 quote activity is sampled by the bot loop and is not full exchange order flow.",
        ],
    }



def _format_participation_value(
    value: Any,
    *,
    digits: int = 3,
) -> str:
    number = _safe_float(value)

    if number is None:
        return "N/A"

    return str(
        round(
            number,
            digits,
        )
    )


def _short_activity_state(
    value: Any,
) -> str:
    mapping = {
        "ACCELERATING_QUOTE_ACTIVITY": "ACCELERATING",
        "ELEVATED_QUOTE_ACTIVITY": "ELEVATED",
        "NORMAL_OR_UNRESOLVED_QUOTE_ACTIVITY": (
            "NORMAL / UNRESOLVED"
        ),
        "INSUFFICIENT_MT5_TICK_SAMPLE": (
            "INSUFFICIENT SAMPLE"
        ),
    }

    text = _safe_text(
        value,
        "UNAVAILABLE",
    )

    return mapping.get(
        text,
        text,
    )


def _short_pressure_state(
    value: Any,
) -> str:
    mapping = {
        "BUY_PRESSURE_PROXY": "BUY",
        "SELL_PRESSURE_PROXY": "SELL",
        "NEUTRAL_OR_MIXED_PRESSURE_PROXY": (
            "NEUTRAL / MIXED"
        ),
    }

    text = _safe_text(
        value,
        "UNAVAILABLE",
    )

    return mapping.get(
        text,
        text,
    )


def format_market_participation_telegram_block(
    context: dict | None,
) -> str:
    """
    Compact operator-facing context.

    MT5-only data is always labelled as a proxy.
    No institutional identity is inferred.
    """

    if not isinstance(
        context,
        dict,
    ):
        return (
            "🏦 Market Participation — Unavailable\n"
            "Context: unavailable\n"
            "Mode: OBSERVE ONLY"
        )

    source_coverage = _safe_text(
        context.get(
            "source_coverage"
        ),
        "MT5_ONLY",
    )

    if source_coverage == "MT5_PLUS_RITHMIC":
        title = (
            "🏦 Market Participation — "
            "MT5 + Rithmic"
        )
    else:
        title = (
            "🏦 Market Participation — "
            "MT5 Proxy"
        )

    mt5_context = (
        context.get(
            "mt5"
        )
        if isinstance(
            context.get(
                "mt5"
            ),
            dict,
        )
        else {}
    )

    window_5s = (
        (
            mt5_context.get(
                "windows"
            )
            or {}
        ).get(
            "5s"
        )
        or {}
    )

    lines = [
        title,
        (
            "Activity: "
            + _short_activity_state(
                mt5_context.get(
                    "activity_state"
                )
            )
        ),
        (
            "Pressure: "
            + _short_pressure_state(
                mt5_context.get(
                    "pressure_state"
                )
            )
        ),
        (
            "5s Imbalance: "
            + _format_participation_value(
                window_5s.get(
                    "directional_imbalance"
                ),
                digits=2,
            )
        ),
        (
            "5s Move: "
            + _format_participation_value(
                window_5s.get(
                    "mid_move"
                ),
                digits=3,
            )
        ),
        (
            "Activity Acceleration: "
            + _format_participation_value(
                mt5_context.get(
                    "quote_activity_acceleration_ratio"
                ),
                digits=2,
            )
        ),
        (
            "Signal Relation: "
            + _safe_text(
                context.get(
                    "signal_relation"
                ),
                "UNRESOLVED",
            )
        ),
    ]

    rithmic = (
        context.get(
            "rithmic"
        )
        if isinstance(
            context.get(
                "rithmic"
            ),
            dict,
        )
        else {}
    )

    if bool(
        rithmic.get(
            "available"
        )
    ):
        lines.extend(
            [
                (
                    "Rithmic Aggression: "
                    + _safe_text(
                        rithmic.get(
                            "aggression_state"
                        ),
                        "UNAVAILABLE",
                    )
                ),
                (
                    "DOM: "
                    + _safe_text(
                        rithmic.get(
                            "dom_state"
                        ),
                        "UNAVAILABLE",
                    )
                ),
                (
                    "Combined: "
                    + _safe_text(
                        context.get(
                            "combined_state"
                        ),
                        "UNRESOLVED",
                    )
                ),
            ]
        )

    else:
        lines.append(
            "Rithmic: UNAVAILABLE / NOT CONNECTED"
        )

    lines.append(
        "Mode: OBSERVE ONLY"
    )

    return "\n".join(
        lines
    )


def classify_market_participation_alert(
    context: dict | None,
) -> dict[str, Any]:
    """
    Classify an operator notification only.

    HIGH_IMPACT does not mean guaranteed direction,
    institutional identity, or execution permission.
    """

    result = {
        "observer_only": True,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
        "severity": "NORMAL",
        "state": "NO_HIGH_IMPACT_ALERT",
        "reason": (
            "high_impact_conditions_not_met"
        ),
        "direction": None,
        "source_coverage": None,
        "sample_count_5s": None,
        "observed_span_seconds_5s": None,
        "directional_imbalance_5s": None,
        "mid_move_5s": None,
        "activity_acceleration_ratio": None,
        "should_notify_candidate": False,
    }

    if not isinstance(
        context,
        dict,
    ):
        result.update(
            {
                "state": "CONTEXT_UNAVAILABLE",
                "reason": (
                    "market_participation_context_"
                    "unavailable"
                ),
            }
        )

        return result

    mt5_context = (
        context.get(
            "mt5"
        )
        if isinstance(
            context.get(
                "mt5"
            ),
            dict,
        )
        else {}
    )

    window_5s = (
        (
            mt5_context.get(
                "windows"
            )
            or {}
        ).get(
            "5s"
        )
        or {}
    )

    activity_state = _safe_text(
        mt5_context.get(
            "activity_state"
        ),
    )

    pressure_state = _safe_text(
        mt5_context.get(
            "pressure_state"
        ),
    )

    imbalance = _safe_float(
        window_5s.get(
            "directional_imbalance"
        )
    )

    mid_move = _safe_float(
        window_5s.get(
            "mid_move"
        )
    )

    acceleration = _safe_float(
        mt5_context.get(
            "quote_activity_acceleration_ratio"
        )
    )

    observed_span = _safe_float(
        window_5s.get(
            "observed_span_seconds"
        )
    )

    try:
        sample_count = int(
            window_5s.get(
                "sample_count"
            )
            or 0
        )
    except Exception:
        sample_count = 0

    direction = None

    if (
        pressure_state
        == "BUY_PRESSURE_PROXY"
    ):
        direction = "BUY"

    elif (
        pressure_state
        == "SELL_PRESSURE_PROXY"
    ):
        direction = "SELL"

    result.update(
        {
            "direction": direction,
            "source_coverage": (
                context.get(
                    "source_coverage"
                )
            ),
            "sample_count_5s": (
                sample_count
            ),
            "observed_span_seconds_5s": (
                observed_span
            ),
            "directional_imbalance_5s": (
                imbalance
            ),
            "mid_move_5s": (
                mid_move
            ),
            "activity_acceleration_ratio": (
                acceleration
            ),
        }
    )

    high_impact = bool(
        activity_state
        == "ACCELERATING_QUOTE_ACTIVITY"
        and direction
        in {
            "BUY",
            "SELL",
        }
        and sample_count
        >= HIGH_IMPACT_MIN_5S_SAMPLES
        and observed_span
        is not None
        and observed_span
        >= HIGH_IMPACT_MIN_OBSERVED_SPAN_SECONDS
        and imbalance
        is not None
        and abs(
            imbalance
        )
        >= HIGH_IMPACT_MIN_DIRECTIONAL_IMBALANCE
    )

    if high_impact:
        result.update(
            {
                "severity": "HIGH_IMPACT",
                "state": (
                    "HIGH_IMPACT_PARTICIPATION_PROXY"
                ),
                "reason": (
                    "accelerating_quote_activity_"
                    "with_strong_directional_"
                    "imbalance"
                ),
                "should_notify_candidate": True,
            }
        )

        return result

    if (
        activity_state
        == "ACCELERATING_QUOTE_ACTIVITY"
    ):
        result.update(
            {
                "severity": "STRONG",
                "state": (
                    "ACCELERATING_ACTIVITY_"
                    "BELOW_HIGH_IMPACT_THRESHOLD"
                ),
                "reason": (
                    "accelerating_activity_without_"
                    "full_high_impact_confirmation"
                ),
            }
        )

    elif (
        activity_state
        == "ELEVATED_QUOTE_ACTIVITY"
    ):
        result.update(
            {
                "severity": "WATCH",
                "state": (
                    "ELEVATED_ACTIVITY"
                ),
                "reason": (
                    "elevated_quote_activity"
                ),
            }
        )

    return result



def build_market_participation_statistics_fields(
    context: dict | None,
) -> dict[str, Any]:
    """
    Convert a market-participation snapshot into
    flat analytics fields for setup-outcome research.

    Research only. These fields have no authority over
    score, RR, risk, confirmation or execution.
    """

    fields = {
        "participation_schema_version": SCHEMA_VERSION,
        "participation_captured_at": None,
        "participation_source_coverage": None,
        "participation_combined_state": None,
        "participation_signal_relation": None,

        "participation_mt5_available": False,
        "participation_mt5_activity_state": None,
        "participation_mt5_pressure_state": None,
        "participation_mt5_current_spread": None,

        "participation_5s_sample_count": None,
        "participation_5s_observed_span_seconds": None,
        "participation_5s_directional_imbalance": None,
        "participation_5s_mid_move": None,
        "participation_activity_acceleration_ratio": None,

        "participation_high_impact_severity": None,
        "participation_high_impact_state": None,
        "participation_direction_proxy": None,

        "participation_rithmic_available": False,
        "participation_rithmic_status": None,
        "participation_rithmic_data_quality": None,
        "participation_rithmic_aggression_state": None,
        "participation_rithmic_dom_state": None,

        "participation_rithmic_bid_volume": None,
        "participation_rithmic_ask_volume": None,
        "participation_rithmic_delta": None,
        "participation_rithmic_cumulative_delta": None,
        "participation_rithmic_footprint_imbalance": None,
        "participation_rithmic_dom_bid_depth": None,
        "participation_rithmic_dom_ask_depth": None,
        "participation_rithmic_dom_depth_imbalance": None,
        "participation_rithmic_volume_profile_poc": None,
    }

    if not isinstance(
        context,
        dict,
    ):
        return fields

    mt5_context = (
        context.get("mt5")
        if isinstance(
            context.get("mt5"),
            dict,
        )
        else {}
    )

    windows = (
        mt5_context.get("windows")
        if isinstance(
            mt5_context.get("windows"),
            dict,
        )
        else {}
    )

    window_5s = (
        windows.get("5s")
        if isinstance(
            windows.get("5s"),
            dict,
        )
        else {}
    )

    rithmic = (
        context.get("rithmic")
        if isinstance(
            context.get("rithmic"),
            dict,
        )
        else {}
    )

    rithmic_metrics = (
        rithmic.get("metrics")
        if isinstance(
            rithmic.get("metrics"),
            dict,
        )
        else {}
    )

    alert = (
        classify_market_participation_alert(
            context
        )
    )

    sample_count = None

    try:
        raw_sample_count = (
            window_5s.get(
                "sample_count"
            )
        )

        if raw_sample_count is not None:
            sample_count = int(
                raw_sample_count
            )
    except Exception:
        sample_count = None

    rithmic_quality = (
        rithmic.get(
            "data_quality"
        )
    )

    if isinstance(
        rithmic_quality,
        (
            dict,
            list,
            tuple,
            set,
        ),
    ):
        try:
            rithmic_quality = json.dumps(
                _json_safe(
                    rithmic_quality
                ),
                sort_keys=True,
                separators=(",", ":"),
            )
        except Exception:
            rithmic_quality = str(
                rithmic_quality
            )

    fields.update(
        {
            "participation_schema_version": (
                context.get(
                    "schema_version"
                )
                or SCHEMA_VERSION
            ),
            "participation_captured_at": (
                context.get(
                    "observed_at"
                )
            ),
            "participation_source_coverage": (
                context.get(
                    "source_coverage"
                )
            ),
            "participation_combined_state": (
                context.get(
                    "combined_state"
                )
            ),
            "participation_signal_relation": (
                context.get(
                    "signal_relation"
                )
            ),

            "participation_mt5_available": (
                bool(
                    mt5_context.get(
                        "available"
                    )
                )
            ),
            "participation_mt5_activity_state": (
                mt5_context.get(
                    "activity_state"
                )
            ),
            "participation_mt5_pressure_state": (
                mt5_context.get(
                    "pressure_state"
                )
            ),
            "participation_mt5_current_spread": (
                _safe_float(
                    mt5_context.get(
                        "current_spread"
                    )
                )
            ),

            "participation_5s_sample_count": (
                sample_count
            ),
            "participation_5s_observed_span_seconds": (
                _safe_float(
                    window_5s.get(
                        "observed_span_seconds"
                    )
                )
            ),
            "participation_5s_directional_imbalance": (
                _safe_float(
                    window_5s.get(
                        "directional_imbalance"
                    )
                )
            ),
            "participation_5s_mid_move": (
                _safe_float(
                    window_5s.get(
                        "mid_move"
                    )
                )
            ),
            "participation_activity_acceleration_ratio": (
                _safe_float(
                    mt5_context.get(
                        "quote_activity_acceleration_ratio"
                    )
                )
            ),

            "participation_high_impact_severity": (
                alert.get(
                    "severity"
                )
            ),
            "participation_high_impact_state": (
                alert.get(
                    "state"
                )
            ),
            "participation_direction_proxy": (
                alert.get(
                    "direction"
                )
            ),

            "participation_rithmic_available": (
                bool(
                    rithmic.get(
                        "available"
                    )
                )
            ),
            "participation_rithmic_status": (
                rithmic.get(
                    "status"
                )
            ),
            "participation_rithmic_data_quality": (
                rithmic_quality
            ),
            "participation_rithmic_aggression_state": (
                rithmic.get(
                    "aggression_state"
                )
            ),
            "participation_rithmic_dom_state": (
                rithmic.get(
                    "dom_state"
                )
            ),

            "participation_rithmic_bid_volume": (
                _safe_float(
                    rithmic_metrics.get(
                        "bid_volume"
                    )
                )
            ),
            "participation_rithmic_ask_volume": (
                _safe_float(
                    rithmic_metrics.get(
                        "ask_volume"
                    )
                )
            ),
            "participation_rithmic_delta": (
                _safe_float(
                    rithmic_metrics.get(
                        "delta"
                    )
                )
            ),
            "participation_rithmic_cumulative_delta": (
                _safe_float(
                    rithmic_metrics.get(
                        "cumulative_delta"
                    )
                )
            ),
            "participation_rithmic_footprint_imbalance": (
                _safe_float(
                    rithmic_metrics.get(
                        "footprint_imbalance"
                    )
                )
            ),
            "participation_rithmic_dom_bid_depth": (
                _safe_float(
                    rithmic_metrics.get(
                        "dom_bid_depth"
                    )
                )
            ),
            "participation_rithmic_dom_ask_depth": (
                _safe_float(
                    rithmic_metrics.get(
                        "dom_ask_depth"
                    )
                )
            ),
            "participation_rithmic_dom_depth_imbalance": (
                _safe_float(
                    rithmic_metrics.get(
                        "dom_depth_imbalance"
                    )
                )
            ),
            "participation_rithmic_volume_profile_poc": (
                _safe_float(
                    rithmic_metrics.get(
                        "volume_profile_poc"
                    )
                )
            ),
        }
    )

    return fields


def claim_market_participation_high_impact_alert(
    context: dict | None,
    *,
    now_epoch: Optional[float] = None,
    cooldown_seconds: float = (
        DEFAULT_HIGH_IMPACT_ALERT_COOLDOWN_SECONDS
    ),
) -> dict[str, Any]:
    """
    Deduplicate same-symbol/same-direction Telegram
    alerts. Notification state only.
    """

    alert = (
        classify_market_participation_alert(
            context
        )
    )

    alert = dict(
        alert
    )

    alert[
        "should_notify"
    ] = False

    alert[
        "notification_reason"
    ] = (
        "classification_not_high_impact"
    )

    if not bool(
        alert.get(
            "should_notify_candidate"
        )
    ):
        return alert

    now_epoch = float(
        now_epoch
        if now_epoch is not None
        else time.time()
    )

    symbol = _safe_text(
        (
            context
            or {}
        ).get(
            "symbol"
        ),
        "UNKNOWN",
    ).upper()

    direction = _safe_text(
        alert.get(
            "direction"
        ),
        "UNKNOWN",
    ).upper()

    fingerprint = (
        f"{symbol}|{direction}"
    )

    cooldown_seconds = max(
        0.0,
        float(
            cooldown_seconds
        ),
    )

    with _HIGH_IMPACT_ALERT_LOCK:
        last_epoch = _safe_float(
            _LAST_HIGH_IMPACT_ALERT.get(
                fingerprint
            )
        )

        if (
            last_epoch is not None
            and (
                now_epoch
                - last_epoch
            )
            < cooldown_seconds
        ):
            alert[
                "notification_reason"
            ] = (
                "same_direction_cooldown_active"
            )

            alert[
                "cooldown_remaining_seconds"
            ] = round(
                max(
                    0.0,
                    cooldown_seconds
                    - (
                        now_epoch
                        - last_epoch
                    ),
                ),
                3,
            )

            return alert

        _LAST_HIGH_IMPACT_ALERT[
            fingerprint
        ] = now_epoch

    alert[
        "should_notify"
    ] = True

    alert[
        "notification_reason"
    ] = "high_impact_alert_claimed"

    alert[
        "cooldown_seconds"
    ] = cooldown_seconds

    return alert


def format_market_participation_high_impact_alert(
    context: dict | None,
    alert: dict | None = None,
) -> str:
    alert = (
        alert
        if isinstance(
            alert,
            dict,
        )
        else classify_market_participation_alert(
            context
        )
    )

    if (
        alert.get(
            "severity"
        )
        != "HIGH_IMPACT"
    ):
        return ""

    context = (
        context
        if isinstance(
            context,
            dict,
        )
        else {}
    )

    symbol = _safe_text(
        context.get(
            "symbol"
        ),
        "UNKNOWN",
    )

    source = _safe_text(
        context.get(
            "source_coverage"
        ),
        "MT5_ONLY",
    )

    source_label = (
        "MT5 + RITHMIC"
        if source
        == "MT5_PLUS_RITHMIC"
        else "MT5 PROXY"
    )

    return (
        "🚨 HIGH-IMPACT MARKET PARTICIPATION\n"
        f"Symbol: {symbol}\n"
        f"Source: {source_label}\n"
        f"Direction Proxy: "
        f"{alert.get('direction') or 'UNRESOLVED'}\n"
        "Activity: ACCELERATING\n"
        f"5s Imbalance: "
        f"{_format_participation_value(alert.get('directional_imbalance_5s'), digits=2)}\n"
        f"5s Move: "
        f"{_format_participation_value(alert.get('mid_move_5s'), digits=3)}\n"
        f"Activity Acceleration: "
        f"{_format_participation_value(alert.get('activity_acceleration_ratio'), digits=2)}\n\n"
        "⚠️ Abnormal short-term participation "
        "conditions detected.\n"
        "This does NOT identify institutions and "
        "does NOT guarantee future price direction.\n"
        "Action: do not chase; wait for structure "
        "and normal confirmation."
    )


def build_market_participation_observation(
    *,
    context: dict,
    capture_phase: str,
    event: str,
    strategy: Optional[str],
    setup_id: Optional[str],
    signal: Optional[str],
    entry_model: Optional[str] = None,
    session: Optional[str] = None,
    market_condition: Optional[str] = None,
    trade_plan: Optional[dict] = None,
) -> Dict[str, Any]:
    trade_plan = trade_plan if isinstance(trade_plan, dict) else {}

    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "record_type": "MARKET_PARTICIPATION_OBSERVATION",
        "capture_phase": _safe_text(capture_phase, "UNKNOWN").upper(),
        "event": _safe_text(event, "UNKNOWN").upper(),
        "strategy": _safe_text(strategy, "UNKNOWN").upper(),
        "setup_id": _safe_text(setup_id),
        "signal": _safe_text(signal, "UNKNOWN").upper(),
        "entry_model": _safe_text(entry_model, "UNKNOWN").upper(),
        "session": _safe_text(session, "UNKNOWN").upper(),
        "market_condition": _safe_text(market_condition, "UNKNOWN").upper(),
        "entry": _safe_float(trade_plan.get("entry_price")),
        "sl": _safe_float(trade_plan.get("stop_loss")),
        "tp": _safe_float(trade_plan.get("take_profit")),
        "lot": _safe_float(trade_plan.get("lot", trade_plan.get("volume"))),
        "participation_context": _json_safe(context),
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
    }


def log_market_participation_observation(
    observation: dict,
    *,
    file_path: Optional[str | Path] = None,
) -> bool:
    if not isinstance(observation, dict):
        return False

    try:
        if file_path is not None:
            path = Path(file_path)
        else:
            from src.account_context import get_account_file
            path = Path(get_account_file(OBSERVATION_FILENAME))
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    _json_safe(observation),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

        logger.info(
            "[MARKET PARTICIPATION] saved | "
            f"phase={observation.get('capture_phase')} "
            f"setup_id={observation.get('setup_id')} "
            f"strategy={observation.get('strategy')}"
        )
        return True
    except Exception as exc:
        logger.warning(
            "[MARKET PARTICIPATION] persistence failed open: "
            f"{exc}"
        )
        return False


def _reset_market_participation_state_for_tests() -> None:
    global _LAST_TICK_KEY

    with _TICK_LOCK:
        _TICK_TAPE.clear()
        _LAST_TICK_KEY = None

    with _RITHMIC_LOCK:
        _RITHMIC_CACHE.clear()

    with _HIGH_IMPACT_ALERT_LOCK:
        _LAST_HIGH_IMPACT_ALERT.clear()
