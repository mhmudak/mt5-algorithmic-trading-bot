import argparse
import json
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_json(path):
    path = Path(path)

    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)

    return path


def resolve_paths(source_dir):
    source_dir = Path(source_dir)

    if not source_dir.is_absolute():
        source_dir = PROJECT_ROOT / source_dir

    account_name = source_dir.name
    output_dir = PROJECT_ROOT / "data" / "strategy_intelligence" / account_name

    return {
        "source_dir": source_dir,
        "account_name": account_name,
        "output_dir": output_dir,
        "phase1_validation_report": output_dir / "phase1_confirmation_validation_report.json",
        "coverage_summary": output_dir / "confirmation_coverage_summary.json",
        "runtime_safety_report": output_dir / "confirmation_runtime_safety_report.json",
        "phase2_readiness_report": output_dir / "phase2_readiness_report.json",
        "shadow_policy_report": output_dir / "phase2_shadow_policy_report.json",
        "shadow_readiness_report": output_dir / "phase2_shadow_readiness_report.json",
    }


def safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def pct(numerator, denominator):
    if not denominator:
        return None

    return round(float(numerator) / float(denominator), 4)


def check_pass(value):
    return "PASS" if value else "FAIL"


def main():
    parser = argparse.ArgumentParser(
        description="Phase 2E readiness gate for shadow confirmation policy."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--min-unique-setups",
        type=int,
        default=30,
    )

    parser.add_argument(
        "--min-clean-known-outcomes",
        type=int,
        default=10,
    )

    parser.add_argument(
        "--max-mixed-outcome-rate",
        type=float,
        default=0.10,
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if blocking readiness is false.",
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)

    phase1 = load_json(paths["phase1_validation_report"]) or {}
    coverage = load_json(paths["coverage_summary"]) or {}
    runtime_safety = load_json(paths["runtime_safety_report"]) or {}
    phase2_base = load_json(paths["phase2_readiness_report"]) or {}
    shadow_report = load_json(paths["shadow_policy_report"]) or {}

    raw_observation_count = safe_int(shadow_report.get("raw_observation_count"))
    unique_setup_count = safe_int(shadow_report.get("unique_setup_count"))
    duplicate_observation_count = safe_int(shadow_report.get("duplicate_observation_count"))

    known_outcome_unique = safe_int(shadow_report.get("known_outcome_count_unique"))
    clean_known_unique = safe_int(shadow_report.get("clean_known_outcome_count_unique"))
    mixed_unique = safe_int(shadow_report.get("mixed_tp_sl_count_unique"))
    quality_issue_count = safe_int(shadow_report.get("outcome_quality_issue_count"))

    mixed_rate_on_known = pct(mixed_unique, known_outcome_unique)
    duplicate_rate = pct(duplicate_observation_count, raw_observation_count)

    infrastructure_ready = all([
        phase1.get("all_ok") is True,
        runtime_safety.get("all_ok") is True,
        coverage.get("coverage_rate") == 1.0,
        coverage.get("missing_observe_before_execute_trade_count") == 0,
    ])

    shadow_report_exists = bool(shadow_report)

    checks = {
        "infrastructure_ready": infrastructure_ready,
        "shadow_report_exists": shadow_report_exists,
        "unique_setup_minimum_met": unique_setup_count >= args.min_unique_setups,
        "clean_known_outcomes_minimum_met": clean_known_unique >= args.min_clean_known_outcomes,
        "mixed_outcome_rate_acceptable": (
            mixed_rate_on_known is not None
            and mixed_rate_on_known <= args.max_mixed_outcome_rate
        ),
        "no_outcome_quality_issues": quality_issue_count == 0,
    }

    shadow_monitoring_ready = all([
        checks["infrastructure_ready"],
        checks["shadow_report_exists"],
        raw_observation_count > 0,
        unique_setup_count > 0,
    ])

    shadow_calibration_ready = all([
        shadow_monitoring_ready,
        checks["unique_setup_minimum_met"],
        checks["clean_known_outcomes_minimum_met"],
        checks["mixed_outcome_rate_acceptable"],
    ])

    blocking_ready = all([
        shadow_calibration_ready,
        checks["no_outcome_quality_issues"],
    ])

    if not infrastructure_ready:
        recommendation = "FIX_INFRASTRUCTURE_FIRST"
    elif not shadow_report_exists:
        recommendation = "RUN_ANALYZE_CONFIRMATION_SHADOW_POLICY_FIRST"
    elif not shadow_monitoring_ready:
        recommendation = "COLLECT_LIVE_OBSERVATIONS"
    elif not checks["unique_setup_minimum_met"]:
        recommendation = "KEEP_COLLECTING_UNIQUE_SETUPS"
    elif not checks["clean_known_outcomes_minimum_met"]:
        recommendation = "KEEP_COLLECTING_CLEAN_OUTCOMES"
    elif not checks["mixed_outcome_rate_acceptable"] or not checks["no_outcome_quality_issues"]:
        recommendation = "FIX_OR_REVIEW_OUTCOME_QUALITY_BEFORE_BLOCKING"
    elif not blocking_ready:
        recommendation = "SHADOW_CALIBRATION_READY_BLOCKING_STILL_NEEDS_REVIEW"
    else:
        recommendation = "BLOCKING_REVIEW_CAN_START_CAREFULLY"

    next_actions = []

    if not shadow_report_exists:
        next_actions.append(
            "Run scripts/analyze_confirmation_shadow_policy.py before this readiness check."
        )

    if unique_setup_count < args.min_unique_setups:
        next_actions.append(
            f"Collect more unique setups: current={unique_setup_count}, required={args.min_unique_setups}."
        )

    if clean_known_unique < args.min_clean_known_outcomes:
        next_actions.append(
            f"Collect more clean known outcomes: current={clean_known_unique}, required={args.min_clean_known_outcomes}."
        )

    if mixed_rate_on_known is not None and mixed_rate_on_known > args.max_mixed_outcome_rate:
        next_actions.append(
            f"Mixed outcome rate too high: current={mixed_rate_on_known}, max={args.max_mixed_outcome_rate}."
        )

    if quality_issue_count > 0:
        next_actions.append(
            f"Review outcome quality issues: current={quality_issue_count}. Check confirmation_shadow_outcome_quality.csv."
        )

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2E",
        "account_name": paths["account_name"],
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "shadow_monitoring_ready": shadow_monitoring_ready,
        "shadow_calibration_ready": shadow_calibration_ready,
        "blocking_ready": blocking_ready,
        "recommendation": recommendation,
        "checks": checks,
        "counts": {
            "raw_observation_count": raw_observation_count,
            "unique_setup_count": unique_setup_count,
            "duplicate_observation_count": duplicate_observation_count,
            "duplicate_rate": duplicate_rate,
            "known_outcome_count_unique": known_outcome_unique,
            "clean_known_outcome_count_unique": clean_known_unique,
            "mixed_tp_sl_count_unique": mixed_unique,
            "mixed_outcome_rate_on_known": mixed_rate_on_known,
            "outcome_quality_issue_count": quality_issue_count,
            "min_unique_setups": args.min_unique_setups,
            "min_clean_known_outcomes": args.min_clean_known_outcomes,
            "max_mixed_outcome_rate": args.max_mixed_outcome_rate,
        },
        "phase2_base": {
            "infrastructure_ready": phase2_base.get("infrastructure_ready"),
            "shadow_phase2_ready": phase2_base.get("shadow_phase2_ready"),
            "data_phase2_ready": phase2_base.get("data_phase2_ready"),
            "blocking_phase2_ready": phase2_base.get("blocking_phase2_ready"),
            "recommendation": phase2_base.get("recommendation"),
        },
        "next_actions": next_actions,
        "notes": [
            "Shadow monitoring means Phase 2A/2B can keep running.",
            "Shadow calibration means labels have enough clean outcomes to begin serious analysis.",
            "Blocking readiness remains false until clean outcomes are sufficient and outcome quality issues are resolved.",
            "This script does not block trades and does not modify live_bot.",
        ],
    }

    write_json(paths["shadow_readiness_report"], report)

    print("[PHASE 2E SHADOW READINESS]")
    print("shadow_monitoring_ready =", shadow_monitoring_ready)
    print("shadow_calibration_ready =", shadow_calibration_ready)
    print("blocking_ready =", blocking_ready)
    print("recommendation =", recommendation)

    print()
    print("[COUNTS]")
    for key, value in report["counts"].items():
        print(f"{key} = {value}")

    print()
    print("[CHECKS]")
    for key, value in checks.items():
        print(f"{key} = {check_pass(value)}")

    if next_actions:
        print()
        print("[NEXT ACTIONS]")
        for item in next_actions:
            print("-", item)

    print()
    print("report =", paths["shadow_readiness_report"])

    if args.strict and not blocking_ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
