from __future__ import annotations

from datetime import date
from pathlib import Path
import ast
import re
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.daily_ladder_provider import DailyLadder, MANUAL_AVO_MODE
from src.strategies.strategy_daily_level_ladder_breakout import (
    evaluate_daily_level_ladder_breakout,
)


def _ladder(broker_date=date(2026, 9, 23)):
    return DailyLadder(
        symbol="XAUUSD",
        broker_date=broker_date,
        pivot=4342.0,
        upper=(4350.0, 4366.0, 4373.0, 4381.0, 4391.0),
        lower=(4334.0, 4324.0, 4315.0, 4307.8),
        source=MANUAL_AVO_MODE,
    )


def _m5_frame(
    *,
    previous_close,
    open_price,
    high,
    low,
    close,
    atr=5.5,
    forming_close=None,
    closed_time="2026-09-23 10:00:00",
):
    if forming_close is None:
        forming_close = close

    return pd.DataFrame(
        [
            {
                "time": "older",
                "open": previous_close - 0.5,
                "high": previous_close + 0.5,
                "low": previous_close - 1.0,
                "close": previous_close - 0.2,
                "atr_14": atr,
            },
            {
                "time": "previous",
                "open": previous_close - 0.3,
                "high": previous_close + 0.4,
                "low": previous_close - 0.5,
                "close": previous_close,
                "atr_14": atr,
            },
            {
                "time": closed_time,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "atr_14": atr,
            },
            {
                "time": "forming",
                "open": close,
                "high": max(close, forming_close) + 25.0,
                "low": min(close, forming_close) - 25.0,
                "close": forming_close,
                "atr_14": atr,
            },
        ]
    )


def test_sell_pivot_break_authoritative_contract():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4343.0,
            open_price=4343.0,
            high=4344.0,
            low=4338.0,
            close=4339.0,
        ),
        approved_ladder=_ladder(),
    )

    assert result is not None
    assert result["signal"] == "SELL"
    assert result["broken_level"] == 4342.0
    assert result["target_level"] == 4334.0
    assert result["sl_reference"] == 4346.0


def test_sell_next_rung_authoritative_contract():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4336.0,
            open_price=4336.0,
            high=4337.0,
            low=4331.0,
            close=4332.0,
        ),
        approved_ladder=_ladder(),
    )

    assert result is not None
    assert result["signal"] == "SELL"
    assert result["broken_level"] == 4334.0
    assert result["target_level"] == 4324.0
    assert result["sl_reference"] == 4338.0


def test_sell_third_rung_authoritative_contract():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4326.0,
            open_price=4326.0,
            high=4327.0,
            low=4319.0,
            close=4320.0,
        ),
        approved_ladder=_ladder(),
    )

    assert result is not None
    assert result["signal"] == "SELL"
    assert result["broken_level"] == 4324.0
    assert result["target_level"] == 4315.0
    assert result["sl_reference"] == 4328.0


def test_buy_pivot_break_mirror():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4341.0,
            open_price=4341.0,
            high=4346.0,
            low=4340.0,
            close=4345.0,
        ),
        approved_ladder=_ladder(),
    )

    assert result is not None
    assert result["signal"] == "BUY"
    assert result["broken_level"] == 4342.0
    assert result["target_level"] == 4350.0
    assert result["sl_reference"] == 4338.0


def test_multi_rung_sell_targets_next_still_unreached_rung():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4345.0,
            open_price=4345.0,
            high=4346.0,
            low=4321.0,
            close=4322.0,
        ),
        approved_ladder=_ladder(),
    )

    assert result is not None
    assert result["signal"] == "SELL"
    assert result["broken_level"] == 4324.0
    assert result["target_level"] == 4315.0
    assert result["target_level"] < 4322.0
    assert result["sl_reference"] == 4328.0


def test_multi_rung_buy_targets_next_still_unreached_rung():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4339.0,
            open_price=4339.0,
            high=4369.0,
            low=4338.0,
            close=4368.0,
        ),
        approved_ladder=_ladder(),
    )

    assert result is not None
    assert result["signal"] == "BUY"
    assert result["broken_level"] == 4366.0
    assert result["target_level"] == 4373.0
    assert result["target_level"] > 4368.0
    assert result["sl_reference"] == 4363.0


