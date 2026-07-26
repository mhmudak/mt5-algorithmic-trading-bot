from __future__ import annotations

import asyncio
import importlib
import os
import pathlib
import ssl
import sys
import time
from dataclasses import dataclass
from typing import Any

import websockets
from dotenv import load_dotenv


@dataclass(frozen=True)
class RithmicConfig:
    ws_url: str
    system_name: str
    username: str
    password: str
    exchange: str
    symbol: str
    sdk_path: str


def load_rithmic_config() -> RithmicConfig:
    load_dotenv()

    return RithmicConfig(
        ws_url=os.getenv("RITHMIC_WS_URL", "wss://rituz00100.rithmic.com:443"),
        system_name=os.getenv("RITHMIC_SYSTEM_NAME", "Rithmic Test"),
        username=os.getenv("RITHMIC_USERNAME", ""),
        password=os.getenv("RITHMIC_PASSWORD", ""),
        exchange=os.getenv("RITHMIC_EXCHANGE", "COMEX"),
        symbol=os.getenv("RITHMIC_SYMBOL", "GCQ6"),
        sdk_path=os.getenv(
            "RITHMIC_SDK_PATH",
            "vendor_private/rithmic_protocol/0.89.0.0/samples/samples.py",
        ),
    )


def _load_sdk_modules(sdk_path: str) -> dict[str, Any]:
    sdk_dir = pathlib.Path(sdk_path).resolve()

    if not sdk_dir.exists():
        raise FileNotFoundError(f"Rithmic SDK path not found: {sdk_dir}")

    if str(sdk_dir) not in sys.path:
        sys.path.insert(0, str(sdk_dir))

    module_names = [
        "base_pb2",
        "request_heartbeat_pb2",
        "response_heartbeat_pb2",
        "request_login_pb2",
        "response_login_pb2",
        "request_logout_pb2",
        "request_market_data_update_pb2",
        "response_market_data_update_pb2",
        "last_trade_pb2",
        "best_bid_offer_pb2",
    ]

    return {name: importlib.import_module(name) for name in module_names}


