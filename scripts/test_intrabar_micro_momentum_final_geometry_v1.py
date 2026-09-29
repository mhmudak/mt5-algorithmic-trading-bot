from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intrabar_micro_momentum_execution_geometry import (
    apply_authoritative_micro_momentum_geometry,
    build_authoritative_micro_momentum_geometry,
)


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def plan(signal):
    return {
        "strategy": "INTRABAR_MICRO_MOMENTUM",
        "signal": signal,
        "entry_price": 4287.32,
        "stop_loss": 4286.82 if signal == "BUY" else 4287.82,
        "take_profit": 4334.32 if signal == "BUY" else 4240.32,
        "execution_geometry_authority": "INTRABAR_MICRO_MOMENTUM",
        "micro_momentum_execution_sl_distance": 0.50,
        "micro_momentum_execution_tp_distance": 2.00,
    }


def main():
    print("[MICRO MOMENTUM FINAL EXECUTION GEOMETRY TEST V1]")

    buy = build_authoritative_micro_momentum_geometry(
        signal="BUY",
        trade_plan=plan("BUY"),
        execution_price=4287.46,
    )
    print("\n[BUY INCIDENT REPAIR]")
    print(buy)
    assert_true(buy["entry_price"] == 4287.46, buy)
    assert_true(buy["stop_loss"] == 4286.96, buy)
    assert_true(buy["take_profit"] == 4289.46, buy)

    sell = build_authoritative_micro_momentum_geometry(
        signal="SELL",
        trade_plan=plan("SELL"),
        execution_price=4287.10,
    )
    print("\n[SELL MIRROR]")
    print(sell)
    assert_true(sell["stop_loss"] == 4287.60, sell)
    assert_true(sell["take_profit"] == 4285.10, sell)

    request = {"price": 4287.46, "sl": 4286.82, "tp": 4334.32}
    trade_plan = plan("BUY")
    applied = apply_authoritative_micro_momentum_geometry(
        signal="BUY",
        trade_plan=trade_plan,
        request=request,
        execution_price=4287.46,
    )
    print("\n[FINAL REQUEST OVERRIDE]")
    print({"request": request, "trade_plan": trade_plan})
    assert_true(applied is not None, applied)
    assert_true(request["sl"] == 4286.96, request)
    assert_true(request["tp"] == 4289.46, request)
    assert_true(trade_plan["take_profit"] == 4289.46, trade_plan)

    other = {
        "strategy": "FVG_CE_MITIGATION",
        "execution_geometry_authority": "INTRABAR_MICRO_MOMENTUM",
        "micro_momentum_execution_sl_distance": 0.50,
        "micro_momentum_execution_tp_distance": 2.00,
    }
    assert_true(
        build_authoritative_micro_momentum_geometry(
            signal="BUY",
            trade_plan=other,
            execution_price=100.0,
        ) is None,
        other,
    )

    live_text = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    executor_text = (ROOT / "src" / "order_executor.py").read_text(encoding="utf-8")

    print("\n[STATIC WIRING]")
    assert_true(
        'trade_plan["execution_geometry_authority"] = strategy_name' in live_text,
        "geometry authority declaration missing",
    )
    assert_true(
        'trade_plan["micro_momentum_execution_sl_distance"]' in live_text,
        "intended SL distance missing",
    )
    assert_true(
        'trade_plan["micro_momentum_execution_tp_distance"]' in live_text,
        "intended TP distance missing",
    )
    assert_true(
        "apply_authoritative_micro_momentum_geometry(" in executor_text,
        "final order request geometry hook missing",
    )
    assert_true(
        "[MICRO MOMENTUM FINAL GEOMETRY]" in executor_text,
        "final geometry audit log missing",
    )

    print(
        "\nPASS: Micro Momentum owns final pre-send entry/SL/TP geometry, "
        "the incident TP=4334.32 is corrected to TP=4289.46 at a fresh "
        "BUY price of 4287.46, and non-momentum strategies are untouched."
    )


if __name__ == "__main__":
    main()