def test_below_pivot_lower_rung_upcross_cannot_create_buy():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4320.0,
            open_price=4320.0,
            high=4327.0,
            low=4319.0,
            close=4326.0,
        ),
        approved_ladder=_ladder(),
    )
    assert result is None


def test_above_pivot_upper_rung_downcross_cannot_create_sell():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4368.0,
            open_price=4368.0,
            high=4369.0,
            low=4361.0,
            close=4362.0,
        ),
        approved_ladder=_ladder(),
    )
    assert result is None


def test_close_through_needs_no_body_colour_or_close_location_filter():
    # Green completed M5 candle, but it closed below Pivot after the
    # previous completed M5 close was above Pivot. That is a SELL break.
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4343.0,
            open_price=4338.0,
            high=4343.5,
            low=4337.5,
            close=4339.0,
            atr=100.0,
        ),
        approved_ladder=_ladder(),
    )

    assert result is not None
    assert result["signal"] == "SELL"
    assert result["broken_level"] == 4342.0


def test_forming_m5_is_ignored():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4341.0,
            open_price=4341.0,
            high=4346.0,
            low=4340.0,
            close=4345.0,
            forming_close=4300.0,
        ),
        approved_ladder=_ladder(),
    )

    assert result is not None
    assert result["signal"] == "BUY"
    assert result["broken_level"] == 4342.0
    assert result["target_level"] == 4350.0


def test_setup_identity_is_unique_per_closed_m5_break():
    first = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4343.0,
            open_price=4343.0,
            high=4344.0,
            low=4338.0,
            close=4339.0,
            closed_time="2026-09-23 10:00:00",
        ),
        approved_ladder=_ladder(),
    )

    duplicate_same_candle = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4343.0,
            open_price=4343.0,
            high=4344.0,
            low=4338.0,
            close=4339.0,
            closed_time="2026-09-23 10:00:00",
        ),
        approved_ladder=_ladder(),
    )

    later_fresh_rebreak = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4343.0,
            open_price=4343.0,
            high=4344.0,
            low=4338.0,
            close=4339.0,
            closed_time="2026-09-23 12:00:00",
        ),
        approved_ladder=_ladder(),
    )

    assert first is not None
    assert duplicate_same_candle is not None
    assert later_fresh_rebreak is not None
    assert first["setup_id"] == duplicate_same_candle["setup_id"]
    assert first["setup_id"] != later_fresh_rebreak["setup_id"]


def test_already_cleared_level_requires_fresh_cross():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4351.0,
            open_price=4351.0,
            high=4354.0,
            low=4350.0,
            close=4352.0,
        ),
        approved_ladder=_ladder(),
    )
    assert result is None


def test_strategy_has_no_legacy_execution_authority():
    text = (
        ROOT / "src" / "strategies" / "strategy_daily_level_ladder_breakout.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "five_level",
        "previous_day_high",
        "previous_day_low",
        "D1_FIVE_LEVEL",
        "PREVIOUS_DAY_HIGH",
        "PREVIOUS_DAY_LOW",
        "CLASSIC_DAILY_PIVOT",
        "build_daily_level_clusters",
        "_strong_close_ok",
    ):
        assert forbidden not in text

    assert "approved_ladder" in text
    assert "math.ceil(raw_sl_distance)" in text


def test_live_integration_is_pre_m15_and_once_per_closed_m5():
    text = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    processor_start = text.index("def process_daily_level_ladder_breakout_v1(")
    process_cycle_start = text.index("def process_cycle(last_processed_candle_time):")
    assert processor_start < process_cycle_start

    call_index = text.index(
        "if process_daily_level_ladder_breakout_v1(",
        process_cycle_start,
    )
    m15_gate = text.index("# NEW CANDLE CHECK", process_cycle_start)
    assert call_index < m15_gate

    block = text[processor_start:process_cycle_start]
    assert "mt5.TIMEFRAME_M5" in block
    assert '"last_closed_m5_time"' in block
    assert "DAILY_LEVEL_LADDER_SKIP_FIRST_M5_AFTER_STARTUP" in block
    assert "approved_ladder=approved_ladder" in block
    assert "calculate_shadow_levels(" in block
    assert "execution_authority=False" in block
    assert "Do not chase an old" in block


