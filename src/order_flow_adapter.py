from datetime import datetime
from typing import Any, Dict, Optional


ORDER_FLOW_MODE = "OBSERVE_ONLY"


REQUIRED_DECISION_METRICS = [
    "bid_volume",
    "ask_volume",
    "delta",
    "cumulative_delta",
    "footprint_imbalance",
    "dom_bid_depth",
    "dom_ask_depth",
]


class OrderFlowProvider:
    """
    Base interface for real futures / COMEX order-flow providers.

    Important:
    - This adapter must not fake order flow from MT5 tick volume.
    - MT5 tick volume can be used as proxy context elsewhere.
    - Real order flow requires a real futures data source.
    """

    provider_name = "BASE_PROVIDER"

    def is_available(self) -> bool:
        return False

    def get_latest_snapshot(self, symbol: str) -> Dict[str, Any]:
        raise NotImplementedError


class NoOrderFlowProvider(OrderFlowProvider):
    """
    Safe default provider.

    Used when no real COMEX / futures feed is connected.
    """

    provider_name = "NO_ORDER_FLOW_PROVIDER"

    def is_available(self) -> bool:
        return False

    def get_latest_snapshot(self, symbol: str) -> Dict[str, Any]:
        return {
            "mode": ORDER_FLOW_MODE,
            "provider": self.provider_name,
            "symbol": symbol,
            "available": False,
            "status": "NOT_CONNECTED",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "data_quality": "UNAVAILABLE",
            "decision_impact": "NONE",
            "warning": (
                "No real COMEX/futures order-flow provider is connected. "
                "Do not use MT5 tick volume as real order flow."
            ),
            "metrics": {
                "bid_volume": None,
                "ask_volume": None,
                "delta": None,
                "cumulative_delta": None,
                "footprint_imbalance": None,
                "dom_bid_depth": None,
                "dom_ask_depth": None,
                "volume_profile_poc": None,
                "value_area_high": None,
                "value_area_low": None,
            },
        }


def get_order_flow_provider(provider_name: Optional[str] = None) -> OrderFlowProvider:
    """
    Provider factory.

    For now, always returns safe unavailable provider.

    Later providers may include:
    - CME direct API
    - Sierra Chart / Denali bridge
    - Rithmic
    - CQG
    - dxFeed
    - broker-supported futures feed
    """

    return NoOrderFlowProvider()


def get_order_flow_snapshot(symbol: str = "XAUUSD", provider_name: Optional[str] = None) -> Dict[str, Any]:
    provider = get_order_flow_provider(provider_name=provider_name)
    return provider.get_latest_snapshot(symbol=symbol)


def evaluate_order_flow_availability(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hard safety gate.

    This function decides whether order-flow data may influence trading decisions.

    Current rule:
    - OBSERVE_ONLY always blocks decision impact.
    - Missing provider always blocks.
    - Unavailable data always blocks.
    - Missing required metrics always blocks.
    """

    metrics = snapshot.get("metrics") if isinstance(snapshot, dict) else {}
    if not isinstance(metrics, dict):
        metrics = {}

    missing_metrics = [
        key for key in REQUIRED_DECISION_METRICS
        if metrics.get(key) is None
    ]

    provider = snapshot.get("provider")
    available = bool(snapshot.get("available"))
    data_quality = snapshot.get("data_quality")
    status = snapshot.get("status")
    mode = snapshot.get("mode") or ORDER_FLOW_MODE

    if provider in (None, "", "NO_ORDER_FLOW_PROVIDER"):
        gate_status = "BLOCKED_NO_REAL_PROVIDER"
        reason = "No real COMEX/futures order-flow provider is connected."
        can_influence_decision = False

    elif not available:
        gate_status = "BLOCKED_PROVIDER_UNAVAILABLE"
        reason = "Order-flow provider exists but is currently unavailable."
        can_influence_decision = False

    elif data_quality not in ("REALTIME", "LIVE", "DELAYED_REVIEW_ONLY", "HISTORICAL_REVIEW_ONLY"):
        gate_status = "BLOCKED_BAD_DATA_QUALITY"
        reason = f"Unsupported order-flow data quality: {data_quality}."
        can_influence_decision = False

    elif missing_metrics:
        gate_status = "BLOCKED_MISSING_REQUIRED_METRICS"
        reason = f"Missing required order-flow metrics: {missing_metrics}."
        can_influence_decision = False

    elif mode == "OBSERVE_ONLY":
        gate_status = "AVAILABLE_OBSERVE_ONLY"
        reason = "Order-flow data may be available, but mode is OBSERVE_ONLY."
        can_influence_decision = False

    else:
        gate_status = "AVAILABLE_REVIEW_REQUIRED"
        reason = "Order-flow data passed technical checks, but manual review is still required before live use."
        can_influence_decision = False

    return {
        "mode": mode,
        "provider": provider,
        "available": available,
        "status": status,
        "data_quality": data_quality,
        "gate_status": gate_status,
        "can_influence_decision": can_influence_decision,
        "decision_impact": "NONE",
        "missing_required_metrics": missing_metrics,
        "reason": reason,
        "safety_rule": "ORDER_FLOW_MUST_NOT_INFLUENCE_LIVE_DECISIONS_UNLESS_GATE_AND_MANUAL_REVIEW_APPROVE",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def get_order_flow_availability_gate(symbol: str = "XAUUSD", provider_name: Optional[str] = None) -> Dict[str, Any]:
    snapshot = get_order_flow_snapshot(symbol=symbol, provider_name=provider_name)
    gate = evaluate_order_flow_availability(snapshot)

    return {
        "snapshot": snapshot,
        "gate": gate,
    }