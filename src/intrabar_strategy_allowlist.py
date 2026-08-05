
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple


PHASE = "PHASE_6U1_INTRABAR_STRATEGY_ALLOWLIST"


def normalize_intrabar_strategy_name(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (list, tuple, set)):
        value = next((item for item in value if item), "")

    return str(value).strip().upper()


def normalize_intrabar_allowlist(allowlist: Optional[Iterable[Any]]) -> Tuple[str, ...]:
    if not allowlist:
        return tuple()

    normalized = []

    for item in allowlist:
        name = normalize_intrabar_strategy_name(item)
        if name:
            normalized.append(name)

    return tuple(dict.fromkeys(normalized))


def pick_intrabar_strategy_name(*payloads: Any) -> str:
    keys = (
        "strategy",
        "strategy_name",
        "setup_source",
        "setup_type",
        "name",
        "profile_name",
    )

    for payload in payloads:
        if not isinstance(payload, dict):
            continue

        for key in keys:
            value = payload.get(key)
            if value:
                return normalize_intrabar_strategy_name(value)

    for payload in payloads:
        if isinstance(payload, str):
            return normalize_intrabar_strategy_name(payload)

    return ""

def is_intrabar_scope(*payloads: Any) -> bool:
    intrabar_keys = (
        "source_bucket",
        "setup_source_bucket",
        "bucket",
        "execution_bucket",
        "setup_source",
        "setup_type",
        "signal_type",
        "profile_name",
        "detection_mode",
        "strategy_family",
        "event",
        "status",
    )

    for payload in payloads:
        if isinstance(payload, dict):
            for key in intrabar_keys:
                value = payload.get(key)
                if value is not None and "INTRABAR" in str(value).upper():
                    return True

            tags = payload.get("tags")
            if isinstance(tags, (list, tuple, set)):
                if any("INTRABAR" in str(tag).upper() for tag in tags):
                    return True

            if isinstance(tags, str) and "INTRABAR" in tags.upper():
                return True

        elif payload is not None and "INTRABAR" in str(payload).upper():
            return True

    return False



def explain_intrabar_strategy_allowlist_decision(
    *,
    signal_payload: Any = None,
    trade_plan: Any = None,
    strategy_name: Any = None,
    enabled: bool = True,
    allowlist: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    allowed_names = normalize_intrabar_allowlist(allowlist)

    strategy = pick_intrabar_strategy_name(
        {"strategy": strategy_name} if strategy_name else {},
        trade_plan,
        signal_payload,
    )

    if not enabled:
        return {
            "phase": PHASE,
            "enabled": False,
            "allowed": True,
            "reason": "allowlist_disabled",
            "strategy": strategy,
            "allowlist": list(allowed_names),
            "decision_impact": "NONE",
            "scope": "INTRABAR_ONLY",
            "can_execute": False,
            "can_block_trade": True,
            "can_modify_risk": False,
            "can_modify_entry_sl_tp": False,
        }

    intrabar_scope = is_intrabar_scope(signal_payload, trade_plan)

    if not intrabar_scope:
        return {
            "phase": PHASE,
            "enabled": True,
            "allowed": True,
            "reason": "non_intrabar_scope",
            "strategy": strategy,
            "allowlist": list(allowed_names),
            "decision_impact": "NONE",
            "scope": "NON_INTRABAR_SKIPPED",
            "can_execute": False,
            "can_block_trade": False,
            "can_modify_risk": False,
            "can_modify_entry_sl_tp": False,
        }

    allowed = strategy in allowed_names

    return {
        "phase": PHASE,
        "enabled": True,
        "allowed": allowed,
        "reason": "allowed_strategy" if allowed else "blocked_intrabar_strategy_not_in_allowlist",
        "strategy": strategy,
        "allowlist": list(allowed_names),
        "decision_impact": "INTRABAR_EXECUTION_ALLOWLIST",
        "scope": "INTRABAR_ONLY",
        "can_execute": False,
        "can_block_trade": True,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
    }


def filter_intrabar_strategy_profiles(
    profiles: Any,
    *,
    enabled: bool = True,
    allowlist: Optional[Iterable[Any]] = None,
) -> Any:
    if not enabled:
        return profiles

    if not isinstance(profiles, list):
        return profiles

    allowed_names = set(normalize_intrabar_allowlist(allowlist))

    filtered = []

    for profile in profiles:
        strategy = pick_intrabar_strategy_name(profile)

        if strategy in allowed_names:
            filtered.append(profile)

    return filtered
