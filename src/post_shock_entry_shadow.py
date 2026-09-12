from __future__ import annotations

from typing import Any


OBSERVER_VERSION = (
    "post_shock_entry_shadow_v1"
)

DEFAULT_SHOCK_SCALE_STOP_RATIO = 0.75


def _safe_float(
    value: Any,
) -> float | None:
    try:
        if value is None:
            return None

        result = float(value)

        if result <= 0:
            return None

        return result

    except (TypeError, ValueError):
        return None


def _base_result() -> dict[str, Any]:
    return {
        "observer_version": OBSERVER_VERSION,
        "observer_only": True,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
        "available": False,
        "state": "UNAVAILABLE",
        "reason": "insufficient_context",
        "shadow_candidate": False,
        "abnormal_stop_geometry": False,
        "shock_scale_stop_ratio": None,
        "shock_scale_ratio_threshold": (
            DEFAULT_SHOCK_SCALE_STOP_RATIO
        ),
        "post_shock_context_state": None,
        "m5_fresh_structure": False,
        "original_geometry": {
            "entry_price": None,
            "stop_loss": None,
            "stop_distance": None,
            "shock_range_price": None,
        },
        "shadow_plan": {
            "status": "NOT_CONSTRUCTED",
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "risk_reward": None,
            "requirements": [
                "fresh_m5_structure",
                "m1_retrace_or_reclaim",
                "new_local_structural_stop",
                "normal_rr_gate",
                "normal_confirmation_gates",
            ],
        },
    }


def build_post_shock_entry_shadow(
    *,
    post_shock_context: dict[str, Any] | None,
    setup: dict[str, Any] | None,
    current_price: Any = None,
    shock_scale_stop_ratio: float = (
        DEFAULT_SHOCK_SCALE_STOP_RATIO
    ),
) -> dict[str, Any]:
    """
    Observe-only post-shock local-entry classifier.

    This function does NOT:
    - block or approve a setup,
    - rewrite entry / SL / TP,
    - alter RR,
    - alter lot sizing,
    - alter confirmation,
    - authorize execution.

    It only identifies shock-scale original stop
    geometry that may deserve a later, separately
    validated local M1/M5 re-entry model.
    """

    result = _base_result()

    context = (
        post_shock_context
        if isinstance(
            post_shock_context,
            dict,
        )
        else {}
    )

    setup_data = (
        setup
        if isinstance(
            setup,
            dict,
        )
        else {}
    )

    if not context:
        return result

    context_state = str(
        context.get("state")
        or "UNKNOWN"
    ).upper()

    active_mode = bool(
        context.get(
            "active_post_shock_mode",
            False,
        )
    )

    setup_geometry = (
        context.get("setup_geometry")
        if isinstance(
            context.get("setup_geometry"),
            dict,
        )
        else {}
    )

    entry_price = _safe_float(
        setup_geometry.get(
            "entry_price"
        )
        or setup_geometry.get(
            "entry_reference"
        )
        or setup_data.get(
            "entry_reference"
        )
        or current_price
    )

    stop_loss = _safe_float(
        setup_geometry.get(
            "stop_loss"
        )
        or setup_geometry.get(
            "sl_reference"
        )
        or setup_data.get(
            "sl_reference"
        )
    )

    stop_distance = _safe_float(
        setup_geometry.get(
            "stop_distance"
        )
    )

    if (
        stop_distance is None
        and entry_price is not None
        and stop_loss is not None
    ):
        stop_distance = abs(
            entry_price
            - stop_loss
        )

    shock_range = _safe_float(
        context.get(
            "shock_range_price"
        )
    )

    threshold = _safe_float(
        shock_scale_stop_ratio
    )

    if threshold is None:
        threshold = (
            DEFAULT_SHOCK_SCALE_STOP_RATIO
        )

    ratio = None

    if (
        stop_distance is not None
        and shock_range is not None
    ):
        ratio = (
            stop_distance
            / shock_range
        )

    abnormal = bool(
        ratio is not None
        and ratio >= threshold
    )

    m5_fresh_structure = bool(
        context.get(
            "m5_fresh_structure",
            False,
        )
    )

    result.update(
        {
            "available": True,
            "shock_scale_ratio_threshold": (
                threshold
            ),
            "post_shock_context_state": (
                context_state
            ),
            "m5_fresh_structure": (
                m5_fresh_structure
            ),
            "abnormal_stop_geometry": (
                abnormal
            ),
            "shock_scale_stop_ratio": (
                round(ratio, 6)
                if ratio is not None
                else None
            ),
            "original_geometry": {
                "entry_price": (
                    entry_price
                ),
                "stop_loss": (
                    stop_loss
                ),
                "stop_distance": (
                    stop_distance
                ),
                "shock_range_price": (
                    shock_range
                ),
            },
        }
    )

    if not active_mode:
        result.update(
            {
                "state": (
                    "INACTIVE_POST_SHOCK_CONTEXT"
                ),
                "reason": (
                    "post_shock_mode_not_active"
                ),
            }
        )

        return result

    if not abnormal:
        result.update(
            {
                "state": (
                    "NORMAL_STOP_GEOMETRY"
                ),
                "reason": (
                    "original_stop_not_shock_scale"
                ),
            }
        )

        return result

    if context_state == "SHOCK_ACTIVE":
        result.update(
            {
                "state": (
                    "WAIT_POST_SHOCK_STRUCTURE"
                ),
                "reason": (
                    "shock_active_wait_for_"
                    "fresh_local_structure"
                ),
                "shadow_candidate": True,
            }
        )

        return result

    if (
        context_state
        == "POST_SHOCK_ENTRY_MODE"
    ):
        if not m5_fresh_structure:
            result.update(
                {
                    "state": (
                        "WAIT_M5_STRUCTURE"
                    ),
                    "reason": (
                        "shock_scale_stop_wait_"
                        "fresh_m5_structure"
                    ),
                    "shadow_candidate": True,
                }
            )

            return result

        result.update(
            {
                "state": (
                    "SHADOW_LOCAL_REPLAN_CANDIDATE"
                ),
                "reason": (
                    "shock_scale_stop_with_"
                    "fresh_m5_structure"
                ),
                "shadow_candidate": True,
            }
        )

        return result

    result.update(
        {
            "state": (
                "ACTIVE_CONTEXT_UNCLASSIFIED"
            ),
            "reason": (
                "active_post_shock_context_"
                "outside_known_state"
            ),
            "shadow_candidate": (
                abnormal
            ),
        }
    )

    return result
