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
        "report_json": output_dir / "breakeven_exit_management_report.json",
        "be_trades_csv": output_dir / "breakeven_exit_management_trades.csv",
        "setup_clusters_csv": output_dir / "breakeven_exit_management_setup_clusters.csv",
        "strategy_csv": output_dir / "breakeven_exit_management_by_strategy.csv",
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


def is_breakeven_trade(trade):
    final_result = str(trade.get("final_result") or "").upper()
    close_reason = str(trade.get("close_reason") or "").upper()
    realized_profit = safe_float(trade.get("realized_profit"))

    return (
        final_result == "BREAKEVEN"
        or close_reason == "BREAKEVEN"
        or realized_profit == 0.0
    )


def setup_id_base(setup_id):
    setup_id = str(setup_id or "").strip()

    for suffix in ["-MTFOVERRIDE", "-EXTRA", "-MAIN"]:
        if setup_id.endswith(suffix):
            return setup_id[: -len(suffix)]

    return setup_id


def reached_level_count(trade):
    reached = trade.get("reached_levels") or {}

    if not isinstance(reached, dict):
        return 0

    return sum(1 for value in reached.values() if bool(value))


def infer_be_diagnosis(trade, cluster=None):
    role = str(trade.get("trade_role") or "").upper()
    close_reason = str(trade.get("close_reason") or "").upper()
    final_result = str(trade.get("final_result") or "").upper()
    max_profit_price = safe_float(trade.get("max_profit_price"))
    tp_buffer = safe_float(trade.get("tp_buffer"))
    reached_count = reached_level_count(trade)

    cluster = cluster or {}
    cluster_has_win = bool(cluster.get("win_count", 0) > 0)
    cluster_main_win = bool(cluster.get("main_win_count", 0) > 0)
    cluster_extra_be = bool(cluster.get("extra_breakeven_count", 0) > 0)

    if role == "EXTRA" and close_reason == "BREAKEVEN":
        if cluster_main_win or cluster_has_win:
            return "EXTRA_BE_AFTER_SETUP_WIN_PROTECTION_LIKELY"
        return "EXTRA_POSITION_PROTECTED_TO_BREAKEVEN"

    if role == "MAIN" and close_reason == "BREAKEVEN":
        if cluster_extra_be and cluster_has_win:
            return "MAIN_BE_WITH_WINNING_CLUSTER_REVIEW_PROTECTION_TIMING"
        if reached_count > 0:
            return "MAIN_BE_AFTER_PARTIAL_PROGRESS_REVIEW_TRAILING"
        return "MAIN_BE_EARLY_PROTECTION_OR_NO_FOLLOW_THROUGH"

    if final_result == "BREAKEVEN":
        return "BREAKEVEN_CLOSE_REVIEW_PROTECTION"

    if max_profit_price > 0 and tp_buffer > 0:
        return "BREAKEVEN_WITH_PROFIT_BUFFER_ACTIVITY"

    return "BREAKEVEN_UNCLASSIFIED"


def compact_trade(trade, cluster=None):
    cluster = cluster or {}

    return {
        "position_id": trade.get("position_id"),
        "main_position_id": trade.get("main_position_id"),
        "setup_id": trade.get("setup_id"),
        "setup_id_base": setup_id_base(trade.get("setup_id")),
        "strategy": trade.get("strategy"),
        "signal": trade.get("signal"),
        "trade_role": trade.get("trade_role"),
        "final_result": trade.get("final_result"),
        "close_reason": trade.get("close_reason"),
        "realized_profit": safe_float(trade.get("realized_profit")),
        "entry_price": safe_float(trade.get("entry_price")),
        "stop_loss": safe_float(trade.get("stop_loss")),
        "take_profit": safe_float(trade.get("take_profit")),
        "close_price": safe_float(trade.get("close_price")),
        "max_profit_price": safe_float(trade.get("max_profit_price")),
        "tp_buffer": safe_float(trade.get("tp_buffer")),
        "reached_level_count": reached_level_count(trade),
        "open_time": trade.get("open_time"),
        "close_time": trade.get("close_time"),
        "cluster_trade_count": cluster.get("trade_count"),
        "cluster_win_count": cluster.get("win_count"),
        "cluster_breakeven_count": cluster.get("breakeven_count"),
        "cluster_extra_breakeven_count": cluster.get("extra_breakeven_count"),
        "diagnosis": infer_be_diagnosis(trade, cluster),
    }


