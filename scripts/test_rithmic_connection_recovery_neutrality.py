from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import src.order_flow_features.rithmic_state_cache as state_module

from src.order_flow_features.rithmic_state_cache import (
    RithmicRollingStateCache,
)

from src.order_flow_features.rithmic_summary import (
    build_rithmic_orderflow_summary,
)


RECORDER = (
    ROOT
    / "scripts"
    / "rithmic_record_market_data.py"
)


def make_cache():
    return RithmicRollingStateCache(
        symbol="GC_TEST",
        exchange="COMEX",
        tick_size=0.1,
        rolling_window_seconds=300,
        bucket_seconds=60,
        stale_after_seconds=15,
        top_levels=20,
    )


def recovery_event():
    return {
        "event_type": "connection_recovery",
        "status": "DISCONNECTED",
        "attempt": 0,
        "max_attempts": 3,
        "symbol": "GC_TEST",
        "exchange": "COMEX",

        # Deliberately misleading market-looking fields.
        # They must never be treated as market data.
        "trade_price": 9999.0,
        "trade_size": 999,
        "aggressor": "SELL",
        "bid_price": 9998.0,
        "ask_price": 10000.0,
        "bid_depth": 999,
        "ask_depth": 1,

        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
    }


def test_cache_recovery_event_is_market_neutral():
    cache = make_cache()

    original_time = state_module.time.time

    try:
        state_module.time.time = lambda: 1000.0

        cache.update(
            {
                "event_type": "login_response",
                "ok": True,
            }
        )

        cache.update(
            {
                "event_type": "market_data_response",
                "rp_code": ["0"],
            }
        )

        cache.update(
            {
                "event_type": "last_trade",
                "received_at_epoch": 1000.0,
                "symbol": "GC_TEST",
                "exchange": "COMEX",
                "trade_price": 4425.0,
                "trade_size": 10,
                "aggressor": "BUY",
            }
        )

        cache.update(
            {
                "event_type": "best_bid_offer",
                "received_at_epoch": 1000.0,
                "symbol": "GC_TEST",
                "exchange": "COMEX",
                "bid_price": 4424.9,
                "ask_price": 4425.1,
                "bid_size": 20,
                "ask_size": 18,
            }
        )

        # Set sentinel DOM state. A recovery event must not
        # mutate any market-depth state either.
        cache.order_book_count = 7
        cache.order_book_available = True
        cache.last_order_book_received_at_epoch = 1000.0
        cache.dom_bid_depth = 125
        cache.dom_ask_depth = 100
        cache.dom_depth_imbalance = 0.111111

        before = {
            "last_trade_count": cache.last_trade_count,
            "buy_volume": cache.total_buy_volume,
            "sell_volume": cache.total_sell_volume,
            "delta": cache.total_cumulative_delta,
            "trade_ts": cache.last_trade_received_at_epoch,
            "bbo_count": cache.bbo_count,
            "bid": cache.last_bid,
            "ask": cache.last_ask,
            "bbo_ts": cache.last_bbo_received_at_epoch,
            "order_book_count": cache.order_book_count,
            "order_book_available": cache.order_book_available,
            "order_book_ts": (
                cache.last_order_book_received_at_epoch
            ),
            "dom_bid_depth": cache.dom_bid_depth,
            "dom_ask_depth": cache.dom_ask_depth,
            "dom_imbalance": cache.dom_depth_imbalance,
        }

        state_module.time.time = lambda: 1001.0

        snapshot = cache.update(
            recovery_event()
        )

        after = {
            "last_trade_count": cache.last_trade_count,
            "buy_volume": cache.total_buy_volume,
            "sell_volume": cache.total_sell_volume,
            "delta": cache.total_cumulative_delta,
            "trade_ts": cache.last_trade_received_at_epoch,
            "bbo_count": cache.bbo_count,
            "bid": cache.last_bid,
            "ask": cache.last_ask,
            "bbo_ts": cache.last_bbo_received_at_epoch,
            "order_book_count": cache.order_book_count,
            "order_book_available": cache.order_book_available,
            "order_book_ts": (
                cache.last_order_book_received_at_epoch
            ),
            "dom_bid_depth": cache.dom_bid_depth,
            "dom_ask_depth": cache.dom_ask_depth,
            "dom_imbalance": cache.dom_depth_imbalance,
        }

        assert after == before

        # Overall observer activity may advance.
        assert cache.updated_at_epoch == 1001.0

        # But actual market timestamps remain at the real
        # market observation time.
        assert (
            cache.last_trade_received_at_epoch
            == 1000.0
        )

        assert (
            cache.last_bbo_received_at_epoch
            == 1000.0
        )

        assert (
            cache.last_order_book_received_at_epoch
            == 1000.0
        )

        assert (
            snapshot["decision_impact"]
            == "NONE"
        )

    finally:
        state_module.time.time = original_time


