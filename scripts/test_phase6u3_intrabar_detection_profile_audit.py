from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intrabar_detection_profile_audit import audit_intrabar_detection_profiles, build_phase6u3_settings_audit


def test_phase6u3_passes_when_only_allowed_profiles_remain():
    report = audit_intrabar_detection_profiles(
        profiles=[
            {"strategy": "AUTO_STRUCTURAL_LEVEL_SCALP"},
            {"strategy": "FAILED_FVG_REVERSAL"},
        ],
        allowed_strategies=("AUTO_STRUCTURAL_LEVEL_SCALP", "FAILED_FVG_REVERSAL"),
        blocked_examples=("MICRO_SR_SWEEP_RECLAIM", "RANGE_SWEEP_RECLAIM"),
    )
    assert report["pass"] is True
    assert report["status"] == "PASS"
    assert report["blocked_profiles_remaining"] == []
    assert report["unknown_profiles_remaining"] == []
    assert report["can_execute"] is False
    assert report["can_block_trade"] is False
    assert report["can_modify_risk"] is False
    assert report["can_modify_detection"] is False


def test_phase6u3_fails_when_blocked_or_unknown_profiles_remain():
    report = audit_intrabar_detection_profiles(
        profiles=[
            {"strategy": "AUTO_STRUCTURAL_LEVEL_SCALP"},
            {"strategy": "MICRO_SR_SWEEP_RECLAIM"},
            {"strategy": "VWAP_RECLAIM"},
            {"strategy": "SOMETHING_ELSE"},
        ],
        allowed_strategies=("AUTO_STRUCTURAL_LEVEL_SCALP", "FAILED_FVG_REVERSAL"),
        blocked_examples=("MICRO_SR_SWEEP_RECLAIM", "VWAP_RECLAIM"),
    )
    assert report["pass"] is False
    assert len(report["blocked_profiles_remaining"]) == 2
    assert len(report["unknown_profiles_remaining"]) == 1


def test_phase6u3_settings_audit_is_safe():
    report = build_phase6u3_settings_audit()
    assert report["phase"] == "PHASE_6U3_INTRABAR_DETECTION_PROFILE_HARD_BLOCK_AUDIT"
    assert report["decision_impact"] == "AUDIT_ONLY"
    assert report["auto_trade_allowed"] is False
    assert report["can_execute"] is False
    assert report["can_block_trade"] is False
    assert report["can_modify_risk"] is False
    assert report["can_modify_detection"] is False
    assert report["settings_pass"] is True


if __name__ == "__main__":
    test_phase6u3_passes_when_only_allowed_profiles_remain()
    test_phase6u3_fails_when_blocked_or_unknown_profiles_remain()
    test_phase6u3_settings_audit_is_safe()
    print("[PASS] Phase 6U3 intrabar detection profile audit passed.")
