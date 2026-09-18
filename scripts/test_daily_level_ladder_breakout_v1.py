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


def _ladder(broker_date=date(2026, 9, 17)):
    return DailyLadder(
        symbol="XAUUSD",
        broker_date=broker_date,
        pivot=4290.0,
        upper=(4300.0, 4315.0, 4330.0, 4345.0),
        lower=(4275.0, 4252.0, 4239.0, 4210.0),
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
                "time": "closed",
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


def test_pivot_is_approved_execution_boundary():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4289.0,
            open_price=4289.1,
            high=4292.0,
            low=4288.8,
            close=4291.2,
        ),
        approved_ladder=_ladder(),
    )
    assert result is not None
    assert result["signal"] == "BUY"
    assert result["broken_level"] == 4290.0
    assert result["target_level"] == 4300.0
    assert result["sl_reference"] == 4286.0


def test_buy_break_targets_next_approved_level():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4299.0,
            open_price=4299.1,
            high=4302.0,
            low=4298.8,
            close=4301.2,
        ),
        approved_ladder=_ladder(),
    )
    assert result is not None
    assert result["broken_level"] == 4300.0
    assert result["target_level"] == 4315.0
    assert result["sl_reference"] == 4294.0
    assert result["tp_reference"] == 4315.0


def test_sell_break_targets_next_approved_level():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4276.0,
            open_price=4276.2,
            high=4276.4,
            low=4272.0,
            close=4273.0,
        ),
        approved_ladder=_ladder(),
    )
    assert result is not None
    assert result["signal"] == "SELL"
    assert result["broken_level"] == 4275.0
    assert result["target_level"] == 4252.0
    assert result["sl_reference"] == 4284.2
    assert result["tp_reference"] == 4252.0


def test_multi_level_m5_uses_furthest_crossed_approved_level():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4298.0,
            open_price=4298.2,
            high=4317.0,
            low=4297.8,
            close=4316.0,
            atr=5.5,
        ),
        approved_ladder=_ladder(),
    )
    assert result is not None
    assert result["broken_level"] == 4315.0
    assert result["target_level"] == 4330.0
    assert result["sl_reference"] == 4309.0


def test_tiny_body_fake_break_rejected():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4299.9,
            open_price=4300.35,
            high=4300.9,
            low=4299.7,
            close=4300.5,
        ),
        approved_ladder=_ladder(),
    )
    assert result is None


def test_forming_m5_is_ignored():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4299.0,
            open_price=4299.1,
            high=4302.0,
            low=4298.8,
            close=4301.2,
            forming_close=4400.0,
        ),
        approved_ladder=_ladder(),
    )
    assert result is not None
    assert result["broken_level"] == 4300.0
    assert result["target_level"] == 4315.0


def test_broker_date_changes_setup_identity():
    frame = _m5_frame(
        previous_close=4299.0,
        open_price=4299.1,
        high=4302.0,
        low=4298.8,
        close=4301.2,
    )
    first = evaluate_daily_level_ladder_breakout(
        m5_df=frame,
        approved_ladder=_ladder(date(2026, 9, 17)),
    )
    second = evaluate_daily_level_ladder_breakout(
        m5_df=frame,
        approved_ladder=_ladder(date(2026, 9, 18)),
    )
    assert first is not None and second is not None
    assert first["setup_id"] != second["setup_id"]


def test_already_cleared_level_requires_fresh_cross():
    result = evaluate_daily_level_ladder_breakout(
        m5_df=_m5_frame(
            previous_close=4300.8,
            open_price=4300.9,
            high=4303.0,
            low=4300.5,
            close=4302.2,
        ),
        approved_ladder=_ladder(),
    )
    assert result is None


def test_strategy_has_no_legacy_level_authority():
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
    ):
        assert forbidden not in text
    assert "approved_ladder" in text


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
    assert "load_manual_avo_ladder(" in block
    assert "approved_ladder=approved_ladder" in block
    assert "calculate_shadow_levels(" in block
    assert "execution_authority=False" in block


