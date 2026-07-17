import json
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_DIR = ROOT / "data" / "accounts" / "Tickmill-Demo_25323531"
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

BASELINE_PATH = INTEL_DIR / "phase3_baseline.json"
REPORT_PATH = INTEL_DIR / "phase3_confirmation_coverage_audit_report.json"
SUMMARY_PATH = INTEL_DIR / "phase3_confirmation_coverage_audit_summary.txt"


ACTIONABLE_KEYWORDS = [
    "EXECUTION_SUCCESS",
    "EXECUTED",
    "CANDIDATE_TRACKED",
    "MTF_CONFLICT",
    "REJECTED_CANDIDATE_TRACKED",
    "SPLIT_IMMEDIATE",
    "SPLIT_DELAYED",
    "WAIT_BETTER_ENTRY",
    "INTRABAR_PRICE_EVENT",
]

NON_DECISION_KEYWORDS = [
    "BREAKEVEN",
    "BREAK_EVEN",
    "POSITION_PROTECTED",
    "TRAILING",
    "TP_TOUCH",
    "SL_TOUCH",
    "FINAL_TP",
    "FINAL_SL",
    "TRADE_CLOSED",
    "CLOSE",
    "REGISTERED_TRADE",
]


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


def setup_ids(record):
    ids = []

    for key in ("setup_id", "source_setup_id", "executed_setup_id", "parent_setup_id"):
        value = pick(record, key)
        if value:
            ids.append(str(value))

    return list(dict.fromkeys(ids))


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


def classify_need(record):
    b = blob(record)

    if any(k in b for k in NON_DECISION_KEYWORDS):
        return "CONFIRMATION_NOT_REQUIRED"

    if any(k in b for k in ACTIONABLE_KEYWORDS):
        return "CONFIRMATION_REQUIRED"

    return "CONFIRMATION_OPTIONAL_OR_UNKNOWN"


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    if not BASELINE_PATH.exists():
        raise SystemExit("[STOP] Missing phase3_baseline.json")

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    counts = baseline.get("counts", {})

    outcomes = load_json_records(ACCOUNT_DIR / "setup_outcomes.json")
    confirmations = load_jsonl_records(ACCOUNT_DIR / "confirmation_observations.jsonl")

    base_outcomes = int(counts.get("setup_outcomes_records") or max(0, len(outcomes) - 50))
    base_confirmations = int(counts.get("confirmation_observations_records") or max(0, len(confirmations) - 50))

    new_outcomes = outcomes[base_outcomes:]
    new_confirmations = confirmations[base_confirmations:]

    confirmation_ids = set()
    for c in new_confirmations:
        for sid in setup_ids(c):
            confirmation_ids.add(sid)

    records = []
    counters = Counter()
    suspicious = []

    for outcome in new_outcomes:
        ids = setup_ids(outcome)
        matched = any(sid in confirmation_ids for sid in ids)

        need = classify_need(outcome)

        if matched:
            status = "MATCHED_CONFIRMATION"
        elif need == "CONFIRMATION_REQUIRED":
            status = "MISSING_CONFIRMATION_SUSPICIOUS"
        elif need == "CONFIRMATION_NOT_REQUIRED":
            status = "NO_CONFIRMATION_EXPECTED"
        else:
            status = "NO_CONFIRMATION_OPTIONAL_OR_UNKNOWN"

        item = {
            "status": status,
            "confirmation_need": need,
            "setup_ids": ids,
            "event": pick(outcome, "event", "result", "status"),
            "strategy": pick(outcome, "strategy", "strategy_name"),
            "signal": pick(outcome, "signal"),
            "session": pick(outcome, "session", "session_name"),
            "source": pick(outcome, "source", "setup_source_bucket", "bucket"),
            "reason": pick(outcome, "reason", "decision_reason", "execution_reason"),
        }

        records.append(item)
        counters[status] += 1

        if status == "MISSING_CONFIRMATION_SUSPICIOUS":
            suspicious.append(item)

    report = {
        "phase": "PHASE_3K_CONFIRMATION_COVERAGE_AUDIT",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "post_baseline_counts": {
            "new_setup_outcomes": len(new_outcomes),
            "new_confirmation_observations": len(new_confirmations),
        },
        "coverage": dict(counters),
        "suspicious_missing_count": len(suspicious),
        "suspicious_missing_records": suspicious[-100:],
        "records": records[-200:],
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": (
            "FIX_CONFIRMATION_HOOKS_FOR_SUSPICIOUS_MISSING_EVENTS"
            if suspicious
            else "CONFIRMATION_COVERAGE_ACCEPTABLE_FOR_CURRENT_SAMPLE"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 3K CONFIRMATION COVERAGE AUDIT]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        "",
        "[COUNTS]",
        f"new_setup_outcomes = {len(new_outcomes)}",
        f"new_confirmation_observations = {len(new_confirmations)}",
        "",
        "[COVERAGE]",
    ]

    for key, value in counters.items():
        lines.append(f"{key}: {value}")

    lines += [
        "",
        f"suspicious_missing_count = {len(suspicious)}",
        "",
        "[SUSPICIOUS MISSING SAMPLE]",
    ]

    for item in suspicious[-20:]:
        lines.append(
            f"{item.get('event')} | {item.get('strategy')} | {item.get('signal')} | "
            f"session={item.get('session')} | source={item.get('source')} | ids={item.get('setup_ids')}"
        )

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