from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable

from config.settings import (
    BETTER_ENTRY_OPTIMIZER_MIN_HISTORICAL_SAMPLE,
    ENABLE_BETTER_ENTRY_OPTIMIZER,
)


BETTER_ENTRY_OPTIMIZER_VERSION = "V1"

CISD_REQUIRED = "CISD_REQUIRED"
CISD_ON_RETEST = "CISD_ON_RETEST"
CISD_OPTIONAL = "CISD_OPTIONAL"
NO_CISD = "NO_CISD"


# Human-reviewed from the repo-wide CISD entry-model audit.
# Specific entry-model rules override strategy defaults.
_STRATEGY_DEFAULT_POLICY: dict[str, str] = {
    "AMD_FVG": CISD_REQUIRED,
    "AUTO_STRUCTURAL_LEVEL_SCALP": CISD_OPTIONAL,
    "BALANCED_AUCTION_RANGE": CISD_REQUIRED,
    "BREAKER_BLOCK": CISD_ON_RETEST,
    "CRT_TBS": CISD_REQUIRED,
    "DAILY_LEVEL_LADDER_BREAKOUT": CISD_OPTIONAL,
    "EXTREME_SWEEP_RECLAIM": CISD_REQUIRED,
    "FAILED_BREAKOUT_REVERSAL": CISD_REQUIRED,
    "FAILED_FVG_REVERSAL": CISD_REQUIRED,
    "FAST": NO_CISD,
    "FCR_M1_FVG": CISD_ON_RETEST,
    "FLAG": CISD_OPTIONAL,
    "FLAG_REFINED": CISD_OPTIONAL,
    "FRACTAL_SWEEP": CISD_REQUIRED,
    "FVG": CISD_ON_RETEST,
    "FVG_CE_MITIGATION": CISD_ON_RETEST,
    "HEAD_SHOULDERS": CISD_ON_RETEST,
    "HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY": CISD_ON_RETEST,
    "HTF_FIB_CONFLUENCE": CISD_ON_RETEST,
    "HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY": CISD_OPTIONAL,
    "HTF_REJECTION_CANDLE_MTF_ENTRY": CISD_REQUIRED,
    "HTF_TREND_PULLBACK": CISD_ON_RETEST,
    "IFVG_RETEST_CONFLUENCE": CISD_ON_RETEST,
    "KEY_LEVEL_BREAK_HOLD": CISD_ON_RETEST,
    "LIQUIDITY_CANDLE": CISD_ON_RETEST,
    "LIQUIDITY_POOL_OB": CISD_REQUIRED,
    "LIQUIDITY_SWEEP": CISD_REQUIRED,
    "LIQUIDITY_TRAP": CISD_REQUIRED,
    "LVN_FVG_RECLAIM": CISD_ON_RETEST,
    "MICRO_SR_SWEEP_RECLAIM": CISD_REQUIRED,
    "MTF_OB_ENTRY": CISD_ON_RETEST,
    "MTF_SR_FVG_RECLAIM": CISD_ON_RETEST,
    "OB_FVG_COMBO": CISD_ON_RETEST,
    "ORB": CISD_ON_RETEST,
    "ORB_V00": CISD_ON_RETEST,
    "ORDER_BLOCK": CISD_ON_RETEST,
    "PRO_TRADER_REPLICATION": CISD_REQUIRED,
    "PSYCH_ROUND_NUMBER_REJECTION": CISD_REQUIRED,
    "RANGE_SWEEP_RECLAIM": CISD_REQUIRED,
    "RELIEF_RALLY": CISD_OPTIONAL,
    "SESSION_EXHAUSTION_REVERSAL": CISD_REQUIRED,
    "SESSION_ORB_RETEST": CISD_ON_RETEST,
    "SMT": CISD_REQUIRED,
    "SMT_PRO": CISD_REQUIRED,
    "SNIPER_V2": CISD_ON_RETEST,
    "STRICT": CISD_OPTIONAL,
    "STRUCTURE_LIQUIDITY": CISD_OPTIONAL,
    "SUPPLY_DEMAND_RETEST": CISD_ON_RETEST,
    "TRIANGLE_PENNANT": CISD_OPTIONAL,
    "VOLATILITY_COMPRESSION_BREAKOUT": CISD_OPTIONAL,
    "VWAP_RANGE_MEAN_REVERSION": CISD_REQUIRED,
    "VWAP_RECLAIM": CISD_REQUIRED,
    "WAVETREND_MOMENTUM": NO_CISD,
    "WAVETREND_PIVOT": CISD_OPTIONAL,
}

