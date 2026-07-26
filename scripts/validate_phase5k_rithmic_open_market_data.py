from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RITHMIC_DIR = ROOT / "data" / "order_flow" / "rithmic"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_symbols(value: str) -> list[str]:
    items = []

    for part in str(value or "").replace(";", ",").split(","):
        symbol = part.strip()
        if symbol:
            items.append(symbol)

    return items or ["GCQ6"]


def safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace("\\", "_").replace(".", "_")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_command(label: str, command: list[str], timeout: int = 300) -> dict[str, Any]:
    started = time.time()

    result = {
        "label": label,
        "command": command,
        "started_at": now_iso(),
        "success": False,
        "returncode": None,
        "duration_seconds": None,
        "stdout_tail": "",
        "stderr_tail": "",
    }

    try:
        proc = subprocess.run(
            command,
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=timeout,
        )

        result["returncode"] = proc.returncode
        result["success"] = proc.returncode == 0
        result["stdout_tail"] = (proc.stdout or "")[-5000:]
        result["stderr_tail"] = (proc.stderr or "")[-5000:]

    except subprocess.TimeoutExpired as exc:
        result["returncode"] = "TIMEOUT"
        result["stderr_tail"] = str(exc)

    except Exception as exc:
        result["returncode"] = "ERROR"
        result["stderr_tail"] = repr(exc)

    result["duration_seconds"] = round(time.time() - started, 2)
    return result


def as_bool(value: Any) -> bool:
    return bool(value)


