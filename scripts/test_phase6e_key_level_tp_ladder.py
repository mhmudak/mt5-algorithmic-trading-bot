from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.key_level_tp_ladder import apply_key_level_tp_ladder  # noqa: E402


def build_df() -> pd.DataFrame:
    rows = []
    price = 4090.0

    for i in range(70):
        price -= 0.08
        rows.append(
            {
                "time": f"2026-07-31T05:{i:02d}:00",
                "open": price + 0.20,
                "high": price + 0.90,
                "low": price - 0.90,
                "close": price,
                "tick_volume": 100,
            }
        )

    # Swing support around the exact area that stopped the move.
    rows.extend(
        [
            {"time": "2026-07-31T06:10:00", "open": 4078.0, "high": 4079.2, "low": 4074.17, "close": 4076.0, "tick_volume": 200},
            {"time": "2026-07-31T06:15:00", "open": 4076.0, "high": 4078.5, "low": 4075.2, "close": 4077.8, "tick_volume": 180},
            {"time": "2026-07-31T06:20:00", "open": 4077.8, "high": 4083.5, "low": 4076.7, "close": 4082.9, "tick_volume": 210},
            {"time": "2026-07-31T06:25:00", "open": 4082.9, "high": 4084.5, "low": 4081.7, "close": 4082.4, "tick_volume": 90},
        ]
    )

    return pd.DataFrame(rows)


def main() -> None:
    trade_plan = {
        "strategy": "SESSION_ORB_RETEST",
        "signal": "SELL",
        "entry_price": 4082.89,
        "stop_loss": 4091.48,
        "take_profit": 4066.92,
        "lot": 0.03,
        "reason": "Session ORB SELL retest original target",
    }

    signal_data = {
        "strategy": "SESSION_ORB_RETEST",
        "signal": "SELL",
        "score": 100,
        "entry_model": "ORB_RETEST_REJECTION",
        "daily_pivot": 4084.0,
        "range_low": 4088.75,
        "range_high": 4117.44,
    }

    adjusted = apply_key_level_tp_ladder(
        df=build_df(),
        signal="SELL",
        trade_plan=trade_plan,
        signal_data=signal_data,
        strategy_name="SESSION_ORB_RETEST",
        session_name="ASIA",
        market_condition="TRENDING",
    )

    print("[ADJUSTED TRADE PLAN]")
    print(adjusted)

    assert adjusted["key_level_tp_ladder_applied"] is True
    assert adjusted["original_take_profit"] == 4066.92
    assert adjusted["take_profit"] > 4066.92
    assert adjusted["take_profit"] < 4082.89
    assert adjusted["tp_ladder"][0]["name"] == "TP1_BEFORE_KEY_BARRIER"
    assert adjusted["tp_ladder"][2]["price"] == 4066.92
    assert "TP1" in adjusted["tp_plan_summary"]
    assert "KEY_LEVEL_TP_LADDER" in adjusted["reason"]
    assert adjusted["tp_barrier"]["barrier_confirmation"] == "STRUCTURAL_LEVEL_CONFIRMED"
    assert "recent_swing_low" in ",".join(adjusted["tp_barrier"]["sources"])

    live_bot = ROOT / "src" / "live_bot.py"
    live_text = live_bot.read_text(encoding="utf-8")

    assert "apply_key_level_tp_ladder" in live_text
    assert "TP Plan:" in live_text
    assert "Original TP:" in live_text
    assert "TP1 / Execution TP:" in live_text

    print("")
    print("[PASS] Phase 6E key level TP ladder clamps TP before support/resistance barrier.")


if __name__ == "__main__":
    main()
