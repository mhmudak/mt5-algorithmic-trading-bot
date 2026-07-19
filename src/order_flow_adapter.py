from datetime import datetime
from typing import Any, Dict, Optional


ORDER_FLOW_MODE = "OBSERVE_ONLY"


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