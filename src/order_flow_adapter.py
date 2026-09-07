import os
from pathlib import Path
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


class RithmicSnapshotOrderFlowProvider(
    OrderFlowProvider
):
    """
    Central read-only adapter for the existing
    Rithmic protocol/state-cache stack.

    It never sends, approves, blocks, sizes,
    or modifies an MT5 trade.
    """

    provider_name = (
        "RITHMIC_SNAPSHOT_PROVIDER"
    )

    def __init__(
        self,
        *,
        snapshot_path: str | Path | None = None,
        rithmic_symbol: str | None = None,
        stale_after_seconds: int | None = None,
    ):
        self.rithmic_symbol = str(
            rithmic_symbol
            or os.getenv("RITHMIC_SYMBOL", "")
        ).strip()


        if stale_after_seconds is None:
            try:
                stale_after_seconds = int(
                    os.getenv(
                        "RITHMIC_SNAPSHOT_"
                        "STALE_SECONDS",
                        "30",
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                stale_after_seconds = 30

        self.stale_after_seconds = max(
            1,
            int(stale_after_seconds),
        )

        if snapshot_path is None:
            configured_path = os.getenv(
                "RITHMIC_STATE_"
                "SNAPSHOT_PATH",
                "",
            ).strip()

            if configured_path:
                snapshot_path = Path(
                    configured_path
                )

        if snapshot_path is None:
            project_root = (
                Path(__file__)
                .resolve()
                .parents[1]
            )

            safe_symbol = (
                self.rithmic_symbol
                .replace("/", "_")
                .replace("\\", "_")
                .replace(".", "_")
            )

            snapshot_path = (
                project_root
                / "data"
                / "order_flow"
                / "rithmic"
                / (
                    f"{safe_symbol}_"
                    "phase5c_rithmic_"
                    "state_latest.json"
                )
            )

        self.snapshot_path = Path(
            snapshot_path
        )

    def _build_status(
        self,
    ) -> Dict[str, Any]:
        from src.order_flow_providers.rithmic_snapshot_adapter import (
            build_rithmic_provider_status,
            load_latest_rithmic_state,
        )

        loaded = (
            load_latest_rithmic_state(
                self.snapshot_path
            )
        )

        raw_snapshot = (
            loaded.get("snapshot")
            if loaded.get("loaded")
            else None
        )

        return (
            build_rithmic_provider_status(
                raw_snapshot,
                snapshot_path=(
                    self.snapshot_path
                ),
                stale_after_seconds=(
                    self.stale_after_seconds
                ),
            )
        )

    def is_available(self) -> bool:
        if not self.rithmic_symbol:
            return False

        status = self._build_status()

        return bool(
            status.get("loaded")
            and status.get(
                "provider_status"
            )
            == "OBSERVE_ONLY_READY"
        )

    def get_latest_snapshot(
        self,
        symbol: str,
    ) -> Dict[str, Any]:
        if not self.rithmic_symbol:
            return {
                "mode": ORDER_FLOW_MODE,
                "provider": self.provider_name,
                "symbol": None,
                "requested_symbol": symbol,
                "available": False,
                "status": "RITHMIC_SYMBOL_NOT_CONFIGURED",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "data_quality": "UNAVAILABLE",
                "decision_impact": "NONE",
                "can_influence_decision": False,
                "safe_for_live_decision": False,
                "safe_for_execution": False,
                "warning": (
                    "RITHMIC_SYMBOL must be explicitly "
                    "configured to the active CME gold "
                    "contract before Rithmic data is used."
                ),
                "metrics": {
                    key: None
                    for key in REQUIRED_DECISION_METRICS
                },
            }

        status = self._build_status()

        metrics = (
            status.get(
                "adapter_metrics"
            )
            or {}
        )

        profile = (
            status.get(
                "volume_profile"
            )
            or {}
        )

        available = bool(
            status.get("loaded")
            and status.get(
                "provider_status"
            )
            == "OBSERVE_ONLY_READY"
        )

        return {
            "mode": ORDER_FLOW_MODE,
            "provider": (
                self.provider_name
            ),
            "symbol": (
                status.get("symbol")
                or self.rithmic_symbol
            ),
            "requested_symbol": symbol,
            "exchange": (
                status.get("exchange")
            ),
            "available": available,
            "status": status.get(
                "provider_status"
            ),
            "updated_at": (
                datetime.now().isoformat(
                    timespec="seconds"
                )
            ),
            "data_quality": (
                "REALTIME"
                if available
                else "UNAVAILABLE"
            ),
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "safe_for_live_decision": False,
            "safe_for_execution": False,
            "metrics": {
                "bid_volume": (
                    metrics.get(
                        "bid_volume"
                    )
                ),
                "ask_volume": (
                    metrics.get(
                        "ask_volume"
                    )
                ),
                "delta": (
                    metrics.get("delta")
                ),
                "cumulative_delta": (
                    metrics.get(
                        "cumulative_delta"
                    )
                ),
                "footprint_imbalance": (
                    metrics.get(
                        "footprint_imbalance"
                    )
                ),
                "dom_bid_depth": (
                    metrics.get(
                        "dom_bid_depth"
                    )
                ),
                "dom_ask_depth": (
                    metrics.get(
                        "dom_ask_depth"
                    )
                ),
                "dom_depth_imbalance": (
                    metrics.get(
                        "dom_depth_imbalance"
                    )
                ),
                "volume_profile_poc": (
                    profile.get(
                        "rolling_poc_price"
                    )
                ),
                "value_area_high": None,
                "value_area_low": None,
            },
            "rithmic_status": status,
            "warning": (
                "Rithmic is registered for "
                "observe-only context. "
                "It cannot influence MT5 "
                "execution."
            ),
        }


def get_order_flow_provider(
    provider_name: Optional[str] = None,
) -> OrderFlowProvider:
    """
    Provider factory.

    Rithmic may be explicitly selected for
    observe-only context.

    Safe default remains NoOrderFlowProvider.
    """

    selected = str(
        provider_name
        or os.getenv(
            "ORDER_FLOW_PROVIDER",
            "",
        )
    ).strip().upper()

    if selected in {
        "RITHMIC",
        "RITHMIC_PROTOCOL",
        "RITHMIC_SNAPSHOT",
        "RITHMIC_SNAPSHOT_PROVIDER",
    }:
        return (
            RithmicSnapshotOrderFlowProvider()
        )

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