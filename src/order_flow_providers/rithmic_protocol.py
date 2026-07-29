from __future__ import annotations

import asyncio
import base64
import importlib
import os
import pathlib
import ssl
import sys
import time
from dataclasses import dataclass
from typing import Any

import websockets
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
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


_ORDER_BOOK_CLASS = None

_ORDER_BOOK_UPDATE_TYPE_NAMES = {
    1: "CLEAR_ORDER_BOOK",
    2: "NO_BOOK",
    3: "SNAPSHOT_IMAGE",
    4: "BEGIN",
    5: "MIDDLE",
    6: "END",
    7: "SOLO",
}


def _add_dynamic_field(message, name, number, label, field_type, type_name=None):
    field = message.field.add()
    field.name = name
    field.number = number
    field.label = label
    field.type = field_type

    if type_name:
        field.type_name = type_name


def _get_dynamic_order_book_class():
    global _ORDER_BOOK_CLASS

    if _ORDER_BOOK_CLASS is not None:
        return _ORDER_BOOK_CLASS

    file_proto = descriptor_pb2.FileDescriptorProto()
    file_proto.name = "dynamic_order_book.proto"
    file_proto.package = "rti"
    file_proto.syntax = "proto2"

    message = file_proto.message_type.add()
    message.name = "OrderBook"

    presence_enum = message.enum_type.add()
    presence_enum.name = "PresenceBits"
    v = presence_enum.value.add()
    v.name = "BID"
    v.number = 1
    v = presence_enum.value.add()
    v.name = "ASK"
    v.number = 2

    update_enum = message.enum_type.add()
    update_enum.name = "UpdateType"

    for name, number in [
        ("CLEAR_ORDER_BOOK", 1),
        ("NO_BOOK", 2),
        ("SNAPSHOT_IMAGE", 3),
        ("BEGIN", 4),
        ("MIDDLE", 5),
        ("END", 6),
        ("SOLO", 7),
    ]:
        v = update_enum.value.add()
        v.name = name
        v.number = number

    Field = descriptor_pb2.FieldDescriptorProto

    _add_dynamic_field(message, "template_id", 154467, Field.LABEL_REQUIRED, Field.TYPE_INT32)
    _add_dynamic_field(message, "symbol", 110100, Field.LABEL_OPTIONAL, Field.TYPE_STRING)
    _add_dynamic_field(message, "exchange", 110101, Field.LABEL_OPTIONAL, Field.TYPE_STRING)
    _add_dynamic_field(message, "presence_bits", 149138, Field.LABEL_OPTIONAL, Field.TYPE_UINT32)
    _add_dynamic_field(
        message,
        "update_type",
        157608,
        Field.LABEL_OPTIONAL,
        Field.TYPE_ENUM,
        ".rti.OrderBook.UpdateType",
    )

    _add_dynamic_field(message, "bid_price", 154282, Field.LABEL_REPEATED, Field.TYPE_DOUBLE)
    _add_dynamic_field(message, "bid_size", 154283, Field.LABEL_REPEATED, Field.TYPE_INT32)
    _add_dynamic_field(message, "bid_orders", 154401, Field.LABEL_REPEATED, Field.TYPE_INT32)
    _add_dynamic_field(message, "impl_bid_size", 154412, Field.LABEL_REPEATED, Field.TYPE_INT32)

    _add_dynamic_field(message, "ask_price", 154284, Field.LABEL_REPEATED, Field.TYPE_DOUBLE)
    _add_dynamic_field(message, "ask_size", 154285, Field.LABEL_REPEATED, Field.TYPE_INT32)
    _add_dynamic_field(message, "ask_orders", 154402, Field.LABEL_REPEATED, Field.TYPE_INT32)
    _add_dynamic_field(message, "impl_ask_size", 154415, Field.LABEL_REPEATED, Field.TYPE_INT32)

    _add_dynamic_field(message, "ssboe", 150100, Field.LABEL_OPTIONAL, Field.TYPE_INT32)
    _add_dynamic_field(message, "usecs", 150101, Field.LABEL_OPTIONAL, Field.TYPE_INT32)

    pool = descriptor_pool.DescriptorPool()
    pool.Add(file_proto)

    descriptor = pool.FindMessageTypeByName("rti.OrderBook")
    factory = message_factory.MessageFactory(pool)

    if hasattr(factory, "GetPrototype"):
        _ORDER_BOOK_CLASS = factory.GetPrototype(descriptor)
    else:
        _ORDER_BOOK_CLASS = message_factory.GetMessageClass(descriptor)

    return _ORDER_BOOK_CLASS


