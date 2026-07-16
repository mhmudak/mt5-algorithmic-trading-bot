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


SCENARIOS = [
    {
        "name": "CURRENT",
        "extra_be_trigger": 3.0,
        "extra_lock_trigger": 4.0,
        "extra_lock_profit": 2.0,
        "extra_take_profit": 5.5,
        "worst_extra_trigger": 2.0,
        "worst_extra_lock_profit": 1.0,
    },
    {
        "name": "CONSERVATIVE_1",
        "extra_be_trigger": 3.5,
        "extra_lock_trigger": 4.5,
        "extra_lock_profit": 2.0,
        "extra_take_profit": 6.0,
        "worst_extra_trigger": 2.5,
        "worst_extra_lock_profit": 1.0,
    },
    {
        "name": "CONSERVATIVE_2",
        "extra_be_trigger": 4.0,
        "extra_lock_trigger": 5.0,
        "extra_lock_profit": 2.0,
        "extra_take_profit": 6.5,
        "worst_extra_trigger": 3.0,
        "worst_extra_lock_profit": 1.0,
    },
    {
        "name": "DELAYED_A",
        "extra_be_trigger": 4.5,
        "extra_lock_trigger": 5.5,
        "extra_lock_profit": 2.0,
        "extra_take_profit": 7.0,
        "worst_extra_trigger": 3.5,
        "worst_extra_lock_profit": 1.0,
    },
    {
        "name": "DELAYED_B",
        "extra_be_trigger": 5.0,
        "extra_lock_trigger": 6.0,
        "extra_lock_profit": 2.0,
        "extra_take_profit": 8.0,
        "worst_extra_trigger": 4.0,
        "worst_extra_lock_profit": 1.0,
    },
    {
        "name": "LOCK_FIRST_NO_EARLY_BE",
        "extra_be_trigger": None,
        "extra_lock_trigger": 4.5,
        "extra_lock_profit": 1.0,
        "extra_take_profit": 7.0,
        "worst_extra_trigger": 3.5,
        "worst_extra_lock_profit": 1.0,
    },
]


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
        "report_json": output_dir / "extra_breakeven_threshold_simulation_report.json",
        "scenario_csv": output_dir / "extra_breakeven_threshold_simulation_by_scenario.csv",
        "trade_csv": output_dir / "extra_breakeven_threshold_simulation_trades.csv",
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


def is_extra_trade(trade):
    return str(trade.get("trade_role") or "").upper() == "EXTRA"


def is_breakeven_trade(trade):
    final_result = str(trade.get("final_result") or "").upper()
    close_reason = str(trade.get("close_reason") or "").upper()
    realized_profit = safe_float(trade.get("realized_profit"))

    return (
        final_result == "BREAKEVEN"
        or close_reason == "BREAKEVEN"
        or realized_profit == 0.0
    )


def favorable_distance(trade):
    """
    Return favorable excursion as a PRICE DISTANCE, not an absolute price.

    Historical tracker data is inconsistent:
    - sometimes max_profit_price appears to be an absolute XAU price near 4000
    - sometimes it appears to be already a favorable distance like 2.5 / 6.0
    - sometimes it is missing/invalid

    This function normalizes safely and rejects absurd values.
    """

    signal = str(trade.get("signal") or "").upper()
    entry = safe_float(trade.get("entry_price"))
    raw_max = trade.get("max_profit_price")

    if raw_max in [None, ""]:
        return None

    max_value = safe_float(raw_max)

    if max_value <= 0:
        return None

    # If max_value is small, it is likely already a favorable distance.
    # XAUUSD absolute prices are normally in the thousands.
    if 0 < max_value <= 100:
        return round(max_value, 4)

    # Otherwise treat it as an absolute price.
    if entry <= 0:
        return None

    if signal == "BUY":
        distance = max_value - entry
    elif signal == "SELL":
        distance = entry - max_value
    else:
        distance = abs(max_value - entry)

    # Reject impossible / corrupted values.
    if distance < 0:
        return None

    if distance > 100:
        return None

    return round(distance, 4)

