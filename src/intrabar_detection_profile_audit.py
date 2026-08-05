from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PHASE = "PHASE_6U3_INTRABAR_DETECTION_PROFILE_HARD_BLOCK_AUDIT"


def normalize_name(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        value = next((item for item in value if item), "")
    return str(value).strip().upper()


def normalize_list(values: Iterable[Any]) -> Tuple[str, ...]:
    output = []
    for value in values or []:
        name = normalize_name(value)
        if name:
            output.append(name)
    return tuple(dict.fromkeys(output))


def extract_profile_strategy_name(profile: Any) -> str:
    if isinstance(profile, dict):
        for key in ("strategy", "strategy_name", "name", "setup_source", "setup_type", "profile_name"):
            value = profile.get(key)
            if value:
                return normalize_name(value)
    return normalize_name(profile)


def audit_intrabar_detection_profiles(
    *,
    profiles: Any,
    allowed_strategies: Iterable[Any],
    blocked_examples: Iterable[Any],
) -> Dict[str, Any]:
    allowed = set(normalize_list(allowed_strategies))
    blocked = set(normalize_list(blocked_examples))

    if not isinstance(profiles, list):
        return {
            "phase": PHASE,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "profile_list_found": False,
            "status": "PROFILE_LIST_NOT_FOUND_OR_NOT_LIST",
            "profile_count": 0,
            "allowed_strategies": sorted(allowed),
            "blocked_examples": sorted(blocked),
            "detected_strategy_names": [],
            "allowed_profiles": [],
            "blocked_profiles_remaining": [],
            "unknown_profiles_remaining": [],
            "pass": True,
            "decision_impact": "AUDIT_ONLY",
            "auto_trade_allowed": False,
            "can_execute": False,
            "can_block_trade": False,
            "can_modify_risk": False,
            "can_modify_entry_sl_tp": False,
            "can_modify_detection": False,
        }

    detected = []
    allowed_profiles = []
    blocked_remaining = []
    unknown_remaining = []

    for index, profile in enumerate(profiles):
        strategy = extract_profile_strategy_name(profile)
        detected.append(strategy)
        row = {"index": index, "strategy": strategy}

        if strategy in allowed:
            allowed_profiles.append(row)
        elif strategy in blocked:
            blocked_remaining.append(row)
        else:
            unknown_remaining.append(row)

    passed = len(blocked_remaining) == 0 and len(unknown_remaining) == 0

    return {
        "phase": PHASE,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "profile_list_found": True,
        "status": "PASS" if passed else "BLOCKED_OR_UNKNOWN_PROFILE_REMAINING",
        "profile_count": len(profiles),
        "allowed_strategies": sorted(allowed),
        "blocked_examples": sorted(blocked),
        "detected_strategy_names": sorted(set(name for name in detected if name)),
        "allowed_profiles": allowed_profiles,
        "blocked_profiles_remaining": blocked_remaining,
        "unknown_profiles_remaining": unknown_remaining,
        "pass": passed,
        "decision_impact": "AUDIT_ONLY",
        "auto_trade_allowed": False,
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
        "can_modify_detection": False,
    }


def build_phase6u3_settings_audit() -> Dict[str, Any]:
    from config import settings

    profiles = getattr(settings, "INTRABAR_PRICE_EVENT_STRATEGY_PROFILES", None)
    allowed = getattr(settings, "INTRABAR_STRATEGY_ALLOWLIST", ())
    blocked = getattr(settings, "INTRABAR_STRATEGY_BLOCKED_EXAMPLES", ())

    report = audit_intrabar_detection_profiles(
        profiles=profiles,
        allowed_strategies=allowed,
        blocked_examples=blocked,
    )

    report["settings_flags"] = {
        "ENABLE_INTRABAR_STRATEGY_ALLOWLIST": bool(getattr(settings, "ENABLE_INTRABAR_STRATEGY_ALLOWLIST", False)),
        "ENABLE_INTRABAR_STRATEGY_DETECTION_ALLOWLIST": bool(getattr(settings, "ENABLE_INTRABAR_STRATEGY_DETECTION_ALLOWLIST", False)),
    }

    report["settings_pass"] = (
        report["settings_flags"]["ENABLE_INTRABAR_STRATEGY_ALLOWLIST"]
        and report["settings_flags"]["ENABLE_INTRABAR_STRATEGY_DETECTION_ALLOWLIST"]
        and "AUTO_STRUCTURAL_LEVEL_SCALP" in report["allowed_strategies"]
        and "FAILED_FVG_REVERSAL" in report["allowed_strategies"]
    )

    return report


def write_phase6u3_audit_report(report: Dict[str, Any], output_dir: str | Path = "data/reports/intrabar_detection_profile_audit") -> Dict[str, str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = target / f"phase6u3_intrabar_detection_profile_audit_{timestamp}.json"
    latest_json_path = target / "phase6u3_intrabar_detection_profile_audit_latest.json"

    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    json_path.write_text(text, encoding="utf-8")
    latest_json_path.write_text(text, encoding="utf-8")

    return {"json": str(json_path), "latest_json": str(latest_json_path)}
