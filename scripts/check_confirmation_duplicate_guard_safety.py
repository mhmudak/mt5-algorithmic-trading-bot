import argparse
import json
import tempfile
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.confirmation_observation_logger import (
    CONFIRMATION_OBSERVATION_DUPLICATE_GUARD_ENABLED,
    CONFIRMATION_OBSERVATION_DUPLICATE_LOOKBACK_ROWS,
    log_confirmation_observation,
    read_confirmation_observations,
)


def resolve_paths(source_dir):
    source_dir = Path(source_dir)

    if not source_dir.is_absolute():
        source_dir = PROJECT_ROOT / source_dir

    account_name = source_dir.name
    output_dir = PROJECT_ROOT / "data" / "strategy_intelligence" / account_name
    output_dir.mkdir(parents=True, exist_ok=True)

    return {
        "source_dir": source_dir,
        "account_name": account_name,
        "output_dir": output_dir,
        "report_json": output_dir / "confirmation_duplicate_guard_safety_report.json",
    }


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)

    return path


def run_duplicate_test():
    tmp = Path(tempfile.gettempdir()) / "confirmation_duplicate_guard_safety_test.jsonl"

    try:
        tmp.unlink()
    except FileNotFoundError:
        pass

    report = {
        "engine_version": "test",
        "mode": "MT5_ONLY",
        "approved": True,
        "confidence": 75,
        "score_delta": 4,
        "shadow_decision": "SUPPORT",
        "shadow_score": 95,
        "shadow_action": "OBSERVE_ONLY",
        "shadow_blocking_allowed": False,
        "strategy": "FAILED_FVG_REVERSAL",
        "signal": "BUY",
        "setup_id": "TEST-DUPLICATE-GUARD-SAFETY",
        "results": [],
    }

    trade_plan = {
        "entry_price": 1.0,
        "stop_loss": 0.5,
        "take_profit": 2.0,
    }

    for _ in range(3):
        log_confirmation_observation(
            report=report,
            trade_plan=trade_plan,
            setup_source_bucket="INTRABAR",
            notes="duplicate guard safety test",
            file_path=tmp,
        )

    rows = read_confirmation_observations(source_file=tmp)

    try:
        tmp.unlink()
    except Exception:
        pass

    return {
        "temp_file": str(tmp),
        "attempted_write_count": 3,
        "actual_row_count": len(rows),
        "duplicate_guard_worked": len(rows) == 1,
        "first_row": rows[0] if rows else None,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Safety check for confirmation observation duplicate guard."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)

    duplicate_test = run_duplicate_test()

    checks = {
        "duplicate_guard_enabled": CONFIRMATION_OBSERVATION_DUPLICATE_GUARD_ENABLED is True,
        "lookback_rows_positive": int(CONFIRMATION_OBSERVATION_DUPLICATE_LOOKBACK_ROWS) > 0,
        "temp_duplicate_test_passed": duplicate_test.get("duplicate_guard_worked") is True,
        "actual_row_count_is_one": duplicate_test.get("actual_row_count") == 1,
    }

    all_ok = all(checks.values())

    if all_ok:
        recommendation = "CONFIRMATION_DUPLICATE_GUARD_SAFETY_CONFIRMED"
    else:
        recommendation = "REVIEW_CONFIRMATION_DUPLICATE_GUARD"

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2AI",
        "source_dir": str(paths["source_dir"]),
        "all_ok": all_ok,
        "recommendation": recommendation,
        "checks": checks,
        "settings": {
            "CONFIRMATION_OBSERVATION_DUPLICATE_GUARD_ENABLED": CONFIRMATION_OBSERVATION_DUPLICATE_GUARD_ENABLED,
            "CONFIRMATION_OBSERVATION_DUPLICATE_LOOKBACK_ROWS": CONFIRMATION_OBSERVATION_DUPLICATE_LOOKBACK_ROWS,
        },
        "duplicate_test": duplicate_test,
        "generated_files": {
            "report_json": str(paths["report_json"]),
        },
        "notes": [
            "This safety check writes only to a temporary file.",
            "It does not modify live confirmation_observations.jsonl.",
            "It confirms repeated observations of the same setup are written once only.",
        ],
    }

    write_json(paths["report_json"], report)

    print("[PHASE 2AI CONFIRMATION DUPLICATE GUARD SAFETY]")
    print("all_ok =", all_ok)
    print("recommendation =", recommendation)

    print()
    print("[CHECKS]")
    for key, value in checks.items():
        print(f"{key} = {value}")

    print()
    print("[TEMP DUPLICATE TEST]")
    print("attempted_write_count =", duplicate_test.get("attempted_write_count"))
    print("actual_row_count =", duplicate_test.get("actual_row_count"))
    print("duplicate_guard_worked =", duplicate_test.get("duplicate_guard_worked"))

    print()
    print("report =", paths["report_json"])

    if args.strict and not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
