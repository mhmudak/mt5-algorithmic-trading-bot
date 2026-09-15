from __future__ import annotations

import math
from typing import Any

from config.settings import (
    ENABLE_ENTRY_TP_OPPORTUNITY_OBSERVER,
    ENTRY_TP_OPPORTUNITY_LOOKBACK_BARS,
    ENTRY_TP_OPPORTUNITY_SWING_WINDOW,
    ENTRY_TP_DAILY_LEVEL_HIGH_DIAP,
    ENTRY_TP_DAILY_LEVEL_LOW_DIAP,
    ENTRY_TP_LEVEL_MATCH_TOLERANCE_PRICE,
    ENTRY_TP_LEVEL_DEDUPE_PRICE,
    ENTRY_TP_EXTENSION_MIN_DISTANCE_PRICE,
    ENTRY_TP_TARGET_REACH_SCORE_ENABLED,
    ENTRY_TP_TARGET_REACH_MOMENTUM_LOOKBACK,
    ENTRY_TP_TARGET_REACH_VOLUME_LOOKBACK,
    ENTRY_TP_TARGET_REACH_DISTANCE_DECAY,
    ENTRY_TP_TARGET_REACH_WEIGHT_DISTANCE,
    ENTRY_TP_TARGET_REACH_WEIGHT_STRUCTURE,
    ENTRY_TP_TARGET_REACH_WEIGHT_MOMENTUM,
    ENTRY_TP_TARGET_REACH_WEIGHT_TICK_ACTIVITY,
    ENTRY_TP_TARGET_REACH_WEIGHT_ENTRY,
)

from src.daily_level_context import (
    calculate_daily_context_from_d1,
)

from src.universal_tp_ladder import (
    build_universal_tp_ladder,
)


DECISION_IMPACT = "DISPLAY_ONLY"
TARGET_REACH_MODEL = "UNCALIBRATED_HEURISTIC_V1"


def safe_float(
    value: Any,
    default: float | None = None,
) -> float | None:
    try:
        if value is None:
            return default

        numeric = float(value)

        if not math.isfinite(numeric):
            return default

        return numeric

    except Exception:
        return default


def _clamp(
    value: float,
    lower: float,
    upper: float,
) -> float:
    return max(
        lower,
        min(
            upper,
            value,
        ),
    )


def calculate_rr(
    signal: str,
    entry: Any,
    sl: Any,
    tp: Any,
) -> float | None:
    entry = safe_float(entry)
    sl = safe_float(sl)
    tp = safe_float(tp)

    if (
        entry is None
        or sl is None
        or tp is None
    ):
        return None

    if signal == "BUY":
        risk = entry - sl
        reward = tp - entry

    elif signal == "SELL":
        risk = sl - entry
        reward = entry - tp

    else:
        return None

    if (
        risk <= 0
        or reward <= 0
    ):
        return None

    return round(
        reward / risk,
        2,
    )


def _reference_entry(
    signal_data: dict[str, Any],
) -> float | None:
    for key in (
        "entry_reference",
        "setup_entry_reference",
        "reference_entry",
    ):
        value = safe_float(
            signal_data.get(key)
        )

        if value is not None:
            return value

    return None


def _directional_entry_drift(
    signal: str,
    reference_entry: float | None,
    actual_entry: float | None,
) -> float | None:
    if (
        reference_entry is None
        or actual_entry is None
    ):
        return None

    if signal == "BUY":
        return round(
            actual_entry
            - reference_entry,
            2,
        )

    if signal == "SELL":
        return round(
            reference_entry
            - actual_entry,
            2,
        )

    return None


def _entry_quality(
    *,
    drift: float | None,
    reference_rr: float | None,
    executable_rr: float | None,
    required_rr: float | None,
) -> tuple[str, str]:
    if drift is None:
        return (
            "UNKNOWN",
            "reference_entry_unavailable",
        )

    if abs(drift) < 0.01:
        return (
            "STABLE",
            "execution_near_reference_entry",
        )

    if drift < 0:
        return (
            "IMPROVED",
            "execution_better_than_reference_entry",
        )

    if (
        reference_rr is not None
        and executable_rr is not None
        and required_rr is not None
        and reference_rr >= required_rr
        and executable_rr < required_rr
    ):
        return (
            "DEGRADED",
            "entry_drift_lost_rr_viability",
        )

    if (
        reference_rr is not None
        and executable_rr is not None
        and (
            reference_rr
            - executable_rr
        ) >= 0.10
    ):
        return (
            "DEGRADED",
            "entry_drift_reduced_rr",
        )

    return (
        "SLIGHTLY_DEGRADED",
        "adverse_entry_drift",
    )


