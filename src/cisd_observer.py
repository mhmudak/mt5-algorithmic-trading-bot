from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Iterable


CISD_OBSERVER_VERSION = "V1.7"
DEFAULT_TIMEFRAME = "M1"
DEFAULT_BARS = 16

CISD_REQUIRED = "CISD_REQUIRED"
CISD_ON_RETEST = "CISD_ON_RETEST"
CISD_OPTIONAL = "CISD_OPTIONAL"
NO_CISD = "NO_CISD"

_FETCH_CACHE: dict[
    tuple[str, str, int, int],
    dict[str, Any],
] = {}


@dataclass(frozen=True)
class CisdEvent:
    signal: str
    timeframe: str
    reference_candle_time: int
    reference_open: float
    confirmation_candle_time: int
    confirmation_open: float
    confirmation_close: float


def _upper(value: Any) -> str:
    return str(
        value
        or ""
    ).strip().upper()


def _as_float(
    value: Any,
) -> float | None:
    try:
        return float(
            value
        )
    except Exception:
        return None


def _as_int(
    value: Any,
) -> int | None:
    try:
        return int(
            value
        )
    except Exception:
        return None


def _normalise_rates(
    rates: Iterable[Any] | None,
) -> list[dict[str, float | int]]:
    rows: list[
        dict[str, float | int]
    ] = []

    if rates is None:
        return rows

    for raw in rates:
        try:
            if isinstance(
                raw,
                dict,
            ):
                get_value = raw.get
            else:
                names = getattr(
                    getattr(
                        raw,
                        "dtype",
                        None,
                    ),
                    "names",
                    None,
                )

                if names:
                    get_value = (
                        lambda key, r=raw: (
                            r[key]
                            if key in names
                            else None
                        )
                    )
                else:
                    get_value = (
                        lambda key, r=raw: getattr(
                            r,
                            key,
                            None,
                        )
                    )

            candle_time = _as_int(
                get_value(
                    "time"
                )
            )
            open_price = _as_float(
                get_value(
                    "open"
                )
            )
            close_price = _as_float(
                get_value(
                    "close"
                )
            )

            if (
                candle_time is None
                or open_price is None
                or close_price is None
            ):
                continue

            rows.append(
                {
                    "time": candle_time,
                    "open": open_price,
                    "close": close_price,
                }
            )
        except Exception:
            continue

    rows.sort(
        key=lambda row: int(
            row["time"]
        )
    )
    return rows


def detect_cisd_event(
    rates: Iterable[Any] | None,
    signal: str,
    *,
    after_bar_time: int | None,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> CisdEvent | None:
    """
    Closed-candle CISD observer.

    BUY:
      - identify the most recent bearish delivery candle before
        a later bullish closed candle;
      - CISD is observed when that later bullish candle closes
        above the bearish delivery candle's open.

    SELL:
      - identify the most recent bullish delivery candle before
        a later bearish closed candle;
      - CISD is observed when that later bearish candle closes
        below the bullish delivery candle's open.

    Only the confirmation candle must be newer than after_bar_time.
    This allows the delivery/reference candle to begin before the
    observer was armed while preventing pre-arm confirmation events
    from being counted.
    """

    direction = _upper(
        signal
    )

    if direction not in {
        "BUY",
        "SELL",
    }:
        return None

    rows = _normalise_rates(
        rates
    )

    if len(
        rows
    ) < 2:
        return None

    baseline = (
        int(
            after_bar_time
        )
        if after_bar_time
        is not None
        else -1
    )

    for index in range(
        1,
        len(
            rows
        ),
    ):
        confirm = rows[
            index
        ]

        confirm_time = int(
            confirm[
                "time"
            ]
        )

        if confirm_time <= baseline:
            continue

        confirm_open = float(
            confirm[
                "open"
            ]
        )
        confirm_close = float(
            confirm[
                "close"
            ]
        )

        reference = None

        for ref_index in range(
            index - 1,
            -1,
            -1,
        ):
            candidate = rows[
                ref_index
            ]
            candidate_open = float(
                candidate[
                    "open"
                ]
            )
            candidate_close = float(
                candidate[
                    "close"
                ]
            )

            if (
                direction == "BUY"
                and candidate_close
                < candidate_open
            ):
                reference = candidate
                break

            if (
                direction == "SELL"
                and candidate_close
                > candidate_open
            ):
                reference = candidate
                break

        if reference is None:
            continue

        reference_open = float(
            reference[
                "open"
            ]
        )

        if direction == "BUY":
            confirmed = (
                confirm_close
                > confirm_open
                and confirm_close
                > reference_open
            )
        else:
            confirmed = (
                confirm_close
                < confirm_open
                and confirm_close
                < reference_open
            )

        if not confirmed:
            continue

        return CisdEvent(
            signal=direction,
            timeframe=_upper(
                timeframe
            )
            or DEFAULT_TIMEFRAME,
            reference_candle_time=int(
                reference[
                    "time"
                ]
            ),
            reference_open=reference_open,
            confirmation_candle_time=confirm_time,
            confirmation_open=confirm_open,
            confirmation_close=confirm_close,
        )

    return None


def _timeframe_value(
    mt5,
    timeframe_name: str,
):
    key = _upper(
        timeframe_name
    )

    mapping = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
    }

    return mapping.get(
        key
    )


