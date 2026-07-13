import argparse
import csv
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
        "setup_outcomes_file": source_dir / "setup_outcomes.json",
        "trades_file": source_dir / "trades.json",
        "outcome_quality_csv": output_dir / "confirmation_shadow_outcome_quality.csv",
        "debug_json": output_dir / "confirmation_outcome_quality_debug.json",
        "report_json": output_dir / "w10_outcome_issue_inspection_report.json",
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


def read_csv_rows(path):
    path = Path(path)

    if not path.exists():
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)

    return path


def normalize_setup_id(value):
    if value is None:
        return ""

    return str(value).strip()


def get_setup_id(row):
    for key in [
        "setup_id",
        "id",
        "candidate_id",
        "signal_id",
    ]:
        value = row.get(key)

        if value:
            return normalize_setup_id(value)

    return ""


def compact_dict(row, max_value_len=400):
    if not isinstance(row, dict):
        return row

    compacted = {}

    preferred_keys = [
        "_line_no",
        "created_at",
        "timestamp",
        "time",
        "setup_id",
        "id",
        "strategy",
        "signal",
        "status",
        "final_outcome",
        "outcome",
        "outcome_label",
        "entry",
        "sl",
        "tp",
        "close_price",
        "realized_profit",
        "profit",
        "result",
        "confidence",
        "score_delta",
        "shadow_decision",
        "shadow_score",
        "shadow_action",
        "shadow_blocking_allowed",
        "reason",
        "notes",
    ]

    for key in preferred_keys:
        if key in row:
            value = row.get(key)

            if isinstance(value, str) and len(value) > max_value_len:
                value = value[:max_value_len] + "...[truncated]"

            compacted[key] = value

    extra_shadow = {
        key: row.get(key)
        for key in row.keys()
        if "shadow" in key.lower() and key not in compacted
    }

    compacted.update(extra_shadow)

    return compacted


def find_matching_rows(rows, setup_id):
    setup_id = normalize_setup_id(setup_id)

    matches = []

    for row in rows:
        row_setup_id = get_setup_id(row)

        if row_setup_id == setup_id:
            matches.append(row)
            continue

        text = json.dumps(row, ensure_ascii=False, default=str)

        if setup_id and setup_id in text:
            matches.append(row)

    return matches


def find_trade_matches(trades, setup_id):
    setup_id = normalize_setup_id(setup_id)
    matches = []

    if isinstance(trades, dict):
        iterable = []

        for value in trades.values():
            if isinstance(value, list):
                iterable.extend(value)
            elif isinstance(value, dict):
                iterable.append(value)
    elif isinstance(trades, list):
        iterable = trades
    else:
        iterable = []

    for row in iterable:
        if not isinstance(row, dict):
            continue

        text = json.dumps(row, ensure_ascii=False, default=str)

        if setup_id and setup_id in text:
            matches.append(row)
            continue

        row_setup_id = get_setup_id(row)

        if row_setup_id == setup_id:
            matches.append(row)

    return matches


def infer_issue_type(setup_outcome_rows, trade_matches):
    final_outcomes = {
        str(row.get("final_outcome"))
        for row in setup_outcome_rows
        if row.get("final_outcome") is not None
    }

    statuses = {
        str(row.get("status"))
        for row in setup_outcome_rows
        if row.get("status") is not None
    }

    has_trade = bool(trade_matches)

    if "W10" in final_outcomes and not has_trade:
        return "VALID_W10_TIMEOUT_NO_MATCHING_TRADE"

    if "W10" in final_outcomes and has_trade:
        return "W10_WITH_MATCHING_TRADE_REVIEW_PROFIT_OR_CLOSE_REASON"

    if not final_outcomes and has_trade:
        return "MISSING_FINAL_OUTCOME_BUT_TRADE_EXISTS"

    if final_outcomes:
        return "FINAL_OUTCOME_REVIEW_REQUIRED"

    if statuses:
        return "STATUS_ONLY_REVIEW_REQUIRED"

    return "INSUFFICIENT_DATA"


