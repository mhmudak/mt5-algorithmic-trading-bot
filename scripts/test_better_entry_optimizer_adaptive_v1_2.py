from __future__ import annotations

from config import settings
from src.better_entry_optimizer import (
    build_better_entry_observer,
)


def _row(
    setup_id,
    *,
    strategy="ORB",
    entry_model="UNKNOWN_ENTRY_MODEL",
    signal="BUY",
    pre_w10=4.0,
):
    return {
        "setup_id": setup_id,
        "status": "CLOSED",
        "strategy": strategy,
        "entry_model": entry_model,
        "signal": signal,
        "path_observed": True,
        "hit_plus_10": True,
        "hit_tp": True,
        "hit_sl": False,
        "first_hit": "W10",
        "max_favorable_usd": 14.0,
        "max_adverse_usd": 8.0,
        "max_recovery_swing_usd": 16.0,
        "pre_w10_max_adverse_usd": pre_w10,
        "time_to_pre_w10_max_adverse_seconds": 180.0,
    }


def _setup(
    *,
    momentum,
    participation,
):
    return {
        "setup_id": "CURRENT",
        "strategy": "ORB",
        "entry_model": "UNKNOWN_ENTRY_MODEL",
        "signal": "BUY",
        "entry": 100.0,
        "orb_high": 95.0,
        "better_entry_detection_context": {
            "atr_14": 8.0,
            "momentum": momentum,
            "signals": {
                "market_participation_state": participation,
            },
        },
    }


def _history():
    values = [
        2.0,
        3.0,
        4.0,
        5.0,
        6.0,
    ]

    rows = []

    for index in range(20):
        rows.append(
            _row(
                f"SPEC-{index}",
                pre_w10=values[index % len(values)],
            )
        )

    return rows


def test_settings_safe_defaults():
    assert settings.ENABLE_BETTER_ENTRY_OPTIMIZER is False
    assert settings.BETTER_ENTRY_OPTIMIZER_MIN_HISTORICAL_SAMPLE == 20
    assert settings.BETTER_ENTRY_OPTIMIZER_HIGH_CONFIDENCE_SAMPLE == 50
    assert settings.FIXED_LOT == 0.25


def test_strong_aligned_selects_shallow_p25():
    snapshot = build_better_entry_observer(
        _setup(
            momentum="strong_bullish_displacement",
            participation="STRONG_ALIGNED",
        ),
        historical_rows=_history(),
        enabled_override=True,
    )

    profile = snapshot[
        "adaptive_wait_profile"
    ]

    assert profile[
        "profile"
    ] == "SHALLOW_P25"
    assert profile[
        "quantile_key"
    ] == "p25"

    depth = snapshot[
        "adaptive_historical_depth"
    ][
        "depth_usd"
    ]

    assert depth == 3.0
    assert snapshot[
        "adaptive_statistical_entry"
    ] == 97.0


def test_weak_state_selects_deep_p75():
    snapshot = build_better_entry_observer(
        _setup(
            momentum="weak_bullish_momentum",
            participation="WEAK",
        ),
        historical_rows=_history(),
        enabled_override=True,
    )

    assert snapshot[
        "adaptive_wait_profile"
    ][
        "profile"
    ] == "DEEP_P75"
    assert snapshot[
        "adaptive_historical_depth"
    ][
        "depth_usd"
    ] == 5.0
    assert snapshot[
        "adaptive_statistical_entry"
    ] == 95.0


def test_unknown_participation_is_conservative_median():
    snapshot = build_better_entry_observer(
        _setup(
            momentum="strong_bullish_displacement",
            participation="UNRESOLVED",
        ),
        historical_rows=_history(),
        enabled_override=True,
    )

    assert snapshot[
        "adaptive_wait_profile"
    ][
        "profile"
    ] == "DEEP_P75"


