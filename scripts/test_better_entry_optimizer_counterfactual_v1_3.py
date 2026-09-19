from __future__ import annotations

from config import settings
from src import setup_outcome_tracker as tracker


def _base_item(
    *,
    signal="BUY",
    entry=100.0,
    sl=90.0,
    tp=120.0,
):
    return {
        "setup_id": "TEST",
        "created_at": "2026-09-19T10:00:00",
        "strategy": "ORB",
        "entry_model": "UNKNOWN_ENTRY_MODEL",
        "signal": signal,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "orb_high": 95.0 if signal == "BUY" else None,
        "orb_low": 105.0 if signal == "SELL" else None,
        "better_entry_detection_context": {
            "atr_14": 8.0,
            "momentum": "neutral",
            "signals": {
                "market_participation_state": "NORMAL",
            },
        },
    }


def _counterfactual(
    *,
    signal="BUY",
    candidate_entry=95.0,
):
    original_entry = (
        100.0
    )
    return tracker._better_entry_candidate_record(
        candidate_id="STRUCTURAL",
        basis="STRUCTURAL_ANCHOR",
        candidate_entry=candidate_entry,
        original_entry=original_entry,
        original_sl=90.0 if signal == "BUY" else 110.0,
        original_tp=120.0 if signal == "BUY" else 80.0,
        created_at="2026-09-19T10:00:00",
    )


def test_safe_default_toggle():
    assert (
        settings
        .ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER
        is False
    )
    assert settings.FIXED_LOT == 0.25


def test_initialize_is_disabled_by_default():
    item = _base_item()

    changed = (
        tracker
        ._initialize_better_entry_counterfactuals(
            item,
            {},
        )
    )

    assert changed is False
    assert (
        "better_entry_counterfactuals"
        not in item
    )


def test_buy_candidate_fills_on_retrace_and_tracks_path():
    item = _base_item()
    item[
        "better_entry_counterfactuals"
    ] = {
        "STRUCTURAL": _counterfactual(),
    }

    assert (
        tracker
        ._update_better_entry_counterfactuals(
            item,
            97.0,
            observed_at="2026-09-19T10:01:00",
        )
        is False
    )

    candidate = item[
        "better_entry_counterfactuals"
    ][
        "STRUCTURAL"
    ]

    assert candidate[
        "filled"
    ] is False

    assert (
        tracker
        ._update_better_entry_counterfactuals(
            item,
            95.0,
            observed_at="2026-09-19T10:02:00",
        )
        is True
    )

    assert candidate[
        "filled"
    ] is True
    assert candidate[
        "status"
    ] == "FILLED_TRACKING"
    assert candidate[
        "fill_wait_seconds"
    ] == 120.0

    tracker._update_better_entry_counterfactuals(
        item,
        101.0,
        observed_at="2026-09-19T10:03:00",
    )

    assert candidate[
        "max_favorable_usd_after_fill"
    ] == 6.0


def test_plus_10_after_better_fill_is_setup_win_but_not_terminal():
    item = _base_item()
    item[
        "better_entry_counterfactuals"
    ] = {
        "STRUCTURAL": _counterfactual(),
    }

    tracker._update_better_entry_counterfactuals(
        item,
        95.0,
        observed_at="2026-09-19T10:02:00",
    )
    tracker._update_better_entry_counterfactuals(
        item,
        105.0,
        observed_at="2026-09-19T10:04:00",
    )

    candidate = item[
        "better_entry_counterfactuals"
    ][
        "STRUCTURAL"
    ]

    assert candidate[
        "hit_plus_10_after_fill"
    ] is True
    assert candidate[
        "status"
    ] == "FILLED_W10_REACHED"
    assert candidate[
        "terminal"
    ] is False


def test_original_winner_before_fill_becomes_missed_winner():
    item = _base_item()
    item[
        "better_entry_counterfactuals"
    ] = {
        "STRUCTURAL": _counterfactual(),
    }

    tracker._update_better_entry_counterfactuals(
        item,
        110.0,
        observed_at="2026-09-19T10:03:00",
    )

    candidate = item[
        "better_entry_counterfactuals"
    ][
        "STRUCTURAL"
    ]

    assert candidate[
        "filled"
    ] is False
    assert candidate[
        "status"
    ] == "MISSED_WINNER"
    assert candidate[
        "missed_trade"
    ] is True
    assert candidate[
        "missed_winner"
    ] is True
    assert candidate[
        "terminal"
    ] is True

    # Later reversal cannot retroactively fill the missed winner.
    tracker._update_better_entry_counterfactuals(
        item,
        94.0,
        observed_at="2026-09-19T10:10:00",
    )

    assert candidate[
        "filled"
    ] is False
    assert candidate[
        "status"
    ] == "MISSED_WINNER"


def test_original_sl_is_preserved_for_counterfactual_trade():
    item = _base_item()
    item[
        "better_entry_counterfactuals"
    ] = {
        "STRUCTURAL": _counterfactual(),
    }

    tracker._update_better_entry_counterfactuals(
        item,
        95.0,
        observed_at="2026-09-19T10:02:00",
    )
    tracker._update_better_entry_counterfactuals(
        item,
        90.0,
        observed_at="2026-09-19T10:05:00",
    )

    candidate = item[
        "better_entry_counterfactuals"
    ][
        "STRUCTURAL"
    ]

    assert candidate[
        "hit_sl_after_fill"
    ] is True
    assert candidate[
        "status"
    ] == "FILLED_SL"
    assert candidate[
        "terminal"
    ] is True
    assert candidate[
        "original_sl"
    ] == 90.0


def test_sell_side_is_symmetric():
    item = _base_item(
        signal="SELL",
        entry=100.0,
        sl=110.0,
        tp=80.0,
    )
    item[
        "better_entry_counterfactuals"
    ] = {
        "STRUCTURAL": _counterfactual(
            signal="SELL",
            candidate_entry=105.0,
        ),
    }

    tracker._update_better_entry_counterfactuals(
        item,
        105.0,
        observed_at="2026-09-19T10:02:00",
    )
    tracker._update_better_entry_counterfactuals(
        item,
        95.0,
        observed_at="2026-09-19T10:04:00",
    )

    candidate = item[
        "better_entry_counterfactuals"
    ][
        "STRUCTURAL"
    ]

    assert candidate[
        "filled"
    ] is True
    assert candidate[
        "hit_plus_10_after_fill"
    ] is True


def test_counterfactual_authority_is_observer_only():
    candidate = _counterfactual()

    assert candidate[
        "decision_impact"
    ] == "OBSERVE_ONLY"
    assert candidate[
        "can_execute"
    ] is False
    assert candidate[
        "can_block_trade"
    ] is False
    assert candidate[
        "can_modify_score"
    ] is False
    assert candidate[
        "can_modify_risk"
    ] is False
    assert candidate[
        "can_modify_entry_sl_tp"
    ] is False
    assert candidate[
        "can_modify_lot"
    ] is False


def main():
    test_safe_default_toggle()
    test_initialize_is_disabled_by_default()
    test_buy_candidate_fills_on_retrace_and_tracks_path()
    test_plus_10_after_better_fill_is_setup_win_but_not_terminal()
    test_original_winner_before_fill_becomes_missed_winner()
    test_original_sl_is_preserved_for_counterfactual_trade()
    test_sell_side_is_symmetric()
    test_counterfactual_authority_is_observer_only()

    print(
        "PASS: Better Entry Optimizer V1.3 counterfactual tracker"
    )


if __name__ == "__main__":
    main()
