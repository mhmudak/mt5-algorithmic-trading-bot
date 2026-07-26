from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"
RITHMIC_DIR = ROOT / "data" / "order_flow" / "rithmic"

OPPORTUNITY_REPORT_PATH = INTEL_DIR / "phase4_opportunity_alerts_report.json"
DECISION_CANDIDATES_PATH = INTEL_DIR / "phase3_decision_candidates_report.json"
RITHMIC_QUALITY_PATH = RITHMIC_DIR / "phase5l_rithmic_data_quality_gate_report.json"
RITHMIC_BRIDGE_PATH = RITHMIC_DIR / "GCQ6_phase5g_rithmic_monitoring_bridge.json"

STATE_PATH = INTEL_DIR / "phase5n_setup_gated_rithmic_filter_state.json"
REPORT_PATH = INTEL_DIR / "phase5n_setup_gated_rithmic_filter_report.json"
SUMMARY_PATH = INTEL_DIR / "phase5n_setup_gated_rithmic_filter_summary.txt"


SETUP_GRADES = {
    "MANUAL_REVIEW_CANDIDATE",
    "PROVIDER_REVIEW_REQUIRED",
}

EXCLUDED_RESEARCH_CODES = {
    "LIQUIDITY_POC_CONTEXT_SAMPLE_READY",
    "SESSION_POC_CONFIRMATION_SAMPLE_READY",
    "MTF_CONFLICT_SAMPLE_READY",
    "POC_CONTEXT_SAMPLE_READY",
    "PROXY_CONTEXT_CHANGED",
    "MT5_PROXY_CONTEXT_CHANGED",
}

EXCLUDED_STATUSES = {
    "NOT_READY",
    "NO_CASES_YET",
    "NOT_NEEDED_NOW",
    "OBSERVE_ONLY_NOT_DECISION_GRADE",
    "MONITOR_MORE",
    "NOT_CONNECTED",
}


def is_real_setup_candidate(item: dict[str, Any]) -> bool:
    grade = str(item.get("grade") or "").upper()
    status = str(item.get("status") or "").upper()
    code = str(item.get("code") or "").upper()

    if code in EXCLUDED_RESEARCH_CODES:
        return False

    if grade in EXCLUDED_STATUSES or status in EXCLUDED_STATUSES:
        return False

    if grade in SETUP_GRADES:
        return True

    evidence = item.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}

    raw_text = json.dumps(item, ensure_ascii=False).upper()

    has_direction = any(word in raw_text for word in [
        '"BUY"',
        '"SELL"',
        "DIRECTION",
        "SIGNAL",
        "ENTRY",
        "SL",
        "TP",
        "STOP_LOSS",
        "TAKE_PROFIT",
        "RR",
    ])

    has_trade_action = any(word in raw_text for word in [
        "WAIT_BETTER_ENTRY",
        "EXECUTABLE",
        "SETUP_DETECTED",
        "TRADE_SETUP",
        "MANUAL_REVIEW_CANDIDATE",
        "PROVIDER_REVIEW_REQUIRED",
    ])

    return bool(has_direction and has_trade_action)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_nested(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = data

    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)

    return cur if cur is not None else default


def load_rithmic_quality() -> dict[str, Any]:
    quality = load_json(RITHMIC_QUALITY_PATH, {})
    bridge = load_json(RITHMIC_BRIDGE_PATH, {})

    if not quality:
        return {
            "loaded": False,
            "overall_status": "RITHMIC_QUALITY_GATE_NOT_BUILT",
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "recommendation": "Run Phase 5L quality gate before using Rithmic as a setup filter.",
            "validations": [],
            "bridge": bridge,
        }

    quality["loaded"] = True
    quality["bridge"] = bridge
    return quality