_ENTRY_MODEL_POLICY: dict[tuple[str, str], str] = {
    ("WAVETREND_PIVOT", "PIVOT_REJECTION_PRECISION"): CISD_REQUIRED,
    ("WAVETREND_PIVOT", "PIVOT_BREAKOUT_PRECISION"): CISD_OPTIONAL,
    ("HEAD_SHOULDERS", "HS_NECKLINE_RETEST"): CISD_ON_RETEST,
    ("HEAD_SHOULDERS", "INVERSE_HS_NECKLINE_RETEST"): CISD_ON_RETEST,
    ("HEAD_SHOULDERS", "HS_NECKLINE_BREAKOUT"): CISD_ON_RETEST,
    ("HEAD_SHOULDERS", "INVERSE_HS_NECKLINE_BREAKOUT"): CISD_ON_RETEST,
    ("SMT", "SMT_INTERNAL_DIVERGENCE_REVERSAL"): CISD_REQUIRED,
    ("SMT_PRO", "SMT_EXTERNAL_DIVERGENCE_REVERSAL"): CISD_REQUIRED,
    ("ORB", "UNKNOWN_ENTRY_MODEL"): CISD_ON_RETEST,
    ("ORB_V00", "UNKNOWN_ENTRY_MODEL"): CISD_ON_RETEST,
}


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None

    if not math.isfinite(number):
        return None

    return number


def _safe_bool(value: Any) -> bool | None:
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


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    index = (len(ordered) - 1) * q
    lo = math.floor(index)
    hi = math.ceil(index)

    if lo == hi:
        return ordered[lo]

    weight = index - lo

    return (
        ordered[lo] * (1.0 - weight)
        + ordered[hi] * weight
    )


def _summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "n": 0,
            "median": None,
            "p25": None,
            "p75": None,
            "mean": None,
        }

    return {
        "n": len(values),
        "median": statistics.median(values),
        "p25": _quantile(values, 0.25),
        "p75": _quantile(values, 0.75),
        "mean": statistics.mean(values),
    }


def _authority_fields() -> dict[str, Any]:
    return {
        "decision_impact": "OBSERVE_ONLY",
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_score": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
        "can_modify_lot": False,
    }


def resolve_cisd_policy(
    strategy: Any,
    entry_model: Any,
) -> str:
    strategy_key = _upper(strategy)
    entry_key = _upper(entry_model)

    explicit = _ENTRY_MODEL_POLICY.get(
        (
            strategy_key,
            entry_key,
        )
    )

    if explicit:
        return explicit

    return _STRATEGY_DEFAULT_POLICY.get(
        strategy_key,
        CISD_OPTIONAL,
    )


def _signal(setup: dict[str, Any]) -> str:
    return _upper(
        setup.get("signal")
        or setup.get("direction")
        or setup.get("side")
    )


def _entry(setup: dict[str, Any]) -> float | None:
    for key in (
        "entry",
        "entry_price",
        "entry_reference",
        "price",
    ):
        value = _safe_float(
            setup.get(key)
        )

        if value is not None:
            return value

    return None


def _zone_mid(
    setup: dict[str, Any],
    low_key: str,
    high_key: str,
) -> float | None:
    low = _safe_float(
        setup.get(low_key)
    )
    high = _safe_float(
        setup.get(high_key)
    )

    if low is None or high is None:
        return None

    if high < low:
        low, high = high, low

    return (
        low + high
    ) / 2.0


