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


def test_profile_container_remains_dictionary():
    assert isinstance(INTRABAR_PRICE_EVENT_STRATEGY_PROFILES, dict)


def test_detection_allowlist_is_consistent():
    allowed = {
        str(item).strip().upper()
        for item in INTRABAR_STRATEGY_ALLOWLIST
    }

    assert set(INTRABAR_PRICE_EVENT_STRATEGY_PROFILES).issubset(allowed)

    configured = {
        str(item).strip().upper()
        for item in INTRABAR_PRICE_EVENT_ALLOWED_STRATEGIES
    }

    assert configured.issubset(allowed)


def test_live_profile_builder_runs():
    profiles = get_intrabar_detector_profiles()

    assert isinstance(profiles, list)
    assert all(isinstance(profile, dict) for profile in profiles)


if __name__ == "__main__":
    test_profile_container_remains_dictionary()
    test_detection_allowlist_is_consistent()
    test_live_profile_builder_runs()

    print("[PASS] Phase 6U intrabar profile shape regression passed.")
