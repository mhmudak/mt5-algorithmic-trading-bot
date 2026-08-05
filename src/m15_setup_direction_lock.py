from __future__ import annotations

from typing import Any, Dict, Optional
import time

from src.intrabar_opposite_direction_guard import (
    is_intrabar_trade_plan,
    is_opposite_signal,
    normalize_signal,
)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _now(now_ts: Optional[float] = None) -> float:
    return float(now_ts if now_ts is not None else time.time())


def register_m15_direction_lock(
    lock_state: Dict[str, Any],
    *,
    signal: Any,
    setup_id: Any = None,
    strategy: Any = None,
    entry_model: Any = None,
    session: Any = None,
    market_condition: Any = None,
    ttl_seconds: int = 900,
    now_ts: Optional[float] = None,
) -> Dict[str, Any]:
    normalized_signal = normalize_signal(signal)

    if not normalized_signal:
        return lock_state

    created_at = _now(now_ts)
    expires_at = created_at + max(int(ttl_seconds or 0), 1)

    lock_state.clear()
    lock_state.update(
        {
            "active": True,
            "signal": normalized_signal,
            "setup_id": setup_id,
            "strategy": strategy,
            "entry_model": entry_model,
            "session": session,
            "market_condition": market_condition,
            "created_at": created_at,
            "expires_at": expires_at,
            "source": "M15_SETUP_DIRECTION_LOCK",
        }
    )

    return lock_state


def get_active_m15_direction_lock(
    lock_state: Optional[Dict[str, Any]],
    *,
    now_ts: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    state = _as_dict(lock_state)

    if not state or not state.get("active"):
        return None

    current_ts = _now(now_ts)
    expires_at = float(state.get("expires_at") or 0)

    if expires_at <= current_ts:
        state.clear()
        return None

    if not normalize_signal(state.get("signal")):
        state.clear()
        return None

    return dict(state)


def clear_m15_direction_lock(lock_state: Dict[str, Any]) -> None:
    lock_state.clear()


def evaluate_intrabar_m15_direction_lock_guard(
    *,
    signal: Any,
    trade_plan: Any,
    lock_state: Optional[Dict[str, Any]],
    enabled: bool = True,
    now_ts: Optional[float] = None,
) -> Dict[str, Any]:
    if not enabled:
        return {
            "allowed": True,
            "reason": "guard_disabled",
            "active_lock": None,
        }

    if not is_intrabar_trade_plan(trade_plan):
        return {
            "allowed": True,
            "reason": "not_intrabar_trade_plan",
            "active_lock": None,
        }

    active_lock = get_active_m15_direction_lock(lock_state, now_ts=now_ts)

    if not active_lock:
        return {
            "allowed": True,
            "reason": "no_active_m15_direction_lock",
            "active_lock": None,
        }

    if is_opposite_signal(signal, active_lock.get("signal")):
        return {
            "allowed": False,
            "reason": "intrabar_opposite_m15_direction_lock_blocked",
            "active_lock": active_lock,
        }

    return {
        "allowed": True,
        "reason": "same_direction_as_m15_lock",
        "active_lock": active_lock,
    }