def build_setup_clusters(clean_trades):
    buckets = defaultdict(list)

    for trade in clean_trades:
        buckets[setup_id_base(trade.get("setup_id"))].append(trade)

    rows = []

    for setup_id, trades in buckets.items():
        wins = [x for x in trades if x.get("final_result") == "WIN"]
        losses = [x for x in trades if x.get("final_result") == "LOSS"]
        bes = [x for x in trades if is_breakeven_trade(x)]

        main_trades = [
            x for x in trades
            if str(x.get("trade_role") or "").upper() == "MAIN"
        ]

        extra_trades = [
            x for x in trades
            if str(x.get("trade_role") or "").upper() == "EXTRA"
        ]

        main_wins = [
            x for x in main_trades
            if x.get("final_result") == "WIN"
        ]

        extra_bes = [
            x for x in extra_trades
            if is_breakeven_trade(x)
        ]

        net_profit = round(sum(safe_float(x.get("realized_profit")) for x in trades), 2)

        if main_wins and extra_bes:
            pattern = "MAIN_WIN_EXTRA_BE_CLUSTER"
        elif wins and bes:
            pattern = "WIN_AND_BE_CLUSTER"
        elif bes and not wins and not losses:
            pattern = "ALL_BREAKEVEN_CLUSTER"
        elif wins and not bes and not losses:
            pattern = "PURE_WIN_CLUSTER"
        elif losses:
            pattern = "LOSS_CLUSTER"
        else:
            pattern = "MIXED_CLUSTER"

        rows.append({
            "setup_id_base": setup_id,
            "strategy": trades[0].get("strategy") if trades else "UNKNOWN",
            "signal": trades[0].get("signal") if trades else "UNKNOWN",
            "trade_count": len(trades),
            "main_count": len(main_trades),
            "extra_count": len(extra_trades),
            "win_count": len(wins),
            "loss_count": len(losses),
            "breakeven_count": len(bes),
            "main_win_count": len(main_wins),
            "extra_breakeven_count": len(extra_bes),
            "net_profit": net_profit,
            "pattern": pattern,
            "position_ids": ",".join(str(x.get("position_id")) for x in trades),
        })

    rows.sort(
        key=lambda x: (
            x["pattern"] != "MAIN_WIN_EXTRA_BE_CLUSTER",
            -x["trade_count"],
            -x["net_profit"],
            x["setup_id_base"],
        )
    )

    return rows