def classify_trade_under_scenario(trade, scenario):
    fav = favorable_distance(trade)

    if fav is None:
        return "INCOMPLETE_EVIDENCE_UNKNOWN"

    be_trigger = scenario.get("extra_be_trigger")
    lock_trigger = scenario.get("extra_lock_trigger")
    tp_trigger = scenario.get("extra_take_profit")
    worst_trigger = scenario.get("worst_extra_trigger")

    if tp_trigger is not None and fav >= tp_trigger:
        return "WOULD_REACH_EXTRA_TAKE_PROFIT"

    if lock_trigger is not None and fav >= lock_trigger:
        return "WOULD_LOCK_PROFIT"

    if be_trigger is not None and fav >= be_trigger:
        return "WOULD_REACH_BREAKEVEN_PROTECTION"

    if worst_trigger is not None and fav >= worst_trigger:
        return "WOULD_REACH_WORST_EXTRA_LOCK_ONLY"

    return "WOULD_REMAIN_UNPROTECTED_IF_DELAYED"

def scenario_row(scenario, trades):
    outcomes = defaultdict(int)

    for trade in trades:
        outcomes[classify_trade_under_scenario(trade, scenario)] += 1

    total = len(trades)

    protected = (
        outcomes["WOULD_REACH_EXTRA_TAKE_PROFIT"]
        + outcomes["WOULD_LOCK_PROFIT"]
        + outcomes["WOULD_REACH_BREAKEVEN_PROTECTION"]
        + outcomes["WOULD_REACH_WORST_EXTRA_LOCK_ONLY"]
    )

    unprotected = outcomes["WOULD_REMAIN_UNPROTECTED_IF_DELAYED"]
    incomplete = outcomes["INCOMPLETE_EVIDENCE_UNKNOWN"]

    known_total = total - incomplete

    return {
        "scenario": scenario["name"],
        "extra_be_trigger": scenario.get("extra_be_trigger"),
        "extra_lock_trigger": scenario.get("extra_lock_trigger"),
        "extra_lock_profit": scenario.get("extra_lock_profit"),
        "extra_take_profit": scenario.get("extra_take_profit"),
        "worst_extra_trigger": scenario.get("worst_extra_trigger"),
        "worst_extra_lock_profit": scenario.get("worst_extra_lock_profit"),
        "extra_be_trade_count": total,
        "known_evidence_trade_count": known_total,
        "incomplete_evidence_trade_count": incomplete,
        "would_reach_take_profit_count": outcomes["WOULD_REACH_EXTRA_TAKE_PROFIT"],
        "would_lock_profit_count": outcomes["WOULD_LOCK_PROFIT"],
        "would_reach_be_count": outcomes["WOULD_REACH_BREAKEVEN_PROTECTION"],
        "would_reach_worst_extra_lock_only_count": outcomes["WOULD_REACH_WORST_EXTRA_LOCK_ONLY"],
        "would_remain_unprotected_count": unprotected,
        "protected_or_partially_protected_count": protected,
        "protected_or_partially_protected_rate": round(protected / known_total, 4) if known_total else None,
        "unprotected_if_delayed_rate": round(unprotected / known_total, 4) if known_total else None,
        "incomplete_evidence_rate": round(incomplete / total, 4) if total else None,
        "recommendation": classify_scenario(scenario["name"], total, known_total, protected, unprotected, incomplete, outcomes),
    }

def classify_scenario(name, total, known_total, protected, unprotected, incomplete, outcomes):
    if total == 0:
        return "NO_EXTRA_BE_TRADES"

    if known_total <= 0:
        return "INSUFFICIENT_EVIDENCE"

    incomplete_rate = incomplete / total
    unprotected_rate = unprotected / known_total

    if name == "CURRENT":
        return "BASELINE_CURRENT_BEHAVIOR"

    if incomplete_rate > 0.35:
        return "EVIDENCE_TOO_INCOMPLETE_FOR_LIVE_CHANGE"

    if unprotected_rate > 0.50:
        return "TOO_RISKY_MANY_EXTRAS_WOULD_BE_UNPROTECTED"

    if outcomes["WOULD_LOCK_PROFIT"] + outcomes["WOULD_REACH_EXTRA_TAKE_PROFIT"] >= 1:
        return "PROMISING_FOR_CONSERVATIVE_TEST"

    if unprotected_rate <= 0.30:
        return "POSSIBLE_DELAYED_BE_CANDIDATE"

    return "OBSERVE_MORE_BEFORE_CHANGE"