def collect_setup_candidates() -> list[dict[str, Any]]:
    opportunity_report = load_json(OPPORTUNITY_REPORT_PATH, {})
    decision_report = load_json(DECISION_CANDIDATES_PATH, {})

    candidates: list[dict[str, Any]] = []

    opportunities = opportunity_report.get("opportunities") or []
    if isinstance(opportunities, list):
        for item in opportunities:
            if not isinstance(item, dict):
                continue

            if is_real_setup_candidate(item):
                candidates.append({
                    "source": "phase4_opportunity_alerts",
                    "grade": item.get("grade"),
                    "code": item.get("code"),
                    "message": item.get("message"),
                    "action": item.get("action"),
                    "evidence": item.get("evidence"),
                    "raw": item,
                })

    # Fallback: only include clear candidate-like records if the report exposes them.
    for key in ["candidates", "decision_candidates", "items", "records"]:
        records = decision_report.get(key)

        if not isinstance(records, list):
            continue

        for item in records:
            if not isinstance(item, dict):
                continue

            if is_real_setup_candidate(item):
                candidates.append({
                    "source": f"phase3_decision_candidates.{key}",
                    "grade": item.get("grade") or item.get("status"),
                    "code": item.get("code") or item.get("strategy") or item.get("setup_type"),
                    "message": item.get("message") or item.get("reason") or item.get("summary"),
                    "action": item.get("action") or "MANUAL_REVIEW_ONLY",
                    "evidence": item.get("evidence") or item,
                    "raw": item,
                })

    return candidates


def summarize_rithmic_quality(quality: dict[str, Any]) -> dict[str, Any]:
    bridge = quality.get("bridge") or {}
    bridge_metrics = bridge.get("adapter_metrics") or {}

    validations = quality.get("validations") or []
    symbol_summaries = []

    if isinstance(validations, list):
        for item in validations:
            if not isinstance(item, dict):
                continue

            metrics = item.get("metrics") or {}

            symbol_summaries.append({
                "symbol": item.get("symbol"),
                "status": item.get("status"),
                "quality_failures": item.get("quality_failures"),
                "hard_failures": item.get("hard_failures"),
                "trade_count": metrics.get("trade_count"),
                "spread": metrics.get("spread"),
                "dom_available": metrics.get("dom_available"),
                "dom_bid_depth": metrics.get("dom_bid_depth"),
                "dom_ask_depth": metrics.get("dom_ask_depth"),
                "delta": metrics.get("delta"),
                "cumulative_delta": metrics.get("cumulative_delta"),
                "order_book_update_type": metrics.get("order_book_update_type"),
            })

    return {
        "loaded": bool(quality.get("loaded")),
        "overall_status": quality.get("overall_status"),
        "all_hard_ok": quality.get("all_hard_ok"),
        "all_quality_ok": quality.get("all_quality_ok"),
        "decision_impact": quality.get("decision_impact", "NONE"),
        "can_influence_decision": quality.get("can_influence_decision", False),
        "recommendation": quality.get("recommendation"),
        "bridge_status": bridge.get("bridge_status"),
        "provider_status": bridge.get("provider_status"),
        "bridge_delta": bridge_metrics.get("delta"),
        "bridge_cumulative_delta": bridge_metrics.get("cumulative_delta"),
        "bridge_dom_available": bridge_metrics.get("dom_available"),
        "symbols": symbol_summaries,
    }


def infer_rithmic_filter_result(candidate: dict[str, Any], quality_summary: dict[str, Any]) -> dict[str, Any]:
    overall_status = str(quality_summary.get("overall_status") or "")

    if not quality_summary.get("loaded"):
        result = "BLOCKED_RITHMIC_QUALITY_NOT_BUILT"
        conclusion = "Setup exists, but Rithmic quality gate has not been built."
    elif overall_status == "RITHMIC_DATA_QUALITY_VALIDATED_OBSERVE_ONLY":
        result = "RITHMIC_QUALITY_PASSED_CONTEXT_ONLY"
        conclusion = "Setup exists and Rithmic data quality passed observe-only validation. Still manual review only."
    else:
        result = "BLOCKED_RITHMIC_DATA_QUALITY_BAD"
        conclusion = "Setup exists, but Rithmic data quality does not confirm it."

    return {
        "filter_result": result,
        "setup_alignment": "NOT_EVALUATED_YET",
        "trade_action": "NO_AUTO_TRADE",
        "manual_action": "REVIEW_ONLY_DO_NOT_USE_RITHMIC_AS_CONFIRMATION_IF_QUALITY_BAD",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "conclusion": conclusion,
    }


