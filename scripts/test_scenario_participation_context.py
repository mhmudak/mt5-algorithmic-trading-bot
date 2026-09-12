from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


import src.scenario_signature_confidence as scenario_module

from src.scenario_signature_confidence import (
    build_participation_key,
    build_scenario_participation_context,
    build_scenario_signature_keys,
)


def _base_setup():
    return {
        "setup_id": "SCENARIO-PART-1",
        "symbol": "XAUUSD",
        "strategy": "FAILED_FVG_REVERSAL",
        "signal": "SELL",
        "entry_model": (
            "FAILED_BULLISH_FVG_REVERSAL"
        ),
        "session": "LONDON_NY_OVERLAP",
        "market_condition": "RANGING",
        "day_of_week": "FRIDAY",
        "time_window": "NEWYORK_LATE",
        "score": 98,
        "nearby_strategies": [
            "FAILED_FVG_REVERSAL",
            "LIQUIDITY_TRAP",
        ],
        "context_key": (
            "FAILED_FVG_REVERSAL|SELL|"
            "FAILED_BULLISH_FVG_REVERSAL|"
            "LONDON_NY_OVERLAP|RANGING|"
            "FRIDAY|NEWYORK_LATE|"
            "SCORE_95_100"
        ),
        "scenario_key": (
            "XAUUSD|2026-09-12T17:15:00"
        ),
    }


def _mt5_setup():
    item = _base_setup()

    item.update(
        {
            "participation_source_coverage": (
                "MT5_ONLY"
            ),
            "participation_combined_state": (
                "MT5_ONLY_SELL_PRESSURE_PROXY"
            ),
            "participation_signal_relation": (
                "WITH_SIGNAL"
            ),
            "participation_mt5_available": True,
            "participation_mt5_activity_state": (
                "ACCELERATING_QUOTE_ACTIVITY"
            ),
            "participation_mt5_pressure_state": (
                "SELL_PRESSURE_PROXY"
            ),
            "participation_high_impact_severity": (
                "HIGH_IMPACT"
            ),
            "participation_direction_proxy": (
                "SELL"
            ),
            "participation_rithmic_available": (
                False
            ),
        }
    )

    return item


def _rithmic_setup():
    item = _mt5_setup()

    item.update(
        {
            "participation_source_coverage": (
                "MT5_PLUS_RITHMIC"
            ),
            "participation_combined_state": (
                "CROSS_MARKET_SELL_ALIGNED"
            ),
            "participation_rithmic_available": (
                True
            ),
            "participation_rithmic_aggression_state": (
                "SELL_AGGRESSION"
            ),
            "participation_rithmic_dom_state": (
                "ASK_DEPTH_DOMINANT"
            ),
        }
    )

    return item


def test_mt5_key():
    key = build_participation_key(
        _mt5_setup()
    )

    assert key == (
        "PART_V1|"
        "MT5_ONLY|"
        "WITH_SIGNAL|"
        "ACCELERATING|"
        "SELL_PRESSURE|"
        "HIGH_IMPACT|"
        "SELL"
    )


def test_rithmic_key():
    key = build_participation_key(
        _rithmic_setup()
    )

    assert key == (
        "PART_V1|"
        "MT5_PLUS_RITHMIC|"
        "WITH_SIGNAL|"
        "ACCELERATING|"
        "SELL_PRESSURE|"
        "SELL_AGGRESSION|"
        "ASK_DEPTH_DOMINANT|"
        "HIGH_IMPACT|"
        "SELL"
    )


def test_legacy_setup_gets_no_fake_key():
    assert (
        build_participation_key(
            _base_setup()
        )
        is None
    )


def test_scenario_context_preserves_old_keys():
    context = (
        build_scenario_participation_context(
            _mt5_setup()
        )
    )

    assert (
        context["context_key"]
        == _base_setup()[
            "context_key"
        ]
    )

    assert (
        context["scenario_key"]
        == _base_setup()[
            "scenario_key"
        ]
    )

    assert (
        context["participation_key"]
        is not None
    )


