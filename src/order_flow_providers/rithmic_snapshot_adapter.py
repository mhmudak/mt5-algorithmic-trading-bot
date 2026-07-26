from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


REQUIRED_ADAPTER_METRICS = [
    "bid_volume",
    "ask_volume",
    "delta",
    "cumulative_delta",
    "footprint_imbalance",
    "dom_bid_depth",
    "dom_ask_depth",
]


def load_latest_rithmic_state(path: str | Path) -> dict[str, Any]:
    p = Path(path)

    if not p.exists():
        return {
            "loaded": False,
            "error": f"snapshot_not_found: {p}",
            "path": str(p),
        }

    try:
        return {
            "loaded": True,
            "path": str(p),
            "snapshot": json.loads(p.read_text(encoding="utf-8")),
        }
    except Exception as exc:
        return {
            "loaded": False,
            "error": f"snapshot_read_error: {exc}",
            "path": str(p),
        }


def build_rithmic_provider_status(
    snapshot: dict[str, Any] | None,
    *,
    snapshot_path: str | Path,
    stale_after_seconds: int = 30,
) -> dict[str, Any]:
    now_epoch = time.time()

    if not snapshot:
        return {
            "phase": "PHASE_5F_RITHMIC_PROVIDER_STATUS",
            "provider_name": "RITHMIC_PROTOCOL",
            "source": "RITHMIC_STATE_SNAPSHOT",
            "snapshot_path": str(snapshot_path),
            "loaded": False,
            "provider_status": "SNAPSHOT_MISSING",
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "safe_for_live_decision": False,
            "adapter_metrics": {k: 0 for k in REQUIRED_ADAPTER_METRICS},
            "warnings": ["RITHMIC_STATE_SNAPSHOT_NOT_FOUND", "DECISION_IMPACT_DISABLED"],
            "updated_at_epoch": now_epoch,
        }

    connection = snapshot.get("connection") or {}
    freshness = snapshot.get("freshness") or {}
    quality = snapshot.get("quality") or {}
    adapter_metrics = snapshot.get("adapter_compatible_metrics") or {}

    login_ok = bool(connection.get("login_ok"))
    market_data_ok = bool(connection.get("market_data_ok"))

    last_trade_age = freshness.get("last_trade_age_seconds")
    has_fresh_trade = bool(freshness.get("has_fresh_trade"))

    order_book = snapshot.get("order_book") or {}
    dom_available = bool(order_book.get("available") or adapter_metrics.get("dom_available"))

    state_status = snapshot.get("state_status") or "UNKNOWN"

    normalized_metrics = {}
    for key in REQUIRED_ADAPTER_METRICS:
        value = adapter_metrics.get(key, 0)
        normalized_metrics[key] = 0 if value is None else value

    normalized_metrics["dom_depth_imbalance"] = adapter_metrics.get("dom_depth_imbalance")
    normalized_metrics["dom_available"] = dom_available

    warnings = list(quality.get("warnings") or [])

    if not login_ok:
        provider_status = "LOGIN_NOT_OK"
        warnings.append("RITHMIC_LOGIN_NOT_OK")
    elif not market_data_ok:
        provider_status = "MARKET_DATA_NOT_OK"
        warnings.append("RITHMIC_MARKET_DATA_NOT_OK")
    elif not has_fresh_trade:
        provider_status = "STALE_OR_LOW_ACTIVITY_OBSERVATION_ONLY"
        warnings.append("RITHMIC_TRADE_FLOW_NOT_FRESH")
    else:
        provider_status = "OBSERVE_ONLY_READY"

    if last_trade_age is not None and last_trade_age > stale_after_seconds:
        warnings.append("RITHMIC_SNAPSHOT_STALE_FOR_DECISION_USE")

    if snapshot.get("is_test_environment"):
        warnings.append("RITHMIC_TEST_ENVIRONMENT_NOT_PRODUCTION")

    if not dom_available:
        warnings.append("DOM_NOT_AVAILABLE_OR_NO_BOOK")

    warnings.append("DECISION_IMPACT_DISABLED")

    return {
        "phase": "PHASE_5F_RITHMIC_PROVIDER_STATUS",
        "provider_name": "RITHMIC_PROTOCOL",
        "source": "RITHMIC_STATE_SNAPSHOT",
        "snapshot_path": str(snapshot_path),
        "loaded": True,
        "symbol": snapshot.get("symbol"),
        "exchange": snapshot.get("exchange"),
        "system_name": snapshot.get("system_name"),
        "is_test_environment": snapshot.get("is_test_environment"),
        "provider_status": provider_status,
        "source_state_status": state_status,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_live_decision": False,
        "safe_for_execution": False,
        "updated_at_epoch": now_epoch,
        "freshness": {
            "last_trade_age_seconds": last_trade_age,
            "last_bbo_age_seconds": freshness.get("last_bbo_age_seconds"),
            "last_order_book_age_seconds": freshness.get("last_order_book_age_seconds"),
            "has_fresh_trade": has_fresh_trade,
            "has_fresh_bbo": bool(freshness.get("has_fresh_bbo")),
            "has_fresh_order_book": bool(freshness.get("has_fresh_order_book")),
        },
        "connection": {
            "login_ok": login_ok,
            "market_data_ok": market_data_ok,
        },
        "sample": snapshot.get("sample") or {},
        "latest_trade": snapshot.get("latest_trade") or {},
        "trade_flow": snapshot.get("trade_flow") or {},
        "volume_profile": snapshot.get("volume_profile") or {},
        "footprint": {
            "candle_count": (snapshot.get("footprint") or {}).get("candle_count", 0),
        },
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
        "adapter_metrics": normalized_metrics,
        "required_adapter_metrics": REQUIRED_ADAPTER_METRICS,
        "warnings": sorted(set(warnings)),
        "notes": [
            "Rithmic data is connected through snapshot adapter only.",
            "This provider status is observe-only.",
            "No MT5 live execution decision may use this yet.",
        ],
    }


