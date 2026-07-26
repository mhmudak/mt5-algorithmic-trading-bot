from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _metric_present(metrics: dict[str, Any], key: str) -> bool:
    return key in metrics and metrics.get(key) is not None


def build_rithmic_monitoring_bridge(provider_status: dict[str, Any]) -> dict[str, Any]:
    now_epoch = time.time()

    adapter_metrics = provider_status.get("adapter_metrics") or {}
    required_metrics = list(provider_status.get("required_adapter_metrics") or [])

    missing_metrics = [
        key for key in required_metrics
        if not _metric_present(adapter_metrics, key)
    ]

    connection = provider_status.get("connection") or {}
    freshness = provider_status.get("freshness") or {}
    order_book = provider_status.get("order_book") or {}

    login_ok = bool(connection.get("login_ok"))
    market_data_ok = bool(connection.get("market_data_ok"))
    has_fresh_trade = bool(freshness.get("has_fresh_trade"))
    dom_available = bool(adapter_metrics.get("dom_available"))

    warnings = list(provider_status.get("warnings") or [])

    if not login_ok:
        bridge_status = "RITHMIC_LOGIN_NOT_OK"
        warnings.append("BRIDGE_BLOCKED_LOGIN_NOT_OK")
    elif not market_data_ok:
        bridge_status = "RITHMIC_MARKET_DATA_NOT_OK"
        warnings.append("BRIDGE_BLOCKED_MARKET_DATA_NOT_OK")
    elif missing_metrics:
        bridge_status = "RITHMIC_MISSING_ADAPTER_METRICS"
        warnings.append("BRIDGE_BLOCKED_MISSING_ADAPTER_METRICS")
    elif not has_fresh_trade:
        bridge_status = "RITHMIC_CONNECTED_STALE_OBSERVATION_ONLY"
        warnings.append("BRIDGE_STALE_OBSERVATION_ONLY")
    else:
        bridge_status = "RITHMIC_CONNECTED_OBSERVE_ONLY"

    if not dom_available:
        warnings.append("BRIDGE_DOM_NOT_AVAILABLE_OR_NO_BOOK")

    warnings.append("BRIDGE_DECISION_IMPACT_DISABLED")

    return {
        "phase": "PHASE_5G_RITHMIC_MONITORING_BRIDGE",
        "provider_name": "RITHMIC_PROTOCOL",
        "source": "PHASE_5F_RITHMIC_PROVIDER_STATUS",
        "bridge_status": bridge_status,
        "provider_status": provider_status.get("provider_status"),
        "symbol": provider_status.get("symbol"),
        "exchange": provider_status.get("exchange"),
        "system_name": provider_status.get("system_name"),
        "is_test_environment": provider_status.get("is_test_environment"),
        "updated_at_epoch": now_epoch,

        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_live_decision": False,
        "safe_for_execution": False,

        "phase4_compatibility": {
            "adapter_metric_format_ready": len(missing_metrics) == 0,
            "can_replace_no_order_flow_provider": False,
            "gate_status_override_allowed": False,
            "reason": "Rithmic bridge is observe-only. Validation and production data are not complete.",
        },

        "connection": {
            "login_ok": login_ok,
            "market_data_ok": market_data_ok,
        },

        "freshness": {
            "has_fresh_trade": has_fresh_trade,
            "has_fresh_bbo": bool(freshness.get("has_fresh_bbo")),
            "has_fresh_order_book": bool(freshness.get("has_fresh_order_book")),
            "last_trade_age_seconds": freshness.get("last_trade_age_seconds"),
            "last_bbo_age_seconds": freshness.get("last_bbo_age_seconds"),
            "last_order_book_age_seconds": freshness.get("last_order_book_age_seconds"),
        },

        "adapter_metrics": {
            "bid_volume": adapter_metrics.get("bid_volume", 0),
            "ask_volume": adapter_metrics.get("ask_volume", 0),
            "delta": adapter_metrics.get("delta", 0),
            "cumulative_delta": adapter_metrics.get("cumulative_delta", 0),
            "footprint_imbalance": adapter_metrics.get("footprint_imbalance", 0),
            "dom_bid_depth": adapter_metrics.get("dom_bid_depth", 0),
            "dom_ask_depth": adapter_metrics.get("dom_ask_depth", 0),
            "dom_depth_imbalance": adapter_metrics.get("dom_depth_imbalance"),
            "dom_available": dom_available,
        },

        "metric_validation": {
            "required_metrics": required_metrics,
            "missing_metrics": missing_metrics,
            "required_metric_count": len(required_metrics),
            "present_required_metric_count": len(required_metrics) - len(missing_metrics),
        },

        "latest_trade": provider_status.get("latest_trade") or {},
        "trade_flow": provider_status.get("trade_flow") or {},
        "volume_profile": provider_status.get("volume_profile") or {},

        "order_book": {
            "available": dom_available,
            "last_update_type_name": order_book.get("last_update_type_name"),
            "bid_level_count": order_book.get("bid_level_count", 0),
            "ask_level_count": order_book.get("ask_level_count", 0),
            "bid_depth": order_book.get("bid_depth", 0),
            "ask_depth": order_book.get("ask_depth", 0),
            "depth_imbalance": order_book.get("depth_imbalance"),
            "top_bid_price": order_book.get("top_bid_price"),
            "top_ask_price": order_book.get("top_ask_price"),
        },

        "dashboard_block": [
            "RITHMIC PROTOCOL ORDER-FLOW BRIDGE",
            f"bridge_status: {bridge_status}",
            f"symbol: {provider_status.get('symbol')}",
            f"decision_impact: NONE",
            f"can_influence_decision: False",
            f"delta: {adapter_metrics.get('delta', 0)}",
            f"cumulative_delta: {adapter_metrics.get('cumulative_delta', 0)}",
            f"dom_available: {dom_available}",
            f"dom_bid_depth: {adapter_metrics.get('dom_bid_depth', 0)}",
            f"dom_ask_depth: {adapter_metrics.get('dom_ask_depth', 0)}",
        ],

        "warnings": sorted(set(warnings)),
        "recommendation": "Keep Rithmic data in observe-only monitoring. Do not connect to live MT5 decisions yet.",
    }


