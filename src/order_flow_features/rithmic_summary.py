from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_jsonl_events(paths: list[Path]) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    skipped = 0

    for path in paths:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue

                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    skipped += 1
                    continue

                event["_source_file"] = str(path)
                events.append(event)

    return events, skipped


def find_rithmic_jsonl_files(
    input_dir: str | Path,
    symbol: str | None = None,
    latest_only: bool = True,
) -> list[Path]:
    root = Path(input_dir)

    if not root.exists():
        return []

    pattern = f"{symbol}_*_market_data.jsonl" if symbol else "*_market_data.jsonl"
    files = sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime)

    if latest_only and files:
        return [files[-1]]

    return files


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

    return 0.0


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


def build_rithmic_orderflow_summary(
    events: list[dict[str, Any]],
    *,
    symbol: str | None = None,
    exchange: str | None = None,
    tick_size: float = 0.1,
    bucket_seconds: int = 60,
    top_levels: int = 20,
) -> dict[str, Any]:
    login_events = [e for e in events if e.get("event_type") == "login_response"]
    market_data_events = [e for e in events if e.get("event_type") == "market_data_response"]
    last_trades = [e for e in events if e.get("event_type") == "last_trade"]
    bbo_events = [e for e in events if e.get("event_type") == "best_bid_offer"]

    resolved_symbol = symbol
    resolved_exchange = exchange

    if not resolved_symbol:
        for e in last_trades + bbo_events:
            if e.get("symbol"):
                resolved_symbol = e.get("symbol")
                break

    if not resolved_exchange:
        for e in last_trades + bbo_events:
            if e.get("exchange"):
                resolved_exchange = e.get("exchange")
                break

    login_ok = any(bool(e.get("ok")) for e in login_events)
    market_data_ok = any((e.get("rp_code") or [""])[0] == "0" for e in market_data_events)

    buy_volume = 0
    sell_volume = 0
    total_volume = 0
    trade_count = 0
    cumulative_delta = 0

    first_trade_price = None
    last_trade_price = None
    high_trade_price = None
    low_trade_price = None

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

    for event in last_trades:
        price = _safe_float(event.get("trade_price"))
        size = _safe_int(event.get("trade_size"))
        aggressor = str(event.get("aggressor") or "").upper()
        epoch = _event_epoch(event)

        if price <= 0 or size <= 0:
            continue

        price_level = _round_to_tick(price, tick_size)

        if first_trade_price is None:
            first_trade_price = price

        last_trade_price = price
        high_trade_price = price if high_trade_price is None else max(high_trade_price, price)
        low_trade_price = price if low_trade_price is None else min(low_trade_price, price)

        is_buy = aggressor == "BUY"
        is_sell = aggressor == "SELL"

        if is_buy:
            buy_volume += size
            cumulative_delta += size
        elif is_sell:
            sell_volume += size
            cumulative_delta -= size
        else:
            # Unknown aggressor side is counted in total volume, but not delta.
            pass

        total_volume += size
        trade_count += 1

        level = volume_at_price_map[price_level]
        level["price"] = price_level
        level["trade_count"] += 1
        level["total_volume"] += size

        if is_buy:
            level["buy_volume"] += size
            level["delta"] += size
        elif is_sell:
            level["sell_volume"] += size
            level["delta"] -= size

        if epoch > 0 and bucket_seconds > 0:
            bucket_start = int(epoch // bucket_seconds) * bucket_seconds
        else:
            bucket_start = 0

        bucket = footprint_buckets.setdefault(
            bucket_start,
            {
                "bucket_start_epoch": bucket_start,
                "bucket_end_epoch": bucket_start + bucket_seconds if bucket_start else 0,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
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

        bucket["high"] = max(bucket["high"], price)
        bucket["low"] = min(bucket["low"], price)
        bucket["close"] = price
        bucket["trade_count"] += 1
        bucket["total_volume"] += size

        if is_buy:
            bucket["buy_volume"] += size
            bucket["delta"] += size
        elif is_sell:
            bucket["sell_volume"] += size
            bucket["delta"] -= size

        b_level = bucket["_vap"][price_level]
        b_level["price"] = price_level
        b_level["trade_count"] += 1
        b_level["total_volume"] += size

        if is_buy:
            b_level["buy_volume"] += size
            b_level["delta"] += size
        elif is_sell:
            b_level["sell_volume"] += size
            b_level["delta"] -= size

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
        bucket["top_volume_at_price"] = bucket_vap[:top_levels]

        del bucket["_vap"]
        footprint_candles.append(bucket)

    nonzero_bbo_events = [
        e for e in bbo_events
        if _safe_float(e.get("bid_price")) > 0 and _safe_float(e.get("ask_price")) > 0
    ]

    last_bbo = bbo_events[-1] if bbo_events else {}
    last_bid = _safe_float(last_bbo.get("bid_price"))
    last_ask = _safe_float(last_bbo.get("ask_price"))

    spread = None
    if last_bid > 0 and last_ask > 0:
        spread = round(last_ask - last_bid, 10)

    imbalance_ratio = None
    if total_volume > 0:
        imbalance_ratio = round((buy_volume - sell_volume) / total_volume, 6)

    system_name = os.getenv("RITHMIC_SYSTEM_NAME", "")
    is_test_environment = "test" in system_name.lower()

    warnings = []

    if is_test_environment:
        warnings.append("RITHMIC_TEST_ENVIRONMENT_PRICES_MAY_BE_SIMULATED_OR_STALE")

    if trade_count < 20:
        warnings.append("LOW_SAMPLE_SIZE_OBSERVE_ONLY")

    if not nonzero_bbo_events:
        warnings.append("NO_NONZERO_BBO_OBSERVED")

    quality_status = "OBSERVE_ONLY_READY"
    if not login_ok:
        quality_status = "LOGIN_NOT_OK"
    elif not market_data_ok:
        quality_status = "MARKET_DATA_SUBSCRIPTION_NOT_OK"
    elif trade_count == 0:
        quality_status = "NO_TRADES_OBSERVED"
    elif trade_count < 20:
        quality_status = "LOW_SAMPLE_OBSERVATION_ONLY"

    return {
        "phase": "PHASE_5B_RITHMIC_ORDERFLOW_SUMMARY",
        "source": "RITHMIC_R_PROTOCOL",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "symbol": resolved_symbol,
        "exchange": resolved_exchange,
        "system_name": system_name or None,
        "is_test_environment": is_test_environment,
        "sample": {
            "event_count": len(events),
            "login_event_count": len(login_events),
            "market_data_response_count": len(market_data_events),
            "last_trade_count": trade_count,
            "bbo_count": len(bbo_events),
            "nonzero_bbo_count": len(nonzero_bbo_events),
            "bucket_seconds": bucket_seconds,
            "tick_size": tick_size,
        },
        "quality": {
            "login_ok": login_ok,
            "market_data_ok": market_data_ok,
            "has_last_trades": trade_count > 0,
            "has_nonzero_bbo": len(nonzero_bbo_events) > 0,
            "quality_status": quality_status,
            "warnings": warnings,
        },
        "trade_flow": {
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "total_volume": total_volume,
            "delta": buy_volume - sell_volume,
            "cumulative_delta": cumulative_delta,
            "imbalance_ratio": imbalance_ratio,
            "first_trade_price": first_trade_price,
            "last_trade_price": last_trade_price,
            "high_trade_price": high_trade_price,
            "low_trade_price": low_trade_price,
        },
        "bbo": {
            "last_bid": last_bid if last_bid > 0 else None,
            "last_ask": last_ask if last_ask > 0 else None,
            "last_spread": spread,
        },
        "volume_profile": {
            "poc_price": poc_price,
            "poc_volume": poc_volume,
            "top_volume_at_price": volume_at_price[:top_levels],
        },
        "footprint": {
            "candle_count": len(footprint_candles),
            "candles": footprint_candles,
        },
    }


def write_summary_text(summary: dict[str, Any], output_path: str | Path) -> None:
    lines = [
        "PHASE 5B RITHMIC ORDER-FLOW SUMMARY",
        "====================================",
        f"source: {summary.get('source')}",
        f"symbol: {summary.get('symbol')}",
        f"exchange: {summary.get('exchange')}",
        f"system_name: {summary.get('system_name')}",
        f"is_test_environment: {summary.get('is_test_environment')}",
        f"decision_impact: {summary.get('decision_impact')}",
        f"can_influence_decision: {summary.get('can_influence_decision')}",
        "",
        "[QUALITY]",
        f"quality_status: {summary['quality']['quality_status']}",
        f"login_ok: {summary['quality']['login_ok']}",
        f"market_data_ok: {summary['quality']['market_data_ok']}",
        f"has_last_trades: {summary['quality']['has_last_trades']}",
        f"has_nonzero_bbo: {summary['quality']['has_nonzero_bbo']}",
        f"warnings: {', '.join(summary['quality']['warnings']) if summary['quality']['warnings'] else 'NONE'}",
        "",
        "[TRADE FLOW]",
        f"last_trade_count: {summary['sample']['last_trade_count']}",
        f"buy_volume: {summary['trade_flow']['buy_volume']}",
        f"sell_volume: {summary['trade_flow']['sell_volume']}",
        f"total_volume: {summary['trade_flow']['total_volume']}",
        f"delta: {summary['trade_flow']['delta']}",
        f"cumulative_delta: {summary['trade_flow']['cumulative_delta']}",
        f"imbalance_ratio: {summary['trade_flow']['imbalance_ratio']}",
        f"first_trade_price: {summary['trade_flow']['first_trade_price']}",
        f"last_trade_price: {summary['trade_flow']['last_trade_price']}",
        "",
        "[VOLUME PROFILE]",
        f"poc_price: {summary['volume_profile']['poc_price']}",
        f"poc_volume: {summary['volume_profile']['poc_volume']}",
        "",
        "[FOOTPRINT]",
        f"candle_count: {summary['footprint']['candle_count']}",
        "",
        "NOTE:",
        "This is real Rithmic R | Protocol market-data parsing, but it is observe-only.",
        "It must not influence MT5 live execution yet.",
    ]

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