def resolve_structural_anchor(
    setup: dict[str, Any],
) -> dict[str, Any]:
    signal = _signal(setup)

    # Strongest exact anchors first.
    for key, anchor_type in (
        ("neckline", "NECKLINE"),
        ("failed_breakout_level", "FAILED_BREAKOUT_LEVEL"),
        ("breakout_level", "BREAKOUT_LEVEL"),
        ("retest_level", "RETEST_LEVEL"),
        ("liquidity_level", "LIQUIDITY_LEVEL"),
        ("sweep_level", "SWEEP_LEVEL"),
        ("daily_pivot", "DAILY_PIVOT"),
    ):
        value = _safe_float(
            setup.get(key)
        )

        if value is not None:
            return {
                "type": anchor_type,
                "price": value,
                "source_fields": [
                    key,
                ],
            }

    # Zone midpoints are more stable than arbitrarily choosing one edge.
    for low_key, high_key, anchor_type in (
        ("fvg_bottom", "fvg_top", "FVG_MID"),
        ("failed_fvg_bottom", "failed_fvg_top", "FAILED_FVG_MID"),
        ("ifvg_bottom", "ifvg_top", "IFVG_MID"),
        ("ob_low", "ob_high", "ORDER_BLOCK_MID"),
        ("order_block_low", "order_block_high", "ORDER_BLOCK_MID"),
        ("demand_low", "demand_high", "DEMAND_ZONE_MID"),
        ("supply_low", "supply_high", "SUPPLY_ZONE_MID"),
    ):
        mid = _zone_mid(
            setup,
            low_key,
            high_key,
        )

        if mid is not None:
            return {
                "type": anchor_type,
                "price": mid,
                "source_fields": [
                    low_key,
                    high_key,
                ],
            }

    # OR/range boundaries depend on direction.
    if signal == "BUY":
        directional_keys = (
            ("orb_high", "ORB_HIGH"),
            ("range_low", "RANGE_LOW"),
            ("support", "SUPPORT"),
            ("sweep_low", "SWEEP_LOW"),
            ("liquidity_low", "LIQUIDITY_LOW"),
        )
    elif signal == "SELL":
        directional_keys = (
            ("orb_low", "ORB_LOW"),
            ("range_high", "RANGE_HIGH"),
            ("resistance", "RESISTANCE"),
            ("sweep_high", "SWEEP_HIGH"),
            ("liquidity_high", "LIQUIDITY_HIGH"),
        )
    else:
        directional_keys = ()

    for key, anchor_type in directional_keys:
        value = _safe_float(
            setup.get(key)
        )

        if value is not None:
            return {
                "type": anchor_type,
                "price": value,
                "source_fields": [
                    key,
                ],
            }

    return {
        "type": "NO_STRUCTURAL_ANCHOR",
        "price": None,
        "source_fields": [],
    }


def _terminal(row: dict[str, Any]) -> bool:
    return _upper(
        row.get("status")
    ) in {
        "CLOSED",
        "EXPIRED",
    }


def _path_measured_legacy_safe(
    row: dict[str, Any],
) -> bool:
    if row.get("path_observed") is True:
        return True

    if _upper(
        row.get("first_hit")
    ) in {
        "W10",
        "TP_TOUCH",
        "SL_TOUCH",
    }:
        return True

    for key in (
        "hit_plus_10",
        "hit_tp",
        "hit_sl",
    ):
        if _safe_bool(
            row.get(key)
        ) is True:
            return True

    for key in (
        "max_favorable_usd",
        "max_adverse_usd",
        "max_recovery_swing_usd",
    ):
        value = _safe_float(
            row.get(key)
        )

        if (
            value is not None
            and abs(value) > 0.0
        ):
            return True

    return False


