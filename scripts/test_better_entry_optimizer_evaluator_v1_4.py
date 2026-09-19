from __future__ import annotations

from scripts.evaluate_better_entry_optimizer_v1_4 import (
    build_report,
    extract_candidate_records,
    summarize_records,
)


def _candidate(
    *,
    basis,
    filled,
    candidate_win,
    missed_winner=False,
    candidate_entry=95.0,
    original_entry=100.0,
    wait=120.0,
    candidate_mae=2.0,
    candidate_mfe=12.0,
):
    return {
        "basis": basis,
        "candidate_entry": candidate_entry,
        "original_entry": original_entry,
        "original_sl": 90.0,
        "original_tp": 120.0,
        "status": (
            "FILLED_W10_REACHED"
            if candidate_win
            else (
                "FILLED_TRACKING"
                if filled
                else "WAITING_FILL"
            )
        ),
        "filled": filled,
        "fill_wait_seconds": (
            wait
            if filled
            else None
        ),
        "missed_winner": missed_winner,
        "max_favorable_usd_after_fill": (
            candidate_mfe
            if filled
            else 0.0
        ),
        "max_adverse_usd_after_fill": (
            candidate_mae
            if filled
            else 0.0
        ),
        "hit_plus_10_after_fill": candidate_win,
        "hit_tp_after_fill": False,
        "hit_sl_after_fill": False,
    }


def _row(
    setup_id,
    *,
    original_win,
    candidates,
    strategy="ORB",
    entry_model="UNKNOWN_ENTRY_MODEL",
    session="LONDON",
    market_condition="TRENDING",
    profile="MEDIAN_P50",
):
    return {
        "setup_id": setup_id,
        "status": "CLOSED",
        "strategy": strategy,
        "entry_model": entry_model,
        "signal": "BUY",
        "session": session,
        "market_condition": market_condition,
        "entry": 100.0,
        "max_adverse_usd": 6.0,
        "max_favorable_usd": (
            12.0
            if original_win
            else 4.0
        ),
        "hit_plus_10": original_win,
        "better_entry_observer_snapshot": {
            "cisd_policy": "CISD_ON_RETEST",
            "adaptive_wait_profile": {
                "profile": profile,
                "momentum": {
                    "state": "ALIGNED",
                },
                "participation": {
                    "state": "ALIGNED",
                },
            },
        },
        "better_entry_counterfactuals": candidates,
    }


def test_metrics_penalize_missed_winners():
    rows = [
        _row(
            "A",
            original_win=True,
            candidates={
                "STRUCTURAL": _candidate(
                    basis="STRUCTURAL_ANCHOR",
                    filled=True,
                    candidate_win=True,
                ),
            },
        ),
        _row(
            "B",
            original_win=True,
            candidates={
                "STRUCTURAL": _candidate(
                    basis="STRUCTURAL_ANCHOR",
                    filled=False,
                    candidate_win=False,
                    missed_winner=True,
                ),
            },
        ),
        _row(
            "C",
            original_win=False,
            candidates={
                "STRUCTURAL": _candidate(
                    basis="STRUCTURAL_ANCHOR",
                    filled=True,
                    candidate_win=False,
                ),
            },
        ),
        _row(
            "D",
            original_win=False,
            candidates={
                "STRUCTURAL": _candidate(
                    basis="STRUCTURAL_ANCHOR",
                    filled=False,
                    candidate_win=False,
                ),
            },
        ),
    ]

    records = extract_candidate_records(
        rows
    )
    summary = summarize_records(
        records
    )

    assert summary[
        "n"
    ] == 4
    assert summary[
        "filled"
    ] == 2
    assert summary[
        "fill_rate"
    ] == 0.5

    # 1 candidate win / 2 fills
    assert summary[
        "filled_setup_win_rate"
    ] == 0.5

    # 1 missed original winner / 2 original winners
    assert summary[
        "missed_winner_rate"
    ] == 0.5

    # 1 candidate win / 2 original winners
    assert summary[
        "opportunity_capture_rate"
    ] == 0.5


