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
        "trades_file": source_dir / "trades.json",
        "setup_outcomes_file": source_dir / "setup_outcomes.json",
        "report_json": output_dir / "trade_tracker_reconciliation_gap_report.json",
        "report_csv": output_dir / "trade_tracker_reconciliation_gap_report.csv",
    }


def read_json(path, default=None):
    path = Path(path)

    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)

    return path


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "setup_id",
        "strategy",
        "signal",
        "trade_status",
        "setup_outcome_status",
        "setup_final_outcome",
        "entry_price",
        "stop_loss",
        "take_profit",
        "setup_entry",
        "setup_sl",
        "setup_tp",
        "position_id",
        "main_position_id",
        "order_id",
        "deal_id",
        "open_time",
        "close_time",
        "final_result",
        "close_reason",
        "close_price",
        "realized_profit",
        "missing_position_checks",
        "last_missing_position_check",
        "issue_count",
        "issues",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow({
                key: row.get(key)
                for key in fieldnames
            })

    return path


def get_setup_id(row):
    return str(row.get("setup_id") or "").strip()


def as_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def compare_optional_numbers(left, right, tolerance=0.0001):
    left_f = as_float(left)
    right_f = as_float(right)

    if left_f is None and right_f is None:
        return "BOTH_MISSING"

    if left_f is None:
        return "LEFT_MISSING"

    if right_f is None:
        return "RIGHT_MISSING"

    if abs(left_f - right_f) <= tolerance:
        return "MATCH"

    return "DIFFERENT"


def build_setup_outcome_index(setup_outcomes):
    index = {}

    for row in setup_outcomes:
        setup_id = get_setup_id(row)

        if not setup_id:
            continue

        index.setdefault(setup_id, []).append(row)

    return index


def latest_setup_outcome(index, setup_id):
    rows = index.get(setup_id) or []

    if not rows:
        return None

    return rows[-1]


def is_missing(value):
    return value is None or value == ""


