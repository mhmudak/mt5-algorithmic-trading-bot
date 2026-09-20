from __future__ import annotations

from config import settings
from src import cisd_observer
from src import notifier
from src import setup_outcome_tracker as tracker


def _rates():
    return [
        {
            "time": 100,
            "open": 100.0,
            "close": 99.0,
        },
        {
            "time": 160,
            "open": 99.0,
            "close": 98.5,
        },
        {
            "time": 220,
            "open": 98.5,
            "close": 100.5,
        },
    ]


def _sell_rates():
    return [
        {
            "time": 100,
            "open": 100.0,
            "close": 101.0,
        },
        {
            "time": 160,
            "open": 101.0,
            "close": 101.5,
        },
        {
            "time": 220,
            "open": 101.5,
            "close": 99.5,
        },
    ]


def _snapshot(rates):
    return {
        "available": True,
        "timeframe": "M1",
        "bars": rates,
        "latest_closed_bar_time": rates[
            -1
        ][
            "time"
        ],
        "reason": None,
    }


def _candidate(
    filled=False,
):
    return {
        "candidate_id": "STRUCTURAL",
        "basis": "STRUCTURAL_ANCHOR",
        "candidate_entry": 99.0,
        "original_entry": 100.0,
        "original_sl": 95.0,
        "original_tp": 110.0,
        "status": (
            "FILLED_TRACKING"
            if filled
            else "WAITING_FILL"
        ),
        "filled": bool(
            filled
        ),
        "fill_at": (
            "2026-09-19T15:10:00"
            if filled
            else None
        ),
    }


def test_buy_cisd_detection():
    event = cisd_observer.detect_cisd_event(
        _rates(),
        "BUY",
        after_bar_time=160,
        timeframe="M1",
    )

    assert event is not None
    assert event.reference_candle_time == 160
    assert event.reference_open == 99.0
    assert event.confirmation_candle_time == 220
    assert event.confirmation_close == 100.5


def test_sell_cisd_detection():
    event = cisd_observer.detect_cisd_event(
        _sell_rates(),
        "SELL",
        after_bar_time=160,
        timeframe="M1",
    )

    assert event is not None
    assert event.reference_candle_time == 160
    assert event.reference_open == 101.0
    assert event.confirmation_candle_time == 220
    assert event.confirmation_close == 99.5


def test_required_arms_without_using_old_confirmation():
    candidate = _candidate(
        filled=False
    )

    first = {
        "available": True,
        "timeframe": "M1",
        "bars": _rates()[
            :2
        ],
        "latest_closed_bar_time": 160,
        "reason": None,
    }

    assert (
        cisd_observer.update_candidate_cisd_state(
            candidate,
            policy="CISD_REQUIRED",
            signal="BUY",
            closed_snapshot=first,
            observed_at="2026-09-19T15:00:00",
        )
        is True
    )

    state = candidate[
        "cisd_observer"
    ]
    assert state[
        "armed_closed_bar_time"
    ] == 160
    assert state[
        "status"
    ] == "WAITING_FOR_CISD"
    assert state[
        "confirmed"
    ] is False

    assert (
        cisd_observer.update_candidate_cisd_state(
            candidate,
            policy="CISD_REQUIRED",
            signal="BUY",
            closed_snapshot=_snapshot(
                _rates()
            ),
            observed_at="2026-09-19T15:01:00",
        )
        is True
    )

    state = candidate[
        "cisd_observer"
    ]
    assert state[
        "status"
    ] == "CONFIRMED"
    assert state[
        "confirmed"
    ] is True
    assert state[
        "qualification_satisfied"
    ] is True
    assert state[
        "shadow_entry_qualified"
    ] is False


