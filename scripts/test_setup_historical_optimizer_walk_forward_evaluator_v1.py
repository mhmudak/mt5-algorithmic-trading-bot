from __future__ import annotations

from scripts.evaluate_setup_historical_optimizer_walk_forward_v2 import (
    evaluate_rows,
    format_report,
)


def _row(
    setup_id,
    *,
    predicted,
    actual,
    confidence="MEDIUM",
    rr_bucket="RR_LT_1_00",
    status="CLOSED",
    path_observed=True,
    snapshot_available=True,
):
    return {
        "setup_id": setup_id,
        "status": status,
        "strategy": "FAILED_FVG_REVERSAL",
        "signal": "BUY",
        "session": "LONDON",
        "market_condition": "RANGING",
        "path_observed": path_observed,
        "max_favorable_usd": 12.0 if actual else 3.0,
        "max_adverse_usd": 4.0 if actual else 13.0,
        "max_recovery_swing_usd": 16.0,
        "hit_plus_10": actual,
        "hit_tp": actual,
        "hit_sl": not actual,
        "first_hit": "TP_TOUCH" if actual else "SL_TOUCH",
        "historical_optimizer_snapshot": {
            "snapshot_schema_version": "V2",
            "optimizer_version": "V1.1",
            "available": snapshot_available,
            "setup_win_rate": predicted,
            "confidence": confidence,
            "rr_bucket": rr_bucket,
            "cohort": {
                "name": "SIGNAL_RR",
            },
        },
    }


def test_calibration_math():
    rows = [
        _row(
            "A",
            predicted=0.75,
            actual=True,
        ),
        _row(
            "B",
            predicted=0.75,
            actual=True,
        ),
        _row(
            "C",
            predicted=0.75,
            actual=False,
        ),
        _row(
            "D",
            predicted=0.75,
            actual=False,
        ),
    ]

    report = evaluate_rows(
        rows
    )
    overall = report[
        "overall"
    ]

    assert overall["n"] == 4
    assert overall["actual_wins"] == 2
    assert overall["actual_setup_win_rate"] == 0.5
    assert overall["predicted_mean_setup_win_rate"] == 0.75
    assert overall[
        "calibration_gap_actual_minus_predicted"
    ] == -0.25

    expected_brier = (
        (
            (0.75 - 1.0) ** 2
            + (0.75 - 1.0) ** 2
            + (0.75 - 0.0) ** 2
            + (0.75 - 0.0) ** 2
        )
        / 4
    )

    assert abs(
        overall["brier_score"]
        - expected_brier
    ) < 1e-12

    assert "mean_absolute_prediction_error" in overall
    assert "mean_absolute_calibration_error" not in overall


def test_w10_then_sl_is_actual_setup_win():
    row = _row(
        "W10-SL",
        predicted=0.60,
        actual=True,
    )
    row[
        "hit_tp"
    ] = False
    row[
        "hit_sl"
    ] = True
    row[
        "first_hit"
    ] = "W10"

    report = evaluate_rows(
        [
            row,
        ]
    )

    assert report[
        "overall"
    ][
        "actual_setup_win_rate"
    ] == 1.0


def test_tracking_is_excluded():
    rows = [
        _row(
            "MATURE",
            predicted=0.5,
            actual=True,
        ),
        _row(
            "TRACKING",
            predicted=0.9,
            actual=True,
            status="TRACKING",
        ),
    ]

    report = evaluate_rows(
        rows
    )

    assert report[
        "overall"
    ][
        "n"
    ] == 1


def test_unobserved_default_zero_is_excluded():
    row = _row(
        "UNOBSERVED",
        predicted=0.2,
        actual=False,
        path_observed=False,
    )
    row[
        "max_favorable_usd"
    ] = 0.0
    row[
        "max_adverse_usd"
    ] = 0.0
    row[
        "max_recovery_swing_usd"
    ] = 0.0
    row[
        "hit_tp"
    ] = False
    row[
        "hit_sl"
    ] = False
    row[
        "first_hit"
    ] = None

    report = evaluate_rows(
        [
            row,
        ]
    )

    assert report[
        "coverage"
    ][
        "mature_measured_rows_with_snapshot"
    ] == 0
    assert report[
        "overall"
    ][
        "n"
    ] == 0


def test_unavailable_prediction_is_not_calibrated():
    row = _row(
        "NO-PREDICTION",
        predicted=None,
        actual=True,
        snapshot_available=False,
    )

    report = evaluate_rows(
        [
            row,
        ]
    )

    assert report[
        "coverage"
    ][
        "prediction_unavailable_rows"
    ] == 1
    assert report[
        "overall"
    ][
        "n"
    ] == 0


def test_group_breakdowns():
    rows = [
        _row(
            "HIGH",
            predicted=0.8,
            actual=True,
            confidence="HIGH",
            rr_bucket="RR_GE_2_00",
        ),
        _row(
            "LOW",
            predicted=0.4,
            actual=False,
            confidence="LOW",
            rr_bucket="RR_LT_1_00",
        ),
    ]

    report = evaluate_rows(
        rows
    )

    confidence_groups = {
        item["group"]: item
        for item in report[
            "groups"
        ][
            "confidence"
        ]
    }

    assert confidence_groups[
        "HIGH"
    ][
        "n"
    ] == 1
    assert confidence_groups[
        "LOW"
    ][
        "n"
    ] == 1

    rr_groups = {
        item["group"]: item
        for item in report[
            "groups"
        ][
            "rr_bucket"
        ]
    }

    assert "RR_GE_2_00" in rr_groups
    assert "RR_LT_1_00" in rr_groups


def test_report_is_observer_only():
    report = evaluate_rows(
        []
    )

    authority = report[
        "authority"
    ]

    assert authority[
        "observer_only"
    ] is True
    assert authority[
        "can_execute"
    ] is False
    assert authority[
        "can_block_trade"
    ] is False
    assert authority[
        "can_modify_score"
    ] is False

    text = format_report(
        report
    )

    assert "OBSERVE ONLY" in text
    assert "+$10 favorable move = Setup Win" in text
    assert "SETUP HISTORICAL OPTIMIZER - WALK-FORWARD EVALUATION" in text


def main():
    test_calibration_math()
    test_w10_then_sl_is_actual_setup_win()
    test_tracking_is_excluded()
    test_unobserved_default_zero_is_excluded()
    test_unavailable_prediction_is_not_calibrated()
    test_group_breakdowns()
    test_report_is_observer_only()

    print(
        "PASS: Setup Historical Optimizer Walk-Forward Evaluator V1"
    )


if __name__ == "__main__":
    main()
