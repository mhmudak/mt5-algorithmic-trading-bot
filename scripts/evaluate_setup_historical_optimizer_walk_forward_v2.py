from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import json
import math
from pathlib import Path
import statistics
from typing import Any

from src.setup_historical_optimizer import _path_measured
from src.setup_outcome_tracker import get_setup_outcomes_file


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


def _wilson_interval(
    wins: int,
    total: int,
    z: float = 1.959963984540054,
) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None

    p = wins / total
    z2 = z * z
    denominator = 1.0 + z2 / total
    center = (
        p + z2 / (2.0 * total)
    ) / denominator
    margin = (
        z
        * math.sqrt(
            p * (1.0 - p) / total
            + z2 / (4.0 * total * total)
        )
        / denominator
    )

    return (
        max(0.0, center - margin),
        min(1.0, center + margin),
    )


def _flatten(payload) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [
            row
            for row in payload
            if isinstance(row, dict)
        ]

    if isinstance(payload, dict):
        if payload and all(
            isinstance(value, dict)
            for value in payload.values()
        ):
            return list(payload.values())

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

    return []


def _terminal(row: dict[str, Any]) -> bool:
    return str(
        row.get("status") or ""
    ).strip().upper() in {
        "CLOSED",
        "EXPIRED",
    }


def _snapshot(row: dict[str, Any]) -> dict[str, Any] | None:
    value = row.get(
        "historical_optimizer_snapshot"
    )

    if isinstance(value, dict):
        return value

    return None


def _prediction_record(
    row: dict[str, Any],
) -> dict[str, Any] | None:
    snapshot = _snapshot(row)

    if snapshot is None:
        return None

    if not _terminal(row):
        return None

    if not _path_measured(row):
        return None

    actual = _safe_bool(
        row.get(
            "hit_plus_10"
        )
    )

    if actual is None:
        return None

    predicted = _safe_float(
        snapshot.get(
            "setup_win_rate"
        )
    )

    if (
        predicted is None
        or predicted < 0.0
        or predicted > 1.0
        or not snapshot.get(
            "available"
        )
    ):
        return {
            "eligible": False,
            "actual": bool(actual),
            "snapshot": snapshot,
            "row": row,
            "reason": "prediction_unavailable",
        }

    cohort = dict(
        snapshot.get(
            "cohort",
            {}
        )
        or {}
    )

    return {
        "eligible": True,
        "actual": bool(actual),
        "predicted": predicted,
        "snapshot": snapshot,
        "row": row,
        "cohort_name": str(
            cohort.get(
                "name"
            )
            or "UNKNOWN"
        ),
        "confidence": str(
            snapshot.get(
                "confidence"
            )
            or "UNKNOWN"
        ),
        "rr_bucket": str(
            snapshot.get(
                "rr_bucket"
            )
            or "RR_UNKNOWN"
        ),
        "strategy": str(
            row.get(
                "strategy"
            )
            or "UNKNOWN"
        ),
        "signal": str(
            row.get(
                "signal"
            )
            or "UNKNOWN"
        ),
        "session": str(
            row.get(
                "session"
            )
            or "UNKNOWN"
        ),
        "market_condition": str(
            row.get(
                "market_condition"
            )
            or "UNKNOWN"
        ),
    }


