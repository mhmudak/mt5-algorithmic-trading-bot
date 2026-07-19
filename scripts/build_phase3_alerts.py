import json
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

REPORT_PATH = INTEL_DIR / "phase3_alerts_report.json"
SUMMARY_PATH = INTEL_DIR / "phase3_alerts_summary.txt"


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


def add_alert(alerts, severity, code, message, action):
    alerts.append({
        "severity": severity,
        "code": code,
        "message": message,
        "action": action,
    })


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    auto_stats = load_json("phase3_auto_statistics_report.json")
    readiness = load_json("phase3_readiness_gate_report.json")
    coverage = load_json("phase3_confirmation_coverage_audit_report.json")
    mtf = load_json("phase3_mtf_conflict_report.json")
    low_rr = load_json("phase3_low_rr_slippage_recovery_report.json")
    candidates = load_json("phase3_decision_candidates_report.json")

    alerts = []

    all_commands_ok = auto_stats.get("all_commands_ok", True)

    new_trades = get(readiness, "post_baseline_counts", "new_trades", default=0) or 0
    new_outcomes = get(readiness, "post_baseline_counts", "new_setup_outcomes", default=0) or 0
    new_confirmations = get(readiness, "post_baseline_counts", "new_confirmation_observations", default=0) or 0

    mtf_records = get(mtf, "post_baseline_counts", "mtf_conflict_records", default=0) or 0
    low_rr_records = get(low_rr, "post_baseline_counts", "low_rr_slippage_records", default=0) or 0
    suspicious_missing = coverage.get("suspicious_missing_count", 0) or 0

    phase3_live_blocking = get(readiness, "readiness", "phase3_live_blocking", default="UNKNOWN")
    mtf_auto = get(readiness, "readiness", "mtf_conflict_auto_execution", default="UNKNOWN")
    comex_status = get(readiness, "readiness", "comex_order_flow", default="UNKNOWN")

    if not all_commands_ok:
        add_alert(
            alerts,
            "CRITICAL",
            "PHASE3_COMMAND_FAILURE",
            "One or more Phase 3 auto-statistics commands failed.",
            "Open phase3_auto_statistics_report.json and fix failed command before trusting reports.",
        )

    if suspicious_missing > 0:
        add_alert(
            alerts,
            "HIGH",
            "SUSPICIOUS_MISSING_CONFIRMATION",
            f"{suspicious_missing} actionable setup outcome(s) are missing confirmation observations.",
            "Patch the exact live_bot confirmation hook paths shown in phase3_confirmation_coverage_audit_report.json.",
        )

    if new_trades >= 30 and new_outcomes >= 50 and new_confirmations >= 50:
        add_alert(
            alerts,
            "MEDIUM",
            "PHASE3_SAMPLE_READY_FOR_MANUAL_REVIEW",
            f"Fresh sample reached review threshold: trades={new_trades}, outcomes={new_outcomes}, confirmations={new_confirmations}.",
            "Manually review Phase 3 decision candidates before enabling any live blocking.",
        )

    if mtf_records >= 10:
        add_alert(
            alerts,
            "MEDIUM",
            "MTF_CONFLICT_SAMPLE_READY",
            f"MTF conflict records reached {mtf_records}.",
            "Review MTF conflict report manually. Do not auto-execute until reviewed.",
        )

    if low_rr_records > 0:
        add_alert(
            alerts,
            "LOW",
            "LOW_RR_SLIPPAGE_RECOVERY_CASES_FOUND",
            f"Low-RR slippage recovery cases found: {low_rr_records}.",
            "Review whether WAIT_BETTER_ENTRY recovery improved or harmed results.",
        )

    if comex_status == "NOT_CONNECTED_OBSERVE_ONLY_REQUIRED_FIRST":
        add_alert(
            alerts,
            "INFO",
            "COMEX_ORDER_FLOW_NOT_CONNECTED",
            "Real COMEX/order-flow adapter is not connected.",
            "Keep MT5 POC as proxy context only. Do not use it as decision-grade order flow.",
        )

    if phase3_live_blocking != "NOT_READY":
        add_alert(
            alerts,
            "MEDIUM",
            "PHASE3_LIVE_BLOCKING_STATUS_CHANGED",
            f"phase3_live_blocking status changed to {phase3_live_blocking}.",
            "Manual review required before enabling any blocking.",
        )

    if mtf_auto != "NOT_READY":
        add_alert(
            alerts,
            "MEDIUM",
            "MTF_AUTO_EXECUTION_STATUS_CHANGED",
            f"mtf_conflict_auto_execution status changed to {mtf_auto}.",
            "Manual review required before allowing MTF conflict auto-execution.",
        )

    severity_rank = {
        "CRITICAL": 5,
        "HIGH": 4,
        "MEDIUM": 3,
        "LOW": 2,
        "INFO": 1,
    }

    severity_counts = Counter(a["severity"] for a in alerts)

    highest = "NONE"
    if alerts:
        highest = max(alerts, key=lambda a: severity_rank.get(a["severity"], 0))["severity"]

    action_alerts = [
        a for a in alerts
        if a["severity"] in ("CRITICAL", "HIGH", "MEDIUM")
    ]

    if action_alerts:
        status = "MANUAL_REVIEW_REQUIRED"
    elif alerts:
        status = "NO_ACTION_REQUIRED_INFO_ONLY"
    else:
        status = "NO_ACTION_REQUIRED"

    report = {
        "phase": "PHASE_3O_AUTOMATED_ALERTS",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "highest_severity": highest,
        "alert_count": len(alerts),
        "severity_counts": dict(severity_counts),
        "fresh_counts": {
            "new_trades": new_trades,
            "new_setup_outcomes": new_outcomes,
            "new_confirmation_observations": new_confirmations,
            "mtf_conflict_records": mtf_records,
            "low_rr_slippage_records": low_rr_records,
            "suspicious_missing_confirmations": suspicious_missing,
        },
        "alerts": alerts,
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": (
            "REVIEW_ALERTS_BEFORE_ANY_PHASE3_ACTION"
            if action_alerts
            else "CONTINUE_AUTOMATIC_OBSERVE_ONLY_MONITORING"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 3O AUTOMATED ALERTS]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"status = {report['status']}",
        f"highest_severity = {report['highest_severity']}",
        f"alert_count = {report['alert_count']}",
        "",
        "[FRESH COUNTS]",
    ]

    for key, value in report["fresh_counts"].items():
        lines.append(f"{key} = {value}")

    lines += [
        "",
        "[ALERTS]",
    ]

    if alerts:
        for alert in alerts:
            lines.append(f"{alert['severity']} | {alert['code']}")
            lines.append(f"  message: {alert['message']}")
            lines.append(f"  action: {alert['action']}")
    else:
        lines.append("No alerts.")

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