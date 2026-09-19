from __future__ import annotations

from datetime import datetime
import json
import math
import os
from pathlib import Path
import statistics
from typing import Any

from config.settings import (
    ENABLE_SETUP_HISTORICAL_OPTIMIZER,
    SETUP_HISTORICAL_OPTIMIZER_HIGH_CONFIDENCE_SAMPLE,
    SETUP_HISTORICAL_OPTIMIZER_MIN_COVERAGE,
    SETUP_HISTORICAL_OPTIMIZER_MIN_DECISIVE_SAMPLE,
    SETUP_HISTORICAL_OPTIMIZER_MIN_PATH_SAMPLE,
)


# ============================================================
# SETUP HISTORICAL OPTIMIZER V1
#
# OBSERVATION / DISPLAY ONLY.
#
# This module:
# - cannot execute
# - cannot block or allow execution
# - cannot modify the setup score
# - cannot modify risk / lot
# - cannot modify entry / SL / TP
#
# Live source of truth:
# data/accounts/<account>/setup_outcomes.json
#
# Google Sheets mirrors the same setup-outcome history and remains
# an external audit / validation surface. The live trading loop does
# not depend on synchronous Google Sheets reads.
# ============================================================


_OPTIMIZER_CACHE: dict[tuple[str, int, int], list[dict[str, Any]]] = {}


def _authority_fields() -> dict[str, Any]:
    return {
        "decision_impact": "DISPLAY_ONLY",
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_score": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
    }


def _safe_float(value) -> float | None:
    try:
        value = float(value)
    except Exception:
        return None

    if not math.isfinite(value):
        return None

    return value


def _safe_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value

    if value is None:
        return None

    text = str(value).strip().lower()

    if text in {"true", "1", "yes", "y"}:
        return True

    if text in {"false", "0", "no", "n"}:
        return False

    return None


def _upper(value) -> str:
    return str(value or "").strip().upper()


def _text(value) -> str:
    return str(value or "").strip()


def _flatten(payload) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [
            item
            for item in payload
            if isinstance(item, dict)
        ]

    if isinstance(payload, dict):
        for key in (
            "records",
            "items",
            "outcomes",
            "setup_outcomes",
            "setups",
        ):
            value = payload.get(key)

            if isinstance(value, list):
                return [
                    item
                    for item in value
                    if isinstance(item, dict)
                ]

        if payload and all(
            isinstance(value, dict)
            for value in payload.values()
        ):
            return list(payload.values())

    return []


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_account_dir(
    data: dict[str, Any],
) -> Path | None:
    explicit = (
        data.get(
            "setup_historical_optimizer_account_dir"
        )
        or os.getenv(
            "SETUP_HISTORICAL_OPTIMIZER_ACCOUNT_DIR"
        )
    )

    if explicit:
        path = Path(explicit)

        if not path.is_absolute():
            path = (
                _repo_root()
                / path
            )

        if (
            path.is_dir()
            and (
                path
                / "setup_outcomes.json"
            ).exists()
        ):
            return path

    base = (
        _repo_root()
        / "data"
        / "accounts"
    )

    if not base.exists():
        return None

    candidates = [
        path
        for path in base.iterdir()
        if path.is_dir()
        and (
            path
            / "setup_outcomes.json"
        ).exists()
    ]

    hints = []

    for key in (
        "account",
        "account_id",
        "account_login",
        "login",
        "mt5_login",
        "account_key",
    ):
        value = data.get(key)

        if value not in (
            None,
            "",
        ):
            hints.append(
                str(value)
                .strip()
                .lower()
            )

    if hints:
        matched = []

        for path in candidates:
            name = path.name.lower()

            if any(
                hint == name
                or hint in name
                or name in hint
                for hint in hints
            ):
                matched.append(
                    path
                )

        if len(matched) == 1:
            return matched[0]

    if len(candidates) == 1:
        return candidates[0]

    return None


def _load_outcomes(
    account_dir: Path,
) -> list[dict[str, Any]] | None:
    path = (
        account_dir
        / "setup_outcomes.json"
    )

    try:
        stat = path.stat()
    except Exception:
        return None

    cache_key = (
        str(path),
        stat.st_mtime_ns,
        stat.st_size,
    )

    cached = _OPTIMIZER_CACHE.get(
        cache_key
    )

    if cached is not None:
        return cached

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )
        rows = _flatten(
            payload
        )
    except Exception:
        return None

    for key in list(
        _OPTIMIZER_CACHE
    ):
        if (
            key[0] == str(path)
            and key != cache_key
        ):
            _OPTIMIZER_CACHE.pop(
                key,
                None,
            )

    _OPTIMIZER_CACHE[
        cache_key
    ] = rows

    return rows