def test_neutral_state_selects_median():
    setup = _setup(
        momentum="neutral",
        participation="NORMAL",
    )

    snapshot = build_better_entry_observer(
        setup,
        historical_rows=_history(),
        enabled_override=True,
    )

    assert snapshot[
        "adaptive_wait_profile"
    ][
        "momentum"
    ][
        "state"
    ] == "UNKNOWN"
    assert snapshot[
        "adaptive_wait_profile"
    ][
        "profile"
    ] == "MEDIAN_P50"
    assert snapshot[
        "adaptive_historical_depth"
    ][
        "depth_usd"
    ] == 4.0


def test_specific_history_is_shrunk_toward_prior_until_n50():
    setup = {
        "setup_id": "CURRENT",
        "strategy": "HEAD_SHOULDERS",
        "entry_model": "HS_NECKLINE_RETEST",
        "signal": "SELL",
        "entry": 100.0,
        "neckline": 104.0,
        "better_entry_detection_context": {
            "momentum": "neutral",
            "signals": {
                "market_participation_state": "NORMAL",
            },
        },
    }

    rows = []

    for index in range(20):
        rows.append(
            _row(
                f"SPEC-{index}",
                strategy="HEAD_SHOULDERS",
                entry_model="HS_NECKLINE_RETEST",
                signal="SELL",
                pre_w10=6.0,
            )
        )

    for index in range(60):
        rows.append(
            _row(
                f"PRIOR-{index}",
                strategy="HEAD_SHOULDERS",
                entry_model="HS_NECKLINE_BREAKOUT",
                signal="SELL",
                pre_w10=3.0,
            )
        )

    snapshot = build_better_entry_observer(
        setup,
        historical_rows=rows,
        enabled_override=True,
    )

    adaptive = snapshot[
        "adaptive_historical_depth"
    ]

    # n=20 / high-confidence 50 -> 0.40 specific weight.
    # 6 * 0.40 + 3 * 0.60 = 4.2
    assert round(
        adaptive[
            "specific_weight"
        ],
        6,
    ) == 0.4
    assert round(
        adaptive[
            "depth_usd"
        ],
        6,
    ) == 4.2
    assert adaptive[
        "source"
    ] == "SHRUNK_SPECIFIC_TO_STRATEGY_SIGNAL_PRIOR"


def test_structure_remains_primary_anchor():
    snapshot = build_better_entry_observer(
        _setup(
            momentum="strong_bullish_displacement",
            participation="STRONG_ALIGNED",
        ),
        historical_rows=_history(),
        enabled_override=True,
    )

    assert snapshot[
        "structural_candidate_entry"
    ] == 95.0
    assert snapshot[
        "adaptive_statistical_entry"
    ] == 97.0

    assert snapshot[
        "preferred_observer_entry_basis"
    ] == "STRUCTURAL_ANCHOR"
    assert snapshot[
        "preferred_observer_entry"
    ] == 95.0


def test_observer_has_no_authority():
    snapshot = build_better_entry_observer(
        _setup(
            momentum="strong_bullish_displacement",
            participation="STRONG_ALIGNED",
        ),
        historical_rows=_history(),
        enabled_override=True,
    )

    assert snapshot[
        "decision_impact"
    ] == "OBSERVE_ONLY"
    assert snapshot[
        "can_execute"
    ] is False
    assert snapshot[
        "can_block_trade"
    ] is False
    assert snapshot[
        "can_modify_score"
    ] is False
    assert snapshot[
        "can_modify_risk"
    ] is False
    assert snapshot[
        "can_modify_entry_sl_tp"
    ] is False
    assert snapshot[
        "can_modify_lot"
    ] is False


def main():
    test_settings_safe_defaults()
    test_strong_aligned_selects_shallow_p25()
    test_weak_state_selects_deep_p75()
    test_unknown_participation_is_conservative_median()
    test_neutral_state_selects_median()
    test_specific_history_is_shrunk_toward_prior_until_n50()
    test_structure_remains_primary_anchor()
    test_observer_has_no_authority()

    print(
        "PASS: Better Entry Optimizer V1.2 adaptive observer"
    )


if __name__ == "__main__":
    main()
