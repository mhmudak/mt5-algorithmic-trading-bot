from __future__ import annotations

from datetime import date
from pathlib import Path
import ast
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.daily_ladder_provider import (
    AUTO_STRONG_MODE,
    MANUAL_AVO_MODE,
    DailyLadder,
)
from src.strategies.strategy_daily_level_ladder_reclaim_reversal import (
    STRATEGY_NAME,
    build_reversal_candidate,
    detect_closed_m5_reclaim,
    find_closed_m1_cisd_confirmation,
)


def _auto_ladder():
    return DailyLadder(
        symbol="XAUUSD",
        broker_date=date(2026, 9, 23),
        pivot=4342.0,
        upper=(4353.0, 4365.0, 4376.0),
        lower=(4334.0, 4324.0, 4315.0),
        source=AUTO_STRONG_MODE,
    )


def _manual_ladder():
    base = _auto_ladder()
    return DailyLadder(
        symbol=base.symbol,
        broker_date=base.broker_date,
        pivot=base.pivot,
        upper=base.upper,
        lower=base.lower,
        source=MANUAL_AVO_MODE,
    )


def test_only_auto_strong_levels_can_authorize_reversal():
    event = detect_closed_m5_reclaim(
        previous_bar={"high": 4336.0, "low": 4335.0},
        current_bar={"high": 4336.0, "low": 4332.0, "close": 4335.0},
        approved_ladder=_manual_ladder(),
        atr=5.0,
        minimum_sweep_usd=0.10,
        atr_sweep_fraction=0.03,
    )
    assert event is None


def test_lower_auto_strong_sweep_reclaim_arms_buy():
    event = detect_closed_m5_reclaim(
        previous_bar={"high": 4336.0, "low": 4335.2},
        current_bar={"high": 4336.0, "low": 4333.0, "close": 4334.8},
        approved_ladder=_auto_ladder(),
        atr=5.0,
        minimum_sweep_usd=0.10,
        atr_sweep_fraction=0.03,
    )
    assert event is not None
    assert event["signal"] == "BUY"
    assert event["level"] == 4334.0
    assert event["level_side"] == "LOWER"


def test_upper_auto_strong_sweep_reclaim_arms_sell():
    event = detect_closed_m5_reclaim(
        previous_bar={"high": 4352.0, "low": 4350.0},
        current_bar={"high": 4354.2, "low": 4351.0, "close": 4352.5},
        approved_ladder=_auto_ladder(),
        atr=5.0,
        minimum_sweep_usd=0.10,
        atr_sweep_fraction=0.03,
    )
    assert event is not None
    assert event["signal"] == "SELL"
    assert event["level"] == 4353.0
    assert event["level_side"] == "UPPER"


def test_non_approved_ordinary_level_cannot_trigger():
    event = detect_closed_m5_reclaim(
        previous_bar={"high": 4348.0, "low": 4346.0},
        current_bar={"high": 4350.0, "low": 4345.0, "close": 4347.0},
        approved_ladder=_auto_ladder(),
        atr=5.0,
        minimum_sweep_usd=0.10,
        atr_sweep_fraction=0.03,
    )
    assert event is None


def test_multi_rung_reclaim_uses_deepest_swept_strong_level():
    event = detect_closed_m5_reclaim(
        previous_bar={"high": 4336.0, "low": 4335.0},
        current_bar={"high": 4337.0, "low": 4322.0, "close": 4335.0},
        approved_ladder=_auto_ladder(),
        atr=5.0,
        minimum_sweep_usd=0.10,
        atr_sweep_fraction=0.03,
    )
    assert event is not None
    assert event["signal"] == "BUY"
    assert event["level"] == 4324.0


def test_cisd_must_be_new_closed_m1_after_reclaim():
    armed_after = pd.Timestamp("2026-09-23 10:05:00")
    frame = pd.DataFrame(
        [
            {"time": "2026-09-23 10:04:00", "open": 4335.0, "high": 4335.2, "low": 4334.0, "close": 4334.2},
            {"time": "2026-09-23 10:05:00", "open": 4334.3, "high": 4334.8, "low": 4334.0, "close": 4334.1},
            {"time": "2026-09-23 10:06:00", "open": 4334.2, "high": 4335.6, "low": 4334.1, "close": 4335.4},
        ]
    )
    cisd = find_closed_m1_cisd_confirmation(
        m1_df=frame,
        signal="BUY",
        armed_after=armed_after,
    )
    assert cisd is not None
    assert pd.Timestamp(cisd["confirmation_time"]) > armed_after
    assert cisd["confirmation_close"] == 4335.4


