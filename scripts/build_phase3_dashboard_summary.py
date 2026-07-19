import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

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
    "alerts": "phase3_alerts_report.json",
    "orderflow_status": "phase4_orderflow_status_report.json",
    "orderflow_gate": "phase4_orderflow_availability_gate_report.json",
    "mt5_proxy_context": "phase4_mt5_proxy_context_report.json",
    "mt5_proxy_context_changes": "phase4_mt5_proxy_context_changes_report.json",
}

JSON_PATH = INTEL_DIR / "phase3_dashboard_summary.json"
SUMMARY_PATH = INTEL_DIR / "phase3_dashboard_summary.txt"


def load_json(filename):
    path = INTEL_DIR / filename
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}



def first_not_none(*values):
    for value in values:
        if value is not None:
            return value
    return None


def read_summary_value(filename, key):
    path = INTEL_DIR / filename
    if not path.exists():
        return None

    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key} = "):
                return line.split(" = ", 1)[1].strip()
    except Exception:
        return None

    return None


def as_int_or_value(value):
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return value


def get_nested(data, *keys, default=None):
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    loaded = {name: load_json(filename) for name, filename in REPORTS.items()}

    auto_stats = loaded.get("auto_statistics", {})
    post_baseline = loaded.get("post_baseline", {})
    readiness = loaded.get("readiness_gate", {})
    confirmation = loaded.get("confirmation_patterns", {})
    mtf = loaded.get("mtf_conflicts", {})
    low_rr = loaded.get("low_rr_slippage_recovery", {})
    poc = loaded.get("poc_context", {})
    liquidity_poc = loaded.get("liquidity_poc_context", {})
    session_poc = loaded.get("session_poc_confirmation", {})
    coverage = loaded.get("confirmation_coverage_audit", {})
    candidates = loaded.get("decision_candidates", {})
    alerts = loaded.get("alerts", {})
    orderflow_status = loaded.get("orderflow_status", {})
    orderflow_gate = loaded.get("orderflow_gate", {})
    mt5_proxy_context = loaded.get("mt5_proxy_context", {})
    mt5_proxy_changes = loaded.get("mt5_proxy_context_changes", {})

    dashboard = {
        "phase": "PHASE_3_4_DASHBOARD_SUMMARY",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "main_status": {
            "phase3_live_blocking": get_nested(readiness, "readiness", "phase3_live_blocking"),
            "mtf_conflict_auto_execution": get_nested(readiness, "readiness", "mtf_conflict_auto_execution"),
            "low_rr_slippage_recovery": get_nested(readiness, "readiness", "low_rr_slippage_recovery"),
            "comex_order_flow": get_nested(readiness, "readiness", "comex_order_flow"),
        },
        "counts": {
            "trades_total": as_int_or_value(first_not_none(
                auto_stats.get("trades"),
                get_nested(auto_stats, "counts", "trades"),
                get_nested(auto_stats, "data_counts", "trades"),
                read_summary_value("phase3_auto_statistics_summary.txt", "trades"),
            )),
            "setup_outcomes_total": as_int_or_value(first_not_none(
                auto_stats.get("setup_outcomes"),
                get_nested(auto_stats, "counts", "setup_outcomes"),
                get_nested(auto_stats, "data_counts", "setup_outcomes"),
                read_summary_value("phase3_auto_statistics_summary.txt", "setup_outcomes"),
            )),
            "confirmation_observations_total": as_int_or_value(first_not_none(
                auto_stats.get("confirmation_observations"),
                get_nested(auto_stats, "counts", "confirmation_observations"),
                get_nested(auto_stats, "data_counts", "confirmation_observations"),
                read_summary_value("phase3_auto_statistics_summary.txt", "confirmation_observations"),
            )),
            "new_trades_post_baseline": get_nested(readiness, "post_baseline_counts", "new_trades"),
            "new_setup_outcomes_post_baseline": get_nested(readiness, "post_baseline_counts", "new_setup_outcomes"),
            "new_confirmations_post_baseline": get_nested(readiness, "post_baseline_counts", "new_confirmation_observations"),
        },
        "confirmation_coverage": {
            "suspicious_missing_count": coverage.get("suspicious_missing_count"),
            "coverage": coverage.get("coverage"),
            "recommendation": coverage.get("recommendation"),
        },
        "decision_candidates": {
            "fresh_counts": candidates.get("fresh_counts"),
            "status_counts": candidates.get("status_counts"),
            "recommendation": candidates.get("recommendation"),
        },
        "alerts": {
            "status": alerts.get("status"),
            "highest_severity": alerts.get("highest_severity"),
            "alert_count": alerts.get("alert_count"),
            "recommendation": alerts.get("recommendation"),
        },
        "orderflow_status": {
            "provider": get_nested(orderflow_status, "orderflow_snapshot", "provider"),
            "available": get_nested(orderflow_status, "orderflow_snapshot", "available"),
            "status": get_nested(orderflow_status, "orderflow_snapshot", "status"),
            "data_quality": get_nested(orderflow_status, "orderflow_snapshot", "data_quality"),
            "decision_impact": get_nested(orderflow_status, "orderflow_snapshot", "decision_impact"),
            "recommendation": orderflow_status.get("recommendation"),
        },
        "orderflow_gate": {
            "gate_status": get_nested(orderflow_gate, "gate", "gate_status"),
            "can_influence_decision": get_nested(orderflow_gate, "gate", "can_influence_decision"),
            "decision_impact": get_nested(orderflow_gate, "gate", "decision_impact"),
            "missing_required_metrics": get_nested(orderflow_gate, "gate", "missing_required_metrics"),
            "reason": get_nested(orderflow_gate, "gate", "reason"),
            "recommendation": orderflow_gate.get("recommendation"),
        },
        "mt5_proxy_context": {
            "available": get_nested(mt5_proxy_context, "context", "available"),
            "status": get_nested(mt5_proxy_context, "context", "status"),
            "is_real_order_flow": get_nested(mt5_proxy_context, "context", "is_real_order_flow"),
            "data_quality": get_nested(mt5_proxy_context, "context", "data_quality"),
            "decision_impact": get_nested(mt5_proxy_context, "context", "decision_impact"),
            "price_vs_value_area": get_nested(mt5_proxy_context, "context", "price_vs_value_area"),
            "proxy_poc": get_nested(mt5_proxy_context, "context", "profile", "poc"),
            "proxy_value_area_low": get_nested(mt5_proxy_context, "context", "profile", "value_area_low"),
            "proxy_value_area_high": get_nested(mt5_proxy_context, "context", "profile", "value_area_high"),
            "volume_state": get_nested(mt5_proxy_context, "context", "volume_context", "volume_state"),
            "tick_volume_zscore": get_nested(mt5_proxy_context, "context", "volume_context", "tick_volume_zscore"),
            "latest_close": get_nested(mt5_proxy_context, "context", "candle_context", "latest_close"),
            "candle_direction": get_nested(mt5_proxy_context, "context", "candle_context", "candle_direction"),
            "recommendation": mt5_proxy_context.get("recommendation"),
        },
        "mt5_proxy_context_changes": {
            "status": mt5_proxy_changes.get("status"),
            "history_count": mt5_proxy_changes.get("history_count"),
            "change_count": mt5_proxy_changes.get("change_count"),
            "current_context": mt5_proxy_changes.get("current_context"),
            "changes": mt5_proxy_changes.get("changes"),
            "event_action": mt5_proxy_changes.get("event_action"),
            "significant_change_event_count": mt5_proxy_changes.get("significant_change_event_count"),
            "latest_significant_change_event": mt5_proxy_changes.get("latest_significant_change_event"),
            "recommendation": mt5_proxy_changes.get("recommendation"),
        },
        "poc_profile": {
            "poc": first_not_none(
                get_nested(poc, "profile", "poc"),
                get_nested(poc, "profile", "proxy_poc"),
                get_nested(poc, "poc"),
                get_nested(mt5_proxy_context, "context", "profile", "poc"),
            ),
            "value_area_low": first_not_none(
                get_nested(poc, "profile", "value_area_low"),
                get_nested(poc, "profile", "proxy_value_area_low"),
                get_nested(poc, "value_area_low"),
                get_nested(mt5_proxy_context, "context", "profile", "value_area_low"),
            ),
            "value_area_high": first_not_none(
                get_nested(poc, "profile", "value_area_high"),
                get_nested(poc, "profile", "proxy_value_area_high"),
                get_nested(poc, "value_area_high"),
                get_nested(mt5_proxy_context, "context", "profile", "value_area_high"),
            ),
        },
        "poc_warning": first_not_none(
            poc.get("warning"),
            get_nested(mt5_proxy_context, "context", "warning"),
            "MT5 tick_volume proxy only, not COMEX order flow",
        ),
        "recommendations": {
            "auto_statistics": auto_stats.get("recommendation"),
            "readiness_gate": readiness.get("recommendation"),
            "confirmation_patterns": confirmation.get("recommendation"),
            "mtf_conflicts": mtf.get("recommendation"),
            "low_rr_slippage_recovery": low_rr.get("recommendation"),
            "poc_context": poc.get("recommendation"),
            "liquidity_poc_context": liquidity_poc.get("recommendation"),
            "session_poc_confirmation": session_poc.get("recommendation"),
            "confirmation_coverage_audit": coverage.get("recommendation"),
            "decision_candidates": candidates.get("recommendation"),
            "alerts": alerts.get("recommendation"),
            "orderflow_status": orderflow_status.get("recommendation"),
            "orderflow_gate": orderflow_gate.get("recommendation"),
            "mt5_proxy_context": mt5_proxy_context.get("recommendation"),
            "mt5_proxy_context_changes": mt5_proxy_changes.get("recommendation"),
        },
        "loaded_reports": {name: bool(data) for name, data in loaded.items()},
    }

    JSON_PATH.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False), encoding="utf-8")

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
        f"trades_total = {dashboard['counts']['trades_total']}",
        f"setup_outcomes_total = {dashboard['counts']['setup_outcomes_total']}",
        f"confirmation_observations_total = {dashboard['counts']['confirmation_observations_total']}",
        f"new_trades_post_baseline = {dashboard['counts']['new_trades_post_baseline']}",
        f"new_setup_outcomes_post_baseline = {dashboard['counts']['new_setup_outcomes_post_baseline']}",
        f"new_confirmations_post_baseline = {dashboard['counts']['new_confirmations_post_baseline']}",
        "",
        "[CONFIRMATION COVERAGE]",
        f"suspicious_missing_count = {dashboard['confirmation_coverage']['suspicious_missing_count']}",
        f"coverage = {dashboard['confirmation_coverage']['coverage']}",
        f"recommendation = {dashboard['confirmation_coverage']['recommendation']}",
        "",
        "[DECISION CANDIDATES]",
        f"fresh_counts = {dashboard['decision_candidates']['fresh_counts']}",
        f"status_counts = {dashboard['decision_candidates']['status_counts']}",
        f"recommendation = {dashboard['decision_candidates']['recommendation']}",
        "",
        "[ALERTS]",
        f"status = {dashboard['alerts']['status']}",
        f"highest_severity = {dashboard['alerts']['highest_severity']}",
        f"alert_count = {dashboard['alerts']['alert_count']}",
        f"recommendation = {dashboard['alerts']['recommendation']}",
        "",
        "[ORDER FLOW STATUS]",
        f"provider = {dashboard['orderflow_status']['provider']}",
        f"available = {dashboard['orderflow_status']['available']}",
        f"status = {dashboard['orderflow_status']['status']}",
        f"data_quality = {dashboard['orderflow_status']['data_quality']}",
        f"decision_impact = {dashboard['orderflow_status']['decision_impact']}",
        f"recommendation = {dashboard['orderflow_status']['recommendation']}",
        "",
        "[ORDER FLOW GATE]",
        f"gate_status = {dashboard['orderflow_gate']['gate_status']}",
        f"can_influence_decision = {dashboard['orderflow_gate']['can_influence_decision']}",
        f"decision_impact = {dashboard['orderflow_gate']['decision_impact']}",
        f"missing_required_metrics = {dashboard['orderflow_gate']['missing_required_metrics']}",
        f"reason = {dashboard['orderflow_gate']['reason']}",
        f"recommendation = {dashboard['orderflow_gate']['recommendation']}",
        "",
        "[MT5 PROXY CONTEXT]",
        f"available = {dashboard['mt5_proxy_context']['available']}",
        f"status = {dashboard['mt5_proxy_context']['status']}",
        f"is_real_order_flow = {dashboard['mt5_proxy_context']['is_real_order_flow']}",
        f"data_quality = {dashboard['mt5_proxy_context']['data_quality']}",
        f"decision_impact = {dashboard['mt5_proxy_context']['decision_impact']}",
        f"price_vs_value_area = {dashboard['mt5_proxy_context']['price_vs_value_area']}",
        f"proxy_poc = {dashboard['mt5_proxy_context']['proxy_poc']}",
        f"proxy_value_area_low = {dashboard['mt5_proxy_context']['proxy_value_area_low']}",
        f"proxy_value_area_high = {dashboard['mt5_proxy_context']['proxy_value_area_high']}",
        f"volume_state = {dashboard['mt5_proxy_context']['volume_state']}",
        f"tick_volume_zscore = {dashboard['mt5_proxy_context']['tick_volume_zscore']}",
        f"latest_close = {dashboard['mt5_proxy_context']['latest_close']}",
        f"candle_direction = {dashboard['mt5_proxy_context']['candle_direction']}",
        f"recommendation = {dashboard['mt5_proxy_context']['recommendation']}",
        "",
        "[MT5 PROXY CHANGE DETECTOR]",
        f"status = {dashboard['mt5_proxy_context_changes']['status']}",
        f"history_count = {dashboard['mt5_proxy_context_changes']['history_count']}",
        f"change_count = {dashboard['mt5_proxy_context_changes']['change_count']}",
        f"recommendation = {dashboard['mt5_proxy_context_changes']['recommendation']}",
        "",
        "[POC PROFILE]",
        f"poc = {dashboard['mt5_proxy_context']['proxy_poc']}",
        f"value_area_low = {dashboard['mt5_proxy_context']['proxy_value_area_low']}",
        f"value_area_high = {dashboard['mt5_proxy_context']['proxy_value_area_high']}",
        "source = MT5_PROXY_CONTEXT",
        f"decision_impact = {dashboard['mt5_proxy_context']['decision_impact']}",
        f"warning = {dashboard['poc_warning']}",
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


    proxy_change_details = get_nested(dashboard, "mt5_proxy_context_changes", "changes", default=[]) or []

    if proxy_change_details:
        detail_lines = [
            "[MT5 PROXY CHANGE DETAILS]",
        ]

        for item in proxy_change_details[:5]:
            if not isinstance(item, dict):
                continue

            code = item.get("code")
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}

            previous = evidence.get("previous")
            current = evidence.get("current")
            delta = evidence.get("delta")

            if previous is not None or current is not None:
                detail = f"{code}: {previous} -> {current}"

                if delta is not None:
                    detail += f" | delta = {delta}"

                detail_lines.append(detail)
            else:
                detail_lines.append(f"{code}: {item.get('message')}")

        detail_lines.append("")

        try:
            poc_index = lines.index("[POC PROFILE]")
            lines[poc_index:poc_index] = detail_lines
        except ValueError:
            lines.extend([""] + detail_lines)



    latest_proxy_event = get_nested(
        dashboard,
        "mt5_proxy_context_changes",
        "latest_significant_change_event",
        default=None,
    )

    if isinstance(latest_proxy_event, dict) and latest_proxy_event:
        event_lines = [
            "[MT5 PROXY LATEST SIGNIFICANT CHANGE]",
            f"event_recorded_at = {latest_proxy_event.get('event_recorded_at') or latest_proxy_event.get('recorded_at')}",
            f"change_count = {latest_proxy_event.get('change_count')}",
            f"current_poc = {latest_proxy_event.get('current_poc')}",
            f"current_value_area_low = {latest_proxy_event.get('current_value_area_low')}",
            f"current_value_area_high = {latest_proxy_event.get('current_value_area_high')}",
            f"current_latest_close = {latest_proxy_event.get('current_latest_close')}",
        ]

        for item in latest_proxy_event.get("changes", [])[:5]:
            if not isinstance(item, dict):
                continue

            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            previous = evidence.get("previous")
            current = evidence.get("current")
            delta = evidence.get("delta")

            detail = f"{item.get('code')}: {previous} -> {current}"

            if delta is not None:
                detail += f" | delta = {delta}"

            event_lines.append(detail)

        event_lines.append("")

        try:
            poc_index = lines.index("[POC PROFILE]")
            lines[poc_index:poc_index] = event_lines
        except ValueError:
            lines.extend([""] + event_lines)


    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\njson = {JSON_PATH}")
    print(f"summary = {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
