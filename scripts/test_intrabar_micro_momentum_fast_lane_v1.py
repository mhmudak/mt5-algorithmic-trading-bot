from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intrabar_micro_momentum_shadow import (
    detect_intrabar_micro_momentum_fast_tick,
    reset_shadow_state,
)


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def tick(ms, mid, spread=0.10):
    return SimpleNamespace(
        time_msc=int(ms),
        bid=float(mid - spread / 2.0),
        ask=float(mid + spread / 2.0),
    )


def main():
    print("[INTRABAR MICRO MOMENTUM FAST LANE TEST V1]")

    reset_shadow_state()

    # 6 fresh samples spanning 2.5 seconds inside the 5-second detector window.
    rows = [
        tick(100000, 4350.00),
        tick(100500, 4350.04),
        tick(101000, 4350.09),
        tick(101500, 4350.16),
        tick(102000, 4350.26),
        tick(102500, 4350.40),
    ]

    candidate = None
    for row in rows:
        candidate = detect_intrabar_micro_momentum_fast_tick(row)

    print("\n[FAST BUY CANDIDATE]")
    print(candidate)

    assert_true(candidate is not None, "fast lane did not qualify momentum")
    assert_true(candidate["signal"] == "BUY", candidate)
    assert_true(candidate["sample_count"] >= 6, candidate)
    assert_true(candidate["span_seconds"] <= 5.0, candidate)
    assert_true(candidate["span_seconds"] >= 2.0, candidate)

    # Identical raw tick must not create a second sample.
    duplicate = detect_intrabar_micro_momentum_fast_tick(rows[-1])
    print("\n[DUPLICATE RAW TICK]")
    print(duplicate)
    assert_true(duplicate is None, duplicate)

    settings_text = (ROOT / "config" / "settings.py").read_text(
        encoding="utf-8"
    )
    live_text = (ROOT / "src" / "live_bot.py").read_text(
        encoding="utf-8"
    )

    print("\n[STATIC WIRING]")

    assert_true(
        "ENABLE_INTRABAR_MICRO_MOMENTUM_FAST_LANE = True"
        in settings_text,
        "fast lane enable flag missing",
    )
    assert_true(
        "MICRO_MOMENTUM_FAST_LANE_POLL_SECONDS = 0.25"
        in settings_text,
        "250ms poll setting missing",
    )
    assert_true(
        "def process_intrabar_micro_momentum_fast_lane_once(" in live_text,
        "fast lane single-poll function missing",
    )
    assert_true(
        "def run_intrabar_micro_momentum_fast_lane_wait(" in live_text,
        "fast lane wait scheduler missing",
    )
    assert_true(
        "run_intrabar_micro_momentum_fast_lane_wait(10.0)" in live_text,
        "old passive 10-second sleep was not replaced",
    )
    assert_true(
        "and not getattr(" in live_text[
            live_text.index("# INTRABAR MICRO MOMENTUM SHADOW V1"):
            live_text.index("# SETUP OUTCOME TRACKER")
        ],
        "legacy process_cycle momentum sampler is not gated off",
    )
    assert_true(
        "time.sleep(10)" not in live_text[
            live_text.index("def main():"):
        ],
        "passive 10-second main-loop sleep still present",
    )

    print(
        "\nPASS: the momentum family now has a dedicated 250ms sampling lane, "
        "can collect >=6 fresh quotes inside a 5-second window, suppresses "
        "duplicate raw ticks, disables the legacy 10-second sampler when the "
        "fast lane is enabled, and preserves the normal full-cycle cadence."
    )


if __name__ == "__main__":
    main()
