
from __future__ import annotations

from typing import Any


PHASE = "PHASE_6S2_SCENARIO_CHANGE_WATCHER"


def _safe_get(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data

    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)

    return current


def _scenario_snapshot(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario_id": scenario.get("scenario_id"),
        "title": scenario.get("title"),
        "direction": scenario.get("direction"),
        "level": scenario.get("level"),
        "status": scenario.get("status"),
        "maturity_score": scenario.get("maturity_score"),
        "action_state": scenario.get("action_state"),
        "can_become_setup": scenario.get("can_become_setup"),
    }


def outlook_watch_snapshot(outlook: dict[str, Any]) -> dict[str, Any]:
    maturity = outlook.get("scenario_maturity") or {}
    nearest = outlook.get("nearest_liquidity") or {}

    scenarios = [
        _scenario_snapshot(item)
        for item in outlook.get("likely_scenarios", [])
    ]

    return {
        "phase": PHASE,
        "symbol": outlook.get("symbol"),
        "report_type": outlook.get("report_type"),
        "last_price": outlook.get("last_price"),
        "combined_htf_bias": outlook.get("combined_htf_bias"),
        "range_zone": outlook.get("range_zone"),
        "scenario_closer": outlook.get("scenario_closer"),
        "scenario_leader": maturity.get("leader"),
        "buy_score": _safe_get(maturity, "BUY", "score"),
        "buy_state": _safe_get(maturity, "BUY", "state"),
        "sell_score": _safe_get(maturity, "SELL", "score"),
        "sell_state": _safe_get(maturity, "SELL", "state"),
        "nearest_buy_label": _safe_get(nearest, "buy", "label"),
        "nearest_buy_price": _safe_get(nearest, "buy", "price"),
        "nearest_buy_distance": _safe_get(nearest, "buy", "distance"),
        "nearest_sell_label": _safe_get(nearest, "sell", "label"),
        "nearest_sell_price": _safe_get(nearest, "sell", "price"),
        "nearest_sell_distance": _safe_get(nearest, "sell", "distance"),
        "news_status": _safe_get(outlook.get("news_filter") or {}, "status"),
        "scenarios": scenarios,
        "triggering_scenarios": [
            item
            for item in scenarios
            if item.get("status") == "AT_TRIGGER_ZONE"
            or item.get("action_state") in {
                "AT_TRIGGER_ZONE",
                "CONFIRMATION_PENDING",
                "SETUP_POSSIBLE_IF_CONFIRMATION_APPEARS",
            }
        ],
    }


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def detect_outlook_changes(
    previous_snapshot: dict[str, Any] | None,
    current_outlook: dict[str, Any],
    *,
    score_delta_threshold: int = 10,
) -> dict[str, Any]:
    current = outlook_watch_snapshot(current_outlook)
    reasons: list[str] = []

    if not previous_snapshot:
        reasons.append("new_scenario_watch_baseline")
        return {
            "phase": PHASE,
            "changed": True,
            "severity": "BASELINE",
            "reasons": reasons,
            "previous_snapshot": previous_snapshot,
            "current_snapshot": current,
        }

    watched_fields = [
        "combined_htf_bias",
        "range_zone",
        "scenario_closer",
        "scenario_leader",
        "buy_state",
        "sell_state",
        "nearest_buy_label",
        "nearest_sell_label",
        "news_status",
    ]

    for field in watched_fields:
        if previous_snapshot.get(field) != current.get(field):
            reasons.append(
                f"{field}_changed: {previous_snapshot.get(field)} -> {current.get(field)}"
            )

    for side in ["buy", "sell"]:
        old_score = _num(previous_snapshot.get(f"{side}_score"))
        new_score = _num(current.get(f"{side}_score"))

        if old_score is None or new_score is None:
            continue

        delta = new_score - old_score

        if abs(delta) >= score_delta_threshold:
            reasons.append(
                f"{side.upper()}_maturity_delta: {old_score:.0f} -> {new_score:.0f}"
            )

    previous_trigger_ids = {
        item.get("scenario_id")
        for item in previous_snapshot.get("triggering_scenarios", [])
    }
    current_trigger_ids = {
        item.get("scenario_id")
        for item in current.get("triggering_scenarios", [])
    }

    new_triggers = sorted(current_trigger_ids - previous_trigger_ids)

    for scenario_id in new_triggers:
        reasons.append(f"scenario_entered_trigger_or_confirmation_state: {scenario_id}")

    severity = "NONE"

    if reasons:
        severity = "INFO"

    if any("scenario_leader_changed" in item for item in reasons):
        severity = "MEDIUM"

    if any("scenario_entered_trigger_or_confirmation_state" in item for item in reasons):
        severity = "HIGH"

    if any(
        "CONFIRMATION_PENDING" in str(item)
        for item in current.get("triggering_scenarios", [])
    ):
        severity = "HIGH"

    return {
        "phase": PHASE,
        "changed": bool(reasons),
        "severity": severity,
        "reasons": reasons,
        "previous_snapshot": previous_snapshot,
        "current_snapshot": current,
    }


def format_outlook_change_telegram(
    current_outlook: dict[str, Any],
    change: dict[str, Any],
) -> str:
    current = change.get("current_snapshot") or outlook_watch_snapshot(current_outlook)
    reasons = change.get("reasons") or []

    lines = [
        "🔔 PHASE 6S2 OUTLOOK CHANGE WATCH",
        f"Symbol: {current.get('symbol')}",
        f"Report Type: {current.get('report_type')}",
        f"Severity: {change.get('severity')}",
        "",
        f"Last Price: {current.get('last_price')}",
        f"HTF Bias: {current.get('combined_htf_bias')}",
        f"Range Zone: {current.get('range_zone')}",
        f"Scenario Closer: {current.get('scenario_closer')}",
        f"Scenario Leader: {current.get('scenario_leader')}",
        "",
        f"BUY Maturity: {current.get('buy_score')} / 100 | State: {current.get('buy_state')}",
        f"SELL Maturity: {current.get('sell_score')} / 100 | State: {current.get('sell_state')}",
        "",
        f"Nearest BUY Liquidity: {current.get('nearest_buy_label')} @ {current.get('nearest_buy_price')} distance={current.get('nearest_buy_distance')}",
        f"Nearest SELL Liquidity: {current.get('nearest_sell_label')} @ {current.get('nearest_sell_price')} distance={current.get('nearest_sell_distance')}",
        "",
        "What Changed:",
    ]

    if reasons:
        for reason in reasons[:10]:
            lines.append(f"- {reason}")
    else:
        lines.append("- No material scenario change.")

    triggering = current.get("triggering_scenarios") or []

    if triggering:
        lines += [
            "",
            "Trigger / Confirmation Watch:",
        ]

        for scenario in triggering[:5]:
            lines.append(
                f"- {scenario.get('direction')} {scenario.get('title')} | "
                f"status={scenario.get('status')} | "
                f"state={scenario.get('action_state')} | "
                f"maturity={scenario.get('maturity_score')}"
            )

    lines += [
        "",
        "Decision Impact: NONE",
        "Auto Trade Allowed: False",
        "Execution: NO — existing setup confirmation rules still required.",
    ]

    return "\n".join(lines)
