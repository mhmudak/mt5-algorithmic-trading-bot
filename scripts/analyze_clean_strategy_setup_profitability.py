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
        "report_json": output_dir / "clean_strategy_setup_profitability_report.json",
        "by_strategy_csv": output_dir / "clean_profitability_by_strategy.csv",
        "by_setup_csv": output_dir / "clean_profitability_by_setup.csv",
        "by_strategy_signal_csv": output_dir / "clean_profitability_by_strategy_signal.csv",
        "by_strategy_role_csv": output_dir / "clean_profitability_by_strategy_role.csv",
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


def safe_float(value, default=0.0):
    try:
        return float(value or 0.0)
    except Exception:
        return default


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


def setup_id_base(setup_id):
    setup_id = str(setup_id or "").strip()

    for suffix in ["-MTFOVERRIDE", "-EXTRA", "-MAIN"]:
        if setup_id.endswith(suffix):
            return setup_id[: -len(suffix)]

    return setup_id


def classify_bucket(row, min_sample=10):
    n = row["trade_count"]
    net = row["net_profit"]
    wins = row["win_count"]
    losses = row["loss_count"]
    be_rate = row["breakeven_rate"]

    if n < min_sample:
        return "TOO_FEW_TRADES_OBSERVE_ONLY"

    if losses == 0 and wins > 0 and net > 0 and be_rate >= 0.70:
        return "PROMISING_BUT_BE_TOO_HIGH"

    if losses == 0 and wins > 0 and net > 0:
        return "PROMISING_OBSERVE_MORE"

    if be_rate >= 0.80 and wins == 0:
        return "NO_DECISIVE_EDGE_YET_HIGH_BE"

    if losses > wins and net <= 0:
        return "WEAK_REVIEW_REQUIRED"

    return "OBSERVE_MORE"


def summarize_group(trades, group_name, group_value, min_sample=10):
    n = len(trades)

    wins = [x for x in trades if x.get("final_result") == "WIN"]
    losses = [x for x in trades if x.get("final_result") == "LOSS"]
    bes = [x for x in trades if x.get("final_result") == "BREAKEVEN"]

    profits = [safe_float(x.get("realized_profit")) for x in trades]

    gross_profit = round(sum(x for x in profits if x > 0), 2)
    gross_loss = round(sum(x for x in profits if x < 0), 2)
    net_profit = round(sum(profits), 2)

    decisive_count = len(wins) + len(losses)

    row = {
        "group": group_name,
        "value": group_value,
        "trade_count": n,
        "win_count": len(wins),
        "loss_count": len(losses),
        "breakeven_count": len(bes),
        "decisive_count": decisive_count,
        "win_rate_all": round(len(wins) / n, 4) if n else None,
        "win_rate_decisive": round(len(wins) / decisive_count, 4) if decisive_count else None,
        "loss_rate_all": round(len(losses) / n, 4) if n else None,
        "breakeven_rate": round(len(bes) / n, 4) if n else None,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_profit": net_profit,
        "avg_profit_per_trade": round(net_profit / n, 4) if n else 0.0,
        "profit_factor": (
            round(gross_profit / abs(gross_loss), 4)
            if gross_loss < 0
            else ("INF" if gross_profit > 0 else None)
        ),
    }

    row["classification"] = classify_bucket(row, min_sample=min_sample)

    return row


def summarize_by_field(trades, field, min_sample=10):
    buckets = defaultdict(list)

    for trade in trades:
        value = trade.get(field)

        if value in [None, ""]:
            value = "UNKNOWN"

        if field == "setup_id":
            value = setup_id_base(value)

        buckets[str(value)].append(trade)

    rows = [
        summarize_group(items, field, key, min_sample=min_sample)
        for key, items in buckets.items()
    ]

    rows.sort(
        key=lambda x: (
            -x["trade_count"],
            -float(x["net_profit"] or 0),
            str(x["value"]),
        )
    )

    return rows


