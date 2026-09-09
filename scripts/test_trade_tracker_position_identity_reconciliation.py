from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )

import src.trade_tracker as tracker


class FakeMT5:
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1

    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_INOUT = 2
    DEAL_ENTRY_OUT_BY = 3

    DEAL_REASON_SL = 10
    DEAL_REASON_TP = 11
    DEAL_REASON_SO = 12

    def __init__(self):
        self.positions = []
        self.positions_by_ticket = {}
        self.deals_by_ticket = {}
        self.orders_by_ticket = {}
        self.deals_by_position = {}
        self.broad_deals = []
        self.broad_calls = 0

    def positions_get(
        self,
        *,
        ticket=None,
        symbol=None,
    ):
        if ticket is not None:
            return self.positions_by_ticket.get(
                int(ticket),
                (),
            )

        return tuple(
            self.positions
        )

    def history_deals_get(
        self,
        *args,
        ticket=None,
        position=None,
    ):
        if ticket is not None:
            deal = self.deals_by_ticket.get(
                int(ticket)
            )

            return (
                (deal,)
                if deal is not None
                else ()
            )

        if position is not None:
            return tuple(
                self.deals_by_position.get(
                    int(position),
                    (),
                )
            )

        self.broad_calls += 1

        return tuple(
            self.broad_deals
        )

    def history_orders_get(
        self,
        *,
        ticket=None,
    ):
        order = self.orders_by_ticket.get(
            int(ticket)
        )

        return (
            (order,)
            if order is not None
            else ()
        )


def test_execution_uses_direct_deal_identity():
    fake = FakeMT5()

    fake.deals_by_ticket[
        9001
    ] = SimpleNamespace(
        ticket=9001,
        order=8001,
        position_id=7001,
        entry=fake.DEAL_ENTRY_IN,
    )

    result = SimpleNamespace(
        order=8001,
        deal=9001,
    )

    original_mt5 = tracker.mt5
    original_sleep = tracker.time.sleep

    try:
        tracker.mt5 = fake
        tracker.time.sleep = lambda _: None

        resolved = (
            tracker.resolve_position_id_after_execution(
                "XAUUSD",
                "BUY",
                {
                    "lot": 0.25,
                },
                result,
            )
        )

    finally:
        tracker.mt5 = original_mt5
        tracker.time.sleep = original_sleep

    assert resolved == "7001"


def test_execution_uses_exact_identifier_not_newest_guess():
    fake = FakeMT5()

    fake.positions = [
        SimpleNamespace(
            ticket=9999,
            identifier=9998,
            type=fake.POSITION_TYPE_BUY,
            volume=0.25,
            time_msc=999999,
        ),
        SimpleNamespace(
            ticket=7001,
            identifier=8001,
            type=fake.POSITION_TYPE_BUY,
            volume=0.25,
            time_msc=1,
        ),
    ]

    result = SimpleNamespace(
        order=8001,
        deal=9001,
    )

    original_mt5 = tracker.mt5
    original_sleep = tracker.time.sleep

    try:
        tracker.mt5 = fake
        tracker.time.sleep = lambda _: None

        resolved = (
            tracker.resolve_position_id_after_execution(
                "XAUUSD",
                "BUY",
                {
                    "lot": 0.25,
                },
                result,
            )
        )

    finally:
        tracker.mt5 = original_mt5
        tracker.time.sleep = original_sleep

    assert resolved == "7001"


def test_execution_never_selects_unrelated_newest_position():
    fake = FakeMT5()

    fake.positions = [
        SimpleNamespace(
            ticket=9999,
            identifier=9998,
            type=fake.POSITION_TYPE_BUY,
            volume=0.25,
            time_msc=999999,
        ),
    ]

    result = SimpleNamespace(
        order=8001,
        deal=9001,
    )

    original_mt5 = tracker.mt5
    original_sleep = tracker.time.sleep

    try:
        tracker.mt5 = fake
        tracker.time.sleep = lambda _: None

        resolved = (
            tracker.resolve_position_id_after_execution(
                "XAUUSD",
                "BUY",
                {
                    "lot": 0.25,
                },
                result,
            )
        )

    finally:
        tracker.mt5 = original_mt5
        tracker.time.sleep = original_sleep

    assert resolved == "8001"
    assert resolved != "9999"


def test_stale_tracker_id_resolves_from_stored_deal():
    fake = FakeMT5()

    fake.deals_by_ticket[
        9001
    ] = SimpleNamespace(
        ticket=9001,
        order=8001,
        position_id=7001,
        entry=fake.DEAL_ENTRY_IN,
    )

    original_mt5 = tracker.mt5

    try:
        tracker.mt5 = fake

        (
            resolved,
            source,
        ) = (
            tracker.resolve_trade_position_id_from_history(
                "9999",
                {
                    "deal_id": 9001,
                    "order_id": 8001,
                },
            )
        )

    finally:
        tracker.mt5 = original_mt5

    assert resolved == "7001"
    assert source == "DIRECT_DEAL_ID"


