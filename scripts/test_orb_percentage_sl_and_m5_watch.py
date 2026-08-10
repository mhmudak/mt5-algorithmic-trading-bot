from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from src.strategies import strategy_orb
from src.strategies import strategy_orb_v00


def test_orb_example_percentage_sl():
    orb_high = 4268.99
    orb_low = 4229.60
    entry = 4269.26
    tp = 4290.30

    width = orb_high - orb_low

    buffer_value = strategy_orb._sl_buffer(
        width,
        "FAST_CONTINUATION",
    )

    assert round(buffer_value, 2) == 7.88

    sl = round(
        orb_high - buffer_value,
        2,
    )

    assert sl == 4261.11

    # The observed throwback to approximately 4264
    # must remain above the new structural stop.
    assert 4264.00 > sl

    risk = entry - sl
    reward = tp - entry
    rr = reward / risk

    assert rr > 2.0
    assert round(rr, 2) == 2.58


def test_orb_v00_example_percentage_sl():
    orb_high = 4271.08
    orb_low = 4231.71
    entry = 4271.38
    tp = 4310.75

    width = orb_high - orb_low

    buffer_value = strategy_orb_v00._sl_buffer(
        width,
        "BREAKOUT",
    )

    assert round(buffer_value, 2) == 7.87

    sl = round(
        orb_high - buffer_value,
        2,
    )

    assert sl == 4263.21

    risk = entry - sl
    reward = tp - entry
    rr = reward / risk

    assert rr > 4.0
    assert rr < 6.0
    assert round(rr, 2) == 4.82

    # ORB_V00 target remains one full opening-range
    # measured move from the actual entry.
    assert round(
        entry + width,
        2,
    ) == tp


def test_percentage_settings():
    assert (
        settings.ORB_SL_RANGE_PCT_BY_ENTRY_MODEL[
            "FAST_CONTINUATION"
        ]
        == 20.0
    )

    assert (
        settings.ORB_SL_RANGE_PCT_BY_ENTRY_MODEL[
            "BREAKOUT"
        ]
        == 20.0
    )

    assert (
        settings.ORB_SL_RANGE_PCT_BY_ENTRY_MODEL[
            "WAIT_RETEST"
        ]
        == 15.0
    )

    assert (
        settings.ORB_V00_SL_RANGE_PCT_BY_ENTRY_MODEL[
            "BREAKOUT"
        ]
        == 20.0
    )

    assert (
        settings.ORB_DIRECT_BREAKOUT_EXTRA_SL_RANGE_PCT
        == 2.0
    )


def test_fixed_orb_sl_constants_removed():
    orb_source = (
        ROOT
        / "src"
        / "strategies"
        / "strategy_orb.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    orb_v00_source = (
        ROOT
        / "src"
        / "strategies"
        / "strategy_orb_v00.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    engine_source = (
        ROOT
        / "src"
        / "execution_engine.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert "ORB_MIN_SL_BUFFER" not in orb_source
    assert "ORB_MAX_SL_BUFFER" not in orb_source
    assert (
        "max(atr * 0.25, 1.5)"
        not in orb_v00_source
    )

    assert (
        "ORB_DIRECT_BREAKOUT_EXTRA_SL_PRICE"
        not in engine_source
    )

    assert (
        "ORB_DIRECT_BREAKOUT_EXTRA_SL_RANGE_PCT"
        in engine_source
    )


def test_tp_models_preserved():
    orb_source = (
        ROOT
        / "src"
        / "strategies"
        / "strategy_orb.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    orb_v00_source = (
        ROOT
        / "src"
        / "strategies"
        / "strategy_orb_v00.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        'target_model": "ORB_RANGE_EXTENSION"'
        in orb_source
    )

    assert (
        "target_distance = _target_distance("
        in orb_source
    )

    assert (
        'target_model": "ORB_V00_RANGE_EXTENSION"'
        in orb_v00_source
    )

    assert (
        "tp_reference = round(price + orb_width, 2)"
        in orb_v00_source
    )


def test_intrabar_orb_uses_percentage_sl():
    settings_source = (
        ROOT
        / "config"
        / "settings.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    live_source = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert '"sl_range_pct"' in settings_source
    assert "use_orb_percentage_sl" in live_source
    assert (
        "float(range_width)"
        in live_source
    )
    assert (
        '"intrabar_sl_range_pct"'
        in live_source
    )


def test_extra_m5_failure_becomes_wait():
    source = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    marker = (
        "# EXTRA ENTRY M5 CONFIRMATION"
    )

    start = source.rindex(marker)

    end = source.index(
        "# OPPOSITE POSITION GUARD",
        start,
    )

    section = source[start:end]

    wait_marker = (
        "execution_engine."
        "mark_wait_orb_tick_breakout("
    )

    skip_marker = (
        'best_setup["state"] = "SKIPPED"'
    )

    assert wait_marker in section
    assert (
        '"orb_tick_require_m5_confirmation"'
        in section
    )
    assert (
        "ORB_EXTRA_M5_WAITING"
        in section
    )

    # Generic non-ORB candidates may still be skipped,
    # but the ORB waiting branch must run first.
    assert skip_marker in section
    assert (
        section.index(wait_marker)
        < section.index(skip_marker)
    )


def test_orb_watcher_rechecks_m5_each_loop():
    source = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    start = source.index(
        "def process_wait_orb_tick_breakout_setups("
    )

    end = source.find(
        "\ndef ",
        start + 5,
    )

    function_source = source[
        start:
        end if end > start else None
    ]

    assert (
        "orb_tick_require_m5_confirmation"
        in function_source
    )

    assert (
        "extra_entry_confirmation_ok("
        in function_source
    )

    assert (
        "M5 confirmation pending"
        in function_source
    )

    assert (
        "check_trade_guard(signal, tick)"
        in function_source
    )

    assert (
        "execute_trade("
        in function_source
    )

    assert (
        function_source.index(
            "check_trade_guard(signal, tick)"
        )
        < function_source.index(
            "execute_trade("
        )
    )


def main():
    test_orb_example_percentage_sl()
    test_orb_v00_example_percentage_sl()
    test_percentage_settings()
    test_fixed_orb_sl_constants_removed()
    test_tp_models_preserved()
    test_intrabar_orb_uses_percentage_sl()
    test_extra_m5_failure_becomes_wait()
    test_orb_watcher_rechecks_m5_each_loop()

    print(
        "[PASS] ORB/ORB_V00 percentage SL, "
        "TP preservation, intrabar alignment, "
        "and extra-entry M5 watcher passed."
    )


if __name__ == "__main__":
    main()
