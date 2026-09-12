from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import src.order_flow_features.rithmic_state_cache as cache_module
from src.order_flow_features.rithmic_state_cache import (
    RithmicRollingStateCache,
)


def order_book_event(
    *,
    bid_levels=None,
    ask_levels=None,
    presence_bits=0,
    update_type_name="UPDATE",
    received_at_epoch=1_700_000_000.0,
):
    return {
        "event_type": "order_book",
        "symbol": "GCZ6",
        "exchange": "COMEX",
        "received_at_epoch": received_at_epoch,
        "presence_bits": presence_bits,
        "update_type": 1,
        "update_type_name": update_type_name,
        "bid_levels": bid_levels or [],
        "ask_levels": ask_levels or [],
    }


def level(price, size=10):
    return {
        "level": 1,
        "price": price,
        "size": size,
        "orders": 1 if size > 0 else 0,
        "implicit_size": 0,
    }


def test_dom_is_hard_bounded():
    cache = RithmicRollingStateCache(
        symbol="GCZ6",
        exchange="COMEX",
        tick_size=0.1,
        rolling_window_seconds=30,
        bucket_seconds=5,
        stale_after_seconds=5,
        top_levels=20,
        max_order_book_levels=64,
    )

    base = 1_700_000_000.0

    for i in range(5000):
        cache.update(
            order_book_event(
                bid_levels=[
                    level(
                        3000.0 - (i * 0.1)
                    )
                ],
                presence_bits=1,
                received_at_epoch=base,
            )
        )

    for i in range(5000):
        cache.update(
            order_book_event(
                ask_levels=[
                    level(
                        3000.1 + (i * 0.1)
                    )
                ],
                presence_bits=2,
                received_at_epoch=base,
            )
        )

    assert len(cache.order_book_bid_levels) == 64
    assert len(cache.order_book_ask_levels) == 64

    # Best prices must be retained after truncation.
    assert (
        cache.order_book_bid_levels[0]["price"]
        == 3000.0
    )
    assert (
        cache.order_book_ask_levels[0]["price"]
        == 3000.1
    )

    snapshot = cache.snapshot(
        now_epoch=base,
    )

    assert (
        len(snapshot["order_book"]["bid_levels"])
        == 20
    )
    assert (
        len(snapshot["order_book"]["ask_levels"])
        == 20
    )

    assert (
        snapshot["order_book"][
            "max_retained_levels_per_side"
        ]
        == 64
    )

    assert (
        snapshot["order_book"][
            "retained_level_limit_reached"
        ]
        is True
    )

    assert (
        snapshot["order_book"][
            "retained_level_truncation_count"
        ]
        > 0
    )

    assert (
        "ORDER_BOOK_RETAINED_LEVEL_LIMIT_REACHED"
        in snapshot["quality"]["warnings"]
    )

    assert (
        snapshot["decision_impact"]
        == "NONE"
    )
    assert (
        snapshot["can_influence_decision"]
        is False
    )
    assert (
        snapshot["quality"][
            "safe_for_execution"
        ]
        is False
    )


def test_dom_removal_and_clear_lifecycle():
    cache = RithmicRollingStateCache(
        symbol="GCZ6",
        exchange="COMEX",
        top_levels=3,
        max_order_book_levels=5,
    )

    base = 1_700_000_100.0

    for i in range(10):
        cache.update(
            order_book_event(
                bid_levels=[
                    level(
                        2000.0 - i
                    )
                ],
                presence_bits=1,
                received_at_epoch=base,
            )
        )

    assert len(cache.order_book_bid_levels) == 5
    assert (
        cache.order_book_truncation_count
        > 0
    )

    # Zero-size update removes a retained level.
    cache.update(
        order_book_event(
            bid_levels=[
                level(
                    2000.0,
                    size=0,
                )
            ],
            presence_bits=1,
            received_at_epoch=base,
        )
    )

    assert len(cache.order_book_bid_levels) == 4
    assert (
        cache.order_book_bid_levels[0]["price"]
        == 1999.0
    )

    # Explicit clear is a resynchronization boundary.
    cleared = cache.update(
        order_book_event(
            update_type_name="CLEAR_ORDER_BOOK",
            received_at_epoch=base,
        )
    )

    assert cache.order_book_bid_levels == []
    assert cache.order_book_ask_levels == []
    assert cache.order_book_truncation_count == 0

    assert (
        cleared["order_book"][
            "retained_level_limit_reached"
        ]
        is False
    )

    assert (
        "ORDER_BOOK_RETAINED_LEVEL_LIMIT_REACHED"
        not in cleared["quality"]["warnings"]
    )