def _setup_id(
    row: dict[str, Any],
) -> str:
    return _text(
        row.get(
            "setup_id"
        )
    )


def _strategy(
    row: dict[str, Any],
) -> str:
    return _upper(
        row.get(
            "strategy"
        )
    )


def _signal(
    row: dict[str, Any],
) -> str:
    return _upper(
        row.get(
            "signal"
        )
    )


def _entry_model(
    row: dict[str, Any],
) -> str:
    return _upper(
        row.get(
            "entry_model"
        )
    )


def _session(
    row: dict[str, Any],
) -> str:
    return _upper(
        row.get(
            "session"
        )
    )


def _market_condition(
    row: dict[str, Any],
) -> str:
    return _upper(
        row.get(
            "market_condition"
        )
    )


def _scenario_key(
    row: dict[str, Any],
) -> str:
    return _text(
        row.get(
            "scenario_key"
        )
    )


def _context_key(
    row: dict[str, Any],
) -> str:
    return _text(
        row.get(
            "context_key"
        )
    )


def _row_created_at(
    row: dict[str, Any],
) -> str:
    return _text(
        row.get(
            "created_at"
        )
    )


def _current_reference_time(
    data: dict[str, Any],
) -> tuple[str, str]:
    for key in (
        "created_at",
        "setup_created_at",
        "timestamp",
    ):
        value = data.get(key)

        if value not in (
            None,
            "",
        ):
            return (
                str(value),
                "SETUP_CREATED_AT",
            )

    return (
        datetime.now().isoformat(),
        "LIVE_NOW",
    )


def _is_completed(
    row: dict[str, Any],
) -> bool:
    # Historical optimizer cohorts must contain mature observations.
    #
    # The tracker can populate first_hit/final_outcome/path flags while
    # a setup is still TRACKING. Those fields are useful live state,
    # but MAE/MFE/recovery and eventual path are still evolving.
    #
    # Therefore only terminal tracker statuses are eligible for
    # historical optimizer statistics.
    status = _upper(
        row.get(
            "status"
        )
    )

    return status in {
        "CLOSED",
        "EXPIRED",
    }


def _rr_value(
    row: dict[str, Any],
) -> float | None:
    for key in (
        "rr",
        "rejected_rr_value",
        "full_rr",
        "risk_reward",
        "risk_reward_ratio",
    ):
        value = _safe_float(
            row.get(key)
        )

        if value is not None:
            return value

    extra = row.get(
        "extra"
    )

    if isinstance(
        extra,
        dict,
    ):
        value = _safe_float(
            extra.get(
                "rr"
            )
        )

        if value is not None:
            return value

    entry = (
        _safe_float(
            row.get(
                "entry"
            )
        )
        or _safe_float(
            row.get(
                "entry_price"
            )
        )
    )
    sl = (
        _safe_float(
            row.get(
                "sl"
            )
        )
        or _safe_float(
            row.get(
                "stop_loss"
            )
        )
    )
    tp = (
        _safe_float(
            row.get(
                "tp"
            )
        )
        or _safe_float(
            row.get(
                "take_profit"
            )
        )
    )

    if (
        entry is None
        or sl is None
        or tp is None
    ):
        return None

    risk = abs(
        entry - sl
    )

    if risk <= 0:
        return None

    return abs(
        tp - entry
    ) / risk


def rr_bucket(
    rr: float | None,
) -> str:
    if rr is None:
        return "RR_UNKNOWN"

    if rr < 1.00:
        return "RR_LT_1_00"

    if rr < 1.20:
        return "RR_1_00_1_19"

    if rr < 1.50:
        return "RR_1_20_1_49"

    if rr < 2.00:
        return "RR_1_50_1_99"

    return "RR_GE_2_00"


def _row_rr_bucket(
    row: dict[str, Any],
) -> str:
    return rr_bucket(
        _rr_value(
            row
        )
    )


