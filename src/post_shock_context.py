from __future__ import annotations

from typing import Mapping

import pandas as pd


OBSERVER_VERSION = (
    "post_shock_context_observer_v1"
)


def _number(value):
    try:
        if value is None:
            return None

        value = float(value)

        if pd.isna(value):
            return None

        return value

    except Exception:
        return None


def _rounded(value, digits=3):
    value = _number(value)

    if value is None:
        return None

    return round(
        value,
        digits,
    )


def _time(value):
    try:
        result = pd.to_datetime(
            value,
            errors="coerce",
        )

        if pd.isna(result):
            return None

        return result

    except Exception:
        return None


def _bar_metrics(row):
    open_price = _number(
        row.get("open")
    )

    high = _number(
        row.get("high")
    )

    low = _number(
        row.get("low")
    )

    close = _number(
        row.get("close")
    )

    atr = _number(
        row.get("atr_14")
    )

    if None in (
        open_price,
        high,
        low,
        close,
    ):
        return None

    candle_range = abs(
        high - low
    )

    body = abs(
        close - open_price
    )

    range_atr = None
    body_atr = None

    if (
        atr is not None
        and atr > 0
    ):
        range_atr = (
            candle_range / atr
        )

        body_atr = (
            body / atr
        )

    return {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "atr": atr,
        "range_price": (
            candle_range
        ),
        "body_price": body,
        "range_atr_ratio": (
            range_atr
        ),
        "body_atr_ratio": (
            body_atr
        ),
    }


def _is_shock(
    metrics,
    *,
    abs_range_price,
    range_atr_ratio,
    body_atr_ratio,
):
    if not metrics:
        return False

    absolute_expansion = bool(
        metrics["range_price"]
        >= float(
            abs_range_price
        )
    )

    normalized_expansion = bool(
        (
            metrics[
                "range_atr_ratio"
            ]
            is not None
            and metrics[
                "range_atr_ratio"
            ]
            >= float(
                range_atr_ratio
            )
        )
        or (
            metrics[
                "body_atr_ratio"
            ]
            is not None
            and metrics[
                "body_atr_ratio"
            ]
            >= float(
                body_atr_ratio
            )
        )
    )

    return bool(
        absolute_expansion
        and normalized_expansion
    )


def _setup_geometry(
    setup,
    atr,
):
    if not isinstance(
        setup,
        Mapping,
    ):
        setup = {}

    entry = None

    for key in (
        "entry_reference",
        "entry_price",
        "entry",
    ):
        entry = _number(
            setup.get(key)
        )

        if entry is not None:
            break

    sl = None

    for key in (
        "sl_reference",
        "stop_loss",
        "sl",
    ):
        sl = _number(
            setup.get(key)
        )

        if sl is not None:
            break

    stop_distance = None
    stop_atr_ratio = None

    if (
        entry is not None
        and sl is not None
    ):
        stop_distance = abs(
            entry - sl
        )

        if (
            atr is not None
            and atr > 0
        ):
            stop_atr_ratio = (
                stop_distance / atr
            )

    return {
        "entry_reference": (
            _rounded(entry)
        ),
        "sl_reference": (
            _rounded(sl)
        ),
        "stop_distance": (
            _rounded(
                stop_distance
            )
        ),
        "stop_atr_ratio": (
            _rounded(
                stop_atr_ratio
            )
        ),
    }


def _normalization(
    post_shock_m5,
    *,
    required_bars,
    max_range_atr_ratio,
    max_body_atr_ratio,
):
    if (
        post_shock_m5 is None
        or len(post_shock_m5)
        < int(required_bars)
    ):
        return {
            "normalized": False,
            "bars_checked": 0,
            "max_range_atr_ratio": None,
            "max_body_atr_ratio": None,
        }

    recent = (
        post_shock_m5.iloc[
            -int(required_bars):
        ]
    )

    ranges = []
    bodies = []

    for _, row in recent.iterrows():
        metrics = _bar_metrics(
            row
        )

        if not metrics:
            return {
                "normalized": False,
                "bars_checked": (
                    len(ranges)
                ),
                "max_range_atr_ratio": None,
                "max_body_atr_ratio": None,
            }

        range_ratio = metrics.get(
            "range_atr_ratio"
        )

        body_ratio = metrics.get(
            "body_atr_ratio"
        )

        if (
            range_ratio is None
            or body_ratio is None
        ):
            return {
                "normalized": False,
                "bars_checked": (
                    len(ranges)
                ),
                "max_range_atr_ratio": None,
                "max_body_atr_ratio": None,
            }

        ranges.append(
            range_ratio
        )

        bodies.append(
            body_ratio
        )

    maximum_range = max(
        ranges
    )

    maximum_body = max(
        bodies
    )

    return {
        "normalized": bool(
            maximum_range
            <= float(
                max_range_atr_ratio
            )
            and maximum_body
            <= float(
                max_body_atr_ratio
            )
        ),
        "bars_checked": len(
            ranges
        ),
        "max_range_atr_ratio": (
            _rounded(
                maximum_range
            )
        ),
        "max_body_atr_ratio": (
            _rounded(
                maximum_body
            )
        ),
    }


