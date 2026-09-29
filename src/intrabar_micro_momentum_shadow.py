from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import time
from typing import Any


STRATEGY = "INTRABAR_MICRO_MOMENTUM"
ENTRY_MODEL = "TICK_VELOCITY_ACCELERATION_PERSISTENCE"
MODE = "SHADOW_ONLY"
DECISION_IMPACT = "NONE"

_TICKS = deque(maxlen=400)
_LAST_RAW_TICK_KEY = None
_LAST_EMIT_AT = 0.0
_LAST_EMIT_BY_DIRECTION = {"BUY": 0.0, "SELL": 0.0}
_LAST_EMIT_PRICE_BY_DIRECTION = {"BUY": None, "SELL": None}
_APPROVED_DAILY_LADDER = None


@dataclass(frozen=True)
class MomentumConfig:
    window_seconds: float = 5.0
    min_samples: int = 6
    min_span_seconds: float = 2.0
    min_move_price: float = 0.30
    min_velocity_price_per_sec: float = 0.06
    min_persistence: float = 0.67
    min_acceleration_ratio: float = 1.00
    max_spread_price: float = 0.20
    breakout_buffer_price: float = 0.01
    min_score: int = 88
    min_seconds_between_any: float = 3.0
    same_direction_rearm_seconds: float = 10.0
    same_direction_rearm_retrace_price: float = 0.20


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        value = float(value)
        return value if math.isfinite(value) else None
    except Exception:
        return None


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _setting(name: str, default: Any) -> Any:
    try:
        from config import settings
        return getattr(settings, name, default)
    except Exception:
        return default


def config_from_settings() -> MomentumConfig:
    return MomentumConfig(
        window_seconds=float(_setting("MICRO_MOMENTUM_SHADOW_WINDOW_SECONDS", 5.0)),
        min_samples=_safe_int(_setting("MICRO_MOMENTUM_SHADOW_MIN_SAMPLES", 6), 6),
        min_span_seconds=float(_setting("MICRO_MOMENTUM_SHADOW_MIN_SPAN_SECONDS", 2.0)),
        min_move_price=float(_setting("MICRO_MOMENTUM_SHADOW_MIN_MOVE_PRICE", 0.30)),
        min_velocity_price_per_sec=float(
            _setting("MICRO_MOMENTUM_SHADOW_MIN_VELOCITY_PRICE_PER_SEC", 0.06)
        ),
        min_persistence=float(_setting("MICRO_MOMENTUM_SHADOW_MIN_PERSISTENCE", 0.67)),
        min_acceleration_ratio=float(
            _setting("MICRO_MOMENTUM_SHADOW_MIN_ACCELERATION_RATIO", 1.00)
        ),
        max_spread_price=float(_setting("MICRO_MOMENTUM_SHADOW_MAX_SPREAD_PRICE", 0.20)),
        breakout_buffer_price=float(
            _setting("MICRO_MOMENTUM_SHADOW_BREAKOUT_BUFFER_PRICE", 0.01)
        ),
        min_score=_safe_int(_setting("MICRO_MOMENTUM_SHADOW_MIN_SCORE", 88), 88),
        min_seconds_between_any=float(
            _setting("MICRO_MOMENTUM_SHADOW_MIN_SECONDS_BETWEEN_ANY", 3.0)
        ),
        same_direction_rearm_seconds=float(
            _setting("MICRO_MOMENTUM_SHADOW_SAME_DIRECTION_REARM_SECONDS", 10.0)
        ),
        same_direction_rearm_retrace_price=float(
            _setting("MICRO_MOMENTUM_SHADOW_SAME_DIRECTION_REARM_RETRACE_PRICE", 0.20)
        ),
    )


def reset_shadow_state() -> None:
    global _LAST_RAW_TICK_KEY, _LAST_EMIT_AT, _APPROVED_DAILY_LADDER
    _TICKS.clear()
    _LAST_RAW_TICK_KEY = None
    _LAST_EMIT_AT = 0.0
    _LAST_EMIT_BY_DIRECTION["BUY"] = 0.0
    _LAST_EMIT_BY_DIRECTION["SELL"] = 0.0
    _LAST_EMIT_PRICE_BY_DIRECTION["BUY"] = None
    _LAST_EMIT_PRICE_BY_DIRECTION["SELL"] = None
    _APPROVED_DAILY_LADDER = None


