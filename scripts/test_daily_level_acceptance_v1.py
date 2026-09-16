from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import ast
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from src.daily_level_acceptance import (
    build_session_orb_daily_level_watch,
    daily_level_acceptance_ready,
)
from src.execution_engine import (
    ExecutionEngine,
)


def _d1_df():
    return pd.DataFrame(
        [
            {
                "time": "old",
                "open": 4270.0,
                "high": 4300.0,
                "low": 4200.0,
                "close": 4250.0,
            },
            {
                "time": "completed",
                "open": 4280.0,
                "high": 4355.50,
                "low": 4253.77,
                "close": 4297.98,
            },
            {
                "time": "forming",
                "open": 4298.0,
                "high": 4360.0,
                "low": 4280.0,
                "close": 4350.60,
            },
        ]
    )


def _m15_df(
    close=4350.60,
):
    return pd.DataFrame(
        [
            {
                "open": 4340.0,
                "high": 4345.0,
                "low": 4335.0,
                "close": 4342.0,
            },
            {
                "open": 4342.0,
                "high": 4348.0,
                "low": 4339.0,
                "close": 4346.0,
            },
            {
                "open": 4346.0,
                "high": 4352.0,
                "low": 4344.0,
                "close": close,
            },
            {
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
            },
        ]
    )


class _Tick:
    def __init__(
        self,
        *,
        bid,
        ask,
    ):
        self.bid = bid
        self.ask = ask


def test_buy_near_r1_waits():
    result = (
        build_session_orb_daily_level_watch(
            d1_df=_d1_df(),
            signal="BUY",
            entry_price=4350.60,
            atr=5.64,
        )
    )

    assert result["available"] is True
    assert result["required"] is True
    assert result["level_name"] == "P-R1"
    assert result["level_price"] == 4351.06
    assert result["state"] == "TESTING"


def test_buy_small_poke_is_not_accepted():
    result = (
        build_session_orb_daily_level_watch(
            d1_df=_d1_df(),
            signal="BUY",
            entry_price=4351.10,
            atr=5.64,
        )
    )

    assert result["required"] is True
    assert result["state"] == "BREAK_UNCONFIRMED"


def test_buy_meaningful_break_clears_r1():
    result = (
        build_session_orb_daily_level_watch(
            d1_df=_d1_df(),
            signal="BUY",
            entry_price=4351.50,
            atr=5.64,
        )
    )

    assert result["required"] is False
    assert (
        result["state"]
        == "NO_NEARBY_OPPOSING_D1_LEVEL"
    )


def test_accepted_level_does_not_mask_next_unresolved_barrier():
    result = (
        build_session_orb_daily_level_watch(
            d1_df=_d1_df(),
            signal="BUY",
            entry_price=4366.0,
            atr=200.0,
        )
    )

    # ATR=200 -> minimum acceptance distance is 10.0.
    # At 4366:
    # - classic R1 4351.06 is accepted by +14.94
    # - PDH 4355.50 is accepted by +10.50
    # - the next unresolved five-level resistance is D-R2 4380.28
    assert result["required"] is True
    assert result["level_name"] == "D-R2"
    assert result["level_price"] == 4380.28
    assert result["level_price"] > 4366.0


def test_sell_near_s1_waits():
    result = (
        build_session_orb_daily_level_watch(
            d1_df=_d1_df(),
            signal="SELL",
            entry_price=4249.80,
            atr=5.64,
        )
    )

    assert result["available"] is True
    assert result["required"] is True
    assert result["level_name"] == "P-S1"
    assert result["level_price"] == 4249.33
    assert result["state"] == "TESTING"


def test_sell_small_poke_is_not_accepted():
    result = (
        build_session_orb_daily_level_watch(
            d1_df=_d1_df(),
            signal="SELL",
            entry_price=4249.20,
            atr=5.64,
        )
    )

    assert result["required"] is True
    assert result["state"] == "BREAK_UNCONFIRMED"


