import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_DIR = ROOT / "data" / "accounts" / "Tickmill-Demo_25323531"
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

BASELINE_PATH = INTEL_DIR / "phase3_baseline.json"
REPORT_PATH = INTEL_DIR / "phase3_session_poc_confirmation_report.json"
SUMMARY_PATH = INTEL_DIR / "phase3_session_poc_confirmation_summary.txt"


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


def load_jsonl_records(path):
    if not path.exists():
        return []

    records = []

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            pass

    return records


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


def get_setup_id(record):
    return pick(record, "setup_id", "source_setup_id", "executed_setup_id", "parent_setup_id")


def as_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def blob(record):
    if not isinstance(record, dict):
        return ""

    parts = []

    for key, value in record.items():
        if isinstance(value, (str, int, float, bool)):
            parts.append(str(value))
        elif isinstance(value, dict):
            parts.extend(str(v) for v in value.values() if isinstance(v, (str, int, float, bool)))
        elif isinstance(value, list):
            parts.extend(str(v) for v in value if isinstance(v, (str, int, float, bool)))

    return " ".join(parts).upper()


def classify_outcome(record):
    b = blob(record)

    if "TP_TOUCH" in b or "TAKE_PROFIT" in b or "FINAL_TP" in b:
        return "WIN_OR_TP"

    if "SL_TOUCH" in b or "STOP_LOSS" in b or "FINAL_SL" in b:
        return "LOSS_OR_SL"

    if "BREAKEVEN" in b or "BREAK_EVEN" in b:
        return "BREAKEVEN"

    if "EXECUTION_SUCCESS" in b:
        return "EXECUTED_PENDING"

    if "TRACKED" in b:
        return "TRACKED_PENDING"

    return "UNKNOWN"


def confirmation_bucket(record):
    if not isinstance(record, dict):
        return "NO_CONFIRMATION"

    decision = (
        pick(record, "shadow_decision", "decision", "shadow_action", "action")
        or "UNKNOWN_DECISION"
    )

    confidence = as_float(pick(record, "confidence"))
    score_delta = as_float(pick(record, "score_delta"))

    if confidence is None:
        conf_bucket = "CONF_UNKNOWN"
    elif confidence >= 85:
        conf_bucket = "CONF_85_PLUS"
    elif confidence >= 75:
        conf_bucket = "CONF_75_84"
    elif confidence >= 65:
        conf_bucket = "CONF_65_74"
    else:
        conf_bucket = "CONF_BELOW_65"

    if score_delta is None:
        delta_bucket = "DELTA_UNKNOWN"
    elif score_delta >= 5:
        delta_bucket = "DELTA_5_PLUS"
    elif score_delta >= 3:
        delta_bucket = "DELTA_3_5"
    elif score_delta >= 0:
        delta_bucket = "DELTA_0_3"
    else:
        delta_bucket = "DELTA_NEGATIVE"

    return f"{decision}|{conf_bucket}|{delta_bucket}"


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

        typical = (high + low + close) / 3.0
        price_bin = round(round(typical / bin_size) * bin_size, 2)
        volume_by_price[price_bin] += volume

    if not volume_by_price:
        return None

    sorted_bins = sorted(volume_by_price.items())
    total_volume = sum(v for _, v in sorted_bins)
    poc_price, poc_volume = max(sorted_bins, key=lambda item: item[1])

    target = total_volume * 0.70
    selected = {poc_price}
    selected_volume = poc_volume

    price_to_volume = dict(sorted_bins)
    prices = [p for p, _ in sorted_bins]
    i = prices.index(poc_price)

    left = i - 1
    right = i + 1

    while selected_volume < target and (left >= 0 or right < len(prices)):
        lv = price_to_volume.get(prices[left], -1) if left >= 0 else -1
        rv = price_to_volume.get(prices[right], -1) if right < len(prices) else -1

        if rv >= lv:
            selected.add(prices[right])
            selected_volume += rv
            right += 1
        else:
            selected.add(prices[left])
            selected_volume += lv
            left -= 1

    return {
        "poc": poc_price,
        "value_area_low": min(selected),
        "value_area_high": max(selected),
        "bin_size": bin_size,
        "total_volume": round(total_volume, 2),
        "poc_volume": round(poc_volume, 2),
    }