def update_approved_daily_ladder_context(approved_ladder: Any) -> None:
    """
    Publish the already-approved DLLB ladder for momentum LOCATION CONTEXT only.

    This function never creates or validates ladder authority. The authoritative
    DLLB provider remains unchanged. Momentum may observe the published pivot /
    upper / lower values but can never grant execution authority from them.
    """
    global _APPROVED_DAILY_LADDER

    if approved_ladder is None:
        _APPROVED_DAILY_LADDER = None
        return

    def values(name: str) -> tuple[float, ...]:
        raw = getattr(approved_ladder, name, None)
        if raw is None and isinstance(approved_ladder, dict):
            raw = approved_ladder.get(name)
        result = []
        for value in raw or ():
            number = _safe_float(value)
            if number is not None:
                result.append(number)
        return tuple(result)

    pivot = getattr(approved_ladder, "pivot", None)
    if pivot is None and isinstance(approved_ladder, dict):
        pivot = approved_ladder.get("pivot")
    pivot = _safe_float(pivot)

    source = getattr(approved_ladder, "source", None)
    if source is None and isinstance(approved_ladder, dict):
        source = approved_ladder.get("source")

    broker_date = getattr(approved_ladder, "broker_date", None)
    if broker_date is None and isinstance(approved_ladder, dict):
        broker_date = approved_ladder.get("broker_date")

    if pivot is None:
        _APPROVED_DAILY_LADDER = None
        return

    _APPROVED_DAILY_LADDER = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "pivot": pivot,
        "upper": values("upper"),
        "lower": values("lower"),
        "source": str(source or "UNKNOWN"),
        "broker_date": str(broker_date or ""),
        "execution_authority": False,
        "role": "MOMENTUM_CONTEXT_ONLY",
    }


def _tick_epoch_seconds(tick: Any) -> float | None:
    time_msc = _safe_float(getattr(tick, "time_msc", None))
    if time_msc is not None and time_msc > 0:
        return time_msc / 1000.0

    value = _safe_float(getattr(tick, "time", None))
    if value is not None and value > 0:
        return value

    return None


def _normalize_tick(tick: Any) -> dict[str, float] | None:
    bid = _safe_float(getattr(tick, "bid", None))
    ask = _safe_float(getattr(tick, "ask", None))
    ts = _tick_epoch_seconds(tick)

    if bid is None or ask is None or ts is None:
        return None
    if bid <= 0 or ask <= 0 or ask < bid:
        return None

    return {
        "ts": ts,
        "bid": bid,
        "ask": ask,
        "mid": (bid + ask) / 2.0,
        "spread": ask - bid,
    }


def ingest_tick(tick: Any) -> bool:
    global _LAST_RAW_TICK_KEY

    sample = _normalize_tick(tick)
    if sample is None:
        return False

    raw_key = (
        round(sample["ts"], 3),
        round(sample["bid"], 6),
        round(sample["ask"], 6),
    )
    if raw_key == _LAST_RAW_TICK_KEY:
        return False

    _LAST_RAW_TICK_KEY = raw_key
    _TICKS.append(sample)

    cutoff = sample["ts"] - 30.0
    while _TICKS and _TICKS[0]["ts"] < cutoff:
        _TICKS.popleft()

    return True


def _window(samples: list[dict[str, float]], seconds: float) -> list[dict[str, float]]:
    if not samples:
        return []
    cutoff = samples[-1]["ts"] - seconds
    return [row for row in samples if row["ts"] >= cutoff]


def _signed_velocity(rows: list[dict[str, float]]) -> float | None:
    if len(rows) < 2:
        return None
    span = rows[-1]["ts"] - rows[0]["ts"]
    if span <= 0:
        return None
    return (rows[-1]["mid"] - rows[0]["mid"]) / span


