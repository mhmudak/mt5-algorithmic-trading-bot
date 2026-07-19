import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

RISK_REPORT_PATH = INTEL_DIR / "phase3_alerts_report.json"
OPPORTUNITY_REPORT_PATH = INTEL_DIR / "phase4_opportunity_alerts_report.json"
STATE_PATH = INTEL_DIR / "phase4_unified_telegram_state.json"
SUMMARY_PATH = INTEL_DIR / "phase4_unified_telegram_summary.txt"


SENDABLE_RISK_SEVERITIES = {"MEDIUM", "HIGH", "CRITICAL"}
SENDABLE_OPPORTUNITY_GRADES = {
    "SHADOW_RESEARCH_CANDIDATE",
    "MANUAL_REVIEW_CANDIDATE",
    "PROVIDER_REVIEW_REQUIRED",
}


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_setting_value(*names):
    try:
        import config.settings as settings
    except Exception:
        settings = None

    for name in names:
        env_value = os.getenv(name)
        if env_value not in (None, ""):
            return env_value

    if settings is not None:
        for name in names:
            value = getattr(settings, name, None)
            if value not in (None, ""):
                return value

    return None


def normalize_chat_ids(value):
    if value in (None, ""):
        return []

    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]

    text = str(value).strip()

    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]

    return [text]


def telegram_credentials():
    token = get_setting_value(
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_TOKEN",
        "BOT_TOKEN",
        "TELEGRAM_API_TOKEN",
    )

    chat_ids = normalize_chat_ids(
        get_setting_value(
            "TELEGRAM_CHAT_ID",
            "TELEGRAM_USER_ID",
            "CHAT_ID",
            "TELEGRAM_CHANNEL_ID",
        )
    )

    return token, chat_ids


def mask_chat_id(chat_id):
    text = str(chat_id)
    if len(text) <= 4:
        return "***"
    return "***" + text[-4:]


def fingerprint_payload(risk_report, opportunity_report, sendable_risks, sendable_opportunities):
    payload = {
        "risk_status": risk_report.get("status"),
        "risk_highest_severity": risk_report.get("highest_severity"),
        "opportunity_status": opportunity_report.get("status"),
        "risk_alerts": [
            {
                "severity": item.get("severity"),
                "code": item.get("code"),
                "message": item.get("message"),
                "action": item.get("action"),
            }
            for item in sendable_risks
        ],
        "opportunities": [
            {
                "grade": item.get("grade"),
                "code": item.get("code"),
                "message": item.get("message"),
                "action": item.get("action"),
                "evidence": item.get("evidence"),
            }
            for item in sendable_opportunities
        ],
    }

    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_message(risk_report, opportunity_report, sendable_risks, sendable_opportunities):
    risk_counts = risk_report.get("fresh_counts", {}) or {}
    opp_counts = opportunity_report.get("fresh_counts", {}) or {}

    lines = [
        "📡 MT5 Phase 3/4 Monitoring",
        "",
        "Manual review only. No live blocking. No auto-execution.",
        "",
        "Risk/System:",
        f"- status: {risk_report.get('status')}",
        f"- highest severity: {risk_report.get('highest_severity')}",
        f"- total risk alerts: {risk_report.get('alert_count')}",
        f"- sendable risk alerts: {len(sendable_risks)}",
        "",
        "Opportunity/Research:",
        f"- status: {opportunity_report.get('status')}",
        f"- total opportunities: {opportunity_report.get('opportunity_count')}",
        f"- sendable opportunities: {len(sendable_opportunities)}",
        "",
        "Key context:",
        f"- new trades: {risk_counts.get('new_trades') or opp_counts.get('new_trades')}",
        f"- new setup outcomes: {risk_counts.get('new_setup_outcomes') or opp_counts.get('new_setup_outcomes')}",
        f"- confirmations: {risk_counts.get('new_confirmation_observations') or opp_counts.get('new_confirmation_observations')}",
        f"- order-flow gate: {risk_counts.get('orderflow_gate_status') or opp_counts.get('orderflow_gate_status')}",
        f"- order-flow can influence decision: {risk_counts.get('orderflow_can_influence_decision') or opp_counts.get('orderflow_can_influence_decision')}",
        f"- proxy change status: {opp_counts.get('proxy_change_status')}",
        f"- proxy change count: {opp_counts.get('proxy_change_count')}",
        "",
    ]

    if sendable_risks:
        lines.append("Risk alerts:")
        for item in sendable_risks:
            lines += [
                f"- {item.get('severity')} | {item.get('code')}",
                f"  {item.get('message')}",
                f"  Action: {item.get('action')}",
            ]
        lines.append("")
    else:
        lines += [
            "Risk alerts:",
            "- No MEDIUM/HIGH/CRITICAL risk alert.",
            "",
        ]

    if sendable_opportunities:
        lines.append("Opportunity candidates:")
        for item in sendable_opportunities:
            lines += [
                f"- {item.get('grade')} | {item.get('code')}",
                f"  {item.get('message')}",
                f"  Action: {item.get('action')}",
            ]
        lines.append("")
    else:
        lines += [
            "Opportunity candidates:",
            "- No opportunity candidate.",
            "",
        ]

    lines += [
        "Recommendations:",
        f"- risk: {risk_report.get('recommendation')}",
        f"- opportunity: {opportunity_report.get('recommendation')}",
        "",
        "Decision impact: NONE",
    ]

    message = "\n".join(lines)

    if len(message) > 3800:
        message = message[:3750] + "\n\n[TRUNCATED] Open JSON reports for full details."

    return message



