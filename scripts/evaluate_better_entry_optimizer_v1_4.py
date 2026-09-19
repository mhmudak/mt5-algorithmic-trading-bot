from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import json
import math
import statistics
from typing import Any, Iterable

from src.setup_outcome_tracker import get_setup_outcomes_file


REPORT_VERSION = "V1.4"
TERMINAL_PARENT_STATUSES = {
    "CLOSED",
    "EXPIRED",
}


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

    if text in {
        "true",
        "1",
        "yes",
        "y",
    }:
        return True

    if text in {
        "false",
        "0",
        "no",
        "n",
    }:
        return False

    return None


def _upper(value: Any) -> str:
    return str(
        value
        or ""
    ).strip().upper()


def _quantile(
    values: list[float],
    q: float,
) -> float | None:
    if not values:
        return None

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    index = (
        len(ordered)
        - 1
    ) * q
    lo = math.floor(index)
    hi = math.ceil(index)

    if lo == hi:
        return ordered[lo]

    weight = (
        index
        - lo
    )

    return (
        ordered[lo]
        * (
            1.0
            - weight
        )
        + ordered[hi]
        * weight
    )


def _distribution(
    values: Iterable[float | None],
) -> dict[str, Any]:
    clean = [
        float(value)
        for value in values
        if value is not None
        and math.isfinite(
            float(value)
        )
    ]

    if not clean:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "p25": None,
            "p75": None,
        }

    return {
        "n": len(clean),
        "mean": statistics.mean(
            clean
        ),
        "median": statistics.median(
            clean
        ),
        "p25": _quantile(
            clean,
            0.25,
        ),
        "p75": _quantile(
            clean,
            0.75,
        ),
    }


def _sample_status(
    n: int,
) -> str:
    if n < 20:
        return "INSUFFICIENT_LT_20"

    if n < 50:
        return "EARLY_20_TO_49"

    return "ESTABLISHED_GE_50"


