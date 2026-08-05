from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import trade_tracker


def _deal(**kwargs):
    return SimpleNamespace(**kwargs)


def test_sl_trigger_with_positive_profit_is_sl_in_profit():
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
                price=4059.48,
                profit=0.0,
            ),
            _deal(
                ticket=2,
                order=101,
                position_id=123,
                entry=trade_tracker.mt5.DEAL_ENTRY_OUT,
                reason=trade_tracker.mt5.DEAL_REASON_SL,
                time=1100,
                price=4061.67,
                profit=6.0,
            ),
        ]

        result = trade_tracker.detect_close_details(
            "123",
            trade={
                "entry_price": 4059.48,
                "stop_loss": 4061.67,
                "take_profit": 4070.0,
            },
        )

        assert result["found_close_deal"] is True
        assert result["close_reason"] == "SL_IN_PROFIT"
        assert result["realized_profit"] == 6.0
        assert result["close_price"] == 4061.67

    finally:
        trade_tracker.mt5.history_deals_get = original_history_deals_get


def test_sl_trigger_with_negative_profit_is_sl_loss():
    original_history_deals_get = trade_tracker.mt5.history_deals_get

    try:
        trade_tracker.mt5.history_deals_get = lambda start, end: [
            _deal(
                ticket=1,
                order=100,
                position_id=456,
                entry=trade_tracker.mt5.DEAL_ENTRY_IN,
                reason=3,
                time=1000,
                price=4055.41,
                profit=0.0,
            ),
            _deal(
                ticket=2,
                order=101,
                position_id=456,
                entry=trade_tracker.mt5.DEAL_ENTRY_OUT,
                reason=trade_tracker.mt5.DEAL_REASON_SL,
                time=1100,
                price=4052.47,
                profit=-9.54,
            ),
        ]

        result = trade_tracker.detect_close_details(
            "456",
            trade={
                "entry_price": 4055.41,
                "stop_loss": 4052.47,
                "take_profit": 4060.41,
            },
        )

        assert result["found_close_deal"] is True
        assert result["close_reason"] == "SL_LOSS"
        assert result["realized_profit"] == -9.54
        assert result["close_price"] == 4052.47

    finally:
        trade_tracker.mt5.history_deals_get = original_history_deals_get


def test_likely_stop_label_uses_profit_result():
    result = trade_tracker.infer_close_reason_from_trade(
        trade={
            "entry_price": 4059.48,
            "stop_loss": 4061.67,
            "take_profit": 4070.0,
        },
        close_price=4061.67,
        realized_profit=6.0,
    )

    assert result == "SL_LIKELY_IN_PROFIT"


if __name__ == "__main__":
    test_sl_trigger_with_positive_profit_is_sl_in_profit()
    test_sl_trigger_with_negative_profit_is_sl_loss()
    test_likely_stop_label_uses_profit_result()
    print("[PASS] Phase 6U6 stop trigger result labels passed.")