def send_via_existing_project_notifier(message):
    """
    Use the project's existing Telegram sender.

    This avoids duplicating Telegram HTTPS logic here and reuses the same
    path already used by live_bot/order_executor/health_monitor.
    """
    from src.notifier import send_telegram_message as project_send_telegram_message

    result = project_send_telegram_message(message)

    return {
        "chat_id": "PROJECT_DEFAULT_TELEGRAM_CHAT_ID",
        "ok": result is not False,
        "response": str(result)[:300],
        "sender": "src.notifier.send_telegram_message",
    }


def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    request = urllib.request.Request(url, data=payload, method="POST")

    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read().decode("utf-8", errors="replace")

    return {
        "chat_id": mask_chat_id(chat_id),
        "ok": True,
        "response": body[:300],
    }


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    risk_report = load_json(RISK_REPORT_PATH, {})
    opportunity_report = load_json(OPPORTUNITY_REPORT_PATH, {})
    state = load_json(STATE_PATH, {})

    risk_alerts = risk_report.get("alerts", [])
    if not isinstance(risk_alerts, list):
        risk_alerts = []

    opportunities = opportunity_report.get("opportunities", [])
    if not isinstance(opportunities, list):
        opportunities = []

    sendable_risks = [
        item for item in risk_alerts
        if str(item.get("severity", "")).upper() in SENDABLE_RISK_SEVERITIES
    ]

    sendable_opportunities = [
        item for item in opportunities
        if str(item.get("grade", "")).upper() in SENDABLE_OPPORTUNITY_GRADES
    ]

    fingerprint = fingerprint_payload(
        risk_report,
        opportunity_report,
        sendable_risks,
        sendable_opportunities,
    )

    has_sendable_content = bool(sendable_risks or sendable_opportunities)

    should_send = False
    reason = "NO_SENDABLE_MONITORING_CONTENT"

    if has_sendable_content:
        if fingerprint != state.get("last_sent_fingerprint"):
            should_send = True
            reason = "NEW_OR_CHANGED_MONITORING_CONTENT"
        else:
            reason = "SKIPPED_DUPLICATE_FINGERPRINT"

    token, chat_ids = telegram_credentials()

    send_results = []
    notification_action = "SKIPPED"

    if should_send:
        if not token or not chat_ids:
            notification_action = "SKIPPED_TELEGRAM_NOT_CONFIGURED"
            reason = "TELEGRAM_TOKEN_OR_CHAT_ID_MISSING"
        else:
            message = build_message(
                risk_report,
                opportunity_report,
                sendable_risks,
                sendable_opportunities,
            )

            try:
                send_results.append(send_via_existing_project_notifier(message))
            except Exception as exc:
                send_results.append({
                    "chat_id": "PROJECT_DEFAULT_TELEGRAM_CHAT_ID",
                    "ok": False,
                    "error": repr(exc),
                    "sender": "src.notifier.send_telegram_message",
                })

            if send_results and all(item.get("ok") for item in send_results):
                notification_action = "SENT"
                state["last_sent_at"] = datetime.now().isoformat(timespec="seconds")
                state["last_sent_fingerprint"] = fingerprint
            else:
                notification_action = "SEND_FAILED"

    state["last_checked_at"] = datetime.now().isoformat(timespec="seconds")
    state["last_risk_status"] = risk_report.get("status")
    state["last_opportunity_status"] = opportunity_report.get("status")
    state["last_risk_alert_count"] = risk_report.get("alert_count")
    state["last_opportunity_count"] = opportunity_report.get("opportunity_count")
    write_json(STATE_PATH, state)

    summary = {
        "phase": "PHASE_4N_UNIFIED_TELEGRAM_MONITORING",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "notification_action": notification_action,
        "reason": reason,
        "risk_status": risk_report.get("status"),
        "risk_highest_severity": risk_report.get("highest_severity"),
        "risk_alert_count": risk_report.get("alert_count"),
        "sendable_risk_alert_count": len(sendable_risks),
        "opportunity_status": opportunity_report.get("status"),
        "opportunity_count": opportunity_report.get("opportunity_count"),
        "sendable_opportunity_count": len(sendable_opportunities),
        "telegram_configured": bool(token and chat_ids),
        "send_results": send_results,
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
    }

    lines = [
        "[PHASE 4N UNIFIED TELEGRAM MONITORING]",
        f"updated_at = {summary['updated_at']}",
        f"mode = {summary['mode']}",
        f"notification_action = {summary['notification_action']}",
        f"reason = {summary['reason']}",
        "",
        "[RISK]",
        f"risk_status = {summary['risk_status']}",
        f"risk_highest_severity = {summary['risk_highest_severity']}",
        f"risk_alert_count = {summary['risk_alert_count']}",
        f"sendable_risk_alert_count = {summary['sendable_risk_alert_count']}",
        "",
        "[OPPORTUNITY]",
        f"opportunity_status = {summary['opportunity_status']}",
        f"opportunity_count = {summary['opportunity_count']}",
        f"sendable_opportunity_count = {summary['sendable_opportunity_count']}",
        "",
        "[TELEGRAM]",
        f"telegram_configured = {summary['telegram_configured']}",
        f"send_results = {summary['send_results']}",
        "",
        "[DECISION]",
        summary["decision"],
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nstate = {STATE_PATH}")
    print(f"summary = {SUMMARY_PATH}")


if __name__ == "__main__":
    main()