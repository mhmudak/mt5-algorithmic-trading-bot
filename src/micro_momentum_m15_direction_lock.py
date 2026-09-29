from __future__ import annotations

from typing import Any, Dict, Optional

from src.intrabar_opposite_direction_guard import (
    is_opposite_signal,
    normalize_signal,
)
from src.m15_setup_direction_lock import get_active_m15_direction_lock


def evaluate_micro_momentum_m15_direction_lock(
    *,
    signal: Any,
    lock_state: Optional[Dict[str, Any]],
    enabled: bool = True,
    now_ts: Optional[float] = None,
) -> Dict[str, Any]:
    normalized_signal = normalize_signal(signal)

    if not enabled:
        return {
            "allowed": True,
            "reason": "guard_disabled",
            "active_lock": None,
        }

    if not normalized_signal:
        return {
            "allowed": True,
            "reason": "invalid_micro_momentum_signal",
            "active_lock": None,
        }

    active_lock = get_active_m15_direction_lock(
        lock_state,
        now_ts=now_ts,
    )

    if not active_lock:
        return {
            "allowed": True,
            "reason": "no_active_m15_direction_lock",
            "active_lock": None,
        }

    if is_opposite_signal(normalized_signal, active_lock.get("signal")):
        return {
            "allowed": False,
            "reason": "micro_momentum_opposite_m15_direction_lock_blocked",
            "active_lock": active_lock,
        }

    return {
        "allowed": True,
        "reason": "micro_momentum_aligned_with_m15_lock",
        "active_lock": active_lock,
    }