def audit_trade(trade, setup_outcome):
    setup_id = get_setup_id(trade)

    issues = []

    trade_status = trade.get("status")
    setup_status = setup_outcome.get("status") if setup_outcome else None
    setup_final = setup_outcome.get("final_outcome") if setup_outcome else None

    final_result = trade.get("final_result")
    close_reason = trade.get("close_reason")
    close_price = trade.get("close_price") or trade.get("exit_price")
    realized_profit = trade.get("realized_profit")

    if trade_status == "CLOSED":
        if is_missing(final_result):
            issues.append("CLOSED_TRADE_MISSING_FINAL_RESULT")

        if is_missing(close_reason):
            issues.append("CLOSED_TRADE_MISSING_CLOSE_REASON")

        if is_missing(close_price):
            issues.append("CLOSED_TRADE_MISSING_CLOSE_PRICE")

        if is_missing(realized_profit):
            issues.append("CLOSED_TRADE_MISSING_REALIZED_PROFIT")

        if trade.get("missing_position_checks"):
            issues.append("CLOSED_AFTER_MISSING_POSITION_CHECK")

        if setup_status == "TRACKING":
            issues.append("SETUP_OUTCOME_STILL_TRACKING_WHILE_TRADE_CLOSED")

        if setup_final == "W10":
            issues.append("SETUP_OUTCOME_W10_WHILE_TRADE_CLOSED")

    if setup_outcome:
        tp_compare = compare_optional_numbers(
            trade.get("take_profit"),
            setup_outcome.get("tp"),
        )

        entry_compare = compare_optional_numbers(
            trade.get("entry_price"),
            setup_outcome.get("entry"),
        )

        sl_compare = compare_optional_numbers(
            trade.get("stop_loss"),
            setup_outcome.get("sl"),
        )

        if tp_compare in ["LEFT_MISSING", "RIGHT_MISSING", "DIFFERENT"]:
            issues.append(f"TRADE_SETUP_TP_MISMATCH:{tp_compare}")

        if entry_compare == "DIFFERENT":
            issues.append("TRADE_SETUP_ENTRY_DIFFERENT")

        if sl_compare == "DIFFERENT":
            issues.append("TRADE_SETUP_SL_DIFFERENT")
    else:
        issues.append("NO_MATCHING_SETUP_OUTCOME")

    return {
        "setup_id": setup_id,
        "strategy": trade.get("strategy"),
        "signal": trade.get("signal"),
        "trade_status": trade_status,
        "setup_outcome_status": setup_status,
        "setup_final_outcome": setup_final,
        "entry_price": trade.get("entry_price"),
        "stop_loss": trade.get("stop_loss"),
        "take_profit": trade.get("take_profit"),
        "setup_entry": setup_outcome.get("entry") if setup_outcome else None,
        "setup_sl": setup_outcome.get("sl") if setup_outcome else None,
        "setup_tp": setup_outcome.get("tp") if setup_outcome else None,
        "position_id": trade.get("position_id"),
        "main_position_id": trade.get("main_position_id"),
        "order_id": trade.get("order_id"),
        "deal_id": trade.get("deal_id"),
        "open_time": trade.get("open_time"),
        "close_time": trade.get("close_time"),
        "final_result": final_result,
        "close_reason": close_reason,
        "close_price": close_price,
        "realized_profit": realized_profit,
        "missing_position_checks": trade.get("missing_position_checks"),
        "last_missing_position_check": trade.get("last_missing_position_check"),
        "issue_count": len(issues),
        "issues": "|".join(issues),
        "_issues_list": issues,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Audit trade tracker reconciliation gaps between trades.json and setup_outcomes.json."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--only-issues",
        action="store_true",
        default=True,
    )

    parser.add_argument(
        "--top",
        type=int,
        default=20,
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)

    trades_payload = read_json(paths["trades_file"], default=[])
    setup_outcomes_payload = read_json(paths["setup_outcomes_file"], default=[])

    trades = flatten_json_container(trades_payload)
    setup_outcomes = flatten_json_container(setup_outcomes_payload)
    setup_index = build_setup_outcome_index(setup_outcomes)

    audited = []

    for trade in trades:
        setup_id = get_setup_id(trade)
        setup_outcome = latest_setup_outcome(setup_index, setup_id)
        audited.append(audit_trade(trade, setup_outcome))

    issue_rows = [
        row
        for row in audited
        if row.get("issue_count", 0) > 0
    ]

    closed_trades = [
        row
        for row in audited
        if row.get("trade_status") == "CLOSED"
    ]

    unresolved_closed = [
        row
        for row in closed_trades
        if any(issue in row.get("issues", "") for issue in [
            "CLOSED_TRADE_MISSING_FINAL_RESULT",
            "CLOSED_TRADE_MISSING_CLOSE_REASON",
            "CLOSED_TRADE_MISSING_CLOSE_PRICE",
            "CLOSED_TRADE_MISSING_REALIZED_PROFIT",
        ])
    ]

    w10_closed = [
        row
        for row in issue_rows
        if "SETUP_OUTCOME_W10_WHILE_TRADE_CLOSED" in row.get("issues", "")
    ]

    tracking_closed = [
        row
        for row in issue_rows
        if "SETUP_OUTCOME_STILL_TRACKING_WHILE_TRADE_CLOSED" in row.get("issues", "")
    ]

    missing_position_closed = [
        row
        for row in issue_rows
        if "CLOSED_AFTER_MISSING_POSITION_CHECK" in row.get("issues", "")
    ]

    tp_mismatch = [
        row
        for row in issue_rows
        if "TRADE_SETUP_TP_MISMATCH" in row.get("issues", "")
    ]

    issue_type_counts = {}

    for row in issue_rows:
        for issue in row.get("_issues_list", []):
            issue_type_counts[issue] = issue_type_counts.get(issue, 0) + 1

    recommendation = "NO_RECONCILIATION_GAPS_FOUND"

    if unresolved_closed:
        recommendation = "FIX_TRADE_TRACKER_CLOSE_RECONCILIATION"

    if w10_closed:
        recommendation = "FIX_TRADE_TRACKER_AND_SETUP_OUTCOME_W10_CLOSED_CONFLICT"

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2AA",
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "recommendation": recommendation,
        "counts": {
            "trade_count": len(trades),
            "setup_outcome_count": len(setup_outcomes),
            "audited_trade_count": len(audited),
            "issue_trade_count": len(issue_rows),
            "closed_trade_count": len(closed_trades),
            "unresolved_closed_trade_count": len(unresolved_closed),
            "w10_closed_conflict_count": len(w10_closed),
            "tracking_closed_conflict_count": len(tracking_closed),
            "missing_position_closed_count": len(missing_position_closed),
            "tp_mismatch_count": len(tp_mismatch),
        },
        "issue_type_counts": issue_type_counts,
        "top_issue_rows": [
            {k: v for k, v in row.items() if not k.startswith("_")}
            for row in issue_rows[:args.top]
        ],
        "generated_files": {
            "report_json": str(paths["report_json"]),
            "report_csv": str(paths["report_csv"]),
        },
        "notes": [
            "This script is diagnostic only.",
            "It does not modify trades.json or setup_outcomes.json.",
            "Use this before patching trade_tracker.py.",
        ],
    }

    write_json(paths["report_json"], report)
    write_csv(paths["report_csv"], [
        {k: v for k, v in row.items() if not k.startswith("_")}
        for row in issue_rows
    ])

    print("[PHASE 2AA TRADE TRACKER RECONCILIATION AUDIT]")
    print("recommendation =", recommendation)

    print()
    print("[COUNTS]")
    for key, value in report["counts"].items():
        print(f"{key} = {value}")

    print()
    print("[ISSUE TYPE COUNTS]")
    for key, value in sorted(issue_type_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"{key} = {value}")

    print()
    print("[TOP ISSUE ROWS]")
    for row in report["top_issue_rows"]:
        print(
            f"{row.get('setup_id')} | "
            f"{row.get('strategy')} | "
            f"trade_status={row.get('trade_status')} | "
            f"setup_status={row.get('setup_outcome_status')} | "
            f"setup_final={row.get('setup_final_outcome')} | "
            f"issues={row.get('issues')}"
        )

    print()
    print("report_json =", paths["report_json"])
    print("report_csv =", paths["report_csv"])


if __name__ == "__main__":
    main()
