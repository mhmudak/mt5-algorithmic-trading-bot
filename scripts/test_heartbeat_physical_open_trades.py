from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.health_monitor as health_monitor


def _capture_heartbeat(
    *,
    positions,
    trades,
    connected=True,
):
    messages = []

    fake_mt5 = SimpleNamespace(
        positions_get=lambda symbol=None: positions,
        terminal_info=(
            lambda: object()
            if connected
            else None
        ),
    )

    original_mt5 = health_monitor.mt5
    original_load_trades = health_monitor.load_trades
    original_send = health_monitor.send_telegram_message
    original_last = health_monitor.LAST_HEARTBEAT

    try:
        health_monitor.mt5 = fake_mt5
        health_monitor.load_trades = lambda: trades
        health_monitor.send_telegram_message = messages.append
        health_monitor.LAST_HEARTBEAT = None

        health_monitor.send_heartbeat(
            "XAUUSD",
            force=True,
        )

    finally:
        health_monitor.mt5 = original_mt5
        health_monitor.load_trades = original_load_trades
        health_monitor.send_telegram_message = original_send
        health_monitor.LAST_HEARTBEAT = original_last

    assert len(messages) == 1

    return messages[0]


def test_physical_mt5_count_is_authoritative():
    trades = {}

    for ticket in range(
        1,
        20,
    ):
        trades[str(ticket)] = {
            "position_id": str(ticket),
            "symbol": "XAUUSD",
            "status": "OPEN",
        }

    positions = (
        SimpleNamespace(
            ticket=1,
        ),
        SimpleNamespace(
            ticket=2,
        ),
    )

    message = _capture_heartbeat(
        positions=positions,
        trades=trades,
    )

    assert "Open Trades: 2" in message
    assert "Tracked Open: 19" in message
    assert "Pending Reconciliation: 17" in message


def test_other_symbols_do_not_pollute_tracker_count():
    trades = {
        "1": {
            "position_id": "1",
            "symbol": "XAUUSD",
            "status": "OPEN",
        },
        "2": {
            "position_id": "2",
            "symbol": "EURUSD",
            "status": "OPEN",
        },
    }

    positions = (
        SimpleNamespace(
            ticket=1,
        ),
    )

    message = _capture_heartbeat(
        positions=positions,
        trades=trades,
    )

    assert "Open Trades: 1" in message
    assert "Tracked Open: 1" in message
    assert "Pending Reconciliation: 0" in message


def test_failed_mt5_position_query_never_uses_tracker_as_physical_count():
    trades = {}

    for ticket in range(
        1,
        20,
    ):
        trades[str(ticket)] = {
            "position_id": str(ticket),
            "symbol": "XAUUSD",
            "status": "OPEN",
        }

    message = _capture_heartbeat(
        positions=None,
        trades=trades,
    )

    assert "Open Trades: UNKNOWN" in message
    assert "Tracked Open: 19" in message
    assert "Pending Reconciliation: UNKNOWN" in message

    assert "Open Trades: 19" not in message


def test_closed_tracker_records_are_not_counted():
    trades = {
        "1": {
            "position_id": "1",
            "symbol": "XAUUSD",
            "status": "OPEN",
        },
        "2": {
            "position_id": "2",
            "symbol": "XAUUSD",
            "status": "CLOSED",
        },
    }

    positions = (
        SimpleNamespace(
            ticket=1,
        ),
    )

    message = _capture_heartbeat(
        positions=positions,
        trades=trades,
    )

    assert "Open Trades: 1" in message
    assert "Tracked Open: 1" in message
    assert "Pending Reconciliation: 0" in message


def main():
    test_physical_mt5_count_is_authoritative()
    test_other_symbols_do_not_pollute_tracker_count()
    test_failed_mt5_position_query_never_uses_tracker_as_physical_count()
    test_closed_tracker_records_are_not_counted()

    print(
        "[PASS] Heartbeat uses physical MT5 positions "
        "as open-trade authority and keeps tracker state "
        "diagnostic-only."
    )


if __name__ == "__main__":
    main()