def _completion_time(
    row: dict[str, Any],
) -> str:
    # Return a trustworthy persisted timestamp proving that the
    # terminal outcome was knowable. Strict historical replay must
    # not use a setup merely because it was created before the
    # current setup; its terminal result must also have been known.
    for key in (
        "completed_at",
        "closed_at",
        "resolved_at",
        "updated_at",
    ):
        value = _text(
            row.get(
                key
            )
        )

        if value:
            return value

    # For expired observations, expires_at is a conservative upper
    # bound for when the terminal expired record is knowable.
    if (
        _upper(
            row.get(
                "status"
            )
        )
        == "EXPIRED"
    ):
        return _text(
            row.get(
                "expires_at"
            )
        )

    return ""


def _historical_row(
    row: dict[str, Any],
    *,
    current_setup_id: str,
    reference_time: str,
    strict_reference_time: bool,
) -> bool:
    if not _is_completed(
        row
    ):
        return False

    if (
        current_setup_id
        and _setup_id(row)
        == current_setup_id
    ):
        return False

    # LIVE_NOW mode reads the persisted file as it exists now.
    # Any row already terminal in the file is currently-known
    # history. Avoid naive timestamp/timezone assumptions here.
    if not strict_reference_time:
        return True

    created_at = (
        _row_created_at(
            row
        )
    )

    if (
        not created_at
        or created_at
        >= reference_time
    ):
        return False

    completion_time = (
        _completion_time(
            row
        )
    )

    # Strict replay fails closed on unknown terminal timing. This
    # reduces sample size rather than leaking a future outcome.
    if (
        not completion_time
        or completion_time
        >= reference_time
    ):
        return False

    return True


def _outcome_class(
    row: dict[str, Any],
) -> str:
    first_hit = _upper(
        row.get(
            "first_hit"
        )
    )

    if first_hit == "TP_TOUCH":
        return "WIN"

    if first_hit == "SL_TOUCH":
        return "LOSS"

    # W10 is positive-path evidence but not treated as a TP win.
    if first_hit == "W10":
        return "W10_ONLY"

    hit_tp = _safe_bool(
        row.get(
            "hit_tp"
        )
    )
    hit_sl = _safe_bool(
        row.get(
            "hit_sl"
        )
    )

    if (
        hit_tp is True
        and hit_sl is True
    ):
        # Ordering is unknown. Do not silently label this a win/loss.
        return "AMBIGUOUS"

    if (
        hit_tp is True
        and hit_sl is not True
    ):
        return "WIN"

    if (
        hit_sl is True
        and hit_tp is not True
    ):
        return "LOSS"

    final_outcome = _upper(
        row.get(
            "final_outcome"
        )
    )

    if final_outcome == "TP_TOUCH":
        return "WIN"

    if final_outcome == "SL_TOUCH":
        return "LOSS"

    if final_outcome == "W10":
        return "W10_ONLY"

    if final_outcome == "BREAKEVEN":
        return "BE"

    return "UNRESOLVED"


def _percentile(
    values: list[float],
    q: float,
) -> float | None:
    values = sorted(
        values
    )

    if not values:
        return None

    if len(values) == 1:
        return values[0]

    position = (
        (len(values) - 1)
        * q
    )
    low = int(
        math.floor(
            position
        )
    )
    high = int(
        math.ceil(
            position
        )
    )

    if low == high:
        return values[low]

    fraction = (
        position
        - low
    )

    return (
        values[low]
        * (1.0 - fraction)
        + values[high]
        * fraction
    )


