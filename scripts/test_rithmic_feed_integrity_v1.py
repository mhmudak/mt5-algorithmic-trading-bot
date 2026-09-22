from __future__ import annotations

import tempfile
from pathlib import Path

from src.order_flow_features.rithmic_feed_integrity import (
    evaluate_rithmic_feed_integrity,
)


ROOT = Path(__file__).resolve().parents[1]


def snapshot(
    *,
    updated_at=1.0,
    trade_count=10,
    bbo_count=20,
    book_count=30,
    login_ok=True,
    market_data_ok=True,
    fresh_trade=True,
    fresh_bbo=True,
    fresh_book=True,
    bid=2400.0,
    ask=2400.1,
    bid_depth=500,
    ask_depth=450,
    bid_levels=10,
    ask_levels=10,
    book_available=True,
    test_environment=False,
):
    return {
        "symbol": "GCZ6",
        "exchange": "COMEX",
        "system_name": (
            "Rithmic Test"
            if test_environment
            else "Rithmic Paper Trading"
        ),
        "is_test_environment": test_environment,
        "updated_at_epoch": updated_at,
        "connection": {
            "login_ok": login_ok,
            "market_data_ok": market_data_ok,
            "login_event_count": 1,
            "market_data_response_count": 1,
        },
        "freshness": {
            "has_fresh_trade": fresh_trade,
            "has_fresh_bbo": fresh_bbo,
            "has_fresh_order_book": fresh_book,
            "last_trade_age_seconds": 0.1 if fresh_trade else 60.0,
            "last_bbo_age_seconds": 0.1 if fresh_bbo else 60.0,
            "last_order_book_age_seconds": 0.1 if fresh_book else 60.0,
        },
        "sample": {
            "last_trade_count_total_session": trade_count,
            "rolling_trade_count": min(trade_count, 20),
            "bbo_count": bbo_count,
            "nonzero_bbo_count": bbo_count,
            "order_book_count": book_count,
        },
        "latest_trade": {
            "price": 2400.05,
            "received_at_epoch": updated_at,
        },
        "order_book": {
            "available": book_available,
            "last_received_at_epoch": updated_at,
            "bid_level_count": bid_levels,
            "ask_level_count": ask_levels,
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "top_bid_price": bid,
            "top_ask_price": ask,
        },
        "quality": {
            "safe_for_live_decision": False,
            "safe_for_execution": False,
        },
    }


def test_healthy_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_feed_integrity(
            snapshot(),
            history_path=Path(tmp) / "history.json",
        )

        assert result["status"] == "HEALTHY"
        assert result["integrity_ok"] is True
        assert result["continuity_valid"] is True
        assert result["safe_for_execution"] is False


def test_trade_stale_alone_is_not_dead_feed():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_feed_integrity(
            snapshot(fresh_trade=False),
            history_path=Path(tmp) / "history.json",
        )

        assert result["status"] == "TRADE_STALE_OR_QUIET"
        assert result["integrity_ok"] is True
        assert result["freshness"]["has_fresh_bbo"] is True
        assert result["freshness"]["has_fresh_order_book"] is True


def test_bbo_and_book_stale_is_hard_failure():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_feed_integrity(
            snapshot(
                fresh_trade=False,
                fresh_bbo=False,
                fresh_book=False,
            ),
            history_path=Path(tmp) / "history.json",
        )

        assert result["status"] == "BBO_AND_ORDER_BOOK_STALE"
        assert result["integrity_ok"] is False


def test_crossed_book_fails():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_feed_integrity(
            snapshot(bid=2400.2, ask=2400.1),
            history_path=Path(tmp) / "history.json",
        )

        assert result["status"] == "CROSSED_BOOK"
        assert result["book"]["crossed"] is True


def test_locked_book_degrades():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_feed_integrity(
            snapshot(bid=2400.1, ask=2400.1),
            history_path=Path(tmp) / "history.json",
        )

        assert result["status"] == "DEGRADED_BOOK"
        assert result["book"]["locked"] is True
        assert result["integrity_ok"] is False


def test_counter_reset_breaks_continuity():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "history.json"

        evaluate_rithmic_feed_integrity(
            snapshot(
                updated_at=1.0,
                trade_count=100,
                bbo_count=200,
                book_count=300,
            ),
            history_path=path,
        )

        result = evaluate_rithmic_feed_integrity(
            snapshot(
                updated_at=2.0,
                trade_count=1,
                bbo_count=2,
                book_count=3,
            ),
            history_path=path,
        )

        assert result["status"] == "RESET_REPRIME_REQUIRED"
        assert result["continuity_valid"] is False
        assert result["continuity"]["counter_reset_detected"] is True


def test_duplicate_snapshot_does_not_expand_history():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "history.json"
        item = snapshot()

        first = evaluate_rithmic_feed_integrity(
            item,
            history_path=path,
        )
        second = evaluate_rithmic_feed_integrity(
            item,
            history_path=path,
        )

        assert first["continuity"]["history_snapshot_count"] == 1
        assert second["continuity"]["history_snapshot_count"] == 1
        assert second["continuity"]["duplicate_snapshot"] is True


def test_test_environment_never_production_eligible():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_feed_integrity(
            snapshot(test_environment=True),
            history_path=Path(tmp) / "history.json",
        )

        assert result["environment_grade"] == "TEST_ENVIRONMENT"
        assert result["production_data_eligible"] is False


def test_sequence_gap_check_is_honest():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_feed_integrity(
            snapshot(),
            history_path=Path(tmp) / "history.json",
        )

        assert result["sequence_gap_check"]["status"] == "UNAVAILABLE"


def test_phase5g_resets_antifakeout_history_on_continuity_break():
    source = (
        ROOT
        / "scripts"
        / "build_phase5g_rithmic_monitoring_bridge.py"
    ).read_text(encoding="utf-8", errors="replace")

    required = (
        'bridge["feed_integrity"]',
        "evaluate_rithmic_feed_integrity",
        "format_feed_integrity_text",
        "phase5g_rithmic_feed_integrity_history.json",
        'if not feed_integrity.get("continuity_valid", False):',
        "anti_fakeout_history.unlink()",
    )

    for marker in required:
        assert marker in source, marker

    assert "execute_trade(" not in source
    assert "order_send(" not in source


def main():
    test_healthy_snapshot()
    test_trade_stale_alone_is_not_dead_feed()
    test_bbo_and_book_stale_is_hard_failure()
    test_crossed_book_fails()
    test_locked_book_degrades()
    test_counter_reset_breaks_continuity()
    test_duplicate_snapshot_does_not_expand_history()
    test_test_environment_never_production_eligible()
    test_sequence_gap_check_is_honest()
    test_phase5g_resets_antifakeout_history_on_continuity_break()

    print("PASS: healthy fresh feed is recognized")
    print("PASS: trade staleness alone does not falsely kill a live BBO/DOM feed")
    print("PASS: stale BBO + DOM is a hard integrity failure")
    print("PASS: crossed/locked book validation is enforced")
    print("PASS: counter reset/reconnect invalidates continuity")
    print("PASS: duplicate snapshots do not inflate history")
    print("PASS: Rithmic Test is never production-data eligible")
    print("PASS: sequence-gap check is UNAVAILABLE until a real sequence field exists")
    print("PASS: continuity break resets anti-fakeout persistence history")
    print("PASS: feed integrity guard has no execution authority")


if __name__ == "__main__":
    main()
