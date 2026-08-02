from __future__ import annotations

from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from src.market_outlook_advisory_bridge import (
    build_outlook_advisory_bridge_result,
    load_advisory_state,
    mark_advisory_sent,
    save_advisory_state,
    should_send_advisory,
)


PHASE = "PHASE_6S6_OUTLOOK_ADVISORY_RUNTIME_HOOK"


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _normalize_direction(value: Any) -> str:
    text = str(value or "").upper().strip()

    if text in {"BUY", "LONG", "BULLISH"}:
        return "BUY"

    if text in {"SELL", "SHORT", "BEARISH"}:
        return "SELL"

    return text


def normalize_signal_setup_for_outlook_advisory(raw_setup: dict[str, Any]) -> dict[str, Any]:
    direction = _normalize_direction(
        _first(raw_setup, "signal", "direction", "side", "action", "order_type")
    )

    return {
        "setup_id": _first(raw_setup, "setup_id", "id", "signal_id", "trade_id", "position_id"),
        "strategy": _first(raw_setup, "strategy", "strategy_name", "setup_source", "setup_type"),
        "signal": direction,
        "entry_reference": _first(raw_setup, "entry_reference", "entry", "entry_price", "price", "close"),
        "sl_reference": _first(raw_setup, "sl_reference", "sl", "stop_loss", "sl_price"),
        "tp_reference": _first(raw_setup, "tp_reference", "tp", "take_profit", "tp1", "target"),
        "rr": _first(raw_setup, "rr", "risk_reward", "rr_ratio", "reward_risk"),
        "raw_setup": raw_setup,
    }


def build_runtime_outlook_advisory(
    *,
    raw_setup: dict[str, Any],
    symbol: str = "XAUUSD",
    report_type: str = "scenario_update",
    outlook: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_setup = normalize_signal_setup_for_outlook_advisory(raw_setup)

    result = build_outlook_advisory_bridge_result(
        setup=normalized_setup,
        symbol=symbol,
        report_type=report_type,
        outlook=outlook,
    )

    result["runtime_phase"] = PHASE
    result["normalized_setup"] = normalized_setup

    return result


def maybe_send_runtime_outlook_advisory(
    *,
    raw_setup: dict[str, Any],
    symbol: str = "XAUUSD",
    report_type: str = "scenario_update",
    enabled: bool = False,
    send_telegram: bool = False,
    force_send: bool = False,
    notifier: Callable[[str], bool] | None = None,
    outlook: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    persist_state: bool = True,
) -> dict[str, Any]:
    result = build_runtime_outlook_advisory(
        raw_setup=raw_setup,
        symbol=symbol,
        report_type=report_type,
        outlook=outlook,
    )

    summary: dict[str, Any] = {
        "phase": PHASE,
        "ready": result.get("ready"),
        "enabled": enabled,
        "send_telegram": send_telegram,
        "force_send": force_send,
        "symbol": symbol,
        "report_type": report_type,
        "risk_level": result.get("risk_level"),
        "alignment": result.get("alignment"),
        "advisory_fingerprint": result.get("advisory_fingerprint"),
        "should_notify": False,
        "telegram_sent": False,
        "state_file": None,
        "reason": None,
        "decision_impact": result.get("decision_impact", "NONE"),
        "auto_trade_allowed": False,
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_risk": False,
        "result": result,
    }

    if not enabled:
        summary["reason"] = "runtime_advisory_disabled"
        return summary

    if not result.get("ready"):
        summary["reason"] = result.get("reason", "advisory_not_ready")
        return summary

    if state is None:
        state = load_advisory_state(symbol, report_type)

    fingerprint = result["advisory_fingerprint"]

    should_notify = should_send_advisory(
        state=state,
        fingerprint=fingerprint,
        force_send=force_send,
    )

    summary["should_notify"] = should_notify

    if send_telegram and should_notify:
        if notifier is None:
            summary["reason"] = "notifier_missing"
        else:
            telegram_sent = bool(notifier(result["message"]))
            summary["telegram_sent"] = telegram_sent

            if telegram_sent:
                state = mark_advisory_sent(
                    state=state,
                    fingerprint=fingerprint,
                    result=result,
                    sent_at=datetime.now(ZoneInfo("Asia/Beirut")).isoformat(timespec="seconds"),
                )

    elif not should_notify:
        summary["reason"] = "duplicate_advisory_fingerprint"
    elif not send_telegram:
        summary["reason"] = "telegram_send_disabled"

    state["last_runtime_checked_at"] = datetime.now(ZoneInfo("Asia/Beirut")).isoformat(timespec="seconds")
    state["last_runtime_ready"] = result.get("ready")
    state["last_runtime_should_notify"] = should_notify
    state["last_runtime_risk_level"] = result.get("risk_level")
    state["last_runtime_alignment"] = result.get("alignment")

    if persist_state:
        state_file = save_advisory_state(symbol, report_type, state)
        summary["state_file"] = str(state_file)

    return summary