def _closed_frame(df: Any):
    if df is None:
        return None

    try:
        if len(df) < 3:
            return None

        # Always exclude current/incomplete candle.
        closed = (
            df.iloc[:-1]
            .copy()
            .reset_index(drop=True)
        )

        lookback = max(
            10,
            int(
                ENTRY_TP_OPPORTUNITY_LOOKBACK_BARS
            ),
        )

        if len(closed) > lookback:
            closed = (
                closed.iloc[-lookback:]
                .reset_index(drop=True)
            )

        return closed

    except Exception:
        return None


def _swing_levels(
    df: Any,
) -> list[dict[str, Any]]:
    closed = _closed_frame(df)

    if closed is None:
        return []

    window = max(
        1,
        int(
            ENTRY_TP_OPPORTUNITY_SWING_WINDOW
        ),
    )

    if len(closed) < (
        window * 2
        + 1
    ):
        return []

    levels: list[dict[str, Any]] = []

    for index in range(
        window,
        len(closed) - window,
    ):
        try:
            row = closed.iloc[index]

            low = safe_float(
                row.get("low")
            )

            high = safe_float(
                row.get("high")
            )

            neighborhood = closed.iloc[
                index - window:
                index + window + 1
            ]

            lows = [
                safe_float(value)
                for value in neighborhood[
                    "low"
                ].tolist()
            ]

            highs = [
                safe_float(value)
                for value in neighborhood[
                    "high"
                ].tolist()
            ]

            lows = [
                value
                for value in lows
                if value is not None
            ]

            highs = [
                value
                for value in highs
                if value is not None
            ]

            if (
                low is not None
                and lows
                and low == min(lows)
            ):
                levels.append(
                    {
                        "name": "M15-SWING-L",
                        "price": round(
                            low,
                            2,
                        ),
                        "source": (
                            "PRIOR_CLOSED_SWING_LOW"
                        ),
                        "priority": 2,
                    }
                )

            if (
                high is not None
                and highs
                and high == max(highs)
            ):
                levels.append(
                    {
                        "name": "M15-SWING-H",
                        "price": round(
                            high,
                            2,
                        ),
                        "source": (
                            "PRIOR_CLOSED_SWING_HIGH"
                        ),
                        "priority": 2,
                    }
                )

        except Exception:
            continue

    return levels


def _daily_context(
    d1_df: Any,
) -> dict[str, Any] | None:
    try:
        return (
            calculate_daily_context_from_d1(
                d1_df,
                high_diap=(
                    ENTRY_TP_DAILY_LEVEL_HIGH_DIAP
                ),
                low_diap=(
                    ENTRY_TP_DAILY_LEVEL_LOW_DIAP
                ),
            )
        )

    except Exception:
        return None