def main():
    parser = argparse.ArgumentParser(
        description="Inspect W10-only outcome quality issues with raw setup/trade context."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--setup-id",
        default="",
        help="Optional specific setup_id. If omitted, inspect W10_ONLY rows from outcome quality CSV.",
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)

    observations = read_jsonl(paths["observations_file"])
    parsed_observations = [row for row in observations if not row.get("_parse_error")]

    setup_outcomes = read_json(paths["setup_outcomes_file"], default=[])
    if isinstance(setup_outcomes, dict):
        setup_outcome_rows = []

        for value in setup_outcomes.values():
            if isinstance(value, list):
                setup_outcome_rows.extend(value)
            elif isinstance(value, dict):
                setup_outcome_rows.append(value)
    elif isinstance(setup_outcomes, list):
        setup_outcome_rows = setup_outcomes
    else:
        setup_outcome_rows = []

    trades = read_json(paths["trades_file"], default=[])

    outcome_quality_rows = read_csv_rows(paths["outcome_quality_csv"])
    debug_report = read_json(paths["debug_json"], default={}) or {}

    setup_ids = []

    if args.setup_id:
        setup_ids.append(args.setup_id)
    else:
        for row in outcome_quality_rows:
            text = json.dumps(row, ensure_ascii=False, default=str)

            if "W10_ONLY" in text or "w10_without_final_tp_sl" in text:
                sid = get_setup_id(row)

                if sid:
                    setup_ids.append(sid)

    setup_ids = sorted(set(setup_ids))

    inspections = []

    for setup_id in setup_ids:
        obs_matches = find_matching_rows(parsed_observations, setup_id)
        outcome_matches = find_matching_rows(setup_outcome_rows, setup_id)
        trade_matches = find_trade_matches(trades, setup_id)

        quality_matches = [
            row
            for row in outcome_quality_rows
            if setup_id in json.dumps(row, ensure_ascii=False, default=str)
        ]

        diagnosis = infer_issue_type(outcome_matches, trade_matches)

        inspections.append({
            "setup_id": setup_id,
            "diagnosis": diagnosis,
            "observation_match_count": len(obs_matches),
            "setup_outcome_match_count": len(outcome_matches),
            "trade_match_count": len(trade_matches),
            "quality_match_count": len(quality_matches),
            "observations": [compact_dict(row) for row in obs_matches[-5:]],
            "setup_outcomes": [compact_dict(row) for row in outcome_matches[-5:]],
            "trades": [compact_dict(row) for row in trade_matches[-5:]],
            "quality_rows": quality_matches[-5:],
        })

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2W",
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "inspected_setup_count": len(inspections),
        "inspections": inspections,
        "debug_report_keys": list(debug_report.keys()) if isinstance(debug_report, dict) else [],
        "generated_files": {
            "report_json": str(paths["report_json"]),
        },
        "notes": [
            "This script does not change outcome classification.",
            "Use this report to decide whether W10_ONLY is a valid timeout outcome or a data quality bug.",
            "No live trading behavior is changed.",
        ],
    }

    write_json(paths["report_json"], report)

    print("[PHASE 2W W10 OUTCOME ISSUE INSPECTOR]")
    print("inspected_setup_count =", len(inspections))

    for item in inspections:
        print()
        print("=" * 100)
        print("setup_id =", item["setup_id"])
        print("diagnosis =", item["diagnosis"])
        print("observation_match_count =", item["observation_match_count"])
        print("setup_outcome_match_count =", item["setup_outcome_match_count"])
        print("trade_match_count =", item["trade_match_count"])
        print("quality_match_count =", item["quality_match_count"])

        print()
        print("[LATEST OBSERVATION]")
        if item["observations"]:
            print(json.dumps(item["observations"][-1], indent=2, ensure_ascii=False))
        else:
            print("none")

        print()
        print("[LATEST SETUP OUTCOME]")
        if item["setup_outcomes"]:
            print(json.dumps(item["setup_outcomes"][-1], indent=2, ensure_ascii=False))
        else:
            print("none")

        print()
        print("[LATEST TRADE]")
        if item["trades"]:
            print(json.dumps(item["trades"][-1], indent=2, ensure_ascii=False))
        else:
            print("none")

    print()
    print("report =", paths["report_json"])


if __name__ == "__main__":
    main()
