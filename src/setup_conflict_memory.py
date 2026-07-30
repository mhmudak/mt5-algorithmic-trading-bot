from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.setup_conflict_resolver import resolve_setup_conflict


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "strategy_intelligence" / "phase5ah_setup_conflicts"

EVENTS_PATH = DATA_DIR / "phase5ah_setup_state_events.json"
CONFLICTS_PATH = DATA_DIR / "phase5ah_setup_conflicts.json"
CONFLICTS_JSONL_PATH = DATA_DIR / "phase5ah_setup_conflicts.jsonl"
LATEST_CONFLICT_PATH = DATA_DIR / "phase5ah_latest_setup_conflict.json"

MAX_EVENTS = 500


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def epoch_to_iso(value: Any) -> str | None:
    try:
        if value is None:
            return None
        return datetime.fromtimestamp(float(value)).isoformat(timespec="seconds")
    except Exception:
        return None


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    created_at = (
        event.get("created_at")
        or event.get("detected_at")
        or epoch_to_iso(event.get("created_at_epoch"))
        or epoch_to_iso(event.get("detected_at_epoch"))
        or now_iso()
    )

    strategy = safe_text(event.get("strategy")).upper()
    signal = safe_text(event.get("signal") or event.get("direction")).upper()
    reason = safe_text(
        event.get("entry_skip_reason")
        or event.get("rejection_reason")
        or event.get("reason")
    )

    state = safe_text(event.get("state")).upper()

    if not state:
        reason_lower = reason.lower()
        if "m5_body_too_small" in reason_lower:
            state = "ENTRY_SKIPPED_WEAK_CONFIRMATION"
        elif "score_too_low" in reason_lower:
            state = "REJECTED_SCORE_TOO_LOW"
        elif "rejected" in reason_lower:
            state = "TRACKED_REJECTED_CANDIDATE"
        else:
            state = "SETUP_DETECTED"

    return {
        "phase": "PHASE_5AH_SETUP_CONFLICT_RESOLVER",
        "recorded_at": now_iso(),
        "created_at": created_at,
        "created_at_epoch": event.get("created_at_epoch") or event.get("detected_at_epoch"),
        "symbol": safe_text(event.get("symbol")).upper() or "XAUUSD",
        "setup_id": safe_text(event.get("setup_id")),
        "strategy": strategy,
        "signal": signal,
        "direction": signal,
        "entry_model": safe_text(event.get("entry_model")),
        "session": safe_text(event.get("session") or event.get("session_name")),
        "market_condition": safe_text(event.get("market_condition") or event.get("market")),
        "score": safe_float(event.get("score")),
        "min_required_score": safe_float(event.get("min_required_score") or event.get("required_score")),
        "entry": safe_float(event.get("entry") or event.get("entry_price")),
        "sl": safe_float(event.get("sl") or event.get("stop_loss")),
        "tp": safe_float(event.get("tp") or event.get("take_profit")),
        "rr": safe_float(event.get("rr") or event.get("risk_reward") or event.get("rr_value")),
        "state": state,
        "entry_skip_reason": safe_text(event.get("entry_skip_reason")),
        "rejection_reason": safe_text(event.get("rejection_reason")),
        "reason": reason,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "auto_trade_allowed": False,
    }


def event_key(event: dict[str, Any]) -> str:
    return "|".join(
        [
            safe_text(event.get("setup_id")),
            safe_text(event.get("strategy")),
            safe_text(event.get("signal")),
            safe_text(event.get("state")),
            safe_text(event.get("reason")),
        ]
    )


