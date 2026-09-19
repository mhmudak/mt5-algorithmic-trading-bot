from __future__ import annotations

from config import settings
from src import notifier
from src import setup_outcome_tracker as tracker


def _item():
    return {
        "setup_id": "TG-BETTER-ENTRY-1",
        "strategy": "ORB",
        "entry_model": "ORB_RETEST",
        "signal": "BUY",
        "better_entry_counterfactual_scope": "PRIMARY",
        "better_entry_counterfactual_eligible": True,
        "better_entry_observer_snapshot": {
            "cisd_policy": "CISD_ON_RETEST",
            "adaptive_wait_profile": {
                "profile": "MEDIAN_P50",
            },
        },
    }


def _candidate():
    return tracker._better_entry_candidate_record(
        candidate_id="STRUCTURAL",
        basis="STRUCTURAL_ANCHOR",
        candidate_entry=4346.5,
        original_entry=4350.0,
        original_sl=4338.0,
        original_tp=4362.0,
        created_at="2026-09-19T15:00:00",
    )


def test_committed_shadow_default_is_still_false():
    assert (
        settings
        .ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER
        is False
    )
    assert settings.ENABLE_BETTER_ENTRY_OPTIMIZER is False
    assert settings.FIXED_LOT == 0.25


def test_notification_is_runtime_shadow_only():
    item = _item()
    candidate = _candidate()

    assert (
        tracker
        ._maybe_notify_better_entry_shadow(
            item,
            candidate,
        )
        is False
    )
    assert (
        candidate.get(
            "telegram_notified_statuses"
        )
        is None
    )


def test_notification_uses_notifier_and_deduplicates_status():
    item = _item()
    candidate = _candidate()

    messages = []
    original_flag = (
        settings
        .ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER
    )
    original_sender = (
        notifier.send_telegram_message
    )

    try:
        settings.ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER = True
        notifier.send_telegram_message = messages.append

        assert (
            tracker
            ._maybe_notify_better_entry_shadow(
                item,
                candidate,
            )
            is True
        )
        assert len(
            messages
        ) == 1
        assert (
            "WAITING FOR BETTER ENTRY"
            in messages[
                0
            ]
        )
        assert (
            "Strategy: ORB"
            in messages[
                0
            ]
        )
        assert (
            "CISD: CISD_ON_RETEST"
            in messages[
                0
            ]
        )
        assert (
            "Wait Profile: MEDIAN_P50"
            in messages[
                0
            ]
        )
        assert (
            "OBSERVATION ONLY"
            in messages[
                0
            ]
        )

        assert (
            tracker
            ._maybe_notify_better_entry_shadow(
                item,
                candidate,
            )
            is False
        )
        assert len(
            messages
        ) == 1

        candidate[
            "status"
        ] = "FILLED_TRACKING"
        candidate[
            "filled"
        ] = True
        candidate[
            "fill_wait_seconds"
        ] = 135.0

        assert (
            tracker
            ._maybe_notify_better_entry_shadow(
                item,
                candidate,
            )
            is True
        )
        assert len(
            messages
        ) == 2
        assert (
            "SHADOW ENTRY FILLED"
            in messages[
                1
            ]
        )
        assert (
            "Fill Wait: 135s"
            in messages[
                1
            ]
        )

    finally:
        notifier.send_telegram_message = (
            original_sender
        )
        settings.ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER = (
            original_flag
        )


def test_ineligible_research_row_never_notifies():
    item = _item()
    item[
        "better_entry_counterfactual_eligible"
    ] = False
    candidate = _candidate()

    original_flag = (
        settings
        .ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER
    )

    try:
        settings.ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER = True

        assert (
            tracker
            ._maybe_notify_better_entry_shadow(
                item,
                candidate,
            )
            is False
        )
    finally:
        settings.ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER = (
            original_flag
        )


def main():
    test_committed_shadow_default_is_still_false()
    test_notification_is_runtime_shadow_only()
    test_notification_uses_notifier_and_deduplicates_status()
    test_ineligible_research_row_never_notifies()

    print(
        "PASS: Better Entry V1.6 Telegram shadow notifications"
    )


if __name__ == "__main__":
    main()
