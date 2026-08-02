
from __future__ import annotations

from typing import Any


PHASE = "PHASE_6S4_OUTLOOK_ADVISORY_MODE"


def _upper(value: Any) -> str:
    return str(value or "").upper()


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _maturity(outlook: dict[str, Any], side: str) -> dict[str, Any]:
    return ((outlook.get("scenario_maturity") or {}).get(side.upper()) or {})


def _scenario_leader(outlook: dict[str, Any]) -> str:
    return _upper((outlook.get("scenario_maturity") or {}).get("leader"))


def _nearest_label(outlook: dict[str, Any], side: str) -> str | None:
    nearest = outlook.get("nearest_liquidity") or {}
    item = nearest.get(side.lower()) or {}
    return item.get("label")


def _nearest_distance(outlook: dict[str, Any], side: str) -> float | None:
    nearest = outlook.get("nearest_liquidity") or {}
    item = nearest.get(side.lower()) or {}
    return _num(item.get("distance"))


def _direction_score(outlook: dict[str, Any], direction: str) -> float:
    maturity = _maturity(outlook, direction)
    score = _num(maturity.get("score"))
    return score if score is not None else 0.0


def _opposite(direction: str) -> str:
    if direction == "BUY":
        return "SELL"
    if direction == "SELL":
        return "BUY"
    return "NONE"


