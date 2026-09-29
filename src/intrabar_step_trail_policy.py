from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Any


STRATEGY_NAME = "INTRABAR_STEP_TRAIL"


@dataclass(frozen=True)
class StepTrailPolicy:
    hard_stop_distance: float = 7.00
    activation_profit: float = 0.60
    first_lock_profit: float = 0.10
    trail_step: float = 0.50
    trail_gap: float = 0.50
    early_failure_grace_seconds: float = 2.00
    early_failure_min_adverse: float = 0.75


DEFAULT_POLICY = StepTrailPolicy()


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number != number:
        return None

    return number


def build_initial_stop(
    *,
    signal: str,
    entry_price: float,
    policy: StepTrailPolicy = DEFAULT_POLICY,
) -> float:
    side = str(signal or "").upper()
    entry = float(entry_price)

    if side == "BUY":
        return round(entry - policy.hard_stop_distance, 2)

    if side == "SELL":
        return round(entry + policy.hard_stop_distance, 2)

    raise ValueError(f"unsupported signal: {signal}")


def favorable_move(
    *,
    signal: str,
    entry_price: float,
    best_price: float,
) -> float:
    side = str(signal or "").upper()
    entry = float(entry_price)
    best = float(best_price)

    if side == "BUY":
        return max(0.0, best - entry)

    if side == "SELL":
        return max(0.0, entry - best)

    raise ValueError(f"unsupported signal: {signal}")


def adverse_move(
    *,
    signal: str,
    entry_price: float,
    current_price: float,
) -> float:
    side = str(signal or "").upper()
    entry = float(entry_price)
    current = float(current_price)

    if side == "BUY":
        return max(0.0, entry - current)

    if side == "SELL":
        return max(0.0, current - entry)

    raise ValueError(f"unsupported signal: {signal}")


def evaluate_profit_lock(
    *,
    signal: str,
    entry_price: float,
    best_price: float,
    current_stop: float | None,
    policy: StepTrailPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    side = str(signal or "").upper()
    entry = float(entry_price)
    best = float(best_price)
    current_sl = _safe_float(current_stop)

    mfe = favorable_move(
        signal=side,
        entry_price=entry,
        best_price=best,
    )

    result = {
        "strategy": STRATEGY_NAME,
        "signal": side,
        "entry_price": round(entry, 2),
        "best_price": round(best, 2),
        "mfe": round(mfe, 4),
        "activation_profit": policy.activation_profit,
        "trail_step": policy.trail_step,
        "trail_gap": policy.trail_gap,
        "current_stop": current_sl,
        "should_modify": False,
        "desired_stop": current_sl,
        "lock_profit": None,
        "stage": "PRE_ACTIVATION",
        "reason": "activation_not_reached",
    }

    if mfe + 1e-9 < policy.activation_profit:
        return result

    completed_steps = floor(
        (mfe - policy.activation_profit + 1e-9)
        / policy.trail_step
    )

    lock_profit = (
        policy.first_lock_profit
        + completed_steps * policy.trail_step
    )

    # The configured values intentionally keep the protective stop about
    # trail_gap behind the best favorable price at each discrete step.
    if side == "BUY":
        desired = entry + lock_profit
        if current_sl is not None:
            desired = max(desired, current_sl)

        should_modify = current_sl is None or desired > current_sl + 1e-9

    elif side == "SELL":
        desired = entry - lock_profit
        if current_sl is not None:
            desired = min(desired, current_sl)

        should_modify = current_sl is None or desired < current_sl - 1e-9

    else:
        raise ValueError(f"unsupported signal: {signal}")

    result.update(
        {
            "should_modify": bool(should_modify),
            "desired_stop": round(float(desired), 2),
            "lock_profit": round(float(lock_profit), 2),
            "stage": (
                "FIRST_PROFIT_LOCK"
                if completed_steps == 0
                else f"STEP_LOCK_{completed_steps + 1}"
            ),
            "reason": (
                "profit_lock_advance"
                if should_modify
                else "existing_stop_already_tighter"
            ),
        }
    )

    return result


def evaluate_early_failure(
    *,
    signal: str,
    entry_price: float,
    current_price: float,
    best_price: float,
    age_seconds: float,
    opposite_impulse: bool = False,
    momentum_failed: bool = False,
    policy: StepTrailPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    side = str(signal or "").upper()
    age = max(0.0, float(age_seconds))

    mfe = favorable_move(
        signal=side,
        entry_price=entry_price,
        best_price=best_price,
    )
    adverse = adverse_move(
        signal=side,
        entry_price=entry_price,
        current_price=current_price,
    )

    result = {
        "strategy": STRATEGY_NAME,
        "signal": side,
        "age_seconds": round(age, 3),
        "mfe": round(mfe, 4),
        "adverse": round(adverse, 4),
        "opposite_impulse": bool(opposite_impulse),
        "momentum_failed": bool(momentum_failed),
        "should_exit": False,
        "reason": "early_failure_not_confirmed",
    }

    # Once the profit-lock activation has been reached, the trailing stop owns
    # the exit. Early-failure logic must not fight the trail.
    if mfe + 1e-9 >= policy.activation_profit:
        result["reason"] = "profit_lock_authority_active"
        return result

    if age + 1e-9 < policy.early_failure_grace_seconds:
        result["reason"] = "early_failure_grace_active"
        return result

    failure_signal = bool(opposite_impulse or momentum_failed)

    if (
        failure_signal
        and adverse + 1e-9 >= policy.early_failure_min_adverse
    ):
        result["should_exit"] = True
        result["reason"] = (
            "opposite_impulse_early_failure"
            if opposite_impulse
            else "momentum_failure_early_exit"
        )

    return result
