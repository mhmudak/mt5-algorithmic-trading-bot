import json
import queue
import threading
import time
from datetime import datetime

import requests

from config.settings import (
    ENABLE_GOOGLE_SHEETS_LOGGING,
    GOOGLE_SHEETS_ASYNC_NONBLOCKING,
    GOOGLE_SHEETS_HTTP_TIMEOUT_SECONDS,
    GOOGLE_SHEETS_RETRY_REQUEST_MIN_INTERVAL_SECONDS,
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


# ============================================================
# Non-blocking Google Sheets transport
# ============================================================
#
# CRITICAL EXECUTION INVARIANT:
# Trading/setup callers may enqueue telemetry only.
#
# HTTP, response parsing, persistent retry-file access, and
# retry delivery run exclusively in this daemon worker.
#
# Google Sheets must never participate in:
# - signal detection
# - setup approval
# - order timing
# - sizing
# - SL / TP calculation
# - execute_trade latency
# ============================================================

_GOOGLE_SHEETS_WORK_QUEUE = queue.Queue()

_GOOGLE_SHEETS_WORKER_LOCK = threading.Lock()
_GOOGLE_SHEETS_WORKER_THREAD = None

_GOOGLE_SHEETS_RETRY_REQUEST_LOCK = threading.Lock()
_GOOGLE_SHEETS_LAST_RETRY_REQUEST = 0.0


def _snapshot_google_payload(payload):
    """
    Fast producer-side snapshot.

    Payload dictionaries are newly constructed by the Google
    adapter functions. A shallow copy intentionally avoids
    expensive serialization/deep-copy work on the trading path.
    """

    if not isinstance(payload, dict):
        return {}

    return dict(payload)


def _post_google_sheets_payload_sync(
    payload,
    label,
):
    """
    WORKER-ONLY synchronous HTTP transport.

    Never call this from setup detection or execution code.
    """

    if not ENABLE_GOOGLE_SHEETS_LOGGING:
        return False, "google_sheets_logging_disabled"

    if not GOOGLE_SHEETS_WEBHOOK_URL:
        return False, "google_sheets_webhook_url_missing"

    try:
        response = requests.post(
            GOOGLE_SHEETS_WEBHOOK_URL,
            json=payload,
            timeout=GOOGLE_SHEETS_HTTP_TIMEOUT_SECONDS,
        )

        if response.status_code != 200:
            return (
                False,
                f"http_{response.status_code}: "
                f"{response.text}",
            )

        data = response.json()

        if not data.get("ok"):
            return (
                False,
                f"api_error: {data}",
            )

        logger.info(
            f"[GOOGLE SHEETS WORKER] "
            f"{label} sent"
        )

        return True, None

    except Exception as exc:
        return False, str(exc)


def _flush_google_sheets_retry_queue_sync(
    max_items=5,
):
    """
    WORKER-ONLY persistent retry processing.
    """

    if not ENABLE_GOOGLE_SHEETS_LOGGING:
        return 0

    retry_items = load_google_sheets_retry_queue()

    if not retry_items:
        return 0

    remaining = []
    flushed = 0

    for item in retry_items:
        if flushed >= max_items:
            remaining.append(item)
            continue

        payload = item.get("payload", {})
        queue_key = item.get("queue_key")

        success, error = (
            _post_google_sheets_payload_sync(
                payload,
                f"Retry payload {queue_key}",
            )
        )

        if success:
            flushed += 1

            logger.info(
                f"[GOOGLE SHEETS QUEUE] "
                f"Flushed | key={queue_key}"
            )

            continue

        item["attempts"] = (
            int(item.get("attempts", 0))
            + 1
        )

        item["last_error"] = str(error)

        item["last_attempt_at"] = (
            datetime.now().isoformat()
        )

        remaining.append(item)

        logger.warning(
            f"[GOOGLE SHEETS QUEUE] "
            f"Retry failed | "
            f"key={queue_key} "
            f"attempts={item['attempts']} "
            f"error={error}"
        )

    save_google_sheets_retry_queue(
        remaining
    )

    if flushed:
        logger.info(
            f"[GOOGLE SHEETS QUEUE] "
            f"Flushed count={flushed}"
        )

    return flushed


def _google_sheets_worker_main():
    logger.info(
        "[GOOGLE SHEETS WORKER] "
        "Async worker started"
    )

    while True:
        item = _GOOGLE_SHEETS_WORK_QUEUE.get()

        try:
            if not isinstance(item, dict):
                continue

            kind = item.get("kind")

            if kind == "PAYLOAD":
                payload = item.get(
                    "payload",
                    {},
                )

                label = item.get(
                    "label",
                    "Google payload",
                )

                queue_on_failure = bool(
                    item.get(
                        "queue_on_failure",
                        True,
                    )
                )

                success, error = (
                    _post_google_sheets_payload_sync(
                        payload,
                        label,
                    )
                )

                if (
                    not success
                    and queue_on_failure
                ):
                    try:
                        queue_google_sheets_payload(
                            dict(payload),
                            error,
                        )

                    except Exception as exc:
                        logger.error(
                            "[GOOGLE SHEETS WORKER] "
                            "Failed to persist retry "
                            f"payload | error={exc}"
                        )

                elif not success:
                    logger.error(
                        "[GOOGLE SHEETS WORKER] "
                        f"{label} failed | "
                        f"error={error}"
                    )

            elif kind == "FLUSH_RETRY":
                _flush_google_sheets_retry_queue_sync(
                    max_items=max(
                        1,
                        int(
                            item.get(
                                "max_items",
                                5,
                            )
                        ),
                    )
                )

        except Exception as exc:
            logger.error(
                "[GOOGLE SHEETS WORKER] "
                f"Unhandled worker error: {exc}"
            )

        finally:
            _GOOGLE_SHEETS_WORK_QUEUE.task_done()


def _ensure_google_sheets_worker_started():
    global _GOOGLE_SHEETS_WORKER_THREAD

    worker = _GOOGLE_SHEETS_WORKER_THREAD

    if (
        worker is not None
        and worker.is_alive()
    ):
        return True

    with _GOOGLE_SHEETS_WORKER_LOCK:
        worker = (
            _GOOGLE_SHEETS_WORKER_THREAD
        )

        if (
            worker is not None
            and worker.is_alive()
        ):
            return True

        try:
            worker = threading.Thread(
                target=_google_sheets_worker_main,
                name="google-sheets-worker",
                daemon=True,
            )

            worker.start()

            _GOOGLE_SHEETS_WORKER_THREAD = (
                worker
            )

            return True

        except Exception as exc:
            logger.error(
                "[GOOGLE SHEETS ASYNC] "
                "Failed to start worker | "
                f"error={exc}"
            )

            return False


def enqueue_google_sheets_payload(
    payload,
    label,
    *,
    queue_on_failure=True,
):
    """
    Producer-side API.

    This function performs NO:
    - HTTP
    - retry-file reads
    - retry-file writes
    - sleeps
    - waits for Google
    """

    if not ENABLE_GOOGLE_SHEETS_LOGGING:
        return (
            False,
            "google_sheets_logging_disabled",
        )

    if not GOOGLE_SHEETS_WEBHOOK_URL:
        return (
            False,
            "google_sheets_webhook_url_missing",
        )

    if not _ensure_google_sheets_worker_started():
        return (
            False,
            "google_sheets_worker_unavailable",
        )

    try:
        _GOOGLE_SHEETS_WORK_QUEUE.put_nowait(
            {
                "kind": "PAYLOAD",
                "payload": (
                    _snapshot_google_payload(
                        payload
                    )
                ),
                "label": str(label),
                "queue_on_failure": bool(
                    queue_on_failure
                ),
                "queued_at": (
                    datetime.now().isoformat()
                ),
            }
        )

        return True, None

    except Exception as exc:
        logger.error(
            "[GOOGLE SHEETS ASYNC] "
            "Failed to enqueue payload | "
            f"label={label} error={exc}"
        )

        return False, str(exc)


def _request_google_sheets_retry_flush(
    max_items=5,
):
    """
    Non-blocking, rate-limited retry request.

    The main trading loop may call this safely. It does not
    touch the persistent retry file or perform HTTP.
    """

    global _GOOGLE_SHEETS_LAST_RETRY_REQUEST

    if not ENABLE_GOOGLE_SHEETS_LOGGING:
        return False

    if not _ensure_google_sheets_worker_started():
        return False

    now = time.monotonic()

    with _GOOGLE_SHEETS_RETRY_REQUEST_LOCK:
        elapsed = (
            now
            - _GOOGLE_SHEETS_LAST_RETRY_REQUEST
        )

        if (
            _GOOGLE_SHEETS_LAST_RETRY_REQUEST
            and elapsed
            < GOOGLE_SHEETS_RETRY_REQUEST_MIN_INTERVAL_SECONDS
        ):
            return False

        _GOOGLE_SHEETS_LAST_RETRY_REQUEST = (
            now
        )

    try:
        _GOOGLE_SHEETS_WORK_QUEUE.put_nowait(
            {
                "kind": "FLUSH_RETRY",
                "max_items": max(
                    1,
                    int(max_items),
                ),
            }
        )

        return True

    except Exception as exc:
        logger.error(
            "[GOOGLE SHEETS ASYNC] "
            "Failed to enqueue retry flush | "
            f"error={exc}"
        )

        return False


def _wait_for_google_sheets_worker_idle_for_test(
    timeout_seconds=3.0,
):
    """
    Focused regression helper only.
    Never used by live trading.
    """

    deadline = (
        time.monotonic()
        + float(timeout_seconds)
    )

    while (
        time.monotonic()
        < deadline
    ):
        if (
            _GOOGLE_SHEETS_WORK_QUEUE
            .unfinished_tasks
            == 0
        ):
            return True

        time.sleep(0.01)

    return False


def post_google_sheets_payload(
    payload,
    label,
    queue_on_failure=True,
):
    """
    Compatibility API.

    Success means accepted by the asynchronous outbox,
    NOT that Google has already acknowledged the row.
    """

    return enqueue_google_sheets_payload(
        payload,
        label,
        queue_on_failure=queue_on_failure,
    )


def send_setup_event_to_google_sheets(
    event_data,
):
    payload = {
        "secret": GOOGLE_SHEETS_WEBHOOK_SECRET,
        "sheet": "Events",
        **event_data,
    }

    accepted, error = (
        post_google_sheets_payload(
            payload,
            "Setup event",
            queue_on_failure=True,
        )
    )

    if not accepted:
        logger.error(
            "[GOOGLE SHEETS ASYNC] "
            "Failed to queue setup event: "
            f"{error}"
        )
        return False

    logger.info(
        "[GOOGLE SHEETS ASYNC] "
        "Setup event queued"
    )

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


def send_setup_outcome_to_google_sheets(
    item,
    queue_on_failure=True,
):
    payload = build_setup_outcome_payload(
        item
    )

    accepted, error = (
        post_google_sheets_payload(
            payload,
            "Setup outcome",
            queue_on_failure=queue_on_failure,
        )
    )

    if not accepted:
        logger.error(
            "[GOOGLE SHEETS ASYNC] "
            "Failed to queue setup outcome: "
            f"{error}"
        )
        return False

    logger.info(
        "[GOOGLE SHEETS ASYNC] "
        "Setup outcome queued"
    )

    return True


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


def send_memory_decision_report_to_google_sheets(
    report,
    queue_on_failure=True,
):
    payload = (
        build_memory_decision_report_payload(
            report
        )
    )

    accepted, error = (
        post_google_sheets_payload(
            payload,
            "Memory decision report",
            queue_on_failure=queue_on_failure,
        )
    )

    if not accepted:
        logger.error(
            "[GOOGLE SHEETS ASYNC] "
            "Failed to queue memory "
            f"decision report: {error}"
        )
        return False

    logger.info(
        "[GOOGLE SHEETS ASYNC] "
        "Memory decision report queued"
    )

    return True


def flush_google_sheets_retry_queue(
    max_items=5,
):
    """
    Legacy compatibility entry point.

    IMPORTANT:
    This no longer performs retry HTTP or retry-file I/O
    on the caller thread.

    It only schedules a background retry request.
    """

    _request_google_sheets_retry_flush(
        max_items=max_items,
    )

    return 0


# Start the daemon worker during module/bootstrap time.
#
# This performs NO network access. The worker immediately
# blocks on Queue.get() until telemetry is submitted.
#
# Result: the first live setup/execution event does not pay
# Python thread-creation latency.
if (
    ENABLE_GOOGLE_SHEETS_LOGGING
    and GOOGLE_SHEETS_ASYNC_NONBLOCKING
):
    _ensure_google_sheets_worker_started()
