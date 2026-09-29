from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


STRATEGY_NAME = "INTRABAR_STEP_TRAIL"


@dataclass(frozen=True)
class StepTrailDetectorPolicy:
    window_seconds: float = 4.0
    min_samples: int = 10
    min_span_seconds: float = 2.0
    max_spread_price: float = 0.20
    min_impulse: float = 0.65
    min_pullback: float = 0.15
    max_pullback: float = 0.45
    min_resume: float = 0.20
    max_peak_distance: float = 0.10
    min_any_signal_gap_seconds: float = 8.0
    same_direction_rearm_seconds: float = 12.0


DEFAULT_POLICY = StepTrailDetectorPolicy()
_TAPE: deque[dict[str, float]] = deque(maxlen=256)
_LAST_SIGNAL_TS: float | None = None
_LAST_DIRECTION: str | None = None


def reset_intrabar_step_trail_detector() -> None:
    global _LAST_SIGNAL_TS, _LAST_DIRECTION
    _TAPE.clear()
    _LAST_SIGNAL_TS = None
    _LAST_DIRECTION = None


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _tick_ts(tick: Any) -> float | None:
    time_msc = _safe_float(getattr(tick, "time_msc", None))
    if time_msc is not None and time_msc > 0:
        return time_msc / 1000.0
    ts = _safe_float(getattr(tick, "time", None))
    return ts if ts is not None and ts > 0 else None


def _sample_from_tick(tick: Any) -> dict[str, float] | None:
    bid = _safe_float(getattr(tick, "bid", None))
    ask = _safe_float(getattr(tick, "ask", None))
    ts = _tick_ts(tick)
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


def _trim_tape(now_ts: float, window_seconds: float) -> None:
    cutoff = now_ts - max(0.5, float(window_seconds))
    while _TAPE and _TAPE[0]["ts"] < cutoff:
        _TAPE.popleft()


def _buy_pattern(samples, policy):
    mids = [x["mid"] for x in samples]
    if len(mids) < policy.min_samples:
        return None

    search_end = max(3, len(mids) - 2)
    peak_idx = max(range(search_end), key=lambda i: mids[i])
    if peak_idx < 2 or peak_idx >= len(mids) - 2:
        return None

    pre_low = min(mids[: peak_idx + 1])
    peak = mids[peak_idx]
    post = mids[peak_idx + 1 :]
    trough = min(post)
    last = mids[-1]

    impulse = peak - pre_low
    pullback = peak - trough
    resume = last - trough
    peak_distance = peak - last

    if impulse < policy.min_impulse:
        return None
    if pullback < policy.min_pullback or pullback > policy.max_pullback:
        return None
    if resume < policy.min_resume:
        return None
    if peak_distance < -1e-9 or peak_distance > policy.max_peak_distance:
        return None

    return {
        "signal": "BUY",
        "impulse": impulse,
        "pullback": pullback,
        "resume": resume,
        "extreme": peak,
        "retrace_extreme": trough,
        "quality": impulse + resume - abs(pullback - 0.30),
    }


def _sell_pattern(samples, policy):
    mids = [x["mid"] for x in samples]
    if len(mids) < policy.min_samples:
        return None

    search_end = max(3, len(mids) - 2)
    trough_idx = min(range(search_end), key=lambda i: mids[i])
    if trough_idx < 2 or trough_idx >= len(mids) - 2:
        return None

    pre_high = max(mids[: trough_idx + 1])
    trough = mids[trough_idx]
    post = mids[trough_idx + 1 :]
    peak = max(post)
    last = mids[-1]

    impulse = pre_high - trough
    pullback = peak - trough
    resume = peak - last
    trough_distance = last - trough

    if impulse < policy.min_impulse:
        return None
    if pullback < policy.min_pullback or pullback > policy.max_pullback:
        return None
    if resume < policy.min_resume:
        return None
    if trough_distance < -1e-9 or trough_distance > policy.max_peak_distance:
        return None

    return {
        "signal": "SELL",
        "impulse": impulse,
        "pullback": pullback,
        "resume": resume,
        "extreme": trough,
        "retrace_extreme": peak,
        "quality": impulse + resume - abs(pullback - 0.30),
    }


