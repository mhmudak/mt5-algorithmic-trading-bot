from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
import json

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


def _get_account_key_safe() -> str:
    try:
        from src.account_context import get_account_key

        return str(get_account_key())
    except Exception:
        return "Tickmill-Demo_25323531"


def _resolve_dynamic_rules_path(raw_path: Any) -> Path:
    path_text = str(raw_path or "")
    if "{account_key}" in path_text:
        path_text = path_text.format(account_key=_get_account_key_safe())
    return Path(path_text)


def _rule_from_dict(item: Dict[str, Any]) -> Optional[Sequence[Any]]:
    strategy = item.get("strategy")
    signal = item.get("signal")
    session = item.get("session")
    market_condition = item.get("market_condition") or "*"
    reason = item.get("rule_reason") or item.get("reason") or "dynamic_intrabar_subprofile_block"

    if not strategy or not signal or not session:
        return None

    return (
        strategy,
        signal,
        session,
        market_condition,
        reason,
    )


def load_dynamic_intrabar_subprofile_block_rules() -> List[Sequence[Any]]:
    try:
        from config import settings
    except Exception:
        return []

    if not bool(getattr(settings, "ENABLE_DYNAMIC_INTRABAR_SUBPROFILE_RISK_RULES", False)):
        return []

    path = _resolve_dynamic_rules_path(
        getattr(
            settings,
            "DYNAMIC_INTRABAR_SUBPROFILE_RULES_FILE",
            "data/strategy_intelligence/{account_key}/intrabar_subprofile_block_rules.json",
        )
    )

    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    raw_rules = data.get("rules") if isinstance(data, dict) else data

    if not isinstance(raw_rules, list):
        return []

    rules: List[Sequence[Any]] = []

    for item in raw_rules:
        if isinstance(item, dict):
            rule = _rule_from_dict(item)
            if rule:
                rules.append(rule)
        elif isinstance(item, (list, tuple)) and len(item) >= 4:
            rules.append(tuple(item))

    return rules


def get_effective_intrabar_subprofile_block_rules(
    static_rules: Optional[Iterable[Sequence[Any]]] = None,
) -> List[Sequence[Any]]:
    dynamic_rules = load_dynamic_intrabar_subprofile_block_rules()

    if dynamic_rules:
        return dynamic_rules

    try:
        from config import settings

        static_fallback = bool(
            getattr(settings, "DYNAMIC_INTRABAR_SUBPROFILE_STATIC_FALLBACK", True)
        )
    except Exception:
        static_fallback = True

    if not static_fallback:
        return []

    return list(static_rules or ())


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

    effective_rules = get_effective_intrabar_subprofile_block_rules(block_rules)

    for raw_rule in effective_rules:
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
            "dynamic_rules_loaded": bool(load_dynamic_intrabar_subprofile_block_rules()),
        }

    return {
        "allowed": True,
        "reason": "intrabar_subprofile_allowed",
        "matched_rule": None,
        "candidate": candidate,
        "dynamic_rules_loaded": bool(load_dynamic_intrabar_subprofile_block_rules()),
    }
