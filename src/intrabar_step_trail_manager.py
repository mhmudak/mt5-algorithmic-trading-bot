from __future__ import annotations

from typing import Any

import MetaTrader5 as mt5

from config import settings as runtime_settings
from src.intrabar_step_trail_detector import get_step_trail_failure_context
from src.intrabar_step_trail_policy import (
    StepTrailPolicy,
    evaluate_early_failure,
    evaluate_profit_lock,
)
from src.logger import logger
from src.position_manager import close_position_volume, modify_sl


STRATEGY_NAME = "INTRABAR_STEP_TRAIL"
_STATES: dict[str, dict[str, Any]] = {}


def build_runtime_step_trail_policy() -> StepTrailPolicy:
    return StepTrailPolicy(
        hard_stop_distance=float(
            getattr(runtime_settings, "INTRABAR_STEP_TRAIL_HARD_STOP_PRICE", 7.00)
        ),
        activation_profit=float(
            getattr(runtime_settings, "INTRABAR_STEP_TRAIL_ACTIVATION_PROFIT", 0.60)
        ),
        first_lock_profit=float(
            getattr(runtime_settings, "INTRABAR_STEP_TRAIL_FIRST_LOCK_PROFIT", 0.10)
        ),
        trail_step=float(
            getattr(runtime_settings, "INTRABAR_STEP_TRAIL_TRAIL_STEP", 0.50)
        ),
        trail_gap=float(
            getattr(runtime_settings, "INTRABAR_STEP_TRAIL_TRAIL_GAP", 0.50)
        ),
        early_failure_grace_seconds=float(
            getattr(
                runtime_settings,
                "INTRABAR_STEP_TRAIL_EARLY_FAILURE_GRACE_SECONDS",
                2.00,
            )
        ),
        early_failure_min_adverse=float(
            getattr(
                runtime_settings,
                "INTRABAR_STEP_TRAIL_EARLY_FAILURE_MIN_ADVERSE",
                0.75,
            )
        ),
    )


def reset_intrabar_step_trail_manager_state() -> None:
    _STATES.clear()


def _is_step_trail_position(position: Any) -> bool:
    comment = str(getattr(position, "comment", "") or "").upper()
    return comment.startswith(STRATEGY_NAME)


def _direction(position: Any) -> str:
    if position.type == mt5.POSITION_TYPE_BUY:
        return "BUY"
    return "SELL"


def _current_price(position: Any, tick: Any) -> float:
    if position.type == mt5.POSITION_TYPE_BUY:
        return float(tick.bid)
    return float(tick.ask)


def _state_for(position: Any, tick: Any) -> dict[str, Any]:
    key = str(position.ticket)
    state = _STATES.get(key)
    direction = _direction(position)
    current = _current_price(position, tick)

    if state is None:
        state = {
            "ticket": int(position.ticket),
            "signal": direction,
            "entry_price": float(position.price_open),
            "best_price": current,
            "opened_ts": float(getattr(position, "time", 0) or 0),
        }
        _STATES[key] = state

    if direction == "BUY":
        state["best_price"] = max(float(state["best_price"]), current)
    else:
        state["best_price"] = min(float(state["best_price"]), current)

    return state


def manage_intrabar_step_trail_positions(
    *,
    symbol: str,
    tick: Any,
) -> list[dict[str, Any]]:
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return []

    positions = [
        position
        for position in positions
        if _is_step_trail_position(position)
    ]

    active_tickets = {str(position.ticket) for position in positions}
    for key in list(_STATES):
        if key not in active_tickets:
            _STATES.pop(key, None)

    events: list[dict[str, Any]] = []
    now_ts = float(getattr(tick, "time", 0) or 0)
    policy = build_runtime_step_trail_policy()

    for position in positions:
        state = _state_for(position, tick)
        signal = state["signal"]
        current = _current_price(position, tick)
        current_sl = float(getattr(position, "sl", 0.0) or 0.0)
        current_sl_value = current_sl if current_sl > 0 else None

        lock = evaluate_profit_lock(
            signal=signal,
            entry_price=float(state["entry_price"]),
            best_price=float(state["best_price"]),
            current_stop=current_sl_value,
            policy=policy,
        )

        if lock["should_modify"]:
            if modify_sl(
                position,
                lock["desired_stop"],
                0.0,
                reason=(
                    "INTRABAR_STEP_TRAIL "
                    f"{lock['stage']} MFE={lock['mfe']}"
                ),
            ):
                events.append(
                    {
                        "event": "STEP_TRAIL_SL_ADVANCED",
                        "ticket": int(position.ticket),
                        **lock,
                    }
                )
                logger.info(
                    "[STEP TRAIL MANAGER] SL advanced | "
                    f"ticket={position.ticket} signal={signal} "
                    f"best={state['best_price']} "
                    f"new_sl={lock['desired_stop']} stage={lock['stage']}"
                )
                try:
                    from src.intrabar_optimization_recorder import (
                        note_intrabar_management_event,
                    )
                    note_intrabar_management_event(
                        position_id=position.ticket,
                        event="STEP_TRAIL_SL_ADVANCED",
                        details=lock,
                    )
                except Exception:
                    pass
            continue

        failure_context = get_step_trail_failure_context(signal)
        age_seconds = max(
            0.0,
            now_ts - float(state.get("opened_ts") or now_ts),
        )

        failure = evaluate_early_failure(
            signal=signal,
            entry_price=float(state["entry_price"]),
            current_price=current,
            best_price=float(state["best_price"]),
            age_seconds=age_seconds,
            opposite_impulse=bool(
                failure_context.get("opposite_impulse")
            ),
            momentum_failed=bool(
                failure_context.get("momentum_failed")
            ),
            policy=policy,
        )

        if failure["should_exit"]:
            if close_position_volume(
                position,
                float(position.volume),
                tick,
                reason=(
                    "INTRABAR_STEP_TRAIL "
                    f"{failure['reason']}"
                ),
            ):
                events.append(
                    {
                        "event": "STEP_TRAIL_EARLY_FAILURE_EXIT",
                        "ticket": int(position.ticket),
                        **failure,
                        "recent_move": failure_context.get("recent_move"),
                    }
                )
                logger.warning(
                    "[STEP TRAIL MANAGER] early failure exit | "
                    f"ticket={position.ticket} signal={signal} "
                    f"adverse={failure['adverse']} "
                    f"reason={failure['reason']}"
                )
                try:
                    from src.intrabar_optimization_recorder import (
                        note_intrabar_management_event,
                    )
                    note_intrabar_management_event(
                        position_id=position.ticket,
                        event="STEP_TRAIL_EARLY_FAILURE_EXIT",
                        details={
                            **failure,
                            "recent_move": failure_context.get(
                                "recent_move"
                            ),
                        },
                    )
                except Exception:
                    pass

    return events
