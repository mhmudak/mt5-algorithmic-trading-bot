from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import trade_tracker


def _deal(**kwargs):
    return SimpleNamespace(**kwargs)


def test_entry_only_deal_does_not_close_trade():
    original_history_deals_get = trade_tracker.mt5.history_deals_get

    try:
        trade_tracker.mt5.history_deals_get = lambda start, end: [
            _deal(
                ticket=1,
                order=100,
                position_id=123,
                entry=trade_tracker.mt5.DEAL_ENTRY_IN,
                reason=3,
                time=1000,
                price=4050.0,
                profit=0.0,
            )
        ]

        result = trade_tracker.detect_close_details(
            "123",
            trade={
                "entry_price": 4050.0,
                "stop_loss": 4047.0,
                "take_profit": 4056.0,
            },
        )

        assert result["found_close_deal"] is False
        assert result["realized_profit"] == 0.0
        assert result["close_price"] == 0.0

    finally:
        trade_tracker.mt5.history_deals_get = original_history_deals_get


def test_real_exit_deal_closes_trade_with_profit():
    original_history_deals_get = trade_tracker.mt5.history_deals_get

    try:
        trade_tracker.mt5.history_deals_get = lambda start, end: [
            _deal(
                ticket=1,
                order=100,
                position_id=123,
                entry=trade_tracker.mt5.DEAL_ENTRY_IN,
                reason=3,
                time=1000,
                price=4050.0,
                profit=0.0,
            ),
            _deal(
                ticket=2,
                order=101,
                position_id=123,
                entry=trade_tracker.mt5.DEAL_ENTRY_OUT,
                reason=trade_tracker.mt5.DEAL_REASON_TP,
                time=1100,
                price=4056.0,
                profit=18.0,
            ),
        ]

        result = trade_tracker.detect_close_details(
            "123",
            trade={
                "entry_price": 4050.0,
                "stop_loss": 4047.0,
                "take_profit": 4056.0,
            },
        )

        assert result["found_close_deal"] is True
        assert result["close_reason"] == "TP"
        assert result["realized_profit"] == 18.0
        assert result["close_price"] == 4056.0

    finally:
        trade_tracker.mt5.history_deals_get = original_history_deals_get


if __name__ == "__main__":
    test_entry_only_deal_does_not_close_trade()
    test_real_exit_deal_closes_trade_with_profit()
    print("[PASS] Phase 6U4 trade tracker close-deal guard passed.")