def test_tick_ready_is_directional_for_buy_and_sell():
    buy_not_ready = (
        daily_level_acceptance_ready(
            signal="BUY",
            tick=_Tick(
                bid=4351.20,
                ask=4351.25,
            ),
            level=4351.06,
            min_distance=0.30,
        )
    )

    assert buy_not_ready[0] is False

    buy_ready = (
        daily_level_acceptance_ready(
            signal="BUY",
            tick=_Tick(
                bid=4351.35,
                ask=4351.40,
            ),
            level=4351.06,
            min_distance=0.30,
        )
    )

    assert buy_ready[0] is True

    sell_not_ready = (
        daily_level_acceptance_ready(
            signal="SELL",
            tick=_Tick(
                bid=4249.10,
                ask=4249.15,
            ),
            level=4249.33,
            min_distance=0.30,
        )
    )

    assert sell_not_ready[0] is False

    sell_ready = (
        daily_level_acceptance_ready(
            signal="SELL",
            tick=_Tick(
                bid=4248.95,
                ask=4249.00,
            ),
            level=4249.33,
            min_distance=0.30,
        )
    )

    assert sell_ready[0] is True


def test_daily_level_wait_state_cannot_be_bypassed_by_m15_process_setups():
    engine = ExecutionEngine()

    setup = {
        "strategy": "SESSION_ORB_RETEST",
        "signal": "BUY",
        "entry_model": "ORB_RETEST_RECLAIM",
        "state": "WAIT_ORB_TICK_BREAKOUT",
        "created_at": datetime.utcnow(),
        "expires_at": (
            datetime.utcnow()
            + timedelta(
                minutes=60
            )
        ),
        "data": {
            "strategy": "SESSION_ORB_RETEST",
            "signal": "BUY",
            "entry_model": "ORB_RETEST_RECLAIM",
            "daily_level_acceptance_level": 4351.06,
        },
        "wait_reason": (
            "Waiting for SESSION_ORB_RETEST "
            "daily-level acceptance"
        ),
    }

    engine.active_setups.append(
        setup
    )

    ready = engine.process_setups(
        _m15_df(),
        4350.60,
        5.64,
    )

    assert ready == []
    assert (
        setup["state"]
        == "WAIT_ORB_TICK_BREAKOUT"
    )


def test_normal_orb_waiter_is_not_globally_skipped():
    engine = ExecutionEngine()

    setup = {
        "strategy": "ORB",
        "signal": "BUY",
        "entry_model": "FAST_CONTINUATION",
        "state": "WAIT_ORB_TICK_BREAKOUT",
        "created_at": datetime.utcnow(),
        "expires_at": (
            datetime.utcnow()
            + timedelta(
                minutes=60
            )
        ),
        "data": {
            "strategy": "ORB",
            "signal": "BUY",
            "entry_model": "FAST_CONTINUATION",
            "orb_high": 4350.0,
            "orb_low": 4340.0,
        },
        "wait_reason": (
            "Waiting for ORB tick breakout continuation"
        ),
    }

    engine.active_setups.append(
        setup
    )

    ready = engine.process_setups(
        _m15_df(),
        4350.60,
        5.64,
    )

    assert ready == [setup]
    assert setup["state"] == "READY"


def test_existing_orb_profile_settings_are_unchanged():
    settings = (
        ROOT
        / "config"
        / "settings.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        'ORB_TICK_BREAKOUT_WATCH_STRATEGIES = [\n'
        '    "ORB",\n'
        '    "ORB_V00",\n'
        ']'
        in settings
    )

    assert (
        "ORB_TICK_BREAKOUT_MIN_DISTANCE = 0.30"
        in settings
    )

    assert (
        "ORB_TICK_BREAKOUT_REQUIRE_M5_CONFIRMATION = False"
        in settings
    )

    assert (
        "SESSION_ORB_DAILY_LEVEL_REQUIRE_M5_CONFIRMATION = True"
        in settings
    )


