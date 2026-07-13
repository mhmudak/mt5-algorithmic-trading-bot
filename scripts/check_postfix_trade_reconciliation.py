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
        "trades_file": source_dir / "trades.json",
        "baseline_json": output_dir / "postfix_trade_reconciliation_baseline.json",
        "report_json": output_dir / "postfix_trade_reconciliation_report.json",
    }


def read_json(path, default=None):
    path = Path(path)

    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def trade_key(trade):
    return str(
        trade.get("position_id")
        or trade.get("order_id")
        or trade.get("deal_id")
        or trade.get("setup_id")
        or ""
    )


def parse_dt(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def is_missing(value):
    return value is None or value == ""


def compact_trade(trade):
    return {
        "key": trade_key(trade),
        "setup_id": trade.get("setup_id"),
        "strategy": trade.get("strategy"),
        "signal": trade.get("signal"),
        "status": trade.get("status"),
        "position_id": trade.get("position_id"),
        "main_position_id": trade.get("main_position_id"),
        "order_id": trade.get("order_id"),
        "deal_id": trade.get("deal_id"),
        "open_time": trade.get("open_time"),
        "close_time": trade.get("close_time"),
        "entry_price": trade.get("entry_price"),
        "stop_loss": trade.get("stop_loss"),
        "take_profit": trade.get("take_profit"),
        "remaining_volume": trade.get("remaining_volume"),
        "closed_volume": trade.get("closed_volume"),
        "final_result": trade.get("final_result"),
        "close_reason": trade.get("close_reason"),
        "close_price": trade.get("close_price"),
        "realized_profit": trade.get("realized_profit"),
        "close_reconciliation_pending": trade.get("close_reconciliation_pending"),
        "missing_position_checks": trade.get("missing_position_checks"),
        "last_missing_position_check": trade.get("last_missing_position_check"),
    }


def build_baseline(trades):
    keys = sorted({
        trade_key(trade)
        for trade in trades
        if trade_key(trade)
    })

    latest_open_time = None
    latest_close_time = None

    for trade in trades:
        open_dt = parse_dt(trade.get("open_time"))
        close_dt = parse_dt(trade.get("close_time"))

        if open_dt and (latest_open_time is None or open_dt > latest_open_time):
            latest_open_time = open_dt

        if close_dt and (latest_close_time is None or close_dt > latest_close_time):
            latest_close_time = close_dt

    status_counts = {}

    for trade in trades:
        status = trade.get("status") or "UNKNOWN"
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2AF",
        "trade_count": len(trades),
        "known_trade_keys": keys,
        "latest_open_time": latest_open_time.isoformat() if latest_open_time else None,
        "latest_close_time": latest_close_time.isoformat() if latest_close_time else None,
        "status_counts": status_counts,
        "notes": [
            "Baseline created after Phase 2AC trade_tracker close reconciliation fix.",
            "Future checks should focus on trades not present in known_trade_keys.",
            "Old broken CLOSED rows before this baseline are intentionally ignored by the post-fix monitor.",
        ],
    }


