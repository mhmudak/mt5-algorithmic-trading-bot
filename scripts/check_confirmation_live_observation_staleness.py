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
        "report_json": output_dir / "confirmation_live_observation_staleness_report.json",
    }


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


def compact_row(row):
    return {
        "line_no": row.get("_line_no"),
        "created_at": row.get("created_at"),
        "setup_id": row.get("setup_id"),
        "strategy": row.get("strategy"),
        "signal": row.get("signal"),
        "bucket": row.get("setup_source_bucket") or row.get("execution_bucket"),
        "mode": row.get("mode"),
        "approved": row.get("approved"),
        "confidence": row.get("confidence"),
        "score_delta": row.get("score_delta"),
        "shadow_decision": row.get("shadow_decision"),
        "shadow_score": row.get("shadow_score"),
        "shadow_action": row.get("shadow_action"),
        "shadow_blocking_allowed": row.get("shadow_blocking_allowed"),
    }


def get_file_status(path, stale_minutes):
    path = Path(path)

    if not path.exists():
        return {
            "file_exists": False,
            "file_mtime": None,
            "file_age_minutes": None,
            "file_stale": True,
        }

    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    now = datetime.now()
    age_minutes = round((now - mtime).total_seconds() / 60.0, 2)

    return {
        "file_exists": True,
        "file_mtime": mtime.isoformat(timespec="seconds"),
        "file_age_minutes": age_minutes,
        "file_stale": age_minutes >= stale_minutes,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check whether live confirmation observation logging is stale."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--stale-minutes",
        type=int,
        default=60,
    )

    parser.add_argument(
        "--latest",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if observation file is stale.",
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)
    file_status = get_file_status(paths["observations_file"], args.stale_minutes)

    rows = read_jsonl(paths["observations_file"])
    parsed = [row for row in rows if not row.get("_parse_error")]
    parse_errors = [row for row in rows if row.get("_parse_error")]

    shadow_rows = [row for row in parsed if has_shadow_fields(row)]

    latest_rows = parsed[-args.latest:] if parsed else []
    latest_shadow_rows = shadow_rows[-args.latest:] if shadow_rows else []

    if not file_status["file_exists"]:
        status = "NO_OBSERVATION_FILE"
        recommendation = "START_OR_CHECK_LIVE_BOT"
    elif not parsed:
        status = "OBSERVATION_FILE_EMPTY"
        recommendation = "WAIT_FOR_FIRST_CONFIRMATION_OBSERVATION"
    elif shadow_rows:
        status = "SHADOW_PERSISTENCE_CONFIRMED"
        recommendation = "CONTINUE_COLLECTING_UNIQUE_SETUPS_AND_CLEAN_OUTCOMES"
    elif file_status["file_stale"]:
        status = "STALE_WAITING_FOR_NEW_OBSERVATION"
        recommendation = "CHECK_WINDOW_1_LIVE_BOT_OR_WAIT_FOR_MARKET_SETUP"
    else:
        status = "FRESH_BUT_WAITING_FOR_SHADOW_ROW"
        recommendation = "WAIT_FOR_NEXT_CONFIRMATION_OBSERVATION_AFTER_RESTART"

    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "phase": "Phase 2S",
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "status": status,
        "recommendation": recommendation,
        "file_status": file_status,
        "counts": {
            "raw_line_count": len(rows),
            "parsed_observation_count": len(parsed),
            "parse_error_count": len(parse_errors),
            "shadow_populated_observation_count": len(shadow_rows),
            "shadow_missing_observation_count": max(0, len(parsed) - len(shadow_rows)),
        },
        "latest_rows": [compact_row(row) for row in latest_rows],
        "latest_shadow_rows": [compact_row(row) for row in latest_shadow_rows],
        "generated_files": {
            "report_json": str(paths["report_json"]),
        },
        "notes": [
            "A stale file is not necessarily a bug. It may mean no setup was detected recently.",
            "Old rows before Phase 2M will not contain shadow fields.",
            "The next new row after live_bot restart should contain shadow fields.",
            "This script does not modify live trading behavior.",
        ],
    }

    write_json(paths["report_json"], report)

    print("[PHASE 2S LIVE OBSERVATION STALENESS]")
    print("status =", status)
    print("recommendation =", recommendation)

    print()
    print("[FILE]")
    print("observations_file =", paths["observations_file"])
    print("file_exists =", file_status["file_exists"])
    print("file_mtime =", file_status["file_mtime"])
    print("file_age_minutes =", file_status["file_age_minutes"])
    print("file_stale =", file_status["file_stale"])
    print("stale_threshold_minutes =", args.stale_minutes)

    print()
    print("[COUNTS]")
    for key, value in report["counts"].items():
        print(f"{key} = {value}")

    print()
    print("[LATEST]")
    for row in report["latest_rows"]:
        print(
            f"line={row.get('line_no')} "
            f"setup_id={row.get('setup_id')} "
            f"strategy={row.get('strategy')} "
            f"signal={row.get('signal')} "
            f"confidence={row.get('confidence')} "
            f"score_delta={row.get('score_delta')} "
            f"shadow={row.get('shadow_decision')}"
        )

    print()
    print("report =", paths["report_json"])

    if args.strict and file_status["file_stale"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
