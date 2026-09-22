from __future__ import annotations

import json
import tempfile
from pathlib import Path

from src.order_flow_features.rithmic_anti_fakeout_bridge import (
    build_bridge_anti_fakeout,
)


ROOT = Path(__file__).resolve().parents[1]


def snapshot(
    *,
    updated_at: float,
    dom_imbalance: float,
    bid_depth: int,
    ask_depth: int,
    top_bid: float,
    top_ask: float,
    flow_imbalance: float = 0.40,
    footprint_imbalance: float = 0.35,
    first_price: float = 2400.0,
    last_price: float = 2400.5,
    fresh: bool = True,
    test_environment: bool = False,
):
    return {
        "symbol": "GCZ6",
        "exchange": "COMEX",
        "system_name": (
            "Rithmic Test"
            if test_environment
            else "Rithmic Paper Trading"
        ),
        "is_test_environment": test_environment,
        "updated_at_epoch": updated_at,
        "freshness": {
            "has_fresh_trade": fresh,
            "has_fresh_bbo": fresh,
            "has_fresh_order_book": fresh,
        },
        "sample": {
            "rolling_trade_count": 30,
            "order_book_count": int(updated_at),
        },
        "latest_trade": {
            "received_at_epoch": updated_at,
        },
        "trade_flow": {
            "rolling_total_volume": 100,
            "rolling_delta": 40,
            "session_cumulative_delta": 200,
            "rolling_imbalance_ratio": flow_imbalance,
            "first_trade_price": first_price,
            "last_trade_price": last_price,
        },
        "adapter_compatible_metrics": {
            "footprint_imbalance": footprint_imbalance,
        },
        "footprint": {
            "candles": [
                {
                    "delta": 40,
                    "total_volume": 100,
                }
            ],
        },
        "order_book": {
            "available": True,
            "last_received_at_epoch": updated_at,
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "depth_imbalance": dom_imbalance,
            "top_bid_price": top_bid,
            "top_ask_price": top_ask,
        },
        "volume_profile": {
            "rolling_poc_price": 2400.3,
        },
        "quality": {
            "safe_for_live_decision": not test_environment,
            "safe_for_execution": False,
        },
    }


def test_history_persists_and_deduplicates():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "history.json"

        items = [
            snapshot(
                updated_at=1.0,
                dom_imbalance=0.75,
                bid_depth=700,
                ask_depth=100,
                top_bid=2400.0,
                top_ask=2400.1,
            ),
            snapshot(
                updated_at=2.0,
                dom_imbalance=0.70,
                bid_depth=680,
                ask_depth=120,
                top_bid=2400.1,
                top_ask=2400.2,
            ),
            snapshot(
                updated_at=3.0,
                dom_imbalance=0.72,
                bid_depth=690,
                ask_depth=110,
                top_bid=2400.2,
                top_ask=2400.3,
            ),
        ]

        for item in items:
            result = build_bridge_anti_fakeout(
                item,
                history_path=path,
                signal="BUY",
                session="NEW_YORK_OPEN",
                tick_size=0.1,
            )

        assert result["bridge_history"]["history_snapshot_count"] == 3
        assert result["dom"]["sample_count"] == 3
        assert result["dom"]["persistent"] is True

        duplicate = build_bridge_anti_fakeout(
            items[-1],
            history_path=path,
            signal="BUY",
            session="NEW_YORK_OPEN",
            tick_size=0.1,
        )

        assert (
            duplicate["bridge_history"]["history_snapshot_count"]
            == 3
        )
        assert (
            duplicate["bridge_history"]["current_snapshot_was_duplicate"]
            is True
        )
        assert duplicate["dom"]["sample_count"] == 3

        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
        assert len(payload["snapshots"]) == 3


def test_test_environment_never_becomes_decision_grade():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "history.json"

        result = build_bridge_anti_fakeout(
            snapshot(
                updated_at=10.0,
                dom_imbalance=0.80,
                bid_depth=900,
                ask_depth=100,
                top_bid=2400.0,
                top_ask=2400.1,
                test_environment=True,
            ),
            history_path=path,
            signal="BUY",
            session="NEW_YORK_OPEN",
        )

        assert result["data_grade"] == (
            "TEST_ENVIRONMENT_OBSERVATION_ONLY"
        )
        assert result["production_data_eligible"] is False
        assert result["decision_impact"] == "NONE"
        assert result["can_influence_decision"] is False
        assert result["safe_for_execution"] is False


def test_empty_snapshot_is_safe():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "history.json"

        result = build_bridge_anti_fakeout(
            None,
            history_path=path,
            signal="SELL",
            session="LONDON_OPEN",
        )

        assert result["status"] == "STALE"
        assert result["production_data_eligible"] is False
        assert result["safe_for_execution"] is False


def test_phase5g_source_has_observe_only_wiring():
    path = (
        ROOT
        / "scripts"
        / "build_phase5g_rithmic_monitoring_bridge.py"
    )
    source = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    required = (
        "build_bridge_anti_fakeout",
        'bridge["anti_fakeout"]',
        "phase5g_rithmic_anti_fakeout_history.json",
        "format_bridge_anti_fakeout_text",
        "--signal",
        "--session",
        "--tick-size",
    )

    for marker in required:
        assert marker in source, marker

    assert "execute_trade(" not in source
    assert "order_send(" not in source
    assert "live_bot" not in source


def main():
    test_history_persists_and_deduplicates()
    test_test_environment_never_becomes_decision_grade()
    test_empty_snapshot_is_safe()
    test_phase5g_source_has_observe_only_wiring()

    print("PASS: Phase 5G anti-fakeout history persists across bridge runs")
    print("PASS: unchanged snapshots do not fake DOM persistence")
    print("PASS: Rithmic Test remains observation-only")
    print("PASS: missing snapshot fails safe as STALE")
    print("PASS: Phase 5G wiring has no MT5 execution authority")


if __name__ == "__main__":
    main()