def audit_postfix_trade(trade):
    issues = []

    status = trade.get("status")
    pending = trade.get("close_reconciliation_pending")

    if status == "CLOSED":
        if is_missing(trade.get("final_result")):
            issues.append("POSTFIX_CLOSED_MISSING_FINAL_RESULT")

        if is_missing(trade.get("close_reason")):
            issues.append("POSTFIX_CLOSED_MISSING_CLOSE_REASON")

        if is_missing(trade.get("close_price")):
            issues.append("POSTFIX_CLOSED_MISSING_CLOSE_PRICE")

        if is_missing(trade.get("realized_profit")):
            issues.append("POSTFIX_CLOSED_MISSING_REALIZED_PROFIT")

        if pending is True:
            issues.append("POSTFIX_CLOSED_STILL_PENDING_RECONCILIATION")

    if status == "OPEN" and pending is True:
        if not trade.get("missing_position_checks"):
            issues.append("POSTFIX_PENDING_WITHOUT_MISSING_POSITION_CHECKS")

    if status == "OPEN" and pending is not True:
        pass

    return {
        **compact_trade(trade),
        "issue_count": len(issues),
        "issues": issues,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Monitor only post-fix trade tracker close reconciliation behavior."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--init-baseline",
        action="store_true",
    )

    parser.add_argument(
        "--reset-baseline",
        action="store_true",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)

    trades_payload = read_json(paths["trades_file"], default=[])
    trades = flatten_json_container(trades_payload)

    if args.reset_baseline and paths["baseline_json"].exists():
        paths["baseline_json"].unlink()

    baseline = read_json(paths["baseline_json"], default=None)

    if args.init_baseline or not baseline:
        baseline = build_baseline(trades)
        write_json(paths["baseline_json"], baseline)

    known_keys = set(baseline.get("known_trade_keys") or [])

    new_trades = [
        trade
        for trade in trades
        if trade_key(trade) and trade_key(trade) not in known_keys
    ]

    audited_new = [audit_postfix_trade(trade) for trade in new_trades]

    issue_rows = [
        row
        for row in audited_new
        if row.get("issue_count", 0) > 0
    ]

    closed_new = [
        row
        for row in audited_new
        if row.get("status") == "CLOSED"
    ]

    pending_new = [
        row
        for row in audited_new
        if row.get("status") == "OPEN" and row.get("close_reconciliation_pending") is True
    ]

    clean_closed_new = [
        row
        for row in closed_new
        if row.get("issue_count", 0) == 0
    ]

    if issue_rows:
        recommendation = "REVIEW_POSTFIX_TRADE_RECONCILIATION_ISSUES"
    elif not new_trades:
        recommendation = "WAITING_FOR_NEW_POSTFIX_TRADES"
    elif pending_new and not closed_new:
        recommendation = "POSTFIX_PENDING_RECONCILIATION_MONITORING"
    else:
        recommendation = "POSTFIX_TRADE_RECONCILIATION_OK"

    all_ok = len(issue_rows) == 0

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2AF",
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "all_ok": all_ok,
        "recommendation": recommendation,
        "baseline": {
            "created_at": baseline.get("created_at"),
            "trade_count": baseline.get("trade_count"),
            "latest_open_time": baseline.get("latest_open_time"),
            "latest_close_time": baseline.get("latest_close_time"),
            "status_counts": baseline.get("status_counts"),
        },
        "counts": {
            "current_trade_count": len(trades),
            "baseline_trade_count": baseline.get("trade_count"),
            "new_postfix_trade_count": len(new_trades),
            "new_postfix_closed_trade_count": len(closed_new),
            "new_postfix_clean_closed_trade_count": len(clean_closed_new),
            "new_postfix_pending_reconciliation_count": len(pending_new),
            "new_postfix_issue_trade_count": len(issue_rows),
        },
        "new_postfix_trades": audited_new[-20:],
        "issue_rows": issue_rows[:50],
        "generated_files": {
            "baseline_json": str(paths["baseline_json"]),
            "report_json": str(paths["report_json"]),
        },
        "notes": [
            "This monitor ignores old trades present in the baseline.",
            "Use --reset-baseline only after intentionally choosing a new post-fix starting point.",
            "A new OPEN trade with close_reconciliation_pending=True is not automatically a failure.",
            "A new CLOSED trade missing close_reason/close_price/realized_profit/final_result is a failure.",
        ],
    }

    write_json(paths["report_json"], report)

    print("[PHASE 2AF POST-FIX TRADE RECONCILIATION]")
    print("all_ok =", all_ok)
    print("recommendation =", recommendation)

    print()
    print("[BASELINE]")
    print("baseline_created_at =", baseline.get("created_at"))
    print("baseline_trade_count =", baseline.get("trade_count"))
    print("baseline_latest_open_time =", baseline.get("latest_open_time"))
    print("baseline_latest_close_time =", baseline.get("latest_close_time"))

    print()
    print("[COUNTS]")
    for key, value in report["counts"].items():
        print(f"{key} = {value}")

    print()
    print("[NEW POST-FIX TRADES]")
    for row in report["new_postfix_trades"]:
        print(
            f"{row.get('key')} | "
            f"{row.get('setup_id')} | "
            f"status={row.get('status')} | "
            f"pending={row.get('close_reconciliation_pending')} | "
            f"final={row.get('final_result')} | "
            f"reason={row.get('close_reason')} | "
            f"close_price={row.get('close_price')} | "
            f"profit={row.get('realized_profit')} | "
            f"issues={row.get('issues')}"
        )

    print()
    print("baseline =", paths["baseline_json"])
    print("report =", paths["report_json"])

    if args.strict and not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
