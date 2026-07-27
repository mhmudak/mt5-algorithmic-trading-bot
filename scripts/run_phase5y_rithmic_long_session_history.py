from __future__ import annotations

import argparse
import asyncio
import json
import inspect
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from src.order_flow_features.rithmic_state_cache import RithmicRollingStateCache
from src.order_flow_providers.rithmic_protocol import RithmicConfig, RithmicMarketDataClient


PHASE = "PHASE_5Y_RITHMIC_LONG_SESSION_HISTORY"

ORDER_FLOW_DIR = ROOT / "data" / "order_flow" / "rithmic"
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

OUT_JSON = ORDER_FLOW_DIR / "phase5y_rithmic_long_session_history_report.json"
OUT_TXT = ORDER_FLOW_DIR / "phase5y_rithmic_long_session_history_summary.txt"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def get_nested(d: dict[str, Any], path: list[str], default: Any = None) -> Any:
    cur: Any = d

    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)

    return cur if cur is not None else default


def deep_find(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]

        for value in obj.values():
            found = deep_find(value, key)
            if found is not None:
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = deep_find(item, key)
            if found is not None:
                return found

    return None


def first_number(*values: Any, default: float = 0.0) -> float:
    for value in values:
        parsed = as_float(value, default=0.0)
        if parsed != 0.0:
            return parsed

    return default


