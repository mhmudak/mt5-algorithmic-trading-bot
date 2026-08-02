
from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json

from src.market_outlook_advisor import (
    PHASE as ADVISOR_PHASE,
    evaluate_setup_against_outlook,
    format_outlook_advisory_telegram,
)

from src.market_outlook_engine import load_latest_market_outlook


PHASE = "PHASE_6S5_OUTLOOK_ADVISORY_BRIDGE_CORE"
STATE_DIR = Path("data/reports/market_outlook/advisory_bridge_state")


def _safe_symbol(symbol: str) -> str:
    return str(symbol).replace("/", "_").replace("\\", "_").replace(".", "_")


def advisory_state_path(symbol: str, report_type: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{_safe_symbol(symbol)}_{report_type}_advisory_bridge_state.json"


def load_advisory_state(symbol: str, report_type: str) -> dict[str, Any]:
    path = advisory_state_path(symbol, report_type)

    if not path.exists():
        return {"sent_fingerprints": {}}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"sent_fingerprints": {}}

    if not isinstance(data.get("sent_fingerprints"), dict):
        data["sent_fingerprints"] = {}

    return data


def save_advisory_state(symbol: str, report_type: str, state: dict[str, Any]) -> Path:
    path = advisory_state_path(symbol, report_type)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def setup_direction(setup: dict[str, Any]) -> str:
    return str(setup.get("signal") or setup.get("direction") or "").upper()


def setup_identity(setup: dict[str, Any]) -> dict[str, Any]:
    return {
        "setup_id": setup.get("setup_id") or setup.get("id"),
        "strategy": setup.get("strategy"),
        "direction": setup_direction(setup),
        "entry": setup.get("entry_reference", setup.get("entry")),
        "sl": setup.get("sl_reference", setup.get("sl")),
        "tp": setup.get("tp_reference", setup.get("tp")),
        "rr": setup.get("rr", setup.get("risk_reward")),
    }


def advisory_fingerprint(
    *,
    setup: dict[str, Any],
    outlook: dict[str, Any],
    advisory: dict[str, Any],
) -> str:
    payload = {
        "setup": setup_identity(setup),
        "outlook": {
            "symbol": outlook.get("symbol"),
            "report_type": outlook.get("report_type"),
            "fingerprint": outlook.get("fingerprint"),
            "leader": advisory.get("outlook_leader"),
            "range_zone": advisory.get("outlook_range_zone"),
            "scenario_closer": advisory.get("outlook_scenario_closer"),
            "risk_level": advisory.get("risk_level"),
            "alignment": advisory.get("alignment"),
        },
    }

    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_outlook_advisory_bridge_result(
    *,
    setup: dict[str, Any],
    symbol: str = "XAUUSD",
    report_type: str = "scenario_update",
    outlook: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if outlook is None:
        outlook = load_latest_market_outlook(symbol, report_type)

    if not outlook:
        return {
            "phase": PHASE,
            "ready": False,
            "reason": "latest_market_outlook_not_found",
            "symbol": symbol,
            "report_type": report_type,
            "setup_identity": setup_identity(setup),
            "decision_impact": "NONE",
            "auto_trade_allowed": False,
            "can_execute": False,
            "can_block_trade": False,
            "can_modify_risk": False,
        }

    advisory = evaluate_setup_against_outlook(setup, outlook)
    message = format_outlook_advisory_telegram(advisory)
    fingerprint = advisory_fingerprint(setup=setup, outlook=outlook, advisory=advisory)

    return {
        "phase": PHASE,
        "ready": True,
        "advisor_phase": ADVISOR_PHASE,
        "symbol": symbol,
        "report_type": report_type,
        "setup_identity": setup_identity(setup),
        "advisory_fingerprint": fingerprint,
        "risk_level": advisory.get("risk_level"),
        "alignment": advisory.get("alignment"),
        "manual_action": advisory.get("manual_action"),
        "advisory": advisory,
        "message": message,
        "decision_impact": "ADVISORY_ONLY",
        "auto_trade_allowed": False,
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_risk": False,
    }


def should_send_advisory(
    *,
    state: dict[str, Any],
    fingerprint: str,
    force_send: bool = False,
) -> bool:
    if force_send:
        return True

    sent = state.get("sent_fingerprints") or {}
    return fingerprint not in sent


def mark_advisory_sent(
    *,
    state: dict[str, Any],
    fingerprint: str,
    result: dict[str, Any],
    sent_at: str | None = None,
) -> dict[str, Any]:
    if "sent_fingerprints" not in state or not isinstance(state["sent_fingerprints"], dict):
        state["sent_fingerprints"] = {}

    state["sent_fingerprints"][fingerprint] = {
        "sent_at": sent_at,
        "risk_level": result.get("risk_level"),
        "alignment": result.get("alignment"),
        "setup_identity": result.get("setup_identity"),
    }

    state["last_advisory_fingerprint"] = fingerprint
    state["last_risk_level"] = result.get("risk_level")
    state["last_alignment"] = result.get("alignment")

    return state
