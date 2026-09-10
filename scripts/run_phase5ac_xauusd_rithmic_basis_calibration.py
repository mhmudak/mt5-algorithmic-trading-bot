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


def write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    """
    Atomically publish the latest basis-calibration status.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_name(
        f".{path.name}.tmp"
    )

    temporary_path.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
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
    Durably append one basis observation.

    Phase 5AC normally samples only every few seconds, so an
    fsync per observation is acceptable for useful partial
    session recovery.
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
        os.fsync(
            f.fileno()
        )


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
        error = (
            "mt5.symbol_select failed for "
            f"{mt5_symbol}: {mt5.last_error()}"
        )

        shutdown_mt5()

        return {
            "ok": False,
            "error": error,
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


BASIS_SAMPLE_EVENT_TYPES = frozenset(
    {
        "last_trade",
        "best_bid_offer",
        "order_book",
    }
)


def _safe_symbol_for_file(
    value: str,
) -> str:
    safe = str(value).strip().upper()

    for old, new in (
        ("/", "_"),
        ("\\", "_"),
        (".", "_"),
        (" ", "_"),
        (":", "_"),
    ):
        safe = safe.replace(
            old,
            new,
        )

    return safe


def resolve_rithmic_symbol(
    cli_symbol: str | None,
    configured_symbol: str | None,
) -> str:
    """
    Resolve only an explicit CLI or configured active contract.

    There is deliberately no dated futures fallback.
    """

    cli = str(
        cli_symbol or ""
    ).strip()

    if cli:
        return cli.upper()

    configured = str(
        configured_symbol or ""
    ).strip()

    if configured:
        return configured.upper()

    raise ValueError(
        "No Rithmic contract configured. "
        "Pass --rithmic-symbol explicitly "
        "or set RITHMIC_SYMBOL to the "
        "active contract."
    )


def should_sample_basis_event(
    event: dict[str, Any],
) -> bool:
    """
    Only actual market observations may trigger a timed basis
    sample. Login, heartbeat and connection-recovery telemetry
    must never cause stale cached futures prices to be sampled.
    """

    return (
        event.get("event_type")
        in BASIS_SAMPLE_EVENT_TYPES
    )


def classify_session_status(
    latest_snapshot: dict[str, Any] | None,
    terminal_recovery_status: str | None,
) -> str:
    """
    Classify a normally-returning stream without treating
    rejected login as successful completion.
    """

    if (
        terminal_recovery_status
        == "RECONNECT_EXHAUSTED"
    ):
        return "RECOVERY_EXHAUSTED"

    connection = (
        (latest_snapshot or {}).get(
            "connection"
        )
        or {}
    )

    if (
        latest_snapshot is not None
        and not bool(
            connection.get("login_ok")
        )
    ):
        return "LOGIN_NOT_OK"

    return "COMPLETED"


class BasisSummaryAccumulator:
    """
    Constant-memory Phase 5AC basis summary.

    Population variance uses Welford's online algorithm so the
    result is equivalent to statistics.pstdev without retaining
    every historical record.
    """

    def __init__(self) -> None:
        self.sample_count = 0
        self.valid_pair_count = 0

        self.sum_basis = 0.0
        self.sum_abs_basis = 0.0

        self.min_basis: float | None = None
        self.max_basis: float | None = None

        self.mean_basis = 0.0
        self.m2_basis = 0.0

        self.previous_valid_basis: (
            float | None
        ) = None

        self.max_abs_basis_jump = 0.0

    def add_record(
        self,
        record: dict[str, Any],
    ) -> None:
        self.sample_count += 1

        if not bool(
            record.get("basis_valid")
        ):
            return

        value = as_float(
            record.get("basis")
        )

        self.valid_pair_count += 1

        self.sum_basis += value
        self.sum_abs_basis += abs(
            value
        )

        if (
            self.min_basis is None
            or value < self.min_basis
        ):
            self.min_basis = value

        if (
            self.max_basis is None
            or value > self.max_basis
        ):
            self.max_basis = value

        delta = (
            value
            - self.mean_basis
        )

        self.mean_basis += (
            delta
            / self.valid_pair_count
        )

        delta2 = (
            value
            - self.mean_basis
        )

        self.m2_basis += (
            delta
            * delta2
        )

        if (
            self.previous_valid_basis
            is not None
        ):
            jump = abs(
                value
                - self.previous_valid_basis
            )

            self.max_abs_basis_jump = max(
                self.max_abs_basis_jump,
                jump,
            )

        self.previous_valid_basis = value

    def summary(
        self,
    ) -> dict[str, Any]:
        if (
            self.valid_pair_count == 0
        ):
            return {
                "sample_count": (
                    self.sample_count
                ),
                "valid_pair_count": 0,
                "valid_pair_rate": 0.0,
                "basis_ready_observe_only": False,
                "reason": (
                    "NO_VALID_BASIS_PAIRS"
                ),
            }

        valid_pair_rate = (
            self.valid_pair_count
            / self.sample_count
            if self.sample_count
            else 0.0
        )

        population_variance = (
            self.m2_basis
            / self.valid_pair_count
        )

        population_std = (
            population_variance ** 0.5
        )

        return {
            "sample_count": (
                self.sample_count
            ),
            "valid_pair_count": (
                self.valid_pair_count
            ),
            "valid_pair_rate": round(
                valid_pair_rate,
                4,
            ),
            "avg_basis": round(
                self.sum_basis
                / self.valid_pair_count,
                6,
            ),
            "min_basis": round(
                float(self.min_basis),
                6,
            ),
            "max_basis": round(
                float(self.max_basis),
                6,
            ),
            "avg_abs_basis": round(
                self.sum_abs_basis
                / self.valid_pair_count,
                6,
            ),
            "basis_std": round(
                population_std,
                6,
            ),
            "max_abs_basis_jump": round(
                self.max_abs_basis_jump,
                6,
            ),
            "basis_ready_observe_only": bool(
                self.valid_pair_count >= 30
                and valid_pair_rate >= 0.90
                and population_std <= 2.0
            ),
            "decision_grade_ready": False,
            "automation_allowed": False,
            "decision_impact": "NONE",
            "can_influence_decision": False,
        }


def summarize_basis(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Backward-compatible offline helper.

    Live Phase 5AC uses BasisSummaryAccumulator directly and
    therefore never retains an unbounded records list.
    """

    accumulator = BasisSummaryAccumulator()

    for record in records:
        accumulator.add_record(
            record
        )

    return accumulator.summary()


