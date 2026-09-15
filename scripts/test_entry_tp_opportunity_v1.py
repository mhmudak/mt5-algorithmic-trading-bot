from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pandas as pd

from src.daily_level_context import (
    calculate_classic_pivots_from_ohlc,
    calculate_daily_context_from_d1,
    calculate_five_level_daily_range_from_ohlc,
)

from src.entry_tp_opportunity import (
    build_entry_tp_opportunity,
    format_entry_tp_opportunity,
)

from src.universal_tp_ladder import (
    build_universal_tp_ladder,
)


ROOT = Path(__file__).resolve().parents[1]


def _sample_df(
    *,
    include_prior_extension=True,
    current_intrabar_low=4200.0,
    current_intrabar_tick_volume=999999,
):
    rows = []

    base = 4305.0

    for index in range(30):
        center = (
            base
            - index * 0.35
        )

        low = center - 1.0
        high = center + 1.0

        rows.append(
            {
                "time": index,
                "open": center + 0.2,
                "high": high,
                "low": low,
                "close": center - 0.2,
                "atr_14": 10.0,
                "tick_volume": (
                    100
                    + index * 3
                ),
            }
        )

    if include_prior_extension:
        rows[15]["low"] = 4266.25
        rows[14]["low"] = 4269.50
        rows[16]["low"] = 4269.10

    # Current/incomplete candle must never become
    # swing or tick-activity evidence.
    rows[-1]["low"] = (
        current_intrabar_low
    )

    rows[-1]["tick_volume"] = (
        current_intrabar_tick_volume
    )

    return pd.DataFrame(
        rows
    )


def _d1_df(
    *,
    previous_close=4292.10,
):
    return pd.DataFrame(
        [
            {
                "time": "2026-09-13",
                "open": 4300.0,
                "high": 4320.0,
                "low": 4260.0,
                "close": 4300.0,
            },
            {
                # Latest completed D1.
                "time": "2026-09-14",
                "open": 4300.0,
                "high": 4340.0,
                "low": 4240.0,
                "close": previous_close,
            },
            {
                # Current/forming D1.
                "time": "2026-09-15",
                "open": 4290.0,
                "high": 4300.0,
                "low": 4260.0,
                "close": 4275.0,
            },
        ]
    )


def _signal_data():
    return {
        "signal": "SELL",
        "strategy": "ORDER_BLOCK",
        "entry_model": (
            "OB_RETEST_CONTINUATION"
        ),
        "entry_reference": 4280.70,
        "sl_reference": 4294.39,
        "tp_reference": 4271.36,
        "target_model": (
            "MEASURED_ORDER_BLOCK_MOVE"
        ),
    }


def _trade_plan():
    return {
        "signal": "SELL",
        "entry_price": 4278.88,
        "stop_loss": 4294.39,
        "take_profit": 4271.36,
    }


def _result(
    *,
    include_prior_extension=True,
    previous_close=4292.10,
    current_intrabar_tick_volume=999999,
):
    return build_entry_tp_opportunity(
        df=_sample_df(
            include_prior_extension=(
                include_prior_extension
            ),
            current_intrabar_tick_volume=(
                current_intrabar_tick_volume
            ),
        ),
        d1_df=_d1_df(
            previous_close=previous_close,
        ),
        signal="SELL",
        signal_data=_signal_data(),
        trade_plan=_trade_plan(),
        required_rr=1.05,
    )


def test_classic_pivot_math():
    result = (
        calculate_classic_pivots_from_ohlc(
            4400.0,
            4300.0,
            4350.0,
        )
    )

    levels = result["levels"]

    assert levels["P"] == 4350.0
    assert levels["R1"] == 4400.0
    assert levels["S1"] == 4300.0
    assert levels["R2"] == 4450.0
    assert levels["S2"] == 4250.0
    assert levels["R3"] == 4500.0
    assert levels["S3"] == 4200.0


def test_levels_mq5_extended_formula():
    result = (
        calculate_five_level_daily_range_from_ohlc(
            4400.0,
            4300.0,
            4350.0,
            high_diap=2000.0,
            low_diap=500.0,
        )
    )

    assert result["mode"] == "EXTENDED"

    levels = result["levels"]

    assert levels["R1"] == 4369.10
    assert levels["S1"] == 4330.90

    assert levels["R2"] == 4430.90
    assert levels["S2"] == 4269.10

    assert levels["R3"] == 4492.70
    assert levels["S3"] == 4207.30

    assert levels["R4"] == 4530.90
    assert levels["S4"] == 4169.10

    assert levels["R5"] == 4592.70
    assert levels["S5"] == 4107.30


