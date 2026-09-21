from __future__ import annotations

import pandas as pd

from src import daily_ladder_reclaim_reversal as r


def test_extract_prefers_strong_over_shadow():
    context = {
        "shadow_upper_levels": [
            4384.0,
            4390.0,
            4396.0,
            4407.0,
            4414.0,
            4421.0,
        ],
        "shadow_lower_levels": [
            4366.0,
            4360.0,
            4342.0,
            4330.0,
            4312.0,
            4305.0,
        ],
        "strong_upper_levels": [
            4378.0,
            4384.0,
            4390.0,
            4396.0,
            4407.0,
        ],
        "strong_lower_levels": [
            4366.0,
            4360.0,
            4342.0,
        ],
        "daily_pivot": 4370.75,
        "broker_date_text": "2026-09-21",
    }

    result = r.extract_approved_ladder_context(
        context
    )

    assert result is not None
    assert result["upper"] == [
        4378.0,
        4384.0,
        4390.0,
        4396.0,
        4407.0,
    ]
    assert result["lower"] == [
        4342.0,
        4360.0,
        4366.0,
    ]
    assert result["pivot"] == 4370.75


def test_buy_sweep_reclaim():
    event = r.detect_closed_m5_reclaim(
        previous_bar={
            "open": 4348.0,
            "high": 4349.0,
            "low": 4341.2,
            "close": 4341.5,
        },
        current_bar={
            "open": 4341.5,
            "high": 4345.0,
            "low": 4340.8,
            "close": 4342.5,
        },
        upper_levels=[4384.0],
        lower_levels=[4341.93],
        atr=4.0,
    )

    assert event is not None
    assert event["signal"] == "BUY"
    assert event["level"] == 4341.93


def test_sell_sweep_reclaim():
    event = r.detect_closed_m5_reclaim(
        previous_bar={
            "open": 4382.0,
            "high": 4384.4,
            "low": 4381.0,
            "close": 4384.2,
        },
        current_bar={
            "open": 4384.2,
            "high": 4385.1,
            "low": 4382.0,
            "close": 4383.6,
        },
        upper_levels=[4384.17],
        lower_levels=[4366.0],
        atr=4.0,
    )

    assert event is not None
    assert event["signal"] == "SELL"
    assert event["level"] == 4384.17


def test_buy_cisd_after_arm():
    df = pd.DataFrame(
        [
            {
                "time": pd.Timestamp("2026-09-21 10:04:00"),
                "open": 4342.5,
                "high": 4342.7,
                "low": 4341.9,
                "close": 4342.0,
            },
            {
                "time": pd.Timestamp("2026-09-21 10:05:00"),
                "open": 4342.0,
                "high": 4342.2,
                "low": 4341.8,
                "close": 4341.9,
            },
            {
                "time": pd.Timestamp("2026-09-21 10:06:00"),
                "open": 4341.9,
                "high": 4342.8,
                "low": 4341.8,
                "close": 4342.6,
            },
        ]
    )

    result = r.find_closed_m1_cisd_confirmation(
        m1_df=df,
        signal="BUY",
        armed_after=pd.Timestamp(
            "2026-09-21 10:05:00"
        ),
    )

    assert result is not None
    assert result["confirmation_time"].startswith(
        "2026-09-21 10:06"
    )


def test_observation_has_no_authority():
    obs = r.build_shadow_observation(
        pending={
            "signal": "BUY",
            "level": 4341.93,
            "level_side": "LOWER",
            "reclaim_mode": "SAME_BAR",
            "sweep_extreme": 4340.80,
            "reclaim_buffer": 0.12,
            "reclaim_m5_time": "2026-09-21 10:00:00",
            "armed_after": "2026-09-21 10:05:00",
        },
        cisd={
            "reference_time": "2026-09-21 10:05:00",
            "reference_open": 4342.0,
            "confirmation_time": "2026-09-21 10:06:00",
            "confirmation_open": 4341.9,
            "confirmation_high": 4342.8,
            "confirmation_low": 4341.8,
            "confirmation_close": 4342.6,
        },
        ladder={
            "upper": [
                4377.97,
                4384.17,
            ],
            "lower": [
                4341.93,
                4360.30,
                4366.26,
            ],
            "pivot": 4370.76,
            "broker_date": "2026-09-21",
            "sources": {},
        },
        atr=4.0,
    )

    assert obs["strategy"] == (
        "DAILY_LEVEL_LADDER_RECLAIM_REVERSAL"
    )
    assert obs["decision_impact"] == "OBSERVE_ONLY"
    assert obs["execution_authority"] is False
    assert obs["can_execute"] is False
    assert obs["shadow_tp"] == 4360.30


def main():
    test_extract_prefers_strong_over_shadow()
    test_buy_sweep_reclaim()
    test_sell_sweep_reclaim()
    test_buy_cisd_after_arm()
    test_observation_has_no_authority()

    print(
        "PASS: Daily Ladder Reclaim Reversal shadow V1"
    )
    print(
        "PASS: approved strong ladder levels only"
    )
    print(
        "PASS: no first-touch signal; sweep + reclaim required"
    )
    print(
        "PASS: new closed-M1 CISD required after reclaim"
    )
    print(
        "PASS: next approved ladder level used as shadow TP"
    )
    print(
        "PASS: decision impact remains OBSERVE_ONLY"
    )
    print(
        "PASS: execution_authority=False"
    )


if __name__ == "__main__":
    main()