def _calibration_summary(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    eligible = [
        record
        for record in records
        if record.get(
            "eligible"
        )
    ]

    total = len(
        eligible
    )

    if total <= 0:
        return {
            "n": 0,
            "actual_wins": 0,
            "actual_setup_win_rate": None,
            "predicted_mean_setup_win_rate": None,
            "calibration_gap_actual_minus_predicted": None,
            "mean_absolute_prediction_error": None,
            "brier_score": None,
            "actual_wilson_low": None,
            "actual_wilson_high": None,
            "sample_status": "NO_CALIBRATION_SAMPLE",
        }

    wins = sum(
        1
        for record in eligible
        if record[
            "actual"
        ]
    )

    actual_rate = (
        wins / total
    )
    predicted_values = [
        record[
            "predicted"
        ]
        for record in eligible
    ]
    predicted_mean = statistics.mean(
        predicted_values
    )

    absolute_errors = [
        abs(
            (1.0 if record["actual"] else 0.0)
            - record["predicted"]
        )
        for record in eligible
    ]
    brier_values = [
        (
            record["predicted"]
            - (
                1.0
                if record["actual"]
                else 0.0
            )
        )
        ** 2
        for record in eligible
    ]

    wilson_low, wilson_high = (
        _wilson_interval(
            wins,
            total,
        )
    )

    if total < 20:
        sample_status = "INSUFFICIENT_LT_20"
    elif total < 50:
        sample_status = "EARLY_20_TO_49"
    else:
        sample_status = "ESTABLISHED_GE_50"

    return {
        "n": total,
        "actual_wins": wins,
        "actual_setup_win_rate": actual_rate,
        "predicted_mean_setup_win_rate": predicted_mean,
        "calibration_gap_actual_minus_predicted": (
            actual_rate
            - predicted_mean
        ),
        "mean_absolute_prediction_error": statistics.mean(
            absolute_errors
        ),
        "brier_score": statistics.mean(
            brier_values
        ),
        "actual_wilson_low": wilson_low,
        "actual_wilson_high": wilson_high,
        "sample_status": sample_status,
    }


def _group_summaries(
    eligible_records: list[dict[str, Any]],
    key: str,
) -> list[dict[str, Any]]:
    grouped: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(
        list
    )

    for record in eligible_records:
        grouped[
            str(
                record.get(
                    key
                )
                or "UNKNOWN"
            )
        ].append(
            record
        )

    output = []

    for value in sorted(
        grouped
    ):
        summary = _calibration_summary(
            grouped[
                value
            ]
        )
        output.append(
            {
                "group": value,
                **summary,
            }
        )

    return output


def evaluate_rows(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = [
        row
        for row in rows
        if isinstance(
            row,
            dict,
        )
    ]

    snapshots = [
        row
        for row in rows
        if _snapshot(
            row
        )
        is not None
    ]
    mature_snapshots = [
        row
        for row in snapshots
        if _terminal(
            row
        )
    ]
    measured_mature = [
        row
        for row in mature_snapshots
        if _path_measured(
            row
        )
    ]

    records = [
        record
        for row in rows
        if (
            record := _prediction_record(
                row
            )
        )
        is not None
    ]

    eligible_records = [
        record
        for record in records
        if record.get(
            "eligible"
        )
    ]

    unavailable_predictions = [
        record
        for record in records
        if not record.get(
            "eligible"
        )
    ]

    overall = _calibration_summary(
        eligible_records
    )

    return {
        "report_version": "V1",
        "generated_at": datetime.now().isoformat(),
        "setup_win_definition": (
            "+$10 favorable move = Setup Win"
        ),
        "authority": {
            "observer_only": True,
            "can_execute": False,
            "can_block_trade": False,
            "can_modify_score": False,
            "can_modify_risk": False,
            "can_modify_entry_sl_tp": False,
        },
        "coverage": {
            "total_setup_outcome_rows": len(
                rows
            ),
            "rows_with_snapshot": len(
                snapshots
            ),
            "mature_rows_with_snapshot": len(
                mature_snapshots
            ),
            "mature_measured_rows_with_snapshot": len(
                measured_mature
            ),
            "calibration_eligible_rows": len(
                eligible_records
            ),
            "prediction_unavailable_rows": len(
                unavailable_predictions
            ),
            "snapshot_coverage_of_all_rows": (
                len(
                    snapshots
                )
                / len(
                    rows
                )
                if rows
                else None
            ),
            "measured_coverage_of_mature_snapshots": (
                len(
                    measured_mature
                )
                / len(
                    mature_snapshots
                )
                if mature_snapshots
                else None
            ),
        },
        "overall": overall,
        "groups": {
            "confidence": _group_summaries(
                eligible_records,
                "confidence",
            ),
            "rr_bucket": _group_summaries(
                eligible_records,
                "rr_bucket",
            ),
            "cohort": _group_summaries(
                eligible_records,
                "cohort_name",
            ),
            "strategy": _group_summaries(
                eligible_records,
                "strategy",
            ),
            "signal": _group_summaries(
                eligible_records,
                "signal",
            ),
            "session": _group_summaries(
                eligible_records,
                "session",
            ),
            "market_condition": _group_summaries(
                eligible_records,
                "market_condition",
            ),
        },
    }


def _pct(value) -> str:
    value = _safe_float(
        value
    )

    if value is None:
        return "N/A"

    return (
        f"{value * 100:.1f}%"
    )


def format_report(
    report: dict[str, Any],
) -> str:
    coverage = dict(
        report.get(
            "coverage",
            {}
        )
        or {}
    )
    overall = dict(
        report.get(
            "overall",
            {}
        )
        or {}
    )

    lines = [
        "SETUP HISTORICAL OPTIMIZER - WALK-FORWARD EVALUATION",
        "OBSERVE ONLY",
        "",
        (
            "Setup Win Definition: "
            "+$10 favorable move = Setup Win"
        ),
        "",
        "COVERAGE",
        (
            "Total setup rows: "
            f"{coverage.get('total_setup_outcome_rows', 0)}"
        ),
        (
            "Rows with detection snapshot: "
            f"{coverage.get('rows_with_snapshot', 0)}"
        ),
        (
            "Mature snapshot rows: "
            f"{coverage.get('mature_rows_with_snapshot', 0)}"
        ),
        (
            "Mature + measured snapshot rows: "
            f"{coverage.get('mature_measured_rows_with_snapshot', 0)}"
        ),
        (
            "Calibration eligible: "
            f"{coverage.get('calibration_eligible_rows', 0)}"
        ),
        "",
        "OVERALL CALIBRATION",
        (
            "Sample: "
            f"{overall.get('n', 0)} "
            f"[{overall.get('sample_status', 'N/A')}]"
        ),
        (
            "Predicted mean Setup Win: "
            f"{_pct(overall.get('predicted_mean_setup_win_rate'))}"
        ),
        (
            "Actual Setup Win: "
            f"{_pct(overall.get('actual_setup_win_rate'))}"
        ),
        (
            "Actual 95% CI: "
            f"{_pct(overall.get('actual_wilson_low'))}"
            "-"
            f"{_pct(overall.get('actual_wilson_high'))}"
        ),
        (
            "Calibration gap (actual - predicted): "
            f"{_pct(overall.get('calibration_gap_actual_minus_predicted'))}"
        ),
        (
            "Brier score: "
            f"{overall.get('brier_score')}"
        ),
        "",
    ]

    groups = dict(
        report.get(
            "groups",
            {}
        )
        or {}
    )

    for dimension in (
        "confidence",
        "rr_bucket",
        "cohort",
        "strategy",
        "signal",
        "session",
        "market_condition",
    ):
        lines.append(
            dimension.upper()
        )

        values = list(
            groups.get(
                dimension,
                []
            )
            or []
        )

        if not values:
            lines.append(
                "  No eligible observations"
            )
        else:
            for item in values:
                lines.append(
                    "  "
                    f"{item.get('group')}: "
                    f"n={item.get('n', 0)} "
                    f"pred={_pct(item.get('predicted_mean_setup_win_rate'))} "
                    f"actual={_pct(item.get('actual_setup_win_rate'))} "
                    f"gap={_pct(item.get('calibration_gap_actual_minus_predicted'))} "
                    f"brier={item.get('brier_score')}"
                )

        lines.append("")

    lines.extend(
        [
            "INTERPRETATION",
            (
                "- n<20: insufficient for calibration conclusions."
            ),
            (
                "- 20-49: early evidence; continue collecting."
            ),
            (
                "- >=50: more useful calibration sample, still observer-only."
            ),
            (
                "- Lower Brier score is better; 0 is perfect."
            ),
            (
                "- Calibration gap near 0 means predicted average and actual "
                "Setup Win rate are aligned."
            ),
            (
                "- This report must not directly control execution, scoring, "
                "risk, entry, SL, TP, or lot size."
            ),
        ]
    )

    return "\n".join(
        lines
    )


def load_rows(
    path: Path,
) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    payload = json.loads(
        path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )

    return _flatten(
        payload
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate detection-time optimizer snapshots against "
            "mature +$10 Setup Win outcomes."
        )
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help=(
            "Optional setup_outcomes.json path. Defaults to the "
            "current account's canonical file."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "local_reports"
        ),
    )

    args = parser.parse_args()

    path = (
        args.path
        if args.path is not None
        else get_setup_outcomes_file()
    )

    rows = load_rows(
        path
    )
    report = evaluate_rows(
        rows
    )
    text_report = format_report(
        report
    )

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = (
        args.output_dir
        / "setup_historical_optimizer_walk_forward_evaluation.json"
    )
    text_path = (
        args.output_dir
        / "setup_historical_optimizer_walk_forward_evaluation.txt"
    )

    json_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    text_path.write_text(
        text_report,
        encoding="utf-8",
    )

    print(
        text_report
    )
    print("")
    print(
        f"WROTE: {json_path}"
    )
    print(
        f"WROTE: {text_path}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