def fetch_closed_candles(
    symbol: str,
    *,
    timeframe: str = DEFAULT_TIMEFRAME,
    bars: int = DEFAULT_BARS,
) -> dict[str, Any]:
    """
    Fetch closed MT5 candles only.

    start_pos=1 intentionally excludes the live forming candle.
    A minute-bucket cache prevents repeated MT5 copy calls while
    setup_outcome_tracker runs every loop.
    """

    timeframe_key = (
        _upper(
            timeframe
        )
        or DEFAULT_TIMEFRAME
    )
    bars = max(
        6,
        int(
            bars
        ),
    )
    minute_bucket = int(
        time.time()
        // 60
    )
    cache_key = (
        str(
            symbol
        ),
        timeframe_key,
        bars,
        minute_bucket,
    )

    cached = _FETCH_CACHE.get(
        cache_key
    )

    if cached is not None:
        return {
            **cached,
            "cached": True,
        }

    result: dict[str, Any] = {
        "available": False,
        "timeframe": timeframe_key,
        "bars": [],
        "latest_closed_bar_time": None,
        "reason": None,
        "cached": False,
    }

    try:
        import MetaTrader5 as mt5

        timeframe_value = _timeframe_value(
            mt5,
            timeframe_key,
        )

        if timeframe_value is None:
            result[
                "reason"
            ] = "unsupported_timeframe"
            return result

        rates = mt5.copy_rates_from_pos(
            str(
                symbol
            ),
            timeframe_value,
            1,
            bars,
        )

        rows = _normalise_rates(
            rates
        )

        if len(
            rows
        ) < 2:
            result[
                "reason"
            ] = "closed_candles_unavailable"
            return result

        result[
            "available"
        ] = True
        result[
            "bars"
        ] = rows
        result[
            "latest_closed_bar_time"
        ] = int(
            rows[
                -1
            ][
                "time"
            ]
        )

    except Exception as exc:
        result[
            "reason"
        ] = (
            "cisd_fetch_error:"
            + exc.__class__.__name__
        )

    _FETCH_CACHE.clear()
    _FETCH_CACHE[
        cache_key
    ] = {
        **result,
        "cached": False,
    }

    return result


def _new_state(
    policy: str,
    timeframe: str,
) -> dict[str, Any]:
    return {
        "schema_version": CISD_OBSERVER_VERSION,
        "policy": policy,
        "timeframe": timeframe,
        "status": "NOT_EVALUATED",
        "armed": False,
        "armed_closed_bar_time": None,
        "confirmed": False,
        "confirmed_at_bar_time": None,
        "reference_candle_time": None,
        "reference_open": None,
        "confirmation_open": None,
        "confirmation_close": None,
        "qualification_satisfied": False,
        "shadow_entry_qualified": False,
        "shadow_entry_qualified_at": None,
        "last_observed_closed_bar_time": None,
        "last_reason": None,
        "decision_impact": "OBSERVE_ONLY",
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_score": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
        "can_modify_lot": False,
    }


