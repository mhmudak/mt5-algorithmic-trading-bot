import json
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

REPORT_PATH = INTEL_DIR / "phase4_opportunity_alerts_report.json"
SUMMARY_PATH = INTEL_DIR / "phase4_opportunity_alerts_summary.txt"


def load_json(filename):
    path = INTEL_DIR / filename
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


def add_opportunity(items, grade, code, message, action, evidence=None):
    items.append({
        "alert_type": "OPPORTUNITY",
        "grade": grade,
        "code": code,
        "message": message,
        "action": action,
        "evidence": evidence or {},
    })


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    readiness = load_json("phase3_readiness_gate_report.json")
    decision_candidates = load_json("phase3_decision_candidates_report.json")
    mtf = load_json("phase3_mtf_conflict_report.json")
    session_conf = load_json("phase3_session_poc_confirmation_report.json")
    liquidity_poc = load_json("phase3_liquidity_poc_context_report.json")
    orderflow_gate = load_json("phase4_orderflow_availability_gate_report.json")
    mt5_proxy_changes = load_json("phase4_mt5_proxy_context_changes_report.json")

    opportunities = []

    new_trades = get(readiness, "post_baseline_counts", "new_trades", default=0) or 0
    new_outcomes = get(readiness, "post_baseline_counts", "new_setup_outcomes", default=0) or 0
    new_confirmations = get(readiness, "post_baseline_counts", "new_confirmation_observations", default=0) or 0

    phase3_live_blocking = get(readiness, "readiness", "phase3_live_blocking", default="UNKNOWN")
    mtf_auto = get(readiness, "readiness", "mtf_conflict_auto_execution", default="UNKNOWN")

    orderflow_gate_status = get(orderflow_gate, "gate", "gate_status", default="UNKNOWN")
    orderflow_can_influence = bool(get(orderflow_gate, "gate", "can_influence_decision", default=False))
    proxy_change_status = get(mt5_proxy_changes, "status", default="UNKNOWN")
    proxy_change_count = get(mt5_proxy_changes, "change_count", default=0) or 0

    mtf_records = get(mtf, "post_baseline_counts", "mtf_conflict_records", default=0) or 0
    liquidity_sample = get(liquidity_poc, "post_baseline_counts", "classified_records", default=0) or 0
    session_sample = get(session_conf, "post_baseline_counts", "classified_records", default=0) or 0

    # Current safe default:
    # No opportunity alert is allowed to mean "auto-trade now".
    # At this stage, opportunities are only future/manual-review candidates.

    if new_trades >= 30 and new_outcomes >= 50 and new_confirmations >= 50:
        add_opportunity(
            opportunities,
            "MANUAL_REVIEW_CANDIDATE",
            "PHASE3_SAMPLE_READY_FOR_OPPORTUNITY_REVIEW",
            "Fresh Phase 3 sample reached the minimum review threshold.",
            "Review strategy/context reports manually. Do not enable auto-trading from this alone.",
            {
                "new_trades": new_trades,
                "new_setup_outcomes": new_outcomes,
                "new_confirmation_observations": new_confirmations,
            },
        )

    if mtf_records >= 10 and mtf_auto != "NOT_READY":
        add_opportunity(
            opportunities,
            "MANUAL_REVIEW_CANDIDATE",
            "MTF_CONFLICT_SAMPLE_READY_FOR_OPPORTUNITY_REVIEW",
            "MTF conflict sample may be ready for manual opportunity review.",
            "Review MTF conflict outcomes before considering any shadow execution rule.",
            {
                "mtf_conflict_records": mtf_records,
                "mtf_conflict_auto_execution_status": mtf_auto,
            },
        )

    if liquidity_sample >= 50:
        add_opportunity(
            opportunities,
            "SHADOW_RESEARCH_CANDIDATE",
            "LIQUIDITY_POC_CONTEXT_SAMPLE_READY",
            "Liquidity + POC context has enough sample for research review.",
            "Check which combined contexts show better/worse outcomes; keep observe-only.",
            {
                "liquidity_poc_sample": liquidity_sample,
            },
        )

    if session_sample >= 50:
        add_opportunity(
            opportunities,
            "SHADOW_RESEARCH_CANDIDATE",
            "SESSION_POC_CONFIRMATION_SAMPLE_READY",
            "Session + POC + confirmation context has enough sample for research review.",
            "Check if specific session/context/confirmation combinations deserve future shadow rules.",
            {
                "session_poc_confirmation_sample": session_sample,
            },
        )

    if proxy_change_status == "PROXY_CONTEXT_CHANGED" and proxy_change_count > 0:
        add_opportunity(
            opportunities,
            "SHADOW_RESEARCH_CANDIDATE",
            "MT5_PROXY_CONTEXT_CHANGED_RESEARCH_REVIEW",
            "MT5 proxy context changed meaningfully.",
            "Review POC/value-area/tick-volume changes manually. This is not a live trade signal.",
            {
                "proxy_change_status": proxy_change_status,
                "proxy_change_count": proxy_change_count,
            },
        )

    if orderflow_can_influence:
        add_opportunity(
            opportunities,
            "PROVIDER_REVIEW_REQUIRED",
            "ORDERFLOW_PROVIDER_AVAILABLE_REVIEW_REQUIRED",
            "Order-flow gate says data can influence decisions.",
            "Manual validation required before any strategy consumes order-flow data.",
            {
                "orderflow_gate_status": orderflow_gate_status,
                "can_influence_decision": orderflow_can_influence,
            },
        )

    grade_counts = Counter(item["grade"] for item in opportunities)

    if opportunities:
        status = "OPPORTUNITY_MANUAL_REVIEW_AVAILABLE"
    else:
        status = "NO_OPPORTUNITY_ALERTS"

    report = {
        "phase": "PHASE_4G_OPPORTUNITY_ALERTS",
        "mode": "OBSERVE_ONLY",
        "alert_family": "OPPORTUNITY_MONITORING",
        "grade_meaning": "Opportunity grades are separate from risk severities. They never mean auto-trade.",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "opportunity_count": len(opportunities),
        "grade_counts": dict(grade_counts),
        "fresh_counts": {
            "new_trades": new_trades,
            "new_setup_outcomes": new_outcomes,
            "new_confirmation_observations": new_confirmations,
            "mtf_conflict_records": mtf_records,
            "liquidity_poc_sample": liquidity_sample,
            "session_poc_confirmation_sample": session_sample,
            "orderflow_gate_status": orderflow_gate_status,
            "orderflow_can_influence_decision": orderflow_can_influence,
        },
        "opportunities": opportunities,
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": (
            "REVIEW_OPPORTUNITY_CANDIDATES_MANUALLY"
            if opportunities
            else "NO_OPPORTUNITY_ACTION_CONTINUE_OBSERVE_ONLY"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 4G OPPORTUNITY ALERTS]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"alert_family = {report['alert_family']}",
        f"status = {report['status']}",
        f"opportunity_count = {report['opportunity_count']}",
        "",
        "[FRESH COUNTS]",
    ]

    for key, value in report["fresh_counts"].items():
        lines.append(f"{key} = {value}")

    lines += [
        "",
        "[OPPORTUNITIES]",
    ]

    if opportunities:
        for item in opportunities:
            lines.append(f"{item['grade']} | {item['code']}")
            lines.append(f"  message: {item['message']}")
            lines.append(f"  action: {item['action']}")
    else:
        lines.append("No opportunity alerts.")

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