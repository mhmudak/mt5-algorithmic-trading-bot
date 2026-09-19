from __future__ import annotations

import ast
from pathlib import Path

from config import settings
from src import setup_outcome_tracker as tracker
from scripts.evaluate_better_entry_optimizer_v1_4 import (
    build_report,
)


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = (
    ROOT
    / "scripts"
    / "run_live_bot_better_entry_shadow.py"
)


def test_safe_committed_defaults():
    assert settings.ENABLE_BETTER_ENTRY_OPTIMIZER is False
    assert (
        settings
        .ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER
        is False
    )
    assert settings.FIXED_LOT == 0.25


def test_primary_event_policy():
    assert (
        tracker
        ._better_entry_counterfactual_scope(
            "SETUP_DETECTED"
        )
        == "PRIMARY"
    )
    assert (
        tracker
        ._better_entry_counterfactual_scope(
            "INTRABAR_PRICE_EVENT_EXECUTED"
        )
        == "PRIMARY"
    )


def test_low_rr_is_separate_entry_rescue_scope():
    for event in (
        "CANDIDATE_REJECTED_LOW_RR",
        "INTRABAR_PRICE_EVENT_REJECTED_LOW_RR",
    ):
        assert (
            tracker
            ._better_entry_counterfactual_scope(
                event
            )
            == "ENTRY_RESCUE"
        )


def test_unrelated_rejections_and_failures_are_ineligible():
    for event in (
        "CANDIDATE_REJECTED",
        "INTRABAR_PRICE_EVENT_EXECUTION_FAILED",
        "MTF_CONFLICT_CANDIDATE_TRACKED",
        "MTF_CONFLICT_EXECUTION_SUCCESS",
        "MTF_CONFLICT_EXECUTION_FAILED",
    ):
        assert (
            tracker
            ._better_entry_counterfactual_scope(
                event
            )
            == "INELIGIBLE"
        )


def test_evaluator_has_primary_and_rescue_views():
    rows = [
        {
            "setup_id": "PRIMARY-1",
            "status": "CLOSED",
            "strategy": "ORB",
            "entry_model": "UNKNOWN_ENTRY_MODEL",
            "signal": "BUY",
            "session": "LONDON",
            "market_condition": "TRENDING",
            "entry": 100.0,
            "max_adverse_usd": 4.0,
            "max_favorable_usd": 12.0,
            "hit_plus_10": True,
            "better_entry_counterfactual_scope": "PRIMARY",
            "better_entry_counterfactuals": {
                "STRUCTURAL": {
                    "basis": "STRUCTURAL_ANCHOR",
                    "candidate_entry": 98.0,
                    "original_entry": 100.0,
                    "original_sl": 90.0,
                    "original_tp": 120.0,
                    "status": "FILLED_W10_REACHED",
                    "filled": True,
                    "fill_wait_seconds": 60.0,
                    "missed_winner": False,
                    "max_favorable_usd_after_fill": 12.0,
                    "max_adverse_usd_after_fill": 2.0,
                    "hit_plus_10_after_fill": True,
                    "hit_tp_after_fill": False,
                    "hit_sl_after_fill": False,
                },
            },
        },
        {
            "setup_id": "RESCUE-1",
            "status": "CLOSED",
            "strategy": "FVG",
            "entry_model": "FVG_RETRACE_REACTION",
            "signal": "BUY",
            "session": "LONDON",
            "market_condition": "TRENDING",
            "entry": 100.0,
            "max_adverse_usd": 5.0,
            "max_favorable_usd": 8.0,
            "hit_plus_10": False,
            "better_entry_counterfactual_scope": "ENTRY_RESCUE",
            "better_entry_counterfactuals": {
                "ADAPTIVE": {
                    "basis": "ADAPTIVE_HISTORICAL_RETRACEMENT",
                    "candidate_entry": 96.0,
                    "original_entry": 100.0,
                    "original_sl": 90.0,
                    "original_tp": 120.0,
                    "status": "FILLED_TRACKING",
                    "filled": True,
                    "fill_wait_seconds": 120.0,
                    "missed_winner": False,
                    "max_favorable_usd_after_fill": 8.0,
                    "max_adverse_usd_after_fill": 1.0,
                    "hit_plus_10_after_fill": False,
                    "hit_tp_after_fill": False,
                    "hit_sl_after_fill": False,
                },
            },
        },
    ]

    report = build_report(
        rows
    )

    assert report[
        "primary_only"
    ][
        "n"
    ] == 1
    assert report[
        "entry_rescue_only"
    ][
        "n"
    ] == 1
    assert (
        "research_scope"
        in report[
            "groups"
        ]
    )


def test_shadow_launcher_changes_only_counterfactual_flag():
    source = LAUNCHER.read_text(
        encoding="utf-8"
    )
    tree = ast.parse(
        source
    )

    assignments = []

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.Assign,
        ):
            continue

        for target in node.targets:
            if (
                isinstance(
                    target,
                    ast.Attribute,
                )
                and isinstance(
                    target.value,
                    ast.Name,
                )
                and target.value.id
                == "settings"
            ):
                assignments.append(
                    target.attr
                )

    assert assignments == [
        "ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER"
    ]

    assert (
        'runpy.run_module(\n'
        '        "src.live_bot",'
        in source
    )
    assert (
        "settings.ENABLE_BETTER_ENTRY_OPTIMIZER = True"
        not in source
    )
    assert (
        "settings.EXECUTION_MODE ="
        not in source
    )
    assert (
        "settings.ALLOW_LIVE_TRADING ="
        not in source
    )
    assert (
        "settings.FIXED_LOT ="
        not in source
    )


def main():
    test_safe_committed_defaults()
    test_primary_event_policy()
    test_low_rr_is_separate_entry_rescue_scope()
    test_unrelated_rejections_and_failures_are_ineligible()
    test_evaluator_has_primary_and_rescue_views()
    test_shadow_launcher_changes_only_counterfactual_flag()

    print(
        "PASS: Better Entry V1.5 shadow activation policy"
    )


if __name__ == "__main__":
    main()