def test_trade_window_is_time_bounded():
    cache = RithmicRollingStateCache(
        symbol="GCZ6",
        exchange="COMEX",
        rolling_window_seconds=30,
        bucket_seconds=5,
        stale_after_seconds=5,
        top_levels=20,
    )

    base = 1_700_001_000.0
    clock = [base]

    with patch.object(
        cache_module.time,
        "time",
        side_effect=lambda: clock[0],
    ):
        # Four trades per second over a long synthetic session.
        for i in range(5000):
            clock[0] = base + (i * 0.25)

            cache.update(
                {
                    "event_type": "last_trade",
                    "symbol": "GCZ6",
                    "exchange": "COMEX",
                    "received_at_epoch": clock[0],
                    "trade_price": 2500.0,
                    "trade_size": 1,
                    "aggressor": (
                        "BUY"
                        if i % 2 == 0
                        else "SELL"
                    ),
                }
            )

            # Cutoff uses "<", so exactly 30 seconds of
            # history plus the current sample can remain.
            assert len(cache.trades) <= 121

        cutoff = (
            clock[0]
            - cache.rolling_window_seconds
        )

        assert all(
            trade.received_at_epoch >= cutoff
            for trade in cache.trades
        )

        total_before = cache.last_trade_count

        # Recovery/control noise advances pruning without
        # adding fake market activity.
        clock[0] += 31.0

        snapshot = cache.update(
            {
                "event_type": "connection_recovery",
                "status": "RECONNECTED",
                "symbol": "GCZ6",
                "exchange": "COMEX",
            }
        )

        assert len(cache.trades) == 0
        assert cache.last_trade_count == total_before
        assert (
            snapshot["sample"][
                "rolling_trade_count"
            ]
            == 0
        )


def test_unknown_aggressor_is_delta_neutral():
    cache = RithmicRollingStateCache(
        symbol="GCZ6",
        exchange="COMEX",
        rolling_window_seconds=30,
    )

    base = 1_700_002_000.0
    clock = [base]

    events = (
        ("BUY", 5),
        ("SELL", 3),
        ("UNKNOWN", 7),
    )

    with patch.object(
        cache_module.time,
        "time",
        side_effect=lambda: clock[0],
    ):
        for index, (aggressor, size) in enumerate(
            events
        ):
            clock[0] = base + index

            cache.update(
                {
                    "event_type": "last_trade",
                    "symbol": "GCZ6",
                    "exchange": "COMEX",
                    "received_at_epoch": clock[0],
                    "trade_price": 2600.0 + index,
                    "trade_size": size,
                    "aggressor": aggressor,
                }
            )

        snapshot = cache.snapshot(
            now_epoch=clock[0],
        )

    flow = snapshot["trade_flow"]

    assert flow["rolling_buy_volume"] == 5
    assert flow["rolling_sell_volume"] == 3
    assert flow["rolling_total_volume"] == 15
    assert flow["rolling_delta"] == 2
    assert flow["session_cumulative_delta"] == 2

    assert (
        snapshot["latest_trade"]["aggressor"]
        == "UNKNOWN"
    )




def test_retention_signal_blocks_depth_quality_claims():
    phase5k = (
        ROOT
        / "scripts"
        / "validate_phase5k_rithmic_open_market_data.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    phase5l = (
        ROOT
        / "scripts"
        / "check_phase5l_rithmic_data_quality_gate.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        'retained_level_limit_reached = as_bool('
        in phase5k
    )

    assert (
        '"order_book_retention_intact": ('
        in phase5k
    )

    phase5k_dom_gate = (
        phase5k
        .split(
            "dom_quality_checks = [",
            1,
        )[1]
        .split(
            "]",
            1,
        )[0]
    )

    assert (
        '"order_book_retention_intact"'
        in phase5k_dom_gate
    )

    assert (
        "retained_level_limit_reached = bool("
        in phase5l
    )

    assert (
        '"order_book_retention_intact": ('
        in phase5l
    )

    phase5l_quality_tail = (
        phase5l.split(
            "quality_failures = []",
            1,
        )[1]
    )

    phase5l_quality_gate = (
        phase5l_quality_tail
        .split(
            "for key in [",
            1,
        )[1]
        .split(
            "]:",
            1,
        )[0]
    )

    assert (
        '"order_book_retention_intact"'
        in phase5l_quality_gate
    )

def main():
    test_dom_is_hard_bounded()
    test_dom_removal_and_clear_lifecycle()
    test_trade_window_is_time_bounded()
    test_unknown_aggressor_is_delta_neutral()
    test_retention_signal_blocks_depth_quality_claims()

    print(
        "[PASS] Rithmic lifecycle/cache boundedness: "
        "persistent DOM sides have an explicit retention "
        "ceiling with truncation telemetry; clear/no-book "
        "resynchronizes that state; rolling trades evict by "
        "time window; recovery noise creates no fake trades; "
        "unknown aggressors remain delta-neutral."
    )


if __name__ == "__main__":
    main()