def candidate_fingerprint(candidate: dict[str, Any], quality_summary: dict[str, Any]) -> str:
    payload = {
        "source": candidate.get("source"),
        "grade": candidate.get("grade"),
        "code": candidate.get("code"),
        "message": candidate.get("message"),
        "quality_status": quality_summary.get("overall_status"),
        "decision_impact": quality_summary.get("decision_impact"),
        "can_influence_decision": quality_summary.get("can_influence_decision"),
    }

    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def format_candidate_message(
    candidate: dict[str, Any],
    quality_summary: dict[str, Any],
    filter_result: dict[str, Any],
) -> str:
    lines = [
        "🚨 SETUP / CANDIDATE DETECTED — MANUAL REVIEW ONLY",
        "",
        "TRADE ACTION: NO AUTO TRADE",
        "MANUAL ACTION: REVIEW ONLY",
        "RITHMIC DECISION IMPACT: NONE",
        "RITHMIC CAN INFLUENCE DECISION: False",
        "",
        "[SETUP / CANDIDATE]",
        f"source: {candidate.get('source')}",
        f"grade: {candidate.get('grade')}",
        f"code: {candidate.get('code')}",
        f"message: {candidate.get('message')}",
        f"action: {candidate.get('action')}",
        "",
        "[RITHMIC ORDER-FLOW FILTER]",
        f"quality_status: {quality_summary.get('overall_status')}",
        f"filter_result: {filter_result.get('filter_result')}",
        f"setup_alignment: {filter_result.get('setup_alignment')}",
        f"bridge_status: {quality_summary.get('bridge_status')}",
        f"provider_status: {quality_summary.get('provider_status')}",
        f"all_hard_ok: {quality_summary.get('all_hard_ok')}",
        f"all_quality_ok: {quality_summary.get('all_quality_ok')}",
        f"delta: {quality_summary.get('bridge_delta')}",
        f"cumulative_delta: {quality_summary.get('bridge_cumulative_delta')}",
        f"dom_available: {quality_summary.get('bridge_dom_available')}",
        "",
        "[RITHMIC SYMBOL DETAILS]",
    ]

    symbols = quality_summary.get("symbols") or []
    if symbols:
        for item in symbols[:4]:
            lines += [
                f"- {item.get('symbol')}: {item.get('status')}",
                f"  failures: {item.get('quality_failures')}",
                f"  trades: {item.get('trade_count')} | spread: {item.get('spread')}",
                f"  DOM: {item.get('dom_available')} | bid_depth: {item.get('dom_bid_depth')} | ask_depth: {item.get('dom_ask_depth')}",
                f"  delta: {item.get('delta')} | cum_delta: {item.get('cumulative_delta')}",
            ]
    else:
        lines.append("- No Phase 5L symbol details available.")

    lines += [
        "",
        "[CONCLUSION]",
        filter_result.get("conclusion"),
        "",
        "Do not treat this as a trade signal. This is a setup-gated Rithmic filter note only.",
    ]

    message = "\n".join(lines)

    if len(message) > 3800:
        message = message[:3750] + "\n\n[TRUNCATED] Open JSON reports for full details."

    return message


