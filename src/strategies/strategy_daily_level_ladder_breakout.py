from __future__ import annotations

import hashlib
from typing import Any

from config.settings import (
    DAILY_LEVEL_LADDER_CLUSTER_ATR,
    DAILY_LEVEL_LADDER_CLUSTER_MAX_PRICE,
    DAILY_LEVEL_LADDER_CLUSTER_MIN_PRICE,
    DAILY_LEVEL_LADDER_MIN_BODY_ATR,
    DAILY_LEVEL_LADDER_MIN_BREAK_ATR,
    DAILY_LEVEL_LADDER_MIN_BREAK_PRICE,
    DAILY_LEVEL_LADDER_MIN_CLOSE_LOCATION,
    DAILY_LEVEL_LADDER_SL_TARGET_ZONE_PCT,
)


STRATEGY_NAME = "DAILY_LEVEL_LADDER_BREAKOUT"
ENTRY_MODEL = "M5_DAILY_LEVEL_BREAKOUT"
SL_MODEL = "DAILY_LEVEL_ZONE_40PCT_SL"
TP_MODEL = "NEXT_DAILY_LEVEL"
DECISION_IMPACT = "MAIN_BOT_RUNTIME_CONTROLLED"


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


def _daily_source_identity(
    daily_context: dict[str, Any],
) -> str:
    value = daily_context.get(
        "time"
    )

    if value is None:
        return "D1_UNKNOWN"

    return str(
        value
    )


