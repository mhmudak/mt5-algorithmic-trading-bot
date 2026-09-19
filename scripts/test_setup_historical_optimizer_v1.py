from __future__ import annotations

import json
from pathlib import Path
import tempfile

from src import setup_historical_optimizer as optimizer


def _row(
    *,
    setup_id,
    created_at,
    strategy="FAILED_FVG_REVERSAL",
    signal="BUY",
    entry_model="FAILED_BEARISH_FVG_REVERSAL",
    session="LONDON",
    market_condition="RANGING",
    rr=0.90,
    first_hit="TP_TOUCH",
    hit_plus_10=True,
    hit_tp=True,
    hit_sl=False,
    mae=5.0,
    mfe=15.0,
    recovery=20.0,
):
    entry = 100.0
    sl = 90.0

    return {
        "setup_id": setup_id,
        "created_at": created_at,
        "updated_at": created_at,
        "strategy": strategy,
        "signal": signal,
        "entry_model": entry_model,
        "session": session,
        "market_condition": market_condition,
        "entry": entry,
        "sl": sl,
        "tp": entry + 10.0 * rr,
        "status": "CLOSED",
        "first_hit": first_hit,
        "final_outcome": first_hit,
        "hit_plus_10": hit_plus_10,
        "hit_tp": hit_tp,
        "hit_sl": hit_sl,
        "max_adverse_usd": mae,
        "max_favorable_usd": mfe,
        "max_recovery_swing_usd": recovery,
        "extra": {
            "rr": rr,
        },
    }


def _write_history(
    root: Path,
    rows,
):
    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        root
        / "setup_outcomes.json"
    ).write_text(
        json.dumps(
            list(rows),
            indent=2,
        ),
        encoding="utf-8",
    )


def _current(
    account_dir: Path,
    **updates,
):
    data = {
        "setup_id": "CURRENT-SETUP",
        "created_at": "2026-09-19T10:00:00",
        "strategy": "FAILED_FVG_REVERSAL",
        "signal": "BUY",
        "entry_model": "FAILED_BEARISH_FVG_REVERSAL",
        "session": "LONDON",
        "market_condition": "RANGING",
        "entry": 100.0,
        "sl": 90.0,
        "tp": 109.0,
        "setup_historical_optimizer_account_dir": str(
            account_dir
        ),
    }

    data.update(
        updates
    )

    return data


def test_disabled_is_empty():
    snapshot = (
        optimizer
        .build_setup_historical_optimizer_snapshot(
            {
                "strategy": "FAILED_FVG_REVERSAL",
                "signal": "BUY",
            },
            enabled_override=False,
        )
    )

    assert snapshot["enabled"] is False
    assert snapshot["available"] is False

    assert (
        optimizer
        .format_setup_historical_optimizer_block(
            snapshot
        )
        == ""
    )


def test_exact_low_rr_cohort_and_stats():
    with tempfile.TemporaryDirectory() as tmp:
        account_dir = Path(tmp)

        rows = []

        for index in range(25):
            win = index < 20

            rows.append(
                _row(
                    setup_id=f"HIST-{index}",
                    created_at=(
                        "2026-09-18T"
                        f"{index // 3:02d}:"
                        f"{(index % 3) * 15:02d}:00"
                    ),
                    first_hit=(
                        "TP_TOUCH"
                        if win
                        else "SL_TOUCH"
                    ),
                    hit_plus_10=win,
                    hit_tp=win,
                    hit_sl=not win,
                    mae=(
                        4.0
                        if win
                        else 18.0
                    ),
                    mfe=(
                        16.0
                        if win
                        else 3.0
                    ),
                    recovery=20.0,
                )
            )

        _write_history(
            account_dir,
            rows,
        )

        snapshot = (
            optimizer
            .build_setup_historical_optimizer_snapshot(
                _current(
                    account_dir
                ),
                enabled_override=True,
            )
        )

        assert snapshot["available"] is True
        assert (
            snapshot[
                "features"
            ][
                "rr_bucket"
            ]
            == "RR_LT_1_00"
        )

        stats = snapshot[
            "stats"
        ]

        assert stats["decisive"] == 25
        assert round(
            stats["win_rate"],
            4,
        ) == 0.8
        assert (
            snapshot[
                "confidence"
            ]
            == "MEDIUM"
        )
        assert (
            snapshot[
                "decision_impact"
            ]
            == "DISPLAY_ONLY"
        )
        assert (
            snapshot[
                "can_execute"
            ]
            is False
        )
        assert (
            snapshot[
                "can_modify_score"
            ]
            is False
        )


