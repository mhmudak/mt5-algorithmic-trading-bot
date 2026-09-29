from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.fcr_runtime_guard import (
    resolve_fcr_signal_entry,
    validate_fcr_runtime_geometry,
)


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    print("[FCR FRESH INTRABAR ENTRY TEST V1]")

    signal_data = {
        "strategy": "FCR_M1_FVG",
        "signal": "BUY",
        "entry_reference": 4350.91,
        "sl_reference": 4349.71,
        "tp_reference": 4378.11,
    }
    plan = {
        "strategy": "FCR_M1_FVG",
        "signal": "BUY",
        "entry_price": 4350.91,
        "stop_loss": 4349.71,
        "take_profit": 4378.11,
    }

    print("\n[ENTRY RESOLUTION]")
    live_entry = resolve_fcr_signal_entry(
        "FCR_M1_FVG", signal_data, 4348.0, 4351.40
    )
    print(f"fcr_live_entry={live_entry}")
    assert_true(live_entry == 4351.40, live_entry)

    frozen_fallback = resolve_fcr_signal_entry(
        "FCR_M1_FVG", signal_data, 4348.0
    )
    print(f"fcr_fallback_entry={frozen_fallback}")
    assert_true(frozen_fallback == 4350.91, frozen_fallback)

    non_fcr = resolve_fcr_signal_entry(
        "OTHER", signal_data, 4400.0, 4500.0
    )
    assert_true(non_fcr == 4400.0, non_fcr)

    print("\n[BUY WITHIN 0.50R CHASE]")
    within = validate_fcr_runtime_geometry(
        strategy_name="FCR_M1_FVG",
        signal="BUY",
        signal_data=signal_data,
        trade_plan=plan,
        executable_price=4351.40,
        min_rr_required=1.10,
        max_chase_r=0.50,
    )
    print(within)
    assert_true(within["allowed"] is True, within)
    assert_true(abs(within["max_chase_distance"] - 0.60) < 1e-9, within)
    assert_true(abs(within["chase_distance"] - 0.49) < 1e-9, within)
    assert_true(within["trade_plan"]["entry_price"] == 4351.40, within)

    print("\n[REPORTED INCIDENT: BUY AT 4356]")
    stale = validate_fcr_runtime_geometry(
        strategy_name="FCR_M1_FVG",
        signal="BUY",
        signal_data=signal_data,
        trade_plan=plan,
        executable_price=4356.00,
        min_rr_required=1.10,
        max_chase_r=0.50,
    )
    print(stale)
    assert_true(stale["allowed"] is False, stale)
    assert_true(stale["reason"] == "runtime_chase_exceeded", stale)
    assert_true(abs(stale["chase_distance"] - 5.09) < 1e-9, stale)

    print("\n[BETTER BUY PRICE]")
    better = validate_fcr_runtime_geometry(
        strategy_name="FCR_M1_FVG",
        signal="BUY",
        signal_data=signal_data,
        trade_plan=plan,
        executable_price=4350.50,
        min_rr_required=1.10,
        max_chase_r=0.50,
    )
    print(better)
    assert_true(better["allowed"] is True, better)
    assert_true(better["chase_distance"] < 0, better)

    print("\n[RR DEGRADATION INSIDE CHASE LIMIT]")
    short_target = dict(plan)
    short_target["take_profit"] = 4352.11
    low_rr = validate_fcr_runtime_geometry(
        strategy_name="FCR_M1_FVG",
        signal="BUY",
        signal_data=signal_data,
        trade_plan=short_target,
        executable_price=4351.40,
        min_rr_required=1.10,
        max_chase_r=0.50,
    )
    print(low_rr)
    assert_true(low_rr["allowed"] is False, low_rr)
    assert_true(low_rr["reason"] == "runtime_rr_below_required", low_rr)

    print("\n[SELL SYMMETRY]")
    sell_data = {
        "strategy": "FCR_M1_FVG",
        "signal": "SELL",
        "entry_reference": 100.0,
        "sl_reference": 102.0,
        "tp_reference": 94.0,
    }
    sell_plan = {
        "strategy": "FCR_M1_FVG",
        "signal": "SELL",
        "entry_price": 100.0,
        "stop_loss": 102.0,
        "take_profit": 94.0,
    }
    sell_stale = validate_fcr_runtime_geometry(
        strategy_name="FCR_M1_FVG",
        signal="SELL",
        signal_data=sell_data,
        trade_plan=sell_plan,
        executable_price=98.90,
        min_rr_required=1.10,
        max_chase_r=0.50,
    )
    print(sell_stale)
    assert_true(sell_stale["allowed"] is False, sell_stale)
    assert_true(sell_stale["reason"] == "runtime_chase_exceeded", sell_stale)

    config_text = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    live_text = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")

    print("\n[STATIC RUNTIME WIRING]")
    assert_true(
        "FCR_M1_FVG_RUNTIME_MAX_CHASE_R = 0.50" in config_text,
        "missing max-chase setting",
    )
    assert_true(
        "# FCR FRESH-ENTRY / ANTI-CHASE GUARD" in live_text,
        "missing pre-selection freshness guard",
    )
    assert_true(
        'candidate["fcr_runtime_entry"]' in live_text,
        "fresh FCR runtime entry not propagated",
    )
    assert_true(
        'selected_signal_data.get("fcr_runtime_entry")' in live_text,
        "setup-detected path not using fresh FCR entry",
    )
    assert_true(
        live_text.count("FCR_M1_FVG_RUNTIME_MAX_CHASE_R") >= 2,
        "max chase not enforced at both gates",
    )

    allow_start = config_text.index("INTRABAR_STRATEGY_ALLOWLIST = (")
    allow_end = config_text.index(")", allow_start)
    allow_block = config_text[allow_start:allow_end]
    assert_true(
        '"FCR_M1_FVG"' not in allow_block,
        "FCR must stay on dedicated Phase 6R cadence, not generic detector",
    )

    assert_true(
        "fcr_m1_only_cycle" in live_text
        and 'if name == "FCR_M1_FVG"' in live_text,
        "dedicated FCR closed-M1 cycle missing",
    )

    print(
        "\nPASS: FCR stays closed-M1 authoritative, uses the fresh executable "
        "quote, rejects >0.50R adverse chase before selection/alert and again "
        "before execution, preserves SL/TP, and remains outside the generic "
        "intrabar detector."
    )


if __name__ == "__main__":
    main()
