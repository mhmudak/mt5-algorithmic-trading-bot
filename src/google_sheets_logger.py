import json
from datetime import datetime

import requests

from config.settings import (
    ENABLE_GOOGLE_SHEETS_LOGGING,
    GOOGLE_SHEETS_WEBHOOK_URL,
    GOOGLE_SHEETS_WEBHOOK_SECRET,
)
from src.account_context import get_account_file
from src.logger import logger


def get_google_sheets_retry_queue_file():
    return get_account_file("google_sheets_retry_queue.json")


def load_google_sheets_retry_queue():
    path = get_google_sheets_retry_queue_file()

    if not path.exists():
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[GOOGLE SHEETS QUEUE] Failed to load queue: {e}")
        return []


def save_google_sheets_retry_queue(items):
    path = get_google_sheets_retry_queue_file()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[GOOGLE SHEETS QUEUE] Failed to save queue: {e}")


def build_payload_queue_key(payload):
    if payload.get("queue_key"):
        return payload["queue_key"]

    sheet = payload.get("sheet", "UNKNOWN")
    action = payload.get("action", "APPEND")
    setup_id = payload.get("setup_id") or "NO_SETUP_ID"

    if sheet == "SetupOutcomes" and action == "UPSERT":
        return f"{sheet}:{action}:{setup_id}"

    if action == "APPEND":
        created_at = payload.get("created_at") or datetime.now().isoformat()
        decision = payload.get("decision") or payload.get("event") or "NO_DECISION"
        return f"{sheet}:{action}:{setup_id}:{decision}:{created_at}"

    return f"{sheet}:{action}:{setup_id}"