def test_current_and_future_rows_do_not_leak():
    with tempfile.TemporaryDirectory() as tmp:
        account_dir = Path(tmp)

        rows = [
            _row(
                setup_id=f"LOSS-{index}",
                created_at=(
                    "2026-09-18T"
                    f"{index:02d}:00:00"
                ),
                first_hit="SL_TOUCH",
                hit_plus_10=False,
                hit_tp=False,
                hit_sl=True,
            )
            for index in range(10)
        ]

        rows.append(
            _row(
                setup_id="CURRENT-SETUP",
                created_at="2026-09-19T10:00:00",
                first_hit="TP_TOUCH",
            )
        )

        # Created before current setup, but terminal result became
        # knowable after current setup. Strict replay must exclude it.
        late_resolved = _row(
            setup_id="LATE-RESOLVED",
            created_at="2026-09-19T09:00:00",
            first_hit="TP_TOUCH",
        )
        late_resolved[
            "updated_at"
        ] = "2026-09-19T10:30:00"
        rows.append(
            late_resolved
        )

        rows.extend(
            [
                _row(
                    setup_id=f"FUTURE-{index}",
                    created_at=(
                        "2026-09-20T"
                        f"{index:02d}:00:00"
                    ),
                    first_hit="TP_TOUCH",
                )
                for index in range(10)
            ]
        )

        _write_history(
            account_dir,
            rows,
        )

        snapshot = (
            optimizer
            .build_setup_historical_optimizer_snapshot(
                _current(
                    account_dir
                ),
                enabled_override=True,
            )
        )

        stats = snapshot[
            "stats"
        ]

        assert stats["decisive"] == 10
        assert stats["wins"] == 0
        assert stats["losses"] == 10
        assert stats["win_rate"] == 0.0



def test_tracking_row_with_outcome_is_not_mature_history():
    with tempfile.TemporaryDirectory() as tmp:
        account_dir = Path(tmp)

        rows = [
            _row(
                setup_id=f"LOSS-{index}",
                created_at=(
                    "2026-09-18T"
                    f"{index:02d}:00:00"
                ),
                first_hit="SL_TOUCH",
                hit_plus_10=False,
                hit_tp=False,
                hit_sl=True,
            )
            for index in range(10)
        ]

        tracking = _row(
            setup_id="TRACKING-W10",
            created_at="2026-09-18T12:30:00",
            first_hit="W10",
            hit_plus_10=True,
            hit_tp=True,
            hit_sl=False,
            mae=2.0,
            mfe=20.0,
        )
        tracking[
            "status"
        ] = "TRACKING"
        tracking[
            "final_outcome"
        ] = "W10"

        rows.append(
            tracking
        )

        _write_history(
            account_dir,
            rows,
        )

        snapshot = (
            optimizer
            .build_setup_historical_optimizer_snapshot(
                _current(
                    account_dir
                ),
                enabled_override=True,
            )
        )

        stats = snapshot[
            "stats"
        ]

        assert stats["total"] == 10
        assert stats["decisive"] == 10
        assert stats["hit_plus_10_known"] == 10
        assert stats["hit_plus_10_true"] == 0