def write_provider_status_text(status: dict[str, Any], output_path: str | Path) -> None:
    lines = [
        "PHASE 5F RITHMIC PROVIDER STATUS",
        "================================",
        f"provider_name: {status.get('provider_name')}",
        f"symbol: {status.get('symbol')}",
        f"exchange: {status.get('exchange')}",
        f"system_name: {status.get('system_name')}",
        f"is_test_environment: {status.get('is_test_environment')}",
        f"provider_status: {status.get('provider_status')}",
        f"source_state_status: {status.get('source_state_status')}",
        f"decision_impact: {status.get('decision_impact')}",
        f"can_influence_decision: {status.get('can_influence_decision')}",
        f"safe_for_live_decision: {status.get('safe_for_live_decision')}",
        "",
        "[CONNECTION]",
        f"login_ok: {status['connection']['login_ok']}",
        f"market_data_ok: {status['connection']['market_data_ok']}",
        "",
        "[FRESHNESS]",
        f"last_trade_age_seconds: {status['freshness']['last_trade_age_seconds']}",
        f"has_fresh_trade: {status['freshness']['has_fresh_trade']}",
        f"last_order_book_age_seconds: {status['freshness']['last_order_book_age_seconds']}",
        f"has_fresh_order_book: {status['freshness']['has_fresh_order_book']}",
        "",
        "[ADAPTER METRICS]",
    ]

    for key, value in (status.get("adapter_metrics") or {}).items():
        lines.append(f"{key}: {value}")

    lines.extend([
        "",
        "[ORDER BOOK]",
        f"available: {status['order_book']['available']}",
        f"last_update_type_name: {status['order_book']['last_update_type_name']}",
        f"bid_level_count: {status['order_book']['bid_level_count']}",
        f"ask_level_count: {status['order_book']['ask_level_count']}",
        f"bid_depth: {status['order_book']['bid_depth']}",
        f"ask_depth: {status['order_book']['ask_depth']}",
        f"depth_imbalance: {status['order_book']['depth_imbalance']}",
        "",
        "[WARNINGS]",
        ", ".join(status.get("warnings") or []),
        "",
        "NOTE:",
        "This file is observe-only and must not influence MT5 execution yet.",
    ])

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