def test_native_d1_uses_completed_candle():
    result = (
        calculate_daily_context_from_d1(
            _d1_df(),
            high_diap=2000.0,
            low_diap=500.0,
        )
    )

    assert (
        result["source"]
        == "BROKER_COMPLETED_D1"
    )

    assert (
        result["previous_day_high"]
        == 4340.0
    )

    assert (
        result["previous_day_low"]
        == 4240.0
    )

    assert (
        result["previous_day_close"]
        == 4292.10
    )

    assert (
        result["previous_day_close"]
        != 4275.0
    )


def test_universal_ladder_tp1_rr_signature_and_reuse():
    ladder = build_universal_tp_ladder(
        signal="SELL",
        entry=4278.88,
        sl=4294.39,
        tp3=4271.36,
    )

    assert isinstance(
        ladder,
        list,
    )

    assert len(ladder) >= 3

    prices = [
        float(
            item["price"]
        )
        for item in ladder[:3]
    ]

    assert prices == [
        4275.12,
        4273.24,
        4271.36,
    ]

    universal_source = (
        ROOT
        / "src"
        / "universal_tp_ladder.py"
    ).read_text(
        encoding="utf-8"
    )

    expected_tp1_rr_call = (
        "tp1_rr = (\n"
        "        calculate_rr(\n"
        "            signal,\n"
        "            entry,\n"
        "            sl,\n"
        "            tp1,\n"
        "        )"
    )

    assert (
        expected_tp1_rr_call
        in universal_source
    )

    observer_source = (
        ROOT
        / "src"
        / "entry_tp_opportunity.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "build_universal_tp_ladder"
        in observer_source
    )

    assert (
        "UNIVERSAL_TP1_REWARD_FRACTION"
        not in observer_source
    )

    assert (
        "UNIVERSAL_TP2_REWARD_FRACTION"
        not in observer_source
    )


def test_entry_degradation_preserved():
    result = _result()

    assert result["available"] is True

    assert (
        result["entry_quality"]
        == "DEGRADED"
    )

    assert (
        result["reference_entry"]
        == 4280.70
    )

    assert (
        result["actual_entry"]
        == 4278.88
    )

    assert (
        result["entry_drift"]
        == 1.82
    )

    assert (
        result["executable_rr"]
        == 0.48
    )


def test_tp1_tp2_tp3_match_real_universal_ladder():
    result = _result()

    targets = {
        item["name"]: item
        for item in result[
            "tp_targets"
        ]
    }

    assert (
        targets["TP1"]["price"]
        == 4275.12
    )

    assert (
        targets["TP2"]["price"]
        == 4273.24
    )

    assert (
        targets["TP3"]["price"]
        == 4271.36
    )

    assert (
        targets["TP3"]["role"]
        == "BASE"
    )


def test_daily_level_zone_matching_and_factual_path():
    result = _result()

    targets = {
        item["name"]: item
        for item in result[
            "tp_targets"
        ]
    }

    assert (
        targets["TP2"][
            "level_name"
        ]
        == "D-S1"
    )

    assert (
        targets["TP2"][
            "level_price"
        ]
        == 4273.0
    )

    assert (
        targets["TP2"][
            "barrier_count"
        ]
        == 0
    )

    assert (
        targets["TP2"][
            "path_label"
        ]
        == "CLEAR"
    )

    assert (
        targets["TP3"][
            "barrier_count"
        ]
        >= 1
    )

    assert "BARRIER" in (
        targets["TP3"][
            "path_label"
        ]
    )


def test_tp4_structural_runner():
    result = _result()

    targets = {
        item["name"]: item
        for item in result[
            "tp_targets"
        ]
    }

    assert "TP4" in targets

    assert (
        targets["TP4"]["price"]
        == 4266.25
    )

    assert (
        targets["TP4"]["role"]
        == "RUNNER"
    )


def test_daily_level_can_supply_tp4():
    result = _result(
        include_prior_extension=False,
        previous_close=4288.0,
    )

    targets = {
        item["name"]: item
        for item in result[
            "tp_targets"
        ]
    }

    assert "TP4" in targets

    assert (
        targets["TP4"]["price"]
        == 4268.90
    )

    assert (
        result[
            "extension_source"
        ]
        == "D1_FIVE_LEVEL"
    )

    assert (
        targets["TP4"][
            "level_name"
        ]
        == "D-S1"
    )


def test_target_reach_score_is_uncalibrated():
    result = _result()

    assert (
        result["target_reach_model"]
        == "UNCALIBRATED_HEURISTIC_V1"
    )

    assert (
        result["target_reach_calibrated"]
        is False
    )

    targets = result[
        "tp_targets"
    ]

    for item in targets:
        score = item[
            "target_reach_score"
        ]

        assert isinstance(
            score,
            int,
        )

        assert 0 <= score <= 100

        assert (
            item[
                "target_reach_calibrated"
            ]
            is False
        )

        assert (
            item[
                "target_reach_model"
            ]
            == "UNCALIBRATED_HEURISTIC_V1"
        )

        assert (
            item[
                "target_distance_atr"
            ]
            is not None
        )

    scores = {
        item["name"]: item[
            "target_reach_score"
        ]
        for item in targets
    }

    assert (
        scores["TP1"]
        > scores["TP4"]
    )


