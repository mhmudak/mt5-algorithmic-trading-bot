from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import statistics
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

try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None

from src.order_flow_features.rithmic_state_cache import RithmicRollingStateCache
from src.order_flow_providers.rithmic_protocol import RithmicConfig, RithmicMarketDataClient


PHASE = "PHASE_5AC_XAUUSD_RITHMIC_BASIS_CALIBRATION"

ORDER_FLOW_DIR = ROOT / "data" / "order_flow" / "rithmic"

OUT_JSON = ORDER_FLOW_DIR / "phase5ac_xauusd_rithmic_basis_calibration.json"
OUT_TXT = ORDER_FLOW_DIR / "phase5ac_xauusd_rithmic_basis_calibration_summary.txt"


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


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

    for name in signature.parameters:
        if name == "self":
            continue

        if name in env_values and env_values[name] is not None:
            kwargs[name] = env_values[name]

    return RithmicConfig(**kwargs)


def initialize_mt5(mt5_symbol: str) -> dict[str, Any]:
    if mt5 is None:
        return {
            "ok": False,
            "error": "MetaTrader5 module not importable",
        }

    if not mt5.initialize():
        return {
            "ok": False,
            "error": f"mt5.initialize failed: {mt5.last_error()}",
        }

    selected = mt5.symbol_select(mt5_symbol, True)

    if not selected:
        return {
            "ok": False,
            "error": f"mt5.symbol_select failed for {mt5_symbol}: {mt5.last_error()}",
        }

    return {
        "ok": True,
        "symbol": mt5_symbol,
    }


def shutdown_mt5() -> None:
    try:
        if mt5 is not None:
            mt5.shutdown()
    except Exception:
        pass


def get_mt5_quote(mt5_symbol: str) -> dict[str, Any]:
    tick = mt5.symbol_info_tick(mt5_symbol) if mt5 is not None else None

    if tick is None:
        return {
            "ok": False,
            "error": "No MT5 tick available",
        }

    bid = as_float(getattr(tick, "bid", 0.0))
    ask = as_float(getattr(tick, "ask", 0.0))
    last = as_float(getattr(tick, "last", 0.0))

    mid = 0.0

    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2
    elif last > 0:
        mid = last

    return {
        "ok": mid > 0,
        "bid": bid,
        "ask": ask,
        "last": last,
        "mid": mid,
        "spread": round(ask - bid, 10) if bid > 0 and ask > 0 else None,
        "time": getattr(tick, "time", None),
    }


def extract_rithmic_quote(snapshot: dict[str, Any]) -> dict[str, Any]:
    latest_bbo = snapshot.get("latest_bbo") or {}
    order_book = snapshot.get("order_book") or {}
    latest_trade = snapshot.get("latest_trade") or {}

    bid = as_float(latest_bbo.get("last_bid") or latest_bbo.get("bid") or latest_bbo.get("bid_price"))
    ask = as_float(latest_bbo.get("last_ask") or latest_bbo.get("ask") or latest_bbo.get("ask_price"))

    top_bid = as_float(order_book.get("top_bid_price") or deep_find(snapshot, "top_bid_price"))
    top_ask = as_float(order_book.get("top_ask_price") or deep_find(snapshot, "top_ask_price"))

    if bid <= 0 and top_bid > 0:
        bid = top_bid

    if ask <= 0 and top_ask > 0:
        ask = top_ask

    last = as_float(
        latest_trade.get("price")
        or latest_trade.get("trade_price")
        or deep_find(snapshot, "trade_price")
        or snapshot.get("rolling_poc_price")
        or deep_find(snapshot, "rolling_poc_price")
    )

    mid = 0.0

    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2
    elif last > 0:
        mid = last

    return {
        "ok": mid > 0,
        "bid": bid,
        "ask": ask,
        "last": last,
        "mid": mid,
        "spread": round(ask - bid, 10) if bid > 0 and ask > 0 else None,
        "bid_depth": as_float(order_book.get("bid_depth") or deep_find(snapshot, "dom_bid_depth")),
        "ask_depth": as_float(order_book.get("ask_depth") or deep_find(snapshot, "dom_ask_depth")),
    }


