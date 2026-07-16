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


CURRENT_EXTRA_BE_TRIGGER = 3.0
CURRENT_WORST_EXTRA_TRIGGER = 2.0


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
        "report_json": output_dir / "extra_be_evidence_quality_report.json",
        "evidence_csv": output_dir / "extra_be_evidence_quality_trades.csv",
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


def favorable_distance_from_max_profit(trade):
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

def close_distance_from_entry(trade):
    signal = str(trade.get("signal") or "").upper()
    entry = safe_float(trade.get("entry_price"))
    close = safe_float(trade.get("close_price"))

    if entry <= 0 or close <= 0:
        return None

    if signal == "BUY":
        return round(close - entry, 4)

    if signal == "SELL":
        return round(entry - close, 4)

    return round(abs(close - entry), 4)


def reached_level_count(trade):
    reached = trade.get("reached_levels") or {}

    if not isinstance(reached, dict):
        return 0

    return sum(1 for value in reached.values() if bool(value))


def find_evidence_keys(obj, prefix=""):
    hits = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            upper = key_text.upper()

            if any(token in upper for token in [
                "BREAKEVEN",
                "BREAK_EVEN",
                "PROTECT",
                "LOCK",
                "MAX_PROFIT",
                "REACHED",
                "TRAIL",
                "SL",
                "STOP",
            ]):
                hits.append(path)

            if isinstance(value, (dict, list)):
                hits.extend(find_evidence_keys(value, path))

    elif isinstance(obj, list):
        for i, value in enumerate(obj[:20]):
            path = f"{prefix}[{i}]"
            if isinstance(value, (dict, list)):
                hits.extend(find_evidence_keys(value, path))

    return hits


def classify_evidence(trade):
    fav = favorable_distance_from_max_profit(trade)
    close_dist = close_distance_from_entry(trade)
    reached_count = reached_level_count(trade)
    evidence_keys = find_evidence_keys(trade)

    has_max_profit = fav is not None
    current_be_reached_by_max = bool(fav is not None and fav >= CURRENT_EXTRA_BE_TRIGGER)
    worst_lock_reached_by_max = bool(fav is not None and fav >= CURRENT_WORST_EXTRA_TRIGGER)

    if not has_max_profit:
        return "MISSING_OR_INVALID_MAX_PROFIT_EVIDENCE"

    if current_be_reached_by_max:
        return "CURRENT_BE_CONFIRMED_BY_MAX_PROFIT"

    if worst_lock_reached_by_max:
        return "WORST_LOCK_CONFIRMED_BUT_EXTRA_BE_NOT_CONFIRMED"

    if reached_count > 0:
        return "REACHED_LEVEL_EXISTS_BUT_MAX_PROFIT_BE_NOT_CONFIRMED"

    if close_dist is not None and abs(close_dist) <= 0.30:
        return "CLOSED_NEAR_ENTRY_BUT_TRIGGER_EVIDENCE_MISSING"

    if evidence_keys:
        return "HAS_OTHER_PROTECTION_KEYS_BUT_BE_TRIGGER_NOT_CONFIRMED"

    return "BE_TRIGGER_EVIDENCE_INCOMPLETE"


def main():
    parser = argparse.ArgumentParser(
        description="Audit whether extra-BE trades contain enough evidence to simulate delayed BE thresholds."
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

    rows = []
    classification_counts = defaultdict(int)
    strategy_counts = defaultdict(int)

    for trade in extra_be_trades:
        classification = classify_evidence(trade)
        classification_counts[classification] += 1
        strategy_counts[str(trade.get("strategy") or "UNKNOWN")] += 1

        evidence_keys = find_evidence_keys(trade)

        rows.append({
            "position_id": trade.get("position_id"),
            "setup_id": trade.get("setup_id"),
            "strategy": trade.get("strategy"),
            "signal": trade.get("signal"),
            "trade_role": trade.get("trade_role"),
            "entry_price": safe_float(trade.get("entry_price")),
            "close_price": safe_float(trade.get("close_price")),
            "max_profit_price": safe_float(trade.get("max_profit_price")),
            "favorable_distance_from_max_profit": favorable_distance_from_max_profit(trade),
            "close_distance_from_entry": close_distance_from_entry(trade),
            "reached_level_count": reached_level_count(trade),
            "final_result": trade.get("final_result"),
            "close_reason": trade.get("close_reason"),
            "realized_profit": safe_float(trade.get("realized_profit")),
            "classification": classification,
            "evidence_key_count": len(evidence_keys),
            "evidence_keys_sample": ",".join(evidence_keys[:20]),
        })

    confirmed = classification_counts.get("CURRENT_BE_CONFIRMED_BY_MAX_PROFIT", 0)
    incomplete = len(extra_be_trades) - confirmed
    incomplete_rate = round(incomplete / len(extra_be_trades), 4) if extra_be_trades else 0.0

    if incomplete_rate >= 0.50:
        recommendation = "SIMULATION_EVIDENCE_INCOMPLETE_ADD_PROTECTION_EVENT_LOGGING"
    elif incomplete_rate > 0:
        recommendation = "SIMULATION_PARTIAL_EVIDENCE_USE_CONSERVATIVE_CHANGE_ONLY"
    else:
        recommendation = "SIMULATION_EVIDENCE_OK"

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2AX",
        "all_ok": True,
        "recommendation": recommendation,
        "counts": {
            "clean_closed_trade_count": len(clean_trades),
            "extra_breakeven_trade_count": len(extra_be_trades),
            "current_be_confirmed_by_max_profit_count": confirmed,
            "incomplete_evidence_count": incomplete,
            "incomplete_evidence_rate": incomplete_rate,
        },
        "classification_counts": dict(sorted(classification_counts.items())),
        "strategy_counts": dict(sorted(strategy_counts.items())),
        "generated_files": {
            "report_json": str(paths["report_json"]),
            "evidence_csv": str(paths["evidence_csv"]),
        },
        "notes": [
            "This is evidence-quality audit only.",
            "If many BE trades do not show max_profit reaching the current BE trigger, delayed-BE simulation is not reliable enough.",
            "Next step should be protection-event logging, not aggressive threshold changes.",
        ],
    }

    write_json(paths["report_json"], report)
    write_csv(paths["evidence_csv"], rows)

    print("[PHASE 2AX EXTRA BE EVIDENCE QUALITY]")
    print("all_ok =", report["all_ok"])
    print("recommendation =", recommendation)

    print()
    print("[COUNTS]")
    for key, value in report["counts"].items():
        print(f"{key} = {value}")

    print()
    print("[CLASSIFICATION COUNTS]")
    for key, value in sorted(classification_counts.items()):
        print(f"{key} = {value}")

    print()
    print("[BY STRATEGY]")
    for key, value in sorted(strategy_counts.items()):
        print(f"{key} = {value}")

    print()
    print("[TRADE EVIDENCE SAMPLE]")
    for row in rows[:30]:
        print(
            f"{row['position_id']} | {row['strategy']} | {row['signal']} | "
            f"fav={row['favorable_distance_from_max_profit']} "
            f"close_dist={row['close_distance_from_entry']} "
            f"reached={row['reached_level_count']} "
            f"class={row['classification']}"
        )

    print()
    print("report =", paths["report_json"])
    print("evidence_csv =", paths["evidence_csv"])


if __name__ == "__main__":
    main()
