import json
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_DIR = ROOT / "data" / "accounts" / "Tickmill-Demo_25323531"
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

BASELINE_PATH = INTEL_DIR / "phase3_baseline.json"
REPORT_PATH = INTEL_DIR / "phase3_low_rr_slippage_recovery_report.json"
SUMMARY_PATH = INTEL_DIR / "phase3_low_rr_slippage_recovery_summary.txt"


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


def blob(record):
    if not isinstance(record, dict):
        return ""

    parts = []

    for key, value in record.items():
        if isinstance(value, (str, int, float, bool)):
            parts.append(str(value))
        elif isinstance(value, dict):
            for sub_value in value.values():
                if isinstance(sub_value, (str, int, float, bool)):
                    parts.append(str(sub_value))

    return " ".join(parts).upper()


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


def classify(record):
    b = blob(record)

    if "LOW_RR_HIGH_ADVERSE_SLIPPAGE" in b:
        return "LOW_RR_HIGH_ADVERSE_SLIPPAGE"

    if "SPLIT_IMMEDIATE_LOW_RR_SLIPPAGE_WAIT_BETTER_ENTRY" in b:
        return "LOW_RR_MOVED_TO_WAIT_BETTER_ENTRY"

    if "WAIT_BETTER_ENTRY" in b and "LOW_RR" in b:
        return "LOW_RR_WAIT_BETTER_ENTRY"

    if "LOW_RR_RECOVERY" in b and "EXECUTION_SUCCESS" in b:
        return "LOW_RR_RECOVERY_EXECUTED"

    if "LOW_RR_RECOVERY" in b and "EXECUTION_FAILED" in b:
        return "LOW_RR_RECOVERY_FAILED"

    return None


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    if not BASELINE_PATH.exists():
        raise SystemExit("[STOP] Missing phase3_baseline.json")

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    counts = baseline.get("counts", {})

    outcomes = load_json_records(ACCOUNT_DIR / "setup_outcomes.json")
    base_outcomes = int(counts.get("setup_outcomes_records") or len(outcomes))
    new_outcomes = outcomes[base_outcomes:]

    low_rr_records = []

    for record in new_outcomes:
        category = classify(record)
        if not category:
            continue

        low_rr_records.append({
            "category": category,
            "setup_id": pick(record, "setup_id", "source_setup_id", "executed_setup_id", "parent_setup_id"),
            "event": pick(record, "event", "result", "status"),
            "strategy": pick(record, "strategy", "strategy_name"),
            "signal": pick(record, "signal"),
            "rr": pick(record, "rr", "risk_reward", "current_rr"),
            "required_rr": pick(record, "required_rr", "min_rr_required"),
            "reason": pick(record, "reason", "decision_reason", "execution_reason"),
            "adverse_slippage": pick(record, "adverse_slippage", "execution_block_adverse_slippage", "slippage"),
            "max_allowed": pick(record, "max_allowed", "execution_block_max_allowed"),
        })

    by_category = Counter(r["category"] for r in low_rr_records)
    by_strategy = Counter(str(r.get("strategy") or "UNKNOWN") for r in low_rr_records)
    by_signal = Counter(str(r.get("signal") or "UNKNOWN") for r in low_rr_records)

    report = {
        "phase": "PHASE_3F_LOW_RR_SLIPPAGE_RECOVERY",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline_created_at": baseline.get("created_at"),
        "post_baseline_counts": {
            "new_setup_outcomes": len(new_outcomes),
            "low_rr_slippage_records": len(low_rr_records),
        },
        "summary": {
            "by_category": dict(by_category),
            "by_strategy": dict(by_strategy.most_common(20)),
            "by_signal": dict(by_signal),
        },
        "records": low_rr_records[-100:],
        "decision": "NO_LIVE_BLOCKING_CHANGE",
        "recommendation": (
            "NO_LOW_RR_SLIPPAGE_RECOVERY_CASES_YET"
            if len(low_rr_records) == 0
            else "MONITOR_LOW_RR_RECOVERY_RESULTS"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 3F LOW-RR SLIPPAGE RECOVERY]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        "",
        "[COUNTS]",
        f"new_setup_outcomes = {len(new_outcomes)}",
        f"low_rr_slippage_records = {len(low_rr_records)}",
        "",
        "[CATEGORIES]",
    ]

    for key, value in by_category.items():
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