def _directional_acceleration_ratio(
    rows: list[dict[str, float]],
    signal: str,
    total_window_seconds: float,
) -> float:
    if len(rows) < 4:
        return 1.0

    end_ts = rows[-1]["ts"]
    half = max(0.5, total_window_seconds / 2.0)
    recent = [r for r in rows if r["ts"] >= end_ts - half]
    prior = [
        r
        for r in rows
        if end_ts - (2.0 * half) <= r["ts"] < end_ts - half
    ]

    recent_v = _signed_velocity(recent)
    prior_v = _signed_velocity(prior)

    sign = 1.0 if signal == "BUY" else -1.0
    recent_speed = max(0.0, (recent_v or 0.0) * sign)
    prior_speed = max(0.0, (prior_v or 0.0) * sign)

    if recent_speed <= 0:
        return 0.0
    if prior_speed <= 0.005:
        return 5.0

    return min(5.0, recent_speed / prior_speed)


def evaluate_momentum_samples(
    samples: list[dict[str, float]],
    config: MomentumConfig,
) -> dict[str, Any] | None:
    rows = _window(samples, config.window_seconds)

    if len(rows) < config.min_samples:
        return None

    span = rows[-1]["ts"] - rows[0]["ts"]
    if span < config.min_span_seconds:
        return None

    spread = rows[-1]["spread"]
    if spread > config.max_spread_price:
        return None

    net_move = rows[-1]["mid"] - rows[0]["mid"]
    abs_move = abs(net_move)
    if abs_move < config.min_move_price:
        return None

    signal = "BUY" if net_move > 0 else "SELL"
    signed_velocity = net_move / span
    directional_velocity = abs(signed_velocity)

    if directional_velocity < config.min_velocity_price_per_sec:
        return None

    steps = [
        rows[index]["mid"] - rows[index - 1]["mid"]
        for index in range(1, len(rows))
    ]
    nonzero = [step for step in steps if abs(step) > 1e-9]
    if not nonzero:
        return None

    if signal == "BUY":
        directional_steps = sum(step > 0 for step in nonzero)
        prior_extreme = max(row["mid"] for row in rows[:-1])
        breakout = (
            rows[-1]["mid"]
            >= prior_extreme + config.breakout_buffer_price - 1e-9
        )
    else:
        directional_steps = sum(step < 0 for step in nonzero)
        prior_extreme = min(row["mid"] for row in rows[:-1])
        breakout = (
            rows[-1]["mid"]
            <= prior_extreme - config.breakout_buffer_price + 1e-9
        )

    persistence = directional_steps / len(nonzero)
    if persistence < config.min_persistence or not breakout:
        return None

    acceleration = _directional_acceleration_ratio(
        rows,
        signal,
        config.window_seconds,
    )
    if acceleration < config.min_acceleration_ratio:
        return None

    score = 80
    if abs_move >= 0.40:
        score += 5
    if abs_move >= 0.60:
        score += 5
    if persistence >= 0.75:
        score += 4
    if persistence >= 0.85:
        score += 3
    if directional_velocity >= 0.10:
        score += 4
    if acceleration >= 1.50:
        score += 3
    if spread <= 0.10:
        score += 2
    score = min(100, score)

    if score < config.min_score:
        return None

    if score >= 97 or abs_move >= 0.80:
        strength = "EXPLOSIVE"
        sl_distance = 0.50
        tp_distance = 2.00
    elif score >= 93 or abs_move >= 0.50:
        strength = "NORMAL"
        sl_distance = 0.40
        tp_distance = 1.20
    else:
        strength = "WEAK_VALID"
        sl_distance = 0.30
        tp_distance = 0.60

    return {
        "signal": signal,
        "score": score,
        "strength": strength,
        "sample_count": len(rows),
        "span_seconds": round(span, 3),
        "net_move": round(net_move, 6),
        "absolute_move": round(abs_move, 6),
        "velocity_price_per_sec": round(directional_velocity, 6),
        "signed_velocity_price_per_sec": round(signed_velocity, 6),
        "persistence": round(persistence, 6),
        "acceleration_ratio": round(acceleration, 6),
        "spread": round(spread, 6),
        "micro_breakout": True,
        "sl_distance": sl_distance,
        "tp_distance": tp_distance,
        "observed_at_epoch": rows[-1]["ts"],
        "mid": rows[-1]["mid"],
        "bid": rows[-1]["bid"],
        "ask": rows[-1]["ask"],
    }


