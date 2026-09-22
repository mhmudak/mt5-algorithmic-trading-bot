from __future__ import annotations

from pathlib import Path
import re

from src.better_entry_optimizer import (
    build_better_entry_observer,
    resolve_structural_anchor,
)


ROOT = Path(__file__).resolve().parents[1]


def _assert_authority(snapshot):
    assert snapshot["decision_impact"] == "OBSERVE_ONLY"
    assert snapshot["can_execute"] is False
    assert snapshot["can_block_trade"] is False
    assert snapshot["can_modify_score"] is False
    assert snapshot["can_modify_risk"] is False
    assert snapshot["can_modify_entry_sl_tp"] is False
    assert snapshot["can_modify_lot"] is False


def test_breaker_sell_uses_native_retest_boundary():
    setup = {
        "setup_id": "TEST-BRE-SELL",
        "strategy": "BREAKER_BLOCK",
        "entry_model": "BEARISH_BREAKER_RETEST",
        "signal": "SELL",
        "entry": 4332.33,
        "extra": {
            "breaker_zone_low": 4345.99,
            "breaker_zone_high": 4356.16,
        },
    }

    anchor = resolve_structural_anchor(setup)

    assert anchor["type"] == "BREAKER_RETEST_BOUNDARY"
    assert anchor["price"] == 4345.99
    assert anchor["source_fields"] == [
        "extra.breaker_zone_low",
        "extra.breaker_zone_high",
    ]

    snapshot = build_better_entry_observer(
        setup,
        historical_rows=[],
        enabled_override=True,
    )

    assert snapshot["cisd_policy"] == "CISD_ON_RETEST"
    assert snapshot["cisd_mode"] == "REQUIRED_AT_STRUCTURAL_RETEST"
    assert snapshot["structural_anchor"] == anchor
    assert snapshot["structural_candidate_entry"] == 4345.99
    assert snapshot["preferred_observer_entry_basis"] == "STRUCTURAL_ANCHOR"
    assert snapshot["preferred_observer_entry"] == 4345.99
    _assert_authority(snapshot)


def test_breaker_buy_uses_native_retest_boundary():
    setup = {
        "setup_id": "TEST-BRE-BUY",
        "strategy": "BREAKER_BLOCK",
        "entry_model": "BULLISH_BREAKER_RETEST",
        "signal": "BUY",
        "entry": 4401.25,
        "extra": {
            "breaker_zone_low": 4380.00,
            "breaker_zone_high": 4390.00,
        },
    }

    anchor = resolve_structural_anchor(setup)

    assert anchor["type"] == "BREAKER_RETEST_BOUNDARY"
    assert anchor["price"] == 4390.00

    snapshot = build_better_entry_observer(
        setup,
        historical_rows=[],
        enabled_override=True,
    )

    assert snapshot["structural_candidate_entry"] == 4390.00
    assert snapshot["preferred_observer_entry"] == 4390.00
    _assert_authority(snapshot)


def test_breaker_requires_valid_native_zone():
    setup = {
        "setup_id": "TEST-BRE-BAD-ZONE",
        "strategy": "BREAKER_BLOCK",
        "entry_model": "BEARISH_BREAKER_RETEST",
        "signal": "SELL",
        "entry": 4332.33,
        "extra": {
            "breaker_zone_low": 4356.16,
            "breaker_zone_high": 4345.99,
        },
    }

    anchor = resolve_structural_anchor(setup)

    assert anchor["type"] == "NO_STRUCTURAL_ANCHOR"
    assert anchor["price"] is None


def test_non_breaker_cannot_consume_breaker_zone_fields():
    setup = {
        "setup_id": "TEST-FVG",
        "strategy": "FVG",
        "entry_model": "FVG_RETEST",
        "signal": "SELL",
        "entry": 4332.33,
        "extra": {
            "breaker_zone_low": 4345.99,
            "breaker_zone_high": 4356.16,
        },
    }

    anchor = resolve_structural_anchor(setup)

    assert anchor["type"] == "NO_STRUCTURAL_ANCHOR"


def test_live_handoff_persists_native_breaker_geometry():
    live = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert (
        '"breaker_zone_low": ('
        in live
    )
    assert (
        '"breaker_zone_high": ('
        in live
    )
    assert (
        'selected_signal_data.get("zone_low")'
        in live
    )
    assert (
        'selected_signal_data.get("zone_high")'
        in live
    )
    assert (
        'strategy_name == "BREAKER_BLOCK"'
        in live
    )


def test_fixed_lot_unchanged():
    settings = (
        ROOT
        / "config"
        / "settings.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    match = re.search(
        r"(?m)^FIXED_LOT\s*=\s*([0-9.]+)\s*$",
        settings,
    )

    assert match
    assert float(match.group(1)) == 0.25


def main():
    test_breaker_sell_uses_native_retest_boundary()
    test_breaker_buy_uses_native_retest_boundary()
    test_breaker_requires_valid_native_zone()
    test_non_breaker_cannot_consume_breaker_zone_fields()
    test_live_handoff_persists_native_breaker_geometry()
    test_fixed_lot_unchanged()

    print("PASS: Breaker SELL uses native zone_low retest boundary")
    print("PASS: Breaker BUY uses native zone_high retest boundary")
    print("PASS: invalid Breaker geometry fails open to no structural anchor")
    print("PASS: Breaker geometry cannot leak into non-Breaker strategies")
    print("PASS: SETUP_DETECTED persists Breaker-native geometry")
    print("PASS: Better Entry remains OBSERVE_ONLY")
    print("PASS: CISD policy remains CISD_ON_RETEST")
    print("PASS: FIXED_LOT remains exactly 0.25")


if __name__ == "__main__":
    main()
