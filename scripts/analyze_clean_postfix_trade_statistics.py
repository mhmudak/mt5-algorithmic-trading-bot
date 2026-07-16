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
        "baseline_file": output_dir / "postfix_trade_reconciliation_baseline.json",
        "report_json": output_dir / "clean_postfix_trade_statistics_report.json",
        "strategy_csv": output_dir / "clean_postfix_trade_statistics_by_strategy.csv",
        "setup_csv": output_dir / "clean_postfix_trade_statistics_by_setup.csv",
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


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        path.write_text("", encoding="utf-8")
        return path

    headers = []

    for row in rows:
        for key in row.keys():
            if key not in headers:
                headers.append(key)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

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


def safe_float(value, default=0.0):
    try:
        return float(value or 0.0)
    except Exception:
        return default


def group_key(trade, field):
    value = trade.get(field)

    if value in [None, ""]:
        return "UNKNOWN"

    return str(value)


def summarize_group(rows, group_name, group_value):
    n = len(rows)

    wins = sum(1 for x in rows if x.get("final_result") == "WIN")
    losses = sum(1 for x in rows if x.get("final_result") == "LOSS")
    breakevens = sum(1 for x in rows if x.get("final_result") == "BREAKEVEN")

    profits = [safe_float(x.get("realized_profit")) for x in rows]
    total_profit = round(sum(profits), 2)

    gross_profit = round(sum(x for x in profits if x > 0), 2)
    gross_loss = round(sum(x for x in profits if x < 0), 2)

    avg_profit = round(total_profit / n, 4) if n else 0.0

    decisive_count = wins + losses
    win_rate_all = round(wins / n, 4) if n else None
    win_rate_decisive = round(wins / decisive_count, 4) if decisive_count else None
    breakeven_rate = round(breakevens / n, 4) if n else None

    if abs(gross_loss) > 0:
        profit_factor = round(gross_profit / abs(gross_loss), 4)
    elif gross_profit > 0:
        profit_factor = "INF"
    else:
        profit_factor = None

    return {
        "group": group_name,
        "value": group_value,
        "trade_count": n,
        "win_count": wins,
        "loss_count": losses,
        "breakeven_count": breakevens,
        "decisive_count": decisive_count,
        "win_rate_all": win_rate_all,
        "win_rate_decisive": win_rate_decisive,
        "breakeven_rate": breakeven_rate,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_profit": total_profit,
        "avg_profit_per_trade": avg_profit,
        "profit_factor": profit_factor,
        "recommendation": recommendation_for_group(n, wins, losses, breakevens, total_profit),
    }


def recommendation_for_group(n, wins, losses, breakevens, total_profit):
    if n < 10:
        return "TOO_FEW_TRADES_OBSERVE_ONLY"

    if wins == 0 and total_profit <= 0:
        return "WEAK_OR_NO_EDGE_REVIEW"

    if total_profit > 0 and wins > losses:
        return "PROMISING_OBSERVE_MORE"

    if breakevens / n >= 0.7:
        return "HIGH_BREAKEVEN_RATE_REVIEW_EXIT_MANAGEMENT"

    return "OBSERVE_MORE"


def summarize_by_field(rows, field):
    buckets = defaultdict(list)

    for row in rows:
        buckets[group_key(row, field)].append(row)

    summaries = [
        summarize_group(bucket_rows, field, key)
        for key, bucket_rows in buckets.items()
    ]

    summaries.sort(
        key=lambda x: (
            -x["trade_count"],
            -float(x["net_profit"] or 0),
            str(x["value"]),
        )
    )

    return summaries


def main():
    parser = argparse.ArgumentParser(
        description="Analyze clean post-fix closed trade statistics."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument("--min-trades", type=int, default=5)

    args = parser.parse_args()
    paths = resolve_paths(args.source_dir)

    trades = flatten_json_container(read_json(paths["trades_file"], default=[]))
    baseline = read_json(paths["baseline_file"], default={})
    baseline_keys = set(baseline.get("known_trade_keys") or [])

    clean_closed = [
        trade
        for trade in trades
        if is_clean_closed_postfix_trade(trade, baseline_keys)
    ]

    strategy_rows = summarize_by_field(clean_closed, "strategy")
    setup_rows = summarize_by_field(clean_closed, "setup_id")
    signal_rows = summarize_by_field(clean_closed, "signal")
    role_rows = summarize_by_field(clean_closed, "trade_role")

    overall = summarize_group(clean_closed, "overall", "ALL_CLEAN_POSTFIX_CLOSED_TRADES")

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2AS",
        "source_dir": str(paths["source_dir"]),
        "all_ok": True,
        "recommendation": "STATISTICS_READY_OBSERVE_ONLY",
        "counts": {
            "clean_closed_trade_count": len(clean_closed),
            "baseline_trade_count": len(baseline_keys),
            "total_trade_count": len(trades),
            "min_trades": args.min_trades,
        },
        "overall": overall,
        "by_strategy": strategy_rows,
        "by_signal": signal_rows,
        "by_trade_role": role_rows,
        "top_setups": setup_rows[:50],
        "generated_files": {
            "report_json": str(paths["report_json"]),
            "strategy_csv": str(paths["strategy_csv"]),
            "setup_csv": str(paths["setup_csv"]),
        },
        "notes": [
            "This is observe-only statistical analysis.",
            "It uses only post-fix clean CLOSED trades after the reconciliation baseline.",
            "Do not optimize parameters directly from this sample size.",
            "Use this to identify where more data is needed and which buckets deserve review.",
        ],
    }

    write_json(paths["report_json"], report)
    write_csv(paths["strategy_csv"], strategy_rows)
    write_csv(paths["setup_csv"], setup_rows)

    print("[PHASE 2AS CLEAN POST-FIX TRADE STATISTICS]")
    print("all_ok =", report["all_ok"])
    print("recommendation =", report["recommendation"])

    print()
    print("[COUNTS]")
    for key, value in report["counts"].items():
        print(f"{key} = {value}")

    print()
    print("[OVERALL]")
    for key, value in overall.items():
        print(f"{key} = {value}")

    print()
    print("[BY STRATEGY]")
    for row in strategy_rows:
        print(
            f"{row['value']} | n={row['trade_count']} "
            f"win={row['win_count']} loss={row['loss_count']} be={row['breakeven_count']} "
            f"win_rate_all={row['win_rate_all']} net={row['net_profit']} "
            f"avg={row['avg_profit_per_trade']} rec={row['recommendation']}"
        )

    print()
    print("[BY SIGNAL]")
    for row in signal_rows:
        print(
            f"{row['value']} | n={row['trade_count']} "
            f"win={row['win_count']} loss={row['loss_count']} be={row['breakeven_count']} "
            f"net={row['net_profit']} rec={row['recommendation']}"
        )

    print()
    print("report =", paths["report_json"])
    print("strategy_csv =", paths["strategy_csv"])
    print("setup_csv =", paths["setup_csv"])


if __name__ == "__main__":
    main()