def write_bridge_text(bridge: dict[str, Any], output_path: str | Path) -> None:
    lines = [
        "PHASE 5G RITHMIC MONITORING BRIDGE",
        "===================================",
        f"provider_name: {bridge.get('provider_name')}",
        f"symbol: {bridge.get('symbol')}",
        f"exchange: {bridge.get('exchange')}",
        f"system_name: {bridge.get('system_name')}",
        f"is_test_environment: {bridge.get('is_test_environment')}",
        f"bridge_status: {bridge.get('bridge_status')}",
        f"provider_status: {bridge.get('provider_status')}",
        f"decision_impact: {bridge.get('decision_impact')}",
        f"can_influence_decision: {bridge.get('can_influence_decision')}",
        f"safe_for_live_decision: {bridge.get('safe_for_live_decision')}",
        "",
        "[PHASE 4 COMPATIBILITY]",
        f"adapter_metric_format_ready: {bridge['phase4_compatibility']['adapter_metric_format_ready']}",
        f"can_replace_no_order_flow_provider: {bridge['phase4_compatibility']['can_replace_no_order_flow_provider']}",
        f"gate_status_override_allowed: {bridge['phase4_compatibility']['gate_status_override_allowed']}",
        f"reason: {bridge['phase4_compatibility']['reason']}",
        "",
        "[ADAPTER METRICS]",
    ]

    for key, value in bridge["adapter_metrics"].items():
        lines.append(f"{key}: {value}")

    lines.extend([
        "",
        "[ORDER BOOK]",
        f"available: {bridge['order_book']['available']}",
        f"last_update_type_name: {bridge['order_book']['last_update_type_name']}",
        f"bid_level_count: {bridge['order_book']['bid_level_count']}",
        f"ask_level_count: {bridge['order_book']['ask_level_count']}",
        f"bid_depth: {bridge['order_book']['bid_depth']}",
        f"ask_depth: {bridge['order_book']['ask_depth']}",
        f"depth_imbalance: {bridge['order_book']['depth_imbalance']}",
        "",
        "[WARNINGS]",
        ", ".join(bridge.get("warnings") or []),
        "",
        "[RECOMMENDATION]",
        bridge.get("recommendation", ""),
        "",
        "NOTE:",
        "This bridge is observe-only and must not influence MT5 execution yet.",
    ])

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_bridge_json(bridge: dict[str, Any], output_path: str | Path) -> None:
    Path(output_path).write_text(json.dumps(bridge, indent=2, ensure_ascii=False), encoding="utf-8")
