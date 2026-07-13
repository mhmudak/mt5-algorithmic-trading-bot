import argparse
import json
import time
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def resolve_source_dir(source_dir):
    source_dir = Path(source_dir)

    if not source_dir.is_absolute():
        source_dir = PROJECT_ROOT / source_dir

    return source_dir


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


def has_shadow_fields(row):
    return bool(
        row.get("shadow_decision")
        or row.get("shadow_action")
        or row.get("shadow_score") is not None
        or row.get("shadow_policy_version")
    )


def compact(row):
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


def print_row(prefix, row):
    item = compact(row)

    print(
        f"{prefix} "
        f"line={item.get('line_no')} "
        f"setup_id={item.get('setup_id')} "
        f"strategy={item.get('strategy')} "
        f"signal={item.get('signal')} "
        f"bucket={item.get('bucket')} "
        f"confidence={item.get('confidence')} "
        f"score_delta={item.get('score_delta')} "
        f"shadow={item.get('shadow_decision')} "
        f"shadow_score={item.get('shadow_score')} "
        f"action={item.get('shadow_action')} "
        f"blocking_allowed={item.get('shadow_blocking_allowed')}"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Watch confirmation observations until a live shadow-persisted row appears."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=30,
    )

    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=0,
        help="0 means no timeout.",
    )

    parser.add_argument(
        "--once",
        action="store_true",
    )

    args = parser.parse_args()

    source_dir = resolve_source_dir(args.source_dir)
    observations_file = source_dir / "confirmation_observations.jsonl"

    started_at = time.time()
    initial_rows = read_jsonl(observations_file)
    initial_count = len([row for row in initial_rows if not row.get("_parse_error")])
    initial_shadow_count = len([row for row in initial_rows if has_shadow_fields(row)])

    print("[PHASE 2P SHADOW PERSISTENCE WATCHER]")
    print("observations_file =", observations_file)
    print("started_at =", datetime.now().isoformat())
    print("initial_observation_count =", initial_count)
    print("initial_shadow_count =", initial_shadow_count)
    print("interval_seconds =", args.interval)
    print("timeout_minutes =", args.timeout_minutes)

    if initial_shadow_count > 0:
        latest_shadow = [row for row in initial_rows if has_shadow_fields(row)][-1]
        print()
        print("[ALREADY CONFIRMED]")
        print_row("latest_shadow", latest_shadow)

        if args.once:
            return

    while True:
        rows = read_jsonl(observations_file)
        parsed = [row for row in rows if not row.get("_parse_error")]
        shadow_rows = [row for row in parsed if has_shadow_fields(row)]

        current_count = len(parsed)
        shadow_count = len(shadow_rows)
        new_rows_count = max(0, current_count - initial_count)
        new_shadow_count = max(0, shadow_count - initial_shadow_count)

        print()
        print(
            f"[CHECK] {datetime.now().isoformat()} | "
            f"rows={current_count} "
            f"new_rows={new_rows_count} "
            f"shadow_rows={shadow_count} "
            f"new_shadow_rows={new_shadow_count}"
        )

        if parsed:
            print_row("latest", parsed[-1])

        if new_shadow_count > 0:
            latest_shadow = shadow_rows[-1]
            print()
            print("[CONFIRMED] New live observation has shadow fields.")
            print_row("latest_shadow", latest_shadow)
            return

        if args.once:
            return

        if args.timeout_minutes and (time.time() - started_at) >= args.timeout_minutes * 60:
            print()
            print("[TIMEOUT] No new live shadow observation found before timeout.")
            raise SystemExit(1)

        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()