def test_on_retest_cannot_arm_before_shadow_fill():
    candidate = _candidate(
        filled=False
    )

    assert (
        cisd_observer.update_candidate_cisd_state(
            candidate,
            policy="CISD_ON_RETEST",
            signal="BUY",
            closed_snapshot=_snapshot(
                _rates()
            ),
            observed_at="2026-09-19T15:00:00",
        )
        is True
    )

    state = candidate[
        "cisd_observer"
    ]
    assert state[
        "status"
    ] == "WAITING_FOR_RETEST"
    assert state[
        "armed"
    ] is False

    candidate[
        "filled"
    ] = True
    candidate[
        "status"
    ] = "FILLED_TRACKING"
    candidate[
        "fill_at"
    ] = "2026-09-19T15:02:00"

    first = {
        "available": True,
        "timeframe": "M1",
        "bars": _rates()[
            :2
        ],
        "latest_closed_bar_time": 160,
        "reason": None,
    }

    assert (
        cisd_observer.update_candidate_cisd_state(
            candidate,
            policy="CISD_ON_RETEST",
            signal="BUY",
            closed_snapshot=first,
            observed_at="2026-09-19T15:02:00",
        )
        is True
    )

    state = candidate[
        "cisd_observer"
    ]
    assert state[
        "status"
    ] == "WAITING_FOR_CISD_AFTER_RETEST"
    assert state[
        "armed_closed_bar_time"
    ] == 160

    assert (
        cisd_observer.update_candidate_cisd_state(
            candidate,
            policy="CISD_ON_RETEST",
            signal="BUY",
            closed_snapshot=_snapshot(
                _rates()
            ),
            observed_at="2026-09-19T15:03:00",
        )
        is True
    )

    state = candidate[
        "cisd_observer"
    ]
    assert state[
        "status"
    ] == "CONFIRMED"
    assert state[
        "shadow_entry_qualified"
    ] is True


def test_no_cisd_never_waits_for_confirmation():
    candidate = _candidate(
        filled=True
    )

    assert (
        cisd_observer.update_candidate_cisd_state(
            candidate,
            policy="NO_CISD",
            signal="BUY",
            closed_snapshot=None,
            observed_at="2026-09-19T15:00:00",
        )
        is True
    )

    state = candidate[
        "cisd_observer"
    ]
    assert state[
        "status"
    ] == "NOT_REQUIRED"
    assert state[
        "qualification_satisfied"
    ] is True
    assert state[
        "shadow_entry_qualified"
    ] is True


def test_tracker_cisd_telegram_notification_is_shadow_only():
    item = {
        "strategy": "ORB",
        "entry_model": "WAIT_RETEST",
        "signal": "BUY",
        "better_entry_counterfactual_eligible": True,
    }
    candidate = _candidate(
        filled=True
    )
    candidate[
        "cisd_observer"
    ] = {
        "status": "CONFIRMED",
        "policy": "CISD_ON_RETEST",
        "timeframe": "M1",
        "reference_open": 99.0,
        "confirmation_close": 100.5,
        "shadow_entry_qualified": True,
    }

    original_flag = (
        settings
        .ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER
    )
    original_sender = (
        notifier.send_telegram_message
    )
    messages = []

    try:
        notifier.send_telegram_message = messages.append

        assert (
            tracker
            ._maybe_notify_better_entry_cisd_shadow(
                item,
                candidate,
            )
            is False
        )

        settings.ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER = True

        assert (
            tracker
            ._maybe_notify_better_entry_cisd_shadow(
                item,
                candidate,
            )
            is True
        )
        assert len(
            messages
        ) == 1
        assert (
            "BETTER ENTRY CISD SHADOW"
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
            ._maybe_notify_better_entry_cisd_shadow(
                item,
                candidate,
            )
            is False
        )
        assert len(
            messages
        ) == 1

    finally:
        notifier.send_telegram_message = (
            original_sender
        )
        settings.ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER = (
            original_flag
        )


def test_safe_defaults_unchanged():
    assert settings.ENABLE_BETTER_ENTRY_OPTIMIZER is False
    assert (
        settings
        .ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER
        is False
    )
    assert settings.FIXED_LOT == 0.25


def main():
    test_buy_cisd_detection()
    test_sell_cisd_detection()
    test_required_arms_without_using_old_confirmation()
    test_on_retest_cannot_arm_before_shadow_fill()
    test_no_cisd_never_waits_for_confirmation()
    test_tracker_cisd_telegram_notification_is_shadow_only()
    test_safe_defaults_unchanged()

    print(
        "PASS: Better Entry V1.7 closed-candle CISD observer"
    )


if __name__ == "__main__":
    main()
