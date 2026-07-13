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
        "setup_outcomes_file": source_dir / "setup_outcomes.json",
        "trades_file": source_dir / "trades.json",
        "report_json": output_dir / "raw_setup_trade_forensics_report.json",
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
                    "_raw": line[:1000],
                })

    return rows


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)

    return path


def flatten_json_container(payload):
    rows = []

    if isinstance(payload, list):
        rows.extend([x for x in payload if isinstance(x, dict)])
    elif isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                rows.extend([x for x in value if isinstance(x, dict)])
            elif isinstance(value, dict):
                rows.append(value)

    return rows


def row_text(row):
    return json.dumps(row, ensure_ascii=False, default=str)


def find_matches(rows, setup_id):
    matches = []

    for row in rows:
        text = row_text(row)

        if setup_id in text:
            matches.append(row)

    return matches


def value(row, keys):
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return None


def as_float(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None


def compare_numbers(a, b, tolerance=0.0001):
    fa = as_float(a)
    fb = as_float(b)

    if fa is None and fb is None:
        return "BOTH_MISSING"

    if fa is None:
        return "LEFT_MISSING"

    if fb is None:
        return "RIGHT_MISSING"

    if abs(fa - fb) <= tolerance:
        return "MATCH"

    return "DIFFERENT"


def summarize_match(row):
    return {
        "keys": sorted(row.keys()),
        "created_at": value(row, ["created_at", "timestamp", "time", "opened_at", "closed_at"]),
        "setup_id": value(row, ["setup_id", "id", "signal_id", "candidate_id"]),
        "strategy": value(row, ["strategy"]),
        "signal": value(row, ["signal", "direction", "type"]),
        "status": value(row, ["status"]),
        "final_outcome": value(row, ["final_outcome"]),
        "outcome": value(row, ["outcome", "result"]),
        "entry": value(row, ["entry", "entry_price", "open_price"]),
        "sl": value(row, ["sl", "stop_loss"]),
        "tp": value(row, ["tp", "take_profit"]),
        "close_price": value(row, ["close_price", "exit_price"]),
        "realized_profit": value(row, ["realized_profit", "profit", "pnl"]),
        "ticket": value(row, ["ticket", "position_id", "order", "deal"]),
        "raw": row,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Raw forensic inspection of a setup across observations, setup outcomes, and trades."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--setup-id",
        required=True,
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)

    observations = [
        row for row in read_jsonl(paths["observations_file"])
        if not row.get("_parse_error")
    ]

    setup_outcomes_payload = read_json(paths["setup_outcomes_file"], default=[])
    setup_outcomes = flatten_json_container(setup_outcomes_payload)

    trades_payload = read_json(paths["trades_file"], default=[])
    trades = flatten_json_container(trades_payload)

    observation_matches = find_matches(observations, args.setup_id)
    setup_outcome_matches = find_matches(setup_outcomes, args.setup_id)
    trade_matches = find_matches(trades, args.setup_id)

    latest_observation = observation_matches[-1] if observation_matches else {}
    latest_setup_outcome = setup_outcome_matches[-1] if setup_outcome_matches else {}
    latest_trade = trade_matches[-1] if trade_matches else {}

    observation_summary = summarize_match(latest_observation) if latest_observation else {}
    setup_outcome_summary = summarize_match(latest_setup_outcome) if latest_setup_outcome else {}
    trade_summary = summarize_match(latest_trade) if latest_trade else {}

    comparisons = {
        "observation_vs_setup_outcome_entry": compare_numbers(
            observation_summary.get("entry"),
            setup_outcome_summary.get("entry"),
        ),
        "observation_vs_setup_outcome_sl": compare_numbers(
            observation_summary.get("sl"),
            setup_outcome_summary.get("sl"),
        ),
        "observation_vs_setup_outcome_tp": compare_numbers(
            observation_summary.get("tp"),
            setup_outcome_summary.get("tp"),
        ),
        "setup_outcome_status": setup_outcome_summary.get("status"),
        "setup_outcome_final_outcome": setup_outcome_summary.get("final_outcome"),
        "trade_status": trade_summary.get("status"),
        "trade_realized_profit": trade_summary.get("realized_profit"),
        "trade_close_price": trade_summary.get("close_price"),
    }

    contradictions = []

    if setup_outcome_summary.get("final_outcome") == "W10" and trade_summary.get("status") == "CLOSED":
        contradictions.append("SETUP_OUTCOME_W10_BUT_TRADE_CLOSED")

    if comparison := comparisons.get("observation_vs_setup_outcome_tp"):
        if comparison in ["LEFT_MISSING", "RIGHT_MISSING", "DIFFERENT"]:
            contradictions.append("OBSERVATION_SETUP_OUTCOME_TP_MISMATCH")

    if setup_outcome_summary.get("status") == "TRACKING" and trade_summary.get("status") == "CLOSED":
        contradictions.append("SETUP_OUTCOME_TRACKING_BUT_TRADE_CLOSED")

    if trade_summary and trade_summary.get("realized_profit") is None:
        contradictions.append("TRADE_CLOSED_BUT_NO_REALIZED_PROFIT_FIELD_FOUND")

    if not contradictions:
        diagnosis = "NO_RAW_CONTRADICTION_FOUND"
    elif "TRADE_CLOSED_BUT_NO_REALIZED_PROFIT_FIELD_FOUND" in contradictions:
        diagnosis = "TRADE_CLOSE_DETAILS_MISSING_OR_NOT_NORMALIZED"
    elif "SETUP_OUTCOME_W10_BUT_TRADE_CLOSED" in contradictions:
        diagnosis = "FINAL_OUTCOME_CONFLICT_REQUIRES_TRACKER_MAPPING_REVIEW"
    else:
        diagnosis = "RAW_DATA_CONSISTENCY_REVIEW_REQUIRED"

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2X",
        "setup_id": args.setup_id,
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "diagnosis": diagnosis,
        "contradictions": contradictions,
        "match_counts": {
            "observation_matches": len(observation_matches),
            "setup_outcome_matches": len(setup_outcome_matches),
            "trade_matches": len(trade_matches),
        },
        "comparisons": comparisons,
        "latest_observation": observation_summary,
        "latest_setup_outcome": setup_outcome_summary,
        "latest_trade": trade_summary,
        "all_observation_matches": [summarize_match(row) for row in observation_matches],
        "all_setup_outcome_matches": [summarize_match(row) for row in setup_outcome_matches],
        "all_trade_matches": [summarize_match(row) for row in trade_matches],
        "generated_files": {
            "report_json": str(paths["report_json"]),
        },
        "notes": [
            "This is diagnostic only.",
            "No live trading behavior is changed.",
            "Use this report before changing analyzer or tracker logic.",
        ],
    }

    write_json(paths["report_json"], report)

    print("[PHASE 2X RAW SETUP/TRADE FORENSICS]")
    print("setup_id =", args.setup_id)
    print("diagnosis =", diagnosis)
    print("contradictions =", contradictions)

    print()
    print("[MATCH COUNTS]")
    for key, val in report["match_counts"].items():
        print(f"{key} = {val}")

    print()
    print("[COMPARISONS]")
    for key, val in comparisons.items():
        print(f"{key} = {val}")

    print()
    print("[OBSERVATION SUMMARY]")
    print(json.dumps({k: v for k, v in observation_summary.items() if k != "raw"}, indent=2, ensure_ascii=False))

    print()
    print("[SETUP OUTCOME SUMMARY]")
    print(json.dumps({k: v for k, v in setup_outcome_summary.items() if k != "raw"}, indent=2, ensure_ascii=False))

    print()
    print("[TRADE SUMMARY]")
    print(json.dumps({k: v for k, v in trade_summary.items() if k != "raw"}, indent=2, ensure_ascii=False))

    print()
    print("[TRADE RAW]")
    if trade_summary:
        print(json.dumps(trade_summary.get("raw"), indent=2, ensure_ascii=False))
    else:
        print("none")

    print()
    print("report =", paths["report_json"])


if __name__ == "__main__":
    main()
