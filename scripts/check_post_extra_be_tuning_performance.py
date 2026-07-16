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
        "baseline_file": output_dir / "post_extra_be_tuning_baseline.json",
        "report_json": output_dir / "post_extra_be_tuning_performance_report.json",
        "by_strategy_csv": output_dir / "post_extra_be_tuning_by_strategy.csv",
        "by_role_csv": output_dir / "post_extra_be_tuning_by_role.csv",
        "trades_csv": output_dir / "post_extra_be_tuning_trades.csv",
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


def is_clean_closed_trade(trade):
    if trade.get("status") != "CLOSED":
        return False

    required = [
        "final_result",
        "close_reason",
        "close_price",
        "realized_profit",
    ]

    return all(trade.get(field) not in [None, ""] for field in required)


def is_extra_trade(trade):
    return str(trade.get("trade_role") or "").upper() == "EXTRA"


def is_breakeven_trade(trade):
    final_result = str(trade.get("final_result") or "").upper()
    close_reason = str(trade.get("close_reason") or "").upper()
    realized_profit = safe_float(trade.get("realized_profit"))

    return final_result == "BREAKEVEN" or close_reason == "BREAKEVEN" or realized_profit == 0.0


def summarize(rows, group, value):
    n = len(rows)

    wins = [x for x in rows if x.get("final_result") == "WIN"]
    losses = [x for x in rows if x.get("final_result") == "LOSS"]
    bes = [x for x in rows if is_breakeven_trade(x)]
    extras = [x for x in rows if is_extra_trade(x)]
    extra_bes = [x for x in extras if is_breakeven_trade(x)]

    profits = [safe_float(x.get("realized_profit")) for x in rows]
    gross_profit = round(sum(x for x in profits if x > 0), 2)
    gross_loss = round(sum(x for x in profits if x < 0), 2)
    net_profit = round(sum(profits), 2)

    decisive = len(wins) + len(losses)

    return {
        "group": group,
        "value": value,
        "trade_count": n,
        "win_count": len(wins),
        "loss_count": len(losses),
        "breakeven_count": len(bes),
        "extra_trade_count": len(extras),
        "extra_breakeven_count": len(extra_bes),
        "decisive_count": decisive,
        "win_rate_all": round(len(wins) / n, 4) if n else None,
        "win_rate_decisive": round(len(wins) / decisive, 4) if decisive else None,
        "loss_rate_all": round(len(losses) / n, 4) if n else None,
        "breakeven_rate": round(len(bes) / n, 4) if n else None,
        "extra_breakeven_rate": round(len(extra_bes) / len(extras), 4) if extras else None,
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


def group_by(rows, field):
    buckets = defaultdict(list)

    for row in rows:
        value = row.get(field)

        if value in [None, ""]:
            value = "UNKNOWN"

        buckets[str(value)].append(row)

    out = [summarize(items, field, key) for key, items in buckets.items()]
    out.sort(key=lambda x: (-x["trade_count"], -float(x["net_profit"] or 0), x["value"]))
    return out


def compact_trade(trade):
    return {
        "position_id": trade.get("position_id"),
        "setup_id": trade.get("setup_id"),
        "strategy": trade.get("strategy"),
        "signal": trade.get("signal"),
        "trade_role": trade.get("trade_role"),
        "status": trade.get("status"),
        "final_result": trade.get("final_result"),
        "close_reason": trade.get("close_reason"),
        "realized_profit": safe_float(trade.get("realized_profit")),
        "entry_price": safe_float(trade.get("entry_price")),
        "close_price": safe_float(trade.get("close_price")),
        "max_profit_price": safe_float(trade.get("max_profit_price")),
        "open_time": trade.get("open_time"),
        "close_time": trade.get("close_time"),
    }


def create_baseline(paths, trades):
    keys = sorted(k for k in [trade_key(t) for t in trades] if k)

    baseline = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2BC",
        "reason": "Baseline after conservative extra-BE tuning settings were applied.",
        "trade_count": len(trades),
        "known_trade_keys": keys,
        "settings_snapshot": {
            "EXTRA_ENTRY_BREAK_EVEN_TRIGGER_PRICE": 3.5,
            "EXTRA_ENTRY_LOCK_TRIGGER_PRICE": 4.5,
            "EXTRA_ENTRY_LOCK_PRICE": 2.0,
            "EXTRA_ENTRY_TAKE_PROFIT_PRICE": 6.0,
            "WORST_EXTRA_LOCK_TRIGGER_PRICE": 2.5,
            "WORST_EXTRA_LOCK_PROFIT_PRICE": 1.0,
        },
    }

    write_json(paths["baseline_file"], baseline)
    return baseline


