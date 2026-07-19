import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

DASHBOARD_JSON = INTEL_DIR / "phase3_dashboard_summary.json"
DASHBOARD_TXT = INTEL_DIR / "phase3_dashboard_summary.txt"


REPORTS = {
    "auto_statistics": "phase3_auto_statistics_report.json",
    "post_baseline": "phase3_post_baseline_report.json",
    "readiness_gate": "phase3_readiness_gate_report.json",
    "confirmation_patterns": "phase3_confirmation_patterns_report.json",
    "mtf_conflicts": "phase3_mtf_conflict_report.json",
    "low_rr_slippage_recovery": "phase3_low_rr_slippage_recovery_report.json",
    "poc_context": "phase3_poc_context_report.json",
    "liquidity_poc_context": "phase3_liquidity_poc_context_report.json",
    "session_poc_confirmation": "phase3_session_poc_confirmation_report.json",
    "confirmation_coverage_audit": "phase3_confirmation_coverage_audit_report.json",
    "decision_candidates": "phase3_decision_candidates_report.json",
}


def load_report(filename):
    path = INTEL_DIR / filename

    if not path.exists():
        return {
            "available": False,
            "path": str(path),
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["available"] = True
        return data
    except Exception as exc:
        return {
            "available": False,
            "path": str(path),
            "error": repr(exc),
        }


def get_nested(data, *keys, default=None):
    current = data

    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)

    return current if current is not None else default


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    loaded = {
        name: load_report(filename)
        for name, filename in REPORTS.items()
    }

    readiness = loaded.get("readiness_gate", {})
    auto_stats = loaded.get("auto_statistics", {})
    post_baseline = loaded.get("post_baseline", {})
    mtf = loaded.get("mtf_conflicts", {})
    low_rr = loaded.get("low_rr_slippage_recovery", {})
    poc = loaded.get("poc_context", {})
    liquidity_poc = loaded.get("liquidity_poc_context", {})
    session_conf = loaded.get("session_poc_confirmation", {})
    conf_patterns = loaded.get("confirmation_patterns", {})
    coverage = loaded.get("confirmation_coverage_audit", {})
    decision_candidates = loaded.get("decision_candidates", {})

    dashboard = {
        "phase": "PHASE_3J_DASHBOARD_SUMMARY",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "main_status": {
            "phase3_live_blocking": get_nested(readiness, "readiness", "phase3_live_blocking", default="UNKNOWN"),
            "mtf_conflict_auto_execution": get_nested(readiness, "readiness", "mtf_conflict_auto_execution", default="UNKNOWN"),
            "low_rr_slippage_recovery": get_nested(readiness, "readiness", "low_rr_slippage_recovery", default="UNKNOWN"),
            "comex_order_flow": get_nested(readiness, "readiness", "comex_order_flow", default="UNKNOWN"),
        },
        "counts": {
            "trades_total": get_nested(auto_stats, "counts", "trades_json_records", default=None),
            "setup_outcomes_total": get_nested(auto_stats, "counts", "setup_outcomes_records", default=None),
            "confirmation_observations_total": get_nested(auto_stats, "counts", "confirmation_observations_records", default=None),
            "new_trades_post_baseline": get_nested(post_baseline, "post_baseline_counts", "new_trades", default=None),
            "new_setup_outcomes_post_baseline": get_nested(post_baseline, "post_baseline_counts", "new_setup_outcomes", default=None),
            "new_confirmations_post_baseline": get_nested(post_baseline, "post_baseline_counts", "new_confirmation_observations", default=None),
        },
        "recommendations": {
            "auto_statistics": auto_stats.get("recommendation"),
            "readiness_gate": readiness.get("recommendation"),
            "confirmation_patterns": conf_patterns.get("recommendation"),
            "mtf_conflicts": mtf.get("recommendation"),
            "low_rr_slippage_recovery": low_rr.get("recommendation"),
            "poc_context": poc.get("recommendation"),
            "liquidity_poc_context": liquidity_poc.get("recommendation"),
            "session_poc_confirmation": session_conf.get("recommendation"),
            "confirmation_coverage_audit": coverage.get("recommendation"),
            "decision_candidates": decision_candidates.get("recommendation"),
        },
        "poc_profile": poc.get("profile"),
        "mtf_summary": mtf.get("summary"),
        "low_rr_summary": low_rr.get("summary"),
        "liquidity_poc_summary": liquidity_poc.get("summary"),
        "session_poc_confirmation_summary": session_conf.get("summary"),
        "confirmation_coverage": {
            "suspicious_missing_count": coverage.get("suspicious_missing_count"),
            "coverage": coverage.get("coverage"),
            "recommendation": coverage.get("recommendation"),
        },
        "decision_candidates": {
            "fresh_counts": decision_candidates.get("fresh_counts"),
            "status_counts": decision_candidates.get("status_counts"),
            "recommendation": decision_candidates.get("recommendation"),
        },
        "loaded_reports": {
            name: report.get("available", False)
            for name, report in loaded.items()
        },
    }

    DASHBOARD_JSON.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 3 DASHBOARD SUMMARY]",
        f"updated_at = {dashboard['updated_at']}",
        f"mode = {dashboard['mode']}",
        f"decision = {dashboard['decision']}",
        "",
        "[MAIN STATUS]",
        f"phase3_live_blocking = {dashboard['main_status']['phase3_live_blocking']}",
        f"mtf_conflict_auto_execution = {dashboard['main_status']['mtf_conflict_auto_execution']}",
        f"low_rr_slippage_recovery = {dashboard['main_status']['low_rr_slippage_recovery']}",
        f"comex_order_flow = {dashboard['main_status']['comex_order_flow']}",
        "",
        "[COUNTS]",
    ]

    for key, value in dashboard["counts"].items():
        lines.append(f"{key} = {value}")

    lines += [
        "",
        "[CONFIRMATION COVERAGE]",
        f"suspicious_missing_count = {dashboard['confirmation_coverage']['suspicious_missing_count']}",
        f"recommendation = {dashboard['confirmation_coverage']['recommendation']}",
        "",
        "[DECISION CANDIDATES]",
        f"status_counts = {dashboard['decision_candidates']['status_counts']}",
        f"recommendation = {dashboard['decision_candidates']['recommendation']}",
        "",
        "[POC PROFILE]",
    ]

    if dashboard["poc_profile"]:
        profile = dashboard["poc_profile"]
        lines += [
            f"poc = {profile.get('poc')}",
            f"value_area_low = {profile.get('value_area_low')}",
            f"value_area_high = {profile.get('value_area_high')}",
            "warning = MT5 tick_volume proxy only, not COMEX order flow",
        ]
    else:
        lines.append("POC profile unavailable")

    lines += [
        "",
        "[RECOMMENDATIONS]",
    ]

    for key, value in dashboard["recommendations"].items():
        lines.append(f"{key} = {value}")

    lines += [
        "",
        "[REPORTS LOADED]",
    ]

    for key, value in dashboard["loaded_reports"].items():
        lines.append(f"{key} = {value}")

    DASHBOARD_TXT.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\njson = {DASHBOARD_JSON}")
    print(f"summary = {DASHBOARD_TXT}")


if __name__ == "__main__":
    main()