def snapshot_metrics(snapshot: dict[str, Any]) -> dict[str, Any]:
    latest_bbo = snapshot.get("latest_bbo") or {}
    order_book = snapshot.get("order_book") or {}
    latest_trade = snapshot.get("latest_trade") or {}
    trade_flow = snapshot.get("trade_flow") or {}
    adapter = snapshot.get("adapter_compatible_metrics") or {}

    top_bid_price = first_number(
        order_book.get("top_bid_price"),
        adapter.get("top_bid_price"),
        deep_find(snapshot, "top_bid_price"),
    )
    top_ask_price = first_number(
        order_book.get("top_ask_price"),
        adapter.get("top_ask_price"),
        deep_find(snapshot, "top_ask_price"),
    )

    bid = first_number(
        latest_bbo.get("last_bid"),
        latest_bbo.get("bid"),
        latest_bbo.get("bid_price"),
        deep_find(snapshot, "last_bid"),
        deep_find(snapshot, "bid_price"),
        top_bid_price,
    )
    ask = first_number(
        latest_bbo.get("last_ask"),
        latest_bbo.get("ask"),
        latest_bbo.get("ask_price"),
        deep_find(snapshot, "last_ask"),
        deep_find(snapshot, "ask_price"),
        top_ask_price,
    )

    spread = None
    if bid > 0 and ask > 0:
        spread = round(ask - bid, 10)

    bid_depth = first_number(
        order_book.get("bid_depth"),
        adapter.get("dom_bid_depth"),
        deep_find(snapshot, "dom_bid_depth"),
        deep_find(snapshot, "bid_depth"),
    )
    ask_depth = first_number(
        order_book.get("ask_depth"),
        adapter.get("dom_ask_depth"),
        deep_find(snapshot, "dom_ask_depth"),
        deep_find(snapshot, "ask_depth"),
    )

    rolling_trade_count = first_number(
        snapshot.get("rolling_trade_count"),
        trade_flow.get("trade_count"),
        trade_flow.get("rolling_trade_count"),
        trade_flow.get("rolling_total_volume"),
        deep_find(snapshot, "rolling_trade_count"),
        deep_find(snapshot, "trade_count"),
        default=0.0,
    )

    rolling_delta = first_number(
        snapshot.get("rolling_delta"),
        trade_flow.get("delta"),
        adapter.get("delta"),
        deep_find(snapshot, "rolling_delta"),
        deep_find(snapshot, "delta"),
        default=0.0,
    )

    session_cumulative_delta = first_number(
        snapshot.get("session_cumulative_delta"),
        adapter.get("cumulative_delta"),
        deep_find(snapshot, "session_cumulative_delta"),
        deep_find(snapshot, "cumulative_delta"),
        default=0.0,
    )

    rolling_poc_price = first_number(
        snapshot.get("rolling_poc_price"),
        deep_find(snapshot, "rolling_poc_price"),
        deep_find(snapshot, "poc"),
        default=0.0,
    )

    latest_trade_price = first_number(
        latest_trade.get("price"),
        latest_trade.get("trade_price"),
        deep_find(snapshot, "trade_price"),
        default=0.0,
    )

    latest_trade_size = first_number(
        latest_trade.get("size"),
        latest_trade.get("trade_size"),
        deep_find(snapshot, "trade_size"),
        default=0.0,
    )

    bbo_source = "BBO"
    if (not latest_bbo or as_float(latest_bbo.get("last_bid")) <= 0 or as_float(latest_bbo.get("last_ask")) <= 0) and top_bid_price > 0 and top_ask_price > 0:
        bbo_source = "DOM_TOP_OF_BOOK_FALLBACK"

    return {
        "state_status": snapshot.get("state_status"),
        "rolling_trade_count": rolling_trade_count,
        "rolling_delta": rolling_delta,
        "session_cumulative_delta": session_cumulative_delta,
        "rolling_poc_price": rolling_poc_price,
        "latest_trade_price": latest_trade_price,
        "latest_trade_size": latest_trade_size,
        "bid": bid,
        "ask": ask,
        "spread": spread,
        "bbo_source": bbo_source,
        "dom_available": bool(order_book.get("available") or adapter.get("dom_available") or (bid_depth > 0 or ask_depth > 0)),
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
        "depth_imbalance": order_book.get("depth_imbalance") or adapter.get("dom_depth_imbalance") or deep_find(snapshot, "dom_depth_imbalance"),
        "top_bid_price": top_bid_price,
        "top_ask_price": top_ask_price,
        "bid_level_count": order_book.get("bid_level_count") or len(order_book.get("bid_levels") or []),
        "ask_level_count": order_book.get("ask_level_count") or len(order_book.get("ask_levels") or []),
    }


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "sample_count": 0,
            "quality_ready": False,
            "reason": "NO_RECORDS",
        }

    metrics = [r.get("metrics") or {} for r in records]

    spreads = [as_float(m.get("spread")) for m in metrics if as_float(m.get("spread")) > 0]
    trade_counts = [as_float(m.get("rolling_trade_count")) for m in metrics]
    bid_depths = [as_float(m.get("bid_depth")) for m in metrics]
    ask_depths = [as_float(m.get("ask_depth")) for m in metrics]

    dom_two_sided = [
        m for m in metrics
        if as_float(m.get("bid_depth")) > 0 and as_float(m.get("ask_depth")) > 0
    ]

    positive_bbo = [
        m for m in metrics
        if as_float(m.get("bid")) > 0 and as_float(m.get("ask")) > 0
    ]

    return {
        "sample_count": len(records),
        "positive_bbo_rate": round(len(positive_bbo) / len(records), 4),
        "two_sided_dom_rate": round(len(dom_two_sided) / len(records), 4),
        "avg_spread": round(sum(spreads) / len(spreads), 6) if spreads else None,
        "max_spread": max(spreads) if spreads else None,
        "avg_rolling_trade_count": round(sum(trade_counts) / len(trade_counts), 4) if trade_counts else 0,
        "max_rolling_trade_count": max(trade_counts) if trade_counts else 0,
        "avg_bid_depth": round(sum(bid_depths) / len(bid_depths), 4) if bid_depths else 0,
        "avg_ask_depth": round(sum(ask_depths) / len(ask_depths), 4) if ask_depths else 0,
        "quality_ready": bool(
            len(records) >= 10
            and len(positive_bbo) / len(records) >= 0.8
            and len(dom_two_sided) / len(records) >= 0.8
            and (max(spreads) if spreads else 999) <= 1
        ),
    }