class RithmicMarketDataClient:
    """
    Rithmic R | Protocol API market-data client.

    Observe-only provider:
    - no orders
    - no live trading decision influence yet
    - intended first for GC/MGC LastTrade/BBO capture
    """

    def __init__(self, config: RithmicConfig):
        self.config = config
        self.sdk_dir = pathlib.Path(config.sdk_path).resolve()
        self.pb = _load_sdk_modules(config.sdk_path)
        self.ws = None

    def _ssl_context(self):
        cert_path = self.sdk_dir / "rithmic_ssl_cert_auth_params"

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

        if cert_path.exists():
            context.load_verify_locations(cert_path)
        else:
            context.load_default_certs()

        return context

    async def connect(self):
        self.ws = await websockets.connect(
            self.config.ws_url,
            ssl=self._ssl_context(),
            ping_interval=3,
        )
        return self.ws

    async def send_heartbeat(self):
        rq = self.pb["request_heartbeat_pb2"].RequestHeartbeat()
        rq.template_id = 18
        await self.ws.send(rq.SerializeToString())

    async def login(self) -> dict[str, Any]:
        rq = self.pb["request_login_pb2"].RequestLogin()
        rq.template_id = 10
        rq.template_version = "3.9"
        rq.user_msg.append("phase5a_orderflow_provider")

        rq.user = self.config.username
        rq.password = self.config.password
        rq.app_name = "MT5BotPhase5A"
        rq.app_version = "0.1.0"
        rq.system_name = self.config.system_name
        rq.infra_type = self.pb["request_login_pb2"].RequestLogin.SysInfraType.TICKER_PLANT

        await self.ws.send(rq.SerializeToString())

        raw = await self.ws.recv()
        rp = self.pb["response_login_pb2"].ResponseLogin()
        rp.ParseFromString(raw)

        rp_code = list(rp.rp_code)

        return {
            "event_type": "login_response",
            "template_id": rp.template_id,
            "rp_code": rp_code,
            "ok": bool(rp_code and rp_code[0] == "0"),
            "fcm_id": rp.fcm_id,
            "ib_id": rp.ib_id,
            "heartbeat_interval": rp.heartbeat_interval,
            "unique_user_id": rp.unique_user_id,
        }

    async def subscribe_market_data(self):
        rq = self.pb["request_market_data_update_pb2"].RequestMarketDataUpdate()
        rq.template_id = 100
        rq.user_msg.append("phase5a_subscribe_market_data")
        rq.symbol = self.config.symbol
        rq.exchange = self.config.exchange
        rq.request = self.pb["request_market_data_update_pb2"].RequestMarketDataUpdate.Request.SUBSCRIBE
        rq.update_bits = (
            self.pb["request_market_data_update_pb2"].RequestMarketDataUpdate.UpdateBits.LAST_TRADE
            | self.pb["request_market_data_update_pb2"].RequestMarketDataUpdate.UpdateBits.BBO
        )

        await self.ws.send(rq.SerializeToString())

    async def logout(self):
        rq = self.pb["request_logout_pb2"].RequestLogout()
        rq.template_id = 12
        rq.user_msg.append("phase5a_logout")

        try:
            await self.ws.send(rq.SerializeToString())
        except Exception:
            pass

        try:
            await self.ws.close(1000, "phase5a done")
        except Exception:
            pass

    def parse_message(self, raw: bytes) -> dict[str, Any]:
        base = self.pb["base_pb2"].Base()
        base.ParseFromString(raw)

        now_ts = time.time()

        if base.template_id == 19:
            return {
                "event_type": "heartbeat_response",
                "template_id": base.template_id,
                "received_at_epoch": now_ts,
            }

        if base.template_id == 101:
            msg = self.pb["response_market_data_update_pb2"].ResponseMarketDataUpdate()
            msg.ParseFromString(raw)
            return {
                "event_type": "market_data_response",
                "template_id": msg.template_id,
                "rp_code": list(msg.rp_code),
                "user_msg": list(msg.user_msg),
                "received_at_epoch": now_ts,
            }

        if base.template_id == 151:
            msg = self.pb["best_bid_offer_pb2"].BestBidOffer()
            msg.ParseFromString(raw)

            return {
                "event_type": "best_bid_offer",
                "template_id": base.template_id,
                "symbol": msg.symbol,
                "exchange": msg.exchange,
                "is_snapshot": bool(msg.is_snapshot),
                "bid_price": float(msg.bid_price),
                "bid_size": int(msg.bid_size),
                "bid_orders": int(msg.bid_orders),
                "ask_price": float(msg.ask_price),
                "ask_size": int(msg.ask_size),
                "ask_orders": int(msg.ask_orders),
                "ssboe": int(msg.ssboe),
                "usecs": int(msg.usecs),
                "received_at_epoch": now_ts,
            }

        if base.template_id == 150:
            msg = self.pb["last_trade_pb2"].LastTrade()
            msg.ParseFromString(raw)

            buy_value = self.pb["last_trade_pb2"].LastTrade.TransactionType.BUY
            aggressor = "BUY" if msg.aggressor == buy_value else "SELL"

            return {
                "event_type": "last_trade",
                "template_id": base.template_id,
                "symbol": msg.symbol,
                "exchange": msg.exchange,
                "is_snapshot": bool(msg.is_snapshot),
                "trade_price": float(msg.trade_price),
                "trade_size": int(msg.trade_size),
                "aggressor": aggressor,
                "net_change": float(msg.net_change),
                "percent_change": float(msg.percent_change),
                "volume": int(msg.volume),
                "ssboe": int(msg.ssboe),
                "usecs": int(msg.usecs),
                "received_at_epoch": now_ts,
            }

        return {
            "event_type": "unhandled",
            "template_id": base.template_id,
            "received_at_epoch": now_ts,
        }

    async def stream(self, duration_seconds: int = 60):
        await self.connect()

        login_event = await self.login()
        yield login_event

        if not login_event.get("ok"):
            return

        await self.subscribe_market_data()
        await self.send_heartbeat()

        end_time = time.time() + duration_seconds

        while time.time() < end_time:
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=5)
                yield self.parse_message(raw)
            except asyncio.TimeoutError:
                await self.send_heartbeat()

        await self.logout()
