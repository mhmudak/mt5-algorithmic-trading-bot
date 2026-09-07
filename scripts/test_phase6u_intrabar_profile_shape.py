from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import (
    INTRABAR_PRICE_EVENT_ALLOWED_STRATEGIES,
    INTRABAR_PRICE_EVENT_STRATEGY_PROFILES,
    INTRABAR_STRATEGY_ALLOWLIST,
)
from src.live_bot import get_intrabar_detector_profiles


def test_profile_container_remains_behavior_catalog():
    assert isinstance(INTRABAR_PRICE_EVENT_STRATEGY_PROFILES, dict)
    assert "ORB_V00" in INTRABAR_PRICE_EVENT_STRATEGY_PROFILES
    assert "ORDER_BLOCK" in INTRABAR_PRICE_EVENT_STRATEGY_PROFILES
    assert "BREAKER_BLOCK" in INTRABAR_PRICE_EVENT_STRATEGY_PROFILES


def test_generic_detector_set_is_derived_from_canonical_allowlist():
    canonical = tuple(str(item).strip().upper() for item in INTRABAR_STRATEGY_ALLOWLIST)
    expected = tuple(
        strategy
        for strategy in canonical
        if strategy in INTRABAR_PRICE_EVENT_STRATEGY_PROFILES
    )

    assert canonical == (
        "AUTO_STRUCTURAL_LEVEL_SCALP",
        "FAILED_FVG_REVERSAL",
        "BREAKER_BLOCK",
        "ORDER_BLOCK",
    )
    assert INTRABAR_PRICE_EVENT_ALLOWED_STRATEGIES == expected
    assert set(expected) == {
        "FAILED_FVG_REVERSAL",
        "BREAKER_BLOCK",
        "ORDER_BLOCK",
    }


def test_live_profile_builder_preserves_strategy_specific_shape():
    profiles = get_intrabar_detector_profiles()
    by_strategy = {profile["strategy"]: profile for profile in profiles}

    assert set(by_strategy) == {
        "FAILED_FVG_REVERSAL",
        "BREAKER_BLOCK",
        "ORDER_BLOCK",
    }

    order_block = by_strategy["ORDER_BLOCK"]
    assert order_block["trigger"] == "REVERSAL_RECLAIM"
    assert order_block["level_source"] == "RECENT_STRUCTURE"
    assert order_block["min_score"] == 96
    assert order_block["min_rr"] == 1.30
    assert order_block["target_rr"] == 1.55
    assert order_block["require_m5_confirmation"] is True
    assert order_block["min_sl_distance"] == 4.00
    assert order_block["max_sl_distance"] == 14.00

    failed_fvg = by_strategy["FAILED_FVG_REVERSAL"]
    assert failed_fvg["trigger"] == "FAILED_FVG_REVERSAL_RECLAIM"
    assert failed_fvg["require_m5_confirmation"] is True

    breaker = by_strategy["BREAKER_BLOCK"]
    assert breaker["trigger"] == "NATIVE_BREAKER_RETEST"
    assert breaker["preserve_native_sl_tp"] is True
    assert breaker["require_m5_confirmation"] is True


if __name__ == "__main__":
    test_profile_container_remains_behavior_catalog()
    test_generic_detector_set_is_derived_from_canonical_allowlist()
    test_live_profile_builder_preserves_strategy_specific_shape()
    print("[PASS] Intrabar profile catalog and canonical derived detector set passed.")