def test_closed_m15_momentum_and_tick_activity():
    result = _result()

    features = result[
        "market_features"
    ]

    assert (
        features["source"]
        == "LATEST_CLOSED_M15"
    )

    assert (
        features["atr"]
        == 10.0
    )

    assert (
        features[
            "directional_move_atr"
        ]
        is not None
    )

    assert (
        features[
            "tick_volume_available"
        ]
        is True
    )

    assert (
        features[
            "tick_volume_z"
        ]
        is not None
    )


def test_forming_candle_volume_is_excluded():
    a = _result(
        current_intrabar_tick_volume=1,
    )

    b = _result(
        current_intrabar_tick_volume=99999999,
    )

    assert (
        a["market_features"][
            "tick_volume_z"
        ]
        == b["market_features"][
            "tick_volume_z"
        ]
    )

    a_scores = [
        item[
            "target_reach_score"
        ]
        for item in a[
            "tp_targets"
        ]
    ]

    b_scores = [
        item[
            "target_reach_score"
        ]
        for item in b[
            "tp_targets"
        ]
    ]

    assert (
        a_scores
        == b_scores
    )


def test_current_intrabar_is_not_extension():
    result = build_entry_tp_opportunity(
        df=_sample_df(
            include_prior_extension=False,
            current_intrabar_low=4200.0,
        ),
        d1_df=None,
        signal="SELL",
        signal_data=_signal_data(),
        trade_plan=_trade_plan(),
        required_rr=1.05,
    )

    assert (
        result["extension_tp"]
        is None
        or result["extension_tp"]
        != 4200.0
    )


def test_inputs_are_not_mutated():
    signal_data = _signal_data()
    trade_plan = _trade_plan()

    original_signal_data = deepcopy(
        signal_data
    )

    original_trade_plan = deepcopy(
        trade_plan
    )

    build_entry_tp_opportunity(
        df=_sample_df(),
        d1_df=_d1_df(),
        signal="SELL",
        signal_data=signal_data,
        trade_plan=trade_plan,
        required_rr=1.05,
    )

    assert (
        signal_data
        == original_signal_data
    )

    assert (
        trade_plan
        == original_trade_plan
    )


def test_authority_is_display_only():
    result = _result()

    assert (
        result["decision_impact"]
        == "DISPLAY_ONLY"
    )

    assert result["can_execute"] is False
    assert result["can_block_trade"] is False
    assert result["can_modify_score"] is False
    assert result["can_modify_risk"] is False

    assert (
        result["can_modify_entry_sl_tp"]
        is False
    )

    assert (
        result["can_modify_required_rr"]
        is False
    )

    assert (
        result["can_modify_recovery"]
        is False
    )


def test_compact_formatter_uses_factual_path_and_uncal_score():
    result = _result()

    text = format_entry_tp_opportunity(
        result
    )

    assert (
        "🎯 TP CONTEXT | TRS=UNCAL"
        in text
    )

    assert (
        "TP1 4275.12"
        in text
    )

    assert (
        "TP2 4273.24"
        in text
    )

    assert (
        "D-S1"
        in text
    )

    assert (
        "TP3 4271.36"
        in text
    )

    assert (
        "BASE"
        in text
    )

    assert (
        "TP4 4266.25"
        in text
    )

    assert (
        "RUNNER"
        in text
    )

    assert (
        "TRS "
        in text
    )

    assert (
        "CLEAR"
        in text
    )

    assert (
        "Entry DEGRADED -1.82"
        in text
    )

    assert (
        "| HIGH"
        not in text
    )

    assert (
        "| MED"
        not in text
    )

    assert (
        "| LOW"
        not in text
    )

    assert len(
        text.splitlines()
    ) <= 7


