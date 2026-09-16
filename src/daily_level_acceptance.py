from __future__ import annotations

from typing import Any

from config.settings import (
    ENTRY_TP_DAILY_LEVEL_HIGH_DIAP,
    ENTRY_TP_DAILY_LEVEL_LOW_DIAP,
    SESSION_ORB_DAILY_LEVEL_MAX_DISTANCE_ATR,
    SESSION_ORB_DAILY_LEVEL_MIN_BREAK_ATR,
    SESSION_ORB_DAILY_LEVEL_MIN_BREAK_PRICE,
)
from src.daily_level_context import (
    calculate_daily_context_from_d1,
)


def _safe_float(
    value: Any,
) -> float | None:
    try:
        value = float(value)

        if value != value:
            return None

        return value

    except Exception:
        return None


def _collect_opposing_levels(
    daily_context: dict[str, Any],
    signal: str,
) -> list[dict[str, Any]]:
    levels: list[dict[str, Any]] = []

    signal = str(
        signal
        or ""
    ).upper()

    if signal not in {
        "BUY",
        "SELL",
    }:
        return levels

    prefix = (
        "R"
        if signal == "BUY"
        else "S"
    )

    five_level = (
        daily_context.get(
            "five_level"
        )
        or {}
    )

    for name, price in (
        five_level.get(
            "ordered"
        )
        or []
    ):
        name = str(
            name
            or ""
        ).upper()

        if not name.startswith(
            prefix
        ):
            continue

        numeric = _safe_float(
            price
        )

        if numeric is None:
            continue

        levels.append(
            {
                "name": f"D-{name}",
                "price": numeric,
                "source": "D1_FIVE_LEVEL",
                "priority": 5,
            }
        )

    classic = (
        daily_context.get(
            "classic"
        )
        or {}
    )

    for name, price in (
        classic.get(
            "ordered"
        )
        or []
    ):
        name = str(
            name
            or ""
        ).upper()

        if not name.startswith(
            prefix
        ):
            continue

        numeric = _safe_float(
            price
        )

        if numeric is None:
            continue

        levels.append(
            {
                "name": f"P-{name}",
                "price": numeric,
                "source": "CLASSIC_DAILY_PIVOT",
                "priority": 4,
            }
        )

    if signal == "BUY":
        previous = _safe_float(
            daily_context.get(
                "previous_day_high"
            )
        )

        if previous is not None:
            levels.append(
                {
                    "name": "PDH",
                    "price": previous,
                    "source": "PREVIOUS_DAY_HIGH",
                    "priority": 4,
                }
            )

    else:
        previous = _safe_float(
            daily_context.get(
                "previous_day_low"
            )
        )

        if previous is not None:
            levels.append(
                {
                    "name": "PDL",
                    "price": previous,
                    "source": "PREVIOUS_DAY_LOW",
                    "priority": 4,
                }
            )

    return levels


def _directional_break_distance(
    *,
    signal: str,
    price: float,
    level: float,
) -> float:
    if signal == "BUY":
        return (
            price
            - level
        )

    return (
        level
        - price
    )