def test_live_execution_preserves_next_level_tp_and_guards():
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
        "authoritative next-level TP",
    ):
        assert required in block
    assert "apply_universal_tp_ladder" not in block
    assert "approved_source={candidate.get('daily_approved_source')}" in block
    assert "broker_date={candidate.get('daily_broker_date')}" in block
    assert "Daily Level Ladder Breakout" in block
    assert "candidate.get('broken_level')" in block
    assert "candidate.get('target_level')" in block


def test_transient_d1_failure_and_provider_invalid_semantics():
    text = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    start = text.index("def process_daily_level_ladder_breakout_v1(")
    end = text.index("def process_cycle(last_processed_candle_time):", start)
    block = text[start:end]

    d1_index = block.index("d1_rates = mt5.copy_rates_from_pos(")
    auto_build_index = block.index(
        "approved_ladder = build_auto_composite_execution_ladder("
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

    # MT5/D1 retrieval / broker-date failure stays retryable and must happen
    # before either AUTO or MANUAL execution-provider construction.
    pre_provider_region = block[d1_index:auto_build_index]
    assert "closed M5 remains unconsumed" in pre_provider_region
    assert d1_index < auto_build_index < manual_load_index

    # Any provider/configuration invalidity (AUTO or MANUAL) consumes the
    # already-closed M5 so a later repair cannot retroactively trade it.
    invalid_region = block[provider_invalid_index:evaluator_index]
    assert 'runtime["last_closed_m5_time"] = latest_closed_time' in invalid_region
    assert "execution disabled for current broker date" in invalid_region
    assert "PROVIDER_INVALID" in invalid_region

    # Successful evaluation still consumes once before all downstream guards.
    assert evaluator_index < final_consume_index
    post_evaluation = block[final_consume_index:]
    assert '"last_closed_m5_time"' in post_evaluation
    assert "Downstream RR/news/time/guard/execution-memory rejection" in block
    assert "Do not chase an old" in block


def test_risk_fixed_lot_and_sources_parse():
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

    for relative in (
        "src/daily_ladder_provider.py",
        "src/strategies/strategy_daily_level_ladder_breakout.py",
        "src/risk.py",
        "src/live_bot.py",
    ):
        ast.parse((ROOT / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    test_pivot_is_approved_execution_boundary()
    test_buy_break_targets_next_approved_level()
    test_sell_break_targets_next_approved_level()
    test_multi_level_m5_uses_furthest_crossed_approved_level()
    test_tiny_body_fake_break_rejected()
    test_forming_m5_is_ignored()
    test_broker_date_changes_setup_identity()
    test_already_cleared_level_requires_fresh_cross()
    test_strategy_has_no_legacy_level_authority()
    test_live_integration_is_pre_m15_and_once_per_closed_m5()
    test_live_execution_preserves_next_level_tp_and_guards()
    test_transient_d1_failure_and_provider_invalid_semantics()
    test_risk_fixed_lot_and_sources_parse()

    print("PASS: Daily Level Ladder Breakout V1")
    print("PASS: approved variable ladder is sole DLLB execution input")
    print("PASS: legacy Five-Level / PDH / PDL execution authority removed")
    print("PASS: BUY/SELL approved-ladder direction")
    print("PASS: next approved daily level is authoritative TP")
    print("PASS: 40% source-to-target structural SL")
    print("PASS: one closed M5 candle can clear multiple approved levels")
    print("PASS: furthest crossed approved level becomes source")
    print("PASS: tiny-body fake break rejected")
    print("PASS: forming M5 candle excluded")
    print("PASS: broker-date rollover changes setup identity")
    print("PASS: M5 processor runs before M15 gate")
    print("PASS: startup does not retro-trade old M5 break")
    print("PASS: fresh live RR/news/time/trade/execution-memory guards preserved")
    print("PASS: Universal TP ladder does not replace approved next-level TP")
    print("PASS: fresh crossing required; already-cleared level cannot retrade")
    print("PASS: transient D1/evaluation failure can retry")
    print("PASS: invalid AUTO/MANUAL provider state consumes M5 and cannot be retro-traded")
    print("PASS: downstream rejection remains one-shot / no chasing")
    print("PASS: AUTO shadow has observation only")
    print("PASS: FIXED_LOT remains 0.25")
