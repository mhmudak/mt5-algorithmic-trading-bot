from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

PHASE = "PHASE_5AI_SETUP_CONFLICT_ACTIVATION_READINESS"

DEFAULT_ACCOUNT_DIR = ROOT / "data" / "accounts" / "Tickmill-Demo_25323531"
PHASE5AH_DIR = ROOT / "data" / "strategy_intelligence" / "phase5ah_setup_conflicts"

OUT_JSON = PHASE5AH_DIR / "phase5ai_setup_conflict_activation_readiness.json"
OUT_TXT = PHASE5AH_DIR / "phase5ai_setup_conflict_activation_readiness_summary.txt"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def load_json_any(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append(dict(row))
    except Exception:
        return []

    return rows


def flatten_json_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]

    if isinstance(payload, dict):
        rows: list[dict[str, Any]] = []

        for key, value in payload.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("setup_id", key)
                rows.append(row)
            elif isinstance(value, list):
                rows.extend([x for x in value if isinstance(x, dict)])

        return rows

    return []


def latest_existing(paths: list[Path]) -> Path | None:
    existing = [p for p in paths if p.exists()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def infer_family(row: dict[str, Any]) -> str:
    text = "|".join(
        [
            safe_text(row.get("strategy")),
            safe_text(row.get("entry_model")),
            safe_text(row.get("type")),
            safe_text(row.get("trigger")),
            safe_text(row.get("reason")),
            safe_text(row.get("rejection_reason")),
            safe_text(row.get("source_events")),
        ]
    ).upper()

    if "MICRO_SR_SWEEP_RECLAIM" in text or "SWEEP_RECLAIM" in text:
        return "SWEEP_RECLAIM"

    if "FAILED_FVG_REVERSAL" in text or "FAILED_FVG" in text:
        return "FAILED_FVG_REVERSAL"

    if "KEY_LEVEL_BREAK_HOLD" in text or "BREAK_HOLD" in text:
        return "BREAK_HOLD"

    if "ORDER_BLOCK" in text or "MTF_OB" in text or "OB_ENTRY" in text:
        return "ORDER_BLOCK"

    if "PRO_TRADER_REPLICATION" in text:
        return "PRO_TRADER_REPLICATION"

    if "ORB" in text:
        return "ORB"

    if "INTRABAR" in text or "TICK_SNIPER" in text:
        return "INTRABAR"

    return safe_text(row.get("strategy")).upper() or "UNKNOWN"


def normalize_direction(value: Any) -> str:
    text = safe_text(value).upper()
    if text in {"BUY", "LONG", "BULLISH"}:
        return "BUY"
    if text in {"SELL", "SHORT", "BEARISH"}:
        return "SELL"
    return ""


def normalize_outcome(row: dict[str, Any]) -> str:
    text = "|".join(
        [
            safe_text(row.get("final_outcome")),
            safe_text(row.get("outcome")),
            safe_text(row.get("result")),
            safe_text(row.get("status")),
            safe_text(row.get("decision")),
        ]
    ).upper()

    if any(x in text for x in ["TP", "WIN", "PROFIT", "PROFITABLE"]):
        return "WIN"

    if any(x in text for x in ["SL", "LOSS", "STOP"]):
        return "LOSS"

    if any(x in text for x in ["BE", "BREAKEVEN"]):
        return "BE"

    return "UNKNOWN"


def row_profit(row: dict[str, Any]) -> float:
    for key in [
        "realized_profit",
        "profit",
        "pnl",
        "net_profit",
        "max_favorable_excursion",
        "mfe",
    ]:
        if key in row:
            return safe_float(row.get(key))

    outcome = normalize_outcome(row)
    if outcome == "WIN":
        return 1.0
    if outcome == "LOSS":
        return -1.0
    return 0.0


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    family_counts = Counter()
    strategy_counts = Counter()
    outcome_counts = Counter()
    source_bucket_counts = Counter()

    profit_sum = 0.0
    profit_known = 0
    wins = 0
    losses = 0
    bes = 0

    for row in rows:
        family = infer_family(row)
        strategy = safe_text(row.get("strategy")).upper() or "UNKNOWN"
        outcome = normalize_outcome(row)
        source_bucket = safe_text(row.get("setup_source_bucket") or row.get("source_bucket")).upper()

        family_counts[family] += 1
        strategy_counts[strategy] += 1
        outcome_counts[outcome] += 1
        if source_bucket:
            source_bucket_counts[source_bucket] += 1

        p = row_profit(row)
        if p != 0:
            profit_sum += p
            profit_known += 1

        if outcome == "WIN":
            wins += 1
        elif outcome == "LOSS":
            losses += 1
        elif outcome == "BE":
            bes += 1

    decisive = wins + losses
    win_rate = wins / decisive if decisive else None
    avg_profit = profit_sum / profit_known if profit_known else None

    return {
        "row_count": len(rows),
        "family_counts": dict(family_counts.most_common()),
        "strategy_counts": dict(strategy_counts.most_common(20)),
        "outcome_counts": dict(outcome_counts.most_common()),
        "source_bucket_counts": dict(source_bucket_counts.most_common()),
        "wins": wins,
        "losses": losses,
        "breakeven": bes,
        "decisive_count": decisive,
        "win_rate": win_rate,
        "profit_known_count": profit_known,
        "profit_sum": profit_sum,
        "avg_profit": avg_profit,
    }


def filter_phase5ah_priority_conflicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []

    for row in rows:
        if row.get("priority_conflict_review") is True:
            out.append(row)
            continue

        text = json.dumps(row, default=str).upper()
        if "DIRECTIONAL_CONFLICT_SAME_ZONE_PRIORITY_REVIEW" in text:
            out.append(row)

    return out


def filter_micro_sweep_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if infer_family(row) == "SWEEP_RECLAIM"]


