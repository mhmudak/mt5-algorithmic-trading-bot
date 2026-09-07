from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from src.order_flow_adapter import (
    RithmicSnapshotOrderFlowProvider,
    evaluate_order_flow_availability,
)
from src.order_flow_providers.rithmic_monitoring_bridge import (
    build_rithmic_monitoring_bridge,
)
from src.order_flow_providers.rithmic_snapshot_adapter import (
    REQUIRED_ADAPTER_METRICS,
    build_rithmic_provider_status,
)


def _fresh_state():
    now = time.time()

    return {
        "phase": (
            "PHASE_5E_RITHMIC_"
            "REALTIME_STATE_CACHE_WITH_DOM"
        ),
        "symbol": "GCQ6",
        "exchange": "COMEX",
        "system_name": "Rithmic Test",
        "state_status": "OBSERVE_ONLY_READY",
        "updated_at_epoch": now,
        "connection": {
            "login_ok": True,
            "market_data_ok": True,
        },
        "freshness": {
            "last_trade_age_seconds": 0.1,
            "last_bbo_age_seconds": 0.1,
            "last_order_book_age_seconds": 0.1,
            "has_fresh_trade": True,
            "has_fresh_bbo": True,
            "has_fresh_order_book": True,
        },
        "sample": {
            "rolling_trade_count": 25,
        },
        "latest_trade": {
            "price": 3650.0,
            "size": 5,
            "aggressor": "BUY",
            "received_at_epoch": now,
        },
        "trade_flow": {
            "rolling_buy_volume": 60,
            "rolling_sell_volume": 40,
            "rolling_total_volume": 100,
            "rolling_delta": 20,
            "session_cumulative_delta": 125,
            "rolling_imbalance_ratio": 0.20,
        },
        "volume_profile": {
            "rolling_poc_price": 3649.8,
        },
        "order_book": {
            "available": True,
            "last_received_at_epoch": now,
            "bid_depth": 120,
            "ask_depth": 100,
            "depth_imbalance": 0.090909,
            "last_update_type_name": "SOLO",
            "bid_level_count": 10,
            "ask_level_count": 10,
        },
        "adapter_compatible_metrics": {
            "bid_volume": 40,
            "ask_volume": 60,
            "delta": 20,
            "cumulative_delta": 125,
            "footprint_imbalance": 0.20,
            "dom_bid_depth": 120,
            "dom_ask_depth": 100,
            "dom_depth_imbalance": 0.090909,
            "dom_available": True,
        },
        "quality": {
            "warnings": [],
            "safe_for_live_decision": False,
            "safe_for_execution": False,
        },
    }


def test_missing_snapshot_is_not_zero():
    status = (
        build_rithmic_provider_status(
            None,
            snapshot_path="missing.json",
            stale_after_seconds=5,
        )
    )

    assert status["loaded"] is False

    assert (
        status["provider_status"]
        == "SNAPSHOT_MISSING"
    )

    assert (
        status[
            "required_adapter_metrics"
        ]
        == REQUIRED_ADAPTER_METRICS
    )

    for key in REQUIRED_ADAPTER_METRICS:
        assert (
            status[
                "adapter_metrics"
            ][key]
            is None
        )

    bridge = (
        build_rithmic_monitoring_bridge(
            status
        )
    )

    assert set(
        bridge[
            "metric_validation"
        ][
            "missing_metrics"
        ]
    ) == set(
        REQUIRED_ADAPTER_METRICS
    )

    assert (
        bridge["can_influence_decision"]
        is False
    )


def test_stale_file_cannot_stay_fresh():
    state = _fresh_state()

    old = (
        time.time()
        - 120.0
    )

    state[
        "updated_at_epoch"
    ] = old

    state[
        "latest_trade"
    ][
        "received_at_epoch"
    ] = old

    state[
        "order_book"
    ][
        "last_received_at_epoch"
    ] = old

    # Frozen booleans deliberately lie.
    state[
        "freshness"
    ][
        "has_fresh_trade"
    ] = True

    status = (
        build_rithmic_provider_status(
            state,
            snapshot_path="stale.json",
            stale_after_seconds=5,
        )
    )

    assert (
        status[
            "freshness"
        ][
            "snapshot_fresh"
        ]
        is False
    )

    assert (
        status[
            "freshness"
        ][
            "has_fresh_trade"
        ]
        is False
    )

    assert (
        status[
            "provider_status"
        ]
        == (
            "STALE_SNAPSHOT_"
            "OBSERVATION_ONLY"
        )
    )


def test_central_provider_observe_only():
    state = _fresh_state()

    with tempfile.TemporaryDirectory() as tmp:
        path = (
            Path(tmp)
            / "GCQ6_state.json"
        )

        path.write_text(
            json.dumps(state),
            encoding="utf-8",
        )

        provider = (
            RithmicSnapshotOrderFlowProvider(
                snapshot_path=path,
                rithmic_symbol="GCQ6",
                stale_after_seconds=5,
            )
        )

        snapshot = (
            provider.get_latest_snapshot(
                "XAUUSD"
            )
        )

    assert (
        snapshot["available"]
        is True
    )

    assert (
        snapshot["provider"]
        == "RITHMIC_SNAPSHOT_PROVIDER"
    )

    assert (
        snapshot["symbol"]
        == "GCQ6"
    )

    assert (
        snapshot["requested_symbol"]
        == "XAUUSD"
    )

    assert (
        snapshot[
            "metrics"
        ][
            "delta"
        ]
        == 20
    )

    assert (
        snapshot[
            "metrics"
        ][
            "dom_bid_depth"
        ]
        == 120
    )

    assert (
        snapshot[
            "decision_impact"
        ]
        == "NONE"
    )

    assert (
        snapshot[
            "can_influence_decision"
        ]
        is False
    )

    assert (
        snapshot[
            "safe_for_execution"
        ]
        is False
    )

    gate = (
        evaluate_order_flow_availability(
            snapshot
        )
    )

    assert (
        gate["gate_status"]
        == "AVAILABLE_OBSERVE_ONLY"
    )

    assert (
        gate["can_influence_decision"]
        is False
    )

    assert (
        gate["decision_impact"]
        == "NONE"
    )


def test_protocol_unknown_not_sell():
    text = (
        ROOT
        / "src"
        / "order_flow_providers"
        / "rithmic_protocol.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        (
            'aggressor = "BUY" '
            'if msg.aggressor '
            '== buy_value else "SELL"'
        )
        not in text
    )

    assert (
        'aggressor = "UNKNOWN"'
        in text
    )

    assert (
        "sell_value = getattr("
        in text
    )


def test_state_cache_phase_wording():
    text = (
        ROOT
        / "src"
        / "order_flow_features"
        / "rithmic_state_cache.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "Observe-only Phase 5C cache."
        not in text
    )

    assert (
        "Observe-only Phase 5E "
        "real-time cache with DOM."
        in text
    )


if __name__ == "__main__":
    test_missing_snapshot_is_not_zero()
    test_stale_file_cannot_stay_fresh()
    test_central_provider_observe_only()
    test_protocol_unknown_not_sell()
    test_state_cache_phase_wording()

    print(
        "[PASS] Rithmic integrity, "
        "freshness, missing-data, "
        "central adapter, and "
        "observe-only safety passed."
    )