def _fresh_m5_structure(
    post_shock_m5,
):
    if (
        post_shock_m5 is None
        or len(post_shock_m5) < 3
    ):
        return {
            "fresh_structure": False,
            "pivot_type": None,
            "pivot_price": None,
        }

    # Latest confirmed 3-bar pivot wins.
    for index in range(
        len(post_shock_m5) - 2,
        0,
        -1,
    ):
        previous = (
            post_shock_m5.iloc[
                index - 1
            ]
        )

        middle = (
            post_shock_m5.iloc[
                index
            ]
        )

        nxt = (
            post_shock_m5.iloc[
                index + 1
            ]
        )

        prev_high = _number(
            previous.get("high")
        )

        middle_high = _number(
            middle.get("high")
        )

        next_high = _number(
            nxt.get("high")
        )

        if None not in (
            prev_high,
            middle_high,
            next_high,
        ):
            if (
                middle_high > prev_high
                and middle_high
                >= next_high
            ):
                return {
                    "fresh_structure": True,
                    "pivot_type": (
                        "M5_SWING_HIGH"
                    ),
                    "pivot_price": (
                        _rounded(
                            middle_high
                        )
                    ),
                }

        prev_low = _number(
            previous.get("low")
        )

        middle_low = _number(
            middle.get("low")
        )

        next_low = _number(
            nxt.get("low")
        )

        if None not in (
            prev_low,
            middle_low,
            next_low,
        ):
            if (
                middle_low < prev_low
                and middle_low
                <= next_low
            ):
                return {
                    "fresh_structure": True,
                    "pivot_type": (
                        "M5_SWING_LOW"
                    ),
                    "pivot_price": (
                        _rounded(
                            middle_low
                        )
                    ),
                }

    return {
        "fresh_structure": False,
        "pivot_type": None,
        "pivot_price": None,
    }