def filter_rejected_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []

    for row in rows:
        text = json.dumps(row, default=str).upper()
        if (
            "REJECTED_CANDIDATE_TRACKED" in text
            or "SCORE_TOO_LOW" in text
            or "REJECTED_SCORE_TOO_LOW" in text
            or "STRONG REJECTED" in text
        ):
            out.append(row)

    return out


def build_readiness(
    *,
    setup_summary: dict[str, Any],
    rejected_summary: dict[str, Any],
    micro_summary: dict[str, Any],
    phase5ah_summary: dict[str, Any],
    min_phase5ah_conflicts: int,
    min_rejected_micro_samples: int,
    min_win_rate: float,
) -> dict[str, Any]:
    passed = []
    failed = []

    phase5ah_priority_count = phase5ah_summary["row_count"]
    rejected_micro_count = micro_summary["row_count"]

    rejected_micro_win_rate = micro_summary.get("win_rate")
    rejected_micro_avg_profit = micro_summary.get("avg_profit")

    if phase5ah_priority_count >= min_phase5ah_conflicts:
        passed.append("phase5ah_live_priority_conflict_samples_ok")
    else:
        failed.append("phase5ah_live_priority_conflict_samples_too_low")

    if rejected_micro_count >= min_rejected_micro_samples:
        passed.append("rejected_micro_sweep_samples_ok")
    else:
        failed.append("rejected_micro_sweep_samples_too_low")

    if rejected_micro_win_rate is not None and rejected_micro_win_rate >= min_win_rate:
        passed.append("rejected_micro_sweep_win_rate_ok")
    else:
        failed.append("rejected_micro_sweep_win_rate_not_proven")

    if rejected_micro_avg_profit is not None and rejected_micro_avg_profit > 0:
        passed.append("rejected_micro_sweep_expectancy_positive")
    else:
        failed.append("rejected_micro_sweep_expectancy_not_proven")

    # Activation levels:
    # - Observe-only if no live Phase5AH conflicts yet.
    # - Shadow decision only if enough historical rejected micro proof but not enough live Phase5AH.
    # - Decision influence only after both historical and live conflict proof.
    can_shadow_decision = (
        rejected_micro_count >= min_rejected_micro_samples
        and (
            rejected_micro_avg_profit is not None
            and rejected_micro_avg_profit > 0
        )
    )

    can_influence_decision = (
        can_shadow_decision
        and phase5ah_priority_count >= min_phase5ah_conflicts
        and rejected_micro_win_rate is not None
        and rejected_micro_win_rate >= min_win_rate
    )

    if can_influence_decision:
        readiness_status = "READY_FOR_CONTROLLED_DECISION_INFLUENCE_REVIEW"
        next_stage = "STAGE_3_REVIEW_ONLY_BEFORE_ENABLE"
        recommendation = (
            "Statistics meet minimum gate, but do not enable automatically. "
            "Review sample quality manually, then stage a separate feature flag."
        )
    elif can_shadow_decision:
        readiness_status = "READY_FOR_SHADOW_DECISION_ONLY"
        next_stage = "STAGE_1_SHADOW_DECISION"
        recommendation = (
            "Historical evidence may be enough to start shadow decisions, but not execution influence. "
            "Phase5AH needs live conflict samples first."
        )
    else:
        readiness_status = "NOT_READY_KEEP_OBSERVE_ONLY"
        next_stage = "STAGE_0_OBSERVE_ONLY"
        recommendation = (
            "Keep observe-only. Need more live Phase5AH conflicts and stronger rejected micro-sweep outcome proof."
        )

    return {
        "readiness_status": readiness_status,
        "next_stage": next_stage,
        "can_shadow_decision": can_shadow_decision,
        "can_influence_decision": False,
        "can_auto_execute": False,
        "raw_can_influence_decision_statistically": can_influence_decision,
        "passed": passed,
        "failed": failed,
        "recommendation": recommendation,
        "industrial_rule": (
            "This script never enables live execution. It only says whether a separate controlled feature flag "
            "may be considered after manual review."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-dir", default=str(DEFAULT_ACCOUNT_DIR))
    parser.add_argument("--min-phase5ah-conflicts", type=int, default=20)
    parser.add_argument("--min-rejected-micro-samples", type=int, default=20)
    parser.add_argument("--min-win-rate", type=float, default=0.55)
    args = parser.parse_args()

    account_dir = Path(args.account_dir)

    setup_outcomes_path = latest_existing(
        [
            account_dir / "setup_outcomes.json",
            ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531" / "setup_outcomes.json",
        ]
    )

    trades_path = latest_existing(
        [
            account_dir / "trades.json",
        ]
    )

    missed_rejected_path = latest_existing(
        [
            ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531" / "missed_profitable_rejected_candidates.csv",
            account_dir / "missed_profitable_rejected_candidates.csv",
        ]
    )

    phase5ah_conflicts_path = PHASE5AH_DIR / "phase5ah_setup_conflicts.json"

    setup_rows = flatten_json_records(load_json_any(setup_outcomes_path, [])) if setup_outcomes_path else []
    trade_rows = flatten_json_records(load_json_any(trades_path, [])) if trades_path else []
    missed_rejected_rows = load_csv_rows(missed_rejected_path) if missed_rejected_path else []
    phase5ah_rows = flatten_json_records(load_json_any(phase5ah_conflicts_path, []))

    all_historical_rows = setup_rows + missed_rejected_rows
    rejected_rows = filter_rejected_rows(all_historical_rows)
    rejected_micro_rows = filter_micro_sweep_rows(rejected_rows)
    phase5ah_priority_rows = filter_phase5ah_priority_conflicts(phase5ah_rows)

    setup_summary = summarize_rows(setup_rows)
    trades_summary = summarize_rows(trade_rows)
    rejected_summary = summarize_rows(rejected_rows)
    rejected_micro_summary = summarize_rows(rejected_micro_rows)
    phase5ah_summary = summarize_rows(phase5ah_priority_rows)

    readiness = build_readiness(
        setup_summary=setup_summary,
        rejected_summary=rejected_summary,
        micro_summary=rejected_micro_summary,
        phase5ah_summary=phase5ah_summary,
        min_phase5ah_conflicts=args.min_phase5ah_conflicts,
        min_rejected_micro_samples=args.min_rejected_micro_samples,
        min_win_rate=args.min_win_rate,
    )

    report = {
        "phase": PHASE,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "AUDIT_ONLY",
        "decision_impact": "NONE",
        "execution_change": "NONE",
        "account_dir": str(account_dir),
        "inputs": {
            "setup_outcomes_path": str(setup_outcomes_path) if setup_outcomes_path else None,
            "trades_path": str(trades_path) if trades_path else None,
            "missed_rejected_path": str(missed_rejected_path) if missed_rejected_path else None,
            "phase5ah_conflicts_path": str(phase5ah_conflicts_path) if phase5ah_conflicts_path.exists() else None,
        },
        "thresholds": {
            "min_phase5ah_conflicts": args.min_phase5ah_conflicts,
            "min_rejected_micro_samples": args.min_rejected_micro_samples,
            "min_win_rate": args.min_win_rate,
        },
        "summaries": {
            "setup_outcomes": setup_summary,
            "trades": trades_summary,
            "rejected_candidates": rejected_summary,
            "rejected_micro_sweep_reclaim": rejected_micro_summary,
            "phase5ah_priority_conflicts": phase5ah_summary,
        },
        "readiness": readiness,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "[PHASE 5AI SETUP CONFLICT ACTIVATION READINESS]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"decision_impact = {report['decision_impact']}",
        f"execution_change = {report['execution_change']}",
        "",
        "[INPUTS]",
        f"setup_outcomes_path = {report['inputs']['setup_outcomes_path']}",
        f"trades_path = {report['inputs']['trades_path']}",
        f"missed_rejected_path = {report['inputs']['missed_rejected_path']}",
        f"phase5ah_conflicts_path = {report['inputs']['phase5ah_conflicts_path']}",
        "",
        "[THRESHOLDS]",
        f"min_phase5ah_conflicts = {args.min_phase5ah_conflicts}",
        f"min_rejected_micro_samples = {args.min_rejected_micro_samples}",
        f"min_win_rate = {args.min_win_rate}",
        "",
        "[SUMMARY]",
        f"setup_outcomes_total = {setup_summary['row_count']}",
        f"trades_total = {trades_summary['row_count']}",
        f"rejected_candidates_total = {rejected_summary['row_count']}",
        f"rejected_micro_sweep_total = {rejected_micro_summary['row_count']}",
        f"phase5ah_priority_conflicts_total = {phase5ah_summary['row_count']}",
        "",
        "[REJECTED MICRO SWEEP]",
        f"wins = {rejected_micro_summary['wins']}",
        f"losses = {rejected_micro_summary['losses']}",
        f"breakeven = {rejected_micro_summary['breakeven']}",
        f"decisive_count = {rejected_micro_summary['decisive_count']}",
        f"win_rate = {rejected_micro_summary['win_rate']}",
        f"profit_known_count = {rejected_micro_summary['profit_known_count']}",
        f"avg_profit = {rejected_micro_summary['avg_profit']}",
        "",
        "[READINESS]",
        f"readiness_status = {readiness['readiness_status']}",
        f"next_stage = {readiness['next_stage']}",
        f"can_shadow_decision = {readiness['can_shadow_decision']}",
        f"can_influence_decision = {readiness['can_influence_decision']}",
        f"raw_can_influence_decision_statistically = {readiness['raw_can_influence_decision_statistically']}",
        f"can_auto_execute = {readiness['can_auto_execute']}",
        "",
        "[PASSED]",
        *[f"- {x}" for x in readiness["passed"]],
        "",
        "[FAILED]",
        *[f"- {x}" for x in readiness["failed"]],
        "",
        "[RECOMMENDATION]",
        readiness["recommendation"],
        "",
        "[INDUSTRIAL RULE]",
        readiness["industrial_rule"],
        "",
        f"json = {OUT_JSON}",
        f"summary = {OUT_TXT}",
    ]

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()