def test_close_detection_prefers_direct_position_history():
    fake = FakeMT5()

    open_deal = SimpleNamespace(
        ticket=9001,
        position_id=7001,
        entry=fake.DEAL_ENTRY_IN,
        reason=0,
        price=100.0,
        profit=0.0,
        time=100,
    )

    close_deal = SimpleNamespace(
        ticket=9002,
        position_id=7001,
        entry=fake.DEAL_ENTRY_OUT,
        reason=fake.DEAL_REASON_TP,
        price=130.0,
        profit=75.0,
        time=200,
    )

    fake.deals_by_position[
        7001
    ] = [
        open_deal,
        close_deal,
    ]

    original_mt5 = tracker.mt5

    try:
        tracker.mt5 = fake

        result = (
            tracker.detect_close_details(
                "7001",
                trade={
                    "stop_loss": 90.0,
                    "take_profit": 130.0,
                },
            )
        )

    finally:
        tracker.mt5 = original_mt5

    assert result["found_close_deal"] is True
    assert result["close_reason"] == "TP"
    assert result["realized_profit"] == 75.0
    assert result["close_price"] == 130.0
    assert result["close_time"] is not None

    # Direct position lookup was enough.
    assert fake.broad_calls == 0


def test_lifecycle_relinks_and_closes_authoritatively():
    fake = FakeMT5()

    open_deal = SimpleNamespace(
        ticket=9001,
        order=8001,
        position_id=7001,
        entry=fake.DEAL_ENTRY_IN,
        reason=0,
        price=100.0,
        profit=0.0,
        time=100,
    )

    close_deal = SimpleNamespace(
        ticket=9002,
        order=8002,
        position_id=7001,
        entry=fake.DEAL_ENTRY_OUT,
        reason=fake.DEAL_REASON_SL,
        price=90.0,
        profit=-25.0,
        time=200,
    )

    fake.deals_by_ticket[
        9001
    ] = open_deal

    fake.orders_by_ticket[
        8001
    ] = SimpleNamespace(
        ticket=8001,
        position_id=7001,
    )

    fake.deals_by_position[
        7001
    ] = [
        open_deal,
        close_deal,
    ]

    trades = {
        "9999": {
            "position_id": "9999",
            "main_position_id": "9999",
            "trade_role": "MAIN",
            "setup_id": "TEST-1",
            "symbol": "XAUUSD",
            "signal": "BUY",
            "entry_price": 100.0,
            "stop_loss": 90.0,
            "take_profit": 130.0,
            "initial_volume": 0.25,
            "remaining_volume": 0.25,
            "closed_volume": 0.0,
            "status": "OPEN",
            "partial_closes": [],
            "strategy": "TEST",
            "market_condition": "TEST",
            "reason": "synthetic",
            "deal_id": 9001,
            "raw_deal_id": 9001,
            "order_id": 8001,
            "raw_order_id": 8001,
            "missing_position_checks": 100,
            "close_reconciliation_pending": True,
        }
    }

    saved = []
    sent = []
    cooldowns = []

    original_mt5 = tracker.mt5
    original_load = tracker.load_trades
    original_save = tracker.save_trades
    original_send = tracker.send_telegram_message
    original_cooldown = tracker.activate_cooldown
    original_log_event = tracker.log_setup_event
    original_reconcile = (
        tracker.reconcile_setup_outcome_from_closed_trade
    )

    try:
        tracker.mt5 = fake
        tracker.load_trades = (
            lambda: deepcopy(trades)
        )
        tracker.save_trades = (
            lambda value:
            saved.append(
                deepcopy(value)
            )
        )
        tracker.send_telegram_message = sent.append
        tracker.activate_cooldown = (
            lambda:
            cooldowns.append(True)
        )
        tracker.log_setup_event = (
            lambda **kwargs: None
        )
        tracker.reconcile_setup_outcome_from_closed_trade = (
            lambda trade: {
                "ok": True,
            }
        )

        tracker.update_trade_lifecycle(
            "XAUUSD"
        )

    finally:
        tracker.mt5 = original_mt5
        tracker.load_trades = original_load
        tracker.save_trades = original_save
        tracker.send_telegram_message = original_send
        tracker.activate_cooldown = original_cooldown
        tracker.log_setup_event = original_log_event
        tracker.reconcile_setup_outcome_from_closed_trade = (
            original_reconcile
        )

    assert saved

    final = saved[-1]

    assert "9999" not in final
    assert "7001" in final

    trade = final["7001"]

    assert trade["position_id"] == "7001"
    assert trade["status"] == "CLOSED"
    assert trade["remaining_volume"] == 0.0
    assert trade["close_reason"] == "SL_LOSS"
    assert trade["final_result"] == "LOSS"

    assert (
        trade["position_id_relinked_from"]
        == "9999"
    )

    # Production lifecycle semantics stay unchanged.
    # The one-time existing backlog will be migrated
    # separately before restart.
    assert cooldowns == [True]
    assert len(sent) == 1
    assert "Trade Fully Closed" in sent[0]


def main():
    test_execution_uses_direct_deal_identity()
    test_execution_uses_exact_identifier_not_newest_guess()
    test_execution_never_selects_unrelated_newest_position()
    test_stale_tracker_id_resolves_from_stored_deal()
    test_close_detection_prefers_direct_position_history()
    test_lifecycle_relinks_and_closes_authoritatively()

    print(
        "[PASS] Trade tracker uses authoritative MT5 "
        "position identity, direct position close history, "
        "and safely relinks provably stale position IDs."
    )


if __name__ == "__main__":
    main()