def main():
    parser = argparse.ArgumentParser(
        description="Simulate delayed extra breakeven protection thresholds."
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

    extra_be_trades = [
        trade
        for trade in clean_trades
        if is_extra_trade(trade) and is_breakeven_trade(trade)
    ]

    scenario_rows = [
        scenario_row(scenario, extra_be_trades)
        for scenario in SCENARIOS
    ]

    trade_rows = []

    for trade in extra_be_trades:
        base = {
            "position_id": trade.get("position_id"),
            "setup_id": trade.get("setup_id"),
            "strategy": trade.get("strategy"),
            "signal": trade.get("signal"),
            "trade_role": trade.get("trade_role"),
            "entry_price": safe_float(trade.get("entry_price")),
            "close_price": safe_float(trade.get("close_price")),
            "max_profit_price": safe_float(trade.get("max_profit_price")),
            "favorable_distance": favorable_distance(trade),
            "final_result": trade.get("final_result"),
            "close_reason": trade.get("close_reason"),
            "realized_profit": safe_float(trade.get("realized_profit")),
        }

        for scenario in SCENARIOS:
            row = dict(base)
            row["scenario"] = scenario["name"]
            row["scenario_classification"] = classify_trade_under_scenario(trade, scenario)
            row["scenario_extra_be_trigger"] = scenario.get("extra_be_trigger")
            row["scenario_extra_lock_trigger"] = scenario.get("extra_lock_trigger")
            row["scenario_extra_take_profit"] = scenario.get("extra_take_profit")
            trade_rows.append(row)

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2AW",
        "all_ok": True,
        "recommendation": "EXTRA_BE_THRESHOLD_SIMULATION_READY_REVIEW_BEFORE_LIVE_CHANGE",
        "counts": {
            "clean_closed_trade_count": len(clean_trades),
            "extra_breakeven_trade_count": len(extra_be_trades),
            "scenario_count": len(SCENARIOS),
        },
        "scenarios": scenario_rows,
        "generated_files": {
            "report_json": str(paths["report_json"]),
            "scenario_csv": str(paths["scenario_csv"]),
            "trade_csv": str(paths["trade_csv"]),
        },
        "notes": [
            "This is not a true tick-level replay.",
            "It uses recorded max_profit_price to estimate whether delayed BE would have been reached before current BE close.",
            "If a trade is classified as WOULD_REMAIN_UNPROTECTED_IF_DELAYED, it does not prove it would have lost; it means more risk would have remained open.",
            "Do not change live thresholds from this alone; use it to select a conservative candidate.",
        ],
    }

    write_json(paths["report_json"], report)
    write_csv(paths["scenario_csv"], scenario_rows)
    write_csv(paths["trade_csv"], trade_rows)

    print("[PHASE 2AW EXTRA BE THRESHOLD SIMULATION]")
    print("all_ok =", report["all_ok"])
    print("recommendation =", report["recommendation"])

    print()
    print("[COUNTS]")
    for key, value in report["counts"].items():
        print(f"{key} = {value}")

    print()
    print("[SCENARIOS]")
    for row in scenario_rows:
        print(
            f"{row['scenario']} | extra_be={row['extra_be_trigger']} "
            f"lock={row['extra_lock_trigger']} tp={row['extra_take_profit']} "
            f"n={row['extra_be_trade_count']} known={row['known_evidence_trade_count']} "
            f"incomplete={row['incomplete_evidence_trade_count']} "
            f"protected={row['protected_or_partially_protected_count']} "
            f"unprotected={row['would_remain_unprotected_count']} "
            f"unprotected_rate={row['unprotected_if_delayed_rate']} "
            f"incomplete_rate={row['incomplete_evidence_rate']} "
            f"rec={row['recommendation']}"
        )

    print()
    print("report =", paths["report_json"])
    print("scenario_csv =", paths["scenario_csv"])
    print("trade_csv =", paths["trade_csv"])


if __name__ == "__main__":
    main()
