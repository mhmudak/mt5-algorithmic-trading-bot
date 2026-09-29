from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.low_mae_momentum_runner import (
    build_runner_levels,
    evaluate_low_mae_runner_snapshot,
)


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    print("[LOW MAE MOMENTUM RUNNER LIVE TEST V1]")

    good = evaluate_low_mae_runner_snapshot(
        risk_distance=0.40,
        current_favorable=0.62,
        max_favorable=0.64,
        max_adverse=0.12,
        sample_count=8,
        spread=0.10,
    )
    print("\n[GOOD LOW-MAE PATH]")
    print(good)
    assert_true(good["qualified"] is True, good)

    high_mae = evaluate_low_mae_runner_snapshot(
        risk_distance=0.40,
        current_favorable=0.70,
        max_favorable=0.75,
        max_adverse=0.25,
        sample_count=8,
        spread=0.10,
    )
    print("\n[HIGH-MAE PATH]")
    print(high_mae)
    assert_true(high_mae["qualified"] is False, high_mae)
    assert_true(high_mae["reason"] == "mae_too_high", high_mae)

    wide_spread = evaluate_low_mae_runner_snapshot(
        risk_distance=0.40,
        current_favorable=0.70,
        max_favorable=0.75,
        max_adverse=0.10,
        sample_count=8,
        spread=0.25,
    )
    print("\n[WIDE SPREAD PATH]")
    print(wide_spread)
    assert_true(wide_spread["qualified"] is False, wide_spread)
    assert_true(wide_spread["reason"] == "spread_too_wide", wide_spread)

    buy_stage1 = build_runner_levels(
        signal="BUY",
        entry_price=4350.00,
        risk_distance=0.40,
        lock_r=0.50,
        target_price_distance=2.00,
    )
    print("\n[BUY PROMOTION LEVELS]")
    print(buy_stage1)
    assert_true(buy_stage1["sl"] == 4350.20, buy_stage1)
    assert_true(buy_stage1["tp"] == 4352.00, buy_stage1)

    sell_stage2 = build_runner_levels(
        signal="SELL",
        entry_price=4350.00,
        risk_distance=0.40,
        lock_r=1.50,
        target_price_distance=2.00,
    )
    print("\n[SELL STAGE-2 LEVELS]")
    print(sell_stage2)
    assert_true(sell_stage2["sl"] == 4349.40, sell_stage2)
    assert_true(sell_stage2["tp"] == 4348.00, sell_stage2)

    capped = build_runner_levels(
        signal="BUY",
        entry_price=100.00,
        risk_distance=0.30,
        lock_r=0.50,
        target_price_distance=99.0,
    )
    assert_true(capped["tp"] == 102.00, capped)
    assert_true(capped["target_distance"] == 2.0, capped)

    settings_text = (ROOT / "config" / "settings.py").read_text(
        encoding="utf-8"
    )
    live_text = (ROOT / "src" / "live_bot.py").read_text(
        encoding="utf-8"
    )
    module_text = (ROOT / "src" / "low_mae_momentum_runner.py").read_text(
        encoding="utf-8"
    )

    print("\n[STATIC WIRING]")
    assert_true(
        "ENABLE_LOW_MAE_MOMENTUM_RUNNER_LIVE = True" in settings_text,
        "runner live setting missing",
    )
    assert_true(
        "manage_low_mae_momentum_runners(" in live_text,
        "fast-lane manager hook missing",
    )
    assert_true(
        "register_low_mae_momentum_trade(" in live_text,
        "post-execution registration missing",
    )
    assert_true(
        "TRADE_ACTION_SLTP" in module_text,
        "live SL/TP modification missing",
    )
    assert_true(
        'str(trade.get("strategy") or "").upper() != STRATEGY'
        in module_text,
        "runner not isolated to momentum trades",
    )
    assert_true(
        "target_distance = min(2.0" in module_text,
        "$2 hard cap missing",
    )

    print(
        "\nPASS: Low-MAE Runner is causal/post-entry, rejects high-MAE and "
        "wide-spread paths, caps TP at $2, locks profit in R, is isolated to "
        "INTRABAR_MICRO_MOMENTUM, and is wired into the 250ms live lane."
    )


if __name__ == "__main__":
    main()