def test_w10_then_sl_is_still_setup_win():
    with tempfile.TemporaryDirectory() as tmp:
        account_dir = Path(tmp)

        rows = []
        for index in range(19):
            rows.append(
                _row(
                    setup_id=f"BASE-{index}",
                    created_at=(
                        "2026-09-18T"
                        f"{index:02d}:00:00"
                    ),
                    first_hit="SL_TOUCH",
                    hit_plus_10=False,
                    hit_tp=False,
                    hit_sl=True,
                )
            )

        w10_then_sl = _row(
            setup_id="W10-THEN-SL",
            created_at="2026-09-18T19:30:00",
            first_hit="W10",
            hit_plus_10=True,
            hit_tp=False,
            hit_sl=True,
            mae=12.0,
            mfe=11.0,
        )
        w10_then_sl["final_outcome"] = "SL_TOUCH"
        rows.append(w10_then_sl)

        _write_history(account_dir, rows)

        snapshot = optimizer.build_setup_historical_optimizer_snapshot(
            _current(account_dir),
            enabled_override=True,
        )
        stats = snapshot["stats"]

        assert stats["setup_sample"] == 20
        assert stats["setup_wins"] == 1
        assert stats["setup_losses"] == 19
        assert stats["setup_win_rate"] == 0.05
        assert stats["sl_reach_true"] == 20
        assert stats["tp_reach_true"] == 0


def test_unmeasured_default_false_is_not_setup_loss():
    with tempfile.TemporaryDirectory() as tmp:
        account_dir = Path(tmp)

        rows = [
            _row(
                setup_id=f"MEASURED-{index}",
                created_at=(
                    "2026-09-18T"
                    f"{index:02d}:00:00"
                ),
                first_hit=(
                    "TP_TOUCH"
                    if index < 10
                    else "SL_TOUCH"
                ),
                hit_plus_10=(index < 10),
                hit_tp=(index < 10),
                hit_sl=(index >= 10),
            )
            for index in range(20)
        ]

        unmeasured = _row(
            setup_id="UNMEASURED",
            created_at="2026-09-18T21:00:00",
            first_hit="",
            hit_plus_10=False,
            hit_tp=False,
            hit_sl=False,
        )
        unmeasured["max_adverse_usd"] = None
        unmeasured["max_favorable_usd"] = None
        unmeasured["max_recovery_swing_usd"] = None
        unmeasured["final_outcome"] = "BREAKEVEN"
        rows.append(unmeasured)

        _write_history(account_dir, rows)

        snapshot = optimizer.build_setup_historical_optimizer_snapshot(
            _current(account_dir),
            enabled_override=True,
        )
        stats = snapshot["stats"]

        assert stats["total"] == 21
        assert stats["setup_sample"] == 20
        assert stats["setup_wins"] == 10
        assert stats["setup_losses"] == 10
        assert stats["setup_win_rate"] == 0.5
        assert round(stats["setup_coverage"], 6) == round(20 / 21, 6)


def test_ambiguous_tp_sl_is_not_decisive():
    with tempfile.TemporaryDirectory() as tmp:
        account_dir = Path(tmp)

        rows = [
            _row(
                setup_id=f"WIN-{index}",
                created_at=(
                    "2026-09-18T"
                    f"{index:02d}:00:00"
                ),
            )
            for index in range(5)
        ]

        ambiguous = _row(
            setup_id="AMBIGUOUS",
            created_at="2026-09-18T12:30:00",
            first_hit="",
            hit_tp=True,
            hit_sl=True,
        )
        ambiguous["final_outcome"] = "TP_TOUCH"

        rows.append(
            ambiguous
        )

        _write_history(
            account_dir,
            rows,
        )

        snapshot = (
            optimizer
            .build_setup_historical_optimizer_snapshot(
                _current(
                    account_dir
                ),
                enabled_override=True,
            )
        )

        stats = snapshot[
            "stats"
        ]

        assert stats["tp_first_wins"] == 5
        assert stats["sl_first_losses"] == 0
        assert stats["ambiguous"] == 1
        assert stats["first_hit_decisive"] == 5


