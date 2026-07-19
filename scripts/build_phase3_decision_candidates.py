import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

REPORT_PATH = INTEL_DIR / "phase3_decision_candidates_report.json"
SUMMARY_PATH = INTEL_DIR / "phase3_decision_candidates_summary.txt"


def load_json(name):
    path = INTEL_DIR / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get(data, *keys, default=None):
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def add_candidate(candidates, name, status, reason, next_action):
    candidates.append({
        "candidate": name,
        "status": status,
        "reason": reason,
        "next_action": next_action,
    })


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    readiness = load_json("phase3_readiness_gate_report.json")
    coverage = load_json("phase3_confirmation_coverage_audit_report.json")
    mtf = load_json("phase3_mtf_conflict_report.json")
    low_rr = load_json("phase3_low_rr_slippage_recovery_report.json")
    poc = load_json("phase3_poc_context_report.json")
    liquidity_poc = load_json("phase3_liquidity_poc_context_report.json")
    session_conf = load_json("phase3_session_poc_confirmation_report.json")
    conf_patterns = load_json("phase3_confirmation_patterns_report.json")
    dashboard = load_json("phase3_dashboard_summary.json")

    new_trades = get(readiness, "post_baseline_counts", "new_trades", default=0) or 0
    new_outcomes = get(readiness, "post_baseline_counts", "new_setup_outcomes", default=0) or 0
    new_confirmations = get(readiness, "post_baseline_counts", "new_confirmation_observations", default=0) or 0

    suspicious_missing = coverage.get("suspicious_missing_count", 0) or 0
    mtf_records = get(mtf, "post_baseline_counts", "mtf_conflict_records", default=0) or 0
    low_rr_records = get(low_rr, "post_baseline_counts", "low_rr_slippage_records", default=0) or 0

    candidates = []

    add_candidate(
        candidates,
        "GLOBAL_PHASE3_LIVE_BLOCKING",
        "NOT_READY",
        f"Fresh sample too small: trades={new_trades}, outcomes={new_outcomes}, confirmations={new_confirmations}.",
        "Collect at least 30 new trades, 50 new setup outcomes, and 50 new confirmations before manual review.",
    )

    add_candidate(
        candidates,
        "MTF_CONFLICT_AUTO_EXECUTION",
        "NOT_READY" if mtf_records < 10 else "READY_FOR_MANUAL_REVIEW_ONLY",
        f"Post-baseline MTF conflict records={mtf_records}. Minimum review threshold=10.",
        "Keep tracking MTF conflicts; do not auto-execute yet.",
    )

    add_candidate(
        candidates,
        "LOW_RR_SLIPPAGE_TO_BETTER_ENTRY",
        "MONITORING" if low_rr_records > 0 else "NO_CASES_YET",
        f"Low-RR slippage recovery cases={low_rr_records}.",
        "Keep the current protection active; review after several LOW_RR_HIGH_ADVERSE_SLIPPAGE cases.",
    )

    add_candidate(
        candidates,
        "CONFIRMATION_BASED_BLOCKING",
        "NOT_READY",
        f"Fresh confirmations={new_confirmations}; suspicious missing confirmations={suspicious_missing}.",
        "Do not allow confirmation engine to block live trades yet.",
    )

    add_candidate(
        candidates,
        "CONFIRMATION_HOOK_FIX",
        "NOT_NEEDED_NOW" if suspicious_missing == 0 else "FIX_REQUIRED",
        f"Suspicious missing confirmation count={suspicious_missing}.",
        "Patch live_bot hooks only if suspicious missing confirmation count becomes positive.",
    )

    add_candidate(
        candidates,
        "MT5_POC_CONTEXT_FILTER",
        "OBSERVE_ONLY_NOT_DECISION_GRADE",
        "POC is calculated from MT5 tick volume proxy, not real COMEX volume/order flow.",
        "Use only for context statistics. Never use alone for live blocking.",
    )

    add_candidate(
        candidates,
        "LIQUIDITY_POC_CONTEXT_RULES",
        "MONITOR_MORE",
        f"Liquidity+POC sample={get(liquidity_poc, 'post_baseline_counts', 'classified_records', default=0)}.",
        "Collect more post-baseline outcomes before proposing any filter.",
    )

    add_candidate(
        candidates,
        "SESSION_POC_CONFIRMATION_RULES",
        "MONITOR_MORE",
        f"Session+POC+confirmation sample={get(session_conf, 'post_baseline_counts', 'classified_records', default=0)}.",
        "Collect more data, especially setups with matched confirmation.",
    )

    add_candidate(
        candidates,
        "COMEX_ORDER_FLOW",
        "NOT_CONNECTED",
        "No real COMEX/futures order-flow data adapter connected.",
        "Build observe-only data adapter first. Never fake order flow from MT5 tick volume.",
    )

    status_counts = {}
    for c in candidates:
        status_counts[c["status"]] = status_counts.get(c["status"], 0) + 1

    report = {
        "phase": "PHASE_3L_DECISION_CANDIDATES",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "fresh_counts": {
            "new_trades": new_trades,
            "new_setup_outcomes": new_outcomes,
            "new_confirmation_observations": new_confirmations,
            "mtf_conflict_records": mtf_records,
            "low_rr_slippage_records": low_rr_records,
            "suspicious_missing_confirmations": suspicious_missing,
        },
        "status_counts": status_counts,
        "candidates": candidates,
        "recommendation": "KEEP_PHASE3_OBSERVE_ONLY_COLLECT_MORE_EVIDENCE",
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 3L DECISION CANDIDATES]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"decision = {report['decision']}",
        "",
        "[FRESH COUNTS]",
    ]

    for key, value in report["fresh_counts"].items():
        lines.append(f"{key} = {value}")

    lines += [
        "",
        "[CANDIDATES]",
    ]

    for c in candidates:
        lines.append(f"{c['candidate']} = {c['status']}")
        lines.append(f"  reason: {c['reason']}")
        lines.append(f"  next: {c['next_action']}")

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