def test_daily_context_is_shared_module():
    pivots_source = (
        ROOT
        / "src"
        / "pivots.py"
    ).read_text(
        encoding="utf-8"
    )

    daily_source = (
        ROOT
        / "src"
        / "daily_level_context.py"
    ).read_text(
        encoding="utf-8"
    )

    observer_source = (
        ROOT
        / "src"
        / "entry_tp_opportunity.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "def calculate_daily_pivots("
        in pivots_source
    )

    assert (
        "TP CONTEXT V1.1"
        not in pivots_source
    )

    assert (
        "calculate_daily_context_from_d1"
        in daily_source
    )

    assert (
        "from src.daily_level_context import"
        in observer_source
    )


def test_live_bot_native_d1_integration():
    text = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8"
    )

    helper_start = text.index(
        "def _entry_tp_opportunity_block_fail_open("
    )

    helper_end = text.index(
        "def notify_rejected_candidate_if_relevant(",
        helper_start,
    )

    helper = text[
        helper_start:
        helper_end
    ]

    assert (
        "mt5.TIMEFRAME_D1"
        in helper
    )

    assert (
        "copy_rates_from_pos"
        in helper
    )

    assert (
        "d1_df=d1_df"
        in helper
    )

    assert (
        text.count(
            "_entry_tp_opportunity_block_fail_open("
        )
        == 4
    )

    mtf_start = text.index(
        "            if strong_mtf_candidate:"
    )

    mtf_end = text.index(
        "        if not execution_allowed:",
        mtf_start,
    )

    mtf_block = text[
        mtf_start:
        mtf_end
    ]

    assert (
        "_entry_tp_opportunity_block_fail_open("
        in mtf_block
    )

    assert (
        "signal_data=candidate"
        in mtf_block
    )

    assert (
        "trade_plan=shadow_trade_plan"
        in mtf_block
    )

    assert (
        "required_rr=required_rr"
        in mtf_block
    )

    assert (
        "if mtf_entry_tp_block:"
        in mtf_block
    )

    assert (
        "+ mtf_entry_tp_block"
        in mtf_block
    )


def test_score_weights_and_fixed_lot():
    settings = (
        ROOT
        / "config"
        / "settings.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "FIXED_LOT = 0.25"
        in settings
    )

    from config.settings import (
        ENTRY_TP_TARGET_REACH_WEIGHT_DISTANCE,
        ENTRY_TP_TARGET_REACH_WEIGHT_STRUCTURE,
        ENTRY_TP_TARGET_REACH_WEIGHT_MOMENTUM,
        ENTRY_TP_TARGET_REACH_WEIGHT_TICK_ACTIVITY,
        ENTRY_TP_TARGET_REACH_WEIGHT_ENTRY,
    )

    total = (
        ENTRY_TP_TARGET_REACH_WEIGHT_DISTANCE
        + ENTRY_TP_TARGET_REACH_WEIGHT_STRUCTURE
        + ENTRY_TP_TARGET_REACH_WEIGHT_MOMENTUM
        + ENTRY_TP_TARGET_REACH_WEIGHT_TICK_ACTIVITY
        + ENTRY_TP_TARGET_REACH_WEIGHT_ENTRY
    )

    assert abs(
        total - 1.0
    ) < 1e-9


def main():
    test_classic_pivot_math()
    test_levels_mq5_extended_formula()
    test_native_d1_uses_completed_candle()
    test_universal_ladder_tp1_rr_signature_and_reuse()
    test_entry_degradation_preserved()
    test_tp1_tp2_tp3_match_real_universal_ladder()
    test_daily_level_zone_matching_and_factual_path()
    test_tp4_structural_runner()
    test_daily_level_can_supply_tp4()
    test_target_reach_score_is_uncalibrated()
    test_closed_m15_momentum_and_tick_activity()
    test_forming_candle_volume_is_excluded()
    test_current_intrabar_is_not_extension()
    test_inputs_are_not_mutated()
    test_authority_is_display_only()
    test_compact_formatter_uses_factual_path_and_uncal_score()
    test_daily_context_is_shared_module()
    test_live_bot_native_d1_integration()
    test_score_weights_and_fixed_lot()

    print(
        "PASS: Entry / TP Opportunity V1.2"
    )

    print(
        "PASS: shared Daily Level Context engine"
    )

    print(
        "PASS: pivots.py restored to classic pivot responsibility"
    )

    print(
        "PASS: exact levels.mq5 S1-S5/R1-R5 preserved"
    )

    print(
        "PASS: real Universal TP ladder reused"
    )

    print(
        "PASS: universal TP1/TP2/TP3 RR signature verified"
    )

    print(
        "PASS: TP1/TP2/TP3 prices preserved"
    )

    print(
        "PASS: TP4 remains display-only runner"
    )

    print(
        "PASS: factual CLEAR/BARRIER path labels"
    )

    print(
        "PASS: Target Reach Score is explicitly uncalibrated"
    )

    print(
        "PASS: ATR-normalized target distance"
    )

    print(
        "PASS: closed-M15 directional momentum/efficiency"
    )

    print(
        "PASS: relative broker tick-activity context"
    )

    print(
        "PASS: current incomplete candle excluded"
    )

    print(
        "PASS: observer remains DISPLAY_ONLY"
    )

    print(
        "PASS: no execution/risk/recovery/RR authority"
    )

    print(
        "PASS: FIXED_LOT unchanged"
    )


if __name__ == "__main__":
    main()
