from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


PHASE = "PHASE_5V_RITHMIC_OBSERVE_ONLY_PROVIDER_REGISTRATION"

ROOT = Path(".")
ORDER_FLOW_DIR = ROOT / "data" / "order_flow" / "rithmic"
ACCOUNT_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

PHASE5U_REPORT = ACCOUNT_DIR / "phase5u_rithmic_real_orderflow_acceptance_report.json"
PHASE5U_SUMMARY = ACCOUNT_DIR / "phase5u_rithmic_real_orderflow_acceptance_summary.txt"
PHASE5C_LATEST = ORDER_FLOW_DIR / "MGCQ6_phase5c_rithmic_state_latest.json"

OUT_JSON = ORDER_FLOW_DIR / "phase5v_rithmic_observe_only_provider_registration.json"
OUT_TXT = ORDER_FLOW_DIR / "phase5v_rithmic_observe_only_provider_registration_summary.txt"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""

    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def deep_find(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]

        for value in obj.values():
            found = deep_find(value, key)
            if found is not None:
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = deep_find(item, key)
            if found is not None:
                return found

    return None


def text_value(text: str, key: str) -> str | None:
    pattern = rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*$"

    for line in text.splitlines():
        m = re.match(pattern, line)
        if m:
            return m.group(1).strip()

    return None


def as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default

    try:
        return float(value)
    except Exception:
        return default


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "accepted"}

    return bool(value)


def get_metric(report: dict[str, Any], text: str, key: str, default: float = 0.0) -> float:
    from_text = text_value(text, key)
    if from_text is not None:
        return as_float(from_text, default)

    return as_float(deep_find(report, key), default)


def get_status(report: dict[str, Any], text: str, key: str, default: str = "UNKNOWN") -> str:
    from_text = text_value(text, key)
    if from_text is not None:
        return str(from_text)

    value = deep_find(report, key)
    return str(value) if value is not None else default


def get_bool_metric(report: dict[str, Any], text: str, key: str, default: bool = False) -> bool:
    from_text = text_value(text, key)
    if from_text is not None:
        return as_bool(from_text)

    value = deep_find(report, key)
    if value is None:
        return default

    return as_bool(value)


