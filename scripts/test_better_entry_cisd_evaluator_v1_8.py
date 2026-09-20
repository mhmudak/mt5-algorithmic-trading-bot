from __future__ import annotations

from config import settings
from scripts import evaluate_better_entry_cisd_v1_8 as e


def candidate(policy, filled, won, confirmed, qualified, armed=True, missed=False, armed_bar=100, confirmed_bar=160):
    return {
        "candidate_id": "STRUCTURAL",
        "basis": "STRUCTURAL_ANCHOR",
        "candidate_entry": 99.0,
        "original_entry": 100.0,
        "original_sl": 95.0,
        "original_tp": 110.0,
        "filled": filled,
        "hit_plus_10_after_fill": won,
        "missed_winner": missed,
        "max_adverse_usd_after_fill": 2.0 if filled else None,
        "max_favorable_usd_after_fill": 12.0 if won else 4.0 if filled else None,
        "fill_wait_seconds": 60.0 if filled else None,
        "cisd_observer": {
            "policy": policy,
            "status": "CONFIRMED" if confirmed else ("NOT_REQUIRED" if policy == "NO_CISD" else "WAITING_FOR_CISD"),
            "armed": armed,
            "armed_closed_bar_time": armed_bar if armed else None,
            "confirmed": confirmed,
            "confirmed_at_bar_time": confirmed_bar if confirmed else None,
            "shadow_entry_qualified": qualified,
        },
    }


def row(setup_id, scope, strategy, entry_model, c, status="CLOSED"):
    return {
        "setup_id": setup_id,
        "status": status,
        "better_entry_counterfactual_scope": scope,
        "strategy": strategy,
        "entry_model": entry_model,
        "signal": "BUY",
        "better_entry_observer_snapshot": {"cisd_policy": c["cisd_observer"]["policy"]},
        "better_entry_counterfactuals": {"STRUCTURAL": c},
    }


def rows():
    return [
        row("P1", "PRIMARY", "LIQUIDITY_SWEEP", "LIQUIDITY_SWEEP_REVERSAL", candidate("CISD_REQUIRED", True, True, True, True)),
        row("P2", "PRIMARY", "LIQUIDITY_SWEEP", "LIQUIDITY_SWEEP_REVERSAL", candidate("CISD_REQUIRED", True, False, False, False)),
        row("P3", "PRIMARY", "ORB", "WAIT_RETEST", candidate("CISD_ON_RETEST", True, True, True, True, armed_bar=200, confirmed_bar=320)),
        row("P4", "PRIMARY", "WAVETREND_MOMENTUM", "FAST_CONTINUATION", candidate("NO_CISD", True, True, False, True, armed=False)),
        row("P5", "PRIMARY", "ORB", "WAIT_RETEST", candidate("CISD_ON_RETEST", False, False, False, False, armed=False, missed=True)),
        row("R1", "ENTRY_RESCUE", "FVG", "FVG_RETRACE", candidate("CISD_ON_RETEST", True, True, True, True)),
        row("OPEN", "PRIMARY", "ORB", "WAIT_RETEST", candidate("CISD_ON_RETEST", True, True, True, True), status="TRACKING"),
    ]


def main():
    report = e.evaluate_rows(rows())
    p = report["primary_only"]

    assert p["n"] == 5
    assert p["cisd_observed_n"] == 5
    assert p["cisd_applicable_n"] == 4
    assert p["cisd_armed_n"] == 3
    assert p["cisd_confirmed_n"] == 2
    assert p["cisd_confirmation_rate_given_armed"] == round(2/3, 6)
    assert p["filled_n"] == 4
    assert p["candidate_setup_win_n"] == 3
    assert p["candidate_setup_win_rate"] == 0.75
    assert p["qualified_filled_n"] == 3
    assert p["qualified_setup_win_rate"] == 1.0
    assert p["unqualified_filled_n"] == 1
    assert p["unqualified_setup_win_rate"] == 0.0
    assert p["missed_winner_n"] == 1
    assert p["cisd_confirmation_wait_seconds"]["p50"] == 90.0

    assert report["entry_rescue_only"]["n"] == 1
    assert report["all"]["n"] == 6
    assert report["groups"]["cisd_policy"]["CISD_REQUIRED"]["n"] == 2
    assert report["authority"]["decision_impact"] == "EVALUATION_ONLY"
    assert report["authority"]["can_execute"] is False
    assert "observational, not causal proof" in e.format_report(report)
    assert "shadow-only" in e.format_report(report)

    assert settings.ENABLE_BETTER_ENTRY_OPTIMIZER is False
    assert settings.ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER is False
    assert settings.FIXED_LOT == 0.25

    print("PASS: Better Entry V1.8 CISD evaluator")


if __name__ == "__main__":
    main()