def summarize_by_composite(trades, fields, group_name, min_sample=10):
    buckets = defaultdict(list)

    for trade in trades:
        parts = []

        for field in fields:
            value = trade.get(field)

            if value in [None, ""]:
                value = "UNKNOWN"

            if field == "setup_id":
                value = setup_id_base(value)

            parts.append(str(value))

        key = "|".join(parts)
        buckets[key].append(trade)

    rows = [
        summarize_group(items, group_name, key, min_sample=min_sample)
        for key, items in buckets.items()
    ]

    rows.sort(
        key=lambda x: (
            -x["trade_count"],
            -float(x["net_profit"] or 0),
            str(x["value"]),
        )
    )

    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Analyze clean post-fix profitability by strategy and setup."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument("--min-sample", type=int, default=10)

    args = parser.parse_args()
    paths = resolve_paths(args.source_dir)

    trades = flatten_json_container(read_json(paths["trades_file"], default=[]))
    baseline = read_json(paths["baseline_file"], default={})
    baseline_keys = set(baseline.get("known_trade_keys") or [])

    clean_trades = [
        trade
        for trade in trades
        if is_clean_closed_postfix_trade(trade, baseline_keys)
    ]

    overall = summarize_group(
        clean_trades,
        "overall",
        "ALL_CLEAN_POSTFIX_CLOSED_TRADES",
        min_sample=args.min_sample,
    )

    by_strategy = summarize_by_field(clean_trades, "strategy", min_sample=args.min_sample)
    by_setup = summarize_by_field(clean_trades, "setup_id", min_sample=args.min_sample)
    by_strategy_signal = summarize_by_composite(
        clean_trades,
        ["strategy", "signal"],
        "strategy_signal",
        min_sample=args.min_sample,
    )
    by_strategy_role = summarize_by_composite(
        clean_trades,
        ["strategy", "trade_role"],
        "strategy_role",
        min_sample=args.min_sample,
    )

    classifications = defaultdict(int)

    for row in by_strategy:
        classifications[row["classification"]] += 1

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2AV",
        "all_ok": True,
        "recommendation": "CLEAN_PROFITABILITY_STATS_READY_OBSERVE_ONLY",
        "source_dir": str(paths["source_dir"]),
        "counts": {
            "total_trade_count": len(trades),
            "baseline_trade_count": len(baseline_keys),
            "clean_closed_trade_count": len(clean_trades),
            "strategy_count": len(by_strategy),
            "setup_count": len(by_setup),
            "min_sample": args.min_sample,
        },
        "overall": overall,
        "strategy_classification_counts": dict(sorted(classifications.items())),
        "by_strategy": by_strategy,
        "by_strategy_signal": by_strategy_signal,
        "by_strategy_role": by_strategy_role,
        "top_setups": by_setup[:100],
        "generated_files": {
            "report_json": str(paths["report_json"]),
            "by_strategy_csv": str(paths["by_strategy_csv"]),
            "by_setup_csv": str(paths["by_setup_csv"]),
            "by_strategy_signal_csv": str(paths["by_strategy_signal_csv"]),
            "by_strategy_role_csv": str(paths["by_strategy_role_csv"]),
        },
        "notes": [
            "Observe-only statistics.",
            "Uses only clean closed post-fix trades after reconciliation baseline.",
            "Do not optimize parameters from low-sample groups.",
            "High breakeven groups should be reviewed through exit-management logic before changing entry filters.",
        ],
    }

    write_json(paths["report_json"], report)
    write_csv(paths["by_strategy_csv"], by_strategy)
    write_csv(paths["by_setup_csv"], by_setup)
    write_csv(paths["by_strategy_signal_csv"], by_strategy_signal)
    write_csv(paths["by_strategy_role_csv"], by_strategy_role)

    print("[PHASE 2AV CLEAN STRATEGY / SETUP PROFITABILITY]")
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
    for row in by_strategy:
        print(
            f"{row['value']} | n={row['trade_count']} "
            f"win={row['win_count']} loss={row['loss_count']} be={row['breakeven_count']} "
            f"be_rate={row['breakeven_rate']} net={row['net_profit']} "
            f"avg={row['avg_profit_per_trade']} class={row['classification']}"
        )

    print()
    print("[BY STRATEGY + SIGNAL]")
    for row in by_strategy_signal:
        print(
            f"{row['value']} | n={row['trade_count']} "
            f"win={row['win_count']} loss={row['loss_count']} be={row['breakeven_count']} "
            f"net={row['net_profit']} class={row['classification']}"
        )

    print()
    print("[BY STRATEGY + ROLE]")
    for row in by_strategy_role:
        print(
            f"{row['value']} | n={row['trade_count']} "
            f"win={row['win_count']} loss={row['loss_count']} be={row['breakeven_count']} "
            f"net={row['net_profit']} class={row['classification']}"
        )

    print()
    print("report =", paths["report_json"])
    print("by_strategy_csv =", paths["by_strategy_csv"])
    print("by_setup_csv =", paths["by_setup_csv"])
    print("by_strategy_signal_csv =", paths["by_strategy_signal_csv"])
    print("by_strategy_role_csv =", paths["by_strategy_role_csv"])


if __name__ == "__main__":
    main()