def _collect_context_levels(
    *,
    df: Any,
    daily_context: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    levels: list[dict[str, Any]] = []

    if isinstance(
        daily_context,
        dict,
    ):
        five_level = (
            daily_context.get(
                "five_level"
            )
            or {}
        )

        classic = (
            daily_context.get(
                "classic"
            )
            or {}
        )

        for name, price in (
            five_level.get(
                "ordered"
            )
            or []
        ):
            numeric = safe_float(
                price
            )

            if numeric is None:
                continue

            levels.append(
                {
                    "name": f"D-{name}",
                    "price": round(
                        numeric,
                        2,
                    ),
                    "source": (
                        "D1_FIVE_LEVEL"
                    ),
                    "priority": 5,
                }
            )

        for name, price in (
            classic.get(
                "ordered"
            )
            or []
        ):
            numeric = safe_float(
                price
            )

            if numeric is None:
                continue

            levels.append(
                {
                    "name": (
                        "D-P"
                        if name == "P"
                        else f"P-{name}"
                    ),
                    "price": round(
                        numeric,
                        2,
                    ),
                    "source": (
                        "CLASSIC_DAILY_PIVOT"
                    ),
                    "priority": 4,
                }
            )

        previous_high = safe_float(
            daily_context.get(
                "previous_day_high"
            )
        )

        previous_low = safe_float(
            daily_context.get(
                "previous_day_low"
            )
        )

        if previous_high is not None:
            levels.append(
                {
                    "name": "PDH",
                    "price": round(
                        previous_high,
                        2,
                    ),
                    "source": (
                        "PREVIOUS_DAY_HIGH"
                    ),
                    "priority": 4,
                }
            )

        if previous_low is not None:
            levels.append(
                {
                    "name": "PDL",
                    "price": round(
                        previous_low,
                        2,
                    ),
                    "source": (
                        "PREVIOUS_DAY_LOW"
                    ),
                    "priority": 4,
                }
            )

    levels.extend(
        _swing_levels(
            df
        )
    )

    # Prefer stronger HTF evidence when sources overlap.
    ordered = sorted(
        levels,
        key=lambda item: (
            -int(
                item.get(
                    "priority",
                    0,
                )
            ),
            float(
                item["price"]
            ),
        ),
    )

    deduped: list[dict[str, Any]] = []

    tolerance = max(
        0.0,
        float(
            ENTRY_TP_LEVEL_DEDUPE_PRICE
        ),
    )

    for item in ordered:
        price = safe_float(
            item.get(
                "price"
            )
        )

        if price is None:
            continue

        duplicate = any(
            abs(
                price
                - float(
                    existing[
                        "price"
                    ]
                )
            )
            <= tolerance
            for existing in deduped
        )

        if duplicate:
            continue

        deduped.append(
            item
        )

    return sorted(
        deduped,
        key=lambda item: float(
            item["price"]
        ),
    )


def _directional_reward(
    signal,
    entry,
    tp,
):
    entry = safe_float(entry)
    tp = safe_float(tp)

    if (
        entry is None
        or tp is None
    ):
        return None

    if signal == "BUY":
        reward = tp - entry

    elif signal == "SELL":
        reward = entry - tp

    else:
        return None

    if reward <= 0:
        return None

    return reward


def _build_management_targets(
    *,
    signal,
    entry,
    sl,
    tp3,
) -> list[dict[str, Any]]:
    ladder = build_universal_tp_ladder(
        signal=signal,
        entry=entry,
        sl=sl,
        tp3=tp3,
    )

    if (
        not isinstance(
            ladder,
            list,
        )
        or len(ladder) < 3
    ):
        return []

    roles = (
        "MANAGEMENT",
        "MANAGEMENT",
        "BASE",
    )

    targets = []

    for index in range(3):
        item = ladder[index]

        if not isinstance(
            item,
            dict,
        ):
            return []

        price = safe_float(
            item.get(
                "price",
                item.get(
                    "take_profit"
                ),
            )
        )

        if price is None:
            return []

        targets.append(
            {
                "name": f"TP{index + 1}",
                "price": round(
                    price,
                    2,
                ),
                "role": roles[index],
            }
        )

    return targets


def _meaningful_extension_distance(
    *,
    signal,
    entry,
    base_tp,
) -> float:
    base_reward = (
        _directional_reward(
            signal,
            entry,
            base_tp,
        )
        or 0.0
    )

    return max(
        float(
            ENTRY_TP_EXTENSION_MIN_DISTANCE_PRICE
        ),
        base_reward * 0.15,
    )


def _select_extension(
    *,
    signal,
    entry,
    base_tp,
    context_levels,
) -> dict[str, Any] | None:
    entry = safe_float(entry)
    base_tp = safe_float(base_tp)

    if (
        entry is None
        or base_tp is None
    ):
        return None

    minimum_distance = (
        _meaningful_extension_distance(
            signal=signal,
            entry=entry,
            base_tp=base_tp,
        )
    )

    candidates = []

    for item in context_levels:
        price = safe_float(
            item.get(
                "price"
            )
        )

        if price is None:
            continue

        if signal == "SELL":
            if (
                price
                >= base_tp
                - minimum_distance
            ):
                continue

            distance = (
                base_tp - price
            )

        elif signal == "BUY":
            if (
                price
                <= base_tp
                + minimum_distance
            ):
                continue

            distance = (
                price - base_tp
            )

        else:
            return None

        candidates.append(
            {
                **item,
                "distance_from_base": (
                    distance
                ),
            }
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            float(
                item[
                    "distance_from_base"
                ]
            ),
            -int(
                item.get(
                    "priority",
                    0,
                )
            ),
        )
    )

    return candidates[0]