def main() -> None:
    ORDER_FLOW_DIR.mkdir(parents=True, exist_ok=True)

    phase5u = load_json(PHASE5U_REPORT)
    phase5u_text = read_text(PHASE5U_SUMMARY)
    phase5c = load_json(PHASE5C_LATEST)

    accepted = get_bool_metric(phase5u, phase5u_text, "accepted", False)
    overall_status = get_status(phase5u, phase5u_text, "overall_status")

    hard_ok_rate = get_metric(phase5u, phase5u_text, "hard_ok_rate")
    quality_ok_rate = get_metric(phase5u, phase5u_text, "quality_ok_rate")

    positive_bbo_rate = get_metric(phase5u, phase5u_text, "positive_bbo_rate")
    dom_available_rate = get_metric(phase5u, phase5u_text, "dom_available_rate")
    two_sided_dom_rate = get_metric(phase5u, phase5u_text, "two_sided_dom_rate")
    avg_trade_count = get_metric(phase5u, phase5u_text, "avg_trade_count")
    max_trade_count = get_metric(phase5u, phase5u_text, "max_trade_count")
    avg_spread = get_metric(phase5u, phase5u_text, "avg_spread")
    max_spread = get_metric(phase5u, phase5u_text, "max_spread")

    latest_bid = as_float(deep_find(phase5c, "last_bid"))
    latest_ask = as_float(deep_find(phase5c, "last_ask"))
    latest_spread = as_float(deep_find(phase5c, "last_spread"))

    dom_bid_depth = as_float(deep_find(phase5c, "dom_bid_depth"))
    dom_ask_depth = as_float(deep_find(phase5c, "dom_ask_depth"))
    dom_depth_imbalance = deep_find(phase5c, "dom_depth_imbalance")

    if dom_bid_depth <= 0:
        dom_bid_depth = as_float(deep_find(phase5c, "bid_depth"))

    if dom_ask_depth <= 0:
        dom_ask_depth = as_float(deep_find(phase5c, "ask_depth"))

    rolling_trade_count = deep_find(phase5c, "rolling_trade_count")
    rolling_delta = deep_find(phase5c, "rolling_delta")
    session_cumulative_delta = deep_find(phase5c, "session_cumulative_delta")
    rolling_poc_price = deep_find(phase5c, "rolling_poc_price")

    has_valid_bbo = bool(
        positive_bbo_rate > 0
        or (latest_bid > 0 and latest_ask > 0)
        or (latest_spread > 0 and latest_spread <= 1)
    )

    has_two_sided_dom = bool(
        two_sided_dom_rate > 0
        or (dom_bid_depth > 0 and dom_ask_depth > 0)
    )

    spread_ok = bool(
        (max_spread > 0 and max_spread <= 1)
        or (latest_spread > 0 and latest_spread <= 1)
        or avg_spread <= 1
    )

    trade_flow_decision_grade = avg_trade_count >= 3

    can_register_observe_only = bool(
        has_valid_bbo
        and has_two_sided_dom
        and spread_ok
    )

    if accepted and trade_flow_decision_grade:
        provider_quality = "ACCEPTED_OBSERVE_ONLY"
    elif can_register_observe_only and not trade_flow_decision_grade:
        provider_quality = "DOM_AND_BBO_VALIDATED_LOW_TRADE_FLOW"
    elif can_register_observe_only:
        provider_quality = "DOM_AND_BBO_VALIDATED_OBSERVE_ONLY"
    else:
        provider_quality = "NOT_REGISTERABLE_BAD_DATA"

    registration_status = "REGISTERED_OBSERVE_ONLY" if can_register_observe_only else "NOT_REGISTERED"

    report = {
        "phase": PHASE,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "provider": "RITHMIC_R_PROTOCOL",
        "provider_role": "REAL_ORDER_FLOW_SOURCE",
        "source_market": "COMEX",
        "symbol": "MGCQ6",
        "instrument_family": "MICRO_GOLD_FUTURES",
        "registration_status": registration_status,
        "provider_quality": provider_quality,
        "mode": "OBSERVE_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
        "manual_review_only": True,
        "manual_decision_support": {
            "telegram_must_show": True,
            "message_rule": "Show whether Rithmic observe-only flow SUPPORTS, AGAINST, or is MIXED/LOW_SAMPLE for the setup. Never auto-trade from this.",
        },
        "phase5u": {
            "report_path": str(PHASE5U_REPORT),
            "summary_path": str(PHASE5U_SUMMARY),
            "accepted": accepted,
            "overall_status": overall_status,
            "hard_ok_rate": hard_ok_rate,
            "quality_ok_rate": quality_ok_rate,
            "positive_bbo_rate": positive_bbo_rate,
            "dom_available_rate": dom_available_rate,
            "two_sided_dom_rate": two_sided_dom_rate,
            "avg_trade_count": avg_trade_count,
            "max_trade_count": max_trade_count,
            "avg_spread": avg_spread,
            "max_spread": max_spread,
        },
        "latest_state": {
            "report_path": str(PHASE5C_LATEST),
            "state_status": deep_find(phase5c, "state_status"),
            "rolling_trade_count": rolling_trade_count,
            "rolling_delta": rolling_delta,
            "session_cumulative_delta": session_cumulative_delta,
            "rolling_poc_price": rolling_poc_price,
            "latest_bid": latest_bid,
            "latest_ask": latest_ask,
            "latest_spread": latest_spread,
            "dom_bid_depth": dom_bid_depth,
            "dom_ask_depth": dom_ask_depth,
            "dom_depth_imbalance": dom_depth_imbalance,
        },
        "gates": {
            "can_register_observe_only": can_register_observe_only,
            "has_valid_bbo": has_valid_bbo,
            "has_two_sided_dom": has_two_sided_dom,
            "spread_ok": spread_ok,
            "trade_flow_decision_grade": trade_flow_decision_grade,
            "decision_influence_allowed": False,
            "execution_allowed": False,
        },
        "recommendation": (
            "Rithmic can be registered as an observe-only real order-flow source. "
            "Telegram may use it for manual-review context only. "
            "Do not allow it to influence entries until stronger trade-flow validation passes."
            if can_register_observe_only
            else "Do not register Rithmic yet. Data quality is still insufficient."
        ),
    }

    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "[PHASE 5V RITHMIC OBSERVE-ONLY PROVIDER REGISTRATION]",
        f"updated_at = {report['updated_at']}",
        f"provider = {report['provider']}",
        f"provider_role = {report['provider_role']}",
        f"source_market = {report['source_market']}",
        f"symbol = {report['symbol']}",
        f"registration_status = {registration_status}",
        f"provider_quality = {provider_quality}",
        f"mode = {report['mode']}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        f"safe_for_execution = {report['safe_for_execution']}",
        f"trade_action = {report['trade_action']}",
        "",
        "[PHASE 5U]",
        f"accepted = {accepted}",
        f"overall_status = {overall_status}",
        f"hard_ok_rate = {hard_ok_rate}",
        f"quality_ok_rate = {quality_ok_rate}",
        f"positive_bbo_rate = {positive_bbo_rate}",
        f"dom_available_rate = {dom_available_rate}",
        f"two_sided_dom_rate = {two_sided_dom_rate}",
        f"avg_trade_count = {avg_trade_count}",
        f"max_trade_count = {max_trade_count}",
        f"avg_spread = {avg_spread}",
        f"max_spread = {max_spread}",
        "",
        "[GATES]",
        f"can_register_observe_only = {can_register_observe_only}",
        f"has_valid_bbo = {has_valid_bbo}",
        f"has_two_sided_dom = {has_two_sided_dom}",
        f"spread_ok = {spread_ok}",
        f"trade_flow_decision_grade = {trade_flow_decision_grade}",
        f"decision_influence_allowed = False",
        f"execution_allowed = False",
        "",
        "[LATEST STATE]",
        f"state_status = {deep_find(phase5c, 'state_status')}",
        f"rolling_trade_count = {rolling_trade_count}",
        f"rolling_delta = {rolling_delta}",
        f"session_cumulative_delta = {session_cumulative_delta}",
        f"rolling_poc_price = {rolling_poc_price}",
        f"latest_bid = {latest_bid}",
        f"latest_ask = {latest_ask}",
        f"latest_spread = {latest_spread}",
        f"dom_bid_depth = {dom_bid_depth}",
        f"dom_ask_depth = {dom_ask_depth}",
        f"dom_depth_imbalance = {dom_depth_imbalance}",
        "",
        "[TELEGRAM RULE]",
        "Telegram can show Rithmic as MANUAL REVIEW ONLY:",
        "RITHMIC SUPPORTS SETUP / RITHMIC AGAINST SETUP / RITHMIC MIXED OR LOW SAMPLE",
        "BOT ACTION must remain: NO AUTO TRADE",
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
        "",
        f"json = {OUT_JSON}",
        f"summary = {OUT_TXT}",
    ]

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