def update_candidate_cisd_state(
    candidate: dict[str, Any],
    *,
    policy: str,
    signal: str,
    closed_snapshot: dict[str, Any] | None,
    observed_at: str | None = None,
) -> bool:
    policy_key = _upper(
        policy
    )

    if not policy_key:
        policy_key = "UNKNOWN"

    timeframe = _upper(
        (
            closed_snapshot
            or {}
        ).get(
            "timeframe"
        )
    ) or DEFAULT_TIMEFRAME

    state = candidate.get(
        "cisd_observer"
    )

    changed = False

    if not isinstance(
        state,
        dict,
    ):
        state = _new_state(
            policy_key,
            timeframe,
        )
        candidate[
            "cisd_observer"
        ] = state
        changed = True

    if state.get(
        "policy"
    ) != policy_key:
        state[
            "policy"
        ] = policy_key
        changed = True

    if policy_key == NO_CISD:
        desired = {
            "status": "NOT_REQUIRED",
            "confirmed": False,
            "qualification_satisfied": True,
        }

        for key, value in desired.items():
            if state.get(
                key
            ) != value:
                state[
                    key
                ] = value
                changed = True

        qualified = bool(
            candidate.get(
                "filled"
            )
        )

        if state.get(
            "shadow_entry_qualified"
        ) != qualified:
            state[
                "shadow_entry_qualified"
            ] = qualified
            changed = True

        if (
            qualified
            and not state.get(
                "shadow_entry_qualified_at"
            )
        ):
            state[
                "shadow_entry_qualified_at"
            ] = (
                observed_at
                or candidate.get(
                    "fill_at"
                )
            )
            changed = True

        return changed

    if policy_key == CISD_ON_RETEST:
        if not bool(
            candidate.get(
                "filled"
            )
        ):
            if state.get(
                "status"
            ) != "WAITING_FOR_RETEST":
                state[
                    "status"
                ] = "WAITING_FOR_RETEST"
                changed = True
            return changed

    snapshot = (
        closed_snapshot
        if isinstance(
            closed_snapshot,
            dict,
        )
        else {}
    )

    if not snapshot.get(
        "available"
    ):
        reason = (
            snapshot.get(
                "reason"
            )
            or "closed_candles_unavailable"
        )
        if state.get(
            "last_reason"
        ) != reason:
            state[
                "last_reason"
            ] = reason
            changed = True
        return changed

    latest_closed = _as_int(
        snapshot.get(
            "latest_closed_bar_time"
        )
    )

    if latest_closed is None:
        return changed

    if state.get(
        "last_observed_closed_bar_time"
    ) != latest_closed:
        state[
            "last_observed_closed_bar_time"
        ] = latest_closed
        changed = True

    if not bool(
        state.get(
            "armed"
        )
    ):
        state[
            "armed"
        ] = True
        state[
            "armed_closed_bar_time"
        ] = latest_closed

        if policy_key == CISD_OPTIONAL:
            state[
                "status"
            ] = "OPTIONAL_OBSERVING"
            state[
                "qualification_satisfied"
            ] = True
        elif policy_key == CISD_ON_RETEST:
            state[
                "status"
            ] = "WAITING_FOR_CISD_AFTER_RETEST"
        else:
            state[
                "status"
            ] = "WAITING_FOR_CISD"

        return True

    if bool(
        state.get(
            "confirmed"
        )
    ):
        qualified = (
            bool(
                candidate.get(
                    "filled"
                )
            )
            and bool(
                state.get(
                    "qualification_satisfied"
                )
            )
        )

        if (
            policy_key == CISD_OPTIONAL
            and candidate.get(
                "filled"
            )
        ):
            qualified = True

        if state.get(
            "shadow_entry_qualified"
        ) != qualified:
            state[
                "shadow_entry_qualified"
            ] = qualified
            changed = True

        if (
            qualified
            and not state.get(
                "shadow_entry_qualified_at"
            )
        ):
            state[
                "shadow_entry_qualified_at"
            ] = observed_at
            changed = True

        return changed

    event = detect_cisd_event(
        snapshot.get(
            "bars"
        ),
        signal,
        after_bar_time=_as_int(
            state.get(
                "armed_closed_bar_time"
            )
        ),
        timeframe=timeframe,
    )

    if event is None:
        return changed

    state[
        "confirmed"
    ] = True
    state[
        "confirmed_at_bar_time"
    ] = event.confirmation_candle_time
    state[
        "reference_candle_time"
    ] = event.reference_candle_time
    state[
        "reference_open"
    ] = event.reference_open
    state[
        "confirmation_open"
    ] = event.confirmation_open
    state[
        "confirmation_close"
    ] = event.confirmation_close
    state[
        "last_reason"
    ] = "closed_candle_cisd_confirmed"

    if policy_key == CISD_OPTIONAL:
        state[
            "status"
        ] = "OPTIONAL_CONFIRMED"
        state[
            "qualification_satisfied"
        ] = True
    else:
        state[
            "status"
        ] = "CONFIRMED"
        state[
            "qualification_satisfied"
        ] = True

    qualified = (
        bool(
            candidate.get(
                "filled"
            )
        )
        and bool(
            state.get(
                "qualification_satisfied"
            )
        )
    )

    if (
        policy_key == CISD_OPTIONAL
        and candidate.get(
            "filled"
        )
    ):
        qualified = True

    state[
        "shadow_entry_qualified"
    ] = qualified

    if qualified:
        state[
            "shadow_entry_qualified_at"
        ] = observed_at

    return True