def _path_label(
    barrier_count: int,
) -> str:
    if barrier_count <= 0:
        return "CLEAR"

    if barrier_count == 1:
        return "1 BARRIER"

    return f"{barrier_count} BARRIERS"


def _target_context(
    *,
    signal,
    entry,
    target,
    context_levels,
) -> dict[str, Any]:
    entry = safe_float(entry)
    target = safe_float(target)

    if (
        entry is None
        or target is None
    ):
        return {
            "path_label": "UNKNOWN",
            "barrier_count": None,
            "barrier_penalty": None,
            "level_name": None,
            "level_price": None,
            "level_source": None,
        }

    tolerance = max(
        0.0,
        float(
            ENTRY_TP_LEVEL_MATCH_TOLERANCE_PRICE
        ),
    )

    target_matches = []

    for item in context_levels:
        price = safe_float(
            item.get(
                "price"
            )
        )

        if price is None:
            continue

        distance = abs(
            price - target
        )

        if distance <= tolerance:
            target_matches.append(
                {
                    **item,
                    "_target_distance": (
                        distance
                    ),
                }
            )

    target_match = None

    if target_matches:
        target_match = min(
            target_matches,
            key=lambda item: (
                float(
                    item[
                        "_target_distance"
                    ]
                ),
                -int(
                    item.get(
                        "priority",
                        0,
                    )
                ),
            ),
        )

    barriers = []

    for item in context_levels:
        price = safe_float(
            item.get(
                "price"
            )
        )

        if price is None:
            continue

        # The target's own structural zone is a destination,
        # not a barrier beyond the target.
        if (
            abs(
                price - target
            )
            <= tolerance
        ):
            continue

        if signal == "SELL":
            between = (
                target
                < price
                < entry
            )

        elif signal == "BUY":
            between = (
                entry
                < price
                < target
            )

        else:
            between = False

        if between:
            barriers.append(
                item
            )

    barrier_penalty = 0.0

    for item in barriers:
        priority = max(
            0,
            int(
                item.get(
                    "priority",
                    0,
                )
            ),
        )

        barrier_penalty += (
            6.0
            + 4.0
            * priority
        )

    barrier_count = len(
        barriers
    )

    return {
        "path_label": _path_label(
            barrier_count
        ),
        "barrier_count": barrier_count,
        "barrier_penalty": round(
            barrier_penalty,
            2,
        ),
        "level_name": (
            target_match.get(
                "name"
            )
            if target_match
            else None
        ),
        "level_price": (
            target_match.get(
                "price"
            )
            if target_match
            else None
        ),
        "level_source": (
            target_match.get(
                "source"
            )
            if target_match
            else None
        ),
    }


def _latest_closed_atr(
    closed,
) -> float | None:
    if (
        closed is None
        or len(closed) == 0
    ):
        return None

    try:
        latest = safe_float(
            closed.iloc[-1].get(
                "atr_14"
            )
        )

        if (
            latest is not None
            and latest > 0
        ):
            return latest

    except Exception:
        pass

    ranges = []

    try:
        subset = closed.iloc[-14:]

        for _, row in subset.iterrows():
            high = safe_float(
                row.get("high")
            )

            low = safe_float(
                row.get("low")
            )

            if (
                high is not None
                and low is not None
                and high > low
            ):
                ranges.append(
                    high - low
                )

    except Exception:
        return None

    if not ranges:
        return None

    ranges = sorted(
        ranges
    )

    middle = len(ranges) // 2

    if len(ranges) % 2:
        value = ranges[middle]

    else:
        value = (
            ranges[middle - 1]
            + ranges[middle]
        ) / 2.0

    if value <= 0:
        return None

    return value


