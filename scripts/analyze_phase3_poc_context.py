import argparse
import json
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_DIR = ROOT / "data" / "accounts" / "Tickmill-Demo_25323531"
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

BASELINE_PATH = INTEL_DIR / "phase3_baseline.json"
REPORT_PATH = INTEL_DIR / "phase3_poc_context_report.json"
SUMMARY_PATH = INTEL_DIR / "phase3_poc_context_summary.txt"


def load_json_records(path):
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for key in ("outcomes", "setup_outcomes", "setups", "records", "items", "trades"):
                if isinstance(data.get(key), list):
                    return data[key]

            return list(data.values())
    except Exception:
        return []

    return []


def pick(record, *keys):
    if not isinstance(record, dict):
        return None

    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value

    extra = record.get("extra")
    if isinstance(extra, dict):
        for key in keys:
            value = extra.get(key)
            if value not in (None, ""):
                return value

    return None


def as_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def classify_outcome(record):
    blob = " ".join(str(v) for v in record.values() if isinstance(v, (str, int, float, bool))).upper()

    extra = record.get("extra") if isinstance(record, dict) else None
    if isinstance(extra, dict):
        blob += " " + " ".join(str(v) for v in extra.values() if isinstance(v, (str, int, float, bool))).upper()

    if "TP_TOUCH" in blob or "TAKE_PROFIT" in blob or "FINAL_TP" in blob:
        return "WIN_OR_TP"

    if "SL_TOUCH" in blob or "STOP_LOSS" in blob or "FINAL_SL" in blob:
        return "LOSS_OR_SL"

    if "BREAKEVEN" in blob or "BREAK_EVEN" in blob:
        return "BREAKEVEN"

    if "EXECUTION_SUCCESS" in blob:
        return "EXECUTED_PENDING"

    if "TRACKED" in blob:
        return "TRACKED_PENDING"

    return "UNKNOWN"


def fetch_mt5_rates(symbol, timeframe_name, bars):
    try:
        import MetaTrader5 as mt5
    except Exception as exc:
        return None, f"MetaTrader5 import failed: {exc}"

    timeframe_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
    }

    timeframe = timeframe_map.get(str(timeframe_name).upper(), mt5.TIMEFRAME_M15)

    if not mt5.initialize():
        return None, f"mt5.initialize failed: {mt5.last_error()}"

    try:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
        if rates is None:
            return None, f"copy_rates_from_pos failed: {mt5.last_error()}"

        return list(rates), None
    finally:
        mt5.shutdown()


def build_volume_profile(rates, bin_size):
    volume_by_price = defaultdict(float)

    for row in rates:
        try:
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            volume = float(row["tick_volume"])
        except Exception:
            continue

        typical_price = (high + low + close) / 3.0
        price_bin = round(round(typical_price / bin_size) * bin_size, 2)
        volume_by_price[price_bin] += volume

    if not volume_by_price:
        return None

    sorted_bins = sorted(volume_by_price.items())
    total_volume = sum(v for _, v in sorted_bins)

    poc_price, poc_volume = max(sorted_bins, key=lambda item: item[1])

    target_value_area_volume = total_volume * 0.70
    selected = {poc_price}
    selected_volume = poc_volume

    price_to_volume = dict(sorted_bins)
    prices = [p for p, _ in sorted_bins]
    poc_index = prices.index(poc_price)

    left = poc_index - 1
    right = poc_index + 1

    while selected_volume < target_value_area_volume and (left >= 0 or right < len(prices)):
        left_volume = price_to_volume.get(prices[left], -1) if left >= 0 else -1
        right_volume = price_to_volume.get(prices[right], -1) if right < len(prices) else -1

        if right_volume >= left_volume:
            selected.add(prices[right])
            selected_volume += right_volume
            right += 1
        else:
            selected.add(prices[left])
            selected_volume += left_volume
            left -= 1

    val = min(selected)
    vah = max(selected)

    return {
        "poc": poc_price,
        "poc_volume": round(poc_volume, 2),
        "value_area_low": val,
        "value_area_high": vah,
        "total_volume": round(total_volume, 2),
        "bin_size": bin_size,
        "bins_count": len(sorted_bins),
        "top_volume_bins": [
            {"price": p, "volume": round(v, 2)}
            for p, v in sorted(sorted_bins, key=lambda item: item[1], reverse=True)[:20]
        ],
    }


