from __future__ import annotations

import json
import math
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TradeRecord:
    received_at_epoch: float
    symbol: str
    exchange: str
    price: float
    size: int
    aggressor: str


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return default
        return value
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _round_to_tick(price: float, tick_size: float) -> float:
    if tick_size <= 0:
        return float(price)
    return round(round(price / tick_size) * tick_size, 10)


def _event_epoch(event: dict[str, Any]) -> float:
    received = event.get("received_at_epoch")
    if isinstance(received, (int, float)) and received > 0:
        return float(received)

    ssboe = event.get("ssboe")
    usecs = event.get("usecs") or 0

    if isinstance(ssboe, int) and ssboe > 0:
        return float(ssboe) + (float(usecs) / 1_000_000.0)

    return time.time()


class RithmicRollingStateCache:
    """
    Real-time rolling Rithmic order-flow state cache.

    This is observe-only:
    - no order execution
    - no live MT5 decision influence
    - DOM metrics are placeholders until Phase 5D market-depth subscription
    """

    def __init__(
        self,
        *,
        symbol: str,
        exchange: str,
        tick_size: float = 0.1,
        rolling_window_seconds: int = 300,
        bucket_seconds: int = 60,
        stale_after_seconds: int = 15,
        top_levels: int = 20,
    ) -> None:
        self.symbol = symbol
        self.exchange = exchange
        self.tick_size = tick_size
        self.rolling_window_seconds = rolling_window_seconds
        self.bucket_seconds = bucket_seconds
        self.stale_after_seconds = stale_after_seconds
        self.top_levels = top_levels

        self.started_at_epoch = time.time()
        self.updated_at_epoch: float | None = None

        self.login_ok = False
        self.market_data_ok = False

        self.login_event_count = 0
        self.market_data_response_count = 0
        self.bbo_count = 0
        self.nonzero_bbo_count = 0
        self.last_trade_count = 0

        self.last_bid: float | None = None
        self.last_ask: float | None = None
        self.last_bid_size: int | None = None
        self.last_ask_size: int | None = None
        self.last_bbo_received_at_epoch: float | None = None

        self.last_trade_price: float | None = None
        self.last_trade_size: int | None = None
        self.last_trade_aggressor: str | None = None
        self.last_trade_received_at_epoch: float | None = None

        self.total_buy_volume = 0
        self.total_sell_volume = 0
        self.total_cumulative_delta = 0

        self.trades: deque[TradeRecord] = deque()

    def update(self, event: dict[str, Any]) -> dict[str, Any]:
        now_epoch = time.time()
        self.updated_at_epoch = now_epoch

        event_type = event.get("event_type")

        if event_type == "login_response":
            self.login_event_count += 1
            self.login_ok = bool(event.get("ok"))

        elif event_type == "market_data_response":
            self.market_data_response_count += 1
            rp_code = event.get("rp_code") or []
            self.market_data_ok = bool(rp_code and rp_code[0] == "0")

        elif event_type == "best_bid_offer":
            self._update_bbo(event)

        elif event_type == "last_trade":
            self._update_last_trade(event)

        self._prune_old_trades(now_epoch)
        return self.snapshot(now_epoch=now_epoch)

    def _update_bbo(self, event: dict[str, Any]) -> None:
        self.bbo_count += 1

        bid = _safe_float(event.get("bid_price"))
        ask = _safe_float(event.get("ask_price"))
        bid_size = _safe_int(event.get("bid_size"))
        ask_size = _safe_int(event.get("ask_size"))

        self.last_bbo_received_at_epoch = _event_epoch(event)

        if bid > 0:
            self.last_bid = bid
        if ask > 0:
            self.last_ask = ask

        self.last_bid_size = bid_size
        self.last_ask_size = ask_size

        if bid > 0 and ask > 0:
            self.nonzero_bbo_count += 1

    def _update_last_trade(self, event: dict[str, Any]) -> None:
        price = _safe_float(event.get("trade_price"))
        size = _safe_int(event.get("trade_size"))
        aggressor = str(event.get("aggressor") or "").upper()
        received_at_epoch = _event_epoch(event)

        if price <= 0 or size <= 0:
            return

        if aggressor not in {"BUY", "SELL"}:
            aggressor = "UNKNOWN"

        record = TradeRecord(
            received_at_epoch=received_at_epoch,
            symbol=str(event.get("symbol") or self.symbol),
            exchange=str(event.get("exchange") or self.exchange),
            price=price,
            size=size,
            aggressor=aggressor,
        )

        self.trades.append(record)

        self.last_trade_count += 1
        self.last_trade_price = price
        self.last_trade_size = size
        self.last_trade_aggressor = aggressor
        self.last_trade_received_at_epoch = received_at_epoch

        if aggressor == "BUY":
            self.total_buy_volume += size
            self.total_cumulative_delta += size
        elif aggressor == "SELL":
            self.total_sell_volume += size
            self.total_cumulative_delta -= size

    def _prune_old_trades(self, now_epoch: float) -> None:
        cutoff = now_epoch - self.rolling_window_seconds

        while self.trades and self.trades[0].received_at_epoch < cutoff:
            self.trades.popleft()

    def _rolling_trade_flow(self) -> dict[str, Any]:
        buy_volume = 0
        sell_volume = 0
        total_volume = 0
        trade_count = 0

        first_price = None
        last_price = None
        high_price = None
        low_price = None

        volume_at_price_map: dict[float, dict[str, Any]] = defaultdict(
            lambda: {
                "price": 0.0,
                "buy_volume": 0,
                "sell_volume": 0,
                "total_volume": 0,
                "delta": 0,
                "trade_count": 0,
            }
        )

        footprint_buckets: dict[int, dict[str, Any]] = {}

        for trade in self.trades:
            price_level = _round_to_tick(trade.price, self.tick_size)

            if first_price is None:
                first_price = trade.price

            last_price = trade.price
            high_price = trade.price if high_price is None else max(high_price, trade.price)
            low_price = trade.price if low_price is None else min(low_price, trade.price)

            total_volume += trade.size
            trade_count += 1

            is_buy = trade.aggressor == "BUY"
            is_sell = trade.aggressor == "SELL"

            if is_buy:
                buy_volume += trade.size
            elif is_sell:
                sell_volume += trade.size

            level = volume_at_price_map[price_level]
            level["price"] = price_level
            level["trade_count"] += 1
            level["total_volume"] += trade.size

            if is_buy:
                level["buy_volume"] += trade.size
                level["delta"] += trade.size
            elif is_sell:
                level["sell_volume"] += trade.size
                level["delta"] -= trade.size

            if self.bucket_seconds > 0:
                bucket_start = int(trade.received_at_epoch // self.bucket_seconds) * self.bucket_seconds
            else:
                bucket_start = 0

            bucket = footprint_buckets.setdefault(
                bucket_start,
                {
                    "bucket_start_epoch": bucket_start,
                    "bucket_end_epoch": bucket_start + self.bucket_seconds if bucket_start else 0,
                    "open": trade.price,
                    "high": trade.price,
                    "low": trade.price,
                    "close": trade.price,
                    "buy_volume": 0,
                    "sell_volume": 0,
                    "total_volume": 0,
                    "delta": 0,
                    "trade_count": 0,
                    "_vap": defaultdict(
                        lambda: {
                            "price": 0.0,
                            "buy_volume": 0,
                            "sell_volume": 0,
                            "total_volume": 0,
                            "delta": 0,
                            "trade_count": 0,
                        }
                    ),
                },
            )

            bucket["high"] = max(bucket["high"], trade.price)
            bucket["low"] = min(bucket["low"], trade.price)
            bucket["close"] = trade.price
            bucket["trade_count"] += 1
            bucket["total_volume"] += trade.size

            if is_buy:
                bucket["buy_volume"] += trade.size
                bucket["delta"] += trade.size
            elif is_sell:
                bucket["sell_volume"] += trade.size
                bucket["delta"] -= trade.size

            b_level = bucket["_vap"][price_level]
            b_level["price"] = price_level
            b_level["trade_count"] += 1
            b_level["total_volume"] += trade.size

            if is_buy:
                b_level["buy_volume"] += trade.size
                b_level["delta"] += trade.size
            elif is_sell:
                b_level["sell_volume"] += trade.size
                b_level["delta"] -= trade.size

        delta = buy_volume - sell_volume
        imbalance_ratio = round(delta / total_volume, 6) if total_volume > 0 else None

        volume_at_price = sorted(
            volume_at_price_map.values(),
            key=lambda row: (-row["total_volume"], row["price"]),
        )

        poc_price = volume_at_price[0]["price"] if volume_at_price else None
        poc_volume = volume_at_price[0]["total_volume"] if volume_at_price else 0

        footprint_candles = []
        for bucket_start in sorted(footprint_buckets):
            bucket = footprint_buckets[bucket_start]

            bucket_vap = sorted(
                bucket["_vap"].values(),
                key=lambda row: (-row["total_volume"], row["price"]),
            )

            bucket["poc_price"] = bucket_vap[0]["price"] if bucket_vap else None
            bucket["poc_volume"] = bucket_vap[0]["total_volume"] if bucket_vap else 0
            bucket["top_volume_at_price"] = bucket_vap[: self.top_levels]

            del bucket["_vap"]
            footprint_candles.append(bucket)

        return {
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "total_volume": total_volume,
            "delta": delta,
            "cumulative_delta": self.total_cumulative_delta,
            "imbalance_ratio": imbalance_ratio,
            "trade_count": trade_count,
            "first_trade_price": first_price,
            "last_trade_price": last_price,
            "high_trade_price": high_price,
            "low_trade_price": low_price,
            "poc_price": poc_price,
            "poc_volume": poc_volume,
            "top_volume_at_price": volume_at_price[: self.top_levels],
            "footprint_candles": footprint_candles,
        }

    def snapshot(self, *, now_epoch: float | None = None) -> dict[str, Any]:
        now_epoch = now_epoch or time.time()
        flow = self._rolling_trade_flow()

        last_trade_age_seconds = None
        if self.last_trade_received_at_epoch:
            last_trade_age_seconds = max(0.0, round(now_epoch - self.last_trade_received_at_epoch, 3))

        last_bbo_age_seconds = None
        if self.last_bbo_received_at_epoch:
            last_bbo_age_seconds = max(0.0, round(now_epoch - self.last_bbo_received_at_epoch, 3))

        has_fresh_trade = (
            last_trade_age_seconds is not None
            and last_trade_age_seconds <= self.stale_after_seconds
        )

        has_fresh_bbo = (
            last_bbo_age_seconds is not None
            and last_bbo_age_seconds <= self.stale_after_seconds
        )

        spread = None
        if self.last_bid and self.last_ask:
            spread = round(self.last_ask - self.last_bid, 10)

        warnings = []

        system_name = os.getenv("RITHMIC_SYSTEM_NAME", "")
        is_test_environment = "test" in system_name.lower()

        if is_test_environment:
            warnings.append("RITHMIC_TEST_ENVIRONMENT_PRICES_MAY_BE_SIMULATED_OR_STALE")

        if flow["trade_count"] < 20:
            warnings.append("LOW_ROLLING_SAMPLE_OBSERVATION_ONLY")

        if self.nonzero_bbo_count == 0:
            warnings.append("NO_NONZERO_BBO_OBSERVED")

        warnings.append("DOM_NOT_SUBSCRIBED_YET_PHASE5D_REQUIRED")
        warnings.append("DECISION_IMPACT_DISABLED")

        if not self.login_ok:
            state_status = "LOGIN_NOT_OK"
        elif not self.market_data_ok:
            state_status = "MARKET_DATA_NOT_OK"
        elif flow["trade_count"] == 0:
            state_status = "NO_RECENT_TRADES"
        elif not has_fresh_trade:
            state_status = "STALE_TRADES_OBSERVATION_ONLY"
        elif flow["trade_count"] < 20:
            state_status = "LOW_SAMPLE_OBSERVATION_ONLY"
        else:
            state_status = "OBSERVE_ONLY_READY"

        # In futures tape reading:
        # BUY aggressor volume is ask-lifted volume.
        # SELL aggressor volume is bid-hit volume.
        ask_volume = flow["buy_volume"]
        bid_volume = flow["sell_volume"]

        footprint_imbalance = flow["imbalance_ratio"]
        if footprint_imbalance is None:
            footprint_imbalance = 0.0

        return {
            "phase": "PHASE_5C_RITHMIC_REALTIME_STATE_CACHE",
            "source": "RITHMIC_R_PROTOCOL",
            "provider_name": "RITHMIC_PROTOCOL",
            "symbol": self.symbol,
            "exchange": self.exchange,
            "system_name": system_name or None,
            "is_test_environment": is_test_environment,
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "state_status": state_status,
            "started_at_epoch": self.started_at_epoch,
            "updated_at_epoch": self.updated_at_epoch,
            "rolling_window_seconds": self.rolling_window_seconds,
            "bucket_seconds": self.bucket_seconds,
            "tick_size": self.tick_size,
            "freshness": {
                "stale_after_seconds": self.stale_after_seconds,
                "last_trade_age_seconds": last_trade_age_seconds,
                "last_bbo_age_seconds": last_bbo_age_seconds,
                "has_fresh_trade": has_fresh_trade,
                "has_fresh_bbo": has_fresh_bbo,
            },
            "connection": {
                "login_ok": self.login_ok,
                "market_data_ok": self.market_data_ok,
                "login_event_count": self.login_event_count,
                "market_data_response_count": self.market_data_response_count,
            },
            "sample": {
                "last_trade_count_total_session": self.last_trade_count,
                "rolling_trade_count": flow["trade_count"],
                "bbo_count": self.bbo_count,
                "nonzero_bbo_count": self.nonzero_bbo_count,
            },
            "latest_trade": {
                "price": self.last_trade_price,
                "size": self.last_trade_size,
                "aggressor": self.last_trade_aggressor,
                "received_at_epoch": self.last_trade_received_at_epoch,
            },
            "bbo": {
                "last_bid": self.last_bid,
                "last_ask": self.last_ask,
                "last_bid_size": self.last_bid_size,
                "last_ask_size": self.last_ask_size,
                "last_spread": spread,
            },
            "trade_flow": {
                "rolling_buy_volume": flow["buy_volume"],
                "rolling_sell_volume": flow["sell_volume"],
                "rolling_total_volume": flow["total_volume"],
                "rolling_delta": flow["delta"],
                "session_cumulative_delta": self.total_cumulative_delta,
                "rolling_imbalance_ratio": flow["imbalance_ratio"],
                "first_trade_price": flow["first_trade_price"],
                "last_trade_price": flow["last_trade_price"],
                "high_trade_price": flow["high_trade_price"],
                "low_trade_price": flow["low_trade_price"],
            },
            "volume_profile": {
                "rolling_poc_price": flow["poc_price"],
                "rolling_poc_volume": flow["poc_volume"],
                "top_volume_at_price": flow["top_volume_at_price"],
            },
            "footprint": {
                "candle_count": len(flow["footprint_candles"]),
                "candles": flow["footprint_candles"],
            },
            "adapter_compatible_metrics": {
                "bid_volume": bid_volume,
                "ask_volume": ask_volume,
                "delta": flow["delta"],
                "cumulative_delta": self.total_cumulative_delta,
                "footprint_imbalance": footprint_imbalance,
                "dom_bid_depth": 0,
                "dom_ask_depth": 0,
                "dom_available": False,
            },
            "quality": {
                "warnings": warnings,
                "safe_for_live_decision": False,
                "safe_for_execution": False,
                "reason": "Observe-only Phase 5C cache. DOM and validation not complete.",
            },
        }


def write_state_text(snapshot: dict[str, Any], output_path: str | Path) -> None:
    lines = [
        "PHASE 5C RITHMIC REAL-TIME STATE CACHE",
        "======================================",
        f"symbol: {snapshot.get('symbol')}",
        f"exchange: {snapshot.get('exchange')}",
        f"system_name: {snapshot.get('system_name')}",
        f"is_test_environment: {snapshot.get('is_test_environment')}",
        f"state_status: {snapshot.get('state_status')}",
        f"decision_impact: {snapshot.get('decision_impact')}",
        f"can_influence_decision: {snapshot.get('can_influence_decision')}",
        "",
        "[CONNECTION]",
        f"login_ok: {snapshot['connection']['login_ok']}",
        f"market_data_ok: {snapshot['connection']['market_data_ok']}",
        "",
        "[FRESHNESS]",
        f"last_trade_age_seconds: {snapshot['freshness']['last_trade_age_seconds']}",
        f"last_bbo_age_seconds: {snapshot['freshness']['last_bbo_age_seconds']}",
        f"has_fresh_trade: {snapshot['freshness']['has_fresh_trade']}",
        f"has_fresh_bbo: {snapshot['freshness']['has_fresh_bbo']}",
        "",
        "[LATEST TRADE]",
        f"price: {snapshot['latest_trade']['price']}",
        f"size: {snapshot['latest_trade']['size']}",
        f"aggressor: {snapshot['latest_trade']['aggressor']}",
        "",
        "[TRADE FLOW]",
        f"rolling_trade_count: {snapshot['sample']['rolling_trade_count']}",
        f"rolling_buy_volume: {snapshot['trade_flow']['rolling_buy_volume']}",
        f"rolling_sell_volume: {snapshot['trade_flow']['rolling_sell_volume']}",
        f"rolling_total_volume: {snapshot['trade_flow']['rolling_total_volume']}",
        f"rolling_delta: {snapshot['trade_flow']['rolling_delta']}",
        f"session_cumulative_delta: {snapshot['trade_flow']['session_cumulative_delta']}",
        f"rolling_imbalance_ratio: {snapshot['trade_flow']['rolling_imbalance_ratio']}",
        "",
        "[VOLUME PROFILE]",
        f"rolling_poc_price: {snapshot['volume_profile']['rolling_poc_price']}",
        f"rolling_poc_volume: {snapshot['volume_profile']['rolling_poc_volume']}",
        "",
        "[FOOTPRINT]",
        f"candle_count: {snapshot['footprint']['candle_count']}",
        "",
        "[ADAPTER-COMPATIBLE METRICS]",
        f"bid_volume: {snapshot['adapter_compatible_metrics']['bid_volume']}",
        f"ask_volume: {snapshot['adapter_compatible_metrics']['ask_volume']}",
        f"delta: {snapshot['adapter_compatible_metrics']['delta']}",
        f"cumulative_delta: {snapshot['adapter_compatible_metrics']['cumulative_delta']}",
        f"footprint_imbalance: {snapshot['adapter_compatible_metrics']['footprint_imbalance']}",
        f"dom_bid_depth: {snapshot['adapter_compatible_metrics']['dom_bid_depth']}",
        f"dom_ask_depth: {snapshot['adapter_compatible_metrics']['dom_ask_depth']}",
        f"dom_available: {snapshot['adapter_compatible_metrics']['dom_available']}",
        "",
        "[WARNINGS]",
        ", ".join(snapshot["quality"]["warnings"]),
        "",
        "NOTE:",
        "This cache is observe-only and cannot influence MT5 execution yet.",
    ]

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_state_json(snapshot: dict[str, Any], output_path: str | Path) -> None:
    Path(output_path).write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