def _market_features(
    *,
    df,
    signal,
) -> dict[str, Any]:
    closed = _closed_frame(df)

    result = {
        "source": "LATEST_CLOSED_M15",
        "atr": None,
        "directional_move_atr": None,
        "directional_efficiency": None,
        "momentum_score": 50.0,
        "tick_volume_z": None,
        "tick_activity_score": 50.0,
        "tick_volume_available": False,
    }

    if (
        closed is None
        or len(closed) < 3
    ):
        return result

    atr = _latest_closed_atr(
        closed
    )

    result["atr"] = (
        round(
            atr,
            6,
        )
        if atr is not None
        else None
    )

    if (
        atr is None
        or atr <= 0
    ):
        return result

    direction = (
        1.0
        if signal == "BUY"
        else -1.0
    )

    momentum_lookback = max(
        2,
        int(
            ENTRY_TP_TARGET_REACH_MOMENTUM_LOOKBACK
        ),
    )

    recent = closed.iloc[
        -min(
            len(closed),
            momentum_lookback + 1,
        ):
    ]

    closes = []

    for value in recent[
        "close"
    ].tolist():
        numeric = safe_float(
            value
        )

        if numeric is not None:
            closes.append(
                numeric
            )

    if len(closes) >= 2:
        raw_net = (
            closes[-1]
            - closes[0]
        )

        directional_net = (
            direction
            * raw_net
        )

        directional_move_atr = (
            directional_net
            / atr
        )

        total_path = sum(
            abs(
                closes[index]
                - closes[index - 1]
            )
            for index in range(
                1,
                len(closes),
            )
        )

        efficiency = (
            abs(
                raw_net
            )
            / total_path
            if total_path > 0
            else 0.0
        )

        signed_efficiency = (
            efficiency
            if directional_net >= 0
            else -efficiency
        )

        normalized_move = _clamp(
            directional_move_atr,
            -1.5,
            1.5,
        ) / 1.5

        momentum_score = _clamp(
            50.0
            + 20.0
            * normalized_move
            + 20.0
            * signed_efficiency,
            0.0,
            100.0,
        )

        result[
            "directional_move_atr"
        ] = round(
            directional_move_atr,
            4,
        )

        result[
            "directional_efficiency"
        ] = round(
            signed_efficiency,
            4,
        )

        result["momentum_score"] = round(
            momentum_score,
            2,
        )

    volume_lookback = max(
        5,
        int(
            ENTRY_TP_TARGET_REACH_VOLUME_LOOKBACK
        ),
    )

    if (
        "tick_volume"
        in closed.columns
        and len(closed) >= 6
    ):
        current_volume = safe_float(
            closed.iloc[-1].get(
                "tick_volume"
            )
        )

        reference = closed.iloc[
            -min(
                len(closed),
                volume_lookback + 1,
            ):
            -1
        ]

        reference_values = [
            safe_float(value)
            for value in reference[
                "tick_volume"
            ].tolist()
        ]

        reference_values = [
            value
            for value in reference_values
            if (
                value is not None
                and value >= 0
            )
        ]

        if (
            current_volume is not None
            and len(reference_values) >= 5
        ):
            mean = sum(
                reference_values
            ) / len(
                reference_values
            )

            variance = sum(
                (
                    value - mean
                ) ** 2
                for value in reference_values
            ) / len(
                reference_values
            )

            std = math.sqrt(
                variance
            )

            z_score = (
                (
                    current_volume
                    - mean
                )
                / std
                if std > 0
                else 0.0
            )

            alignment = _clamp(
                safe_float(
                    result.get(
                        "directional_move_atr"
                    ),
                    0.0,
                )
                or 0.0,
                -1.0,
                1.0,
            )

            if z_score >= 0:
                tick_activity_score = (
                    50.0
                    + 15.0
                    * min(
                        z_score,
                        2.0,
                    )
                    * alignment
                )

            else:
                # Quiet activity does not create directional
                # conviction; apply only a mild penalty.
                tick_activity_score = (
                    50.0
                    - 5.0
                    * min(
                        abs(
                            z_score
                        ),
                        2.0,
                    )
                )

            result[
                "tick_volume_z"
            ] = round(
                z_score,
                3,
            )

            result[
                "tick_activity_score"
            ] = round(
                _clamp(
                    tick_activity_score,
                    0.0,
                    100.0,
                ),
                2,
            )

            result[
                "tick_volume_available"
            ] = True

    return result


def _entry_component_score(
    entry_quality: str,
) -> float:
    return {
        "IMPROVED": 90.0,
        "STABLE": 70.0,
        "SLIGHTLY_DEGRADED": 50.0,
        "DEGRADED": 30.0,
        "UNKNOWN": 50.0,
    }.get(
        str(
            entry_quality
            or "UNKNOWN"
        ),
        50.0,
    )


