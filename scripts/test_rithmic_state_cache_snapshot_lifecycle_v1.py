import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.order_flow_features.rithmic_state_cache import (
    RithmicRollingStateCache,
)


def level(price, size):
    return {
        "level": 1,
        "price": price,
        "size": size,
        "orders": 1 if size > 0 else 0,
        "implicit_size": 0,
    }


def book_event(
    *,
    update_type,
    update_type_name,
    presence_bits,
    bids=None,
    asks=None,
):
    return {
        "event_type": "order_book",
        "update_type": update_type,
        "update_type_name": update_type_name,
        "presence_bits": presence_bits,
        "bid_levels": bids or [],
        "ask_levels": asks or [],
        "received_at_epoch": 1.0,
    }


cache = RithmicRollingStateCache(
    symbol="GCZ6",
    exchange="COMEX",
    tick_size=0.1,
)

# Initial complete book image.
cache.update(
    book_event(
        update_type=3,
        update_type_name="SNAPSHOT_IMAGE",
        presence_bits=3,
        bids=[
            level(4243.0, 5),
            level(4242.9, 4),
        ],
        asks=[
            level(4243.3, 5),
            level(4243.4, 4),
        ],
    )
)

assert cache.top_dom_bid_price == 4243.0
assert cache.top_dom_ask_price == 4243.3

# Model reconnect/resubscribe: a new complete image is substantially lower.
# Old 4243.0 must NOT survive this replacement.
cache.update(
    book_event(
        update_type=3,
        update_type_name="SNAPSHOT_IMAGE",
        presence_bits=3,
        bids=[
            level(4239.8, 7),
            level(4239.7, 3),
        ],
        asks=[
            level(4240.4, 6),
            level(4240.5, 2),
        ],
    )
)

assert cache.top_dom_bid_price == 4239.8
assert cache.top_dom_ask_price == 4240.4

bid_prices = {
    row["price"]
    for row in cache.order_book_bid_levels
}

assert 4243.0 not in bid_prices
assert max(bid_prices) < cache.top_dom_ask_price

# SOLO remains incremental: add/update one price without replacing the side.
cache.update(
    book_event(
        update_type=7,
        update_type_name="SOLO",
        presence_bits=1,
        bids=[level(4239.9, 8)],
    )
)

assert cache.top_dom_bid_price == 4239.9
assert any(
    row["price"] == 4239.8
    for row in cache.order_book_bid_levels
)

# Existing zero-size deletion semantics must remain intact.
cache.update(
    book_event(
        update_type=7,
        update_type_name="SOLO",
        presence_bits=1,
        bids=[level(4239.9, 0)],
    )
)

assert cache.top_dom_bid_price == 4239.8
assert all(
    row["price"] != 4239.9
    for row in cache.order_book_bid_levels
)

# CLEAR_ORDER_BOOK remains a hard reset.
cache.update(
    book_event(
        update_type=1,
        update_type_name="CLEAR_ORDER_BOOK",
        presence_bits=0,
    )
)

assert cache.order_book_bid_levels == []
assert cache.order_book_ask_levels == []
assert cache.top_dom_bid_price is None
assert cache.top_dom_ask_price is None

print(
    "[PASS] SNAPSHOT_IMAGE replaces retained DOM; "
    "SOLO merge/delete semantics preserved"
)