def test_recovery_event_cannot_fake_market_freshness():
    cache = make_cache()

    original_time = state_module.time.time

    try:
        state_module.time.time = lambda: 1000.0

        cache.update(
            {
                "event_type": "login_response",
                "ok": True,
            }
        )

        cache.update(
            {
                "event_type": "market_data_response",
                "rp_code": ["0"],
            }
        )

        cache.update(
            {
                "event_type": "last_trade",
                "received_at_epoch": 1000.0,
                "symbol": "GC_TEST",
                "exchange": "COMEX",
                "trade_price": 4425.0,
                "trade_size": 10,
                "aggressor": "BUY",
            }
        )

        cache.update(
            {
                "event_type": "best_bid_offer",
                "received_at_epoch": 1000.0,
                "symbol": "GC_TEST",
                "exchange": "COMEX",
                "bid_price": 4424.9,
                "ask_price": 4425.1,
                "bid_size": 20,
                "ask_size": 18,
            }
        )

        cache.order_book_count = 1
        cache.order_book_available = True
        cache.last_order_book_received_at_epoch = 1000.0

        # Recovery activity occurs later.
        state_module.time.time = lambda: 1019.0
        cache.update(recovery_event())

        snapshot = cache.snapshot(
            now_epoch=1020.0
        )

        freshness = snapshot["freshness"]

        assert (
            freshness["last_trade_age_seconds"]
            == 20.0
        )

        assert (
            freshness["last_bbo_age_seconds"]
            == 20.0
        )

        assert (
            freshness[
                "last_order_book_age_seconds"
            ]
            == 20.0
        )

        assert (
            freshness["has_fresh_trade"]
            is False
        )

        assert (
            freshness["has_fresh_bbo"]
            is False
        )

        assert (
            freshness["has_fresh_order_book"]
            is False
        )

    finally:
        state_module.time.time = original_time


def _collect_market_metrics(value, path=""):
    interesting = {
        "buy_volume",
        "sell_volume",
        "total_volume",
        "trade_count",
        "cumulative_delta",
    }

    found = []

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (
                f"{path}.{key}"
                if path
                else str(key)
            )

            if key in interesting:
                found.append(
                    (
                        child_path,
                        child,
                    )
                )

            found.extend(
                _collect_market_metrics(
                    child,
                    child_path,
                )
            )

    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(
                _collect_market_metrics(
                    child,
                    f"{path}[{index}]",
                )
            )

    return found


def test_summary_ignores_recovery_for_market_metrics():
    base_events = [
        {
            "event_type": "login_response",
            "ok": True,
        },
        {
            "event_type": "market_data_response",
            "rp_code": ["0"],
        },
        {
            "event_type": "last_trade",
            "received_at_epoch": 1000.0,
            "symbol": "GC_TEST",
            "exchange": "COMEX",
            "trade_price": 4425.0,
            "trade_size": 7,
            "aggressor": "BUY",
        },
        {
            "event_type": "last_trade",
            "received_at_epoch": 1001.0,
            "symbol": "GC_TEST",
            "exchange": "COMEX",
            "trade_price": 4424.9,
            "trade_size": 3,
            "aggressor": "SELL",
        },
        {
            "event_type": "best_bid_offer",
            "received_at_epoch": 1001.0,
            "symbol": "GC_TEST",
            "exchange": "COMEX",
            "bid_price": 4424.8,
            "ask_price": 4425.0,
            "bid_size": 12,
            "ask_size": 11,
        },
    ]

    without_recovery = (
        build_rithmic_orderflow_summary(
            base_events,
            symbol="GC_TEST",
            exchange="COMEX",
        )
    )

    with_recovery = (
        build_rithmic_orderflow_summary(
            base_events + [recovery_event()],
            symbol="GC_TEST",
            exchange="COMEX",
        )
    )

    assert (
        _collect_market_metrics(
            without_recovery
        )
        ==
        _collect_market_metrics(
            with_recovery
        )
    )


def test_recorder_persists_before_event_routing():
    source = RECORDER.read_text(
        encoding="utf-8-sig"
    )

    write_marker = (
        'f.write(json.dumps(event, '
        'ensure_ascii=False) + "\\n")'
    )

    route_marker = (
        'event_type = event.get("event_type")'
    )

    assert write_marker in source
    assert route_marker in source

    # All stream events, including connection_recovery,
    # are persisted before type-specific accounting.
    assert (
        source.index(write_marker)
        <
        source.index(route_marker)
    )


def main():
    test_cache_recovery_event_is_market_neutral()
    test_recovery_event_cannot_fake_market_freshness()
    test_summary_ignores_recovery_for_market_metrics()
    test_recorder_persists_before_event_routing()

    print(
        "[PASS] Rithmic connection-recovery events are "
        "raw-persisted and market-neutral: no fake trade "
        "volume, delta, BBO, DOM, or market freshness."
    )


if __name__ == "__main__":
    main()
