from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intrabar_micro_momentum_shadow import (
    MomentumConfig,
    build_daily_level_context,
    build_shadow_setup,
    evaluate_momentum_samples,
    reset_shadow_state,
    update_approved_daily_ladder_context,
)


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def sample(ts, mid, spread=0.10):
    return {
        "ts": float(ts),
        "bid": float(mid - spread / 2.0),
        "ask": float(mid + spread / 2.0),
        "mid": float(mid),
        "spread": float(spread),
    }


def main():
    print("[INTRABAR MICRO MOMENTUM SHADOW TEST V1]")
    reset_shadow_state()

    cfg = MomentumConfig(
        window_seconds=5.0,
        min_samples=6,
        min_span_seconds=2.0,
        min_move_price=0.30,
        min_velocity_price_per_sec=0.06,
        min_persistence=0.67,
        min_acceleration_ratio=1.0,
        max_spread_price=0.20,
        breakout_buffer_price=0.01,
        min_score=88,
    )

    buy_rows = [
        sample(100.0, 4350.00),
        sample(100.8, 4350.04),
        sample(101.6, 4350.08),
        sample(102.4, 4350.14),
        sample(103.2, 4350.24),
        sample(104.0, 4350.38),
    ]

    buy = evaluate_momentum_samples(buy_rows, cfg)
    print("\n[BUY MOMENTUM]")
    print(buy)
    assert_true(buy is not None, "BUY impulse was not detected")
    assert_true(buy["signal"] == "BUY", buy)
    assert_true(buy["absolute_move"] >= 0.30, buy)
    assert_true(buy["persistence"] >= 0.67, buy)
    assert_true(buy["sl_distance"] in {0.30, 0.40, 0.50}, buy)
    assert_true(0.60 <= buy["tp_distance"] <= 2.00, buy)

    sell_rows = [
        sample(200.0, 4352.00),
        sample(200.8, 4351.96),
        sample(201.6, 4351.90),
        sample(202.4, 4351.83),
        sample(203.2, 4351.70),
        sample(204.0, 4351.55),
    ]
    sell = evaluate_momentum_samples(sell_rows, cfg)
    print("\n[SELL MOMENTUM]")
    print(sell)
    assert_true(sell is not None, "SELL impulse was not detected")
    assert_true(sell["signal"] == "SELL", sell)

    noisy = [
        sample(300.0, 4350.00),
        sample(300.8, 4350.10),
        sample(301.6, 4350.01),
        sample(302.4, 4350.11),
        sample(303.2, 4350.03),
        sample(304.0, 4350.12),
    ]
    rejected = evaluate_momentum_samples(noisy, cfg)
    print("\n[NOISY / NON-PERSISTENT]")
    print(rejected)
    assert_true(rejected is None, rejected)

    wide_spread = [
        sample(400.0, 4350.00, 0.30),
        sample(400.8, 4350.05, 0.30),
        sample(401.6, 4350.10, 0.30),
        sample(402.4, 4350.18, 0.30),
        sample(403.2, 4350.28, 0.30),
        sample(404.0, 4350.42, 0.30),
    ]
    rejected_spread = evaluate_momentum_samples(wide_spread, cfg)
    print("\n[WIDE SPREAD]")
    print(rejected_spread)
    assert_true(rejected_spread is None, rejected_spread)

    ladder = {
        "pivot": 4342.0,
        "upper": (4350.0, 4366.0, 4373.0),
        "lower": (4334.0, 4324.0, 4315.0),
        "source": "AUTO_STRONG_DAILY_LADDER",
        "broker_date": "2026-09-23",
    }
    update_approved_daily_ladder_context(ladder)

    daily_buy = build_daily_level_context(4350.40, "BUY")
    print("\n[DAILY LEVEL CONTEXT BUY]")
    print(daily_buy)
    assert_true(daily_buy["available"] is True, daily_buy)
    assert_true(daily_buy["pivot_direction_aligned"] is True, daily_buy)
    assert_true(daily_buy["next_level_in_direction"] == 4366.0, daily_buy)
    assert_true(daily_buy["execution_authority"] is False, daily_buy)

    daily_sell = build_daily_level_context(4333.50, "SELL")
    assert_true(daily_sell["pivot_direction_aligned"] is True, daily_sell)
    assert_true(daily_sell["next_level_in_direction"] == 4324.0, daily_sell)

    setup = build_shadow_setup(
        buy,
        session="NEWYORK",
        market_condition="TRENDING",
    )
    print("\n[SHADOW SETUP]")
    print(setup)
    assert_true(setup["strategy"] == "INTRABAR_MICRO_MOMENTUM", setup)
    assert_true(setup["extra"]["shadow_only"] is True, setup)
    assert_true(setup["extra"]["decision_impact"] == "NONE", setup)
    assert_true(setup["extra"]["orders_sent"] == 0, setup)
    assert_true(setup["entry"] == round(buy["ask"], 2), setup)
    sl_distance = abs(setup["entry"] - setup["sl"])
    assert_true(
        (0.30 - 1e-9) <= sl_distance <= (0.50 + 1e-9),
        {"setup": setup, "sl_distance": sl_distance},
    )
    tp_distance = abs(setup["tp"] - setup["entry"])
    assert_true(
        (0.60 - 1e-9) <= tp_distance <= (2.00 + 1e-9),
        {"setup": setup, "tp_distance": tp_distance},
    )

    settings_text = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    live_text = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")

    print("\n[STATIC WIRING]")
    assert_true(
        "ENABLE_INTRABAR_MICRO_MOMENTUM_SHADOW = True" in settings_text,
        "missing shadow enable setting",
    )
    assert_true(
        "# INTRABAR MICRO MOMENTUM SHADOW V1" in live_text,
        "missing per-loop shadow hook",
    )
    assert_true(
        "observe_intrabar_micro_momentum_shadow(" in live_text,
        "missing observer call",
    )
    assert_true(
        "update_approved_daily_ladder_context(approved_ladder)" in live_text,
        "approved daily ladder is not published for context",
    )
    assert_true(
        "execute_trade(" not in (
            ROOT / "src" / "intrabar_micro_momentum_shadow.py"
        ).read_text(encoding="utf-8"),
        "shadow module must not call execute_trade",
    )

    print(
        "\nPASS: tick momentum detection, persistence/acceleration, spread gate, "
        "adaptive $0.30-$0.50 SL / $0.60-$2.00 TP, approved daily-ladder context, "
        "and strict shadow-only authority verified."
    )


if __name__ == "__main__":
    main()
