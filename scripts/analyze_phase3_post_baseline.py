import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ACCOUNT_DIR = ROOT / "data" / "accounts" / "Tickmill-Demo_25323531"
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

BASELINE_PATH = INTEL_DIR / "phase3_baseline.json"
REPORT_PATH = INTEL_DIR / "phase3_post_baseline_report.json"
SUMMARY_PATH = INTEL_DIR / "phase3_post_baseline_summary.txt"


def load_json_records(path):
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for key in ("trades", "outcomes", "setups", "records", "items"):
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

    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                records.append({"raw": line})
    except Exception:
        return []

    return records


def safe_get(record, *keys):
    if not isinstance(record, dict):
        return None

    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value

    return None


def summarize_records(records):
    strategies = Counter()
    signals = Counter()
    events = Counter()
    sessions = Counter()
    buckets = Counter()

    for r in records:
        if not isinstance(r, dict):
            continue

        strategies[str(safe_get(r, "strategy", "strategy_name") or "UNKNOWN")] += 1
        signals[str(safe_get(r, "signal", "direction") or "UNKNOWN")] += 1
        events[str(safe_get(r, "event", "final_result", "result", "status") or "UNKNOWN")] += 1
        sessions[str(safe_get(r, "session", "session_name") or "UNKNOWN")] += 1
        buckets[str(safe_get(r, "setup_source_bucket", "bucket", "source") or "UNKNOWN")] += 1

    return {
        "by_strategy": dict(strategies.most_common(20)),
        "by_signal": dict(signals.most_common(10)),
        "by_event_or_result": dict(events.most_common(30)),
        "by_session": dict(sessions.most_common(20)),
        "by_bucket_or_source": dict(buckets.most_common(20)),
    }


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    if not BASELINE_PATH.exists():
        raise SystemExit("[STOP] phase3_baseline.json not found. Run scripts/create_phase3_baseline.py first.")

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    counts = baseline.get("counts", {})

    trades = load_json_records(ACCOUNT_DIR / "trades.json")
    outcomes = load_json_records(ACCOUNT_DIR / "setup_outcomes.json")
    confirmations = load_jsonl_records(ACCOUNT_DIR / "confirmation_observations.jsonl")

    base_trades = int(counts.get("trades_json_records") or 0)
    base_outcomes = int(counts.get("setup_outcomes_records") or 0)
    base_confirmations = int(counts.get("confirmation_observations_records") or 0)

    new_trades = trades[base_trades:]
    new_outcomes = outcomes[base_outcomes:]
    new_confirmations = confirmations[base_confirmations:]

    report = {
        "phase": "PHASE_3_POST_BASELINE",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline_created_at": baseline.get("created_at"),
        "baseline_counts": counts,
        "current_counts": {
            "trades_json_records": len(trades),
            "setup_outcomes_records": len(outcomes),
            "confirmation_observations_records": len(confirmations),
        },
        "post_baseline_counts": {
            "new_trades": len(new_trades),
            "new_setup_outcomes": len(new_outcomes),
            "new_confirmation_observations": len(new_confirmations),
        },
        "new_trades_summary": summarize_records(new_trades),
        "new_setup_outcomes_summary": summarize_records(new_outcomes),
        "new_confirmation_observations_summary": summarize_records(new_confirmations),
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": (
            "COLLECT_MORE_POST_BASELINE_EVIDENCE"
            if len(new_trades) < 30 or len(new_outcomes) < 50
            else "ENOUGH_SAMPLE_FOR_REVIEW_NOT_AUTOMATIC_PHASE3"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 3 POST-BASELINE REPORT]",
        f"updated_at = {report['updated_at']}",
        f"baseline_created_at = {report['baseline_created_at']}",
        f"mode = {report['mode']}",
        "",
        "[COUNTS]",
        f"new_trades = {len(new_trades)}",
        f"new_setup_outcomes = {len(new_outcomes)}",
        f"new_confirmation_observations = {len(new_confirmations)}",
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
        "",
        "[TOP NEW SETUP OUTCOME EVENTS]",
    ]

    for key, value in report["new_setup_outcomes_summary"]["by_event_or_result"].items():
        lines.append(f"{key}: {value}")

    lines += [
        "",
        "[TOP NEW CONFIRMATION BUCKETS/SOURCES]",
    ]

    for key, value in report["new_confirmation_observations_summary"]["by_bucket_or_source"].items():
        lines.append(f"{key}: {value}")

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nreport = {REPORT_PATH}")
    print(f"summary = {SUMMARY_PATH}")


if __name__ == "__main__":
    main()