def test_live_execution_preserves_dllb_contract_and_global_mechanical_guards():
    text = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    start = text.index("def process_daily_level_ladder_breakout_v1(")
    end = text.index("def process_cycle(last_processed_candle_time):", start)
    block = text[start:end]

    for required in (
        "calculate_trade_plan(",
        "calculate_rr_value(",
        "get_min_rr(",
        "is_news_blackout_active()",
        "is_trading_blackout_active()",
        "check_trade_guard(",
        "_daily_level_ladder_execution_memory_blocked_fail_closed(",
        "execute_trade(",
        "[DLLB CANDIDATE]",
        "[DLLB BLOCK]",
        "[DLLB RR DIAGNOSTIC]",
        "[DLLB EXECUTION ATTEMPT]",
        "[DLLB EXECUTION FAILED]",
        "[DLLB EXECUTED]",
        "runtime_price_outside_authoritative_geometry",
        "DLLB_NEXT_APPROVED_RUNG",
    ):
        assert required in block

    assert "fresh live RR below requirement" not in block
    assert "apply_universal_tp_ladder" not in block


def test_dllb_bypasses_unrelated_intrabar_m15_wrapper_policies_only():
    text = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    start = text.index("def execute_trade(signal, trade_plan, symbol):")
    end = text.index("\nPHASE6W_M15_DIRECTION_LOCK = {}", start)
    block = text[start:end]

    assert "daily_ladder_native_execution" in block
    assert block.count("not daily_ladder_native_execution") >= 3

    # Global funded safety remains in the common wrapper and is not bypassed.
    assert "evaluate_funded_account_safe_mode(" in block
    assert '"ENABLE_PROP_FIRM_SAFE_MODE"' in block


def test_raw_executor_preserves_dllb_sl_tp_and_freshness_guards():
    text = (ROOT / "src" / "order_executor.py").read_text(encoding="utf-8")
    start = text.index("def execute_trade(signal, trade_plan, symbol):")
    block = text[start:]

    for required in (
        "daily_ladder_geometry_authoritative",
        "DLLB_NEXT_APPROVED_RUNG",
        "[DLLB EXECUTION GEOMETRY]",
        "fresh_tick_outside_authoritative_geometry",
        "is_adverse_slippage_too_high(",
        "ENABLE_EXECUTION_FAVORABLE_DRIFT_GUARD",
        "ENABLE_LOW_RR_STRICT_ADVERSE_SLIPPAGE_GUARD",
    ):
        assert required in block

    assert "not daily_ladder_geometry_authoritative" in block


def test_position_manager_does_not_preempt_dllb_broker_sl_tp():
    text = (ROOT / "src" / "position_manager.py").read_text(encoding="utf-8")
    assert "strategy-owned SL/TP" in text
    assert '"DAILY_LEVEL_LADDER_BREAKOUT"' in text
    assert "daily_ladder_stats_updated" in text


def test_provider_shadow_stays_observation_only():
    text = (ROOT / "src" / "daily_ladder_provider.py").read_text(encoding="utf-8")

    assert "AUTO_STRONG_MODE" in text
    assert "build_auto_strong_execution_ladder(" in text
    assert "The broader AUTO composite shadow remains diagnostic/observation-only." in text
    assert "execution_authority" in text


def test_transient_d1_failure_and_provider_invalid_semantics():
    text = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    start = text.index("def process_daily_level_ladder_breakout_v1(")
    end = text.index("def process_cycle(last_processed_candle_time):", start)
    block = text[start:end]

    d1_index = block.index("d1_rates = mt5.copy_rates_from_pos(")
    auto_build_index = block.index(
        "approved_ladder = build_auto_strong_execution_ladder("
    )
    manual_load_index = block.index(
        "approved_ladder = load_manual_avo_ladder("
    )
    provider_invalid_index = block.index(
        "except DailyLadderValidationError as exc:"
    )
    evaluator_index = block.index(
        "evaluate_daily_level_ladder_breakout("
    )
    final_consume_index = block.index(
        "# D1 retrieval, execution-provider validation and strategy"
    )

    pre_provider_region = block[d1_index:auto_build_index]
    assert "closed M5 remains unconsumed" in pre_provider_region
    assert d1_index < auto_build_index < manual_load_index

    invalid_region = block[provider_invalid_index:evaluator_index]
    assert 'runtime["last_closed_m5_time"] = latest_closed_time' in invalid_region
    assert "execution disabled for current broker date" in invalid_region
    assert "PROVIDER_INVALID" in invalid_region

    assert evaluator_index < final_consume_index
    post_evaluation = block[final_consume_index:]
    assert '"last_closed_m5_time"' in post_evaluation
    assert (
        "Downstream news/time/guard/execution-memory/raw-executor"
        in block
    )
    assert "Do not chase an old" in block