def _target_reach_score(
    *,
    signal,
    entry,
    target,
    path_context,
    market_features,
    entry_quality,
) -> dict[str, Any]:
    if not ENTRY_TP_TARGET_REACH_SCORE_ENABLED:
        return {
            "target_reach_score": None,
            "target_reach_model": (
                TARGET_REACH_MODEL
            ),
            "target_reach_calibrated": False,
            "target_distance_atr": None,
            "target_reach_components": None,
        }

    entry = safe_float(entry)
    target = safe_float(target)

    atr = safe_float(
        market_features.get(
            "atr"
        )
    )

    if (
        entry is None
        or target is None
        or atr is None
        or atr <= 0
    ):
        return {
            "target_reach_score": None,
            "target_reach_model": (
                TARGET_REACH_MODEL
            ),
            "target_reach_calibrated": False,
            "target_distance_atr": None,
            "target_reach_components": None,
        }

    reward = _directional_reward(
        signal,
        entry,
        target,
    )

    if reward is None:
        return {
            "target_reach_score": None,
            "target_reach_model": (
                TARGET_REACH_MODEL
            ),
            "target_reach_calibrated": False,
            "target_distance_atr": None,
            "target_reach_components": None,
        }

    distance_atr = (
        reward / atr
    )

    distance_score = (
        100.0
        * math.exp(
            -float(
                ENTRY_TP_TARGET_REACH_DISTANCE_DECAY
            )
            * distance_atr
        )
    )

    barrier_penalty = safe_float(
        path_context.get(
            "barrier_penalty"
        ),
        0.0,
    ) or 0.0

    structure_score = _clamp(
        100.0
        - barrier_penalty,
        0.0,
        100.0,
    )

    momentum_score = safe_float(
        market_features.get(
            "momentum_score"
        ),
        50.0,
    ) or 50.0

    tick_activity_score = safe_float(
        market_features.get(
            "tick_activity_score"
        ),
        50.0,
    ) or 50.0

    entry_score = (
        _entry_component_score(
            entry_quality
        )
    )

    components = {
        "distance": round(
            distance_score,
            2,
        ),
        "structure": round(
            structure_score,
            2,
        ),
        "momentum": round(
            momentum_score,
            2,
        ),
        "tick_activity": round(
            tick_activity_score,
            2,
        ),
        "entry": round(
            entry_score,
            2,
        ),
    }

    weights = {
        "distance": float(
            ENTRY_TP_TARGET_REACH_WEIGHT_DISTANCE
        ),
        "structure": float(
            ENTRY_TP_TARGET_REACH_WEIGHT_STRUCTURE
        ),
        "momentum": float(
            ENTRY_TP_TARGET_REACH_WEIGHT_MOMENTUM
        ),
        "tick_activity": float(
            ENTRY_TP_TARGET_REACH_WEIGHT_TICK_ACTIVITY
        ),
        "entry": float(
            ENTRY_TP_TARGET_REACH_WEIGHT_ENTRY
        ),
    }

    total_weight = sum(
        max(
            0.0,
            value,
        )
        for value in weights.values()
    )

    if total_weight <= 0:
        return {
            "target_reach_score": None,
            "target_reach_model": (
                TARGET_REACH_MODEL
            ),
            "target_reach_calibrated": False,
            "target_distance_atr": round(
                distance_atr,
                4,
            ),
            "target_reach_components": (
                components
            ),
        }

    weighted_score = sum(
        components[name]
        * max(
            0.0,
            weights[name],
        )
        for name in components
    ) / total_weight

    return {
        "target_reach_score": int(
            round(
                _clamp(
                    weighted_score,
                    0.0,
                    100.0,
                )
            )
        ),
        "target_reach_model": (
            TARGET_REACH_MODEL
        ),
        "target_reach_calibrated": False,
        "target_distance_atr": round(
            distance_atr,
            4,
        ),
        "target_reach_components": (
            components
        ),
    }


