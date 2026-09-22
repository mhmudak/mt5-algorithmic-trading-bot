from __future__ import annotations

import tempfile
from pathlib import Path

from src.order_flow_features.rithmic_liquidity_pull_replenishment import (
    evaluate_rithmic_liquidity_pull_replenishment,
)


ROOT = Path(__file__).resolve().parents[1]


def integrity_ok():
    return {
        "integrity_ok": True,
        "continuity_valid": True,
    }


def levels(side: str, sizes: list[int], start: float):
    result = []

    for idx, size in enumerate(sizes):
        price = (
            start - (0.1 * idx)
            if side == "bid"
            else start + (0.1 * idx)
        )
        result.append(
            {
                "level": idx + 1,
                "price": price,
                "size": size,
                "orders": max(1, size // 10),
                "implicit_size": 0,
            }
        )

    return result


def snapshot(
    *,
    updated_at: float,
    bid_sizes: list[int],
    ask_sizes: list[int],
    bid_start: float = 2400.0,
    ask_start: float = 2400.1,
    book_count: int = 1,
    fresh_book: bool = True,
):
    return {
        "symbol": "GCZ6",
        "exchange": "COMEX",
        "updated_at_epoch": updated_at,
        "freshness": {
            "has_fresh_order_book": fresh_book,
        },
        "sample": {
            "order_book_count": book_count,
        },
        "order_book": {
            "available": True,
            "last_received_at_epoch": updated_at,
            "top_bid_price": bid_start,
            "top_ask_price": ask_start,
            "bid_levels": levels(
                "bid",
                bid_sizes,
                bid_start,
            ),
            "ask_levels": levels(
                "ask",
                ask_sizes,
                ask_start,
            ),
        },
    }


def run_pair(
    first,
    second,
    *,
    signal="BUY",
):
    tmp = tempfile.TemporaryDirectory()
    path = Path(tmp.name) / "history.json"

    evaluate_rithmic_liquidity_pull_replenishment(
        first,
        history_path=path,
        feed_integrity=integrity_ok(),
        signal=signal,
        session="NEW_YORK_OPEN",
        tick_size=0.1,
    )

    result = evaluate_rithmic_liquidity_pull_replenishment(
        second,
        history_path=path,
        feed_integrity=integrity_ok(),
        signal=signal,
        session="NEW_YORK_OPEN",
        tick_size=0.1,
    )

    return tmp, result


def test_bid_replenishment():
    tmp, result = run_pair(
        snapshot(
            updated_at=1.0,
            bid_sizes=[100, 80, 60, 50, 40],
            ask_sizes=[80, 70, 60, 50, 40],
            book_count=1,
        ),
        snapshot(
            updated_at=2.0,
            bid_sizes=[160, 120, 90, 50, 40],
            ask_sizes=[80, 70, 60, 50, 40],
            book_count=2,
        ),
        signal="BUY",
    )

    try:
        assert result["status"] == "BID_REPLENISHMENT"
        assert result["bid"]["replenishment"] is True
        assert (
            result["signal_context"][
                "liquidity_replenishment_supports_signal"
            ]
            is True
        )
    finally:
        tmp.cleanup()


def test_bid_pull_risk_against_buy():
    tmp, result = run_pair(
        snapshot(
            updated_at=1.0,
            bid_sizes=[120, 100, 80, 60, 40],
            ask_sizes=[80, 70, 60, 50, 40],
            book_count=1,
        ),
        snapshot(
            updated_at=2.0,
            bid_sizes=[20, 10, 10, 10, 10],
            ask_sizes=[80, 70, 60, 50, 40],
            book_count=2,
        ),
        signal="BUY",
    )

    try:
        assert result["status"] == "BID_LIQUIDITY_PULL_RISK"
        assert result["bid"]["pull_risk"] is True
        assert (
            result["signal_context"][
                "liquidity_pull_against_signal"
            ]
            is True
        )
    finally:
        tmp.cleanup()


def test_large_touch_shift_suppresses_pull_label():
    tmp, result = run_pair(
        snapshot(
            updated_at=1.0,
            bid_sizes=[100, 80, 60, 50, 40],
            ask_sizes=[80, 70, 60, 50, 40],
            bid_start=2400.0,
            ask_start=2400.1,
            book_count=1,
        ),
        snapshot(
            updated_at=2.0,
            bid_sizes=[10, 10, 10, 10, 10],
            ask_sizes=[10, 10, 10, 10, 10],
            bid_start=2400.5,
            ask_start=2400.6,
            book_count=2,
        ),
        signal="BUY",
    )

    try:
        assert result["bid"]["touch_stable_for_comparison"] is False
        assert result["bid"]["pull_risk"] is False
        assert result["ask"]["pull_risk"] is False
    finally:
        tmp.cleanup()


def test_feed_integrity_blocks():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "history.json"

        result = evaluate_rithmic_liquidity_pull_replenishment(
            snapshot(
                updated_at=1.0,
                bid_sizes=[100, 80, 60],
                ask_sizes=[80, 70, 60],
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
            bid_sizes=[100, 80, 60],
            ask_sizes=[80, 70, 60],
        )

        first = evaluate_rithmic_liquidity_pull_replenishment(
            item,
            history_path=path,
            feed_integrity=integrity_ok(),
        )
        second = evaluate_rithmic_liquidity_pull_replenishment(
            item,
            history_path=path,
            feed_integrity=integrity_ok(),
        )

        assert first["history"]["snapshot_count"] == 1
        assert second["history"]["snapshot_count"] == 1
        assert (
            second["history"]["current_snapshot_was_duplicate"]
            is True
        )


def test_policy_never_claims_exact_cancels():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_liquidity_pull_replenishment(
            snapshot(
                updated_at=1.0,
                bid_sizes=[100, 80, 60],
                ask_sizes=[80, 70, 60],
            ),
            history_path=Path(tmp) / "history.json",
            feed_integrity=integrity_ok(),
        )

        assert result["policy"]["exact_cancel_add_available"] is False
        assert result["policy"]["exact_mbo_lifecycle_available"] is False
        assert result["policy"]["can_confirm_setup_alone"] is False


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
        'bridge["liquidity_pull_replenishment"]',
        "evaluate_rithmic_liquidity_pull_replenishment",
        "format_liquidity_pull_replenishment_text",
        "phase5g_rithmic_liquidity_pull_replenishment_history.json",
        "liquidity_pull_replenishment_history.unlink()",
    )

    for marker in required:
        assert marker in source, marker

    assert "execute_trade(" not in source
    assert "order_send(" not in source


def main():
    test_bid_replenishment()
    test_bid_pull_risk_against_buy()
    test_large_touch_shift_suppresses_pull_label()
    test_feed_integrity_blocks()
    test_duplicate_does_not_expand_history()
    test_policy_never_claims_exact_cancels()
    test_phase5g_wiring_is_observe_only()

    print("PASS: same-price bid replenishment is detected")
    print("PASS: large bid depth removal can flag pull risk against BUY")
    print("PASS: large touch movement suppresses false pull classification")
    print("PASS: bad feed integrity blocks liquidity classification")
    print("PASS: duplicate snapshots do not inflate liquidity history")
    print("PASS: aggregate DOM changes are never labeled exact cancels")
    print("PASS: Phase 5G liquidity wiring has no execution authority")


if __name__ == "__main__":
    main()
