from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from config.rithmic_systems import (  # noqa: E402
    CONFORMANCE_STATUS,
    DEFAULT_PRODUCTION_ENDPOINT_KEY,
    PHASE,
    PRODUCTION_SWITCH_POLICY,
    REQUIRED_APP_PREFIX,
    get_rithmic_endpoint,
    list_rithmic_endpoints,
)


OUT_DIR = ROOT / "data" / "strategy_intelligence" / "rithmic_production"
OUT_JSON = OUT_DIR / "phase5an_rithmic_production_readiness.json"
OUT_TXT = OUT_DIR / "phase5an_rithmic_production_readiness_summary.txt"


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    env: dict[str, str] = {}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key:
            env[key] = value

    return env


def bool_env(env: dict[str, str], key: str) -> bool:
    return safe_text(env.get(key)).lower() in {"1", "true", "yes", "y", "on"}


def redacted_presence(env: dict[str, str], key: str) -> dict[str, Any]:
    value = env.get(key)

    return {
        "present": bool(value),
        "length": len(value) if value else 0,
        "value": "***REDACTED***" if value else None,
    }


def main() -> None:
    env_path = ROOT / ".env"
    env = parse_env_file(env_path)

    endpoint_key = safe_text(env.get("RITHMIC_ENDPOINT_KEY"), DEFAULT_PRODUCTION_ENDPOINT_KEY).upper()

    try:
        endpoint = get_rithmic_endpoint(endpoint_key)
        endpoint_known = True
        endpoint_error = None
    except Exception as exc:
        endpoint = get_rithmic_endpoint(DEFAULT_PRODUCTION_ENDPOINT_KEY)
        endpoint_known = False
        endpoint_error = str(exc)

    app_name = safe_text(env.get("RITHMIC_APP_NAME"))
    ws_url = safe_text(env.get("RITHMIC_WS_URL"))
    system_name = safe_text(env.get("RITHMIC_SYSTEM_NAME"))

    conformance_passed = CONFORMANCE_STATUS == "PASSED"
    app_prefix_ok = app_name.startswith(REQUIRED_APP_PREFIX)

    username_present = bool(env.get("RITHMIC_USERNAME"))
    password_present = bool(env.get("RITHMIC_PASSWORD"))

    subscription_active = bool_env(env, "RITHMIC_DIRECT_MARKET_DATA_SUBSCRIPTION_ACTIVE")
    comex_market_data_enabled = bool_env(env, "RITHMIC_COMEX_MARKET_DATA_ENABLED")
    market_depth_enabled = bool_env(env, "RITHMIC_COMEX_MARKET_DEPTH_ENABLED")

    current_is_test = (
        "TEST" in system_name.upper()
        or "RITHMIC TEST" in system_name.upper()
        or "rituz" in ws_url.lower()
    )

    current_is_production_like = bool(
        ws_url
        and "rprotocol" in ws_url.lower()
        and not current_is_test
    )

    recommended_ws_url = endpoint.websocket_url

    required_checks = {
        "conformance_passed": conformance_passed,
        "app_prefix_ok": app_prefix_ok,
        "endpoint_key_known": endpoint_known,
        "username_present": username_present,
        "password_present": password_present,
        "subscription_active": subscription_active,
        "comex_market_data_enabled": comex_market_data_enabled,
        "market_depth_enabled": market_depth_enabled,
        "production_like_url_selected": current_is_production_like,
        "system_name_not_test": bool(system_name and not current_is_test),
    }

    missing = [key for key, ok in required_checks.items() if not ok]
    passed = [key for key, ok in required_checks.items() if ok]

    ready_for_production_connection_test = not missing

    if ready_for_production_connection_test:
        readiness_status = "READY_FOR_PRODUCTION_CONNECTION_TEST_OBSERVE_ONLY"
        next_action = "Run a short observe-only production login and market-data permission test."
    elif conformance_passed and app_prefix_ok:
        readiness_status = "WAITING_FOR_RITHMIC_SUBSCRIPTION_OR_CREDENTIALS"
        next_action = "Wait for Rithmic subscription price, credentials, system name, and COMEX market-depth confirmation."
    else:
        readiness_status = "NOT_READY_FIX_APP_PREFIX_OR_CONFORMANCE"
        next_action = "Fix RITHMIC_APP_NAME prefix and conformance configuration before any production attempt."

    report = {
        "phase": PHASE,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "AUDIT_ONLY",
        "decision_impact": "NONE",
        "execution_change": "NONE",
        "can_auto_trade": False,
        "can_influence_decision": False,
        "conformance_status": CONFORMANCE_STATUS,
        "readiness_status": readiness_status,
        "next_action": next_action,
        "recommended_endpoint": {
            "key": endpoint.key,
            "label": endpoint.label,
            "region": endpoint.region,
            "host": endpoint.host,
            "websocket_url": endpoint.websocket_url,
        },
        "current_env": {
            "env_path": str(env_path),
            "rithmic_endpoint_key": endpoint_key,
            "rithmic_ws_url": ws_url,
            "recommended_ws_url": recommended_ws_url,
            "rithmic_system_name": system_name,
            "rithmic_app_name": app_name,
            "rithmic_username": redacted_presence(env, "RITHMIC_USERNAME"),
            "rithmic_password": redacted_presence(env, "RITHMIC_PASSWORD"),
            "current_is_test": current_is_test,
            "current_is_production_like": current_is_production_like,
        },
        "subscription_flags": {
            "RITHMIC_DIRECT_MARKET_DATA_SUBSCRIPTION_ACTIVE": subscription_active,
            "RITHMIC_COMEX_MARKET_DATA_ENABLED": comex_market_data_enabled,
            "RITHMIC_COMEX_MARKET_DEPTH_ENABLED": market_depth_enabled,
        },
        "required_checks": required_checks,
        "passed": passed,
        "missing": missing,
        "endpoint_error": endpoint_error,
        "available_endpoints": list_rithmic_endpoints(),
        "production_switch_policy": PRODUCTION_SWITCH_POLICY,
        "safety_rule": (
            "Do not replace test .env with production values until Rithmic provides credentials, system name, "
            "market data subscription confirmation, and COMEX market-depth permission."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "[PHASE 5AN RITHMIC PRODUCTION READINESS]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"decision_impact = {report['decision_impact']}",
        f"execution_change = {report['execution_change']}",
        f"can_auto_trade = {report['can_auto_trade']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        "",
        "[CONFORMANCE]",
        f"conformance_status = {CONFORMANCE_STATUS}",
        f"required_app_prefix = {REQUIRED_APP_PREFIX}",
        f"app_prefix_ok = {app_prefix_ok}",
        "",
        "[CURRENT ENV]",
        f"RITHMIC_WS_URL = {ws_url}",
        f"RITHMIC_SYSTEM_NAME = {system_name}",
        f"RITHMIC_APP_NAME = {app_name}",
        f"RITHMIC_USERNAME_PRESENT = {username_present}",
        f"RITHMIC_PASSWORD_PRESENT = {password_present}",
        f"current_is_test = {current_is_test}",
        f"current_is_production_like = {current_is_production_like}",
        "",
        "[RECOMMENDED FIRST PRODUCTION ENDPOINT]",
        f"endpoint_key = {endpoint.key}",
        f"label = {endpoint.label}",
        f"websocket_url = {endpoint.websocket_url}",
        "",
        "[SUBSCRIPTION FLAGS]",
        f"RITHMIC_DIRECT_MARKET_DATA_SUBSCRIPTION_ACTIVE = {subscription_active}",
        f"RITHMIC_COMEX_MARKET_DATA_ENABLED = {comex_market_data_enabled}",
        f"RITHMIC_COMEX_MARKET_DEPTH_ENABLED = {market_depth_enabled}",
        "",
        "[READINESS]",
        f"readiness_status = {readiness_status}",
        f"next_action = {next_action}",
        "",
        "[PASSED]",
        *[f"- {x}" for x in passed],
        "",
        "[MISSING]",
        *[f"- {x}" for x in missing],
        "",
        "[SAFETY RULE]",
        report["safety_rule"],
        "",
        f"json = {OUT_JSON}",
        f"summary = {OUT_TXT}",
    ]

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
