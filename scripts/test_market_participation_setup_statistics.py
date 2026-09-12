from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from src.google_sheets_logger import (
    build_setup_outcome_payload,
)
from src.market_participation_context import (
    build_market_participation_statistics_fields,
)


def _mt5_context():
    return {
        "schema_version": 1,
        "observed_at": "2026-09-12T12:00:00+00:00",
        "symbol": "XAUUSD",
        "signal": "SELL",
        "source_coverage": "MT5_ONLY",
        "combined_state": (
            "MT5_ONLY_SELL_PRESSURE_PROXY"
        ),
        "signal_relation": "WITH_SIGNAL",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "mt5": {
            "available": True,
            "activity_state": (
                "ACCELERATING_QUOTE_ACTIVITY"
            ),
            "pressure_state": (
                "SELL_PRESSURE_PROXY"
            ),
            "quote_activity_acceleration_ratio": 1.85,
            "current_spread": 0.20,
            "windows": {
                "5s": {
                    "sample_count": 9,
                    "observed_span_seconds": 4.0,
                    "directional_imbalance": -0.78,
                    "mid_move": -1.25,
                },
                "15s": {},
                "60s": {},
            },
        },
        "rithmic": {
            "available": False,
            "status": (
                "RITHMIC_CONTEXT_CACHE_MISSING_OR_STALE"
            ),
            "data_quality": None,
            "metrics": {},
            "aggression_state": "UNAVAILABLE",
            "dom_state": "UNAVAILABLE",
        },
    }


def _mt5_rithmic_context():
    context = _mt5_context()

    context = {
        **context,
        "source_coverage": "MT5_PLUS_RITHMIC",
        "combined_state": (
            "CROSS_MARKET_SELL_ALIGNED"
        ),
        "rithmic": {
            "available": True,
            "status": "OBSERVE_ONLY_READY",
            "data_quality": "REALTIME",
            "aggression_state": "SELL_AGGRESSION",
            "dom_state": "ASK_DEPTH_DOMINANT",
            "metrics": {
                "bid_volume": 40,
                "ask_volume": 60,
                "delta": -20,
                "cumulative_delta": -125,
                "footprint_imbalance": -0.20,
                "dom_bid_depth": 100,
                "dom_ask_depth": 120,
                "dom_depth_imbalance": -0.10,
                "volume_profile_poc": 4000.0,
            },
        },
    }

    return context


def test_mt5_fields():
    fields = (
        build_market_participation_statistics_fields(
            _mt5_context()
        )
    )

    assert (
        fields[
            "participation_source_coverage"
        ]
        == "MT5_ONLY"
    )

    assert (
        fields[
            "participation_combined_state"
        ]
        == "MT5_ONLY_SELL_PRESSURE_PROXY"
    )

    assert (
        fields[
            "participation_signal_relation"
        ]
        == "WITH_SIGNAL"
    )

    assert (
        fields[
            "participation_mt5_available"
        ]
        is True
    )

    assert (
        fields[
            "participation_mt5_activity_state"
        ]
        == "ACCELERATING_QUOTE_ACTIVITY"
    )

    assert (
        fields[
            "participation_mt5_pressure_state"
        ]
        == "SELL_PRESSURE_PROXY"
    )

    assert (
        fields[
            "participation_5s_sample_count"
        ]
        == 9
    )

    assert (
        fields[
            "participation_5s_observed_span_seconds"
        ]
        == 4.0
    )

    assert (
        fields[
            "participation_5s_directional_imbalance"
        ]
        == -0.78
    )

    assert (
        fields[
            "participation_5s_mid_move"
        ]
        == -1.25
    )

    assert (
        fields[
            "participation_activity_acceleration_ratio"
        ]
        == 1.85
    )

    assert (
        fields[
            "participation_high_impact_severity"
        ]
        == "HIGH_IMPACT"
    )

    assert (
        fields[
            "participation_direction_proxy"
        ]
        == "SELL"
    )

    assert (
        fields[
            "participation_rithmic_available"
        ]
        is False
    )


