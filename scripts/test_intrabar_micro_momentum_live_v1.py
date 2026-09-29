from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intrabar_micro_momentum_shadow import (
    build_live_signal_data_from_shadow,
)


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    print("[INTRABAR MICRO MOMENTUM LIVE TEST V1]")

    buy_setup = {
        "setup_id": "IMM-BUY-1",
        "strategy": "INTRABAR_MICRO_MOMENTUM",
        "signal": "BUY",
        "entry_model": "TICK_VELOCITY_ACCELERATION_PERSISTENCE",
        "score": 92,
        "session": "NEWYORK",
        "market_condition": "TRENDING",
        "entry": 100.00,
        "sl": 99.70,
        "tp": 100.60,
        "extra": {
            "strength": "WEAK_VALID",
            "sl_distance": 0.30,
            "tp_distance": 0.60,
            "daily_level_context": {
                "available": True,
                "pivot_direction_aligned": True,
            },
        },
    }

    buy = build_live_signal_data_from_shadow(
        buy_setup,
        SimpleNamespace(bid=101.08, ask=101.10),
    )

    print("\n[FRESH BUY HANDOFF]")
    print(buy)
    assert_true(buy is not None, "BUY handoff missing")
    assert_true(buy["entry_reference"] == 101.10, buy)
    assert_true(abs(buy["sl_reference"] - 100.80) < 1e-9, buy)
    assert_true(abs(buy["tp_reference"] - 101.70) < 1e-9, buy)
    assert_true(buy["entry_reference"] != buy_setup["entry"], buy)

    sell_setup = {
        "setup_id": "IMM-SELL-2",
        "strategy": "INTRABAR_MICRO_MOMENTUM",
        "signal": "SELL",
        "entry_model": "TICK_VELOCITY_ACCELERATION_PERSISTENCE",
        "score": 100,
        "session": "NEWYORK",
        "market_condition": "TRENDING",
        "entry": 200.00,
        "sl": 200.50,
        "tp": 198.00,
        "extra": {
            "strength": "EXPLOSIVE",
            "sl_distance": 0.50,
            "tp_distance": 2.00,
            "daily_level_context": {
                "available": True,
                "pivot_direction_aligned": True,
            },
        },
    }

    sell = build_live_signal_data_from_shadow(
        sell_setup,
        SimpleNamespace(bid=198.90, ask=198.92),
    )

    print("\n[FRESH SELL HANDOFF]")
    print(sell)
    assert_true(sell is not None, "SELL handoff missing")
    assert_true(sell["entry_reference"] == 198.90, sell)
    assert_true(abs(sell["sl_reference"] - 199.40) < 1e-9, sell)
    assert_true(abs(sell["tp_reference"] - 196.90) < 1e-9, sell)

    settings_text = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    risk_text = (ROOT / "src" / "risk.py").read_text(encoding="utf-8")
    live_text = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")

    print("\n[STATIC WIRING]")
    assert_true(
        "ENABLE_INTRABAR_MICRO_MOMENTUM_LIVE = True" in settings_text,
        "live enable flag missing",
    )
    assert_true(
        '"INTRABAR_MICRO_MOMENTUM",' in risk_text,
        "risk engine does not preserve momentum SL reference",
    )
    assert_true(
        "def process_intrabar_micro_momentum_live(" in live_text,
        "live executor missing",
    )
    assert_true(
        "MICRO_MOMENTUM_EXECUTION_ATTEMPT" in live_text,
        "execution audit event missing",
    )
    assert_true(
        "check_trade_guard(signal, live_tick)" in live_text,
        "trade guard missing",
    )
    assert_true(
        "is_news_blackout_active()" in live_text,
        "news guard missing",
    )
    assert_true(
        "is_trading_blackout_active()" in live_text,
        "time guard missing",
    )
    assert_true(
        "MICRO_MOMENTUM_EXECUTION_BLOCKED_BY_MEMORY" in live_text,
        "execution memory integration missing",
    )
    assert_true(
        "execute_trade(signal, trade_plan, SYMBOL)" in live_text,
        "MT5 execution call missing",
    )
    assert_true(
        "process_intrabar_micro_momentum_live(" in live_text[
            live_text.index("# INTRABAR MICRO MOMENTUM SHADOW V1"):
        ],
        "per-loop live handoff missing",
    )

    print(
        "\nPASS: live micro-momentum promotion uses fresh ask/bid, preserves "
        "$0.30-$0.50 SL / $0.60-$2.00 TP geometry through the normal risk "
        "engine, and is wired through trade/news/time/memory guards before "
        "MT5 execution."
    )


if __name__ == "__main__":
    main()