def build_entry_tp_opportunity(
    *,
    df: Any,
    signal: str,
    signal_data: dict[str, Any] | None,
    trade_plan: dict[str, Any] | None,
    required_rr: Any = None,
    d1_df: Any = None,
) -> dict[str, Any]:
    # Display-only entry/target context.
    #
    # TRS is an uncalibrated heuristic score. It must never
    # be presented as a probability until outcome calibration
    # is separately implemented and validated.

    result: dict[str, Any] = {
        "enabled": bool(
            ENABLE_ENTRY_TP_OPPORTUNITY_OBSERVER
        ),
        "decision_impact": DECISION_IMPACT,
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_score": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
        "can_modify_required_rr": False,
        "can_modify_recovery": False,
    }

    if (
        not ENABLE_ENTRY_TP_OPPORTUNITY_OBSERVER
    ):
        result["available"] = False
        result["reason"] = (
            "observer_disabled"
        )

        return result

    signal_data = dict(
        signal_data or {}
    )

    trade_plan = dict(
        trade_plan or {}
    )

    signal = str(
        signal or ""
    ).upper()

    if signal not in {
        "BUY",
        "SELL",
    }:
        result["available"] = False
        result["reason"] = (
            "invalid_signal"
        )

        return result

    actual_entry = safe_float(
        trade_plan.get(
            "entry_price"
        )
    )

    sl = safe_float(
        trade_plan.get(
            "stop_loss"
        )
    )

    base_tp = safe_float(
        trade_plan.get(
            "original_take_profit",
            trade_plan.get(
                "take_profit"
            ),
        )
    )

    reference_entry = (
        _reference_entry(
            signal_data
        )
    )

    required_rr_value = safe_float(
        required_rr
    )

    executable_rr = calculate_rr(
        signal,
        actual_entry,
        sl,
        base_tp,
    )

    reference_rr = calculate_rr(
        signal,
        reference_entry,
        sl,
        base_tp,
    )

    drift = (
        _directional_entry_drift(
            signal,
            reference_entry,
            actual_entry,
        )
    )

    quality, quality_reason = (
        _entry_quality(
            drift=drift,
            reference_rr=reference_rr,
            executable_rr=executable_rr,
            required_rr=required_rr_value,
        )
    )

    daily_context = (
        _daily_context(
            d1_df
        )
    )

    context_levels = (
        _collect_context_levels(
            df=df,
            daily_context=daily_context,
        )
    )

    market_features = (
        _market_features(
            df=df,
            signal=signal,
        )
    )

    targets = (
        _build_management_targets(
            signal=signal,
            entry=actual_entry,
            sl=sl,
            tp3=base_tp,
        )
    )

    extension = (
        _select_extension(
            signal=signal,
            entry=actual_entry,
            base_tp=base_tp,
            context_levels=context_levels,
        )
        if (
            actual_entry is not None
            and base_tp is not None
        )
        else None
    )

    if extension:
        targets.append(
            {
                "name": "TP4",
                "price": round(
                    float(
                        extension[
                            "price"
                        ]
                    ),
                    2,
                ),
                "role": "RUNNER",
                "extension_source": (
                    extension.get(
                        "source"
                    )
                ),
                "extension_level_name": (
                    extension.get(
                        "name"
                    )
                ),
            }
        )

    enriched_targets = []

    for target in targets:
        price = safe_float(
            target.get(
                "price"
            )
        )

        path_context = (
            _target_context(
                signal=signal,
                entry=actual_entry,
                target=price,
                context_levels=context_levels,
            )
        )

        reach = (
            _target_reach_score(
                signal=signal,
                entry=actual_entry,
                target=price,
                path_context=path_context,
                market_features=market_features,
                entry_quality=quality,
            )
        )

        enriched_targets.append(
            {
                **target,
                "rr": calculate_rr(
                    signal,
                    actual_entry,
                    sl,
                    price,
                ),
                **path_context,
                **reach,
            }
        )

    runner = None

    for item in enriched_targets:
        if (
            item.get("role")
            == "RUNNER"
        ):
            runner = item
            break

    result.update(
        {
            "available": (
                actual_entry is not None
                and sl is not None
                and base_tp is not None
            ),
            "signal": signal,
            "strategy": signal_data.get(
                "strategy"
            ),
            "entry_model": signal_data.get(
                "entry_model"
            ),
            "reference_entry": (
                round(
                    reference_entry,
                    2,
                )
                if reference_entry
                is not None
                else None
            ),
            "actual_entry": (
                round(
                    actual_entry,
                    2,
                )
                if actual_entry
                is not None
                else None
            ),
            "entry_drift": drift,
            "entry_quality": quality,
            "entry_quality_reason": (
                quality_reason
            ),
            "reference_rr": reference_rr,
            "executable_rr": executable_rr,
            "required_rr": (
                round(
                    required_rr_value,
                    2,
                )
                if required_rr_value
                is not None
                else None
            ),
            "rr_degradation": (
                round(
                    reference_rr
                    - executable_rr,
                    2,
                )
                if (
                    reference_rr
                    is not None
                    and executable_rr
                    is not None
                )
                else None
            ),
            "base_tp": (
                round(
                    base_tp,
                    2,
                )
                if base_tp
                is not None
                else None
            ),
            "base_tp_model": (
                signal_data.get(
                    "target_model"
                )
                or "UNKNOWN"
            ),
            "daily_context_available": (
                daily_context
                is not None
            ),
            "daily_context": daily_context,
            "context_level_count": len(
                context_levels
            ),
            "market_features": market_features,
            "target_reach_model": (
                TARGET_REACH_MODEL
            ),
            "target_reach_calibrated": False,
            "tp_targets": enriched_targets,
            "extension_tp": (
                runner.get(
                    "price"
                )
                if runner
                else None
            ),
            "extension_rr": (
                runner.get(
                    "rr"
                )
                if runner
                else None
            ),
            "extension_source": (
                extension.get(
                    "source"
                )
                if extension
                else None
            ),
        }
    )

    return result