def conflict_key(report: dict[str, Any]) -> str:
    previous_setup = report.get("previous_setup") or {}
    new_setup = report.get("new_setup") or {}
    metrics = report.get("conflict_metrics") or {}

    return "|".join(
        [
            safe_text(previous_setup.get("setup_id")),
            safe_text(previous_setup.get("strategy")),
            safe_text(previous_setup.get("direction")),
            safe_text(new_setup.get("setup_id")),
            safe_text(new_setup.get("strategy")),
            safe_text(new_setup.get("direction")),
            safe_text(report.get("conflict_status")),
            safe_text(metrics.get("entry_distance")),
        ]
    )


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def record_setup_state_event(
    event: dict[str, Any],
    *,
    max_minutes: int = 30,
    max_entry_distance: float = 3.0,
    min_conflict_rr: float = 2.5,
) -> dict[str, Any] | None:
    normalized = normalize_event(event)

    events = load_json(EVENTS_PATH, [])
    if not isinstance(events, list):
        events = []

    existing_keys = {event_key(item) for item in events if isinstance(item, dict)}
    current_key = event_key(normalized)

    candidate_reports = []

    for previous in events:
        if not isinstance(previous, dict):
            continue

        if safe_text(previous.get("symbol")).upper() != normalized["symbol"]:
            continue

        if safe_text(previous.get("setup_id")) and safe_text(previous.get("setup_id")) == normalized["setup_id"]:
            continue

        report = resolve_setup_conflict(
            previous,
            normalized,
            max_minutes=max_minutes,
            max_entry_distance=max_entry_distance,
            min_conflict_rr=min_conflict_rr,
        )

        if report.get("conflict_detected"):
            candidate_reports.append(report)

    if current_key not in existing_keys:
        events.append(normalized)
        events = events[-MAX_EVENTS:]
        write_json(EVENTS_PATH, events)

    if not candidate_reports:
        return None

    candidate_reports.sort(
        key=lambda item: (
            bool(item.get("priority_conflict_review")),
            -safe_float((item.get("conflict_metrics") or {}).get("entry_distance"), 999999),
        ),
        reverse=True,
    )

    selected = candidate_reports[0]
    selected["symbol"] = normalized["symbol"]
    selected["new_event_key"] = current_key
    selected["reported_at"] = now_iso()
    selected["duplicate_conflict"] = False

    conflicts = load_json(CONFLICTS_PATH, [])
    if not isinstance(conflicts, list):
        conflicts = []

    selected_key = conflict_key(selected)
    existing_conflict_keys = {
        safe_text(item.get("conflict_key"))
        for item in conflicts
        if isinstance(item, dict)
    }

    selected["conflict_key"] = selected_key

    if selected_key in existing_conflict_keys:
        selected["duplicate_conflict"] = True
        write_json(LATEST_CONFLICT_PATH, selected)
        return selected

    conflicts.append(selected)
    conflicts = conflicts[-MAX_EVENTS:]

    write_json(CONFLICTS_PATH, conflicts)
    write_json(LATEST_CONFLICT_PATH, selected)
    append_jsonl(CONFLICTS_JSONL_PATH, selected)

    return selected


def format_conflict_telegram_message(report: dict[str, Any]) -> str:
    previous_setup = report.get("previous_setup") or {}
    new_setup = report.get("new_setup") or {}
    metrics = report.get("conflict_metrics") or {}
    matrix = report.get("strategy_family_matrix") or {}

    return (
        "⚠️ PHASE 5AH SETUP CONFLICT\n"
        "Mode: OBSERVE ONLY\n"
        "Trade Action: WAIT / MANUAL REVIEW\n"
        "Auto Trade: NO\n\n"
        f"Status: {report.get('conflict_status')}\n"
        f"Priority Review: {report.get('priority_conflict_review')}\n"
        f"Symbol: {report.get('symbol', 'XAUUSD')}\n\n"
        "Strategy-Family Matrix:\n"
        f"- Pair: {matrix.get('pair')}\n"
        f"- Rule: {matrix.get('rule')}\n"
        f"- Preferred confirmation: {matrix.get('preferred_confirmation')}\n"
        f"- Priority side: {matrix.get('priority_side')}\n\n"
        "Previous Setup:\n"
        f"- {previous_setup.get('strategy')} {previous_setup.get('direction')}\n"
        f"- Family: {previous_setup.get('family')}\n"
        f"- Entry: {previous_setup.get('entry')}\n"
        f"- Score: {previous_setup.get('score')}\n"
        f"- RR: {previous_setup.get('rr')}\n"
        f"- State: {previous_setup.get('state')}\n"
        f"- Action: {previous_setup.get('action')}\n\n"
        "New Setup:\n"
        f"- {new_setup.get('strategy')} {new_setup.get('direction')}\n"
        f"- Family: {new_setup.get('family')}\n"
        f"- Entry: {new_setup.get('entry')}\n"
        f"- Score: {new_setup.get('score')} / Required: {new_setup.get('min_required_score')}\n"
        f"- RR: {new_setup.get('rr')}\n"
        f"- State: {new_setup.get('state')}\n"
        f"- Action: {new_setup.get('action')}\n\n"
        "Conflict Metrics:\n"
        f"- Time gap: {metrics.get('time_gap_minutes')} min\n"
        f"- Entry distance: {metrics.get('entry_distance')}\n"
        f"- Same zone: {metrics.get('same_zone')}\n\n"
        "Rule:\n"
        "Do not silently discard strong MICRO_SR_SWEEP_RECLAIM conflicts.\n"
        "Daily pivot = context only, not a hard block.\n"
        "Order flow = optional confirmation layer, not required for conflict detection."
    )
