import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


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


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = rows or []
    headers = []

    for row in rows:
        for key in row.keys():
            if key not in headers:
                headers.append(key)

    with path.open("w", encoding="utf-8", newline="") as f:
        if not headers:
            f.write("")
            return path

        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()

        for row in rows:
            safe = {}

            for key in headers:
                value = row.get(key)

                if isinstance(value, (dict, list, tuple, set)):
                    value = json.dumps(list(value) if isinstance(value, set) else value, ensure_ascii=False, sort_keys=True)

                safe[key] = value

            writer.writerow(safe)

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
        "audit_csv": output_dir / "confirmation_duplicate_observation_audit.csv",
        "audit_json": output_dir / "confirmation_duplicate_observation_audit.json",
    }


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def get_modules(row):
    for key in ["modules", "results", "module_results"]:
        value = row.get(key)

        if isinstance(value, list):
            return value

    report = row.get("report") or row.get("confirmation_report") or {}

    if isinstance(report, dict):
        for key in ["results", "modules"]:
            value = report.get(key)

            if isinstance(value, list):
                return value

    return []


def get_bucket(row):
    return row.get("setup_source_bucket") or row.get("execution_bucket") or "UNKNOWN"


def make_group_key(row):
    setup_id = row.get("setup_id")

    if setup_id:
        return "|".join([
            str(setup_id),
            str(row.get("strategy") or "UNKNOWN"),
            str(row.get("signal") or "UNKNOWN"),
            str(get_bucket(row)),
        ])

    return "|".join([
        "NO_SETUP_ID",
        str(row.get("strategy") or "UNKNOWN"),
        str(row.get("signal") or "UNKNOWN"),
        str(get_bucket(row)),
        str(row.get("created_at") or row.get("_line_no")),
    ])


def compact_values(values, limit=10):
    cleaned = []

    for value in values:
        if value not in cleaned:
            cleaned.append(value)

    if len(cleaned) <= limit:
        return cleaned

    return cleaned[:limit] + [f"... +{len(cleaned) - limit} more"]