def main():
    parser = argparse.ArgumentParser(
        description="Monitor performance after conservative extra-BE tuning."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--reset-baseline",
        action="store_true",
        help="Reset baseline to current trades. Use only immediately after settings change and before live monitoring.",
    )

    args = parser.parse_args()
    paths = resolve_paths(args.source_dir)

    trades = flatten_json_container(read_json(paths["trades_file"], default=[]))

    if args.reset_baseline or not paths["baseline_file"].exists():
        baseline = create_baseline(paths, trades)
        baseline_created = True
    else:
        baseline = read_json(paths["baseline_file"], default={})
        baseline_created = False

    baseline_keys = set(baseline.get("known_trade_keys") or [])

    post_tuning_trades = [
        trade
        for trade in trades
        if trade_key(trade) and trade_key(trade) not in baseline_keys
    ]

    clean_closed = [
        trade
        for trade in post_tuning_trades
        if is_clean_closed_trade(trade)
    ]

    overall = summarize(clean_closed, "overall", "POST_EXTRA_BE_TUNING_CLEAN_CLOSED")
    by_strategy = group_by(clean_closed, "strategy")
    by_role = group_by(clean_closed, "trade_role")
    trade_rows = [compact_trade(t) for t in clean_closed]

    extra_rows = [x for x in clean_closed if is_extra_trade(x)]
    extra_be_rows = [x for x in extra_rows if is_breakeven_trade(x)]

    if len(clean_closed) < 20:
        recommendation = "COLLECT_MORE_POST_TUNING_TRADES"
    elif overall["loss_count"] >= 5:
        recommendation = "REVIEW_TUNING_LOSS_COUNT_INCREASED"
    elif extra_rows and len(extra_be_rows) / len(extra_rows) < 0.70 and overall["net_profit"] >= 0:
        recommendation = "POST_TUNING_IMPROVEMENT_POSSIBLE_OBSERVE_MORE"
    elif overall["net_profit"] < 0:
        recommendation = "POST_TUNING_NEGATIVE_REVIEW_OR_REVERT"
    else:
        recommendation = "OBSERVE_MORE"

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2BC",
        "all_ok": True,
        "recommendation": recommendation,
        "baseline_created_now": baseline_created,
        "baseline": {
            "created_at": baseline.get("created_at"),
            "trade_count": baseline.get("trade_count"),
            "baseline_file": str(paths["baseline_file"]),
        },
        "counts": {
            "current_total_trade_count": len(trades),
            "baseline_trade_count": len(baseline_keys),
            "post_tuning_trade_count": len(post_tuning_trades),
            "post_tuning_clean_closed_trade_count": len(clean_closed),
            "post_tuning_extra_trade_count": len(extra_rows),
            "post_tuning_extra_be_count": len(extra_be_rows),
        },
        "overall": overall,
        "by_strategy": by_strategy,
        "by_role": by_role,
        "generated_files": {
            "report_json": str(paths["report_json"]),
            "by_strategy_csv": str(paths["by_strategy_csv"]),
            "by_role_csv": str(paths["by_role_csv"]),
            "trades_csv": str(paths["trades_csv"]),
            "baseline_file": str(paths["baseline_file"]),
        },
        "notes": [
            "This monitor isolates trades opened after the conservative extra-BE tuning baseline.",
            "Do not judge the tuning before at least 20 clean closed post-tuning trades.",
            "Main success metric: lower extra breakeven rate without sharp increase in losses.",
        ],
    }

    write_json(paths["report_json"], report)
    write_csv(paths["by_strategy_csv"], by_strategy)
    write_csv(paths["by_role_csv"], by_role)
    write_csv(paths["trades_csv"], trade_rows)

    print("[PHASE 2BC POST EXTRA-BE TUNING PERFORMANCE]")
    print("all_ok =", report["all_ok"])
    print("recommendation =", recommendation)
    print("baseline_created_now =", baseline_created)

    print()
    print("[BASELINE]")
    print("baseline_created_at =", baseline.get("created_at"))
    print("baseline_trade_count =", baseline.get("trade_count"))
    print("baseline_file =", paths["baseline_file"])

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
            f"extra_be={row['extra_breakeven_count']} net={row['net_profit']} "
            f"be_rate={row['breakeven_rate']} extra_be_rate={row['extra_breakeven_rate']}"
        )

    print()
    print("[BY ROLE]")
    for row in by_role:
        print(
            f"{row['value']} | n={row['trade_count']} "
            f"win={row['win_count']} loss={row['loss_count']} be={row['breakeven_count']} "
            f"net={row['net_profit']} be_rate={row['breakeven_rate']}"
        )

    print()
    print("report =", paths["report_json"])
    print("trades_csv =", paths["trades_csv"])


if __name__ == "__main__":
    main()
