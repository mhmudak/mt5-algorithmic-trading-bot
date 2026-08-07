from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from config import settings
from src.key_level_tp_ladder import (
    apply_key_level_tp_ladder,
    calculate_rr,
)
from src.risk import (
    STRATEGY_SL_REFERENCE_MODELS,
    calculate_trade_plan,
)


STRATEGY = "HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY"
ENTRY = 4240.50
INTENDED_SL = 4245.14
INTENDED_TP = 4230.29
MIN_EXECUTION_RR = 1.10


def build_test_dataframe() -> pd.DataFrame:
    row_count = int(settings.BREAKOUT_LOOKBACK) + 12

    rows = []

    for index in range(row_count):
        rows.append(
            {
                "open": 4240.00,
                "high": 4311.00,
                "low": 4200.00,
                "close": 4240.00,
                "atr_14": 10.00,
                "time": index,
            }
        )

    return pd.DataFrame(rows)


def build_signal_data() -> dict:
    return {
        "strategy": STRATEGY,
        "signal": "SELL",
        "entry_model": "DOUBLE_TOP_NECKLINE_RETEST_SELL",
        "sl_model": "NECKLINE_RETEST_EXTREME_SL",
        "target_model": "FIXED_RR_TARGET_KEY_LEVEL_LADDER_ELIGIBLE",
        "entry_reference": ENTRY,
        "sl_reference": INTENDED_SL,
        "tp_reference": INTENDED_TP,
        "rr": 2.20,
        "risk_reward": 2.20,
        "neckline": 4240.81,
        "retest_high": 4244.44,
        "retest_close": ENTRY,
    }


def test_strategy_sl_reference_is_preserved() -> dict:
    assert STRATEGY in STRATEGY_SL_REFERENCE_MODELS

    df = build_test_dataframe()
    tick = SimpleNamespace(
        bid=ENTRY,
        ask=ENTRY + 0.10,
    )

    plan = calculate_trade_plan(
        df=df,
        signal="SELL",
        tick=tick,
        account_balance=50000.00,
        signal_data=build_signal_data(),
    )

    assert plan is not None

    assert plan["entry_price"] == ENTRY
    assert plan["stop_loss"] == INTENDED_SL
    assert plan["take_profit"] == INTENDED_TP

    original_rr = calculate_rr(
        "SELL",
        plan["entry_price"],
        plan["stop_loss"],
        plan["take_profit"],
    )

    assert original_rr is not None
    assert original_rr >= settings.DTB_MIN_RR
    assert original_rr == 2.20

    return plan


def test_close_barrier_cannot_create_low_execution_rr(
    original_plan: dict,
) -> None:
    signal_data = build_signal_data()

    # A close barrier can produce a TP1 near the generic 1.10R threshold.
    signal_data["pivot_level"] = 4234.85

    adjusted = apply_key_level_tp_ladder(
        df=build_test_dataframe(),
        signal="SELL",
        trade_plan=dict(original_plan),
        signal_data=signal_data,
        strategy_name=STRATEGY,
        session_name="NEWYORK",
        market_condition="TRENDING",
    )

    final_rr = calculate_rr(
        "SELL",
        adjusted["entry_price"],
        adjusted["stop_loss"],
        adjusted["take_profit"],
    )

    strategy_floor = settings.KLT_STRATEGY_MIN_EXECUTION_RR[
        STRATEGY
    ]

    assert final_rr is not None
    assert final_rr >= strategy_floor
    assert final_rr >= MIN_EXECUTION_RR

    if not adjusted.get("key_level_tp_ladder_applied"):
        assert adjusted["take_profit"] == original_plan["take_profit"]
        assert (
            "strategy_execution_rr_floor"
            in adjusted.get("key_level_tp_ladder_reason", "")
        )


def test_safe_barrier_can_still_use_ladder(
    original_plan: dict,
) -> None:
    signal_data = build_signal_data()

    # This barrier leaves enough reward for a safe TP1.
    signal_data["pivot_level"] = 4233.00

    adjusted = apply_key_level_tp_ladder(
        df=build_test_dataframe(),
        signal="SELL",
        trade_plan=dict(original_plan),
        signal_data=signal_data,
        strategy_name=STRATEGY,
        session_name="NEWYORK",
        market_condition="TRENDING",
    )

    assert adjusted.get("key_level_tp_ladder_applied") is True

    final_rr = calculate_rr(
        "SELL",
        adjusted["entry_price"],
        adjusted["stop_loss"],
        adjusted["take_profit"],
    )

    strategy_floor = settings.KLT_STRATEGY_MIN_EXECUTION_RR[
        STRATEGY
    ]

    assert final_rr is not None
    assert final_rr >= strategy_floor
    assert final_rr >= MIN_EXECUTION_RR


def main() -> None:
    original_plan = test_strategy_sl_reference_is_preserved()

    test_close_barrier_cannot_create_low_execution_rr(
        original_plan,
    )

    test_safe_barrier_can_still_use_ladder(
        original_plan,
    )

    print(
        "[PASS] HTF double-top/bottom retest SL preservation "
        "and TP-ladder RR floor passed."
    )


if __name__ == "__main__":
    main()