def _raw_daily_levels(
    daily_context: dict[str, Any],
) -> list[dict[str, Any]]:
    levels: list[dict[str, Any]] = []

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
        numeric = _safe_float(
            price
        )

        if numeric is None:
            continue

        level_name = (
            "D-P"
            if str(name).upper() == "P"
            else f"P-{str(name).upper()}"
        )

        levels.append(
            {
                "name": level_name,
                "price": numeric,
                "source": "CLASSIC_DAILY_PIVOT",
                "is_pivot": (
                    str(name).upper()
                    == "P"
                ),
                "priority": 4,
            }
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
        numeric = _safe_float(
            price
        )

        if numeric is None:
            continue

        levels.append(
            {
                "name": (
                    f"D-{str(name).upper()}"
                ),
                "price": numeric,
                "source": "D1_FIVE_LEVEL",
                "is_pivot": False,
                "priority": 5,
            }
        )

    previous_high = _safe_float(
        daily_context.get(
            "previous_day_high"
        )
    )

    if previous_high is not None:
        levels.append(
            {
                "name": "PDH",
                "price": previous_high,
                "source": "PREVIOUS_DAY_HIGH",
                "is_pivot": False,
                "priority": 4,
            }
        )

    previous_low = _safe_float(
        daily_context.get(
            "previous_day_low"
        )
    )

    if previous_low is not None:
        levels.append(
            {
                "name": "PDL",
                "price": previous_low,
                "source": "PREVIOUS_DAY_LOW",
                "is_pivot": False,
                "priority": 4,
            }
        )

    return sorted(
        levels,
        key=lambda item: (
            float(
                item[
                    "price"
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


def _cluster_distance(
    atr: float,
) -> float:
    return min(
        max(
            float(
                DAILY_LEVEL_LADDER_CLUSTER_MIN_PRICE
            ),
            atr
            * float(
                DAILY_LEVEL_LADDER_CLUSTER_ATR
            ),
        ),
        float(
            DAILY_LEVEL_LADDER_CLUSTER_MAX_PRICE
        ),
    )


def build_daily_level_clusters(
    *,
    daily_context: dict[str, Any],
    atr: Any,
) -> dict[str, Any] | None:
    atr_value = _safe_float(
        atr
    )

    if (
        not isinstance(
            daily_context,
            dict,
        )
        or atr_value is None
        or atr_value <= 0
    ):
        return None

    classic = (
        daily_context.get(
            "classic"
        )
        or {}
    )

    pivot = _safe_float(
        (
            classic.get(
                "levels"
            )
            or {}
        ).get(
            "P"
        )
    )

    if pivot is None:
        return None

    raw_levels = _raw_daily_levels(
        daily_context
    )

    if not raw_levels:
        return None

    threshold = _cluster_distance(
        atr_value
    )

    clusters: list[dict[str, Any]] = []

    for item in raw_levels:
        price = float(
            item[
                "price"
            ]
        )

        if not clusters:
            clusters.append(
                {
                    "low": price,
                    "high": price,
                    "levels": [
                        item
                    ],
                }
            )
            continue

        active = clusters[-1]

        prospective_low = min(
            float(
                active[
                    "low"
                ]
            ),
            price,
        )

        prospective_high = max(
            float(
                active[
                    "high"
                ]
            ),
            price,
        )

        if (
            prospective_high
            - prospective_low
            <= threshold
        ):
            active[
                "low"
            ] = prospective_low

            active[
                "high"
            ] = prospective_high

            active[
                "levels"
            ].append(
                item
            )

        else:
            clusters.append(
                {
                    "low": price,
                    "high": price,
                    "levels": [
                        item
                    ],
                }
            )

    enriched = []

    for index, cluster in enumerate(
        clusters
    ):
        members = cluster[
            "levels"
        ]

        names = [
            str(
                item.get(
                    "name"
                )
            )
            for item in members
        ]

        sources = sorted(
            {
                str(
                    item.get(
                        "source"
                    )
                )
                for item in members
            }
        )

        contains_pivot = any(
            bool(
                item.get(
                    "is_pivot"
                )
            )
            for item in members
        )

        enriched.append(
            {
                "index": index,
                "low": round(
                    float(
                        cluster[
                            "low"
                        ]
                    ),
                    5,
                ),
                "high": round(
                    float(
                        cluster[
                            "high"
                        ]
                    ),
                    5,
                ),
                "names": names,
                "sources": sources,
                "contains_pivot": (
                    contains_pivot
                ),
            }
        )

    return {
        "source": (
            "BROKER_COMPLETED_D1"
        ),
        "source_time": (
            _daily_source_identity(
                daily_context
            )
        ),
        "pivot": round(
            pivot,
            5,
        ),
        "cluster_distance": round(
            threshold,
            5,
        ),
        "clusters": enriched,
    }


def _closed_m5_rows(
    m5_df: Any,
):
    try:
        if (
            m5_df is None
            or len(m5_df) < 3
        ):
            return None

        previous = m5_df.iloc[-3]
        candle = m5_df.iloc[-2]

        return (
            previous,
            candle,
        )

    except Exception:
        return None


def _setup_id(
    *,
    source_time: str,
    signal: str,
    broken_boundary: float,
    target_price: float,
) -> str:
    raw = (
        f"{STRATEGY_NAME}|"
        f"{source_time}|"
        f"{signal}|"
        f"{broken_boundary:.5f}|"
        f"{target_price:.5f}"
    )

    digest = hashlib.sha1(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()[:12]

    return (
        f"DLLB-{signal}-"
        f"{digest}"
    )


def _strong_close_ok(
    *,
    signal: str,
    candle_open: float,
    candle_high: float,
    candle_low: float,
    candle_close: float,
    atr: float,
) -> tuple[
    bool,
    float,
    float,
]:
    candle_range = (
        candle_high
        - candle_low
    )

    if candle_range <= 0:
        return (
            False,
            0.0,
            0.0,
        )

    body = abs(
        candle_close
        - candle_open
    )

    min_body = (
        atr
        * float(
            DAILY_LEVEL_LADDER_MIN_BODY_ATR
        )
    )

    if body < min_body:
        return (
            False,
            body,
            0.0,
        )

    if signal == "BUY":
        close_location = (
            candle_close
            - candle_low
        ) / candle_range

        passed = (
            candle_close
            > candle_open
            and close_location
            >= float(
                DAILY_LEVEL_LADDER_MIN_CLOSE_LOCATION
            )
        )

    else:
        close_location = (
            candle_high
            - candle_close
        ) / candle_range

        passed = (
            candle_close
            < candle_open
            and close_location
            >= float(
                DAILY_LEVEL_LADDER_MIN_CLOSE_LOCATION
            )
        )

    return (
        passed,
        body,
        close_location,
    )


def evaluate_daily_level_ladder_breakout(
    *,
    m5_df: Any,
    daily_context: dict[str, Any],
) -> dict[str, Any] | None:
    rows = _closed_m5_rows(
        m5_df
    )

    if rows is None:
        return None

    previous, candle = rows

    previous_close = _safe_float(
        previous.get(
            "close"
        )
    )

    candle_open = _safe_float(
        candle.get(
            "open"
        )
    )

    candle_high = _safe_float(
        candle.get(
            "high"
        )
    )

    candle_low = _safe_float(
        candle.get(
            "low"
        )
    )

    candle_close = _safe_float(
        candle.get(
            "close"
        )
    )

    atr = _safe_float(
        candle.get(
            "atr_14"
        )
    )

    if None in {
        previous_close,
        candle_open,
        candle_high,
        candle_low,
        candle_close,
        atr,
    }:
        return None

    if atr <= 0:
        return None

    ladder = (
        build_daily_level_clusters(
            daily_context=daily_context,
            atr=atr,
        )
    )

    if ladder is None:
        return None

    pivot = float(
        ladder[
            "pivot"
        ]
    )

    if candle_close > pivot:
        signal = "BUY"

    elif candle_close < pivot:
        signal = "SELL"

    else:
        return None

    strong_close, body, close_location = (
        _strong_close_ok(
            signal=signal,
            candle_open=candle_open,
            candle_high=candle_high,
            candle_low=candle_low,
            candle_close=candle_close,
            atr=atr,
        )
    )

    if not strong_close:
        return None

    break_buffer = max(
        float(
            DAILY_LEVEL_LADDER_MIN_BREAK_PRICE
        ),
        atr
        * float(
            DAILY_LEVEL_LADDER_MIN_BREAK_ATR
        ),
    )

    clusters = ladder[
        "clusters"
    ]

    crossed: list[
        tuple[
            dict[str, Any],
            float,
        ]
    ] = []

    if signal == "BUY":
        for cluster in clusters:
            boundary = float(
                cluster[
                    "high"
                ]
            )

            if boundary < pivot:
                continue

            if (
                previous_close
                <= boundary
                and candle_close
                >= boundary
                + break_buffer
            ):
                crossed.append(
                    (
                        cluster,
                        boundary,
                    )
                )

        if not crossed:
            return None

        broken_cluster, broken_boundary = max(
            crossed,
            key=lambda item: item[
                1
            ],
        )

        target_cluster = None
        target_price = None

        for cluster in clusters:
            first_contact = float(
                cluster[
                    "low"
                ]
            )

            if (
                cluster[
                    "index"
                ]
                <= broken_cluster[
                    "index"
                ]
            ):
                continue

            if first_contact <= candle_close:
                continue

            target_cluster = cluster
            target_price = first_contact
            break

    else:
        for cluster in clusters:
            boundary = float(
                cluster[
                    "low"
                ]
            )

            if boundary > pivot:
                continue

            if (
                previous_close
                >= boundary
                and candle_close
                <= boundary
                - break_buffer
            ):
                crossed.append(
                    (
                        cluster,
                        boundary,
                    )
                )

        if not crossed:
            return None

        broken_cluster, broken_boundary = min(
            crossed,
            key=lambda item: item[
                1
            ],
        )

        target_cluster = None
        target_price = None

        for cluster in reversed(
            clusters
        ):
            first_contact = float(
                cluster[
                    "high"
                ]
            )

            if (
                cluster[
                    "index"
                ]
                >= broken_cluster[
                    "index"
                ]
            ):
                continue

            if first_contact >= candle_close:
                continue

            target_cluster = cluster
            target_price = first_contact
            break

    if (
        target_cluster is None
        or target_price is None
    ):
        return None

    if signal == "BUY":
        zone_distance = (
            target_price
            - broken_boundary
        )

        if zone_distance <= 0:
            return None

        sl_reference = (
            broken_boundary
            - zone_distance
            * float(
                DAILY_LEVEL_LADDER_SL_TARGET_ZONE_PCT
            )
        )

    else:
        zone_distance = (
            broken_boundary
            - target_price
        )

        if zone_distance <= 0:
            return None

        sl_reference = (
            broken_boundary
            + zone_distance
            * float(
                DAILY_LEVEL_LADDER_SL_TARGET_ZONE_PCT
            )
        )

    if signal == "BUY":
        break_distance = (
            candle_close
            - broken_boundary
        )

    else:
        break_distance = (
            broken_boundary
            - candle_close
        )

    if (
        break_distance
        < break_buffer
    ):
        return None

    source_time = str(
        ladder[
            "source_time"
        ]
    )

    setup_id = _setup_id(
        source_time=source_time,
        signal=signal,
        broken_boundary=broken_boundary,
        target_price=target_price,
    )

    candle_time = None

    try:
        candle_time = str(
            candle.get(
                "time"
            )
        )
    except Exception:
        candle_time = None

    reason = (
        f"{STRATEGY_NAME} {signal} -> "
        f"M5 closed through "
        f"{'/'.join(broken_cluster['names'])} "
        f"boundary={round(broken_boundary, 2)} -> "
        f"next daily zone "
        f"{'/'.join(target_cluster['names'])} "
        f"target={round(target_price, 2)} -> "
        f"SL 40% zone={round(sl_reference, 2)}"
    )

    return {
        "signal": signal,
        "score": 95,
        "strategy": STRATEGY_NAME,
        "entry_model": ENTRY_MODEL,
        "sl_model": SL_MODEL,
        "tp_model": TP_MODEL,
        "target_model": TP_MODEL,
        "decision_impact": DECISION_IMPACT,
        "auto_trade_allowed": True,
        "setup_id": setup_id,
        "daily_source_time": source_time,
        "daily_pivot": round(
            pivot,
            2,
        ),
        "daily_cluster_distance": round(
            float(
                ladder[
                    "cluster_distance"
                ]
            ),
            4,
        ),
        "broken_level": round(
            broken_boundary,
            2,
        ),
        "broken_cluster_names": list(
            broken_cluster[
                "names"
            ]
        ),
        "broken_cluster_low": round(
            float(
                broken_cluster[
                    "low"
                ]
            ),
            2,
        ),
        "broken_cluster_high": round(
            float(
                broken_cluster[
                    "high"
                ]
            ),
            2,
        ),
        "target_level": round(
            target_price,
            2,
        ),
        "target_cluster_names": list(
            target_cluster[
                "names"
            ]
        ),
        "target_cluster_low": round(
            float(
                target_cluster[
                    "low"
                ]
            ),
            2,
        ),
        "target_cluster_high": round(
            float(
                target_cluster[
                    "high"
                ]
            ),
            2,
        ),
        "sl_reference": round(
            sl_reference,
            2,
        ),
        "tp_reference": round(
            target_price,
            2,
        ),
        "entry_reference": round(
            candle_close,
            2,
        ),
        "zone_distance": round(
            zone_distance,
            2,
        ),
        "break_buffer": round(
            break_buffer,
            4,
        ),
        "break_distance": round(
            break_distance,
            4,
        ),
        "m5_body": round(
            body,
            4,
        ),
        "m5_atr": round(
            atr,
            4,
        ),
        "m5_close_location": round(
            close_location,
            4,
        ),
        "m5_closed_time": candle_time,
        "reason": reason,
        "duplicate_policy": (
            "completed_d1_direction_broken_cluster_target_cluster"
        ),
    }
