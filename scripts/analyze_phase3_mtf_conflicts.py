import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_DIR = ROOT / "data" / "accounts" / "Tickmill-Demo_25323531"
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

BASELINE_PATH = INTEL_DIR / "phase3_baseline.json"
REPORT_PATH = INTEL_DIR / "phase3_mtf_conflict_report.json"
SUMMARY_PATH = INTEL_DIR / "phase3_mtf_conflict_summary.txt"


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


def get_setup_id(record):
    if not isinstance(record, dict):
        return None

    for key in ("setup_id", "source_setup_id", "executed_setup_id", "parent_setup_id"):
        value = record.get(key)
        if value:
            return str(value)

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

    if "EXECUTION_FAILED" in b:
        return "EXECUTION_FAILED"

    return "UNKNOWN"


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


def main():
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

    confirmations_by_setup = defaultdict(list)

    for c in new_confirmations:
        sid = get_setup_id(c)
        if sid:
            confirmations_by_setup[sid].append(c)

    mtf_records = []

    for outcome in new_outcomes:
        b = blob(outcome)

        if "MTF_CONFLICT" not in b:
            continue

        setup_id = get_setup_id(outcome)
        matched_confirmations = confirmations_by_setup.get(setup_id, [])

        confirmation_decisions = []
        confirmation_scores = []

        for c in matched_confirmations:
            confirmation_decisions.append(
                pick(c, "shadow_decision", "decision", "shadow_action", "action") or "UNKNOWN"
            )
            confirmation_scores.append(
                pick(c, "confidence", "score_delta", "shadow_score")
            )

        mtf_records.append({
            "setup_id": setup_id,
            "event": pick(outcome, "event", "result", "status"),
            "strategy": pick(outcome, "strategy", "strategy_name"),
            "signal": pick(outcome, "signal"),
            "entry_model": pick(outcome, "entry_model"),
            "score": pick(outcome, "score"),
            "rr": pick(outcome, "rr", "risk_reward", "current_rr"),
            "required_rr": pick(outcome, "required_rr", "min_rr_required"),
            "mtf_bias": pick(outcome, "mtf_bias"),
            "execution_allowed": pick(outcome, "execution_allowed"),
            "execution_reason": pick(outcome, "execution_reason", "reason"),
            "outcome_class": classify_outcome(outcome),
            "confirmation_count": len(matched_confirmations),
            "confirmation_decisions": confirmation_decisions,
            "confirmation_scores": confirmation_scores,
        })

    by_outcome = Counter(r["outcome_class"] for r in mtf_records)
    by_strategy = Counter(str(r.get("strategy") or "UNKNOWN") for r in mtf_records)
    by_signal = Counter(str(r.get("signal") or "UNKNOWN") for r in mtf_records)
    by_reason = Counter(str(r.get("execution_reason") or "UNKNOWN") for r in mtf_records)

    report = {
        "phase": "PHASE_3E_MTF_CONFLICT_REVIEW",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline_created_at": baseline.get("created_at"),
        "post_baseline_counts": {
            "new_setup_outcomes": len(new_outcomes),
            "new_confirmation_observations": len(new_confirmations),
            "mtf_conflict_records": len(mtf_records),
        },
        "summary": {
            "by_outcome": dict(by_outcome),
            "by_strategy": dict(by_strategy.most_common(20)),
            "by_signal": dict(by_signal),
            "by_execution_reason": dict(by_reason.most_common(20)),
        },
        "records": mtf_records[-100:],
        "decision": "NO_MTF_AUTO_EXECUTION",
        "recommendation": (
            "COLLECT_MORE_MTF_CONFLICT_EVIDENCE"
            if len(mtf_records) < 10
            else "READY_FOR_MANUAL_MTF_CONFLICT_REVIEW_ONLY"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 3E MTF CONFLICT REVIEW]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        "",
        "[COUNTS]",
        f"new_setup_outcomes = {len(new_outcomes)}",
        f"new_confirmation_observations = {len(new_confirmations)}",
        f"mtf_conflict_records = {len(mtf_records)}",
        "",
        "[OUTCOMES]",
    ]

    for key, value in by_outcome.items():
        lines.append(f"{key}: {value}")

    lines += [
        "",
        "[TOP EXECUTION REASONS]",
    ]

    for key, value in by_reason.most_common(10):
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