def queue_google_sheets_payload(payload, reason):
    queue = load_google_sheets_retry_queue()
    queue_key = build_payload_queue_key(payload)

    payload["queue_key"] = queue_key

    existing = None

    for item in queue:
        if item.get("queue_key") == queue_key:
            existing = item
            break

    if existing:
        existing["payload"] = payload
        existing["last_error"] = str(reason)
        existing["updated_at"] = datetime.now().isoformat()
        existing["attempts"] = int(existing.get("attempts", 0))
    else:
        queue.append(
            {
                "queue_key": queue_key,
                "payload": payload,
                "attempts": 0,
                "last_error": str(reason),
                "queued_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
        )

    save_google_sheets_retry_queue(queue)

    logger.warning(
        f"[GOOGLE SHEETS QUEUE] Payload queued | "
        f"key={queue_key} reason={reason}"
    )


def post_google_sheets_payload(payload, label):
    if not ENABLE_GOOGLE_SHEETS_LOGGING:
        return False, "google_sheets_logging_disabled"

    if not GOOGLE_SHEETS_WEBHOOK_URL:
        return False, "google_sheets_webhook_url_missing"

    try:
        response = requests.post(
            GOOGLE_SHEETS_WEBHOOK_URL,
            json=payload,
            timeout=15,
        )

        if response.status_code != 200:
            return False, f"http_{response.status_code}: {response.text}"

        data = response.json()

        if not data.get("ok"):
            return False, f"api_error: {data}"

        logger.info(f"[GOOGLE SHEETS] {label} sent")
        return True, None

    except Exception as e:
        return False, str(e)


def send_setup_event_to_google_sheets(event_data):
    payload = {
        "secret": GOOGLE_SHEETS_WEBHOOK_SECRET,
        "sheet": "Events",
        **event_data,
    }

    success, error = post_google_sheets_payload(payload, "Setup event")

    if not success:
        logger.error(f"[GOOGLE SHEETS] Failed to send event: {error}")
        return False

    return True


def build_setup_outcome_payload(item):
    source_events = item.get("source_events", [])
    nearby_strategies = item.get("nearby_strategies", [])

    if isinstance(source_events, list):
        source_events = ",".join(source_events)

    if isinstance(nearby_strategies, list):
        nearby_strategies = ",".join(nearby_strategies)

    return {
        "secret": GOOGLE_SHEETS_WEBHOOK_SECRET,
        "sheet": "SetupOutcomes",
        "action": "UPSERT",
        "key": "setup_id",
        "setup_id": item.get("setup_id"),
        "symbol": item.get("symbol"),
        "source_events": source_events,
        "strategy": item.get("strategy"),
        "signal": item.get("signal"),
        "entry_model": item.get("entry_model"),
        "session": item.get("session"),
        "market_condition": item.get("market_condition"),
        "score": item.get("score"),
        "entry": item.get("entry"),
        "sl": item.get("sl"),
        "tp": item.get("tp"),
        "max_favorable_usd": item.get("max_favorable_usd"),
        "max_adverse_usd": item.get("max_adverse_usd"),
        "max_recovery_swing_usd": item.get("max_recovery_swing_usd"),
        "hit_plus_10": item.get("hit_plus_10"),
        "hit_tp": item.get("hit_tp"),
        "hit_sl": item.get("hit_sl"),
        "first_hit": item.get("first_hit"),
        "final_outcome": item.get("final_outcome"),
        "status": item.get("status"),
        "context_key": item.get("context_key"),
        "scenario_key": item.get("scenario_key"),
        "nearby_strategies": nearby_strategies,
        "created_at": item.get("created_at"),
        "last_seen_at": item.get("last_seen_at"),
        "updated_at": item.get("updated_at"),
    }


def send_setup_outcome_to_google_sheets(item, queue_on_failure=True):
    payload = build_setup_outcome_payload(item)

    success, error = post_google_sheets_payload(payload, "Setup outcome")

    if success:
        logger.info("[GOOGLE SHEETS] Setup outcome upserted")
        return True

    logger.error(f"[GOOGLE SHEETS] Failed to send setup outcome: {error}")

    if queue_on_failure:
        queue_google_sheets_payload(payload, error)

    return False


def build_memory_decision_report_payload(report):
    queue_key = (
        f"MemoryDecisionReports:APPEND:"
        f"{report.get('setup_id')}:{report.get('decision')}:{report.get('created_at')}"
    )

    return {
        "secret": GOOGLE_SHEETS_WEBHOOK_SECRET,
        "sheet": "MemoryDecisionReports",
        "action": "APPEND",
        "queue_key": queue_key,
        "setup_id": report.get("setup_id"),
        "created_at": report.get("created_at"),
        "decision": report.get("decision"),
        "decision_reason": report.get("decision_reason"),
        "strategy": report.get("strategy"),
        "signal": report.get("signal"),
        "score": report.get("score"),
        "session": report.get("session"),
        "market_condition": report.get("market_condition"),
        "entry_model": report.get("entry_model"),
        "news_tag": report.get("setup_news_tag"),
        "entry": report.get("entry"),
        "sl": report.get("sl"),
        "tp": report.get("tp"),
        "lot": report.get("lot"),
        "rr": report.get("rr"),
        "required_rr": report.get("required_rr"),
        "reason": report.get("reason"),
        "memory_json": report.get("memory"),
        "adjustments_json": report.get("adjustments"),
        "context_json": report.get("context"),
        "extra_json": report.get("extra"),
        "ai_recommendation": report.get("ai_recommendation"),
        "ai_reason": report.get("ai_reason"),
        "ai_match_type": report.get("ai_match_type"),
        "ai_samples": report.get("ai_samples"),
        "ai_w10_rate": report.get("ai_w10_rate"),
        "ai_tp_rate": report.get("ai_tp_rate"),
        "ai_sl_rate": report.get("ai_sl_rate"),
        "ai_execution_allowed": report.get("ai_execution_allowed"),
        "ai_execution_reason": report.get("ai_execution_reason"),
        "ai_shadow_advice_json": report.get("ai_shadow_advice"),
    }


def send_memory_decision_report_to_google_sheets(report, queue_on_failure=True):
    payload = build_memory_decision_report_payload(report)

    success, error = post_google_sheets_payload(
        payload,
        "Memory decision report",
    )

    if success:
        logger.info("[GOOGLE SHEETS] Memory decision report appended")
        return True

    logger.error(f"[GOOGLE SHEETS] Failed to send memory decision report: {error}")

    if queue_on_failure:
        queue_google_sheets_payload(payload, error)

    return False


def flush_google_sheets_retry_queue(max_items=5):
    if not ENABLE_GOOGLE_SHEETS_LOGGING:
        return 0

    queue = load_google_sheets_retry_queue()

    if not queue:
        return 0

    remaining = []
    flushed = 0

    for item in queue:
        if flushed >= max_items:
            remaining.append(item)
            continue

        payload = item.get("payload", {})
        queue_key = item.get("queue_key")

        success, error = post_google_sheets_payload(
            payload,
            f"Retry payload {queue_key}",
        )

        if success:
            flushed += 1
            logger.info(f"[GOOGLE SHEETS QUEUE] Flushed | key={queue_key}")
            continue

        item["attempts"] = int(item.get("attempts", 0)) + 1
        item["last_error"] = str(error)
        item["last_attempt_at"] = datetime.now().isoformat()
        remaining.append(item)

        logger.warning(
            f"[GOOGLE SHEETS QUEUE] Retry failed | "
            f"key={queue_key} attempts={item['attempts']} error={error}"
        )

    save_google_sheets_retry_queue(remaining)

    if flushed:
        logger.info(f"[GOOGLE SHEETS QUEUE] Flushed count={flushed}")

    return flushed