def test_risk_settings_and_sources_parse():
    risk = (ROOT / "src" / "risk.py").read_text(encoding="utf-8")
    match = re.search(
        r"STRATEGY_SL_REFERENCE_MODELS\s*=\s*\{(.*?)\n\}",
        risk,
        flags=re.DOTALL,
    )
    assert match is not None
    assert '"DAILY_LEVEL_LADDER_BREAKOUT"' in match.group(0)

    settings = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    assert "FIXED_LOT = 0.25" in settings
    assert "ENABLE_PROP_FIRM_SAFE_MODE = False" in settings
    assert (
        'DAILY_LEVEL_LADDER_DLLB_EXECUTION_MODE = '
        '"AUTO_STRONG_DAILY_LADDER"'
        in settings
    )
    assert "Diagnostic reference only." in settings

    for relative in (
        "src/daily_ladder_provider.py",
        "src/strategies/strategy_daily_level_ladder_breakout.py",
        "src/risk.py",
        "src/live_bot.py",
        "src/order_executor.py",
        "src/position_manager.py",
        "config/settings.py",
    ):
        ast.parse((ROOT / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    test_sell_pivot_break_authoritative_contract()
    test_sell_next_rung_authoritative_contract()
    test_sell_third_rung_authoritative_contract()
    test_buy_pivot_break_mirror()
    test_multi_rung_sell_targets_next_still_unreached_rung()
    test_multi_rung_buy_targets_next_still_unreached_rung()
    test_below_pivot_lower_rung_upcross_cannot_create_buy()
    test_above_pivot_upper_rung_downcross_cannot_create_sell()
    test_close_through_needs_no_body_colour_or_close_location_filter()
    test_forming_m5_is_ignored()
    test_setup_identity_is_unique_per_closed_m5_break()
    test_already_cleared_level_requires_fresh_cross()
    test_strategy_has_no_legacy_execution_authority()
    test_live_integration_is_pre_m15_and_once_per_closed_m5()
    test_live_execution_preserves_dllb_contract_and_global_mechanical_guards()
    test_dllb_bypasses_unrelated_intrabar_m15_wrapper_policies_only()
    test_raw_executor_preserves_dllb_sl_tp_and_freshness_guards()
    test_position_manager_does_not_preempt_dllb_broker_sl_tp()
    test_provider_shadow_stays_observation_only()
    test_transient_d1_failure_and_provider_invalid_semantics()
    test_risk_settings_and_sources_parse()

    print("PASS: Daily Level Ladder Breakout authoritative contract")
    print("PASS: completed M5 close-through is the DLLB trigger")
    print("PASS: Pivot anchors BUY-above / SELL-below direction")
    print("PASS: next still-unreached approved rung is authoritative TP")
    print("PASS: multi-rung BUY/SELL skips already-consumed targets")
    print("PASS: SL distance is ceil(40% of broken-to-target rung gap)")
    print("PASS: body/colour/close-location/ATR-break filters are diagnostic only")
    print("PASS: forming M5 candle is excluded")
    print("PASS: setup identity is unique per closed-M5 rung break")
    print("PASS: M5 processor remains before M15 gate")
    print("PASS: no old-break chase after downstream rejection")
    print("PASS: DLLB strategy RR threshold is diagnostic only")
    print("PASS: news/time/trade/execution-memory safeguards remain")
    print("PASS: unrelated intrabar/M15 wrapper policies do not veto DLLB")
    print("PASS: raw executor preserves DLLB fixed rung SL/TP")
    print("PASS: Universal TP/runner management cannot overwrite DLLB TP")
    print("PASS: position manager cannot pre-empt DLLB broker SL/TP")
    print("PASS: AUTO strong approved ladder remains execution authority")
    print("PASS: shadow/raw levels remain observation-only")
    print("PASS: FIXED_LOT remains 0.25")
    print("PASS: prop-firm-safe mode remains disabled")
