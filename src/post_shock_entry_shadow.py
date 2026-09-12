from __future__ import annotations

from typing import Any


OBSERVER_VERSION = (
    "post_shock_entry_shadow_v1_2"
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


def _base_m1_observation() -> dict[str, Any]:
    return {
        "available": False,
        "observer_only": True,
        "decision_impact": "NONE",
        "safe_for_execution": False,
        "state": "UNAVAILABLE",
        "reason": "insufficient_closed_m1_bars",
        "signal": None,
        "closed_bar_count": 0,
        "latest_closed_time": None,
        "retrace_observed": False,
        "reclaim_observed": False,
        "directional_body": False,
        "directional_pattern_observed": False,
        "previous_bar": None,
        "latest_bar": None,
    }


def _safe_bar(
    value: Any,
) -> dict[str, Any] | None:
    if not isinstance(
        value,
        dict,
    ):
        return None

    open_price = _safe_float(
        value.get("open")
    )

    high_price = _safe_float(
        value.get("high")
    )

    low_price = _safe_float(
        value.get("low")
    )

    close_price = _safe_float(
        value.get("close")
    )

    if any(
        price is None
        for price in (
            open_price,
            high_price,
            low_price,
            close_price,
        )
    ):
        return None

    if high_price < max(
        open_price,
        close_price,
        low_price,
    ):
        return None

    if low_price > min(
        open_price,
        close_price,
        high_price,
    ):
        return None

    time_value = value.get(
        "time"
    )

    if time_value is not None:
        time_value = str(
            time_value
        )

    return {
        "time": time_value,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
    }


def build_m1_retrace_reclaim_observation(
    *,
    m1_closed_bars: Any,
    signal: Any,
) -> dict[str, Any]:
    """
    Observe closed M1 bars only.

    This does not construct an entry, stop, target,
    RR decision, risk decision or execution signal.
    """

    result = (
        _base_m1_observation()
    )

    normalized_signal = str(
        signal
        or ""
    ).upper()

    result[
        "signal"
    ] = normalized_signal or None

    if normalized_signal not in {
        "BUY",
        "SELL",
    }:
        result.update(
            {
                "state": (
                    "INVALID_SIGNAL"
                ),
                "reason": (
                    "m1_observer_requires_"
                    "buy_or_sell"
                ),
            }
        )

        return result

    if not isinstance(
        m1_closed_bars,
        (list, tuple),
    ):
        return result

    result[
        "closed_bar_count"
    ] = len(
        m1_closed_bars
    )

    if len(
        m1_closed_bars
    ) < 2:
        return result

    previous_bar = _safe_bar(
        m1_closed_bars[-2]
    )

    latest_bar = _safe_bar(
        m1_closed_bars[-1]
    )

    if (
        previous_bar is None
        or latest_bar is None
    ):
        result.update(
            {
                "state": (
                    "INVALID_M1_BAR_DATA"
                ),
                "reason": (
                    "invalid_closed_m1_ohlc"
                ),
            }
        )

        return result

    result.update(
        {
            "available": True,
            "latest_closed_time": (
                latest_bar.get(
                    "time"
                )
            ),
            "previous_bar": (
                previous_bar
            ),
            "latest_bar": (
                latest_bar
            ),
        }
    )

    if (
        normalized_signal
        == "BUY"
    ):
        directional_body = bool(
            latest_bar["close"]
            > latest_bar["open"]
        )

        retrace_observed = bool(
            latest_bar["low"]
            <= previous_bar["close"]
            and latest_bar["close"]
            > previous_bar["close"]
        )

        reclaim_observed = bool(
            latest_bar["close"]
            > previous_bar["high"]
        )

    else:
        directional_body = bool(
            latest_bar["close"]
            < latest_bar["open"]
        )

        retrace_observed = bool(
            latest_bar["high"]
            >= previous_bar["close"]
            and latest_bar["close"]
            < previous_bar["close"]
        )

        reclaim_observed = bool(
            latest_bar["close"]
            < previous_bar["low"]
        )

    directional_pattern = bool(
        directional_body
        and (
            retrace_observed
            or reclaim_observed
        )
    )

    result.update(
        {
            "retrace_observed": (
                retrace_observed
            ),
            "reclaim_observed": (
                reclaim_observed
            ),
            "directional_body": (
                directional_body
            ),
            "directional_pattern_observed": (
                directional_pattern
            ),
        }
    )

    if directional_pattern:
        result.update(
            {
                "state": (
                    "M1_RETRACE_RECLAIM_OBSERVED"
                ),
                "reason": (
                    "directional_closed_m1_"
                    "retrace_or_reclaim_observed"
                ),
            }
        )

        return result

    result.update(
        {
            "state": (
                "M1_WAIT_DIRECTIONAL_PATTERN"
            ),
            "reason": (
                "closed_m1_directional_pattern_"
                "not_observed"
            ),
        }
    )

    return result


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
        "m1_observation": (
            _base_m1_observation()
        ),
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
    m1_closed_bars: Any = None,
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

    m1_observation = (
        build_m1_retrace_reclaim_observation(
            m1_closed_bars=(
                m1_closed_bars
            ),
            signal=(
                setup_data.get(
                    "signal"
                )
            ),
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
            "m1_observation": (
                m1_observation
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

        if not m1_observation.get(
            "available",
            False,
        ):
            result.update(
                {
                    "state": (
                        "WAIT_M1_DATA"
                    ),
                    "reason": (
                        "shock_scale_stop_wait_"
                        "closed_m1_data"
                    ),
                    "shadow_candidate": True,
                }
            )

            return result

        if not m1_observation.get(
            "directional_pattern_observed",
            False,
        ):
            result.update(
                {
                    "state": (
                        "WAIT_M1_RETRACE_RECLAIM"
                    ),
                    "reason": (
                        "shock_scale_stop_wait_"
                        "m1_retrace_or_reclaim"
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
                    "fresh_m5_and_m1_pattern"
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

def build_post_shock_entry_shadow_fail_open(
    *,
    post_shock_context: dict[str, Any] | None,
    setup: dict[str, Any] | None,
    current_price: Any = None,
    m1_closed_bars: Any = None,
    shock_scale_stop_ratio: float = (
        DEFAULT_SHOCK_SCALE_STOP_RATIO
    ),
) -> dict[str, Any]:
    """
    Guaranteed fail-open live integration wrapper.

    Any observer/classifier failure must degrade to
    inert telemetry and must never interrupt or
    influence the trading decision path.
    """

    try:
        return build_post_shock_entry_shadow(
            post_shock_context=(
                post_shock_context
            ),
            setup=setup,
            current_price=current_price,
            m1_closed_bars=(
                m1_closed_bars
            ),
            shock_scale_stop_ratio=(
                shock_scale_stop_ratio
            ),
        )

    except Exception as exc:
        result = _base_result()

        result.update(
            {
                "available": False,
                "state": "OBSERVER_ERROR",
                "reason": (
                    "shadow_classifier_failed_open"
                ),
                "shadow_candidate": False,
                "abnormal_stop_geometry": False,
                "error_type": (
                    type(exc).__name__
                ),
            }
        )

        return result
