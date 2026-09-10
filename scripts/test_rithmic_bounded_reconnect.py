from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.order_flow_providers.rithmic_protocol import (
    RithmicConfig,
    RithmicMarketDataClient,
)


def make_client():
    client = object.__new__(
        RithmicMarketDataClient
    )

    client.config = RithmicConfig(
        ws_url="wss://example.invalid",
        system_name="TEST",
        username="test",
        password="test",
        exchange="COMEX",
        symbol="GC_TEST",
        sdk_path="unused",
    )

    client.pb = {}
    client.ws = None

    return client


class FakeWebSocket:
    def __init__(
        self,
        *,
        disconnect=False,
    ):
        self.disconnect = disconnect
        self.closed = False
        self.recv_count = 0

    async def recv(self):
        self.recv_count += 1

        if self.disconnect:
            raise ConnectionResetError(
                "simulated disconnect"
            )

        return b"market-data"

    async def close(self, *args, **kwargs):
        self.closed = True


class FakeClock:
    def __init__(self):
        self.value = 1000.0

    def time(self):
        self.value += 0.20
        return self.value


async def collect(generator):
    items = []

    async for item in generator:
        items.append(item)

    return items


def install_common_methods(
    client,
    *,
    connect_impl,
    login_impl,
):
    async def subscribe_market_data(
        self,
        *,
        include_order_book=False,
    ):
        self._subscribe_calls += 1
        self._subscribe_order_book.append(
            include_order_book
        )

    async def send_heartbeat(self):
        self._heartbeat_calls += 1

    async def logout(self):
        self._logout_calls += 1

        ws = self.ws

        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

        self.ws = None

    def parse_message(self, raw):
        return {
            "event_type": "last_trade",
            "symbol": self.config.symbol,
            "exchange": self.config.exchange,
            "raw": raw.decode("ascii"),
        }

    client._connect_calls = 0
    client._login_calls = 0
    client._subscribe_calls = 0
    client._subscribe_order_book = []
    client._heartbeat_calls = 0
    client._logout_calls = 0

    client.connect = types.MethodType(
        connect_impl,
        client,
    )

    client.login = types.MethodType(
        login_impl,
        client,
    )

    client.subscribe_market_data = (
        types.MethodType(
            subscribe_market_data,
            client,
        )
    )

    client.send_heartbeat = (
        types.MethodType(
            send_heartbeat,
            client,
        )
    )

    client.logout = types.MethodType(
        logout,
        client,
    )

    client.parse_message = types.MethodType(
        parse_message,
        client,
    )


async def test_disconnect_then_successful_recovery():
    client = make_client()

    first_ws = FakeWebSocket(
        disconnect=True
    )

    recovered_ws = FakeWebSocket(
        disconnect=False
    )

    async def connect(self):
        self._connect_calls += 1

        if self._connect_calls == 1:
            self.ws = first_ws
        else:
            self.ws = recovered_ws

        return self.ws

    async def login(self):
        self._login_calls += 1

        return {
            "event_type": "login_response",
            "ok": True,
            "rp_code": ["0"],
        }

    install_common_methods(
        client,
        connect_impl=connect,
        login_impl=login,
    )

    import src.order_flow_providers.rithmic_protocol as protocol

    original_time = protocol.time.time

    clock = FakeClock()
    protocol.time.time = clock.time

    try:
        events = await collect(
            client.stream(
                duration_seconds=2,
                include_order_book=True,
                reconnect_max_attempts=3,
                reconnect_backoff_seconds=0,
            )
        )
    finally:
        protocol.time.time = original_time

    statuses = [
        event.get("status")
        for event in events
        if event.get("event_type")
        == "connection_recovery"
    ]

    assert "DISCONNECTED" in statuses
    assert "RECONNECTED" in statuses

    assert (
        "RECONNECT_EXHAUSTED"
        not in statuses
    )

    assert client._connect_calls == 2
    assert client._login_calls == 2
    assert client._subscribe_calls == 2
    assert client._heartbeat_calls == 2

    assert client._subscribe_order_book == [
        True,
        True,
    ]

    market_events = [
        event
        for event in events
        if event.get("event_type")
        == "last_trade"
    ]

    assert market_events

    for event in market_events:
        assert event["symbol"] == "GC_TEST"
        assert event["exchange"] == "COMEX"