def _load_rows(
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

    if isinstance(
        payload,
        list,
    ):
        return [
            row
            for row in payload
            if isinstance(
                row,
                dict,
            )
        ]

    if isinstance(
        payload,
        dict,
    ):
        if payload and all(
            isinstance(
                value,
                dict,
            )
            for value in payload.values()
        ):
            return list(
                payload.values()
            )

        for key in (
            "items",
            "records",
            "outcomes",
            "setup_outcomes",
        ):
            value = payload.get(
                key
            )

            if isinstance(
                value,
                list,
            ):
                return [
                    row
                    for row in value
                    if isinstance(
                        row,
                        dict,
                    )
                ]

    return []


def _rr(
    *,
    signal: str,
    entry: float | None,
    sl: float | None,
    tp: float | None,
) -> float | None:
    if (
        entry is None
        or sl is None
        or tp is None
    ):
        return None

    signal = _upper(
        signal
    )

    if signal == "BUY":
        risk = (
            entry
            - sl
        )
        reward = (
            tp
            - entry
        )
    elif signal == "SELL":
        risk = (
            sl
            - entry
        )
        reward = (
            entry
            - tp
        )
    else:
        return None

    if (
        risk <= 0.0
        or reward <= 0.0
    ):
        return None

    return (
        reward
        / risk
    )


def _snapshot_context(
    row: dict[str, Any],
) -> dict[str, Any]:
    snapshot = row.get(
        "better_entry_observer_snapshot"
    )

    if not isinstance(
        snapshot,
        dict,
    ):
        snapshot = {}

    profile = snapshot.get(
        "adaptive_wait_profile"
    )

    if not isinstance(
        profile,
        dict,
    ):
        profile = {}

    momentum = profile.get(
        "momentum"
    )

    if not isinstance(
        momentum,
        dict,
    ):
        momentum = {}

    participation = profile.get(
        "participation"
    )

    if not isinstance(
        participation,
        dict,
    ):
        participation = {}

    return {
        "cisd_policy": (
            snapshot.get(
                "cisd_policy"
            )
            or "UNKNOWN"
        ),
        "adaptive_profile": (
            profile.get(
                "profile"
            )
            or "UNKNOWN"
        ),
        "momentum_state": (
            momentum.get(
                "state"
            )
            or "UNKNOWN"
        ),
        "participation_state": (
            participation.get(
                "state"
            )
            or "UNKNOWN"
        ),
    }


def _normalized_candidate_status(
    *,
    parent_terminal: bool,
    candidate: dict[str, Any],
) -> str:
    status = _upper(
        candidate.get(
            "status"
        )
    )
    filled = bool(
        candidate.get(
            "filled"
        )
    )

    if status:
        if status == "WAITING_FILL" and parent_terminal:
            return "UNFILLED_TERMINAL"

        if status == "FILLED_TRACKING" and parent_terminal:
            return "FILLED_TERMINAL_NO_EVENT"

        if status == "FILLED_W10_REACHED" and parent_terminal:
            return "FILLED_W10_REACHED"

        return status

    if parent_terminal:
        return (
            "FILLED_TERMINAL_NO_EVENT"
            if filled
            else "UNFILLED_TERMINAL"
        )

    return (
        "FILLED_TRACKING"
        if filled
        else "WAITING_FILL"
    )


def _candidate_record(
    row: dict[str, Any],
    candidate_key: str,
    candidate: dict[str, Any],
) -> dict[str, Any] | None:
    parent_status = _upper(
        row.get(
            "status"
        )
    )
    parent_terminal = (
        parent_status
        in TERMINAL_PARENT_STATUSES
    )

    if not parent_terminal:
        return None

    signal = _upper(
        row.get(
            "signal"
        )
    )

    original_entry = _safe_float(
        candidate.get(
            "original_entry"
        )
    )

    if original_entry is None:
        original_entry = _safe_float(
            row.get(
                "entry"
            )
        )

    candidate_entry = _safe_float(
        candidate.get(
            "candidate_entry"
        )
    )
    sl = _safe_float(
        candidate.get(
            "original_sl"
        )
    )
    tp = _safe_float(
        candidate.get(
            "original_tp"
        )
    )

    original_rr = _rr(
        signal=signal,
        entry=original_entry,
        sl=sl,
        tp=tp,
    )
    candidate_rr = _rr(
        signal=signal,
        entry=candidate_entry,
        sl=sl,
        tp=tp,
    )

    rr_improvement = None

    if (
        original_rr is not None
        and candidate_rr is not None
    ):
        rr_improvement = (
            candidate_rr
            - original_rr
        )

    filled = bool(
        candidate.get(
            "filled"
        )
    )
    candidate_win = (
        _safe_bool(
            candidate.get(
                "hit_plus_10_after_fill"
            )
        )
        is True
    )
    original_win = (
        _safe_bool(
            row.get(
                "hit_plus_10"
            )
        )
        is True
    )

    missed_winner = (
        _safe_bool(
            candidate.get(
                "missed_winner"
            )
        )
        is True
    )

    if (
        original_win
        and not filled
    ):
        missed_winner = True

    context = _snapshot_context(
        row
    )

    return {
        "setup_id": row.get(
            "setup_id"
        ),
        "candidate_key": candidate_key,
        "basis": (
            candidate.get(
                "basis"
            )
            or candidate_key
        ),
        "strategy": (
            row.get(
                "strategy"
            )
            or "UNKNOWN"
        ),
        "entry_model": (
            row.get(
                "entry_model"
            )
            or "UNKNOWN"
        ),
        "signal": signal
        or "UNKNOWN",
        "session": (
            row.get(
                "session"
            )
            or "UNKNOWN"
        ),
        "market_condition": (
            row.get(
                "market_condition"
            )
            or "UNKNOWN"
        ),
        **context,
        "research_scope": (
            row.get(
                "better_entry_counterfactual_scope"
            )
            or "LEGACY_UNSCOPED"
        ),
        "parent_status": parent_status,
        "normalized_status": (
            _normalized_candidate_status(
                parent_terminal=parent_terminal,
                candidate=candidate,
            )
        ),
        "filled": filled,
        "original_setup_win": original_win,
        "candidate_setup_win": candidate_win,
        "missed_winner": missed_winner,
        "fill_wait_seconds": _safe_float(
            candidate.get(
                "fill_wait_seconds"
            )
        ),
        "candidate_mae": _safe_float(
            candidate.get(
                "max_adverse_usd_after_fill"
            )
        ),
        "candidate_mfe": _safe_float(
            candidate.get(
                "max_favorable_usd_after_fill"
            )
        ),
        "original_mae": _safe_float(
            row.get(
                "max_adverse_usd"
            )
        ),
        "original_mfe": _safe_float(
            row.get(
                "max_favorable_usd"
            )
        ),
        "original_rr": original_rr,
        "candidate_rr": candidate_rr,
        "rr_improvement": rr_improvement,
        "hit_tp_after_fill": (
            _safe_bool(
                candidate.get(
                    "hit_tp_after_fill"
                )
            )
            is True
        ),
        "hit_sl_after_fill": (
            _safe_bool(
                candidate.get(
                    "hit_sl_after_fill"
                )
            )
            is True
        ),
    }


def extract_candidate_records(
    rows: Iterable[
        dict[str, Any]
    ],
) -> list[dict[str, Any]]:
    records = []

    for row in rows:
        if not isinstance(
            row,
            dict,
        ):
            continue

        candidates = row.get(
            "better_entry_counterfactuals"
        )

        if not isinstance(
            candidates,
            dict,
        ):
            continue

        for key, candidate in candidates.items():
            if not isinstance(
                candidate,
                dict,
            ):
                continue

            record = _candidate_record(
                row,
                str(
                    key
                ),
                candidate,
            )

            if record is not None:
                records.append(
                    record
                )

    return records


def summarize_records(
    records: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    n = len(
        records
    )

    filled = [
        row
        for row in records
        if row[
            "filled"
        ]
    ]
    original_wins = [
        row
        for row in records
        if row[
            "original_setup_win"
        ]
    ]
    candidate_wins = [
        row
        for row in filled
        if row[
            "candidate_setup_win"
        ]
    ]
    missed_winners = [
        row
        for row in records
        if row[
            "missed_winner"
        ]
    ]

    fill_rate = (
        len(filled)
        / n
        if n
        else None
    )

    filled_setup_win_rate = (
        len(candidate_wins)
        / len(filled)
        if filled
        else None
    )

    original_setup_win_rate = (
        len(original_wins)
        / n
        if n
        else None
    )

    missed_winner_rate = (
        len(missed_winners)
        / len(original_wins)
        if original_wins
        else None
    )

    opportunity_capture_rate = (
        len(candidate_wins)
        / len(original_wins)
        if original_wins
        else None
    )

    terminal_unfilled_nonwinners = [
        row
        for row in records
        if (
            not row[
                "filled"
            ]
            and not row[
                "original_setup_win"
            ]
        )
    ]

    rr_rows = [
        row
        for row in filled
        if row[
            "rr_improvement"
        ]
        is not None
    ]

    mae_improvements = []

    for row in filled:
        original_mae = row[
            "original_mae"
        ]
        candidate_mae = row[
            "candidate_mae"
        ]

        if (
            original_mae is None
            or candidate_mae is None
        ):
            continue

        mae_improvements.append(
            original_mae
            - candidate_mae
        )

    return {
        "n": n,
        "sample_status": _sample_status(
            n
        ),
        "filled": len(
            filled
        ),
        "fill_rate": fill_rate,
        "original_setup_wins": len(
            original_wins
        ),
        "original_setup_win_rate": (
            original_setup_win_rate
        ),
        "candidate_setup_wins": len(
            candidate_wins
        ),
        "filled_setup_win_rate": (
            filled_setup_win_rate
        ),
        "missed_winners": len(
            missed_winners
        ),
        "missed_winner_rate": (
            missed_winner_rate
        ),
        "opportunity_capture_rate": (
            opportunity_capture_rate
        ),
        "terminal_unfilled_nonwinners": len(
            terminal_unfilled_nonwinners
        ),
        "wait_seconds": _distribution(
            row[
                "fill_wait_seconds"
            ]
            for row in filled
        ),
        "candidate_mae": _distribution(
            row[
                "candidate_mae"
            ]
            for row in filled
        ),
        "candidate_mfe": _distribution(
            row[
                "candidate_mfe"
            ]
            for row in filled
        ),
        "original_mae": _distribution(
            row[
                "original_mae"
            ]
            for row in filled
        ),
        "original_mfe": _distribution(
            row[
                "original_mfe"
            ]
            for row in filled
        ),
        "mae_improvement_original_minus_candidate": (
            _distribution(
                mae_improvements
            )
        ),
        "original_rr": _distribution(
            row[
                "original_rr"
            ]
            for row in rr_rows
        ),
        "candidate_rr": _distribution(
            row[
                "candidate_rr"
            ]
            for row in rr_rows
        ),
        "rr_improvement_candidate_minus_original": (
            _distribution(
                row[
                    "rr_improvement"
                ]
                for row in rr_rows
            )
        ),
        "tp_after_fill_rate": (
            sum(
                1
                for row in filled
                if row[
                    "hit_tp_after_fill"
                ]
            )
            / len(filled)
            if filled
            else None
        ),
        "sl_after_fill_rate": (
            sum(
                1
                for row in filled
                if row[
                    "hit_sl_after_fill"
                ]
            )
            / len(filled)
            if filled
            else None
        ),
    }


GROUP_FIELDS = (
    "basis",
    "strategy",
    "entry_model",
    "signal",
    "session",
    "market_condition",
    "cisd_policy",
    "adaptive_profile",
    "momentum_state",
    "participation_state",
    "research_scope",
)


def grouped_summaries(
    records: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    output = {}

    for field in GROUP_FIELDS:
        buckets = defaultdict(
            list
        )

        for row in records:
            value = (
                row.get(
                    field
                )
                or "UNKNOWN"
            )
            buckets[
                str(
                    value
                )
            ].append(
                row
            )

        output[
            field
        ] = {
            key: summarize_records(
                values
            )
            for key, values in sorted(
                buckets.items()
            )
        }

    return output


def build_report(
    rows: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    records = (
        extract_candidate_records(
            rows
        )
    )

    by_basis = defaultdict(
        list
    )

    for record in records:
        by_basis[
            str(
                record[
                    "basis"
                ]
            )
        ].append(
            record
        )

    basis_summary = {
        key: summarize_records(
            values
        )
        for key, values in sorted(
            by_basis.items()
        )
    }

    primary_records = [
        row
        for row in records
        if row.get(
            "research_scope"
        )
        == "PRIMARY"
    ]
    rescue_records = [
        row
        for row in records
        if row.get(
            "research_scope"
        )
        == "ENTRY_RESCUE"
    ]

    return {
        "report_version": REPORT_VERSION,
        "authority": {
            "decision_impact": "EVALUATION_ONLY",
            "can_execute": False,
            "can_block_trade": False,
            "can_modify_score": False,
            "can_modify_risk": False,
            "can_modify_entry_sl_tp": False,
            "can_modify_lot": False,
        },
        "definitions": {
            "setup_win": (
                "+$10 favorable move after the relevant entry"
            ),
            "filled_setup_win_rate": (
                "candidate Setup Wins / candidate fills"
            ),
            "missed_winner_rate": (
                "unfilled original Setup Wins / original Setup Wins"
            ),
            "opportunity_capture_rate": (
                "candidate Setup Wins / original Setup Wins"
            ),
            "lifecycle_normalization": (
                "Terminal parent + WAITING_FILL => UNFILLED_TERMINAL; "
                "terminal parent + FILLED_TRACKING => FILLED_TERMINAL_NO_EVENT"
            ),
        },
        "coverage": {
            "setup_outcome_rows": len(
                rows
            ),
            "candidate_records": len(
                records
            ),
            "candidate_parent_setups": len(
                {
                    str(
                        row.get(
                            "setup_id"
                        )
                    )
                    for row in records
                }
            ),
        },
        "overall": summarize_records(
            records
        ),
        "primary_only": summarize_records(
            primary_records
        ),
        "entry_rescue_only": summarize_records(
            rescue_records
        ),
        "by_basis": basis_summary,
        "groups": grouped_summaries(
            records
        ),
        "records": records,
    }


def _pct(
    value: Any,
) -> str:
    number = _safe_float(
        value
    )

    if number is None:
        return "NA"

    return (
        f"{number * 100.0:.2f}%"
    )


def _num(
    value: Any,
    digits: int = 2,
) -> str:
    number = _safe_float(
        value
    )

    if number is None:
        return "NA"

    return (
        f"{number:.{digits}f}"
    )


def _summary_line(
    name: str,
    summary: dict[str, Any],
) -> str:
    return (
        f"{name}: "
        f"n={summary.get('n', 0)} | "
        f"fill={_pct(summary.get('fill_rate'))} | "
        f"filled_win={_pct(summary.get('filled_setup_win_rate'))} | "
        f"missed_winner={_pct(summary.get('missed_winner_rate'))} | "
        f"capture={_pct(summary.get('opportunity_capture_rate'))} | "
        f"wait_med={_num(summary.get('wait_seconds', {}).get('median'))}s | "
        f"MAE_improve_med={_num(summary.get('mae_improvement_original_minus_candidate', {}).get('median'))} | "
        f"RR_improve_med={_num(summary.get('rr_improvement_candidate_minus_original', {}).get('median'))}"
    )


def format_report(
    report: dict[str, Any],
) -> str:
    lines = [
        "BETTER ENTRY OPTIMIZER - COUNTERFACTUAL EVALUATION",
        "EVALUATION ONLY - NO EXECUTION AUTHORITY",
        "Setup Win Definition: +$10 favorable move after relevant entry",
        "",
        "COVERAGE",
        (
            f"Setup outcome rows: "
            f"{report.get('coverage', {}).get('setup_outcome_rows', 0)}"
        ),
        (
            f"Candidate records: "
            f"{report.get('coverage', {}).get('candidate_records', 0)}"
        ),
        (
            f"Candidate parent setups: "
            f"{report.get('coverage', {}).get('candidate_parent_setups', 0)}"
        ),
        "",
        "OVERALL",
        _summary_line(
            "ALL",
            report.get(
                "overall",
                {},
            ),
        ),
        "",
        "BY BASIS",
    ]

    for name, summary in (
        report.get(
            "by_basis",
            {}
        ).items()
    ):
        lines.append(
            _summary_line(
                name,
                summary,
            )
        )

    lines.extend(
        [
            "",
            "GROUP BREAKDOWNS",
        ]
    )

    groups = report.get(
        "groups",
        {}
    )

    for field in GROUP_FIELDS:
        lines.append(
            f"[{field}]"
        )

        for name, summary in (
            groups.get(
                field,
                {}
            ).items()
        ):
            lines.append(
                _summary_line(
                    name,
                    summary,
                )
            )

    lines.extend(
        [
            "",
            "INTERPRETATION",
            "- Promotion evidence should use PRIMARY scope, not ENTRY_RESCUE or legacy-unscoped rows.",
            "- ENTRY_RESCUE is a separate cohort for low-RR setups where entry improvement could repair geometry.",
            "- Filled Setup Win rate alone is not sufficient for promotion.",
            "- Opportunity capture penalizes better-entry policies that miss original Setup Wins.",
            "- Positive MAE improvement means the hypothetical fill reduced adverse excursion.",
            "- Positive RR improvement means the same original SL/TP geometry improved from the hypothetical entry.",
            "- Parent-terminal lifecycle normalization prevents stale WAITING_FILL/FILLED_TRACKING states from biasing evaluation.",
            "- All results remain observer/evaluation only.",
        ]
    )

    return "\n".join(
        lines
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate Better Entry Optimizer V1.3 counterfactual outcomes."
        )
    )
    parser.add_argument(
        "--path",
        default=None,
        help=(
            "Optional setup_outcomes.json path. "
            "Defaults to current account canonical local file."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="local_reports",
    )

    args = parser.parse_args()

    path = (
        Path(
            args.path
        )
        if args.path
        else Path(
            get_setup_outcomes_file()
        )
    )

    rows = _load_rows(
        path
    )
    report = build_report(
        rows
    )
    text = format_report(
        report
    )

    output_dir = Path(
        args.output_dir
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = (
        output_dir
        / "better_entry_optimizer_counterfactual_evaluation.json"
    )
    text_path = (
        output_dir
        / "better_entry_optimizer_counterfactual_evaluation.txt"
    )

    json_path.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    text_path.write_text(
        text.rstrip()
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(
        text
    )
    print("")
    print(
        f"JSON: {json_path}"
    )
    print(
        f"TEXT: {text_path}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