def test_participation_does_not_change_matching_keys():
    old_keys = (
        build_scenario_signature_keys(
            _base_setup()
        )
    )

    new_keys = (
        build_scenario_signature_keys(
            _mt5_setup()
        )
    )

    assert old_keys == new_keys


def test_raw_numbers_do_not_enter_key():
    item = _rithmic_setup()

    item.update(
        {
            "participation_5s_directional_imbalance": (
                -0.731245
            ),
            "participation_activity_acceleration_ratio": (
                2.417
            ),
            "participation_rithmic_delta": (
                -912.5
            ),
            "participation_rithmic_dom_depth_imbalance": (
                -0.42
            ),
        }
    )

    key = build_participation_key(
        item
    )

    for raw_value in (
        "-0.731245",
        "2.417",
        "-912.5",
        "-0.42",
    ):
        assert raw_value not in key


def test_analyze_report_contains_participation_metadata():
    item = _mt5_setup()

    original_enabled = (
        scenario_module
        .ENABLE_SCENARIO_SIGNATURE_CONFIDENCE
    )

    original_loader = (
        scenario_module
        .load_setup_outcomes
    )

    original_matcher = (
        scenario_module
        ._signature_matches
    )

    original_stats = (
        scenario_module
        .build_similarity_stats
    )

    try:
        scenario_module.ENABLE_SCENARIO_SIGNATURE_CONFIDENCE = True

        scenario_module.load_setup_outcomes = (
            lambda: {
                item["setup_id"]: item,
            }
        )

        scenario_module._signature_matches = (
            lambda current_item, items: (
                [item],
                "SIG_TEST",
            )
        )

        scenario_module.build_similarity_stats = (
            lambda matches: {
                "total": 5,
                "w10_rate": 0.8,
                "tp_rate": 0.6,
                "sl_rate": 0.2,
                "avg_favorable": 20.0,
                "avg_adverse": -5.0,
                "avg_recovery_swing": 10.0,
            }
        )

        report = (
            scenario_module
            .analyze_scenario_signature(
                item["setup_id"]
            )
        )

        assert (
            report["context_key"]
            == item["context_key"]
        )

        assert (
            report["scenario_key"]
            == item["scenario_key"]
        )

        assert (
            report["nearby_strategies"]
            == item["nearby_strategies"]
        )

        assert (
            report["participation_key"]
            == build_participation_key(
                item
            )
        )

        assert isinstance(
            report[
                "participation_context"
            ],
            dict,
        )

    finally:
        scenario_module.ENABLE_SCENARIO_SIGNATURE_CONFIDENCE = (
            original_enabled
        )

        scenario_module.load_setup_outcomes = (
            original_loader
        )

        scenario_module._signature_matches = (
            original_matcher
        )

        scenario_module.build_similarity_stats = (
            original_stats
        )


def test_live_event_contains_metadata():
    source = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    event_anchor = (
        'event="SCENARIO_SIGNATURE_CONFIDENCE"'
    )

    start = source.index(
        event_anchor
    )

    block = source[
        start:
        start + 3000
    ]

    for required in (
        '"context_key"',
        '"scenario_key"',
        '"nearby_strategies"',
        '"participation_key"',
        '"participation_context"',
    ):
        assert required in block


def test_research_only_no_execution_authority():
    scenario_source = (
        ROOT
        / "src"
        / "scenario_signature_confidence.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    matcher_start = (
        scenario_source.index(
            "def _signature_matches("
        )
    )

    matcher_end = (
        scenario_source.index(
            "def classify_scenario_signature(",
            matcher_start,
        )
    )

    matcher = scenario_source[
        matcher_start:
        matcher_end
    ]

    assert (
        "participation"
        not in matcher.lower()
    )

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
            "build_participation_key"
            not in source
        )


if __name__ == "__main__":
    test_mt5_key()
    test_rithmic_key()
    test_legacy_setup_gets_no_fake_key()
    test_scenario_context_preserves_old_keys()
    test_participation_does_not_change_matching_keys()
    test_raw_numbers_do_not_enter_key()
    test_analyze_report_contains_participation_metadata()
    test_live_event_contains_metadata()
    test_research_only_no_execution_authority()

    print(
        "[PASS] Scenario Participation "
        "Context V1 regression passed."
    )