def build_daily_level_context(
    entry: float,
    signal: str,
    ladder: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ladder = ladder if ladder is not None else _APPROVED_DAILY_LADDER

    result = {
        "available": False,
        "source": None,
        "broker_date": None,
        "pivot": None,
        "pivot_side": "UNKNOWN",
        "pivot_direction_aligned": None,
        "nearest_level": None,
        "nearest_level_kind": None,
        "nearest_level_distance": None,
        "next_level_in_direction": None,
        "next_level_distance": None,
        "execution_authority": False,
        "role": "MOMENTUM_CONTEXT_ONLY",
    }

    if not isinstance(ladder, dict):
        return result

    pivot = _safe_float(ladder.get("pivot"))
    if pivot is None:
        return result

    uppers = [
        value
        for value in (_safe_float(v) for v in ladder.get("upper", ()))
        if value is not None
    ]
    lowers = [
        value
        for value in (_safe_float(v) for v in ladder.get("lower", ()))
        if value is not None
    ]

    levels = [(pivot, "PIVOT")]
    levels.extend((v, "UPPER") for v in uppers)
    levels.extend((v, "LOWER") for v in lowers)

    nearest_price, nearest_kind = min(
        levels,
        key=lambda item: abs(entry - item[0]),
    )

    pivot_side = "ABOVE" if entry > pivot else ("BELOW" if entry < pivot else "AT")
    aligned = (
        (signal == "BUY" and entry > pivot)
        or (signal == "SELL" and entry < pivot)
    )

    if signal == "BUY":
        candidates = sorted(value for value, _kind in levels if value > entry)
        next_level = candidates[0] if candidates else None
    else:
        candidates = sorted(
            (value for value, _kind in levels if value < entry),
            reverse=True,
        )
        next_level = candidates[0] if candidates else None

    result.update(
        {
            "available": True,
            "source": ladder.get("source"),
            "broker_date": ladder.get("broker_date"),
            "pivot": round(pivot, 2),
            "pivot_side": pivot_side,
            "pivot_direction_aligned": bool(aligned),
            "nearest_level": round(nearest_price, 2),
            "nearest_level_kind": nearest_kind,
            "nearest_level_distance": round(abs(entry - nearest_price), 4),
            "next_level_in_direction": (
                round(next_level, 2) if next_level is not None else None
            ),
            "next_level_distance": (
                round(abs(next_level - entry), 4)
                if next_level is not None
                else None
            ),
        }
    )
    return result


def _rearm_allowed(candidate: dict[str, Any], config: MomentumConfig) -> bool:
    now = float(candidate["observed_at_epoch"])
    signal = str(candidate["signal"])
    price = float(candidate["mid"])

    if _LAST_EMIT_AT and (now - _LAST_EMIT_AT) < config.min_seconds_between_any:
        return False

    previous_time = _LAST_EMIT_BY_DIRECTION.get(signal, 0.0) or 0.0
    if not previous_time:
        return True

    elapsed = now - previous_time
    if elapsed >= config.same_direction_rearm_seconds:
        return True

    previous_price = _LAST_EMIT_PRICE_BY_DIRECTION.get(signal)
    if previous_price is None:
        return False

    if signal == "BUY":
        retraced = price <= previous_price - config.same_direction_rearm_retrace_price
    else:
        retraced = price >= previous_price + config.same_direction_rearm_retrace_price

    return bool(retraced)


def _mark_emitted(candidate: dict[str, Any]) -> None:
    global _LAST_EMIT_AT
    now = float(candidate["observed_at_epoch"])
    signal = str(candidate["signal"])
    _LAST_EMIT_AT = now
    _LAST_EMIT_BY_DIRECTION[signal] = now
    _LAST_EMIT_PRICE_BY_DIRECTION[signal] = float(candidate["mid"])


def build_shadow_setup(
    candidate: dict[str, Any],
    *,
    session: str,
    market_condition: str,
) -> dict[str, Any]:
    signal = candidate["signal"]
    entry = candidate["ask"] if signal == "BUY" else candidate["bid"]
    sl_distance = float(candidate["sl_distance"])
    tp_distance = float(candidate["tp_distance"])

    if signal == "BUY":
        sl = entry - sl_distance
        tp = entry + tp_distance
    else:
        sl = entry + sl_distance
        tp = entry - tp_distance

    ts_ms = int(float(candidate["observed_at_epoch"]) * 1000)
    setup_id = f"IMM-{signal}-{ts_ms}"
    daily = build_daily_level_context(entry, signal)

    return {
        "setup_id": setup_id,
        "strategy": STRATEGY,
        "signal": signal,
        "entry_model": ENTRY_MODEL,
        "score": int(candidate["score"]),
        "session": session,
        "market_condition": market_condition,
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "tp": round(tp, 2),
        "reason": (
            f"Shadow micro momentum {signal} | strength={candidate['strength']} "
            f"move={candidate['absolute_move']:.2f} "
            f"vel={candidate['velocity_price_per_sec']:.3f}/s "
            f"persistence={candidate['persistence']:.2f} "
            f"accel={candidate['acceleration_ratio']:.2f}x "
            f"spread={candidate['spread']:.2f}"
        ),
        "extra": {
            "family": "MOMENTUM_FAMILY",
            "shadow_only": True,
            "execution_mode": MODE,
            "decision_impact": DECISION_IMPACT,
            "orders_sent": 0,
            "strength": candidate["strength"],
            "sample_count": candidate["sample_count"],
            "span_seconds": candidate["span_seconds"],
            "net_move": candidate["net_move"],
            "absolute_move": candidate["absolute_move"],
            "velocity_price_per_sec": candidate["velocity_price_per_sec"],
            "signed_velocity_price_per_sec": candidate[
                "signed_velocity_price_per_sec"
            ],
            "persistence": candidate["persistence"],
            "acceleration_ratio": candidate["acceleration_ratio"],
            "spread": candidate["spread"],
            "micro_breakout": candidate["micro_breakout"],
            "sl_distance": sl_distance,
            "tp_distance": tp_distance,
            "daily_level_context": daily,
            "runner_research_role": "LOW_MAE_MOMENTUM_RUNNER_SOURCE",
        },
    }



def build_live_signal_data_from_shadow(
    setup: dict[str, Any],
    tick: Any,
) -> dict[str, Any] | None:
    """
    Convert a qualified shadow impulse into a live candidate using a FRESH
    executable quote. Shadow entry is evidence only; live SL/TP are rebuilt
    from the same detected distance model around current ask/bid.
    """
    if not isinstance(setup, dict):
        return None

    signal = str(setup.get("signal") or "").upper()
    if signal not in {"BUY", "SELL"}:
        return None

    extra = setup.get("extra")
    if not isinstance(extra, dict):
        return None

    sl_distance = _safe_float(extra.get("sl_distance"))
    tp_distance = _safe_float(extra.get("tp_distance"))
    score = _safe_int(setup.get("score"), 0)

    if sl_distance is None or tp_distance is None:
        return None
    if sl_distance <= 0 or tp_distance <= 0:
        return None

    bid = _safe_float(getattr(tick, "bid", None))
    ask = _safe_float(getattr(tick, "ask", None))
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None

    entry = ask if signal == "BUY" else bid

    if signal == "BUY":
        sl = entry - sl_distance
        tp = entry + tp_distance
    else:
        sl = entry + sl_distance
        tp = entry - tp_distance

    live_setup_id = str(setup.get("setup_id") or "")
    if not live_setup_id:
        return None

    return {
        "setup_id": live_setup_id,
        "strategy": STRATEGY,
        "family": "MOMENTUM_FAMILY",
        "signal": signal,
        "entry_model": ENTRY_MODEL,
        "score": score,
        "session": setup.get("session"),
        "market_condition": setup.get("market_condition"),
        "entry_reference": round(entry, 2),
        "sl_reference": round(sl, 2),
        "tp_reference": round(tp, 2),
        "sl_model": "MICRO_MOMENTUM_FIXED_PRICE_DISTANCE",
        "target_model": "MICRO_MOMENTUM_ADAPTIVE_PRICE_DISTANCE",
        "execution_mode": "LIVE_INTRABAR_MICRO_MOMENTUM",
        "decision_impact": "LIVE_EXECUTION",
        "shadow_setup_id": live_setup_id,
        "strength": extra.get("strength"),
        "sl_distance": sl_distance,
        "tp_distance": tp_distance,
        "daily_level_context": extra.get("daily_level_context"),
        "reason": (
            f"Live micro momentum {signal} | "
            f"strength={extra.get('strength')} "
            f"score={score} fresh_entry={round(entry, 2)} "
            f"SL_distance={sl_distance:.2f} TP_distance={tp_distance:.2f}"
        ),
    }


def _resolve_runtime_context(df: Any, current_candle_time: Any) -> tuple[str, str]:
    session = "UNKNOWN"
    market_condition = "UNKNOWN"

    try:
        from src.session_engine import detect_session
        session = str(detect_session(current_candle_time) or "UNKNOWN")
    except Exception:
        pass

    try:
        from src.market_condition import detect_market_condition
        market_condition = str(detect_market_condition(df) or "UNKNOWN")
    except Exception:
        pass

    return session, market_condition



def detect_intrabar_micro_momentum_fast_tick(
    tick: Any,
) -> dict[str, Any] | None:
    """
    Fast-lane detector only.

    Ingests one fresh MT5 quote and returns a qualified impulse candidate.
    It does NOT fetch candles/account state, register outcomes, or execute.
    This keeps the 250ms lane lightweight until an actual impulse qualifies.
    """
    shadow_enabled = bool(
        _setting("ENABLE_INTRABAR_MICRO_MOMENTUM_SHADOW", True)
    )
    live_enabled = bool(
        _setting("ENABLE_INTRABAR_MICRO_MOMENTUM_LIVE", False)
    )

    if not (shadow_enabled or live_enabled):
        return None

    if not ingest_tick(tick):
        return None

    config = config_from_settings()
    candidate = evaluate_momentum_samples(list(_TICKS), config)
    if candidate is None:
        return None

    if not _rearm_allowed(candidate, config):
        return None

    return candidate


def finalize_intrabar_micro_momentum_candidate(
    *,
    symbol: str,
    candidate: dict[str, Any],
    df: Any,
    current_candle_time: Any,
) -> dict[str, Any] | None:
    """
    Materialize one already-qualified fast-lane candidate.

    The candidate is consumed exactly once before any downstream live guard so
    a single impulse cannot spam repeated order/block attempts every 250ms.
    Shadow outcome registration remains best-effort and cannot block live mode.
    """
    if not isinstance(candidate, dict):
        return None

    session, market_condition = _resolve_runtime_context(
        df,
        current_candle_time,
    )
    setup = build_shadow_setup(
        candidate,
        session=session,
        market_condition=market_condition,
    )

    try:
        from src.intrabar_optimization_recorder import (
            register_intrabar_candidate_snapshot,
        )
        register_intrabar_candidate_snapshot(setup)
    except Exception:
        pass

    # Consume first: one qualified impulse -> at most one live handoff.
    _mark_emitted(candidate)

    if bool(_setting("ENABLE_INTRABAR_MICRO_MOMENTUM_SHADOW", True)):
        try:
            from src.setup_outcome_tracker import register_setup_outcome

            registered = register_setup_outcome(
                symbol=symbol,
                setup_id=setup["setup_id"],
                event="SETUP_DETECTED",
                strategy=setup["strategy"],
                signal=setup["signal"],
                entry_model=setup["entry_model"],
                score=setup["score"],
                session=setup["session"],
                market_condition=setup["market_condition"],
                entry=setup["entry"],
                sl=setup["sl"],
                tp=setup["tp"],
                reason=setup["reason"],
                extra=setup["extra"],
            )

            if not registered:
                try:
                    from src.logger import logger
                    logger.warning(
                        "[MICRO MOMENTUM FAST] "
                        f"shadow registration returned False | "
                        f"setup_id={setup['setup_id']}"
                    )
                except Exception:
                    pass
        except Exception as exc:
            try:
                from src.logger import logger
                logger.warning(
                    "[MICRO MOMENTUM FAST] "
                    "shadow registration failed open "
                    f"| setup_id={setup.get('setup_id')} error={exc}"
                )
            except Exception:
                pass

    try:
        from src.logger import logger
        daily = setup["extra"]["daily_level_context"]
        logger.info(
            "[MICRO MOMENTUM FAST QUALIFIED] "
            f"setup_id={setup['setup_id']} "
            f"signal={setup['signal']} "
            f"entry={setup['entry']} "
            f"sl={setup['sl']} "
            f"tp={setup['tp']} "
            f"strength={candidate['strength']} "
            f"score={candidate['score']} "
            f"move={candidate['absolute_move']} "
            f"velocity={candidate['velocity_price_per_sec']} "
            f"persistence={candidate['persistence']} "
            f"accel={candidate['acceleration_ratio']} "
            f"daily_available={daily.get('available')} "
            f"pivot_aligned={daily.get('pivot_direction_aligned')}"
        )
    except Exception:
        pass

    return setup


def observe_intrabar_micro_momentum_shadow(
    *,
    symbol: str,
    tick: Any,
    df: Any,
    current_candle_time: Any,
) -> dict[str, Any] | None:
    """
    Per-loop shadow observer.

    It NEVER sends an order, NEVER calls execute_trade, NEVER changes risk,
    and NEVER blocks another strategy. Qualified impulses are registered in
    the existing setup-outcome tracker so MAE/MFE/TP/SL and existing market-
    participation context can be studied with the rest of the bot.
    """
    if not bool(_setting("ENABLE_INTRABAR_MICRO_MOMENTUM_SHADOW", True)):
        return None

    appended = ingest_tick(tick)
    if not appended:
        return None

    config = config_from_settings()
    candidate = evaluate_momentum_samples(list(_TICKS), config)
    if candidate is None:
        return None

    if not _rearm_allowed(candidate, config):
        return None

    session, market_condition = _resolve_runtime_context(
        df,
        current_candle_time,
    )
    setup = build_shadow_setup(
        candidate,
        session=session,
        market_condition=market_condition,
    )

    try:
        from src.setup_outcome_tracker import register_setup_outcome
        registered = register_setup_outcome(
            symbol=symbol,
            setup_id=setup["setup_id"],
            event="SETUP_DETECTED",
            strategy=setup["strategy"],
            signal=setup["signal"],
            entry_model=setup["entry_model"],
            score=setup["score"],
            session=setup["session"],
            market_condition=setup["market_condition"],
            entry=setup["entry"],
            sl=setup["sl"],
            tp=setup["tp"],
            reason=setup["reason"],
            extra=setup["extra"],
        )
    except Exception as exc:
        try:
            from src.logger import logger
            logger.warning(
                "[MICRO MOMENTUM SHADOW] tracker registration failed open "
                f"| error={exc}"
            )
        except Exception:
            pass
        return None

    if not registered:
        return None

    _mark_emitted(candidate)

    try:
        from src.logger import logger
        daily = setup["extra"]["daily_level_context"]
        logger.info(
            "[MICRO MOMENTUM SHADOW] "
            f"setup_id={setup['setup_id']} signal={setup['signal']} "
            f"entry={setup['entry']} sl={setup['sl']} tp={setup['tp']} "
            f"strength={candidate['strength']} score={candidate['score']} "
            f"move={candidate['absolute_move']} "
            f"velocity={candidate['velocity_price_per_sec']} "
            f"persistence={candidate['persistence']} "
            f"accel={candidate['acceleration_ratio']} "
            f"daily_available={daily.get('available')} "
            f"pivot_aligned={daily.get('pivot_direction_aligned')} "
            "mode=SHADOW_ONLY orders_sent=0"
        )
    except Exception:
        pass

    return setup
