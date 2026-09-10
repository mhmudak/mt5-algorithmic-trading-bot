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


def write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    """
    Atomically publish JSON status.

    Long-session diagnostics must never leave a partially
    rewritten latest-status file if the process is interrupted
    during the write.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_name(
        f".{path.name}.tmp"
    )

    temporary_path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    os.replace(
        temporary_path,
        path,
    )


def append_jsonl(
    path: Path,
    payload: dict[str, Any],
) -> None:
    """
    Durably append one long-session observation.

    Snapshot cadence is intentionally low enough that a flush
    and fsync per record is acceptable and protects useful
    partial-session evidence.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "a",
        encoding="utf-8",
    ) as f:
        f.write(
            json.dumps(
                payload,
                ensure_ascii=False,
            )
            + "\n"
        )

        f.flush()
        os.fsync(f.fileno())


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


class SessionSummaryAccumulator:
    """
    Constant-memory Phase 5Y quality accumulator.

    The capture JSONL remains the source of historical records.
    The live collector must not retain every snapshot for the
    duration of an arbitrarily long session.
    """

    def __init__(self) -> None:
        self.sample_count = 0
        self.positive_bbo_count = 0
        self.two_sided_dom_count = 0

        self.spread_count = 0
        self.spread_sum = 0.0
        self.max_spread: float | None = None

        self.trade_count_sum = 0.0
        self.max_rolling_trade_count = 0.0

        self.bid_depth_sum = 0.0
        self.ask_depth_sum = 0.0

    def add_record(
        self,
        record: dict[str, Any],
    ) -> None:
        metrics = record.get("metrics") or {}

        self.sample_count += 1

        bid = as_float(metrics.get("bid"))
        ask = as_float(metrics.get("ask"))

        if bid > 0 and ask > 0:
            self.positive_bbo_count += 1

        bid_depth = as_float(
            metrics.get("bid_depth")
        )

        ask_depth = as_float(
            metrics.get("ask_depth")
        )

        if (
            bid_depth > 0
            and ask_depth > 0
        ):
            self.two_sided_dom_count += 1

        spread = as_float(
            metrics.get("spread")
        )

        if spread > 0:
            self.spread_count += 1
            self.spread_sum += spread

            if (
                self.max_spread is None
                or spread > self.max_spread
            ):
                self.max_spread = spread

        rolling_trade_count = as_float(
            metrics.get(
                "rolling_trade_count"
            )
        )

        self.trade_count_sum += (
            rolling_trade_count
        )

        self.max_rolling_trade_count = max(
            self.max_rolling_trade_count,
            rolling_trade_count,
        )

        self.bid_depth_sum += bid_depth
        self.ask_depth_sum += ask_depth

    def summary(self) -> dict[str, Any]:
        if self.sample_count == 0:
            return {
                "sample_count": 0,
                "quality_ready": False,
                "reason": "NO_RECORDS",
            }

        positive_bbo_rate = (
            self.positive_bbo_count
            / self.sample_count
        )

        two_sided_dom_rate = (
            self.two_sided_dom_count
            / self.sample_count
        )

        return {
            "sample_count": self.sample_count,
            "positive_bbo_rate": round(
                positive_bbo_rate,
                4,
            ),
            "two_sided_dom_rate": round(
                two_sided_dom_rate,
                4,
            ),
            "avg_spread": (
                round(
                    self.spread_sum
                    / self.spread_count,
                    6,
                )
                if self.spread_count
                else None
            ),
            "max_spread": self.max_spread,
            "avg_rolling_trade_count": round(
                self.trade_count_sum
                / self.sample_count,
                4,
            ),
            "max_rolling_trade_count": (
                self.max_rolling_trade_count
            ),
            "avg_bid_depth": round(
                self.bid_depth_sum
                / self.sample_count,
                4,
            ),
            "avg_ask_depth": round(
                self.ask_depth_sum
                / self.sample_count,
                4,
            ),
            "quality_ready": bool(
                self.sample_count >= 10
                and positive_bbo_rate >= 0.8
                and two_sided_dom_rate >= 0.8
                and (
                    self.max_spread
                    if self.max_spread is not None
                    else 999
                )
                <= 1
            ),
        }


