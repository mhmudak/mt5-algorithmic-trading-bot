from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence

from src.intrabar_opposite_direction_guard import is_intrabar_trade_plan, normalize_signal


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()


def _matches_rule_value(rule_value: Any, actual_value: Any) -> bool:
    rule = _norm(rule_value)
    actual = _norm(actual_value)

    if rule in {"", "*", "ANY"}:
        return True

    return rule == actual


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def evaluate_intrabar_subprofile_risk_guard(
    *,
    signal: Any,
    trade_plan: Any,
    enabled: bool = True,
    block_rules: Optional[Iterable[Sequence[Any]]] = None,
) -> Dict[str, Any]:
    if not enabled:
        return {
            "allowed": True,
            "reason": "guard_disabled",
            "matched_rule": None,
        }

    plan = _as_dict(trade_plan)

    if not is_intrabar_trade_plan(plan):
        return {
            "allowed": True,
            "reason": "not_intrabar_trade_plan",
            "matched_rule": None,
        }

    candidate = {
        "strategy": plan.get("strategy"),
        "signal": normalize_signal(signal) or normalize_signal(plan.get("signal")),
        "session": plan.get("session"),
        "market_condition": plan.get("market_condition"),
        "entry_model": plan.get("entry_model"),
        "setup_id": plan.get("setup_id"),
    }

    for raw_rule in block_rules or ():
        try:
            rule = tuple(raw_rule)
        except TypeError:
            continue

        if len(rule) < 4:
            continue

        strategy_rule = rule[0]
        signal_rule = rule[1]
        session_rule = rule[2]
        market_rule = rule[3]
        reason = rule[4] if len(rule) >= 5 else "blocked_intrabar_subprofile"

        if not _matches_rule_value(strategy_rule, candidate["strategy"]):
            continue

        if not _matches_rule_value(signal_rule, candidate["signal"]):
            continue

        if not _matches_rule_value(session_rule, candidate["session"]):
            continue

        if not _matches_rule_value(market_rule, candidate["market_condition"]):
            continue

        return {
            "allowed": False,
            "reason": "intrabar_subprofile_risk_blocked",
            "matched_rule": {
                "strategy": _norm(strategy_rule),
                "signal": _norm(signal_rule),
                "session": _norm(session_rule),
                "market_condition": _norm(market_rule),
                "rule_reason": str(reason),
            },
            "candidate": candidate,
        }

    return {
        "allowed": True,
        "reason": "intrabar_subprofile_allowed",
        "matched_rule": None,
        "candidate": candidate,
    }