def _historical_cohort(
    setup: dict[str, Any],
    rows: Iterable[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    strategy = _upper(
        setup.get("strategy")
    )
    entry_model = _upper(
        setup.get("entry_model")
    )
    signal = _signal(setup)
    current_setup_id = str(
        setup.get("setup_id")
        or ""
    ).strip()

    usable = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        if not _terminal(row):
            continue

        if not _path_measured_legacy_safe(row):
            continue

        row_setup_id = str(
            row.get("setup_id")
            or ""
        ).strip()

        if (
            current_setup_id
            and row_setup_id == current_setup_id
        ):
            continue

        usable.append(row)

    exact = [
        row
        for row in usable
        if _upper(row.get("strategy")) == strategy
        and _upper(row.get("entry_model")) == entry_model
        and _upper(row.get("signal")) == signal
    ]

    if exact:
        return (
            "STRATEGY_ENTRY_MODEL_SIGNAL",
            exact,
        )

    strategy_signal = [
        row
        for row in usable
        if _upper(row.get("strategy")) == strategy
        and _upper(row.get("signal")) == signal
    ]

    if strategy_signal:
        return (
            "STRATEGY_SIGNAL",
            strategy_signal,
        )

    strategy_only = [
        row
        for row in usable
        if _upper(row.get("strategy")) == strategy
    ]

    return (
        "STRATEGY",
        strategy_only,
    )


def _historical_calibration(
    setup: dict[str, Any],
    rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    cohort_name, cohort = _historical_cohort(
        setup,
        rows,
    )

    full_path_mae = []
    full_path_mfe = []
    full_path_recovery = []
    pre_w10_mae = []
    pre_w10_time_to_max_adverse = []
    pre_w10_mae_atr_ratio = []
    setup_win_known = []

    for row in cohort:
        mae = _safe_float(
            row.get("max_adverse_usd")
        )
        mfe = _safe_float(
            row.get("max_favorable_usd")
        )
        recovery = _safe_float(
            row.get("max_recovery_swing_usd")
        )
        pre_w10 = _safe_float(
            row.get("pre_w10_max_adverse_usd")
        )
        pre_w10_time = _safe_float(
            row.get(
                "time_to_pre_w10_max_adverse_seconds"
            )
        )
        setup_win = _safe_bool(
            row.get("hit_plus_10")
        )

        if mae is not None:
            full_path_mae.append(
                abs(mae)
            )

        if mfe is not None:
            full_path_mfe.append(
                abs(mfe)
            )

        if recovery is not None:
            full_path_recovery.append(
                abs(recovery)
            )

        if pre_w10 is not None:
            pre_w10 = abs(pre_w10)
            pre_w10_mae.append(
                pre_w10
            )

            detection_context = row.get(
                "better_entry_detection_context"
            )

            if isinstance(
                detection_context,
                dict,
            ):
                atr = _safe_float(
                    detection_context.get(
                        "atr_14"
                    )
                )

                if atr is None:
                    atr = _safe_float(
                        detection_context.get(
                            "atr"
                        )
                    )

                if (
                    atr is not None
                    and atr > 0.0
                ):
                    pre_w10_mae_atr_ratio.append(
                        pre_w10 / atr
                    )

        if (
            pre_w10_time is not None
            and pre_w10_time >= 0.0
        ):
            pre_w10_time_to_max_adverse.append(
                pre_w10_time
            )

        if setup_win is not None:
            setup_win_known.append(
                setup_win
            )

    win_count = sum(
        1
        for value in setup_win_known
        if value
    )
    win_rate = (
        win_count
        / len(setup_win_known)
        if setup_win_known
        else None
    )

    pre_w10_stats = _summary(
        pre_w10_mae
    )

    return {
        "cohort_name": cohort_name,
        "cohort_total": len(cohort),
        "setup_win_sample": len(setup_win_known),
        "setup_wins": win_count,
        "setup_win_rate": win_rate,
        "full_path_mae": _summary(
            full_path_mae
        ),
        "full_path_mfe": _summary(
            full_path_mfe
        ),
        "full_path_recovery": _summary(
            full_path_recovery
        ),
        "pre_w10_mae": pre_w10_stats,
        "pre_w10_time_to_max_adverse_seconds": _summary(
            pre_w10_time_to_max_adverse
        ),
        "pre_w10_mae_atr_ratio": _summary(
            pre_w10_mae_atr_ratio
        ),
        "pre_w10_calibration_ready": (
            pre_w10_stats["n"]
            >= BETTER_ENTRY_OPTIMIZER_MIN_HISTORICAL_SAMPLE
        ),
        "full_path_excursion_usage": (
            "DIAGNOSTIC_ONLY_NOT_ENTRY_DEPTH"
        ),
    }



def _load_local_rows_fail_open() -> list[dict[str, Any]]:
    try:
        from src.setup_outcome_tracker import (
            get_setup_outcomes_file,
        )

        path = get_setup_outcomes_file()

        if not path.exists():
            return []

        payload = json.loads(
            path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )

        if isinstance(payload, dict):
            if payload and all(
                isinstance(value, dict)
                for value in payload.values()
            ):
                return list(
                    payload.values()
                )

            for key in (
                "records",
                "items",
                "outcomes",
                "setup_outcomes",
            ):
                value = payload.get(key)

                if isinstance(value, list):
                    return [
                        row
                        for row in value
                        if isinstance(row, dict)
                    ]

        if isinstance(payload, list):
            return [
                row
                for row in payload
                if isinstance(row, dict)
            ]
    except Exception:
        return []

    return []


def _proposed_structural_entry(
    *,
    signal: str,
    original_entry: float | None,
    anchor_price: float | None,
) -> tuple[float | None, float | None]:
    if (
        original_entry is None
        or anchor_price is None
    ):
        return (
            None,
            None,
        )

    if signal == "BUY":
        improvement = (
            original_entry
            - anchor_price
        )
    elif signal == "SELL":
        improvement = (
            anchor_price
            - original_entry
        )
    else:
        return (
            None,
            None,
        )

    # Only call it a better structural entry when price improves.
    if improvement <= 0:
        return (
            None,
            improvement,
        )

    return (
        anchor_price,
        improvement,
    )


def _historical_entry_candidate(
    *,
    signal: str,
    original_entry: float | None,
    calibration: dict[str, Any],
) -> tuple[float | None, float | None]:
    if original_entry is None:
        return (
            None,
            None,
        )

    pre_w10 = dict(
        calibration.get(
            "pre_w10_mae",
            {}
        )
        or {}
    )

    if not calibration.get(
        "pre_w10_calibration_ready"
    ):
        return (
            None,
            None,
        )

    depth = _safe_float(
        pre_w10.get("median")
    )

    if (
        depth is None
        or depth <= 0
    ):
        return (
            None,
            None,
        )

    if signal == "BUY":
        return (
            original_entry - depth,
            depth,
        )

    if signal == "SELL":
        return (
            original_entry + depth,
            depth,
        )

    return (
        None,
        None,
    )


def build_better_entry_observer(
    setup: dict[str, Any],
    *,
    historical_rows: list[dict[str, Any]] | None = None,
    enabled_override: bool | None = None,
) -> dict[str, Any]:
    enabled = (
        ENABLE_BETTER_ENTRY_OPTIMIZER
        if enabled_override is None
        else bool(enabled_override)
    )

    if not enabled:
        return {
            "enabled": False,
            "version": BETTER_ENTRY_OPTIMIZER_VERSION,
            **_authority_fields(),
        }

    source = dict(
        setup or {}
    )

    strategy = _upper(
        source.get("strategy")
    )
    entry_model = _upper(
        source.get("entry_model")
    ) or "UNKNOWN_ENTRY_MODEL"
    signal = _signal(source)
    original_entry = _entry(source)

    policy = resolve_cisd_policy(
        strategy,
        entry_model,
    )
    anchor = resolve_structural_anchor(
        source
    )

    rows = (
        historical_rows
        if historical_rows is not None
        else _load_local_rows_fail_open()
    )

    calibration = _historical_calibration(
        source,
        rows,
    )

    structural_entry, structural_improvement = (
        _proposed_structural_entry(
            signal=signal,
            original_entry=original_entry,
            anchor_price=_safe_float(
                anchor.get("price")
            ),
        )
    )

    historical_entry, historical_depth = (
        _historical_entry_candidate(
            signal=signal,
            original_entry=original_entry,
            calibration=calibration,
        )
    )

    if policy == NO_CISD:
        cisd_mode = "NOT_REQUIRED"
    elif policy == CISD_REQUIRED:
        cisd_mode = "REQUIRED_BEFORE_OBSERVER_ENTRY"
    elif policy == CISD_ON_RETEST:
        cisd_mode = "REQUIRED_AT_STRUCTURAL_RETEST"
    else:
        cisd_mode = "OPTIONAL_OBSERVER_CONFIRMATION"

    if structural_entry is not None:
        preferred_basis = "STRUCTURAL_ANCHOR"
        preferred_entry = structural_entry
    elif historical_entry is not None:
        preferred_basis = "HISTORICAL_PRE_W10_MAE"
        preferred_entry = historical_entry
    else:
        preferred_basis = "NO_BETTER_ENTRY_YET"
        preferred_entry = None

    return {
        "enabled": True,
        "version": BETTER_ENTRY_OPTIMIZER_VERSION,
        "setup_id": source.get("setup_id"),
        "strategy": strategy,
        "entry_model": entry_model,
        "signal": signal,
        "original_entry": original_entry,
        "cisd_policy": policy,
        "cisd_mode": cisd_mode,
        "cisd_status": "NOT_EVALUATED_V1",
        "structural_anchor": anchor,
        "structural_candidate_entry": structural_entry,
        "structural_entry_improvement_usd": structural_improvement,
        "historical_candidate_entry": historical_entry,
        "historical_wait_depth_usd": historical_depth,
        "preferred_observer_entry_basis": preferred_basis,
        "preferred_observer_entry": preferred_entry,
        "historical_calibration": calibration,
        "requires_pre_event_path_instrumentation": (
            not calibration.get(
                "pre_w10_calibration_ready"
            )
        ),
        "note": (
            "Full-path MAE/MFE/recovery are diagnostic only. "
            "They are never converted directly into entry depth."
        ),
        **_authority_fields(),
    }


def format_better_entry_observer(
    snapshot: dict[str, Any],
) -> str:
    if not snapshot.get("enabled"):
        return ""

    calibration = dict(
        snapshot.get(
            "historical_calibration",
            {}
        )
        or {}
    )
    pre_w10 = dict(
        calibration.get(
            "pre_w10_mae",
            {}
        )
        or {}
    )

    return "\n".join(
        [
            "BETTER ENTRY OPTIMIZER [OBSERVE ONLY]",
            (
                f"Policy: {snapshot.get('cisd_policy')} | "
                f"CISD: {snapshot.get('cisd_status')}"
            ),
            (
                "Original Entry: "
                f"{snapshot.get('original_entry')}"
            ),
            (
                "Structural Anchor: "
                f"{snapshot.get('structural_anchor', {}).get('type')} "
                f"@ {snapshot.get('structural_anchor', {}).get('price')}"
            ),
            (
                "Structural Candidate: "
                f"{snapshot.get('structural_candidate_entry')}"
            ),
            (
                "Historical Candidate: "
                f"{snapshot.get('historical_candidate_entry')}"
            ),
            (
                "Historical Cohort: "
                f"{calibration.get('cohort_name')} "
                f"n={calibration.get('cohort_total', 0)}"
            ),
            (
                "Pre-W10 MAE: "
                f"n={pre_w10.get('n', 0)} "
                f"median={pre_w10.get('median')}"
            ),
            (
                "Preferred Observer Entry: "
                f"{snapshot.get('preferred_observer_entry_basis')} "
                f"@ {snapshot.get('preferred_observer_entry')}"
            ),
        ]
    )