def test_daily_level_profile_uses_level_specific_m5_confirmation():
    text = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "def daily_level_m5_acceptance_confirmation_ok("
        in text
    )

    helper_start = text.index(
        "def daily_level_m5_acceptance_confirmation_ok("
    )

    helper_end = text.index(
        "def extra_entry_confirmation_ok(",
        helper_start,
    )

    helper = text[
        helper_start:
        helper_end
    ]

    assert "mt5.TIMEFRAME_M5" in helper
    assert "> level" in helper
    assert "< level" in helper

    processor_start = text.index(
        "def process_wait_orb_tick_breakout_setups("
    )

    processor_end = text.index(
        "def process_wait_tick_sniper_setups(",
        processor_start,
    )

    processor = text[
        processor_start:
        processor_end
    ]

    assert (
        "if is_daily_level_acceptance:"
        in processor
    )

    assert (
        "daily_level_m5_acceptance_confirmation_ok("
        in processor
    )

    assert (
        "extra_entry_confirmation_ok("
        in processor
    )


def test_reused_watcher_keeps_full_execution_checks():
    text = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8",
    )

    start = text.index(
        "def process_wait_orb_tick_breakout_setups("
    )

    end = text.index(
        "def process_wait_tick_sniper_setups(",
        start,
    )

    block = text[start:end]

    for required in (
        "calculate_trade_plan(",
        "calculate_rr_value(",
        "check_trade_guard(",
        "is_news_blackout_active()",
        "is_trading_blackout_active()",
        "is_trade_blocked_by_execution_memory(",
        "execute_trade(",
        "DAILY_LEVEL_ACCEPTANCE",
        "ORB_TICK_BREAKOUT",
    ):
        assert required in block


def test_persistence_has_no_authority():
    module = (
        ROOT
        / "src"
        / "daily_level_acceptance.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "persistence"
        not in module.lower()
    )

    settings = (
        ROOT
        / "config"
        / "settings.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "Persistence remains observation-only"
        in settings
    )


def test_sources_parse_and_fixed_lot_unchanged():
    for relative in (
        "src/daily_level_acceptance.py",
        "src/execution_engine.py",
        "src/live_bot.py",
    ):
        ast.parse(
            (
                ROOT
                / relative
            ).read_text(
                encoding="utf-8",
            )
        )

    settings = (
        ROOT
        / "config"
        / "settings.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "FIXED_LOT = 0.25"
        in settings
    )


if __name__ == "__main__":
    test_buy_near_r1_waits()
    test_buy_small_poke_is_not_accepted()
    test_buy_meaningful_break_clears_r1()
    test_accepted_level_does_not_mask_next_unresolved_barrier()
    test_sell_near_s1_waits()
    test_sell_small_poke_is_not_accepted()
    test_tick_ready_is_directional_for_buy_and_sell()
    test_daily_level_wait_state_cannot_be_bypassed_by_m15_process_setups()
    test_normal_orb_waiter_is_not_globally_skipped()
    test_existing_orb_profile_settings_are_unchanged()
    test_daily_level_profile_uses_level_specific_m5_confirmation()
    test_reused_watcher_keeps_full_execution_checks()
    test_persistence_has_no_authority()
    test_sources_parse_and_fixed_lot_unchanged()

    print("PASS: SESSION ORB Daily-Level Acceptance V1 hardened")
    print("PASS: nearest unresolved opposing D1 level selected")
    print("PASS: accepted level cannot mask the next barrier")
    print("PASS: BUY and SELL symmetry covered")
    print("PASS: small level poke remains unconfirmed")
    print("PASS: M15 process_setups cannot bypass daily-level watcher")
    print("PASS: normal ORB WAIT_ORB behavior remains unchanged")
    print("PASS: M5 confirmation is tied to the actual D1 level")
    print("PASS: fresh trade plan / RR / guards preserved")
    print("PASS: ORB / ORB_V00 profile settings unchanged")
    print("PASS: Persistence remains observation-only")
    print("PASS: FIXED_LOT remains 0.25")