async def test_reconnect_attempts_are_bounded():
    client = make_client()

    initial_ws = FakeWebSocket(
        disconnect=True
    )

    async def connect(self):
        self._connect_calls += 1

        if self._connect_calls == 1:
            self.ws = initial_ws
            return self.ws

        raise ConnectionResetError(
            "simulated reconnect failure"
        )

    async def login(self):
        self._login_calls += 1

        return {
            "event_type": "login_response",
            "ok": True,
            "rp_code": ["0"],
        }

    install_common_methods(
        client,
        connect_impl=connect,
        login_impl=login,
    )

    events = await collect(
        client.stream(
            duration_seconds=60,
            reconnect_max_attempts=2,
            reconnect_backoff_seconds=0,
        )
    )

    statuses = [
        event.get("status")
        for event in events
        if event.get("event_type")
        == "connection_recovery"
    ]

    assert statuses.count(
        "RECONNECT_ATTEMPT_FAILED"
    ) == 2

    assert statuses.count(
        "RECONNECT_EXHAUSTED"
    ) == 1

    assert "RECONNECTED" not in statuses

    # Initial connect + exactly two bounded retries.
    assert client._connect_calls == 3


async def test_reconnect_login_rejection_stops_retrying():
    client = make_client()

    first_ws = FakeWebSocket(
        disconnect=True
    )

    second_ws = FakeWebSocket(
        disconnect=False
    )

    async def connect(self):
        self._connect_calls += 1

        if self._connect_calls == 1:
            self.ws = first_ws
        else:
            self.ws = second_ws

        return self.ws

    async def login(self):
        self._login_calls += 1

        if self._login_calls == 1:
            return {
                "event_type": "login_response",
                "ok": True,
                "rp_code": ["0"],
            }

        return {
            "event_type": "login_response",
            "ok": False,
            "rp_code": ["AUTH_REJECTED"],
        }

    install_common_methods(
        client,
        connect_impl=connect,
        login_impl=login,
    )

    events = await collect(
        client.stream(
            duration_seconds=60,
            reconnect_max_attempts=3,
            reconnect_backoff_seconds=0,
        )
    )

    statuses = [
        event.get("status")
        for event in events
        if event.get("event_type")
        == "connection_recovery"
    ]

    assert (
        "RECONNECT_LOGIN_REJECTED"
        in statuses
    )

    assert (
        "RECONNECT_EXHAUSTED"
        in statuses
    )

    assert "RECONNECTED" not in statuses

    # Do not hammer rejected credentials.
    assert client._connect_calls == 2
    assert client._login_calls == 2


async def test_zero_retry_budget_reports_zero_attempts():
    client = make_client()

    initial_ws = FakeWebSocket(
        disconnect=True
    )

    async def connect(self):
        self._connect_calls += 1
        self.ws = initial_ws
        return self.ws

    async def login(self):
        self._login_calls += 1

        return {
            "event_type": "login_response",
            "ok": True,
            "rp_code": ["0"],
        }

    install_common_methods(
        client,
        connect_impl=connect,
        login_impl=login,
    )

    events = await collect(
        client.stream(
            duration_seconds=60,
            reconnect_max_attempts=0,
            reconnect_backoff_seconds=0,
        )
    )

    exhausted = [
        event
        for event in events
        if (
            event.get("event_type")
            == "connection_recovery"
            and event.get("status")
            == "RECONNECT_EXHAUSTED"
        )
    ]

    assert len(exhausted) == 1
    assert exhausted[0]["attempt"] == 0
    assert exhausted[0]["max_attempts"] == 0

    # No reconnect was attempted.
    assert client._connect_calls == 1


def test_recovery_events_are_observe_only():
    client = make_client()

    event = (
        client._connection_recovery_event(
            status="DISCONNECTED",
            attempt=0,
            max_attempts=3,
            error_type="ConnectionResetError",
        )
    )

    assert event["symbol"] == "GC_TEST"
    assert event["exchange"] == "COMEX"

    assert (
        event["decision_impact"]
        == "NONE"
    )

    assert (
        event["can_influence_decision"]
        is False
    )

    assert (
        event["safe_for_execution"]
        is False
    )


def main():
    asyncio.run(
        test_disconnect_then_successful_recovery()
    )

    asyncio.run(
        test_reconnect_attempts_are_bounded()
    )

    asyncio.run(
        test_reconnect_login_rejection_stops_retrying()
    )

    asyncio.run(
        test_zero_retry_budget_reports_zero_attempts()
    )

    test_recovery_events_are_observe_only()

    print(
        "[PASS] Rithmic stream performs bounded "
        "disconnect recovery with re-login, "
        "same-contract re-subscription, heartbeat "
        "restoration, and observe-only diagnostics."
    )


if __name__ == "__main__":
    main()
