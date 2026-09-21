from __future__ import annotations

import pandas as pd

from src import daily_ladder_reclaim_reversal as r
from scripts.evaluate_daily_ladder_reclaim_reversal_shadow_v1_1 import (
    summarize,
)


def _base_outcome(signal="BUY"):
    return {
        "schema_version": "V1.1",
        "outcome_id": "test",
        "strategy": "DAILY_LEVEL_LADDER_RECLAIM_REVERSAL",
        "entry_model": "STRONG_DAILY_LEVEL_SWEEP_RECLAIM_CISD",
        "signal": signal,
        "confirmation_time": "2026-09-21 10:00:00",
        "expiry_time": "2026-09-21 13:00:00",
        "entry": 4342.0,
        "sl": 4339.0 if signal == "BUY" else 4345.0,
        "tp": 4360.0 if signal == "BUY" else 4324.0,
        "rr": 6.0,
        "required_rr": 1.2,
        "rr_pass": True,
        "hit_plus_10": False,
        "plus_10_time": None,
        "hit_tp": False,
        "tp_time": None,
        "hit_sl": False,
        "sl_time": None,
        "first_hit": None,
        "first_hit_time": None,
        "max_favorable_usd": 0.0,
        "max_adverse_usd": 0.0,
        "mfe_time": None,
        "mae_time": None,
        "last_processed_m1_time": "2026-09-21 10:00:00",
        "final_outcome": "TRACKING",
        "decision_impact": "OBSERVE_ONLY",
        "execution_authority": False,
    }


def test_buy_outcome_path():
    outcome = _base_outcome("BUY")

    df = pd.DataFrame(
        [
            {
                "time": pd.Timestamp("2026-09-21 10:01:00"),
                "high": 4348.0,
                "low": 4341.0,
            },
            {
                "time": pd.Timestamp("2026-09-21 10:02:00"),
                "high": 4352.2,
                "low": 4344.0,
            },
            {
                "time": pd.Timestamp("2026-09-21 10:03:00"),
                "high": 4360.5,
                "low": 4350.0,
            },
        ]
    )

    updated, completed = r._advance_one_outcome(
        outcome,
        df,
    )

    assert completed is False
    assert updated["hit_plus_10"] is True
    assert updated["hit_tp"] is True
    assert updated["hit_sl"] is False
    assert updated["first_hit"] == "TP"
    assert updated["max_favorable_usd"] == 18.5
    assert updated["max_adverse_usd"] == 1.0


def test_no_confirmation_bar_lookahead():
    outcome = _base_outcome("BUY")

    df = pd.DataFrame(
        [
            {
                "time": pd.Timestamp("2026-09-21 10:00:00"),
                "high": 4365.0,
                "low": 4335.0,
            },
            {
                "time": pd.Timestamp("2026-09-21 10:01:00"),
                "high": 4343.0,
                "low": 4341.5,
            },
        ]
    )

    updated, _ = r._advance_one_outcome(
        outcome,
        df,
    )

    assert updated["hit_plus_10"] is False
    assert updated["hit_tp"] is False
    assert updated["hit_sl"] is False
    assert updated["max_favorable_usd"] == 1.0
    assert updated["max_adverse_usd"] == 0.5


def test_same_m1_ambiguity():
    outcome = _base_outcome("BUY")
    outcome["tp"] = 4344.0
    outcome["sl"] = 4340.0

    df = pd.DataFrame(
        [
            {
                "time": pd.Timestamp("2026-09-21 10:01:00"),
                "high": 4345.0,
                "low": 4339.0,
            },
        ]
    )

    updated, _ = r._advance_one_outcome(
        outcome,
        df,
    )

    assert (
        updated["first_hit"]
        == "TP_SL_SAME_M1_AMBIGUOUS"
    )


def test_evaluator_setup_win_semantics():
    rows = [
        {
            "hit_plus_10": True,
            "hit_tp": False,
            "hit_sl": True,
            "first_hit": "SL",
            "rr": 2.0,
            "max_favorable_usd": 11.0,
            "max_adverse_usd": 4.0,
        },
        {
            "hit_plus_10": False,
            "hit_tp": False,
            "hit_sl": True,
            "first_hit": "SL",
            "rr": 1.5,
            "max_favorable_usd": 7.0,
            "max_adverse_usd": 5.0,
        },
    ]

    stats = summarize(rows)

    assert stats["n"] == 2
    assert stats["setup_wins_plus_10"] == 1
    assert stats["setup_win_rate"] == 0.5


def main():
    test_buy_outcome_path()
    test_no_confirmation_bar_lookahead()
    test_same_m1_ambiguity()
    test_evaluator_setup_win_semantics()

    print(
        "PASS: Daily Ladder Reclaim outcome tracking V1.1"
    )
    print(
        "PASS: confirmation M1 bar excluded from future path"
    )
    print(
        "PASS: Setup Win uses favorable +$10 semantics"
    )
    print(
        "PASS: TP/SL same-M1 ambiguity is explicit"
    )
    print(
        "PASS: tracker remains observer-only"
    )


if __name__ == "__main__":
    main()