def summarize_by_strategy(clean_trades, be_trades):
    strategies = sorted(
        set(str(x.get("strategy") or "UNKNOWN") for x in clean_trades)
    )

    rows = []

    for strategy in strategies:
        all_rows = [
            x for x in clean_trades
            if str(x.get("strategy") or "UNKNOWN") == strategy
        ]

        be_rows = [
            x for x in be_trades
            if str(x.get("strategy") or "UNKNOWN") == strategy
        ]

        extra_be = [
            x for x in be_rows
            if str(x.get("trade_role") or "").upper() == "EXTRA"
        ]

        main_be = [
            x for x in be_rows
            if str(x.get("trade_role") or "").upper() == "MAIN"
        ]

        wins = [x for x in all_rows if x.get("final_result") == "WIN"]
        losses = [x for x in all_rows if x.get("final_result") == "LOSS"]

        trade_count = len(all_rows)
        be_count = len(be_rows)
        net_profit = round(sum(safe_float(x.get("realized_profit")) for x in all_rows), 2)

        if trade_count == 0:
            continue

        be_rate = round(be_count / trade_count, 4)

        if trade_count < 10:
            recommendation = "TOO_FEW_TRADES_OBSERVE_ONLY"
        elif be_rate >= 0.70 and len(wins) > 0 and len(losses) == 0:
            recommendation = "REVIEW_BE_TOO_AGGRESSIVE_BUT_PROMISING"
        elif be_rate >= 0.70:
            recommendation = "HIGH_BE_RATE_REVIEW_EXIT_MANAGEMENT"
        elif net_profit > 0:
            recommendation = "PROMISING_OBSERVE_MORE"
        else:
            recommendation = "OBSERVE_MORE"

        rows.append({
            "strategy": strategy,
            "trade_count": trade_count,
            "win_count": len(wins),
            "loss_count": len(losses),
            "breakeven_count": be_count,
            "extra_breakeven_count": len(extra_be),
            "main_breakeven_count": len(main_be),
            "breakeven_rate": be_rate,
            "net_profit": net_profit,
            "recommendation": recommendation,
        })

    rows.sort(
        key=lambda x: (
            -x["trade_count"],
            -x["breakeven_rate"],
            x["strategy"],
        )
    )

    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Analyze breakeven exit management on clean post-fix closed trades."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

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

    setup_clusters = build_setup_clusters(clean_trades)
    cluster_map = {
        row["setup_id_base"]: row
        for row in setup_clusters
    }

    be_trades = [
        trade
        for trade in clean_trades
        if is_breakeven_trade(trade)
    ]

    be_trade_rows = [
        compact_trade(trade, cluster_map.get(setup_id_base(trade.get("setup_id"))))
        for trade in be_trades
    ]

    strategy_rows = summarize_by_strategy(clean_trades, be_trades)

    pattern_counts = defaultdict(int)

    for cluster in setup_clusters:
        pattern_counts[cluster["pattern"]] += 1

    diagnosis_counts = defaultdict(int)

    for row in be_trade_rows:
        diagnosis_counts[row["diagnosis"]] += 1

    clean_count = len(clean_trades)
    be_count = len(be_trades)

    be_rate = round(be_count / clean_count, 4) if clean_count else 0.0

    high_be_rate = be_rate >= 0.70
    has_wins = any(x.get("final_result") == "WIN" for x in clean_trades)
    has_losses = any(x.get("final_result") == "LOSS" for x in clean_trades)

    if high_be_rate and has_wins and not has_losses:
        recommendation = "REVIEW_BE_PROTECTION_TOO_AGGRESSIVE_BEFORE_ENTRY_OPTIMIZATION"
    elif high_be_rate:
        recommendation = "HIGH_BREAKEVEN_RATE_REVIEW_EXIT_MANAGEMENT"
    else:
        recommendation = "BREAKEVEN_RATE_ACCEPTABLE_OBSERVE_MORE"

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2AT",
        "source_dir": str(paths["source_dir"]),
        "all_ok": True,
        "recommendation": recommendation,
        "counts": {
            "clean_closed_trade_count": clean_count,
            "breakeven_trade_count": be_count,
            "breakeven_rate": be_rate,
            "setup_cluster_count": len(setup_clusters),
            "main_win_extra_be_cluster_count": pattern_counts.get("MAIN_WIN_EXTRA_BE_CLUSTER", 0),
            "all_breakeven_cluster_count": pattern_counts.get("ALL_BREAKEVEN_CLUSTER", 0),
        },
        "diagnosis_counts": dict(sorted(diagnosis_counts.items())),
        "pattern_counts": dict(sorted(pattern_counts.items())),
        "by_strategy": strategy_rows,
        "setup_clusters": setup_clusters,
        "breakeven_trades": be_trade_rows,
        "generated_files": {
            "report_json": str(paths["report_json"]),
            "be_trades_csv": str(paths["be_trades_csv"]),
            "setup_clusters_csv": str(paths["setup_clusters_csv"]),
            "strategy_csv": str(paths["strategy_csv"]),
        },
        "notes": [
            "This is observe-only analysis.",
            "High breakeven rate after clean post-fix reconciliation usually points to protection/exit logic, not necessarily weak entries.",
            "Do not change SL-to-BE or extra-entry logic before reviewing this report.",
        ],
    }

    write_json(paths["report_json"], report)
    write_csv(paths["be_trades_csv"], be_trade_rows)
    write_csv(paths["setup_clusters_csv"], setup_clusters)
    write_csv(paths["strategy_csv"], strategy_rows)

    print("[PHASE 2AT BREAKEVEN EXIT MANAGEMENT AUDIT]")
    print("all_ok =", report["all_ok"])
    print("recommendation =", recommendation)

    print()
    print("[COUNTS]")
    for key, value in report["counts"].items():
        print(f"{key} = {value}")

    print()
    print("[DIAGNOSIS COUNTS]")
    for key, value in sorted(diagnosis_counts.items()):
        print(f"{key} = {value}")

    print()
    print("[PATTERN COUNTS]")
    for key, value in sorted(pattern_counts.items()):
        print(f"{key} = {value}")

    print()
    print("[BY STRATEGY]")
    for row in strategy_rows:
        print(
            f"{row['strategy']} | n={row['trade_count']} "
            f"win={row['win_count']} loss={row['loss_count']} "
            f"be={row['breakeven_count']} extra_be={row['extra_breakeven_count']} "
            f"main_be={row['main_breakeven_count']} "
            f"be_rate={row['breakeven_rate']} net={row['net_profit']} "
            f"rec={row['recommendation']}"
        )

    print()
    print("[SETUP CLUSTERS]")
    for row in setup_clusters[:30]:
        print(
            f"{row['setup_id_base']} | {row['strategy']} | {row['signal']} | "
            f"trades={row['trade_count']} main={row['main_count']} extra={row['extra_count']} "
            f"win={row['win_count']} loss={row['loss_count']} be={row['breakeven_count']} "
            f"net={row['net_profit']} pattern={row['pattern']}"
        )

    print()
    print("report =", paths["report_json"])
    print("be_trades_csv =", paths["be_trades_csv"])
    print("setup_clusters_csv =", paths["setup_clusters_csv"])
    print("strategy_csv =", paths["strategy_csv"])


if __name__ == "__main__":
    main()