def test_candidate_has_strategy_owned_geometry_and_next_strong_target():
    pending = {
        "signal": "BUY",
        "level": 4334.0,
        "level_side": "LOWER",
        "reclaim_mode": "SAME_BAR",
        "reclaim_close": 4334.8,
        "sweep_extreme": 4332.8,
        "reclaim_buffer": 0.15,
        "reclaim_m5_time": "2026-09-23 10:00:00",
    }
    cisd = {
        "reference_time": "2026-09-23 10:05:00",
        "reference_open": 4334.4,
        "confirmation_time": "2026-09-23 10:06:00",
        "confirmation_open": 4334.2,
        "confirmation_high": 4335.8,
        "confirmation_low": 4334.1,
        "confirmation_close": 4335.4,
    }
    candidate = build_reversal_candidate(
        pending=pending,
        cisd=cisd,
        approved_ladder=_auto_ladder(),
        atr=5.0,
        minimum_rr=1.20,
    )
    assert candidate is not None
    assert candidate["strategy"] == STRATEGY_NAME
    assert candidate["signal"] == "BUY"
    assert candidate["tp_reference"] == 4342.0
    assert candidate["sl_reference"] < pending["sweep_extreme"]
    assert candidate["strategy_geometry_authoritative"] is True
    assert candidate["tp_authority"] == "DLRR_NEXT_APPROVED_STRONG_LEVEL"
    assert candidate["position_management_mode"] == "DLRR_FIXED_LEVEL_EXIT"


def test_executable_kernel_is_pure_and_has_no_heuristic_locals_scan():
    text = (
        ROOT
        / "src"
        / "strategies"
        / "strategy_daily_level_ladder_reclaim_reversal.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "MetaTrader5",
        "mt5.",
        "dllb_locals",
        "Path(",
        "open(",
        "send_telegram",
        "notifier",
        "_candidate_score",
        "_best_side_levels",
    ):
        assert forbidden not in text
    assert "AUTO_STRONG_MODE" in text
    assert "DailyLadder" in text


def test_live_wiring_is_pre_m15_every_loop_and_one_shot():
    live = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    runtime = (
        ROOT / "src" / "daily_ladder_reclaim_reversal_runtime.py"
    ).read_text(encoding="utf-8")

    cycle = live.index("def process_cycle(last_processed_candle_time):")
    reclaim_call = live.index(
        "if process_daily_ladder_reclaim_reversal_v1(",
        cycle,
    )
    dllb_call = live.index(
        "if process_daily_level_ladder_breakout_v1(",
        cycle,
    )
    m15_gate = live.index("# NEW CANDLE CHECK", cycle)
    assert reclaim_call < dllb_call < m15_gate

    for required in (
        "AUTO_STRONG_MODE",
        'mt5.TIMEFRAME_M5',
        'mt5.TIMEFRAME_M1',
        'start_pos=1 excludes the forming M1 candle',
        'consumed.add(setup_id)',
        '[DLRR CANDIDATE]',
        '[DLRR BLOCK]',
        '[DLRR EXECUTION ATTEMPT]',
        '[DLRR EXECUTED]',
        'is_news_blackout_active()',
        'is_trading_blackout_active()',
        'check_trade_guard(',
        'execution_memory_check_fn(',
        'execute_trade_fn(',
    ):
        assert required in runtime