def summarize_basis(records: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [r for r in records if r.get("basis_valid")]

    basis_values = [as_float(r.get("basis")) for r in valid]
    abs_basis_values = [abs(x) for x in basis_values]

    basis_changes = []
    for prev, cur in zip(basis_values, basis_values[1:]):
        basis_changes.append(cur - prev)

    if not valid:
        return {
            "sample_count": len(records),
            "valid_pair_count": 0,
            "valid_pair_rate": 0.0,
            "basis_ready_observe_only": False,
            "reason": "NO_VALID_BASIS_PAIRS",
        }

    avg_basis = sum(basis_values) / len(basis_values)

    return {
        "sample_count": len(records),
        "valid_pair_count": len(valid),
        "valid_pair_rate": round(len(valid) / len(records), 4) if records else 0.0,
        "avg_basis": round(avg_basis, 6),
        "min_basis": round(min(basis_values), 6),
        "max_basis": round(max(basis_values), 6),
        "avg_abs_basis": round(sum(abs_basis_values) / len(abs_basis_values), 6),
        "basis_std": round(statistics.pstdev(basis_values), 6) if len(basis_values) >= 2 else 0.0,
        "max_abs_basis_jump": round(max([abs(x) for x in basis_changes], default=0.0), 6),
        "basis_ready_observe_only": bool(
            len(valid) >= 30
            and len(valid) / len(records) >= 0.90
            and (statistics.pstdev(basis_values) if len(basis_values) >= 2 else 0.0) <= 2.0
        ),
        "decision_grade_ready": False,
        "automation_allowed": False,
        "decision_impact": "NONE",
        "can_influence_decision": False,
    }


async def main_async() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mt5-symbol", default="XAUUSD")
    parser.add_argument("--rithmic-symbol", default="MGCQ6")
    parser.add_argument("--exchange", default="COMEX")
    parser.add_argument("--duration-seconds", type=int, default=300)
    parser.add_argument("--snapshot-interval-seconds", type=int, default=3)
    parser.add_argument("--include-order-book", action="store_true")
    args = parser.parse_args()

    ORDER_FLOW_DIR.mkdir(parents=True, exist_ok=True)

    jsonl_path = ORDER_FLOW_DIR / "phase5ac_xauusd_mgcq6_basis_history.jsonl"
    jsonl_path.write_text("", encoding="utf-8")

    print("[PHASE 5AC XAUUSD ↔ RITHMIC BASIS CALIBRATION]")
    print(f"mt5_symbol = {args.mt5_symbol}")
    print(f"rithmic_symbol = {args.rithmic_symbol}")
    print(f"exchange = {args.exchange}")
    print(f"duration_seconds = {args.duration_seconds}")
    print(f"snapshot_interval_seconds = {args.snapshot_interval_seconds}")
    print("mode = OBSERVE_ONLY")
    print("decision_impact = NONE")
    print("can_influence_decision = False")
    print("trade_action = NO_AUTO_TRADE")
    print("")

    mt5_status = initialize_mt5(args.mt5_symbol)

    if not mt5_status.get("ok"):
        report = {
            "phase": PHASE,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "status": "FAILED_MT5_NOT_AVAILABLE",
            "mt5_status": mt5_status,
            "mode": "OBSERVE_ONLY",
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "trade_action": "NO_AUTO_TRADE",
        }
        write_json(OUT_JSON, report)
        print(f"[STOP] {mt5_status.get('error')}")
        return

    config = build_rithmic_config(symbol=args.rithmic_symbol, exchange=args.exchange)
    client = RithmicMarketDataClient(config)
    cache = RithmicRollingStateCache(symbol=args.rithmic_symbol, exchange=args.exchange)

    records: list[dict[str, Any]] = []
    next_snapshot_at = time.time()
    end_time = time.time() + args.duration_seconds

    try:
        async for event in client.stream(
            duration_seconds=args.duration_seconds,
            include_order_book=args.include_order_book,
        ):
            snapshot = cache.update(event)
            now = time.time()

            if now < next_snapshot_at:
                continue

            mt5_quote = get_mt5_quote(args.mt5_symbol)
            rithmic_quote = extract_rithmic_quote(snapshot)

            basis_valid = bool(mt5_quote.get("ok") and rithmic_quote.get("ok"))

            basis = None
            if basis_valid:
                basis = round(as_float(mt5_quote.get("mid")) - as_float(rithmic_quote.get("mid")), 6)

            record = {
                "phase": PHASE,
                "recorded_at": datetime.now().isoformat(timespec="seconds"),
                "elapsed_seconds": round(args.duration_seconds - max(0, end_time - now), 3),
                "mt5_symbol": args.mt5_symbol,
                "rithmic_symbol": args.rithmic_symbol,
                "mt5": mt5_quote,
                "rithmic": rithmic_quote,
                "basis": basis,
                "basis_valid": basis_valid,
                "interpretation": "basis = MT5_XAUUSD_mid - Rithmic_MGCQ6_mid",
                "decision_impact": "NONE",
                "can_influence_decision": False,
                "trade_action": "NO_AUTO_TRADE",
            }

            append_jsonl(jsonl_path, record)
            records.append(record)

            print(
                f"[BASIS] samples={len(records)} "
                f"valid={basis_valid} "
                f"mt5_mid={mt5_quote.get('mid')} "
                f"rithmic_mid={rithmic_quote.get('mid')} "
                f"basis={basis} "
                f"mt5_spread={mt5_quote.get('spread')} "
                f"rithmic_spread={rithmic_quote.get('spread')}"
            )

            next_snapshot_at = now + args.snapshot_interval_seconds

    finally:
        shutdown_mt5()

    summary = summarize_basis(records)

    report = {
        "phase": PHASE,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "mt5_symbol": args.mt5_symbol,
        "rithmic_symbol": args.rithmic_symbol,
        "exchange": args.exchange,
        "jsonl": str(jsonl_path),
        "mode": "OBSERVE_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
        "summary": summary,
        "recommendation": (
            "Use basis calibration only to understand XAUUSD vs MGCQ6 price distance. "
            "Do not allow Rithmic to influence decisions until repeated production sessions pass."
        ),
    }

    write_json(OUT_JSON, report)

    lines = [
        "[PHASE 5AC XAUUSD ↔ RITHMIC BASIS CALIBRATION]",
        f"updated_at = {report['updated_at']}",
        f"mt5_symbol = {args.mt5_symbol}",
        f"rithmic_symbol = {args.rithmic_symbol}",
        f"mode = {report['mode']}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        f"safe_for_execution = {report['safe_for_execution']}",
        f"trade_action = {report['trade_action']}",
        "",
        "[SUMMARY]",
        f"sample_count = {summary.get('sample_count')}",
        f"valid_pair_count = {summary.get('valid_pair_count')}",
        f"valid_pair_rate = {summary.get('valid_pair_rate')}",
        f"avg_basis = {summary.get('avg_basis')}",
        f"min_basis = {summary.get('min_basis')}",
        f"max_basis = {summary.get('max_basis')}",
        f"avg_abs_basis = {summary.get('avg_abs_basis')}",
        f"basis_std = {summary.get('basis_std')}",
        f"max_abs_basis_jump = {summary.get('max_abs_basis_jump')}",
        f"basis_ready_observe_only = {summary.get('basis_ready_observe_only')}",
        f"decision_grade_ready = {summary.get('decision_grade_ready')}",
        f"automation_allowed = {summary.get('automation_allowed')}",
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
        "",
        f"json = {OUT_JSON}",
        f"jsonl = {jsonl_path}",
        f"summary = {OUT_TXT}",
    ]

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("")
    print("\n".join(lines))


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()