def summarize_group(key, items):
    items_sorted = sorted(items, key=lambda x: int(x.get("_line_no") or 0))

    first = items_sorted[0]
    last = items_sorted[-1]

    confidence_values = compact_values([
        safe_float(row.get("confidence"), 0.0)
        for row in items_sorted
    ])

    score_delta_values = compact_values([
        safe_float(row.get("score_delta"), 0.0)
        for row in items_sorted
    ])

    shadow_decisions = compact_values([
        row.get("shadow_decision")
        for row in items_sorted
        if row.get("shadow_decision") is not None
    ])

    module_counts = compact_values([
        len(get_modules(row))
        for row in items_sorted
    ])

    line_numbers = [
        row.get("_line_no")
        for row in items_sorted
    ]

    created_values = [
        row.get("created_at")
        for row in items_sorted
        if row.get("created_at")
    ]

    exact_signature_set = set()

    for row in items_sorted:
        signature = json.dumps({
            "setup_id": row.get("setup_id"),
            "strategy": row.get("strategy"),
            "signal": row.get("signal"),
            "bucket": get_bucket(row),
            "confidence": safe_float(row.get("confidence"), 0.0),
            "score_delta": safe_float(row.get("score_delta"), 0.0),
            "approved": row.get("approved"),
            "shadow_decision": row.get("shadow_decision"),
            "module_count": len(get_modules(row)),
        }, sort_keys=True, ensure_ascii=False)

        exact_signature_set.add(signature)

    count = len(items_sorted)

    return {
        "group_key": key,
        "setup_id": first.get("setup_id"),
        "strategy": first.get("strategy") or "UNKNOWN",
        "signal": first.get("signal") or "UNKNOWN",
        "bucket": get_bucket(first),
        "observation_count": count,
        "duplicate_count": max(0, count - 1),
        "first_line_no": line_numbers[0],
        "last_line_no": line_numbers[-1],
        "line_numbers": line_numbers,
        "first_created_at": created_values[0] if created_values else None,
        "last_created_at": created_values[-1] if created_values else None,
        "confidence_values": confidence_values,
        "score_delta_values": score_delta_values,
        "shadow_decisions": shadow_decisions,
        "module_counts": module_counts,
        "unique_signature_count": len(exact_signature_set),
        "exact_duplicate_like": len(exact_signature_set) == 1 and count > 1,
        "latest_confidence": safe_float(last.get("confidence"), 0.0),
        "latest_score_delta": safe_float(last.get("score_delta"), 0.0),
        "latest_shadow_decision": last.get("shadow_decision"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Audit duplicate confirmation observations by setup."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=20,
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)

    rows = read_jsonl(paths["observations_file"])
    parsed_rows = [row for row in rows if not row.get("_parse_error")]

    groups = defaultdict(list)

    for row in parsed_rows:
        groups[make_group_key(row)].append(row)

    all_group_rows = [
        summarize_group(key, items)
        for key, items in groups.items()
    ]

    duplicate_rows = [
        row
        for row in all_group_rows
        if row.get("observation_count", 0) > 1
    ]

    duplicate_rows.sort(
        key=lambda row: (
            -int(row.get("duplicate_count") or 0),
            -int(row.get("observation_count") or 0),
            str(row.get("setup_id") or ""),
        )
    )

    raw_observation_count = len(parsed_rows)
    unique_group_count = len(all_group_rows)
    duplicate_observation_count = sum(row.get("duplicate_count", 0) for row in all_group_rows)
    duplicate_group_count = len(duplicate_rows)

    duplicate_rate = round(duplicate_observation_count / raw_observation_count, 4) if raw_observation_count else 0.0

    if duplicate_rate >= 0.50:
        recommendation = "HIGH_DUPLICATION_REVIEW_LOGGER_COOLDOWN"
    elif duplicate_rate >= 0.25:
        recommendation = "MODERATE_DUPLICATION_MONITOR_OR_ADD_COOLDOWN"
    else:
        recommendation = "DUPLICATION_ACCEPTABLE"

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2J",
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "raw_observation_count": raw_observation_count,
        "unique_group_count": unique_group_count,
        "duplicate_observation_count": duplicate_observation_count,
        "duplicate_group_count": duplicate_group_count,
        "duplicate_rate": duplicate_rate,
        "recommendation": recommendation,
        "top_duplicates": duplicate_rows[:args.top],
        "generated_files": {
            "audit_csv": str(paths["audit_csv"]),
            "audit_json": str(paths["audit_json"]),
        },
        "notes": [
            "This script does not modify live trading behavior.",
            "Exact duplicate-like rows usually mean the same setup is being observed repeatedly with unchanged confirmation output.",
            "Analyzer dedupe already protects performance stats, but logger-level cooldown may reduce file noise later.",
        ],
    }

    write_csv(paths["audit_csv"], duplicate_rows)
    write_json(paths["audit_json"], report)

    print("[PHASE 2J DUPLICATE OBSERVATION AUDIT] done")
    print("raw_observation_count =", raw_observation_count)
    print("unique_group_count =", unique_group_count)
    print("duplicate_observation_count =", duplicate_observation_count)
    print("duplicate_group_count =", duplicate_group_count)
    print("duplicate_rate =", duplicate_rate)
    print("recommendation =", recommendation)
    print("audit_csv =", paths["audit_csv"])
    print("audit_json =", paths["audit_json"])

    if duplicate_rows:
        print()
        print("[TOP DUPLICATES]")
        for row in duplicate_rows[:args.top]:
            print(
                f"{row.get('setup_id')} | "
                f"{row.get('strategy')} | "
                f"{row.get('signal')} | "
                f"{row.get('bucket')} | "
                f"count={row.get('observation_count')} "
                f"dupes={row.get('duplicate_count')} "
                f"exact_like={row.get('exact_duplicate_like')} "
                f"shadow={row.get('latest_shadow_decision')}"
            )


if __name__ == "__main__":
    main()