def build_session_orb_daily_level_watch(
    *,
    d1_df: Any,
    signal: str,
    entry_price: Any,
    atr: Any,
) -> dict[str, Any]:
    signal = str(
        signal
        or ""
    ).upper()

    entry = _safe_float(
        entry_price
    )

    atr_value = _safe_float(
        atr
    )

    result = {
        "available": False,
        "required": False,
        "strategy_scope": "SESSION_ORB_RETEST_ONLY",
        "signal": signal,
        "entry_price": entry,
        "atr": atr_value,
        "state": "UNAVAILABLE",
        "level_name": None,
        "level_price": None,
        "level_source": None,
        "distance_to_level": None,
        "distance_atr": None,
        "break_distance": None,
        "min_break_distance": None,
        "max_watch_distance": None,
        "daily_context": None,
    }

    if (
        signal not in {
            "BUY",
            "SELL",
        }
        or entry is None
        or atr_value is None
        or atr_value <= 0
    ):
        return result

    try:
        daily_context = (
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
        daily_context = None

    if not isinstance(
        daily_context,
        dict,
    ):
        return result

    max_watch_distance = (
        atr_value
        * max(
            0.0,
            float(
                SESSION_ORB_DAILY_LEVEL_MAX_DISTANCE_ATR
            ),
        )
    )

    min_break_distance = max(
        max(
            0.0,
            float(
                SESSION_ORB_DAILY_LEVEL_MIN_BREAK_PRICE
            ),
        ),
        atr_value
        * max(
            0.0,
            float(
                SESSION_ORB_DAILY_LEVEL_MIN_BREAK_ATR
            ),
        ),
    )

    candidates = []

    for item in _collect_opposing_levels(
        daily_context,
        signal,
    ):
        level_price = _safe_float(
            item.get(
                "price"
            )
        )

        if level_price is None:
            continue

        absolute_distance = abs(
            entry
            - level_price
        )

        if (
            absolute_distance
            > max_watch_distance
        ):
            continue

        item_break_distance = (
            _directional_break_distance(
                signal=signal,
                price=entry,
                level=level_price,
            )
        )

        # A level already cleared by the configured acceptance
        # distance must not mask the next unresolved barrier.
        if (
            item_break_distance
            >= min_break_distance
        ):
            continue

        candidates.append(
            {
                **item,
                "absolute_distance": (
                    absolute_distance
                ),
                "break_distance": (
                    item_break_distance
                ),
            }
        )

    result.update(
        {
            "available": True,
            "daily_context": daily_context,
            "max_watch_distance": round(
                max_watch_distance,
                4,
            ),
            "min_break_distance": round(
                min_break_distance,
                4,
            ),
        }
    )

    if not candidates:
        result["state"] = (
            "NO_NEARBY_OPPOSING_D1_LEVEL"
        )
        return result

    nearest = sorted(
        candidates,
        key=lambda item: (
            float(
                item[
                    "absolute_distance"
                ]
            ),
            -int(
                item.get(
                    "priority",
                    0,
                )
            ),
        ),
    )[0]

    level_price = float(
        nearest[
            "price"
        ]
    )

    break_distance = (
        _directional_break_distance(
            signal=signal,
            price=entry,
            level=level_price,
        )
    )

    distance_to_level = (
        level_price
        - entry
        if signal == "BUY"
        else entry
        - level_price
    )

    if (
        break_distance
        >= min_break_distance
    ):
        state = (
            "ACCEPTED_BY_DISTANCE"
        )
        required = False

    elif break_distance >= 0:
        state = (
            "BREAK_UNCONFIRMED"
        )
        required = True

    else:
        state = "TESTING"
        required = True

    result.update(
        {
            "required": required,
            "state": state,
            "level_name": (
                nearest.get(
                    "name"
                )
            ),
            "level_price": round(
                level_price,
                2,
            ),
            "level_source": (
                nearest.get(
                    "source"
                )
            ),
            "distance_to_level": round(
                distance_to_level,
                4,
            ),
            "distance_atr": round(
                (
                    distance_to_level
                    / atr_value
                ),
                4,
            ),
            "break_distance": round(
                break_distance,
                4,
            ),
        }
    )

    return result


def daily_level_acceptance_ready(
    *,
    signal: str,
    tick: Any,
    level: Any,
    min_distance: Any,
) -> tuple[
    bool,
    float | None,
    float | None,
]:
    signal = str(
        signal
        or ""
    ).upper()

    level_value = _safe_float(
        level
    )

    min_distance_value = _safe_float(
        min_distance
    )

    if (
        signal not in {
            "BUY",
            "SELL",
        }
        or level_value is None
        or min_distance_value is None
    ):
        return (
            False,
            None,
            None,
        )

    try:
        current_price = (
            float(
                tick.ask
            )
            if signal == "BUY"
            else float(
                tick.bid
            )
        )

    except Exception:
        return (
            False,
            None,
            None,
        )

    break_distance = (
        _directional_break_distance(
            signal=signal,
            price=current_price,
            level=level_value,
        )
    )

    return (
        break_distance
        >= min_distance_value,
        round(
            current_price,
            5,
        ),
        round(
            break_distance,
            5,
        ),
    )
