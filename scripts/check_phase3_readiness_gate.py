import json
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_DIR = ROOT / "data" / "accounts" / "Tickmill-Demo_25323531"
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

BASELINE_PATH = INTEL_DIR / "phase3_baseline.json"
REPORT_PATH = INTEL_DIR / "phase3_readiness_gate_report.json"
SUMMARY_PATH = INTEL_DIR / "phase3_readiness_gate_summary.txt"


MIN_NEW_TRADES = 30
MIN_NEW_SETUP_OUTCOMES = 50
MIN_NEW_CONFIRMATIONS = 50
MIN_MTF_TRACKED = 10


def load_json_records(path):
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for key in ("trades", "outcomes", "setup_outcomes", "setups", "records", "items"):
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


def safe_text(value):
    if value is None:
        return ""
    return str(value)


def count_events(records):
    counter = Counter()

    for r in records:
        if not isinstance(r, dict):
            continue

        event = safe_text(r.get("event") or r.get("result") or r.get("final_result") or r.get("status"))
        strategy = safe_text(r.get("strategy") or r.get("strategy_name"))
        source = safe_text(r.get("source") or r.get("setup_source_bucket") or r.get("bucket"))
        reason = safe_text(r.get("reason") or r.get("decision_reason") or r.get("execution_reason"))

        combined = " ".join([event, strategy, source, reason]).upper()

        if "MTF_CONFLICT" in combined:
            counter["mtf_conflict_related"] += 1

        if "MTF_CONFLICT_CANDIDATE_TRACKED" in combined:
            counter["mtf_conflict_tracked"] += 1

        if "LOW_RR_HIGH_ADVERSE_SLIPPAGE" in combined:
            counter["low_rr_high_adverse_slippage"] += 1

        if "WAIT_BETTER_ENTRY" in combined:
            counter["wait_better_entry"] += 1

        if "HIGH_ADVERSE_SLIPPAGE" in combined:
            counter["high_adverse_slippage"] += 1

        if "EXECUTION_SUCCESS" in combined or "TRADE_EXECUTED" in combined:
            counter["execution_success"] += 1

        if "EXECUTION_FAILED" in combined:
            counter["execution_failed"] += 1

    return dict(counter)


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    if not BASELINE_PATH.exists():
        raise SystemExit("[STOP] Missing phase3_baseline.json. Run create_phase3_baseline.py first.")

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    baseline_counts = baseline.get("counts", {})

    trades = load_json_records(ACCOUNT_DIR / "trades.json")
    outcomes = load_json_records(ACCOUNT_DIR / "setup_outcomes.json")
    confirmations = load_jsonl_records(ACCOUNT_DIR / "confirmation_observations.jsonl")

    base_trades = int(baseline_counts.get("trades_json_records") or len(trades))
    base_outcomes = int(baseline_counts.get("setup_outcomes_records") or len(outcomes))
    base_confirmations = int(baseline_counts.get("confirmation_observations_records") or len(confirmations))

    new_trades = trades[base_trades:]
    new_outcomes = outcomes[base_outcomes:]
    new_confirmations = confirmations[base_confirmations:]

    outcome_events = count_events(new_outcomes)
    confirmation_events = count_events(new_confirmations)

    sample_ready = (
        len(new_trades) >= MIN_NEW_TRADES
        and len(new_outcomes) >= MIN_NEW_SETUP_OUTCOMES
        and len(new_confirmations) >= MIN_NEW_CONFIRMATIONS
    )

    mtf_review_ready = outcome_events.get("mtf_conflict_tracked", 0) >= MIN_MTF_TRACKED

    report = {
        "phase": "PHASE_3C_READINESS_GATE",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline_created_at": baseline.get("created_at"),
        "baseline_counts": baseline_counts,
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
        "minimum_required_for_review": {
            "new_trades": MIN_NEW_TRADES,
            "new_setup_outcomes": MIN_NEW_SETUP_OUTCOMES,
            "new_confirmation_observations": MIN_NEW_CONFIRMATIONS,
            "mtf_conflict_tracked": MIN_MTF_TRACKED,
        },
        "post_baseline_outcome_events": outcome_events,
        "post_baseline_confirmation_events": confirmation_events,
        "readiness": {
            "phase3_live_blocking": "NOT_READY" if not sample_ready else "READY_FOR_MANUAL_REVIEW_ONLY",
            "mtf_conflict_auto_execution": "NOT_READY" if not mtf_review_ready else "READY_FOR_MANUAL_REVIEW_ONLY",
            "low_rr_slippage_recovery": "MONITORING",
            "comex_order_flow": "NOT_CONNECTED_OBSERVE_ONLY_REQUIRED_FIRST",
        },
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": (
            "COLLECT_MORE_POST_BASELINE_EVIDENCE"
            if not sample_ready
            else "REVIEW_PHASE3_RULES_MANUALLY_BEFORE_ANY_LIVE_BLOCKING"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 3C READINESS GATE]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        "",
        "[POST-BASELINE COUNTS]",
        f"new_trades = {len(new_trades)} / {MIN_NEW_TRADES}",
        f"new_setup_outcomes = {len(new_outcomes)} / {MIN_NEW_SETUP_OUTCOMES}",
        f"new_confirmation_observations = {len(new_confirmations)} / {MIN_NEW_CONFIRMATIONS}",
        "",
        "[READINESS]",
        f"phase3_live_blocking = {report['readiness']['phase3_live_blocking']}",
        f"mtf_conflict_auto_execution = {report['readiness']['mtf_conflict_auto_execution']}",
        f"low_rr_slippage_recovery = {report['readiness']['low_rr_slippage_recovery']}",
        f"comex_order_flow = {report['readiness']['comex_order_flow']}",
        "",
        "[EVENTS]",
    ]

    for key, value in outcome_events.items():
        lines.append(f"{key} = {value}")

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