def test_terminal_waiting_candidate_is_normalized():
    rows = [
        _row(
            "A",
            original_win=False,
            candidates={
                "ADAPTIVE": _candidate(
                    basis="ADAPTIVE_HISTORICAL_RETRACEMENT",
                    filled=False,
                    candidate_win=False,
                ),
            },
        ),
    ]

    records = extract_candidate_records(
        rows
    )

    assert records[
        0
    ][
        "normalized_status"
    ] == "UNFILLED_TERMINAL"


def test_terminal_filled_tracking_is_normalized():
    rows = [
        _row(
            "A",
            original_win=False,
            candidates={
                "ADAPTIVE": _candidate(
                    basis="ADAPTIVE_HISTORICAL_RETRACEMENT",
                    filled=True,
                    candidate_win=False,
                ),
            },
        ),
    ]

    records = extract_candidate_records(
        rows
    )

    assert records[
        0
    ][
        "normalized_status"
    ] == "FILLED_TERMINAL_NO_EVENT"


def test_rr_improvement_uses_same_original_sl_tp():
    rows = [
        _row(
            "A",
            original_win=True,
            candidates={
                "STRUCTURAL": _candidate(
                    basis="STRUCTURAL_ANCHOR",
                    filled=True,
                    candidate_win=True,
                    candidate_entry=95.0,
                    original_entry=100.0,
                ),
            },
        ),
    ]

    records = extract_candidate_records(
        rows
    )
    record = records[
        0
    ]

    # Original BUY: risk 10, reward 20 => 2R.
    assert record[
        "original_rr"
    ] == 2.0

    # Candidate BUY at 95: risk 5, reward 25 => 5R.
    assert record[
        "candidate_rr"
    ] == 5.0
    assert record[
        "rr_improvement"
    ] == 3.0


def test_mae_improvement_is_original_minus_candidate():
    rows = [
        _row(
            "A",
            original_win=True,
            candidates={
                "STRUCTURAL": _candidate(
                    basis="STRUCTURAL_ANCHOR",
                    filled=True,
                    candidate_win=True,
                    candidate_mae=2.0,
                ),
            },
        ),
    ]

    summary = summarize_records(
        extract_candidate_records(
            rows
        )
    )

    assert summary[
        "mae_improvement_original_minus_candidate"
    ][
        "median"
    ] == 4.0


def test_report_separates_structural_and_adaptive():
    rows = [
        _row(
            "A",
            original_win=True,
            candidates={
                "STRUCTURAL": _candidate(
                    basis="STRUCTURAL_ANCHOR",
                    filled=True,
                    candidate_win=True,
                ),
                "ADAPTIVE": _candidate(
                    basis="ADAPTIVE_HISTORICAL_RETRACEMENT",
                    filled=False,
                    candidate_win=False,
                    missed_winner=True,
                ),
            },
        ),
    ]

    report = build_report(
        rows
    )

    assert (
        "STRUCTURAL_ANCHOR"
        in report[
            "by_basis"
        ]
    )
    assert (
        "ADAPTIVE_HISTORICAL_RETRACEMENT"
        in report[
            "by_basis"
        ]
    )


def test_authority_is_evaluation_only():
    report = build_report(
        []
    )

    authority = report[
        "authority"
    ]

    assert authority[
        "decision_impact"
    ] == "EVALUATION_ONLY"
    assert authority[
        "can_execute"
    ] is False
    assert authority[
        "can_block_trade"
    ] is False
    assert authority[
        "can_modify_score"
    ] is False
    assert authority[
        "can_modify_risk"
    ] is False
    assert authority[
        "can_modify_entry_sl_tp"
    ] is False
    assert authority[
        "can_modify_lot"
    ] is False


def main():
    test_metrics_penalize_missed_winners()
    test_terminal_waiting_candidate_is_normalized()
    test_terminal_filled_tracking_is_normalized()
    test_rr_improvement_uses_same_original_sl_tp()
    test_mae_improvement_is_original_minus_candidate()
    test_report_separates_structural_and_adaptive()
    test_authority_is_evaluation_only()

    print(
        "PASS: Better Entry Optimizer V1.4 counterfactual evaluator"
    )


if __name__ == "__main__":
    main()
