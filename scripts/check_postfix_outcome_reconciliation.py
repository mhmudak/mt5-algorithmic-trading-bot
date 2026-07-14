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
        "output_dir": output_dir,
        "trades_file": source_dir / "trades.json",
        "setup_outcomes_file": source_dir / "setup_outcomes.json",
        "baseline_file": output_dir / "postfix_trade_reconciliation_baseline.json",
        "report_json": output_dir / "postfix_outcome_reconciliation_report.json",
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


def setup_variants(setup_id):
    setup_id = str(setup_id or "").strip()

    variants = []

    if setup_id:
        variants.append(setup_id)

    suffixes = [
        "-MTFOVERRIDE",
        "-EXTRA",
        "-MAIN",
    ]

    for suffix in suffixes:
        if setup_id.endswith(suffix):
            variants.append(setup_id[: -len(suffix)])

    # Keep order, remove duplicates.
    out = []
    for item in variants:
        if item and item not in out:
            out.append(item)

    return out


def build_setup_index(setup_rows):
    index = {}

    for row in setup_rows:
        setup_id = str(row.get("setup_id") or "").strip()
        if not setup_id:
            continue
        index.setdefault(setup_id, []).append(row)

    return index


def latest_setup_match(index, setup_id):
    for candidate in setup_variants(setup_id):
        rows = index.get(candidate) or []
        if rows:
            return candidate, rows[-1]

    return None, None


def is_clean_closed_postfix_trade(trade, baseline_keys):
    key = trade_key(trade)

    if not key or key in baseline_keys:
        return False

    if trade.get("status") != "CLOSED":
        return False

    required = [
        "final_result",
        "close_reason",
        "close_price",
        "realized_profit",
    ]

    return all(trade.get(field) not in [None, ""] for field in required)


def classify_reconciliation(trade, setup_row):
    issues = []

    trade_final = trade.get("final_result")
    setup_final = setup_row.get("final_outcome") if setup_row else None
    setup_status = setup_row.get("status") if setup_row else None

    if setup_row is None:
        issues.append("NO_MATCHING_SETUP_OUTCOME")
        return issues

    if setup_final in [None, ""]:
        issues.append("SETUP_OUTCOME_MISSING_FINAL_OUTCOME")

    if setup_final == "W10":
        issues.append("SETUP_OUTCOME_W10_WHILE_POSTFIX_TRADE_CLOSED")

    if setup_status == "TRACKING":
        issues.append("SETUP_OUTCOME_TRACKING_WHILE_POSTFIX_TRADE_CLOSED")

    if trade_final == "WIN" and setup_final not in ["TP_TOUCH", "WIN", "PROFIT_CLOSE"]:
        issues.append("TRADE_WIN_SETUP_NOT_TP")

    if trade_final == "LOSS" and setup_final not in ["SL_TOUCH", "LOSS", "LOSS_CLOSE"]:
        issues.append("TRADE_LOSS_SETUP_NOT_SL")

    return issues


def compact_row(trade, matched_setup_id, setup_row, issues):
    return {
        "trade_key": trade_key(trade),
        "trade_setup_id": trade.get("setup_id"),
        "matched_setup_id": matched_setup_id,
        "strategy": trade.get("strategy"),
        "signal": trade.get("signal"),
        "trade_status": trade.get("status"),
        "trade_final_result": trade.get("final_result"),
        "trade_close_reason": trade.get("close_reason"),
        "trade_close_price": trade.get("close_price"),
        "trade_realized_profit": trade.get("realized_profit"),
        "setup_status": setup_row.get("status") if setup_row else None,
        "setup_final_outcome": setup_row.get("final_outcome") if setup_row else None,
        "setup_entry": setup_row.get("entry") if setup_row else None,
        "setup_sl": setup_row.get("sl") if setup_row else None,
        "setup_tp": setup_row.get("tp") if setup_row else None,
        "setup_reason": setup_row.get("reason") if setup_row else None,
        "issue_count": len(issues),
        "issues": issues,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Audit post-fix clean closed trades against setup_outcomes final outcomes."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument("--strict", action="store_true")

    args = parser.parse_args()
    paths = resolve_paths(args.source_dir)

    trades = flatten_json_container(read_json(paths["trades_file"], default=[]))
    setup_rows = flatten_json_container(read_json(paths["setup_outcomes_file"], default=[]))
    baseline = read_json(paths["baseline_file"], default={})

    baseline_keys = set(baseline.get("known_trade_keys") or [])
    setup_index = build_setup_index(setup_rows)

    clean_closed = [
        trade for trade in trades
        if is_clean_closed_postfix_trade(trade, baseline_keys)
    ]

    audited = []

    for trade in clean_closed:
        matched_setup_id, setup_row = latest_setup_match(setup_index, trade.get("setup_id"))
        issues = classify_reconciliation(trade, setup_row)
        audited.append(compact_row(trade, matched_setup_id, setup_row, issues))

    issue_rows = [row for row in audited if row["issue_count"] > 0]

    issue_type_counts = {}

    for row in issue_rows:
        for issue in row["issues"]:
            issue_type_counts[issue] = issue_type_counts.get(issue, 0) + 1

    all_ok = len(issue_rows) == 0

    if all_ok and clean_closed:
        recommendation = "POSTFIX_OUTCOME_RECONCILIATION_OK"
    elif not clean_closed:
        recommendation = "WAITING_FOR_POSTFIX_CLOSED_TRADES"
    else:
        recommendation = "FIX_SETUP_OUTCOME_POSTFIX_CLOSE_RECONCILIATION"

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2AK",
        "source_dir": str(paths["source_dir"]),
        "all_ok": all_ok,
        "recommendation": recommendation,
        "counts": {
            "postfix_clean_closed_trade_count": len(clean_closed),
            "audited_trade_count": len(audited),
            "issue_trade_count": len(issue_rows),
            "setup_outcome_count": len(setup_rows),
        },
        "issue_type_counts": issue_type_counts,
        "issue_rows": issue_rows[:100],
        "audited_rows": audited[-50:],
        "generated_files": {
            "report_json": str(paths["report_json"]),
        },
        "notes": [
            "This is diagnostic only.",
            "It checks whether clean post-fix CLOSED trades are reflected correctly in setup_outcomes.json.",
            "MTFOVERRIDE suffixes are matched back to the base setup_id when possible.",
        ],
    }

    write_json(paths["report_json"], report)

    print("[PHASE 2AK POST-FIX OUTCOME RECONCILIATION]")
    print("all_ok =", all_ok)
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
    print("[ISSUE ROWS]")
    for row in issue_rows[:30]:
        print(
            f"{row.get('trade_setup_id')} | matched={row.get('matched_setup_id')} | "
            f"trade_final={row.get('trade_final_result')} | "
            f"setup_final={row.get('setup_final_outcome')} | "
            f"setup_status={row.get('setup_status')} | "
            f"issues={row.get('issues')}"
        )

    print()
    print("report =", paths["report_json"])

    if args.strict and not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