def detect_step_trail_pattern(
    samples: list[dict[str, float]],
    *,
    policy: StepTrailDetectorPolicy = DEFAULT_POLICY,
):
    if len(samples) < policy.min_samples:
        return None

    span = float(samples[-1]["ts"] - samples[0]["ts"])
    if span < policy.min_span_seconds:
        return None
    if float(samples[-1]["spread"]) > policy.max_spread_price:
        return None

    buy = _buy_pattern(samples, policy)
    sell = _sell_pattern(samples, policy)

    if buy is None and sell is None:
        return None
    if buy is None:
        chosen = sell
    elif sell is None:
        chosen = buy
    else:
        chosen = buy if buy["quality"] >= sell["quality"] else sell

    result = dict(chosen)
    result.update(
        {
            "strategy": STRATEGY_NAME,
            "span_seconds": round(span, 4),
            "sample_count": len(samples),
            "spread": round(float(samples[-1]["spread"]), 6),
            "entry_reference": round(
                float(
                    samples[-1]["ask"]
                    if chosen["signal"] == "BUY"
                    else samples[-1]["bid"]
                ),
                2,
            ),
        }
    )
    return result


def observe_intrabar_step_trail_tick(
    tick: Any,
    *,
    policy: StepTrailDetectorPolicy = DEFAULT_POLICY,
):
    global _LAST_SIGNAL_TS, _LAST_DIRECTION

    sample = _sample_from_tick(tick)
    if sample is None:
        return None

    _TAPE.append(sample)
    _trim_tape(sample["ts"], policy.window_seconds)

    candidate = detect_step_trail_pattern(list(_TAPE), policy=policy)
    if candidate is None:
        return None

    now_ts = sample["ts"]
    if _LAST_SIGNAL_TS is not None:
        elapsed = now_ts - _LAST_SIGNAL_TS
        if elapsed < policy.min_any_signal_gap_seconds:
            return None
        if (
            candidate["signal"] == _LAST_DIRECTION
            and elapsed < policy.same_direction_rearm_seconds
        ):
            return None

    _LAST_SIGNAL_TS = now_ts
    _LAST_DIRECTION = candidate["signal"]

    candidate["detected_ts"] = now_ts
    candidate["setup_id"] = (
        f"IST-{candidate['signal']}-{int(round(now_ts * 1000.0))}"
    )
    candidate["entry_model"] = "INTRABAR_IMPULSE_PULLBACK_RESUME"
    candidate["reason"] = (
        f"Intrabar step-trail {candidate['signal']} | "
        f"impulse={round(candidate['impulse'], 3)} "
        f"pullback={round(candidate['pullback'], 3)} "
        f"resume={round(candidate['resume'], 3)}"
    )

    try:
        from src.intrabar_optimization_recorder import (
            register_intrabar_candidate_snapshot,
        )
        register_intrabar_candidate_snapshot(candidate)
    except Exception:
        pass

    return candidate


def get_step_trail_failure_context(
    signal: str,
    *,
    lookback_seconds: float = 1.25,
    opposite_impulse_distance: float = 0.35,
    momentum_failure_distance: float = 0.20,
):
    side = str(signal or "").upper()
    if len(_TAPE) < 3:
        return {
            "opposite_impulse": False,
            "momentum_failed": False,
            "recent_move": 0.0,
        }

    now_ts = _TAPE[-1]["ts"]
    recent = [
        item
        for item in _TAPE
        if item["ts"] >= now_ts - max(0.25, float(lookback_seconds))
    ]
    if len(recent) < 3:
        return {
            "opposite_impulse": False,
            "momentum_failed": False,
            "recent_move": 0.0,
        }

    recent_move = float(recent[-1]["mid"] - recent[0]["mid"])

    if side == "BUY":
        opposite_distance = max(0.0, -recent_move)
    elif side == "SELL":
        opposite_distance = max(0.0, recent_move)
    else:
        opposite_distance = 0.0

    return {
        "opposite_impulse": opposite_distance >= opposite_impulse_distance,
        "momentum_failed": opposite_distance >= momentum_failure_distance,
        "recent_move": round(recent_move, 6),
    }