def as_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def validate_symbol(symbol: str, *, stale_after_seconds: int) -> dict[str, Any]:
    s = safe_symbol(symbol)

    state_path = RITHMIC_DIR / f"{s}_phase5c_rithmic_state_latest.json"
    provider_path = RITHMIC_DIR / f"{s}_phase5g_rithmic_monitoring_bridge.json"

    state = load_json(state_path)
    bridge = load_json(provider_path)

    connection = state.get("connection") or {}
    freshness = state.get("freshness") or {}
    sample = state.get("sample") or {}
    bbo = state.get("bbo") or {}
    order_book = state.get("order_book") or {}
    metrics = state.get("adapter_compatible_metrics") or {}
    bridge_metrics = bridge.get("adapter_metrics") or {}

    login_ok = as_bool(connection.get("login_ok"))
    market_data_ok = as_bool(connection.get("market_data_ok"))
    has_fresh_trade = as_bool(freshness.get("has_fresh_trade"))
    has_fresh_bbo = as_bool(freshness.get("has_fresh_bbo"))
    has_fresh_order_book = as_bool(freshness.get("has_fresh_order_book"))

    trade_count = int(as_number(sample.get("rolling_trade_count"), 0))
    bbo_count = int(as_number(sample.get("bbo_count"), 0))
    nonzero_bbo_count = int(as_number(sample.get("nonzero_bbo_count"), 0))
    order_book_count = int(as_number(sample.get("order_book_count"), 0))

    delta = metrics.get("delta", bridge_metrics.get("delta"))
    cumulative_delta = metrics.get("cumulative_delta", bridge_metrics.get("cumulative_delta"))
    dom_available = as_bool(metrics.get("dom_available") or bridge_metrics.get("dom_available"))

    last_bid = as_number(bbo.get("last_bid"), 0)
    last_ask = as_number(bbo.get("last_ask"), 0)

    checks = {
        "state_snapshot_exists": bool(state),
        "bridge_snapshot_exists": bool(bridge),
        "login_ok": login_ok,
        "market_data_ok": market_data_ok,
        "has_fresh_trade": has_fresh_trade,
        "has_fresh_bbo": has_fresh_bbo,
        "has_fresh_order_book": has_fresh_order_book,
        "trade_count_positive": trade_count > 0,
        "bbo_count_positive": bbo_count > 0,
        "nonzero_bbo_available": nonzero_bbo_count > 0 or (last_bid > 0 and last_ask > 0),
        "order_book_observed": order_book_count > 0,
        "dom_available": dom_available,
        "delta_available": delta is not None,
        "cumulative_delta_available": cumulative_delta is not None,
        "decision_impact_none": state.get("decision_impact") == "NONE" and bridge.get("decision_impact") == "NONE",
        "cannot_influence_decision": bridge.get("can_influence_decision") is False,
    }

    critical_checks = [
        "state_snapshot_exists",
        "bridge_snapshot_exists",
        "login_ok",
        "market_data_ok",
        "delta_available",
        "cumulative_delta_available",
        "decision_impact_none",
        "cannot_influence_decision",
    ]

    open_market_quality_checks = [
        "trade_count_positive",
        "has_fresh_trade",
        "has_fresh_bbo",
        "nonzero_bbo_available",
    ]

    dom_quality_checks = [
        "order_book_observed",
        "dom_available",
    ]

    critical_ok = all(checks.get(k) for k in critical_checks)
    open_market_quality_ok = all(checks.get(k) for k in open_market_quality_checks)
    dom_quality_ok = all(checks.get(k) for k in dom_quality_checks)

    if not critical_ok:
        status = "RITHMIC_VALIDATION_FAILED_CRITICAL"
    elif not open_market_quality_ok:
        status = "RITHMIC_CONNECTED_BUT_MARKET_DATA_NOT_ACTIVE_OR_STALE"
    elif not dom_quality_ok:
        status = "RITHMIC_TRADES_OK_DOM_NOT_READY"
    else:
        status = "RITHMIC_OPEN_MARKET_DATA_VALIDATED_OBSERVE_ONLY"

    return {
        "symbol": symbol,
        "status": status,
        "state_path": str(state_path),
        "bridge_path": str(provider_path),
        "checks": checks,
        "critical_ok": critical_ok,
        "open_market_quality_ok": open_market_quality_ok,
        "dom_quality_ok": dom_quality_ok,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_live_decision": False,
        "metrics": {
            "trade_count": trade_count,
            "bbo_count": bbo_count,
            "nonzero_bbo_count": nonzero_bbo_count,
            "order_book_count": order_book_count,
            "delta": delta,
            "cumulative_delta": cumulative_delta,
            "last_bid": last_bid,
            "last_ask": last_ask,
            "dom_available": dom_available,
            "dom_bid_depth": metrics.get("dom_bid_depth", bridge_metrics.get("dom_bid_depth")),
            "dom_ask_depth": metrics.get("dom_ask_depth", bridge_metrics.get("dom_ask_depth")),
            "order_book_update_type": order_book.get("last_update_type_name"),
            "last_trade_age_seconds": freshness.get("last_trade_age_seconds"),
            "last_bbo_age_seconds": freshness.get("last_bbo_age_seconds"),
            "last_order_book_age_seconds": freshness.get("last_order_book_age_seconds"),
        },
        "warnings": sorted(set(
            list((state.get("quality") or {}).get("warnings") or [])
            + list(bridge.get("warnings") or [])
        )),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="GCQ6,MGCQ6")
    parser.add_argument("--exchange", default="COMEX")
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--include-order-book", action="store_true")
    parser.add_argument("--run-refresh-first", action="store_true")
    parser.add_argument("--stale-after-seconds", type=int, default=30)
    args = parser.parse_args()

    RITHMIC_DIR.mkdir(parents=True, exist_ok=True)

    symbols = parse_symbols(args.symbols)
    python = sys.executable

    refresh_result = None

    if args.run_refresh_first:
        command = [
            python,
            str(ROOT / "scripts" / "run_phase5j_rithmic_manual_refresh_pipeline.py"),
            "--symbols",
            ",".join(symbols),
            "--exchange",
            args.exchange,
            "--duration-seconds",
            str(args.duration_seconds),
        ]

        if args.include_order_book:
            command.append("--include-order-book")

        print("[RUN] Phase 5J refresh before validation")
        refresh_result = run_command(
            "phase5j_manual_refresh",
            command,
            timeout=max(180, args.duration_seconds * len(symbols) + 180),
        )

        print(
            "phase5j_manual_refresh",
            "| success=",
            refresh_result["success"],
            "| returncode=",
            refresh_result["returncode"],
            "| duration=",
            refresh_result["duration_seconds"],
        )

    validations = [
        validate_symbol(symbol, stale_after_seconds=args.stale_after_seconds)
        for symbol in symbols
    ]

    report = {
        "phase": "PHASE_5K_RITHMIC_OPEN_MARKET_VALIDATION",
        "mode": "OBSERVE_ONLY",
        "updated_at": now_iso(),
        "symbols": symbols,
        "exchange": args.exchange,
        "duration_seconds": args.duration_seconds,
        "include_order_book": args.include_order_book,
        "run_refresh_first": args.run_refresh_first,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_live_decision": False,
        "safe_for_execution": False,
        "refresh_result": refresh_result,
        "validations": validations,
        "all_critical_ok": all(item["critical_ok"] for item in validations),
        "all_open_market_quality_ok": all(item["open_market_quality_ok"] for item in validations),
        "all_dom_quality_ok": all(item["dom_quality_ok"] for item in validations),
    }

    if not report["all_critical_ok"]:
        report["overall_status"] = "CRITICAL_VALIDATION_NOT_READY"
        report["recommendation"] = "Fix missing snapshots/login/market-data basics before using Rithmic for strategy validation."
    elif not report["all_open_market_quality_ok"]:
        report["overall_status"] = "CONNECTED_BUT_RETEST_WHEN_MARKET_ACTIVE_OR_LOW_TRADE_FLOW"
        report["recommendation"] = "Rithmic connection works, but fresh active trade flow is not validated yet."
    elif not report["all_dom_quality_ok"]:
        report["overall_status"] = "TRADE_FLOW_VALIDATED_DOM_NOT_READY"
        report["recommendation"] = "Trade flow is usable for observe-only research, but DOM depth is not validated."
    else:
        report["overall_status"] = "OPEN_MARKET_RITHMIC_VALIDATED_OBSERVE_ONLY"
        report["recommendation"] = "Rithmic open-market data is validated for observe-only research. Keep decision impact disabled."

    report_path = RITHMIC_DIR / "phase5k_rithmic_open_market_validation_report.json"
    summary_path = RITHMIC_DIR / "phase5k_rithmic_open_market_validation_summary.txt"

    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 5K RITHMIC OPEN-MARKET VALIDATION]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"symbols = {', '.join(symbols)}",
        f"exchange = {args.exchange}",
        f"include_order_book = {args.include_order_book}",
        f"run_refresh_first = {args.run_refresh_first}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        f"overall_status = {report['overall_status']}",
        f"all_critical_ok = {report['all_critical_ok']}",
        f"all_open_market_quality_ok = {report['all_open_market_quality_ok']}",
        f"all_dom_quality_ok = {report['all_dom_quality_ok']}",
        f"recommendation = {report['recommendation']}",
        "",
        "[SYMBOLS]",
    ]

    for item in validations:
        metrics = item["metrics"]
        lines += [
            f"{item['symbol']} status = {item['status']}",
            f"{item['symbol']} critical_ok = {item['critical_ok']}",
            f"{item['symbol']} open_market_quality_ok = {item['open_market_quality_ok']}",
            f"{item['symbol']} dom_quality_ok = {item['dom_quality_ok']}",
            f"{item['symbol']} trade_count = {metrics['trade_count']}",
            f"{item['symbol']} bbo_count = {metrics['bbo_count']}",
            f"{item['symbol']} nonzero_bbo_count = {metrics['nonzero_bbo_count']}",
            f"{item['symbol']} order_book_count = {metrics['order_book_count']}",
            f"{item['symbol']} delta = {metrics['delta']}",
            f"{item['symbol']} cumulative_delta = {metrics['cumulative_delta']}",
            f"{item['symbol']} last_bid = {metrics['last_bid']}",
            f"{item['symbol']} last_ask = {metrics['last_ask']}",
            f"{item['symbol']} dom_available = {metrics['dom_available']}",
            f"{item['symbol']} dom_bid_depth = {metrics['dom_bid_depth']}",
            f"{item['symbol']} dom_ask_depth = {metrics['dom_ask_depth']}",
            f"{item['symbol']} order_book_update_type = {metrics['order_book_update_type']}",
            "",
        ]

    summary_path.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"report = {report_path}")
    print(f"summary = {summary_path}")


if __name__ == "__main__":
    main()