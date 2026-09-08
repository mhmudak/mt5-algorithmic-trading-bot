from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.health_monitor as health_monitor


def _tracker_records(count):
    return {
        str(ticket): {
            "position_id": str(ticket),
            "symbol": "XAUUSD",
            "status": "OPEN",
        }
        for ticket in range(1, count + 1)
    }


def _capture(
    *,
    positions,
    trades,
    tick=None,
    outlook=None,
    connected=True,
):
    messages = []

    fake_mt5 = SimpleNamespace(
        positions_get=lambda symbol=None: positions,
        symbol_info_tick=lambda symbol=None: tick,
        terminal_info=(
            lambda: object()
            if connected
            else None
        ),
    )

    original_mt5 = health_monitor.mt5
    original_load_trades = health_monitor.load_trades
    original_outlook = health_monitor.load_latest_market_outlook
    original_send = health_monitor.send_telegram_message
    original_last = health_monitor.LAST_HEARTBEAT

    try:
        health_monitor.mt5 = fake_mt5
        health_monitor.load_trades = lambda: trades
        health_monitor.load_latest_market_outlook = (
            lambda symbol, report_type: outlook
        )
        health_monitor.send_telegram_message = messages.append
        health_monitor.LAST_HEARTBEAT = None

        health_monitor.send_heartbeat(
            "XAUUSD",
            force=True,
        )

    finally:
        health_monitor.mt5 = original_mt5
        health_monitor.load_trades = original_load_trades
        health_monitor.load_latest_market_outlook = original_outlook
        health_monitor.send_telegram_message = original_send
        health_monitor.LAST_HEARTBEAT = original_last

    assert len(messages) == 1
    return messages[0]


def test_clean_live_heartbeat():
    message = _capture(
        positions=(
            SimpleNamespace(ticket=1),
            SimpleNamespace(ticket=2),
        ),
        trades=_tracker_records(18),
        tick=SimpleNamespace(
            bid=4403.20,
            ask=4403.30,
        ),
        outlook={
            "combined_htf_bias": "BEARISH",
        },
    )

    assert "Symbol: XAUUSD" in message
    assert "Price: 4403.25" in message
    assert "Bias: BEARISH" in message
    assert "Open Trades: 2" in message

    assert "Tracked Open:" not in message
    assert "Pending Reconciliation:" not in message


def test_tracker_diagnostics_remain_internal():
    original_mt5 = health_monitor.mt5
    original_load_trades = health_monitor.load_trades

    try:
        health_monitor.mt5 = SimpleNamespace(
            positions_get=lambda symbol=None: (
                SimpleNamespace(ticket=1),
                SimpleNamespace(ticket=2),
            )
        )

        health_monitor.load_trades = lambda: _tracker_records(18)

        snapshot = health_monitor._get_heartbeat_trade_snapshot(
            "XAUUSD"
        )

    finally:
        health_monitor.mt5 = original_mt5
        health_monitor.load_trades = original_load_trades

    assert snapshot["physical_open_count"] == 2
    assert snapshot["tracked_open_count"] == 18
    assert snapshot["pending_reconciliation_count"] == 16


def test_missing_outlook_is_unknown():
    message = _capture(
        positions=(),
        trades={},
        tick=SimpleNamespace(
            bid=4400.0,
            ask=4400.2,
        ),
        outlook=None,
    )

    assert "Price: 4400.1" in message
    assert "Bias: UNKNOWN" in message
    assert "Open Trades: 0" in message


def test_missing_tick_is_unknown():
    message = _capture(
        positions=(),
        trades={},
        tick=None,
        outlook={
            "combined_htf_bias": "BULLISH",
        },
    )

    assert "Price: UNKNOWN" in message
    assert "Bias: BULLISH" in message


def test_failed_position_query_never_uses_tracker_count():
    message = _capture(
        positions=None,
        trades=_tracker_records(18),
        tick=SimpleNamespace(
            bid=4403.2,
            ask=4403.3,
        ),
        outlook={
            "combined_htf_bias": "BEARISH",
        },
    )

    assert "Open Trades: UNKNOWN" in message
    assert "Open Trades: 18" not in message


def main():
    test_clean_live_heartbeat()
    test_tracker_diagnostics_remain_internal()
    test_missing_outlook_is_unknown()
    test_missing_tick_is_unknown()
    test_failed_position_query_never_uses_tracker_count()

    print(
        "[PASS] Heartbeat shows live MT5 price, "
        "existing HTF bias, physical open positions, "
        "and keeps tracker reconciliation internal."
    )


if __name__ == "__main__":
    main()
