import argparse
import json
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.setup_outcome_reconciler import reconcile_setup_outcome_from_closed_trade


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
        "report_json": output_dir / "postfix_setup_outcome_backfill_report.json",
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


def compact_trade(trade):
    return {
        "trade_key": trade_key(trade),
        "setup_id": trade.get("setup_id"),
        "strategy": trade.get("strategy"),
        "signal": trade.get("signal"),
        "status": trade.get("status"),
        "final_result": trade.get("final_result"),
        "close_reason": trade.get("close_reason"),
        "close_price": trade.get("close_price"),
        "realized_profit": trade.get("realized_profit"),
        "position_id": trade.get("position_id"),
        "main_position_id": trade.get("main_position_id"),
        "trade_role": trade.get("trade_role"),
        "close_time": trade.get("close_time"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Backfill setup_outcomes.json from clean post-fix closed trades."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually update setup_outcomes.json. Without this flag, dry-run only.",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)

    trades = flatten_json_container(read_json(paths["trades_file"], default=[]))
    baseline = read_json(paths["baseline_file"], default={})
    baseline_keys = set(baseline.get("known_trade_keys") or [])

    target_trades = [
        trade
        for trade in trades
        if is_clean_closed_postfix_trade(trade, baseline_keys)
    ]

    results = []

    for trade in target_trades:
        if args.apply:
            result = reconcile_setup_outcome_from_closed_trade(
                trade,
                setup_outcomes_file=paths["setup_outcomes_file"],
            )
        else:
            result = {
                "ok": True,
                "action": "DRY_RUN",
                "setup_id": trade.get("setup_id"),
                "trade_setup_id": trade.get("setup_id"),
            }

        results.append({
            "trade": compact_trade(trade),
            "result": result,
        })

    action_counts = {}

    for row in results:
        action = (row.get("result") or {}).get("action") or "UNKNOWN"
        action_counts[action] = action_counts.get(action, 0) + 1

    failed = [
        row for row in results
        if not (row.get("result") or {}).get("ok")
    ]

    all_ok = len(failed) == 0

    if not args.apply:
        recommendation = "DRY_RUN_REVIEW_THEN_RUN_WITH_APPLY"
    elif all_ok:
        recommendation = "POSTFIX_SETUP_OUTCOME_BACKFILL_APPLIED"
    else:
        recommendation = "REVIEW_BACKFILL_FAILURES"

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2AN",
        "source_dir": str(paths["source_dir"]),
        "apply": args.apply,
        "all_ok": all_ok,
        "recommendation": recommendation,
        "counts": {
            "target_clean_closed_postfix_trade_count": len(target_trades),
            "result_count": len(results),
            "failed_count": len(failed),
        },
        "action_counts": action_counts,
        "failed_rows": failed[:50],
        "results": results,
        "generated_files": {
            "report_json": str(paths["report_json"]),
            "setup_outcomes_file": str(paths["setup_outcomes_file"]),
        },
        "notes": [
            "Dry-run is default.",
            "Use --apply to update setup_outcomes.json.",
            "This uses the same runtime reconciler called by trade_tracker.py.",
        ],
    }

    write_json(paths["report_json"], report)

    print("[PHASE 2AN POST-FIX SETUP OUTCOME BACKFILL]")
    print("apply =", args.apply)
    print("all_ok =", all_ok)
    print("recommendation =", recommendation)

    print()
    print("[COUNTS]")
    for key, value in report["counts"].items():
        print(f"{key} = {value}")

    print()
    print("[ACTION COUNTS]")
    for key, value in sorted(action_counts.items()):
        print(f"{key} = {value}")

    print()
    print("[TARGET TRADES]")
    for row in results[:30]:
        trade = row.get("trade") or {}
        result = row.get("result") or {}
        print(
            f"{trade.get('setup_id')} | "
            f"final={trade.get('final_result')} | "
            f"reason={trade.get('close_reason')} | "
            f"profit={trade.get('realized_profit')} | "
            f"action={result.get('action')} | "
            f"ok={result.get('ok')}"
        )

    print()
    print("report =", paths["report_json"])

    if args.strict and not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