def _distribution(
    rows: list[dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    values = []

    for row in rows:
        value = _safe_float(
            row.get(field)
        )

        if value is not None:
            values.append(
                abs(value)
            )

    return {
        "count": len(values),
        "median": (
            statistics.median(
                values
            )
            if values
            else None
        ),
        "p75": (
            _percentile(
                values,
                0.75,
            )
            if values
            else None
        ),
    }


def _wilson_interval(
    wins: int,
    total: int,
    z: float = 1.959963984540054,
) -> tuple[float | None, float | None]:
    if total <= 0:
        return (
            None,
            None,
        )

    p = wins / total
    z2 = z * z
    denominator = (
        1.0
        + z2 / total
    )
    center = (
        p
        + z2 / (
            2.0 * total
        )
    ) / denominator
    margin = (
        z
        * math.sqrt(
            (
                p
                * (1.0 - p)
                / total
            )
            + (
                z2
                / (
                    4.0
                    * total
                    * total
                )
            )
        )
        / denominator
    )

    return (
        max(
            0.0,
            center - margin,
        ),
        min(
            1.0,
            center + margin,
        ),
    )


def _stats(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    classes = {
        "WIN": 0,
        "LOSS": 0,
        "AMBIGUOUS": 0,
        "W10_ONLY": 0,
        "BE": 0,
        "UNRESOLVED": 0,
    }

    for row in rows:
        classification = (
            _outcome_class(
                row
            )
        )

        classes[
            classification
        ] = (
            classes.get(
                classification,
                0,
            )
            + 1
        )

    wins = classes[
        "WIN"
    ]
    losses = classes[
        "LOSS"
    ]
    decisive = (
        wins
        + losses
    )

    win_rate = (
        wins / decisive
        if decisive
        else None
    )

    wilson_low, wilson_high = (
        _wilson_interval(
            wins,
            decisive,
        )
    )

    hit_plus_10_known = 0
    hit_plus_10_true = 0

    for row in rows:
        value = _safe_bool(
            row.get(
                "hit_plus_10"
            )
        )

        if value is None:
            continue

        hit_plus_10_known += 1

        if value:
            hit_plus_10_true += 1

    hit_plus_10_rate = (
        hit_plus_10_true
        / hit_plus_10_known
        if hit_plus_10_known
        else None
    )

    total = len(
        rows
    )
    ambiguous = classes[
        "AMBIGUOUS"
    ]

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "decisive": decisive,
        "win_rate": win_rate,
        "win_wilson_low": wilson_low,
        "win_wilson_high": wilson_high,
        "ambiguous": ambiguous,
        "ambiguous_rate": (
            ambiguous / total
            if total
            else None
        ),
        "breakeven": classes[
            "BE"
        ],
        "w10_only": classes[
            "W10_ONLY"
        ],
        "unresolved": classes[
            "UNRESOLVED"
        ],
        "outcome_coverage": (
            decisive / total
            if total
            else None
        ),
        "hit_plus_10_known": (
            hit_plus_10_known
        ),
        "hit_plus_10_true": (
            hit_plus_10_true
        ),
        "hit_plus_10_rate": (
            hit_plus_10_rate
        ),
        "hit_plus_10_coverage": (
            hit_plus_10_known
            / total
            if total
            else None
        ),
        "max_favorable_usd": (
            _distribution(
                rows,
                "max_favorable_usd",
            )
        ),
        "max_adverse_usd": (
            _distribution(
                rows,
                "max_adverse_usd",
            )
        ),
        "max_recovery_swing_usd": (
            _distribution(
                rows,
                "max_recovery_swing_usd",
            )
        ),
    }


def _current_features(
    data: dict[str, Any],
) -> dict[str, str]:
    return {
        "strategy": _strategy(
            data
        ),
        "signal": _signal(
            data
        ),
        "entry_model": _entry_model(
            data
        ),
        "session": _session(
            data
        ),
        "market_condition": (
            _market_condition(
                data
            )
        ),
        "scenario_key": (
            _scenario_key(
                data
            )
        ),
        "context_key": (
            _context_key(
                data
            )
        ),
        "rr_bucket": (
            rr_bucket(
                _rr_value(
                    data
                )
            )
        ),
    }


def _row_feature(
    row: dict[str, Any],
    key: str,
) -> str:
    if key == "strategy":
        return _strategy(
            row
        )

    if key == "signal":
        return _signal(
            row
        )

    if key == "entry_model":
        return _entry_model(
            row
        )

    if key == "session":
        return _session(
            row
        )

    if key == "market_condition":
        return _market_condition(
            row
        )

    if key == "scenario_key":
        return _scenario_key(
            row
        )

    if key == "context_key":
        return _context_key(
            row
        )

    if key == "rr_bucket":
        return _row_rr_bucket(
            row
        )

    return _text(
        row.get(key)
    )


def _cohort_specs(
    features: dict[str, str],
) -> list[tuple[str, tuple[str, ...]]]:
    specs = []

    if features.get(
        "scenario_key"
    ):
        specs.append(
            (
                "SCENARIO_RR",
                (
                    "strategy",
                    "signal",
                    "scenario_key",
                    "rr_bucket",
                ),
            )
        )

    if features.get(
        "context_key"
    ):
        specs.append(
            (
                "CONTEXT_RR",
                (
                    "strategy",
                    "signal",
                    "context_key",
                    "rr_bucket",
                ),
            )
        )

    specs.extend(
        [
            (
                "MODEL_SESSION_REGIME_RR",
                (
                    "strategy",
                    "signal",
                    "entry_model",
                    "session",
                    "market_condition",
                    "rr_bucket",
                ),
            ),
            (
                "MODEL_SESSION_RR",
                (
                    "strategy",
                    "signal",
                    "entry_model",
                    "session",
                    "rr_bucket",
                ),
            ),
            (
                "MODEL_RR",
                (
                    "strategy",
                    "signal",
                    "entry_model",
                    "rr_bucket",
                ),
            ),
            (
                "SIGNAL_RR",
                (
                    "strategy",
                    "signal",
                    "rr_bucket",
                ),
            ),
            (
                "STRATEGY_RR",
                (
                    "strategy",
                    "rr_bucket",
                ),
            ),
            (
                "MODEL_SESSION",
                (
                    "strategy",
                    "signal",
                    "entry_model",
                    "session",
                ),
            ),
            (
                "SIGNAL",
                (
                    "strategy",
                    "signal",
                ),
            ),
            (
                "STRATEGY",
                (
                    "strategy",
                ),
            ),
        ]
    )

    output = []

    for name, keys in specs:
        if all(
            features.get(
                key
            )
            not in {
                "",
                "RR_UNKNOWN",
            }
            for key in keys
        ):
            output.append(
                (
                    name,
                    keys,
                )
            )

    # Always retain strategy-only fallback when strategy is available.
    if (
        features.get(
            "strategy"
        )
        and not any(
            name == "STRATEGY"
            for name, _ in output
        )
    ):
        output.append(
            (
                "STRATEGY",
                (
                    "strategy",
                ),
            )
        )

    return output


def _match_cohort(
    rows: list[dict[str, Any]],
    *,
    features: dict[str, str],
    keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    output = []

    for row in rows:
        if all(
            _row_feature(
                row,
                key,
            )
            == features.get(
                key,
                "",
            )
            for key in keys
        ):
            output.append(
                row
            )

    return output


def _select_cohort(
    rows: list[dict[str, Any]],
    features: dict[str, str],
) -> tuple[
    str,
    tuple[str, ...],
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
]:
    specs = _cohort_specs(
        features
    )

    evaluated = []
    best_fallback = None

    for priority, (
        name,
        keys,
    ) in enumerate(
        specs
    ):
        matched = (
            _match_cohort(
                rows,
                features=features,
                keys=keys,
            )
        )
        stats = _stats(
            matched
        )

        evaluated.append(
            {
                "name": name,
                "keys": list(
                    keys
                ),
                "total": stats[
                    "total"
                ],
                "decisive": stats[
                    "decisive"
                ],
                "hit_plus_10_known": (
                    stats[
                        "hit_plus_10_known"
                    ]
                ),
            }
        )

        if (
            stats["decisive"]
            >= SETUP_HISTORICAL_OPTIMIZER_MIN_DECISIVE_SAMPLE
        ):
            return (
                name,
                keys,
                matched,
                stats,
                evaluated,
            )

        fallback_rank = (
            stats[
                "decisive"
            ],
            stats[
                "hit_plus_10_known"
            ],
            stats[
                "total"
            ],
            -priority,
        )

        if (
            best_fallback is None
            or fallback_rank
            > best_fallback[0]
        ):
            best_fallback = (
                fallback_rank,
                name,
                keys,
                matched,
                stats,
            )

    if best_fallback is None:
        return (
            "NO_COHORT",
            tuple(),
            [],
            _stats(
                []
            ),
            evaluated,
        )

    return (
        best_fallback[1],
        best_fallback[2],
        best_fallback[3],
        best_fallback[4],
        evaluated,
    )


def _rr_peer_stats(
    rows: list[dict[str, Any]],
    features: dict[str, str],
) -> dict[str, Any]:
    rr_name = (
        features.get(
            "rr_bucket"
        )
    )

    if (
        not rr_name
        or rr_name == "RR_UNKNOWN"
    ):
        return {
            "available": False,
            "cohort": "RR_UNKNOWN",
        }

    keys = (
        "strategy",
        "signal",
        "rr_bucket",
    )

    if not all(
        features.get(
            key
        )
        for key in keys
    ):
        keys = (
            "strategy",
            "rr_bucket",
        )

    matched = _match_cohort(
        rows,
        features=features,
        keys=keys,
    )
    stats = _stats(
        matched
    )

    return {
        "available": bool(
            matched
        ),
        "cohort": "+".join(
            key.upper()
            for key in keys
        ),
        "sample": stats[
            "total"
        ],
        "decisive": stats[
            "decisive"
        ],
        "win_rate": stats[
            "win_rate"
        ],
        "hit_plus_10_known": (
            stats[
                "hit_plus_10_known"
            ]
        ),
        "hit_plus_10_rate": (
            stats[
                "hit_plus_10_rate"
            ]
        ),
    }


def _confidence(
    stats: dict[str, Any],
) -> str:
    decisive = int(
        stats.get(
            "decisive",
            0,
        )
        or 0
    )

    if (
        decisive
        >= SETUP_HISTORICAL_OPTIMIZER_HIGH_CONFIDENCE_SAMPLE
    ):
        return "HIGH"

    if (
        decisive
        >= SETUP_HISTORICAL_OPTIMIZER_MIN_DECISIVE_SAMPLE
    ):
        return "MEDIUM"

    if decisive >= 10:
        return "LOW"

    return "INSUFFICIENT"


def _data_quality(
    stats: dict[str, Any],
) -> str:
    decisive = int(
        stats.get(
            "decisive",
            0,
        )
        or 0
    )
    coverage = (
        _safe_float(
            stats.get(
                "outcome_coverage"
            )
        )
    )
    hit_coverage = (
        _safe_float(
            stats.get(
                "hit_plus_10_coverage"
            )
        )
    )
    ambiguous_rate = (
        _safe_float(
            stats.get(
                "ambiguous_rate"
            )
        )
    )

    if (
        decisive
        < SETUP_HISTORICAL_OPTIMIZER_MIN_DECISIVE_SAMPLE
    ):
        return "INSUFFICIENT_SAMPLE"

    if (
        ambiguous_rate is not None
        and ambiguous_rate > 0.10
    ):
        return "ORDERING_CONFLICT"

    if (
        coverage is None
        or coverage
        < SETUP_HISTORICAL_OPTIMIZER_MIN_COVERAGE
        or hit_coverage is None
        or hit_coverage
        < SETUP_HISTORICAL_OPTIMIZER_MIN_COVERAGE
    ):
        return "PARTIAL_COVERAGE"

    return "GOOD"


def _evidence_conflict(
    stats: dict[str, Any],
) -> bool:
    win_rate = (
        _safe_float(
            stats.get(
                "win_rate"
            )
        )
    )
    hit_rate = (
        _safe_float(
            stats.get(
                "hit_plus_10_rate"
            )
        )
    )

    if (
        win_rate is None
        or hit_rate is None
    ):
        return False

    return bool(
        (
            win_rate >= 0.65
            and hit_rate <= 0.45
        )
        or (
            win_rate <= 0.45
            and hit_rate >= 0.65
        )
    )


def _upgrade_guidance(
    *,
    stats: dict[str, Any],
    features: dict[str, str],
    selected_cohort: str,
    evaluated: list[dict[str, Any]],
) -> list[str]:
    guidance = []

    decisive = int(
        stats.get(
            "decisive",
            0,
        )
        or 0
    )

    if (
        decisive
        < SETUP_HISTORICAL_OPTIMIZER_MIN_DECISIVE_SAMPLE
    ):
        guidance.append(
            "Need "
            f"{SETUP_HISTORICAL_OPTIMIZER_MIN_DECISIVE_SAMPLE - decisive} "
            "more decisive TP-first/SL-first peer outcomes"
        )

    hit_known = int(
        stats.get(
            "hit_plus_10_known",
            0,
        )
        or 0
    )

    if (
        hit_known
        < SETUP_HISTORICAL_OPTIMIZER_MIN_PATH_SAMPLE
    ):
        guidance.append(
            "Need "
            f"{SETUP_HISTORICAL_OPTIMIZER_MIN_PATH_SAMPLE - hit_known} "
            "more peers with measured hit_plus_10/path data"
        )

    ambiguous_rate = (
        _safe_float(
            stats.get(
                "ambiguous_rate"
            )
        )
    )

    if (
        ambiguous_rate is not None
        and ambiguous_rate > 0.10
    ):
        guidance.append(
            "Improve first_hit ordering coverage; too many TP+SL rows are ambiguous"
        )

    outcome_coverage = (
        _safe_float(
            stats.get(
                "outcome_coverage"
            )
        )
    )

    if (
        outcome_coverage is not None
        and outcome_coverage
        < SETUP_HISTORICAL_OPTIMIZER_MIN_COVERAGE
    ):
        guidance.append(
            "Increase completed decisive outcome coverage for this cohort"
        )

    if (
        features.get(
            "market_condition"
        )
        in {
            "",
            "PENDING",
            "INTRABAR_PENDING",
            "UNKNOWN",
        }
    ):
        guidance.append(
            "Persist resolved market regime at setup detection"
        )

    if (
        features.get(
            "rr_bucket"
        )
        == "RR_UNKNOWN"
    ):
        guidance.append(
            "Persist planned RR / RR bucket on every setup"
        )

    if not features.get(
        "scenario_key"
    ):
        guidance.append(
            "Persist scenario_key consistently for finer cohort statistics"
        )

    if not features.get(
        "context_key"
    ):
        guidance.append(
            "Persist context_key consistently for finer cohort statistics"
        )

    if (
        _evidence_conflict(
            stats
        )
    ):
        guidance.append(
            "Historical TP-first and +$10 evidence conflict; collect more peers before optimization authority"
        )

    if (
        selected_cohort
        in {
            "SIGNAL",
            "STRATEGY",
            "NO_COHORT",
        }
        and evaluated
    ):
        guidance.append(
            "Specific cohort is sparse; current statistics use a broader fallback"
        )

    return guidance[:5]


def build_setup_historical_optimizer_snapshot(
    data: dict[str, Any],
    *,
    enabled_override: bool | None = None,
) -> dict[str, Any]:
    data = dict(
        data or {}
    )

    enabled = (
        ENABLE_SETUP_HISTORICAL_OPTIMIZER
        if enabled_override is None
        else bool(
            enabled_override
        )
    )

    base = {
        "version": "V1",
        "enabled": enabled,
        **_authority_fields(),
    }

    if not enabled:
        return {
            **base,
            "available": False,
            "reason": "optimizer_disabled",
        }

    features = _current_features(
        data
    )

    if (
        not features[
            "strategy"
        ]
        or features[
            "signal"
        ]
        not in {
            "BUY",
            "SELL",
        }
    ):
        return {
            **base,
            "available": False,
            "reason": "missing_strategy_or_signal",
            "features": features,
        }

    account_dir = (
        _resolve_account_dir(
            data
        )
    )

    if account_dir is None:
        return {
            **base,
            "available": False,
            "reason": "account_history_unresolved",
            "features": features,
        }

    rows = _load_outcomes(
        account_dir
    )

    if rows is None:
        return {
            **base,
            "available": False,
            "reason": "setup_outcomes_read_failed",
            "features": features,
        }

    reference_time, time_mode = (
        _current_reference_time(
            data
        )
    )
    current_setup_id = (
        _setup_id(
            data
        )
    )
    strict_time = (
        time_mode
        == "SETUP_CREATED_AT"
    )

    historical = [
        row
        for row in rows
        if _historical_row(
            row,
            current_setup_id=current_setup_id,
            reference_time=reference_time,
            strict_reference_time=strict_time,
        )
    ]

    (
        cohort_name,
        cohort_keys,
        cohort_rows,
        cohort_stats,
        evaluated,
    ) = _select_cohort(
        historical,
        features,
    )

    rr_peers = (
        _rr_peer_stats(
            historical,
            features,
        )
    )

    quality = _data_quality(
        cohort_stats
    )
    confidence = _confidence(
        cohort_stats
    )
    conflict = (
        _evidence_conflict(
            cohort_stats
        )
    )

    guidance = (
        _upgrade_guidance(
            stats=cohort_stats,
            features=features,
            selected_cohort=cohort_name,
            evaluated=evaluated,
        )
    )

    return {
        **base,
        "available": True,
        "reason": "historical_optimizer_ready",
        "source": (
            str(
                account_dir.name
            )
        ),
        "history_source": "setup_outcomes.json",
        "reference_time": reference_time,
        "time_filter_mode": time_mode,
        "features": features,
        "cohort": {
            "name": cohort_name,
            "keys": list(
                cohort_keys
            ),
            "sample": len(
                cohort_rows
            ),
        },
        "stats": cohort_stats,
        "rr_peer_stats": rr_peers,
        "confidence": confidence,
        "data_quality": quality,
        "evidence_conflict": conflict,
        "upgrade_guidance": guidance,
        "cohort_fallback_trace": evaluated,
    }


def _pct(
    value,
) -> str:
    value = _safe_float(
        value
    )

    if value is None:
        return "N/A"

    return (
        f"{value * 100:.1f}%"
    )


def _usd(
    value,
) -> str:
    value = _safe_float(
        value
    )

    if value is None:
        return "N/A"

    return f"${value:.2f}"


def format_setup_historical_optimizer_block(
    snapshot: dict[str, Any],
) -> str:
    snapshot = dict(
        snapshot or {}
    )

    if (
        not snapshot.get(
            "enabled"
        )
        or not snapshot.get(
            "available"
        )
    ):
        return ""

    stats = dict(
        snapshot.get(
            "stats",
            {}
        )
        or {}
    )
    cohort = dict(
        snapshot.get(
            "cohort",
            {}
        )
        or {}
    )
    features = dict(
        snapshot.get(
            "features",
            {}
        )
        or {}
    )
    rr_peers = dict(
        snapshot.get(
            "rr_peer_stats",
            {}
        )
        or {}
    )

    decisive = int(
        stats.get(
            "decisive",
            0,
        )
        or 0
    )
    wins = int(
        stats.get(
            "wins",
            0,
        )
        or 0
    )
    losses = int(
        stats.get(
            "losses",
            0,
        )
        or 0
    )

    lines = [
        "HISTORICAL OPTIMIZER [OBSERVE ONLY]",
        (
            "Cohort: "
            f"{cohort.get('name', 'N/A')} "
            f"| total={cohort.get('sample', 0)} "
            f"| decisive={decisive}"
        ),
        (
            "Historical Win: "
            f"{_pct(stats.get('win_rate'))} "
            f"({wins}W/{losses}L)"
        ),
        (
            "Wilson 95%: "
            f"{_pct(stats.get('win_wilson_low'))}"
            "-"
            f"{_pct(stats.get('win_wilson_high'))}"
        ),
        (
            "Hit +$10: "
            f"{_pct(stats.get('hit_plus_10_rate'))} "
            f"(n={stats.get('hit_plus_10_known', 0)})"
        ),
        (
            "RR Bucket: "
            f"{features.get('rr_bucket', 'RR_UNKNOWN')}"
        ),
    ]

    if rr_peers.get(
        "available"
    ):
        lines.append(
            "RR Peers: "
            f"Win {_pct(rr_peers.get('win_rate'))} "
            f"(decisive={rr_peers.get('decisive', 0)}) "
            f"| +$10 {_pct(rr_peers.get('hit_plus_10_rate'))} "
            f"(n={rr_peers.get('hit_plus_10_known', 0)})"
        )

    favorable = dict(
        stats.get(
            "max_favorable_usd",
            {}
        )
        or {}
    )
    adverse = dict(
        stats.get(
            "max_adverse_usd",
            {}
        )
        or {}
    )
    recovery = dict(
        stats.get(
            "max_recovery_swing_usd",
            {}
        )
        or {}
    )

    lines.append(
        "Path: "
        f"MFE med {_usd(favorable.get('median'))} "
        f"| MAE med {_usd(adverse.get('median'))} "
        f"/ P75 {_usd(adverse.get('p75'))} "
        f"| Recovery med {_usd(recovery.get('median'))}"
    )

    lines.append(
        "Confidence: "
        f"{snapshot.get('confidence', 'N/A')} "
        f"| Data: {snapshot.get('data_quality', 'N/A')}"
    )

    guidance = list(
        snapshot.get(
            "upgrade_guidance",
            []
        )
        or []
    )

    if guidance:
        lines.append(
            "Upgrade: "
            + " | ".join(
                guidance[:2]
            )
        )

    return "\n".join(
        lines
    )


def build_setup_historical_optimizer_block(
    data: dict[str, Any],
) -> str:
    try:
        snapshot = (
            build_setup_historical_optimizer_snapshot(
                data
            )
        )

        return (
            format_setup_historical_optimizer_block(
                snapshot
            )
        )
    except Exception:
        # Fail-open by design. Optimizer display must never break alerts.
        return ""