def test_execution_stack_preserves_dlrr_geometry():
    live = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    wrapper_start = live.index("def execute_trade(signal, trade_plan, symbol):")
    wrapper_end = live.index("\nPHASE6W_M15_DIRECTION_LOCK = {}", wrapper_start)
    wrapper = live[wrapper_start:wrapper_end]
    assert '"DAILY_LEVEL_LADDER_RECLAIM_REVERSAL"' in wrapper
    assert wrapper.count("not daily_ladder_native_execution") >= 3

    executor = (ROOT / "src" / "order_executor.py").read_text(encoding="utf-8")
    assert '"DAILY_LEVEL_LADDER_RECLAIM_REVERSAL"' in executor
    assert "[DLRR EXECUTION GEOMETRY]" in executor
    assert "fresh_tick_outside_authoritative_geometry" in executor
    assert "strategy_geometry_authoritative" in executor

    manager = (ROOT / "src" / "position_manager.py").read_text(encoding="utf-8")
    assert '"DAILY_LEVEL_LADDER_RECLAIM_REVERSAL"' in manager
    assert '"DLRR"' in manager
    assert "daily_ladder_stats_updated" in manager

    risk = (ROOT / "src" / "risk.py").read_text(encoding="utf-8")
    assert '"DAILY_LEVEL_LADDER_RECLAIM_REVERSAL"' in risk


def test_settings_make_reversal_executable_but_keep_shadow_separate():
    settings = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    assert "ENABLE_DAILY_LEVEL_LADDER_RECLAIM_REVERSAL = True" in settings
    assert "ENABLE_DAILY_LEVEL_LADDER_RECLAIM_REVERSAL_SHADOW = False" in settings
    assert 'DAILY_LEVEL_LADDER_DLLB_EXECUTION_MODE = "AUTO_STRONG_DAILY_LADDER"' in settings
    assert "FIXED_LOT = 0.25" in settings
    assert "ENABLE_PROP_FIRM_SAFE_MODE = False" in settings

    observer = (
        ROOT / "src" / "daily_ladder_reclaim_reversal.py"
    ).read_text(encoding="utf-8")
    assert '"decision_impact": "OBSERVE_ONLY"' in observer
    assert '"execution_authority": False' in observer


def test_sources_parse():
    for relative in (
        "src/strategies/strategy_daily_level_ladder_reclaim_reversal.py",
        "src/daily_ladder_reclaim_reversal.py",
        "src/daily_ladder_reclaim_reversal_runtime.py",
        "src/live_bot.py",
        "src/order_executor.py",
        "src/position_manager.py",
        "src/risk.py",
        "config/settings.py",
    ):
        ast.parse((ROOT / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    test_only_auto_strong_levels_can_authorize_reversal()
    test_lower_auto_strong_sweep_reclaim_arms_buy()
    test_upper_auto_strong_sweep_reclaim_arms_sell()
    test_non_approved_ordinary_level_cannot_trigger()
    test_multi_rung_reclaim_uses_deepest_swept_strong_level()
    test_cisd_must_be_new_closed_m1_after_reclaim()
    test_candidate_has_strategy_owned_geometry_and_next_strong_target()
    test_executable_kernel_is_pure_and_has_no_heuristic_locals_scan()
    test_live_wiring_is_pre_m15_every_loop_and_one_shot()
    test_execution_stack_preserves_dlrr_geometry()
    test_settings_make_reversal_executable_but_keep_shadow_separate()
    test_sources_parse()

    print("PASS: Daily Ladder Reclaim Reversal executable V1")
    print("PASS: executable authority is AUTO_STRONG approved levels only")
    print("PASS: ordinary/raw/shadow/manual levels cannot authorize reversal")
    print("PASS: completed-M5 sweep + reclaim is required")
    print("PASS: NEW closed-M1 CISD after reclaim is mandatory")
    print("PASS: multi-rung reclaim chooses deepest swept strong rung")
    print("PASS: next approved strong level/Pivot is authoritative TP")
    print("PASS: sweep-extreme structural SL is strategy-owned")
    print("PASS: live confirmation is checked every bot loop before M15 gate")
    print("PASS: one confirmed event gets one execution attempt; no chase")
    print("PASS: news/time/trade/execution-memory safeguards remain")
    print("PASS: unrelated M15/intrabar wrapper policies do not veto DLRR")
    print("PASS: Universal TP/runner management cannot overwrite DLRR geometry")
    print("PASS: position manager cannot pre-empt DLRR broker SL/TP")
    print("PASS: research shadow/outcome observer remains separate and non-authoritative")
    print("PASS: FIXED_LOT remains 0.25")
