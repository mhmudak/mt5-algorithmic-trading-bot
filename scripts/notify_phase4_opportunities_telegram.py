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

OPPORTUNITY_REPORT_PATH = INTEL_DIR / "phase4_opportunity_alerts_report.json"
STATE_PATH = INTEL_DIR / "phase4_opportunity_telegram_state.json"
SUMMARY_PATH = INTEL_DIR / "phase4_opportunity_telegram_summary.txt"


SENDABLE_GRADES = {
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


def fingerprint_payload(report, sendable_opportunities):
    payload = {
        "status": report.get("status"),
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


def build_message(report, sendable_opportunities):
    counts = report.get("fresh_counts", {}) or {}

    lines = [
        "🟡 Phase 4 Opportunity Review",
        "",
        "Manual review only — NOT a live trade signal.",
        "",
        f"Status: {report.get('status')}",
        f"Opportunity count: {report.get('opportunity_count')}",
        "",
        "Fresh counts:",
        f"- new_trades: {counts.get('new_trades')}",
        f"- new_setup_outcomes: {counts.get('new_setup_outcomes')}",
        f"- new_confirmations: {counts.get('new_confirmation_observations')}",
        f"- MTF conflicts: {counts.get('mtf_conflict_records')}",
        f"- liquidity POC sample: {counts.get('liquidity_poc_sample')}",
        f"- session POC confirmation sample: {counts.get('session_poc_confirmation_sample')}",
        f"- orderflow gate: {counts.get('orderflow_gate_status')}",
        f"- proxy change status: {counts.get('proxy_change_status')}",
        f"- proxy change count: {counts.get('proxy_change_count')}",
        "",
        "Opportunities:",
    ]

    for item in sendable_opportunities:
        lines += [
            f"- {item.get('grade')} | {item.get('code')}",
            f"  {item.get('message')}",
            f"  Action: {item.get('action')}",
        ]

    lines += [
        "",
        f"Recommendation: {report.get('recommendation')}",
        "",
        "Decision impact: NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
    ]

    message = "\n".join(lines)

    if len(message) > 3800:
        message = message[:3750] + "\n\n[TRUNCATED] Open phase4_opportunity_alerts_report.json for full details."

    return message


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
        "chat_id": chat_id,
        "ok": True,
        "response": body[:500],
    }


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    report = load_json(OPPORTUNITY_REPORT_PATH, {})
    state = load_json(STATE_PATH, {})

    opportunities = report.get("opportunities", [])
    if not isinstance(opportunities, list):
        opportunities = []

    sendable = [
        item for item in opportunities
        if str(item.get("grade", "")).upper() in SENDABLE_GRADES
    ]

    fingerprint = fingerprint_payload(report, sendable)

    should_send = False
    reason = "NO_SENDABLE_OPPORTUNITIES"

    if sendable:
        if fingerprint != state.get("last_sent_fingerprint"):
            should_send = True
            reason = "NEW_OR_CHANGED_OPPORTUNITIES"
        else:
            reason = "SKIPPED_DUPLICATE_OPPORTUNITY_FINGERPRINT"

    token, chat_ids = telegram_credentials()

    send_results = []
    notification_action = "SKIPPED"

    if should_send:
        if not token or not chat_ids:
            notification_action = "SKIPPED_TELEGRAM_NOT_CONFIGURED"
            reason = "TELEGRAM_TOKEN_OR_CHAT_ID_MISSING"
        else:
            message = build_message(report, sendable)

            for chat_id in chat_ids:
                try:
                    send_results.append(send_telegram_message(token, chat_id, message))
                except Exception as exc:
                    send_results.append({
                        "chat_id": chat_id,
                        "ok": False,
                        "error": repr(exc),
                    })

            if all(item.get("ok") for item in send_results):
                notification_action = "SENT"
                state["last_sent_at"] = datetime.now().isoformat(timespec="seconds")
                state["last_sent_fingerprint"] = fingerprint
            else:
                notification_action = "SEND_FAILED"

    state["last_checked_at"] = datetime.now().isoformat(timespec="seconds")
    state["last_status"] = report.get("status")
    state["last_opportunity_count"] = report.get("opportunity_count")
    write_json(STATE_PATH, state)

    summary = {
        "phase": "PHASE_4M_OPPORTUNITY_TELEGRAM_NOTIFIER",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "notification_action": notification_action,
        "reason": reason,
        "status": report.get("status"),
        "opportunity_count": report.get("opportunity_count"),
        "sendable_opportunity_count": len(sendable),
        "telegram_configured": bool(token and chat_ids),
        "send_results": [
            {
                "chat_id": item.get("chat_id"),
                "ok": item.get("ok"),
                "error": item.get("error"),
            }
            for item in send_results
        ],
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
    }

    lines = [
        "[PHASE 4M OPPORTUNITY TELEGRAM NOTIFIER]",
        f"updated_at = {summary['updated_at']}",
        f"mode = {summary['mode']}",
        f"notification_action = {summary['notification_action']}",
        f"reason = {summary['reason']}",
        "",
        "[OPPORTUNITY STATUS]",
        f"status = {summary['status']}",
        f"opportunity_count = {summary['opportunity_count']}",
        f"sendable_opportunity_count = {summary['sendable_opportunity_count']}",
        f"telegram_configured = {summary['telegram_configured']}",
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