def summarize_records(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Backward-compatible summary helper for offline callers.

    Phase 5Y live capture itself uses SessionSummaryAccumulator
    directly and therefore does not retain an unbounded records
    list.
    """

    accumulator = SessionSummaryAccumulator()

    for record in records:
        accumulator.add_record(record)

    return accumulator.summary()


def resolve_symbols(
    cli_symbols: str | None,
    configured_symbol: str | None,
) -> list[str]:
    """
    Resolve only explicitly supplied/configured contracts.

    There is deliberately no dated GC/MGC fallback.
    """

    raw = (
        str(cli_symbols).strip()
        if cli_symbols is not None
        else ""
    )

    if not raw:
        raw = str(
            configured_symbol or ""
        ).strip()

    symbols = [
        value.strip().upper()
        for value in raw.split(",")
        if value.strip()
    ]

    if not symbols:
        raise ValueError(
            "No Rithmic contract configured. "
            "Pass --symbols explicitly or set "
            "RITHMIC_SYMBOL to the active contract."
        )

    return symbols


def build_connection_diagnostic_record(
    event: dict[str, Any],
    *,
    symbol: str,
    exchange: str,
) -> dict[str, Any]:
    """
    Whitelist connection-recovery telemetry.

    Never copy market-looking fields into the diagnostic
    channel, so a malformed diagnostic cannot later be
    mistaken for trade/BBO/DOM evidence.
    """

    return {
        "phase": PHASE,
        "record_kind": "CONNECTION_RECOVERY",
        "recorded_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "symbol": symbol,
        "exchange": exchange,
        "status": event.get("status"),
        "attempt": event.get("attempt"),
        "max_attempts": event.get(
            "max_attempts"
        ),
        "error_type": event.get(
            "error_type"
        ),
        "received_at_epoch": event.get(
            "received_at_epoch"
        ),
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
    }


def persist_connection_recovery_event(
    path: Path,
    event: dict[str, Any],
    *,
    symbol: str,
    exchange: str,
) -> dict[str, Any] | None:
    if (
        event.get("event_type")
        != "connection_recovery"
    ):
        return None

    record = (
        build_connection_diagnostic_record(
            event,
            symbol=symbol,
            exchange=exchange,
        )
    )

    append_jsonl(
        path,
        record,
    )

    return record


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
    started = datetime.now().isoformat(
        timespec="seconds"
    )

    started_epoch = time.time()

    jsonl_path = (
        ORDER_FLOW_DIR
        / f"{symbol}_phase5y_long_session_history.jsonl"
    )

    diagnostics_path = (
        ORDER_FLOW_DIR
        / f"{symbol}_phase5y_long_session_diagnostics.jsonl"
    )

    latest_path = (
        ORDER_FLOW_DIR
        / f"{symbol}_phase5y_long_session_latest.json"
    )

    accumulator = SessionSummaryAccumulator()

    latest_snapshot: dict[str, Any] | None = None

    last_connection_recovery: (
        dict[str, Any] | None
    ) = None

    terminal_recovery_status: str | None = None

    session_status = "INITIALIZING"
    error_type: str | None = None

    next_snapshot_at = time.time()
    end_time = (
        time.time()
        + max(0, duration_seconds)
    )

    def write_progress() -> None:
        now = time.time()

        write_json(
            latest_path,
            {
                "phase": PHASE,
                "symbol": symbol,
                "exchange": exchange,
                "started_at": started,
                "updated_at": (
                    datetime.now().isoformat(
                        timespec="seconds"
                    )
                ),
                "elapsed_seconds": round(
                    max(
                        0.0,
                        now - started_epoch,
                    ),
                    3,
                ),
                "duration_seconds": (
                    duration_seconds
                ),
                "snapshot_interval_seconds": (
                    snapshot_interval_seconds
                ),
                "include_order_book": (
                    include_order_book
                ),
                "session_status": (
                    session_status
                ),
                "error_type": error_type,
                "snapshot_jsonl_path": str(
                    jsonl_path
                ),
                "diagnostics_jsonl_path": str(
                    diagnostics_path
                ),
                "summary": (
                    accumulator.summary()
                ),
                "last_connection_recovery": (
                    last_connection_recovery
                ),
                "latest_snapshot": (
                    latest_snapshot
                ),
                "mode": "OBSERVE_ONLY",
                "decision_impact": "NONE",
                "can_influence_decision": False,
                "safe_for_execution": False,
                "trade_action": "NO_AUTO_TRADE",
            },
        )

    try:
        jsonl_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Fresh files for this explicitly requested session.
        jsonl_path.write_text(
            "",
            encoding="utf-8",
        )

        diagnostics_path.write_text(
            "",
            encoding="utf-8",
        )

        config = build_rithmic_config(
            symbol=symbol,
            exchange=exchange,
        )

        client = RithmicMarketDataClient(
            config
        )

        cache = RithmicRollingStateCache(
            symbol=symbol,
            exchange=exchange,
        )

        session_status = "RUNNING"
        write_progress()

        async for event in client.stream(
            duration_seconds=duration_seconds,
            include_order_book=(
                include_order_book
            ),
        ):
            latest_snapshot = cache.update(
                event
            )

            now = time.time()

            event_type = event.get(
                "event_type"
            )

            # Recovery diagnostics have their own durable
            # channel and are not dependent on snapshot timing.
            diagnostic_record = (
                persist_connection_recovery_event(
                    diagnostics_path,
                    event,
                    symbol=symbol,
                    exchange=exchange,
                )
            )

            if diagnostic_record is not None:
                last_connection_recovery = (
                    diagnostic_record
                )

                terminal_recovery_status = str(
                    diagnostic_record.get(
                        "status"
                    )
                    or ""
                )

                write_progress()

            if (
                now >= next_snapshot_at
                and latest_snapshot
            ):
                metrics = snapshot_metrics(
                    latest_snapshot
                )

                order_book = (
                    latest_snapshot.get(
                        "order_book"
                    )
                    or {}
                )

                trade_flow = (
                    latest_snapshot.get(
                        "trade_flow"
                    )
                    or {}
                )

                record = {
                    "phase": PHASE,
                    "record_kind": (
                        "STATE_SNAPSHOT"
                    ),
                    "recorded_at": (
                        datetime.now().isoformat(
                            timespec="seconds"
                        )
                    ),
                    "symbol": symbol,
                    "exchange": exchange,
                    "elapsed_seconds": round(
                        duration_seconds
                        - max(
                            0,
                            end_time - now,
                        ),
                        3,
                    ),
                    "event_type": event_type,
                    "metrics": metrics,
                    "top_bid_levels": list(
                        order_book.get(
                            "bid_levels"
                        )
                        or []
                    )[:20],
                    "top_ask_levels": list(
                        order_book.get(
                            "ask_levels"
                        )
                        or []
                    )[:20],
                    "trade_flow": {
                        "rolling_buy_volume": (
                            trade_flow.get(
                                "buy_volume"
                            )
                        ),
                        "rolling_sell_volume": (
                            trade_flow.get(
                                "sell_volume"
                            )
                        ),
                        "rolling_total_volume": (
                            trade_flow.get(
                                "total_volume"
                            )
                        ),
                        "rolling_delta": (
                            trade_flow.get(
                                "delta"
                            )
                        ),
                    },
                    "decision_impact": "NONE",
                    "can_influence_decision": False,
                    "trade_action": (
                        "NO_AUTO_TRADE"
                    ),
                }

                append_jsonl(
                    jsonl_path,
                    record,
                )

                accumulator.add_record(
                    record
                )

                next_snapshot_at = (
                    now
                    + max(
                        1,
                        snapshot_interval_seconds,
                    )
                )

                write_progress()

                summary = (
                    accumulator.summary()
                )

                print(
                    f"[SNAPSHOT] {symbol} "
                    f"samples="
                    f"{summary.get('sample_count')} "
                    f"trades="
                    f"{metrics.get('rolling_trade_count')} "
                    f"spread="
                    f"{metrics.get('spread')} "
                    f"dom="
                    f"{metrics.get('dom_available')} "
                    f"bid_depth="
                    f"{metrics.get('bid_depth')} "
                    f"ask_depth="
                    f"{metrics.get('ask_depth')}"
                )

        connection = (
            (latest_snapshot or {}).get(
                "connection"
            )
            or {}
        )

        if (
            terminal_recovery_status
            == "RECONNECT_EXHAUSTED"
        ):
            session_status = (
                "RECOVERY_EXHAUSTED"
            )

        elif (
            latest_snapshot is not None
            and not bool(
                connection.get("login_ok")
            )
        ):
            session_status = "LOGIN_NOT_OK"

        else:
            session_status = "COMPLETED"

        write_progress()

    except BaseException as exc:
        error_type = type(exc).__name__

        if isinstance(
            exc,
            (
                asyncio.CancelledError,
                KeyboardInterrupt,
            ),
        ):
            session_status = "INTERRUPTED"
        else:
            session_status = "ERROR"

        # Do not allow a secondary status-write failure to
        # hide the original capture exception.
        try:
            write_progress()
        except Exception:
            pass

        raise

    summary = accumulator.summary()

    return {
        "symbol": symbol,
        "exchange": exchange,
        "jsonl_path": str(jsonl_path),
        "diagnostics_jsonl_path": str(
            diagnostics_path
        ),
        "latest_path": str(latest_path),
        "session_status": session_status,
        "summary": summary,
    }


async def main_async() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--exchange", default="COMEX")
    parser.add_argument("--duration-seconds", type=int, default=600)
    parser.add_argument("--snapshot-interval-seconds", type=int, default=10)
    parser.add_argument("--include-order-book", action="store_true")
    args = parser.parse_args()

    ORDER_FLOW_DIR.mkdir(parents=True, exist_ok=True)
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")

    try:
        symbols = resolve_symbols(
            args.symbols,
            os.getenv("RITHMIC_SYMBOL"),
        )
    except ValueError as exc:
        parser.error(str(exc))

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