def evaluate_setup_against_outlook(
    setup: dict[str, Any],
    outlook: dict[str, Any],
    *,
    strong_maturity: int = 65,
    weak_maturity_gap: int = 15,
) -> dict[str, Any]:
    direction = _upper(setup.get("signal") or setup.get("direction"))
    strategy = setup.get("strategy")
    setup_id = setup.get("setup_id") or setup.get("id")
    rr = setup.get("rr", setup.get("risk_reward"))
    entry = setup.get("entry_reference", setup.get("entry"))
    sl = setup.get("sl_reference", setup.get("sl"))
    tp = setup.get("tp_reference", setup.get("tp"))

    leader = _scenario_leader(outlook)
    opposite = _opposite(direction)

    direction_score = _direction_score(outlook, direction)
    opposite_score = _direction_score(outlook, opposite)

    direction_state = _upper(_maturity(outlook, direction).get("state"))
    opposite_state = _upper(_maturity(outlook, opposite).get("state"))

    range_zone = _upper(outlook.get("range_zone"))
    htf_bias = _upper(outlook.get("combined_htf_bias"))
    scenario_closer = _upper(outlook.get("scenario_closer"))

    reasons: list[str] = []
    warnings: list[str] = []
    confirmations_needed: list[str] = []

    alignment = "UNKNOWN"
    risk_level = "MEDIUM"
    manual_action = "Manual review required before any entry."

    if direction not in {"BUY", "SELL"}:
        alignment = "INVALID_DIRECTION"
        risk_level = "HIGH"
        warnings.append("Setup direction is missing or invalid.")
        manual_action = "Do not enter. Direction is not valid."
    elif leader == direction:
        alignment = "ALIGNED_WITH_OUTLOOK_LEADER"
        risk_level = "LOW"
        reasons.append(f"Setup direction {direction} matches outlook leader {leader}.")
    elif leader in {"BUY", "SELL"} and leader != direction:
        alignment = "AGAINST_OUTLOOK_LEADER"
        risk_level = "HIGH"
        warnings.append(f"Setup direction {direction} is opposite outlook leader {leader}.")
    else:
        alignment = "NO_CLEAR_OUTLOOK_LEADER"
        risk_level = "MEDIUM"
        warnings.append("Outlook leader is not clear.")

    if direction_score >= strong_maturity:
        reasons.append(f"{direction} scenario maturity is strong: {direction_score:.0f}/100.")
    else:
        warnings.append(f"{direction} scenario maturity is not strong: {direction_score:.0f}/100.")

    if opposite in {"BUY", "SELL"} and opposite_score - direction_score >= weak_maturity_gap:
        risk_level = "HIGH"
        warnings.append(
            f"Opposite {opposite} maturity is stronger: {opposite_score:.0f}/100 vs {direction_score:.0f}/100."
        )

    if direction == "BUY" and range_zone == "PREMIUM_RESISTANCE_SIDE":
        risk_level = "HIGH"
        warnings.append("BUY setup is in premium/resistance side; chasing risk.")
    elif direction == "SELL" and range_zone == "DISCOUNT_SUPPORT_SIDE":
        risk_level = "HIGH"
        warnings.append("SELL setup is in discount/support side; chasing risk.")

    if range_zone == "MIDDLE_OF_RANGE":
        risk_level = "HIGH"
        warnings.append("Price is in middle of range; lower-quality setup zone.")

    if "BULLISH" in htf_bias and direction == "BUY":
        reasons.append("HTF bias supports BUY direction.")
    elif "BEARISH" in htf_bias and direction == "SELL":
        reasons.append("HTF bias supports SELL direction.")
    elif "BULLISH" in htf_bias and direction == "SELL":
        warnings.append("SELL setup is against bullish HTF bias.")
    elif "BEARISH" in htf_bias and direction == "BUY":
        warnings.append("BUY setup is against bearish HTF bias.")

    if direction_state in {"CONFIRMATION_PENDING", "AT_TRIGGER_ZONE", "SETUP_POSSIBLE_IF_CONFIRMATION_APPEARS"}:
        reasons.append(f"{direction} scenario state is active: {direction_state}.")
    else:
        confirmations_needed.append(f"Wait for {direction} scenario state to improve; current state is {direction_state or 'UNKNOWN'}.")

    confirmations_needed += [
        "M15/M5 confirmation must be present.",
        "Entry, SL, TP, and RR must remain valid.",
        "Spread/slippage/news risk must be acceptable.",
        "Do not use this advisory as execution permission.",
    ]

    if risk_level == "LOW":
        manual_action = "Setup is outlook-aligned. You may review it manually, but normal confirmation/risk rules still decide."
    elif risk_level == "MEDIUM":
        manual_action = "Be selective. Only consider if confirmation is clean and RR is strong."
    else:
        manual_action = "Avoid blind entry. Treat as dangerous unless fresh M15/M5 confirmation fully overrides the warning."

    return {
        "phase": PHASE,
        "setup_id": setup_id,
        "strategy": strategy,
        "setup_direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rr": rr,
        "outlook_symbol": outlook.get("symbol"),
        "outlook_report_type": outlook.get("report_type"),
        "outlook_last_price": outlook.get("last_price"),
        "outlook_htf_bias": outlook.get("combined_htf_bias"),
        "outlook_range_zone": outlook.get("range_zone"),
        "outlook_scenario_closer": outlook.get("scenario_closer"),
        "outlook_leader": leader,
        "setup_direction_maturity": direction_score,
        "opposite_direction": opposite,
        "opposite_direction_maturity": opposite_score,
        "setup_direction_state": direction_state,
        "opposite_direction_state": opposite_state,
        "nearest_buy_liquidity": _nearest_label(outlook, "buy"),
        "nearest_buy_distance": _nearest_distance(outlook, "buy"),
        "nearest_sell_liquidity": _nearest_label(outlook, "sell"),
        "nearest_sell_distance": _nearest_distance(outlook, "sell"),
        "alignment": alignment,
        "risk_level": risk_level,
        "reasons": reasons,
        "warnings": warnings,
        "confirmations_needed": confirmations_needed,
        "manual_action": manual_action,
        "decision_impact": "ADVISORY_ONLY",
        "auto_trade_allowed": False,
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_risk": False,
    }


