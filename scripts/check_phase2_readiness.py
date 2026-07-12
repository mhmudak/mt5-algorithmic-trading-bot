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


def read_jsonl_count(path):
    path = Path(path)

    if not path.exists():
        return 0, 0

    total = 0
    errors = 0

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            total += 1

            try:
                json.loads(line)
            except Exception:
                errors += 1

    return total, errors


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
        "observations_file": source_dir / "confirmation_observations.jsonl",
        "phase1_validation_report": output_dir / "phase1_confirmation_validation_report.json",
        "runtime_safety_report": output_dir / "confirmation_runtime_safety_report.json",
        "coverage_summary": output_dir / "confirmation_coverage_summary.json",
        "confirmation_summary": output_dir / "confirmation_observation_summary.json",
        "strategy_report": output_dir / "strategy_performance_report.json",
        "phase2_readiness_report": output_dir / "phase2_readiness_report.json",
    }


def get_confirmation_engine_from_strategy_report(strategy_report):
    if not isinstance(strategy_report, dict):
        return {}

    value = strategy_report.get("confirmation_engine")

    if isinstance(value, dict):
        return value

    return {}


def status(ok):
    return "PASS" if ok else "FAIL"


def main():
    parser = argparse.ArgumentParser(
        description="Check whether confirmation engine is ready for Phase 2."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
        help="Account data directory.",
    )

    parser.add_argument(
        "--min-observations",
        type=int,
        default=30,
        help="Minimum live observations required before Phase 2 analysis decisions.",
    )

    parser.add_argument(
        "--min-known-outcomes",
        type=int,
        default=10,
        help="Minimum known outcomes required before any blocking/weighting decision.",
    )

    parser.add_argument(
        "--min-module-rows",
        type=int,
        default=100,
        help="Minimum module rows required before module-level performance analysis.",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if Phase 2 is not fully ready.",
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)

    phase1_validation = load_json(paths["phase1_validation_report"]) or {}
    runtime_safety = load_json(paths["runtime_safety_report"]) or {}
    coverage = load_json(paths["coverage_summary"]) or {}
    confirmation_summary = load_json(paths["confirmation_summary"]) or {}
    strategy_report = load_json(paths["strategy_report"]) or {}
    strategy_confirmation = get_confirmation_engine_from_strategy_report(strategy_report)

    raw_observation_count, parse_error_count = read_jsonl_count(paths["observations_file"])

    analyzer_observation_count = confirmation_summary.get("observation_count") or 0
    module_row_count = confirmation_summary.get("module_row_count") or 0
    matched_outcome_count = confirmation_summary.get("matched_outcome_count") or 0
    known_outcome_count = confirmation_summary.get("known_outcome_count") or 0

    checks = {
        "phase1_validation_all_ok": phase1_validation.get("all_ok") is True,
        "runtime_safety_all_ok": runtime_safety.get("all_ok") is True,
        "coverage_full": (
            coverage.get("coverage_rate") == 1.0
            and coverage.get("missing_observe_before_execute_trade_count") == 0
        ),
        "strategy_report_has_confirmation_engine": bool(strategy_confirmation),
        "observation_file_parse_ok": parse_error_count == 0,
        "raw_live_observations_minimum_met": raw_observation_count >= args.min_observations,
        "analyzer_observations_minimum_met": analyzer_observation_count >= args.min_observations,
        "known_outcomes_minimum_met": known_outcome_count >= args.min_known_outcomes,
        "module_rows_minimum_met": module_row_count >= args.min_module_rows,
    }

    infrastructure_ready = all([
        checks["phase1_validation_all_ok"],
        checks["runtime_safety_all_ok"],
        checks["coverage_full"],
        checks["strategy_report_has_confirmation_engine"],
        checks["observation_file_parse_ok"],
    ])

    shadow_phase2_ready = infrastructure_ready

    data_phase2_ready = all([
        infrastructure_ready,
        checks["raw_live_observations_minimum_met"],
        checks["analyzer_observations_minimum_met"],
        checks["module_rows_minimum_met"],
    ])

    blocking_phase2_ready = all([
        data_phase2_ready,
        checks["known_outcomes_minimum_met"],
    ])

    if not infrastructure_ready:
        recommendation = "DO_NOT_START_PHASE_2_FIX_INFRASTRUCTURE_FIRST"
    elif not raw_observation_count:
        recommendation = "RUN_LIVE_BOT_OBSERVE_ONLY_FIRST"
    elif not data_phase2_ready:
        recommendation = "START_PHASE_2_SHADOW_ONLY_OR_KEEP_COLLECTING_DATA"
    elif not blocking_phase2_ready:
        recommendation = "PHASE_2_SHADOW_ANALYSIS_READY_BLOCKING_NOT_READY"
    else:
        recommendation = "PHASE_2_ANALYSIS_READY_BLOCKING_CAN_BE_DISCUSSSED_CAREFULLY"

    missing = []

    if not checks["phase1_validation_all_ok"]:
        missing.append("Run/fix scripts/validate_phase1_confirmation_engine.py until all_ok=True.")

    if not checks["runtime_safety_all_ok"]:
        missing.append("Run/fix scripts/check_confirmation_runtime_safety.py until all_ok=True.")

    if not checks["coverage_full"]:
        missing.append("Fix confirmation observe coverage until coverage_rate=1.0 and missing=0.")

    if not checks["strategy_report_has_confirmation_engine"]:
        missing.append("Run main analyzer so strategy_performance_report.json contains confirmation_engine.")

    if parse_error_count:
        missing.append("Fix malformed JSONL records in confirmation_observations.jsonl.")

    if raw_observation_count < args.min_observations:
        missing.append(
            f"Collect more live observations: current={raw_observation_count}, required={args.min_observations}."
        )

    if analyzer_observation_count < args.min_observations:
        missing.append(
            f"Run analyzer after live observations accumulate: analyzer_count={analyzer_observation_count}, required={args.min_observations}."
        )

    if module_row_count < args.min_module_rows:
        missing.append(
            f"Need more module rows for performance analysis: current={module_row_count}, required={args.min_module_rows}."
        )

    if known_outcome_count < args.min_known_outcomes:
        missing.append(
            f"Need more known outcomes before blocking decisions: current={known_outcome_count}, required={args.min_known_outcomes}."
        )

    report = {
        "created_at": datetime.now().isoformat(),
        "account_name": paths["account_name"],
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "phase": "Phase 1S",
        "infrastructure_ready": infrastructure_ready,
        "shadow_phase2_ready": shadow_phase2_ready,
        "data_phase2_ready": data_phase2_ready,
        "blocking_phase2_ready": blocking_phase2_ready,
        "recommendation": recommendation,
        "checks": checks,
        "counts": {
            "raw_observation_count": raw_observation_count,
            "parse_error_count": parse_error_count,
            "analyzer_observation_count": analyzer_observation_count,
            "module_row_count": module_row_count,
            "matched_outcome_count": matched_outcome_count,
            "known_outcome_count": known_outcome_count,
            "min_observations": args.min_observations,
            "min_known_outcomes": args.min_known_outcomes,
            "min_module_rows": args.min_module_rows,
        },
        "coverage": {
            "coverage_rate": coverage.get("coverage_rate"),
            "execute_trade_call_count": coverage.get("execute_trade_call_count"),
            "covered_execute_trade_call_count": coverage.get("covered_execute_trade_call_count"),
            "missing_observe_before_execute_trade_count": coverage.get("missing_observe_before_execute_trade_count"),
        },
        "strategy_report_confirmation_status": strategy_confirmation.get("status"),
        "missing_or_next_actions": missing,
        "notes": [
            "Phase 2 can be started in shadow-only mode once infrastructure is ready.",
            "Blocking/weighting should not start until enough real live observations and known outcomes exist.",
            "Current confirmation engine remains observe-only.",
            "A zero observation count usually means live_bot has not reached execute_trade paths yet.",
        ],
    }

    write_json(paths["phase2_readiness_report"], report)

    print("[PHASE 2 READINESS]")
    print("infrastructure_ready =", infrastructure_ready)
    print("shadow_phase2_ready =", shadow_phase2_ready)
    print("data_phase2_ready =", data_phase2_ready)
    print("blocking_phase2_ready =", blocking_phase2_ready)
    print("recommendation =", recommendation)
    print()
    print("[COUNTS]")
    for key, value in report["counts"].items():
        print(f"{key} = {value}")

    print()
    print("[CHECKS]")
    for key, ok in checks.items():
        print(f"{key} = {status(ok)}")

    if missing:
        print()
        print("[NEXT ACTIONS]")
        for item in missing:
            print("-", item)

    print()
    print("report =", paths["phase2_readiness_report"])

    if args.strict and not blocking_phase2_ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