def classify_poc_context(entry, profile):
    if entry is None or not profile:
        return "UNKNOWN"

    poc = profile["poc"]
    val = profile["value_area_low"]
    vah = profile["value_area_high"]
    bin_size = profile["bin_size"]

    if entry < val:
        return "BELOW_VALUE_AREA"

    if entry > vah:
        return "ABOVE_VALUE_AREA"

    if abs(entry - poc) <= bin_size:
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
    counts = baseline.get("counts", {})

    outcomes = load_json_records(ACCOUNT_DIR / "setup_outcomes.json")
    confirmations = load_jsonl_records(ACCOUNT_DIR / "confirmation_observations.jsonl")

    base_outcomes = int(counts.get("setup_outcomes_records") or len(outcomes))
    base_confirmations = int(counts.get("confirmation_observations_records") or len(confirmations))

    new_outcomes = outcomes[base_outcomes:]
    new_confirmations = confirmations[base_confirmations:]

    latest_confirmation_by_setup = {}

    for c in new_confirmations:
        sid = get_setup_id(c)
        if sid:
            latest_confirmation_by_setup[str(sid)] = c

    rates, mt5_error = fetch_mt5_rates(args.symbol, args.timeframe, args.bars)
    profile = build_volume_profile(rates, args.bin_size) if rates else None

    combo_counter = Counter()
    outcome_by_combo = defaultdict(Counter)
    records = []

    for record in new_outcomes:
        setup_id = get_setup_id(record)
        confirmation = latest_confirmation_by_setup.get(str(setup_id)) if setup_id else None

        entry = as_float(pick(record, "entry", "entry_price"))
        session = pick(record, "session", "session_name") or "UNKNOWN_SESSION"
        poc_context = classify_poc_context(entry, profile)
        conf_bucket = confirmation_bucket(confirmation)
        outcome_class = classify_outcome(record)

        combo = f"{session}|{poc_context}|{conf_bucket}"

        combo_counter[combo] += 1
        outcome_by_combo[combo][outcome_class] += 1

        records.append({
            "setup_id": setup_id,
            "event": pick(record, "event", "result", "status"),
            "strategy": pick(record, "strategy", "strategy_name"),
            "signal": pick(record, "signal"),
            "session": session,
            "entry": entry,
            "rr": pick(record, "rr", "risk_reward", "current_rr"),
            "poc_context": poc_context,
            "confirmation_bucket": conf_bucket,
            "combined_context": combo,
            "outcome_class": outcome_class,
        })

    report = {
        "phase": "PHASE_3I_SESSION_POC_CONFIRMATION",
        "mode": "OBSERVE_ONLY",
        "data_warning": "MT5 tick_volume POC is proxy only. Not COMEX order flow.",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "bars": args.bars,
        "bin_size": args.bin_size,
        "mt5_error": mt5_error,
        "profile": profile,
        "post_baseline_counts": {
            "new_setup_outcomes": len(new_outcomes),
            "new_confirmation_observations": len(new_confirmations),
            "classified_records": len(records),
        },
        "summary": {
            "by_combined_context": dict(combo_counter.most_common(50)),
            "outcome_by_combined_context": {k: dict(v) for k, v in outcome_by_combo.items()},
        },
        "records": records[-200:],
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": (
            "COLLECT_MORE_SESSION_POC_CONFIRMATION_EVIDENCE"
            if len(records) < 50
            else "READY_FOR_MANUAL_CONTEXT_REVIEW_ONLY"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 3I SESSION + POC + CONFIRMATION]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        "data_warning = MT5 tick_volume POC is proxy only, not COMEX order flow",
        "",
        "[COUNTS]",
        f"new_setup_outcomes = {len(new_outcomes)}",
        f"new_confirmation_observations = {len(new_confirmations)}",
        f"classified_records = {len(records)}",
        "",
        "[PROFILE]",
    ]

    if profile:
        lines += [
            f"poc = {profile['poc']}",
            f"value_area_low = {profile['value_area_low']}",
            f"value_area_high = {profile['value_area_high']}",
        ]
    else:
        lines.append(f"mt5_error = {mt5_error}")

    lines += [
        "",
        "[TOP COMBINED CONTEXTS]",
    ]

    for key, value in combo_counter.most_common(15):
        lines.append(f"{key}: {value} | outcomes={dict(outcome_by_combo[key])}")

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