def _fmt_price(value: Any) -> str:
    numeric = safe_float(value)

    if numeric is None:
        return "N/A"

    return f"{numeric:.2f}"


def _fmt_rr(value: Any) -> str:
    numeric = safe_float(value)

    if numeric is None:
        return "N/A"

    return f"{numeric:.2f}R"


def format_entry_tp_opportunity(
    result: dict[str, Any] | None,
) -> str:
    if not isinstance(
        result,
        dict,
    ):
        return ""

    if (
        not result.get("enabled")
        or not result.get("available")
    ):
        return ""

    targets = (
        result.get(
            "tp_targets"
        )
        or []
    )

    if not targets:
        return ""

    lines = [
        "🎯 TP CONTEXT | TRS=UNCAL",
    ]

    for item in targets:
        name = str(
            item.get(
                "name",
                "TP",
            )
        )

        price = _fmt_price(
            item.get(
                "price"
            )
        )

        rr = _fmt_rr(
            item.get(
                "rr"
            )
        )

        score = item.get(
            "target_reach_score"
        )

        score_text = (
            f"TRS {int(score)}"
            if isinstance(
                score,
                (int, float),
            )
            else "TRS N/A"
        )

        path = str(
            item.get(
                "path_label",
                "UNKNOWN",
            )
        )

        parts = [
            f"{name} {price}",
            rr,
            score_text,
            path,
        ]

        level_name = (
            item.get(
                "level_name"
            )
        )

        if level_name:
            parts.append(
                str(
                    level_name
                )
            )

        role = str(
            item.get(
                "role"
            )
            or ""
        )

        if role == "BASE":
            parts.append(
                "BASE"
            )

        elif role == "RUNNER":
            parts.append(
                "RUNNER"
            )

        lines.append(
            " | ".join(
                parts
            )
        )

    drift = safe_float(
        result.get(
            "entry_drift"
        )
    )

    quality = str(
        result.get(
            "entry_quality",
            "UNKNOWN",
        )
    )

    if drift is None:
        drift_text = "N/A"

    elif drift > 0:
        drift_text = (
            f"-{drift:.2f}"
        )

    elif drift < 0:
        drift_text = (
            f"+{abs(drift):.2f}"
        )

    else:
        drift_text = "0.00"

    executable_rr = _fmt_rr(
        result.get(
            "executable_rr"
        )
    )

    required_rr = _fmt_rr(
        result.get(
            "required_rr"
        )
    )

    lines.append(
        f"Entry {quality} {drift_text}"
        f" | RR {executable_rr}/{required_rr}"
    )

    daily_context = (
        result.get(
            "daily_context"
        )
        or {}
    )

    five_level = (
        daily_context.get(
            "five_level"
        )
        or {}
    )

    classic = (
        daily_context.get(
            "classic"
        )
        or {}
    )

    pivot = safe_float(
        (
            classic.get(
                "levels"
            )
            or {}
        ).get(
            "P"
        )
    )

    if daily_context:
        mode = (
            five_level.get(
                "mode"
            )
            or "UNKNOWN"
        )

        if pivot is not None:
            lines.append(
                f"D1 {mode}"
                f" | Pivot {pivot:.2f}"
            )

        else:
            lines.append(
                f"D1 {mode}"
            )

    return "\n".join(
        lines
    )
