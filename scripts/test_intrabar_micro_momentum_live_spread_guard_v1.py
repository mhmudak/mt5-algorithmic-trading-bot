from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    print("[MICRO MOMENTUM LIVE SPREAD GUARD TEST V1]")

    live_text = (ROOT / "src" / "live_bot.py").read_text(
        encoding="utf-8"
    )

    assert_true(
        "MICRO_MOMENTUM_SHADOW_MAX_SPREAD_PRICE" in live_text,
        "micro spread setting is not reused at final execution quote",
    )
    assert_true(
        "reason=micro_spread_too_wide" in live_text,
        "fresh micro spread rejection is missing",
    )

    live_start = live_text.index(
        "def process_intrabar_micro_momentum_live("
    )
    fresh_tick_pos = live_text.index(
        "live_tick = mt5.symbol_info_tick(SYMBOL)",
        live_start,
    )
    spread_guard_pos = live_text.index(
        "reason=micro_spread_too_wide",
        fresh_tick_pos,
    )
    trade_guard_pos = live_text.index(
        "check_trade_guard(signal, live_tick)",
        spread_guard_pos,
    )

    assert_true(
        fresh_tick_pos < spread_guard_pos < trade_guard_pos,
        "micro spread guard must run on fresh quote before generic trade guard",
    )

    print(
        "PASS: live micro-momentum rechecks the fresh executable quote against "
        "the strategy's tighter spread ceiling before the generic trade guard."
    )


if __name__ == "__main__":
    main()
