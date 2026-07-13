import argparse
import json
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.confirmation_shadow_policy import apply_confirmation_shadow_policy
from src.confirmation_observation_logger import build_confirmation_observation_record


def read_jsonl(path):
    path = Path(path)

    if not path.exists():
        return []

    rows = []

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                row = json.loads(line)
                row["_line_no"] = line_no
                rows.append(row)
            except Exception as exc:
                rows.append({
                    "_line_no": line_no,
                    "_parse_error": str(exc),
                    "_raw": line[:500],
                })

    return rows


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
    output_dir.mkdir(parents=True, exist_ok=True)

    return {
        "source_dir": source_dir,
        "account_name": account_name,
        "output_dir": output_dir,
        "observations_file": source_dir / "confirmation_observations.jsonl",
        "report_json": output_dir / "confirmation_shadow_persistence_report.json",
    }


def has_shadow_fields(row):
    return bool(
        row.get("shadow_decision")
        or row.get("shadow_action")
        or row.get("shadow_score") is not None
        or row.get("shadow_policy_version")
    )


def run_code_level_test():
    report = {
        "engine_version": "PERSISTENCE_TEST",
        "mode": "MT5_ONLY",
        "approved": True,
        "confidence": 83,
        "score_delta": 5.0,
        "summary": "shadow persistence validator test",
        "results": [
            {"module": "SETUP_SCHEMA", "status": "PASS", "score_delta": 0},
            {"module": "ENTRY_QUALITY", "status": "PASS", "score_delta": 2},
        ],
    }

    apply_confirmation_shadow_policy(report)

    record = build_confirmation_observation_record(
        report=report,
        signal_data={
            "setup_id": "TEST-SHADOW-PERSISTENCE",
            "strategy": "TEST",
            "signal": "BUY",
        },
        trade_plan={},
        setup_source_bucket="TEST",
        notes="shadow persistence validator",
    )

    required_fields = [
        "shadow_decision",
        "shadow_score",
        "shadow_action",
        "shadow_reason",
        "shadow_policy_version",
        "shadow_blocking_allowed",
    ]

    missing_fields = [
        field
        for field in required_fields
        if field not in record
    ]

    populated_fields = [
        field
        for field in required_fields
        if record.get(field) is not None
    ]

    ok = (
        report.get("shadow_decision") == "STRONG_SUPPORT"
        and record.get("shadow_decision") == "STRONG_SUPPORT"
        and record.get("shadow_action") == "OBSERVE_ONLY"
        and record.get("shadow_blocking_allowed") is False
        and not missing_fields
    )

    return {
        "ok": ok,
        "report_shadow_decision": report.get("shadow_decision"),
        "record_shadow_decision": record.get("shadow_decision"),
        "record_shadow_score": record.get("shadow_score"),
        "record_shadow_action": record.get("shadow_action"),
        "record_shadow_reason": record.get("shadow_reason"),
        "record_shadow_policy_version": record.get("shadow_policy_version"),
        "record_shadow_blocking_allowed": record.get("shadow_blocking_allowed"),
        "required_fields": required_fields,
        "missing_fields": missing_fields,
        "populated_fields": populated_fields,
    }


def compact_row(row):
    return {
        "line_no": row.get("_line_no"),
        "created_at": row.get("created_at"),
        "setup_id": row.get("setup_id"),
        "strategy": row.get("strategy"),
        "signal": row.get("signal"),
        "bucket": row.get("setup_source_bucket") or row.get("execution_bucket"),
        "confidence": row.get("confidence"),
        "score_delta": row.get("score_delta"),
        "shadow_decision": row.get("shadow_decision"),
        "shadow_score": row.get("shadow_score"),
        "shadow_action": row.get("shadow_action"),
        "shadow_reason": row.get("shadow_reason"),
        "shadow_blocking_allowed": row.get("shadow_blocking_allowed"),
        "shadow_keys": [key for key in row.keys() if "shadow" in key.lower()],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check whether confirmation shadow fields are persisted in observation records."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--latest",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if no live shadow observations exist.",
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)

    rows = read_jsonl(paths["observations_file"])
    parsed_rows = [row for row in rows if not row.get("_parse_error")]

    shadow_rows = [
        row
        for row in parsed_rows
        if has_shadow_fields(row)
    ]

    missing_shadow_rows = [
        row
        for row in parsed_rows
        if not has_shadow_fields(row)
    ]

    code_test = run_code_level_test()

    latest_rows = parsed_rows[-args.latest:] if parsed_rows else []
    latest_shadow_rows = shadow_rows[-args.latest:] if shadow_rows else []

    raw_count = len(parsed_rows)
    shadow_count = len(shadow_rows)
    missing_count = len(missing_shadow_rows)

    shadow_rate = round(shadow_count / raw_count, 4) if raw_count else 0.0

    code_level_ready = bool(code_test.get("ok"))
    live_shadow_observations_present = shadow_count > 0

    if not code_level_ready:
        recommendation = "FIX_SHADOW_PERSISTENCE_CODE"
    elif not live_shadow_observations_present:
        recommendation = "WAITING_FOR_NEW_LIVE_SHADOW_OBSERVATIONS"
    else:
        recommendation = "SHADOW_PERSISTENCE_CONFIRMED"

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2N",
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "code_level_ready": code_level_ready,
        "live_shadow_observations_present": live_shadow_observations_present,
        "recommendation": recommendation,
        "counts": {
            "raw_observation_count": raw_count,
            "shadow_populated_observation_count": shadow_count,
            "shadow_missing_observation_count": missing_count,
            "shadow_populated_rate": shadow_rate,
        },
        "code_test": code_test,
        "latest_rows": [compact_row(row) for row in latest_rows],
        "latest_shadow_rows": [compact_row(row) for row in latest_shadow_rows],
        "generated_files": {
            "report_json": str(paths["report_json"]),
        },
        "notes": [
            "Old observations logged before Phase 2M will not contain shadow fields.",
            "After restarting live_bot, the next new observation should contain shadow fields.",
            "This script does not modify live trading behavior.",
        ],
    }

    write_json(paths["report_json"], report)

    print("[PHASE 2N SHADOW PERSISTENCE]")
    print("code_level_ready =", code_level_ready)
    print("live_shadow_observations_present =", live_shadow_observations_present)
    print("recommendation =", recommendation)

    print()
    print("[COUNTS]")
    for key, value in report["counts"].items():
        print(f"{key} = {value}")

    print()
    print("[CODE TEST]")
    print("record_shadow_decision =", code_test.get("record_shadow_decision"))
    print("record_shadow_score =", code_test.get("record_shadow_score"))
    print("record_shadow_action =", code_test.get("record_shadow_action"))
    print("record_shadow_blocking_allowed =", code_test.get("record_shadow_blocking_allowed"))
    print("missing_fields =", code_test.get("missing_fields"))

    print()
    print("[LATEST ROWS]")
    for row in report["latest_rows"]:
        print(
            f"line={row.get('line_no')} "
            f"setup_id={row.get('setup_id')} "
            f"shadow={row.get('shadow_decision')} "
            f"score={row.get('shadow_score')}"
        )

    print()
    print("report =", paths["report_json"])

    if args.strict and not live_shadow_observations_present:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