def send_telegram(message: str) -> dict[str, Any]:
    from src.notifier import send_telegram_message

    result = send_telegram_message(message)

    return {
        "ok": result is not False,
        "sender": "src.notifier.send_telegram_message",
        "response": str(result)[:300],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-candidates", type=int, default=3)
    args = parser.parse_args()

    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    state = load_json(STATE_PATH, {})
    quality = load_rithmic_quality()
    quality_summary = summarize_rithmic_quality(quality)
    candidates = collect_setup_candidates()

    selected = candidates[: max(1, args.max_candidates)]

    events = []
    send_results = []
    notification_action = "SKIPPED"
    reason = "NO_SETUP_CANDIDATE"

    if selected:
        reason = "SETUP_CANDIDATE_FOUND"

        for candidate in selected:
            filter_result = infer_rithmic_filter_result(candidate, quality_summary)
            fingerprint = candidate_fingerprint(candidate, quality_summary)
            duplicate = fingerprint == state.get("last_sent_fingerprint")

            message = format_candidate_message(candidate, quality_summary, filter_result)

            event = {
                "candidate": candidate,
                "quality_summary": quality_summary,
                "filter_result": filter_result,
                "fingerprint": fingerprint,
                "duplicate": duplicate,
                "message_preview": message[:1000],
                "trade_action": "NO_AUTO_TRADE",
                "manual_review_only": True,
                "decision_impact": "NONE",
                "can_influence_decision": False,
            }

            if args.send_telegram and (args.force or not duplicate):
                try:
                    send_result = send_telegram(message)
                    send_results.append(send_result)
                    event["telegram_sent"] = bool(send_result.get("ok"))
                except Exception as exc:
                    send_result = {"ok": False, "error": repr(exc)}
                    send_results.append(send_result)
                    event["telegram_sent"] = False
                    event["telegram_error"] = repr(exc)
            else:
                event["telegram_sent"] = False

            events.append(event)

        if args.send_telegram:
            if send_results and all(item.get("ok") for item in send_results):
                notification_action = "SENT"
                state["last_sent_at"] = now_iso()
                state["last_sent_fingerprint"] = events[0]["fingerprint"]
            elif send_results:
                notification_action = "SEND_FAILED"
            else:
                notification_action = "SKIPPED_DUPLICATE_OR_NOT_FORCED"
        else:
            notification_action = "DRY_RUN_NOT_SENT"

    state["last_checked_at"] = now_iso()
    state["last_candidate_count"] = len(candidates)
    state["last_rithmic_quality_status"] = quality_summary.get("overall_status")
    write_json(STATE_PATH, state)

    report = {
        "phase": "PHASE_5N_SETUP_GATED_RITHMIC_TELEGRAM_FILTER",
        "mode": "OBSERVE_ONLY",
        "updated_at": now_iso(),
        "notification_action": notification_action,
        "reason": reason,
        "candidate_count": len(candidates),
        "selected_candidate_count": len(selected),
        "send_telegram": args.send_telegram,
        "force": args.force,
        "trade_action": "NO_AUTO_TRADE",
        "manual_review_only": True,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "rithmic_quality": quality_summary,
        "events": events,
        "send_results": send_results,
        "recommendation": "Use this only as setup-gated manual-review context. Do not enable live execution from Rithmic.",
    }

    write_json(REPORT_PATH, report)

    lines = [
        "[PHASE 5N SETUP-GATED RITHMIC TELEGRAM FILTER]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"notification_action = {notification_action}",
        f"reason = {reason}",
        f"candidate_count = {len(candidates)}",
        f"selected_candidate_count = {len(selected)}",
        f"send_telegram = {args.send_telegram}",
        f"force = {args.force}",
        f"trade_action = {report['trade_action']}",
        f"manual_review_only = {report['manual_review_only']}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        "",
        "[RITHMIC QUALITY]",
        f"overall_status = {quality_summary.get('overall_status')}",
        f"all_hard_ok = {quality_summary.get('all_hard_ok')}",
        f"all_quality_ok = {quality_summary.get('all_quality_ok')}",
        f"bridge_status = {quality_summary.get('bridge_status')}",
        f"provider_status = {quality_summary.get('provider_status')}",
        f"delta = {quality_summary.get('bridge_delta')}",
        f"cumulative_delta = {quality_summary.get('bridge_cumulative_delta')}",
        f"dom_available = {quality_summary.get('bridge_dom_available')}",
        "",
        "[EVENTS]",
    ]

    if events:
        for event in events:
            c = event["candidate"]
            fr = event["filter_result"]
            lines += [
                f"- source = {c.get('source')}",
                f"  grade = {c.get('grade')}",
                f"  code = {c.get('code')}",
                f"  filter_result = {fr.get('filter_result')}",
                f"  setup_alignment = {fr.get('setup_alignment')}",
                f"  telegram_sent = {event.get('telegram_sent')}",
                f"  duplicate = {event.get('duplicate')}",
            ]
    else:
        lines.append("- No setup/candidate found. No Telegram message needed.")

    lines += [
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nreport = {REPORT_PATH}")
    print(f"summary = {SUMMARY_PATH}")
    print(f"state = {STATE_PATH}")


if __name__ == "__main__":
    main()