def _list_get(values, idx, default=0):
    try:
        return values[idx]
    except Exception:
        return default


def _build_order_book_levels(prices, sizes, orders, impl_sizes):
    prices = list(prices)
    sizes = list(sizes)
    orders = list(orders)
    impl_sizes = list(impl_sizes)

    levels = []

    for idx, price in enumerate(prices):
        levels.append(
            {
                "level": idx + 1,
                "price": float(price),
                "size": int(_list_get(sizes, idx, 0)),
                "orders": int(_list_get(orders, idx, 0)),
                "implicit_size": int(_list_get(impl_sizes, idx, 0)),
            }
        )

    return levels


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
        rq.app_name = os.getenv("RITHMIC_APP_NAME", "MT5_XAUUSD_RITHMIC_OBSERVE_ONLY")
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

    async def subscribe_market_data(self, *, include_order_book: bool = False):
        rq = self.pb["request_market_data_update_pb2"].RequestMarketDataUpdate()
        rq.template_id = 100
        rq.user_msg.append("phase5_subscribe_market_data")
        rq.symbol = self.config.symbol
        rq.exchange = self.config.exchange
        rq.request = self.pb["request_market_data_update_pb2"].RequestMarketDataUpdate.Request.SUBSCRIBE

        update_bits = (
            self.pb["request_market_data_update_pb2"].RequestMarketDataUpdate.UpdateBits.LAST_TRADE
            | self.pb["request_market_data_update_pb2"].RequestMarketDataUpdate.UpdateBits.BBO
        )

        if include_order_book:
            update_bits = (
                update_bits
                | self.pb["request_market_data_update_pb2"].RequestMarketDataUpdate.UpdateBits.ORDER_BOOK
            )
            rq.user_msg.append("phase5d_include_order_book")

        rq.update_bits = update_bits

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

        if base.template_id == 156:
            cls = _get_dynamic_order_book_class()
            msg = cls()
            msg.ParseFromString(raw)

            bid_levels = _build_order_book_levels(
                msg.bid_price,
                msg.bid_size,
                msg.bid_orders,
                msg.impl_bid_size,
            )
            ask_levels = _build_order_book_levels(
                msg.ask_price,
                msg.ask_size,
                msg.ask_orders,
                msg.impl_ask_size,
            )

            bid_depth = sum(level["size"] for level in bid_levels)
            ask_depth = sum(level["size"] for level in ask_levels)

            total_depth = bid_depth + ask_depth
            depth_imbalance = None
            if total_depth > 0:
                depth_imbalance = round((bid_depth - ask_depth) / total_depth, 6)

            update_type = int(getattr(msg, "update_type", 0) or 0)

            return {
                "event_type": "order_book",
                "template_id": base.template_id,
                "symbol": msg.symbol,
                "exchange": msg.exchange,
                "presence_bits": int(getattr(msg, "presence_bits", 0) or 0),
                "update_type": update_type,
                "update_type_name": _ORDER_BOOK_UPDATE_TYPE_NAMES.get(update_type, "UNKNOWN"),
                "bid_level_count": len(bid_levels),
                "ask_level_count": len(ask_levels),
                "bid_depth": bid_depth,
                "ask_depth": ask_depth,
                "depth_imbalance": depth_imbalance,
                "top_bid_price": bid_levels[0]["price"] if bid_levels else None,
                "top_ask_price": ask_levels[0]["price"] if ask_levels else None,
                "bid_levels": bid_levels,
                "ask_levels": ask_levels,
                "ssboe": int(getattr(msg, "ssboe", 0) or 0),
                "usecs": int(getattr(msg, "usecs", 0) or 0),
                "received_at_epoch": now_ts,
            }

        return {
            "event_type": "unhandled",
            "template_id": base.template_id,
            "received_at_epoch": now_ts,
            "raw_base64": base64.b64encode(raw).decode("ascii"),
            "raw_size_bytes": len(raw),
        }

    async def stream(self, duration_seconds: int = 60, *, include_order_book: bool = False):
        await self.connect()

        login_event = await self.login()
        yield login_event

        if not login_event.get("ok"):
            return

        await self.subscribe_market_data(include_order_book=include_order_book)
        await self.send_heartbeat()

        end_time = time.time() + duration_seconds

        while time.time() < end_time:
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=5)
                yield self.parse_message(raw)
            except asyncio.TimeoutError:
                await self.send_heartbeat()

        await self.logout()
