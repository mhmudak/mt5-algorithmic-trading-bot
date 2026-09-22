from __future__ import annotations

import tempfile
from pathlib import Path

from src.order_flow_features.rithmic_delta_price_divergence import (
    evaluate_rithmic_delta_price_divergence,
)


ROOT = Path(__file__).resolve().parents[1]


def integrity_ok():
    return {
        "integrity_ok": True,
        "continuity_valid": True,
    }


def snapshot(
    *,
    updated_at: float,
    cumulative_delta: float,
    price: float,
    trade_count: int = 30,
    fresh_trade: bool = True,
):
    return {
        "symbol": "GCZ6",
        "exchange": "COMEX",
        "updated_at_epoch": updated_at,
        "freshness": {
            "has_fresh_trade": fresh_trade,
        },
        "sample": {
            "last_trade_count_total_session": trade_count,
            "rolling_trade_count": trade_count,
        },
        "latest_trade": {
            "price": price,
            "received_at_epoch": updated_at,
        },
        "adapter_compatible_metrics": {
            "cumulative_delta": cumulative_delta,
        },
    }


def run_pair(first, second, *, signal="BUY"):
    tmp = tempfile.TemporaryDirectory()
    path = Path(tmp.name) / "history.json"

    evaluate_rithmic_delta_price_divergence(
        first,
        history_path=path,
        feed_integrity=integrity_ok(),
        signal=signal,
        session="NEW_YORK_OPEN",
        tick_size=0.1,
    )

    result = evaluate_rithmic_delta_price_divergence(
        second,
        history_path=path,
        feed_integrity=integrity_ok(),
        signal=signal,
        session="NEW_YORK_OPEN",
        tick_size=0.1,
    )

    return tmp, result


def test_potential_trapped_buyers():
    tmp, result = run_pair(
        snapshot(
            updated_at=1.0,
            cumulative_delta=100,
            price=2400.0,
        ),
        snapshot(
            updated_at=2.0,
            cumulative_delta=140,
            price=2400.0,
            trade_count=60,
        ),
        signal="BUY",
    )

    try:
        assert result["status"] == "POTENTIAL_TRAPPED_BUYERS"
        assert (
            result["classification"][
                "potential_trapped_buyers"
            ]
            is True
        )
        assert (
            result["classification"][
                "trapped_against_signal"
            ]
            is True
        )
    finally:
        tmp.cleanup()


def test_potential_trapped_sellers():
    tmp, result = run_pair(
        snapshot(
            updated_at=1.0,
            cumulative_delta=-100,
            price=2400.0,
        ),
        snapshot(
            updated_at=2.0,
            cumulative_delta=-140,
            price=2400.1,
            trade_count=60,
        ),
        signal="BUY",
    )

    try:
        assert result["status"] == "POTENTIAL_TRAPPED_SELLERS"
        assert (
            result["classification"][
                "potential_trapped_sellers"
            ]
            is True
        )
        assert (
            result["classification"][
                "trapped_supports_signal"
            ]
            is True
        )
    finally:
        tmp.cleanup()


def test_buy_flow_price_confirmed():
    tmp, result = run_pair(
        snapshot(
            updated_at=1.0,
            cumulative_delta=100,
            price=2400.0,
        ),
        snapshot(
            updated_at=2.0,
            cumulative_delta=135,
            price=2400.4,
            trade_count=60,
        ),
        signal="BUY",
    )

    try:
        assert result["status"] == "BUY_FLOW_PRICE_CONFIRMED"
        assert (
            result["classification"][
                "flow_confirms_signal"
            ]
            is True
        )
    finally:
        tmp.cleanup()


def test_sell_flow_price_confirmed():
    tmp, result = run_pair(
        snapshot(
            updated_at=1.0,
            cumulative_delta=-100,
            price=2400.0,
        ),
        snapshot(
            updated_at=2.0,
            cumulative_delta=-135,
            price=2399.6,
            trade_count=60,
        ),
        signal="SELL",
    )

    try:
        assert result["status"] == "SELL_FLOW_PRICE_CONFIRMED"
        assert (
            result["classification"][
                "flow_confirms_signal"
            ]
            is True
        )
    finally:
        tmp.cleanup()


def test_feed_integrity_blocks():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "history.json"

        result = evaluate_rithmic_delta_price_divergence(
            snapshot(
                updated_at=1.0,
                cumulative_delta=100,
                price=2400.0,
            ),
            history_path=path,
            feed_integrity={
                "integrity_ok": False,
                "continuity_valid": False,
            },
            signal="BUY",
            session="NEW_YORK_OPEN",
        )

        assert result["status"] == "FEED_INTEGRITY_NOT_USABLE"
        assert result["safe_for_execution"] is False


def test_duplicate_does_not_expand_history():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "history.json"

        item = snapshot(
            updated_at=1.0,
            cumulative_delta=100,
            price=2400.0,
        )

        first = evaluate_rithmic_delta_price_divergence(
            item,
            history_path=path,
            feed_integrity=integrity_ok(),
        )
        second = evaluate_rithmic_delta_price_divergence(
            item,
            history_path=path,
            feed_integrity=integrity_ok(),
        )

        assert first["history"]["snapshot_count"] == 1
        assert second["history"]["snapshot_count"] == 1
        assert (
            second["history"][
                "current_snapshot_was_duplicate"
            ]
            is True
        )


def test_policy_uses_potential_trapped_language():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_delta_price_divergence(
            snapshot(
                updated_at=1.0,
                cumulative_delta=100,
                price=2400.0,
            ),
            history_path=Path(tmp) / "history.json",
            feed_integrity=integrity_ok(),
        )

        assert (
            result["policy"][
                "trapped_label_is_potential_not_certain"
            ]
            is True
        )
        assert (
            result["policy"][
                "uses_cumulative_delta_change_not_absolute_level"
            ]
            is True
        )


def test_phase5g_wiring_is_observe_only():
    source = (
        ROOT
        / "scripts"
        / "build_phase5g_rithmic_monitoring_bridge.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    required = (
        'bridge["delta_price_divergence"]',
        "evaluate_rithmic_delta_price_divergence",
        "format_delta_price_divergence_text",
        "phase5g_rithmic_delta_price_divergence_history.json",
        "delta_price_divergence_history.unlink()",
    )

    for marker in required:
        assert marker in source, marker

    assert "execute_trade(" not in source
    assert "order_send(" not in source


def main():
    test_potential_trapped_buyers()
    test_potential_trapped_sellers()
    test_buy_flow_price_confirmed()
    test_sell_flow_price_confirmed()
    test_feed_integrity_blocks()
    test_duplicate_does_not_expand_history()
    test_policy_uses_potential_trapped_language()
    test_phase5g_wiring_is_observe_only()

    print("PASS: rising delta with stalled price flags potential trapped buyers")
    print("PASS: falling delta with stalled/reversing price flags potential trapped sellers")
    print("PASS: aligned buy delta + price progress confirms effective buy flow")
    print("PASS: aligned sell delta + price progress confirms effective sell flow")
    print("PASS: bad feed integrity blocks divergence classification")
    print("PASS: duplicate snapshots do not inflate divergence history")
    print("PASS: trapped-aggressor labels remain probabilistic, not certain")
    print("PASS: Phase 5G delta/price wiring has no execution authority")


if __name__ == "__main__":
    main()