async def main_async() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mt5-symbol",
        default="XAUUSD",
    )

    parser.add_argument(
        "--rithmic-symbol",
        default=None,
    )

    parser.add_argument(
        "--exchange",
        default="COMEX",
    )

    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=300,
    )

    parser.add_argument(
        "--snapshot-interval-seconds",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--include-order-book",
        action="store_true",
    )

    args = parser.parse_args()

    if load_dotenv is not None:
        load_dotenv(
            ROOT / ".env"
        )

    try:
        rithmic_symbol = (
            resolve_rithmic_symbol(
                args.rithmic_symbol,
                os.getenv(
                    "RITHMIC_SYMBOL"
                ),
            )
        )
    except ValueError as exc:
        parser.error(
            str(exc)
        )

    ORDER_FLOW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    safe_mt5_symbol = (
        _safe_symbol_for_file(
            args.mt5_symbol
        )
    )

    safe_rithmic_symbol = (
        _safe_symbol_for_file(
            rithmic_symbol
        )
    )

    jsonl_path = (
        ORDER_FLOW_DIR
        / (
            "phase5ac_"
            f"{safe_mt5_symbol}_"
            f"{safe_rithmic_symbol}_"
            "basis_history.jsonl"
        )
    )

    jsonl_path.write_text(
        "",
        encoding="utf-8",
    )

    print(
        "[PHASE 5AC XAUUSD "
        "↔ RITHMIC BASIS CALIBRATION]"
    )

    print(
        f"mt5_symbol = "
        f"{args.mt5_symbol}"
    )

    print(
        f"rithmic_symbol = "
        f"{rithmic_symbol}"
    )

    print(
        f"exchange = "
        f"{args.exchange}"
    )

    print(
        f"duration_seconds = "
        f"{args.duration_seconds}"
    )

    print(
        "snapshot_interval_seconds = "
        f"{args.snapshot_interval_seconds}"
    )

    print("mode = OBSERVE_ONLY")
    print("decision_impact = NONE")
    print(
        "can_influence_decision = False"
    )
    print(
        "trade_action = NO_AUTO_TRADE"
    )
    print("")

    accumulator = (
        BasisSummaryAccumulator()
    )

    session_status = "INITIALIZING"
    error_type: str | None = None

    terminal_recovery_status: (
        str | None
    ) = None

    last_connection_recovery: (
        dict[str, Any] | None
    ) = None

    latest_snapshot: (
        dict[str, Any] | None
    ) = None

    started_at = (
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    interpretation = (
        f"basis = MT5_{args.mt5_symbol}_mid "
        f"- Rithmic_{rithmic_symbol}_mid"
    )

    recommendation = (
        "Use basis calibration only to understand "
        f"{args.mt5_symbol} vs {rithmic_symbol} "
        "price distance. Do not allow Rithmic to "
        "influence decisions until repeated "
        "production sessions pass."
    )

    def write_progress(
        *,
        mt5_status: (
            dict[str, Any] | None
        ) = None,
    ) -> None:
        write_json(
            OUT_JSON,
            {
                "phase": PHASE,
                "started_at": started_at,
                "updated_at": (
                    datetime.now().isoformat(
                        timespec="seconds"
                    )
                ),
                "session_status": (
                    session_status
                ),
                "error_type": error_type,
                "mt5_symbol": (
                    args.mt5_symbol
                ),
                "rithmic_symbol": (
                    rithmic_symbol
                ),
                "exchange": (
                    args.exchange
                ),
                "duration_seconds": (
                    args.duration_seconds
                ),
                "snapshot_interval_seconds": (
                    args.snapshot_interval_seconds
                ),
                "include_order_book": (
                    args.include_order_book
                ),
                "jsonl": str(
                    jsonl_path
                ),
                "mt5_status": (
                    mt5_status
                ),
                "summary": (
                    accumulator.summary()
                ),
                "last_connection_recovery": (
                    last_connection_recovery
                ),
                "interpretation": (
                    interpretation
                ),
                "mode": "OBSERVE_ONLY",
                "decision_impact": "NONE",
                "can_influence_decision": False,
                "safe_for_execution": False,
                "trade_action": (
                    "NO_AUTO_TRADE"
                ),
                "recommendation": (
                    recommendation
                ),
            },
        )

    mt5_status = initialize_mt5(
        args.mt5_symbol
    )

    if not mt5_status.get("ok"):
        session_status = (
            "FAILED_MT5_NOT_AVAILABLE"
        )

        write_progress(
            mt5_status=mt5_status,
        )

        print(
            "[STOP] "
            f"{mt5_status.get('error')}"
        )

        return

    next_snapshot_at = time.time()

    end_time = (
        time.time()
        + max(
            0,
            args.duration_seconds,
        )
    )

    try:
        config = build_rithmic_config(
            symbol=rithmic_symbol,
            exchange=args.exchange,
        )

        client = (
            RithmicMarketDataClient(
                config
            )
        )

        cache = (
            RithmicRollingStateCache(
                symbol=rithmic_symbol,
                exchange=args.exchange,
            )
        )

        session_status = "RUNNING"

        write_progress(
            mt5_status=mt5_status,
        )

        async for event in client.stream(
            duration_seconds=(
                args.duration_seconds
            ),
            include_order_book=(
                args.include_order_book
            ),
        ):
            latest_snapshot = cache.update(
                event
            )

            snapshot = latest_snapshot

            now = time.time()

            event_type = event.get(
                "event_type"
            )

            if (
                event_type
                == "connection_recovery"
            ):
                last_connection_recovery = {
                    "status": (
                        event.get("status")
                    ),
                    "attempt": (
                        event.get("attempt")
                    ),
                    "max_attempts": (
                        event.get(
                            "max_attempts"
                        )
                    ),
                    "error_type": (
                        event.get(
                            "error_type"
                        )
                    ),
                    "received_at_epoch": (
                        event.get(
                            "received_at_epoch"
                        )
                    ),
                    "decision_impact": (
                        "NONE"
                    ),
                    "can_influence_decision": False,
                    "safe_for_execution": False,
                }

                terminal_recovery_status = (
                    str(
                        event.get(
                            "status"
                        )
                        or ""
                    )
                )

                write_progress(
                    mt5_status=mt5_status,
                )

            # Connection/login/heartbeat telemetry may update
            # observer state, but must never trigger a basis
            # observation from cached futures prices.
            if not should_sample_basis_event(
                event
            ):
                continue

            if now < next_snapshot_at:
                continue

            mt5_quote = get_mt5_quote(
                args.mt5_symbol
            )

            rithmic_quote = (
                extract_rithmic_quote(
                    snapshot
                )
            )

            basis_valid = bool(
                mt5_quote.get("ok")
                and rithmic_quote.get("ok")
            )

            basis = None

            if basis_valid:
                basis = round(
                    as_float(
                        mt5_quote.get(
                            "mid"
                        )
                    )
                    - as_float(
                        rithmic_quote.get(
                            "mid"
                        )
                    ),
                    6,
                )

            record = {
                "phase": PHASE,
                "recorded_at": (
                    datetime.now().isoformat(
                        timespec="seconds"
                    )
                ),
                "elapsed_seconds": round(
                    args.duration_seconds
                    - max(
                        0,
                        end_time - now,
                    ),
                    3,
                ),
                "mt5_symbol": (
                    args.mt5_symbol
                ),
                "rithmic_symbol": (
                    rithmic_symbol
                ),
                "mt5": mt5_quote,
                "rithmic": (
                    rithmic_quote
                ),
                "basis": basis,
                "basis_valid": (
                    basis_valid
                ),
                "interpretation": (
                    interpretation
                ),
                "decision_impact": "NONE",
                "can_influence_decision": False,
                "safe_for_execution": False,
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

            summary = (
                accumulator.summary()
            )

            print(
                "[BASIS] "
                f"samples="
                f"{summary.get('sample_count')} "
                f"valid={basis_valid} "
                f"mt5_mid="
                f"{mt5_quote.get('mid')} "
                f"rithmic_mid="
                f"{rithmic_quote.get('mid')} "
                f"basis={basis} "
                f"mt5_spread="
                f"{mt5_quote.get('spread')} "
                f"rithmic_spread="
                f"{rithmic_quote.get('spread')}"
            )

            next_snapshot_at = (
                now
                + max(
                    1,
                    args.snapshot_interval_seconds,
                )
            )

            write_progress(
                mt5_status=mt5_status,
            )

        session_status = (
            classify_session_status(
                latest_snapshot,
                terminal_recovery_status,
            )
        )

        write_progress(
            mt5_status=mt5_status,
        )

    except BaseException as exc:
        error_type = (
            type(exc).__name__
        )

        if isinstance(
            exc,
            (
                asyncio.CancelledError,
                KeyboardInterrupt,
            ),
        ):
            session_status = (
                "INTERRUPTED"
            )
        else:
            session_status = "ERROR"

        try:
            write_progress(
                mt5_status=mt5_status,
            )
        except Exception:
            pass

        raise

    finally:
        shutdown_mt5()

    summary = (
        accumulator.summary()
    )

    lines = [
        "[PHASE 5AC XAUUSD "
        "↔ RITHMIC BASIS CALIBRATION]",
        f"updated_at = "
        f"{datetime.now().isoformat(timespec='seconds')}",
        f"session_status = "
        f"{session_status}",
        f"mt5_symbol = "
        f"{args.mt5_symbol}",
        f"rithmic_symbol = "
        f"{rithmic_symbol}",
        f"mode = OBSERVE_ONLY",
        f"decision_impact = NONE",
        f"can_influence_decision = False",
        f"safe_for_execution = False",
        f"trade_action = NO_AUTO_TRADE",
        "",
        "[SUMMARY]",
        f"sample_count = "
        f"{summary.get('sample_count')}",
        f"valid_pair_count = "
        f"{summary.get('valid_pair_count')}",
        f"valid_pair_rate = "
        f"{summary.get('valid_pair_rate')}",
        f"avg_basis = "
        f"{summary.get('avg_basis')}",
        f"min_basis = "
        f"{summary.get('min_basis')}",
        f"max_basis = "
        f"{summary.get('max_basis')}",
        f"avg_abs_basis = "
        f"{summary.get('avg_abs_basis')}",
        f"basis_std = "
        f"{summary.get('basis_std')}",
        f"max_abs_basis_jump = "
        f"{summary.get('max_abs_basis_jump')}",
        f"basis_ready_observe_only = "
        f"{summary.get('basis_ready_observe_only')}",
        f"decision_grade_ready = "
        f"{summary.get('decision_grade_ready')}",
        f"automation_allowed = "
        f"{summary.get('automation_allowed')}",
        "",
        "[RECOMMENDATION]",
        recommendation,
        "",
        f"json = {OUT_JSON}",
        f"jsonl = {jsonl_path}",
        f"summary = {OUT_TXT}",
    ]

    OUT_TXT.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("")
    print(
        "\n".join(lines)
    )


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()