def build_post_shock_context(
    *,
    m15_df,
    m5_df=None,
    setup=None,
    now=None,
    enabled=True,
    m15_abs_range_price=30.0,
    m15_range_atr_ratio=2.5,
    m15_body_atr_ratio=1.8,
    lookback_m15_bars=5,
    max_age_minutes=60,
    m5_min_closed_bars=3,
    m5_normalized_bars=2,
    m5_max_range_atr_ratio=1.6,
    m5_max_body_atr_ratio=1.0,
):
    base = {
        "observer_version": (
            OBSERVER_VERSION
        ),
        "observer_only": True,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "enabled": bool(enabled),
    }

    if not enabled:
        return {
            **base,
            "available": False,
            "state": "DISABLED",
            "active_post_shock_mode": False,
            "exit_ready": False,
            "reason": (
                "observer_disabled"
            ),
        }

    if (
        m15_df is None
        or len(m15_df) < 3
    ):
        return {
            **base,
            "available": False,
            "state": "UNAVAILABLE",
            "active_post_shock_mode": False,
            "exit_ready": False,
            "reason": (
                "insufficient_m15_data"
            ),
        }

    # Last row is the current/forming M15.
    closed_m15 = (
        m15_df.iloc[:-1]
        .copy()
        .reset_index(drop=True)
    )

    search_start = max(
        0,
        len(closed_m15)
        - int(
            lookback_m15_bars
        ),
    )

    shocks = []

    for index in range(
        search_start,
        len(closed_m15),
    ):
        row = closed_m15.iloc[
            index
        ]

        metrics = _bar_metrics(
            row
        )

        if not _is_shock(
            metrics,
            abs_range_price=(
                m15_abs_range_price
            ),
            range_atr_ratio=(
                m15_range_atr_ratio
            ),
            body_atr_ratio=(
                m15_body_atr_ratio
            ),
        ):
            continue

        bar_time = _time(
            row.get("time")
        )

        if bar_time is None:
            continue

        shock_close_time = (
            bar_time
            + pd.Timedelta(
                minutes=15
            )
        )

        shocks.append(
            {
                "index": index,
                "bar_time": bar_time,
                "close_time": (
                    shock_close_time
                ),
                "metrics": metrics,
            }
        )

    latest_atr = _number(
        closed_m15.iloc[-1].get(
            "atr_14"
        )
    )

    geometry = (
        _setup_geometry(
            setup,
            latest_atr,
        )
    )

    if not shocks:
        return {
            **base,
            "available": True,
            "state": "NORMAL",
            "active_post_shock_mode": False,
            "exit_ready": True,
            "reason": (
                "no_recent_shock"
            ),
            "recent_shock_detected": False,
            "setup_geometry": geometry,
        }

    shock = shocks[-1]

    now_value = _time(
        now
    )

    if now_value is None:
        now_value = (
            shock["close_time"]
        )

    age_minutes = max(
        0.0,
        (
            now_value
            - shock[
                "close_time"
            ]
        ).total_seconds()
        / 60.0,
    )

    metrics = shock[
        "metrics"
    ]

    if (
        metrics["close"]
        > metrics["open"]
    ):
        direction = "UP"

    elif (
        metrics["close"]
        < metrics["open"]
    ):
        direction = "DOWN"

    else:
        direction = "FLAT"

    post_shock_m5 = None

    if (
        m5_df is not None
        and len(m5_df) >= 3
        and "time" in m5_df.columns
    ):
        # Last M5 row is considered forming.
        closed_m5 = (
            m5_df.iloc[:-1]
            .copy()
        )

        times = pd.to_datetime(
            closed_m5["time"],
            errors="coerce",
        )

        post_shock_m5 = (
            closed_m5.loc[
                times
                >= shock[
                    "close_time"
                ]
            ]
            .copy()
            .reset_index(
                drop=True
            )
        )

    post_count = (
        len(post_shock_m5)
        if post_shock_m5
        is not None
        else 0
    )

    normalization = (
        _normalization(
            post_shock_m5,
            required_bars=(
                m5_normalized_bars
            ),
            max_range_atr_ratio=(
                m5_max_range_atr_ratio
            ),
            max_body_atr_ratio=(
                m5_max_body_atr_ratio
            ),
        )
    )

    structure = (
        _fresh_m5_structure(
            post_shock_m5
        )
    )

    enough_m5 = bool(
        post_count
        >= int(
            m5_min_closed_bars
        )
    )

    normalized = bool(
        normalization[
            "normalized"
        ]
    )

    fresh_structure = bool(
        structure[
            "fresh_structure"
        ]
    )

    natural_exit_ready = bool(
        enough_m5
        and normalized
        and fresh_structure
    )

    timeout = bool(
        age_minutes
        >= float(
            max_age_minutes
        )
    )

    if timeout:
        state = "NORMAL"
        active = False
        exit_ready = True
        reason = (
            "post_shock_max_age_reclassification"
        )

    elif not enough_m5:
        state = "SHOCK_ACTIVE"
        active = True
        exit_ready = False
        reason = (
            "waiting_for_minimum_closed_m5_bars"
        )

    elif natural_exit_ready:
        state = "NORMAL"
        active = False
        exit_ready = True
        reason = (
            "fresh_m5_structure_and_"
            "volatility_normalized"
        )

    else:
        state = (
            "POST_SHOCK_ENTRY_MODE"
        )

        active = True
        exit_ready = False
        reason = (
            "post_shock_structure_"
            "not_yet_normalized"
        )

    return {
        **base,
        "available": True,
        "state": state,
        "active_post_shock_mode": active,
        "exit_ready": exit_ready,
        "reason": reason,
        "recent_shock_detected": True,
        "shock_direction": direction,
        "shock_bar_time": str(
            shock["bar_time"]
        ),
        "shock_close_time": str(
            shock["close_time"]
        ),
        "shock_age_minutes": (
            _rounded(
                age_minutes
            )
        ),
        "shock_range_price": (
            _rounded(
                metrics[
                    "range_price"
                ]
            )
        ),
        "shock_body_price": (
            _rounded(
                metrics[
                    "body_price"
                ]
            )
        ),
        "shock_atr": (
            _rounded(
                metrics[
                    "atr"
                ]
            )
        ),
        "shock_range_atr_ratio": (
            _rounded(
                metrics[
                    "range_atr_ratio"
                ]
            )
        ),
        "shock_body_atr_ratio": (
            _rounded(
                metrics[
                    "body_atr_ratio"
                ]
            )
        ),
        "post_shock_m5_closed_bars": (
            post_count
        ),
        "m5_volatility_normalized": (
            normalized
        ),
        "m5_normalization": (
            normalization
        ),
        "m5_fresh_structure": (
            fresh_structure
        ),
        "m5_pivot_type": (
            structure[
                "pivot_type"
            ]
        ),
        "m5_pivot_price": (
            structure[
                "pivot_price"
            ]
        ),
        "setup_geometry": geometry,
    }