def build_rithmic_config(*, symbol: str, exchange: str) -> RithmicConfig:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")

    env_values = {
        "ws_url": os.getenv("RITHMIC_WS_URL"),
        "url": os.getenv("RITHMIC_WS_URL"),
        "websocket_url": os.getenv("RITHMIC_WS_URL"),
        "system_name": os.getenv("RITHMIC_SYSTEM_NAME"),
        "system": os.getenv("RITHMIC_SYSTEM_NAME"),
        "username": os.getenv("RITHMIC_USERNAME"),
        "user": os.getenv("RITHMIC_USERNAME"),
        "password": os.getenv("RITHMIC_PASSWORD"),
        "exchange": exchange,
        "symbol": symbol,
        "sdk_path": os.getenv("RITHMIC_SDK_PATH"),
        "rithmic_sdk_path": os.getenv("RITHMIC_SDK_PATH"),
    }

    signature = inspect.signature(RithmicConfig)
    kwargs = {}

    for name, parameter in signature.parameters.items():
        if name == "self":
            continue

        if name in env_values and env_values[name] is not None:
            kwargs[name] = env_values[name]

    try:
        return RithmicConfig(**kwargs)
    except TypeError as exc:
        raise TypeError(
            "Could not build RithmicConfig from .env. "
            f"Constructor parameters={list(signature.parameters.keys())}, "
            f"provided={sorted(kwargs.keys())}"
        ) from exc


async def collect_symbol(
    *,
    symbol: str,
    exchange: str,
    duration_seconds: int,
    snapshot_interval_seconds: int,
    include_order_book: bool,
) -> dict[str, Any]:
    started = datetime.now().isoformat(timespec="seconds")
    jsonl_path = ORDER_FLOW_DIR / f"{symbol}_phase5y_long_session_history.jsonl"

    # Fresh file per run.
    jsonl_path.write_text("", encoding="utf-8")

    config = build_rithmic_config(symbol=symbol, exchange=exchange)
    client = RithmicMarketDataClient(config)
    cache = RithmicRollingStateCache(symbol=symbol, exchange=exchange)

    records: list[dict[str, Any]] = []
    latest_snapshot: dict[str, Any] | None = None

    next_snapshot_at = time.time()
    end_time = time.time() + duration_seconds

    async for event in client.stream(duration_seconds=duration_seconds, include_order_book=include_order_book):
        latest_snapshot = cache.update(event)
        now = time.time()

        if now >= next_snapshot_at and latest_snapshot:
            metrics = snapshot_metrics(latest_snapshot)

            order_book = latest_snapshot.get("order_book") or {}
            trade_flow = latest_snapshot.get("trade_flow") or {}

            record = {
                "phase": PHASE,
                "recorded_at": datetime.now().isoformat(timespec="seconds"),
                "symbol": symbol,
                "exchange": exchange,
                "elapsed_seconds": round(duration_seconds - max(0, end_time - now), 3),
                "event_type": event.get("event_type"),
                "metrics": metrics,
                "top_bid_levels": list(order_book.get("bid_levels") or [])[:20],
                "top_ask_levels": list(order_book.get("ask_levels") or [])[:20],
                "trade_flow": {
                    "rolling_buy_volume": trade_flow.get("buy_volume"),
                    "rolling_sell_volume": trade_flow.get("sell_volume"),
                    "rolling_total_volume": trade_flow.get("total_volume"),
                    "rolling_delta": trade_flow.get("delta"),
                },
                "decision_impact": "NONE",
                "can_influence_decision": False,
                "trade_action": "NO_AUTO_TRADE",
            }

            append_jsonl(jsonl_path, record)
            records.append(record)
            next_snapshot_at = now + snapshot_interval_seconds

            print(
                f"[SNAPSHOT] {symbol} samples={len(records)} "
                f"trades={metrics.get('rolling_trade_count')} "
                f"spread={metrics.get('spread')} "
                f"dom={metrics.get('dom_available')} "
                f"bid_depth={metrics.get('bid_depth')} "
                f"ask_depth={metrics.get('ask_depth')}"
            )

    summary = summarize_records(records)

    latest_path = ORDER_FLOW_DIR / f"{symbol}_phase5y_long_session_latest.json"
    write_json(latest_path, {
        "phase": PHASE,
        "symbol": symbol,
        "exchange": exchange,
        "started_at": started,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "duration_seconds": duration_seconds,
        "snapshot_interval_seconds": snapshot_interval_seconds,
        "include_order_book": include_order_book,
        "jsonl_path": str(jsonl_path),
        "latest_snapshot": latest_snapshot,
        "summary": summary,
        "mode": "OBSERVE_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
    })

    return {
        "symbol": symbol,
        "exchange": exchange,
        "jsonl_path": str(jsonl_path),
        "latest_path": str(latest_path),
        "summary": summary,
    }