def classify_entry_vs_poc(entry, profile):
    if entry is None or not profile:
        return "UNKNOWN"

    poc = profile["poc"]
    val = profile["value_area_low"]
    vah = profile["value_area_high"]

    if entry > vah:
        return "ABOVE_VALUE_AREA"

    if entry < val:
        return "BELOW_VALUE_AREA"

    if abs(entry - poc) <= profile["bin_size"]:
        return "NEAR_POC"

    return "INSIDE_VALUE_AREA"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--bars", type=int, default=500)
    parser.add_argument("--bin-size", type=float, default=0.50)
    args = parser.parse_args()

    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    if not BASELINE_PATH.exists():
        raise SystemExit("[STOP] Missing phase3_baseline.json")

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    baseline_counts = baseline.get("counts", {})

    outcomes = load_json_records(ACCOUNT_DIR / "setup_outcomes.json")
    base_outcomes = int(baseline_counts.get("setup_outcomes_records") or len(outcomes))
    new_outcomes = outcomes[base_outcomes:]

    rates, mt5_error = fetch_mt5_rates(args.symbol, args.timeframe, args.bars)

    profile = None
    if rates:
        profile = build_volume_profile(rates, args.bin_size)

    setup_context_records = []
    context_counter = Counter()
    outcome_by_context = defaultdict(Counter)

    for record in new_outcomes:
        entry = as_float(pick(record, "entry", "entry_price"))
        context = classify_entry_vs_poc(entry, profile)
        outcome_class = classify_outcome(record)

        context_counter[context] += 1
        outcome_by_context[context][outcome_class] += 1

        setup_context_records.append({
            "setup_id": pick(record, "setup_id", "source_setup_id", "executed_setup_id"),
            "event": pick(record, "event", "result", "status"),
            "strategy": pick(record, "strategy", "strategy_name"),
            "signal": pick(record, "signal"),
            "entry": entry,
            "rr": pick(record, "rr", "risk_reward", "current_rr"),
            "outcome_class": outcome_class,
            "poc_context": context,
            "distance_from_poc": round(entry - profile["poc"], 2) if entry is not None and profile else None,
        })

    report = {
        "phase": "PHASE_3G_POC_CONTEXT",
        "mode": "OBSERVE_ONLY",
        "data_warning": "MT5 tick_volume POC is a proxy only. Not COMEX order flow.",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "bars": args.bars,
        "bin_size": args.bin_size,
        "mt5_error": mt5_error,
        "profile": profile,
        "post_baseline_counts": {
            "new_setup_outcomes": len(new_outcomes),
            "setup_context_records": len(setup_context_records),
        },
        "summary": {
            "by_poc_context": dict(context_counter),
            "outcomes_by_poc_context": {k: dict(v) for k, v in outcome_by_context.items()},
        },
        "records": setup_context_records[-150:],
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": (
            "MT5_POC_PROXY_AVAILABLE_OBSERVE_ONLY"
            if profile
            else "POC_PROXY_NOT_AVAILABLE_CHECK_MT5_CONNECTION"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 3G POC / VOLUME PROFILE CONTEXT]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        "data_warning = MT5 tick_volume POC is proxy only, not COMEX order flow",
        "",
        "[PROFILE]",
    ]

    if profile:
        lines += [
            f"symbol = {args.symbol}",
            f"timeframe = {args.timeframe}",
            f"bars = {args.bars}",
            f"poc = {profile['poc']}",
            f"value_area_low = {profile['value_area_low']}",
            f"value_area_high = {profile['value_area_high']}",
            f"bin_size = {profile['bin_size']}",
        ]
    else:
        lines.append(f"mt5_error = {mt5_error}")

    lines += [
        "",
        "[POST-BASELINE COUNTS]",
        f"new_setup_outcomes = {len(new_outcomes)}",
        "",
        "[POC CONTEXT COUNTS]",
    ]

    for key, value in context_counter.items():
        lines.append(f"{key}: {value}")

    lines += [
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nreport = {REPORT_PATH}")
    print(f"summary = {SUMMARY_PATH}")


if __name__ == "__main__":
    main()