def test_sparse_specific_cohort_falls_back():
    with tempfile.TemporaryDirectory() as tmp:
        account_dir = Path(tmp)

        rows = []

        for index in range(30):
            rows.append(
                _row(
                    setup_id=f"ALL-{index}",
                    created_at=(
                        "2026-09-18T"
                        f"{index // 2:02d}:"
                        f"{(index % 2) * 30:02d}:00"
                    ),
                    session=(
                        "LONDON"
                        if index < 4
                        else "ASIA"
                    ),
                    first_hit=(
                        "TP_TOUCH"
                        if index % 2 == 0
                        else "SL_TOUCH"
                    ),
                    hit_plus_10=(
                        index % 2 == 0
                    ),
                    hit_tp=(
                        index % 2 == 0
                    ),
                    hit_sl=(
                        index % 2 != 0
                    ),
                )
            )

        _write_history(
            account_dir,
            rows,
        )

        snapshot = (
            optimizer
            .build_setup_historical_optimizer_snapshot(
                _current(
                    account_dir,
                    session="LONDON",
                ),
                enabled_override=True,
            )
        )

        assert (
            snapshot["stats"][
                "decisive"
            ]
            >= 20
        )
        assert (
            snapshot["cohort"][
                "name"
            ]
            in {
                "MODEL_RR",
                "SIGNAL_RR",
                "STRATEGY_RR",
                "SIGNAL",
                "STRATEGY",
            }
        )


def test_upgrade_guidance_identifies_missing_data():
    with tempfile.TemporaryDirectory() as tmp:
        account_dir = Path(tmp)

        rows = [
            _row(
                setup_id=f"SMALL-{index}",
                created_at=(
                    "2026-09-18T"
                    f"{index:02d}:00:00"
                ),
            )
            for index in range(5)
        ]

        _write_history(
            account_dir,
            rows,
        )

        snapshot = (
            optimizer
            .build_setup_historical_optimizer_snapshot(
                _current(
                    account_dir,
                    market_condition="INTRABAR_PENDING",
                    scenario_key=None,
                    context_key=None,
                ),
                enabled_override=True,
            )
        )

        guidance = " | ".join(
            snapshot[
                "upgrade_guidance"
            ]
        )

        assert (
            "more measured +$10 setup outcomes"
            in guidance
        )
        assert (
            "resolved market regime"
            in guidance
        )


def test_formatter_contains_observer_stats():
    with tempfile.TemporaryDirectory() as tmp:
        account_dir = Path(tmp)

        rows = [
            _row(
                setup_id=f"FMT-{index}",
                created_at=(
                    "2026-09-18T"
                    f"{index // 3:02d}:"
                    f"{(index % 3) * 15:02d}:00"
                ),
                first_hit=(
                    "TP_TOUCH"
                    if index < 15
                    else "SL_TOUCH"
                ),
                hit_plus_10=(
                    index < 16
                ),
                hit_tp=(
                    index < 15
                ),
                hit_sl=(
                    index >= 15
                ),
            )
            for index in range(20)
        ]

        _write_history(
            account_dir,
            rows,
        )

        snapshot = (
            optimizer
            .build_setup_historical_optimizer_snapshot(
                _current(
                    account_dir
                ),
                enabled_override=True,
            )
        )

        block = (
            optimizer
            .format_setup_historical_optimizer_block(
                snapshot
            )
        )

        assert "HISTORICAL OPTIMIZER [OBSERVE ONLY]" in block
        assert "Setup Win:" in block
        assert "Win Definition: +$10 favorable move = SETUP WIN" in block
        assert "RR Bucket: RR_LT_1_00" in block
        assert "Confidence:" in block


def main():
    test_disabled_is_empty()
    test_exact_low_rr_cohort_and_stats()
    test_current_and_future_rows_do_not_leak()
    test_tracking_row_with_outcome_is_not_mature_history()
    test_w10_then_sl_is_still_setup_win()
    test_unmeasured_default_false_is_not_setup_loss()
    test_ambiguous_tp_sl_is_not_decisive()
    test_sparse_specific_cohort_falls_back()
    test_upgrade_guidance_identifies_missing_data()
    test_formatter_contains_observer_stats()

    print(
        "PASS: Setup Historical Optimizer V1"
    )


if __name__ == "__main__":
    main()