async def main_async() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="MGCQ6")
    parser.add_argument("--exchange", default="COMEX")
    parser.add_argument("--duration-seconds", type=int, default=600)
    parser.add_argument("--snapshot-interval-seconds", type=int, default=10)
    parser.add_argument("--include-order-book", action="store_true")
    args = parser.parse_args()

    ORDER_FLOW_DIR.mkdir(parents=True, exist_ok=True)
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    print("[PHASE 5Y RITHMIC LONG-SESSION HISTORY]")
    print(f"symbols = {','.join(symbols)}")
    print(f"exchange = {args.exchange}")
    print(f"duration_seconds = {args.duration_seconds}")
    print(f"snapshot_interval_seconds = {args.snapshot_interval_seconds}")
    print("mode = OBSERVE_ONLY")
    print("decision_impact = NONE")
    print("can_influence_decision = False")
    print("trade_action = NO_AUTO_TRADE")
    print("")

    results = []

    for symbol in symbols:
        result = await collect_symbol(
            symbol=symbol,
            exchange=args.exchange,
            duration_seconds=args.duration_seconds,
            snapshot_interval_seconds=args.snapshot_interval_seconds,
            include_order_book=args.include_order_book,
        )
        results.append(result)

    report = {
        "phase": PHASE,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "symbols": symbols,
        "exchange": args.exchange,
        "duration_seconds": args.duration_seconds,
        "snapshot_interval_seconds": args.snapshot_interval_seconds,
        "include_order_book": args.include_order_book,
        "mode": "OBSERVE_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
        "results": results,
        "recommendation": (
            "Use this history for long-session validation and later pulling/stacking, spoofing, iceberg suspicion, "
            "volume profile, footprint, and decision-grade acceptance. Still observe-only."
        ),
    }

    write_json(OUT_JSON, report)

    lines = [
        "[PHASE 5Y RITHMIC LONG-SESSION HISTORY]",
        f"updated_at = {report['updated_at']}",
        f"symbols = {','.join(symbols)}",
        f"exchange = {args.exchange}",
        f"duration_seconds = {args.duration_seconds}",
        f"snapshot_interval_seconds = {args.snapshot_interval_seconds}",
        f"mode = {report['mode']}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        f"trade_action = {report['trade_action']}",
        "",
        "[RESULTS]",
    ]

    for result in results:
        summary = result["summary"]
        lines += [
            f"- {result['symbol']}",
            f"  sample_count = {summary.get('sample_count')}",
            f"  positive_bbo_rate = {summary.get('positive_bbo_rate')}",
            f"  two_sided_dom_rate = {summary.get('two_sided_dom_rate')}",
            f"  avg_spread = {summary.get('avg_spread')}",
            f"  max_spread = {summary.get('max_spread')}",
            f"  avg_rolling_trade_count = {summary.get('avg_rolling_trade_count')}",
            f"  max_rolling_trade_count = {summary.get('max_rolling_trade_count')}",
            f"  avg_bid_depth = {summary.get('avg_bid_depth')}",
            f"  avg_ask_depth = {summary.get('avg_ask_depth')}",
            f"  quality_ready = {summary.get('quality_ready')}",
            f"  jsonl = {result['jsonl_path']}",
        ]

    lines += [
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
        "",
        f"json = {OUT_JSON}",
        f"summary = {OUT_TXT}",
    ]

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("")
    print("\n".join(lines))


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()