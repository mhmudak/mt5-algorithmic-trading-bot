from __future__ import annotations

from datetime import datetime, timedelta

from src import setup_outcome_tracker as tracker
from src.better_entry_optimizer import (
    build_better_entry_observer,
)


def _base_item(
    signal="BUY",
):
    created = (
        datetime.now()
        - timedelta(
            minutes=10
        )
    ).isoformat()

    return {
        "setup_id": "TEST",
        "status": "TRACKING",
        "created_at": created,
        "entry": 100.0,
        "signal": signal,
        "hit_plus_10": False,
        "pre_w10_path_observed": False,
        "pre_w10_path_frozen": False,
        "pre_w10_max_adverse_usd": 0.0,
        "pre_w10_max_adverse_price": None,
        "pre_w10_max_adverse_at": None,
        "time_to_pre_w10_max_adverse_seconds": None,
        "w10_hit_at": None,
        "time_to_w10_seconds": None,
    }


def test_buy_pre_w10_mae_updates_and_freezes():
    item = _base_item(
        "BUY"
    )

    assert tracker._update_pre_w10_path_metrics(
        item,
        96.0,
    ) is True

    assert item[
        "pre_w10_max_adverse_usd"
    ] == 4.0
    assert item[
        "pre_w10_max_adverse_price"
    ] == 96.0
    assert item[
        "pre_w10_path_observed"
    ] is True
    assert (
        item[
            "time_to_pre_w10_max_adverse_seconds"
        ]
        is not None
    )

    assert tracker._freeze_pre_w10_path_metrics(
        item
    ) is True

    item[
        "hit_plus_10"
    ] = True

    frozen_value = item[
        "pre_w10_max_adverse_usd"
    ]

    assert tracker._update_pre_w10_path_metrics(
        item,
        90.0,
    ) is False

    assert item[
        "pre_w10_max_adverse_usd"
    ] == frozen_value


def test_sell_pre_w10_mae_is_symmetric():
    item = _base_item(
        "SELL"
    )

    assert tracker._update_pre_w10_path_metrics(
        item,
        106.5,
    ) is True

    assert item[
        "pre_w10_max_adverse_usd"
    ] == 6.5
    assert item[
        "pre_w10_max_adverse_price"
    ] == 106.5


def test_detection_context_preserves_proxy_fields():
    item = {
        "session": "LONDON",
        "market_condition": "TRENDING",
        "momentum": "bullish_displacement",
        "extra": {
            "direction_context": "price_above_ema",
            "atr_14": 7.5,
            "market_participation_state": "STRONG_ALIGNED",
            "participation_score": 0.82,
            "tick_volume_ratio": 1.35,
        },
    }

    context = (
        tracker
        ._build_better_entry_detection_context(
            item
        )
    )

    assert context[
        "session"
    ] == "LONDON"
    assert context[
        "market_condition"
    ] == "TRENDING"
    assert context[
        "momentum"
    ] == "bullish_displacement"
    assert context[
        "direction_context"
    ] == "price_above_ema"
    assert context[
        "atr_14"
    ] == 7.5

    signals = context[
        "signals"
    ]

    assert signals[
        "market_participation_state"
    ] == "STRONG_ALIGNED"
    assert signals[
        "participation_score"
    ] == 0.82
    assert signals[
        "tick_volume_ratio"
    ] == 1.35


def test_optimizer_summarizes_pre_w10_time_and_atr_normalization():
    setup = {
        "setup_id": "CURRENT",
        "strategy": "ORB",
        "entry_model": "UNKNOWN_ENTRY_MODEL",
        "signal": "BUY",
        "entry": 100.0,
    }

    rows = []

    for index in range(20):
        rows.append(
            {
                "setup_id": f"H-{index}",
                "status": "CLOSED",
                "strategy": "ORB",
                "entry_model": "UNKNOWN_ENTRY_MODEL",
                "signal": "BUY",
                "path_observed": True,
                "hit_plus_10": True,
                "hit_tp": True,
                "hit_sl": False,
                "first_hit": "W10",
                "max_favorable_usd": 12.0,
                "max_adverse_usd": 8.0,
                "max_recovery_swing_usd": 20.0,
                "pre_w10_max_adverse_usd": 4.0,
                "time_to_pre_w10_max_adverse_seconds": 180.0,
                "better_entry_detection_context": {
                    "atr_14": 8.0,
                },
            }
        )

    snapshot = build_better_entry_observer(
        setup,
        historical_rows=rows,
        enabled_override=True,
    )

    calibration = snapshot[
        "historical_calibration"
    ]

    assert calibration[
        "pre_w10_mae"
    ][
        "median"
    ] == 4.0
    assert calibration[
        "pre_w10_time_to_max_adverse_seconds"
    ][
        "median"
    ] == 180.0
    assert calibration[
        "pre_w10_mae_atr_ratio"
    ][
        "median"
    ] == 0.5


def main():
    test_buy_pre_w10_mae_updates_and_freezes()
    test_sell_pre_w10_mae_is_symmetric()
    test_detection_context_preserves_proxy_fields()
    test_optimizer_summarizes_pre_w10_time_and_atr_normalization()

    print(
        "PASS: Better Entry Optimizer V1.1 path instrumentation"
    )


if __name__ == "__main__":
    main()