def format_outlook_advisory_telegram(advisory: dict[str, Any]) -> str:
    risk = advisory.get("risk_level")
    icon = "🟢" if risk == "LOW" else "🟡" if risk == "MEDIUM" else "🔴"

    if risk == "LOW":
        verdict = "OUTLOOK ALIGNED — REVIEW NORMALLY"
        manual_priority = "OK TO REVIEW, BUT NOT EXECUTION PERMISSION"
    elif risk == "MEDIUM":
        verdict = "CAUTION — WAIT FOR CLEAN CONFIRMATION"
        manual_priority = "BE SELECTIVE"
    else:
        verdict = "HIGH RISK — AVOID BLIND ENTRY"
        manual_priority = "WAIT / DO NOT ENTER BLINDLY"

    setup_direction = advisory.get("setup_direction")
    strategy = advisory.get("strategy")
    alignment = advisory.get("alignment")

    lines = [
        f"{icon} PHASE 6S4 OUTLOOK ADVISORY — MANUAL REVIEW",
        "",
        f"FINAL ADVISORY: {verdict}",
        f"MANUAL ACTION: {manual_priority}",
        "",
        f"Setup: {setup_direction} {strategy}",
        f"Setup ID: {advisory.get('setup_id')}",
        f"Entry: {advisory.get('entry')} | SL: {advisory.get('sl')} | TP: {advisory.get('tp')} | RR: {advisory.get('rr')}",
        "",
        "Outlook Match:",
        f"- Outlook Leader: {advisory.get('outlook_leader')}",
        f"- Setup Direction: {setup_direction}",
        f"- Alignment: {alignment}",
        f"- Risk: {risk}",
        "",
        "Market Context:",
        f"- HTF Bias: {advisory.get('outlook_htf_bias')}",
        f"- Range Zone: {advisory.get('outlook_range_zone')}",
        f"- Scenario Closer: {advisory.get('outlook_scenario_closer')}",
        "",
        "Scenario Strength:",
        f"- {setup_direction} Maturity: {advisory.get('setup_direction_maturity')} / 100 | State: {advisory.get('setup_direction_state')}",
        f"- {advisory.get('opposite_direction')} Maturity: {advisory.get('opposite_direction_maturity')} / 100 | State: {advisory.get('opposite_direction_state')}",
        "",
        "Nearest Liquidity:",
        f"- BUY side: {advisory.get('nearest_buy_liquidity')} distance={advisory.get('nearest_buy_distance')}",
        f"- SELL side: {advisory.get('nearest_sell_liquidity')} distance={advisory.get('nearest_sell_distance')}",
        "",
        "Positive Factors:",
    ]

    reasons = advisory.get("reasons") or []
    if reasons:
        for item in reasons:
            lines.append(f"- {item}")
    else:
        lines.append("- None.")

    warnings = advisory.get("warnings") or []
    if warnings:
        lines += ["", "Risk Warnings:"]
        for item in warnings:
            lines.append(f"- {item}")

    confirmations = advisory.get("confirmations_needed") or []
    if confirmations:
        lines += ["", "Required Before Any Manual Entry:"]
        for item in confirmations:
            lines.append(f"- {item}")

    lines += [
        "",
        "Clear Meaning:",
    ]

    if risk == "HIGH":
        lines += [
            "- This is NOT a trade approval.",
            "- The setup may still work, but the outlook says risk is elevated.",
            "- Only fresh M15/M5 confirmation can justify manual review.",
        ]
    elif risk == "MEDIUM":
        lines += [
            "- The setup is not clean enough to trust blindly.",
            "- Wait for confirmation and strong RR.",
        ]
    else:
        lines += [
            "- The setup agrees with the current outlook.",
            "- Still wait for normal strategy confirmation and risk checks.",
        ]

    lines += [
        "",
        "Decision Impact: ADVISORY ONLY",
        "Auto Trade Allowed: False",
        "Can Block Trade: False",
        "Execution: NO",
    ]

    return "\n".join(lines)

