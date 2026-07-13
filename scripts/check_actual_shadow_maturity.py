import argparse
import json
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


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
        "shadow_policy_report": output_dir / "phase2_shadow_policy_report.json",
        "shadow_readiness_report": output_dir / "phase2_shadow_readiness_report.json",
        "report_json": output_dir / "actual_shadow_maturity_report.json",
    }


def read_json(path, default=None):
    path = Path(path)

    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def has_shadow_fields(row):
    return bool(
        row.get("shadow_decision")
        or row.get("shadow_action")
        or row.get("shadow_score") is not None
        or row.get("shadow_policy_version")
    )


def make_unique_key(row):
    setup_id = row.get("setup_id")

    if setup_id:
        return str(setup_id)

    return "|".join([
        str(row.get("strategy") or "UNKNOWN"),
        str(row.get("signal") or "UNKNOWN"),
        str(row.get("setup_source_bucket") or row.get("execution_bucket") or "UNKNOWN"),
        str(row.get("created_at") or row.get("_line_no")),
    ])


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
        "shadow_blocking_allowed": row.get("shadow_blocking_allowed"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check maturity of actual persisted live shadow observations."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--min-actual-shadow-rows",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--min-actual-shadow-unique-setups",
        type=int,
        default=15,
    )

    parser.add_argument(
        "--latest",
        type=int,
        default=5,
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)

    rows = read_jsonl(paths["observations_file"])
    parsed = [row for row in rows if not row.get("_parse_error")]

    actual_shadow_rows = [
        row
        for row in parsed
        if has_shadow_fields(row)
    ]

    actual_shadow_unique_keys = sorted({
        make_unique_key(row)
        for row in actual_shadow_rows
    })

    shadow_policy_report = read_json(paths["shadow_policy_report"], default={}) or {}
    shadow_readiness_report = read_json(paths["shadow_readiness_report"], default={}) or {}

    actual_shadow_count = len(actual_shadow_rows)
    actual_shadow_unique_count = len(actual_shadow_unique_keys)

    actual_shadow_rows_ready = actual_shadow_count >= args.min_actual_shadow_rows
    actual_shadow_unique_ready = actual_shadow_unique_count >= args.min_actual_shadow_unique_setups

    live_shadow_maturity_ready = all([
        actual_shadow_rows_ready,
        actual_shadow_unique_ready,
    ])

    if not actual_shadow_rows:
        recommendation = "WAIT_FOR_ACTUAL_LIVE_SHADOW_ROWS"
    elif not actual_shadow_rows_ready:
        recommendation = "COLLECT_MORE_ACTUAL_SHADOW_ROWS"
    elif not actual_shadow_unique_ready:
        recommendation = "COLLECT_MORE_UNIQUE_ACTUAL_SHADOW_SETUPS"
    elif not shadow_readiness_report.get("blocking_ready"):
        recommendation = "ACTUAL_SHADOW_MATURE_BUT_BLOCKING_STILL_NOT_READY"
    else:
        recommendation = "ACTUAL_SHADOW_MATURE_AND_READY_FOR_MANUAL_BLOCKING_REVIEW"

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2U",
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "live_shadow_maturity_ready": live_shadow_maturity_ready,
        "recommendation": recommendation,
        "counts": {
            "raw_observation_count": len(parsed),
            "actual_shadow_observation_count": actual_shadow_count,
            "actual_shadow_unique_setup_count": actual_shadow_unique_count,
            "legacy_or_missing_shadow_count": max(0, len(parsed) - actual_shadow_count),
            "min_actual_shadow_rows": args.min_actual_shadow_rows,
            "min_actual_shadow_unique_setups": args.min_actual_shadow_unique_setups,
            "actual_shadow_rows_ready": actual_shadow_rows_ready,
            "actual_shadow_unique_ready": actual_shadow_unique_ready,
            "global_unique_setup_count": shadow_policy_report.get("unique_setup_count"),
            "global_clean_known_outcome_count": shadow_policy_report.get("clean_known_outcome_count_unique"),
            "global_blocking_ready": shadow_readiness_report.get("blocking_ready"),
        },
        "latest_actual_shadow_rows": [
            compact_row(row)
            for row in actual_shadow_rows[-args.latest:]
        ],
        "generated_files": {
            "report_json": str(paths["report_json"]),
        },
        "notes": [
            "Actual shadow rows are rows persisted with shadow_decision/shadow_score after Phase 2M.",
            "Old observations can be backfilled analytically, but actual shadow maturity tracks live persisted evidence only.",
            "This script does not modify live trading behavior.",
            "Blocking remains disabled.",
        ],
    }

    write_json(paths["report_json"], report)

    print("[PHASE 2U ACTUAL SHADOW MATURITY]")
    print("live_shadow_maturity_ready =", live_shadow_maturity_ready)
    print("recommendation =", recommendation)

    print()
    print("[COUNTS]")
    for key, value in report["counts"].items():
        print(f"{key} = {value}")

    print()
    print("[LATEST ACTUAL SHADOW ROWS]")
    for row in report["latest_actual_shadow_rows"]:
        print(
            f"line={row.get('line_no')} "
            f"setup_id={row.get('setup_id')} "
            f"strategy={row.get('strategy')} "
            f"signal={row.get('signal')} "
            f"confidence={row.get('confidence')} "
            f"score_delta={row.get('score_delta')} "
            f"shadow={row.get('shadow_decision')} "
            f"shadow_score={row.get('shadow_score')} "
            f"action={row.get('shadow_action')} "
            f"blocking_allowed={row.get('shadow_blocking_allowed')}"
        )

    print()
    print("report =", paths["report_json"])


if __name__ == "__main__":
    main()
