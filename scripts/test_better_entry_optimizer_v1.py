from __future__ import annotations

from config import settings
from src.better_entry_optimizer import (
    CISD_ON_RETEST,
    CISD_REQUIRED,
    NO_CISD,
    build_better_entry_observer,
    resolve_cisd_policy,
)


def _row(
    setup_id,
    *,
    strategy="ORB",
    entry_model="UNKNOWN_ENTRY_MODEL",
    signal="BUY",
    win=True,
    pre_w10_mae=None,
):
    return {
        "setup_id": setup_id,
        "status": "CLOSED",
        "strategy": strategy,
        "entry_model": entry_model,
        "signal": signal,
        "path_observed": True,
        "hit_plus_10": win,
        "hit_tp": win,
        "hit_sl": not win,
        "first_hit": "W10" if win else "SL_TOUCH",
        "max_favorable_usd": 14.0 if win else 3.0,
        "max_adverse_usd": 9.0,
        "max_recovery_swing_usd": 17.0,
        "pre_w10_max_adverse_usd": pre_w10_mae,
    }


def test_safe_defaults():
    assert settings.ENABLE_BETTER_ENTRY_OPTIMIZER is False
    assert settings.BETTER_ENTRY_OPTIMIZER_MIN_HISTORICAL_SAMPLE == 20
    assert settings.FIXED_LOT == 0.25


def test_policy_registry():
    assert resolve_cisd_policy(
        "LIQUIDITY_SWEEP",
        "LIQUIDITY_SWEEP_REVERSAL",
    ) == CISD_REQUIRED

    assert resolve_cisd_policy(
        "HEAD_SHOULDERS",
        "HS_NECKLINE_RETEST",
    ) == CISD_ON_RETEST

    assert resolve_cisd_policy(
        "ORB",
        "UNKNOWN_ENTRY_MODEL",
    ) == CISD_ON_RETEST

    assert resolve_cisd_policy(
        "SMT",
        "SMT_INTERNAL_DIVERGENCE_REVERSAL",
    ) == CISD_REQUIRED

    assert resolve_cisd_policy(
        "WAVETREND_MOMENTUM",
        "WT_M5_BULLISH_CROSS",
    ) == NO_CISD


def test_orb_structural_entry():
    setup = {
        "setup_id": "ORB-NOW",
        "strategy": "ORB",
        "entry_model": "UNKNOWN_ENTRY_MODEL",
        "signal": "BUY",
        "entry": 4350.0,
        "orb_high": 4344.0,
        "orb_low": 4334.0,
    }

    snapshot = build_better_entry_observer(
        setup,
        historical_rows=[],
        enabled_override=True,
    )

    assert snapshot["cisd_policy"] == CISD_ON_RETEST
    assert snapshot["structural_anchor"]["type"] == "ORB_HIGH"
    assert snapshot["structural_anchor"]["price"] == 4344.0
    assert snapshot["structural_candidate_entry"] == 4344.0
    assert snapshot["structural_entry_improvement_usd"] == 6.0
    assert snapshot["preferred_observer_entry_basis"] == "STRUCTURAL_ANCHOR"
    assert snapshot["can_execute"] is False
    assert snapshot["can_modify_entry_sl_tp"] is False


def test_head_shoulders_neckline_anchor():
    setup = {
        "setup_id": "HS-NOW",
        "strategy": "HEAD_SHOULDERS",
        "entry_model": "HS_NECKLINE_RETEST",
        "signal": "SELL",
        "entry": 4318.0,
        "neckline": 4322.5,
    }

    snapshot = build_better_entry_observer(
        setup,
        historical_rows=[],
        enabled_override=True,
    )

    assert snapshot["structural_anchor"]["type"] == "NECKLINE"
    assert snapshot["structural_candidate_entry"] == 4322.5
    assert snapshot["structural_entry_improvement_usd"] == 4.5


def test_full_path_mae_is_never_used_as_entry_depth():
    setup = {
        "setup_id": "CURRENT",
        "strategy": "ORB",
        "entry_model": "UNKNOWN_ENTRY_MODEL",
        "signal": "BUY",
        "entry": 4350.0,
    }

    rows = [
        _row(
            f"H-{index}",
            pre_w10_mae=None,
        )
        for index in range(30)
    ]

    snapshot = build_better_entry_observer(
        setup,
        historical_rows=rows,
        enabled_override=True,
    )

    assert (
        snapshot["historical_calibration"]["full_path_mae"]["n"]
        == 30
    )
    assert snapshot["historical_candidate_entry"] is None
    assert snapshot["historical_wait_depth_usd"] is None
    assert snapshot["requires_pre_event_path_instrumentation"] is True


def test_pre_w10_history_can_calibrate_entry_after_min_sample():
    setup = {
        "setup_id": "CURRENT",
        "strategy": "ORB",
        "entry_model": "UNKNOWN_ENTRY_MODEL",
        "signal": "BUY",
        "entry": 4350.0,
    }

    rows = [
        _row(
            f"H-{index}",
            pre_w10_mae=4.0 + (index % 3),
        )
        for index in range(20)
    ]

    snapshot = build_better_entry_observer(
        setup,
        historical_rows=rows,
        enabled_override=True,
    )

    assert (
        snapshot["historical_calibration"]["pre_w10_calibration_ready"]
        is True
    )
    assert snapshot["historical_wait_depth_usd"] == 5.0
    assert snapshot["historical_candidate_entry"] == 4345.0


def test_current_setup_is_excluded_from_history():
    setup = {
        "setup_id": "CURRENT",
        "strategy": "ORB",
        "entry_model": "UNKNOWN_ENTRY_MODEL",
        "signal": "BUY",
        "entry": 4350.0,
    }

    rows = [
        _row(
            "CURRENT",
            pre_w10_mae=99.0,
        )
    ] + [
        _row(
            f"H-{index}",
            pre_w10_mae=5.0,
        )
        for index in range(20)
    ]

    snapshot = build_better_entry_observer(
        setup,
        historical_rows=rows,
        enabled_override=True,
    )

    assert (
        snapshot["historical_calibration"]["cohort_total"]
        == 20
    )
    assert snapshot["historical_wait_depth_usd"] == 5.0


def test_disabled_is_authority_free():
    snapshot = build_better_entry_observer(
        {
            "strategy": "ORB",
        },
        historical_rows=[],
        enabled_override=False,
    )

    assert snapshot["enabled"] is False
    assert snapshot["can_execute"] is False
    assert snapshot["can_block_trade"] is False
    assert snapshot["can_modify_score"] is False
    assert snapshot["can_modify_risk"] is False
    assert snapshot["can_modify_entry_sl_tp"] is False
    assert snapshot["can_modify_lot"] is False


def main():
    test_safe_defaults()
    test_policy_registry()
    test_orb_structural_entry()
    test_head_shoulders_neckline_anchor()
    test_full_path_mae_is_never_used_as_entry_depth()
    test_pre_w10_history_can_calibrate_entry_after_min_sample()
    test_current_setup_is_excluded_from_history()
    test_disabled_is_authority_free()

    print("PASS: Better Entry Optimizer V1 observer foundation")


if __name__ == "__main__":
    main()