def test_rithmic_quant_fields():
    fields = (
        build_market_participation_statistics_fields(
            _mt5_rithmic_context()
        )
    )

    assert (
        fields[
            "participation_source_coverage"
        ]
        == "MT5_PLUS_RITHMIC"
    )

    assert (
        fields[
            "participation_rithmic_available"
        ]
        is True
    )

    assert (
        fields[
            "participation_rithmic_status"
        ]
        == "OBSERVE_ONLY_READY"
    )

    assert (
        fields[
            "participation_rithmic_data_quality"
        ]
        == "REALTIME"
    )

    assert (
        fields[
            "participation_rithmic_aggression_state"
        ]
        == "SELL_AGGRESSION"
    )

    assert (
        fields[
            "participation_rithmic_dom_state"
        ]
        == "ASK_DEPTH_DOMINANT"
    )

    assert (
        fields[
            "participation_rithmic_bid_volume"
        ]
        == 40.0
    )

    assert (
        fields[
            "participation_rithmic_ask_volume"
        ]
        == 60.0
    )

    assert (
        fields[
            "participation_rithmic_delta"
        ]
        == -20.0
    )

    assert (
        fields[
            "participation_rithmic_cumulative_delta"
        ]
        == -125.0
    )

    assert (
        fields[
            "participation_rithmic_footprint_imbalance"
        ]
        == -0.20
    )

    assert (
        fields[
            "participation_rithmic_dom_bid_depth"
        ]
        == 100.0
    )

    assert (
        fields[
            "participation_rithmic_dom_ask_depth"
        ]
        == 120.0
    )

    assert (
        fields[
            "participation_rithmic_dom_depth_imbalance"
        ]
        == -0.10
    )

    assert (
        fields[
            "participation_rithmic_volume_profile_poc"
        ]
        == 4000.0
    )


def test_setup_outcome_payload_exports_fields():
    fields = (
        build_market_participation_statistics_fields(
            _mt5_context()
        )
    )

    fields[
        "participation_capture_event"
    ] = "SETUP_DETECTED"

    fields[
        "participation_capture_source"
    ] = "EXACT_SETUP_SNAPSHOT"

    item = {
        "setup_id": "STAT-1",
        "symbol": "XAUUSD",
        "source_events": [
            "SETUP_DETECTED",
        ],
        "strategy": "TEST",
        "signal": "SELL",
        "entry_model": "TEST",
        "session": "NEWYORK",
        "market_condition": "TRENDING",
        "score": 95,
        "entry": 4000.0,
        "sl": 4010.0,
        "tp": 3980.0,
        "nearby_strategies": [],
        **fields,
    }

    payload = (
        build_setup_outcome_payload(
            item
        )
    )

    for key, expected in fields.items():
        actual = payload.get(
            key
        )

        assert actual == expected, (
            key,
            actual,
            expected,
        )


def test_context_key_remains_legacy_only():
    source = (
        ROOT
        / "src"
        / "setup_outcome_tracker.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    start = source.index(
        "def build_context_key(item):"
    )

    end = source.index(
        "def _build_scenario_key",
        start,
    )

    body = source[
        start:end
    ]

    assert (
        "participation_"
        not in body
    )


def test_exact_setup_snapshot_reused():
    source = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "market_participation_context=("
        in source
    )

    assert (
        "setup_participation_context"
        in source
    )


def test_no_trading_authority():
    for relative_path in (
        "src/risk.py",
        "src/execution_engine.py",
        "src/candidate_rejection_recovery.py",
    ):
        source = (
            ROOT
            / relative_path
        ).read_text(
            encoding="utf-8-sig"
        )

        assert (
            "build_market_participation_statistics_fields"
            not in source
        )


if __name__ == "__main__":
    test_mt5_fields()
    test_rithmic_quant_fields()
    test_setup_outcome_payload_exports_fields()
    test_context_key_remains_legacy_only()
    test_exact_setup_snapshot_reused()
    test_no_trading_authority()

    print(
        "[PASS] Market-participation setup "
        "statistics V1 regression passed."
    )
