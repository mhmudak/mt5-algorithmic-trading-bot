from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RITHMIC_DIR = ROOT / "data" / "order_flow" / "rithmic"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace("\\", "_").replace(".", "_")


def parse_symbols(value: str) -> list[str]:
    symbols = []

    for part in str(value or "").replace(";", ",").split(","):
        symbol = part.strip()
        if symbol:
            symbols.append(symbol)

    return symbols or ["GCQ6"]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def validate_symbol(symbol: str, *, max_bbo_spread: float, min_trades: int, require_two_sided_dom: bool) -> dict[str, Any]:
    state_path = RITHMIC_DIR / f"{safe_symbol(symbol)}_phase5c_rithmic_state_latest.json"
    bridge_path = RITHMIC_DIR / f"{safe_symbol(symbol)}_phase5g_rithmic_monitoring_bridge.json"

    state = load_json(state_path)
    bridge = load_json(bridge_path)

    connection = state.get("connection") or {}
    freshness = state.get("freshness") or {}
    sample = state.get("sample") or {}
    bbo = state.get("bbo") or {}
    order_book = state.get("order_book") or {}
    metrics = state.get("adapter_compatible_metrics") or {}

    login_ok = bool(connection.get("login_ok"))
    market_data_ok = bool(connection.get("market_data_ok"))

    last_bid = as_float(bbo.get("last_bid"))
    last_ask = as_float(bbo.get("last_ask"))
    spread = last_ask - last_bid if last_bid > 0 and last_ask > 0 else None

    trade_count = as_int(sample.get("rolling_trade_count"))
    bbo_count = as_int(sample.get("bbo_count"))
    nonzero_bbo_count = as_int(sample.get("nonzero_bbo_count"))
    order_book_count = as_int(sample.get("order_book_count"))

    dom_available = bool(metrics.get("dom_available") or order_book.get("available"))
    dom_bid_depth = as_int(metrics.get("dom_bid_depth"))
    dom_ask_depth = as_int(metrics.get("dom_ask_depth"))

    checks = {
        "state_snapshot_exists": bool(state),
        "bridge_snapshot_exists": bool(bridge),
        "login_ok": login_ok,
        "market_data_ok": market_data_ok,
        "trade_count_enough": trade_count >= min_trades,
        "bbo_seen": bbo_count > 0,
        "nonzero_bbo_seen": nonzero_bbo_count > 0,
        "bid_positive": last_bid > 0,
        "ask_positive": last_ask > 0,
        "spread_positive": spread is not None and spread > 0,
        "spread_reasonable": spread is not None and spread <= max_bbo_spread,
        "order_book_seen": order_book_count > 0,
        "dom_available": dom_available,
        "two_sided_dom": dom_bid_depth > 0 and dom_ask_depth > 0,
        "decision_impact_none": state.get("decision_impact") == "NONE" and bridge.get("decision_impact") == "NONE",
        "cannot_influence_decision": bridge.get("can_influence_decision") is False,
    }

    hard_failures = []

    for key in [
        "state_snapshot_exists",
        "bridge_snapshot_exists",
        "login_ok",
        "market_data_ok",
        "decision_impact_none",
        "cannot_influence_decision",
    ]:
        if not checks[key]:
            hard_failures.append(key)

    quality_failures = []

    for key in [
        "trade_count_enough",
        "bbo_seen",
        "nonzero_bbo_seen",
        "bid_positive",
        "ask_positive",
        "spread_positive",
        "spread_reasonable",
        "order_book_seen",
        "dom_available",
    ]:
        if not checks[key]:
            quality_failures.append(key)

    if require_two_sided_dom and not checks["two_sided_dom"]:
        quality_failures.append("two_sided_dom")

    if hard_failures:
        status = "RITHMIC_DATA_GATE_FAILED_HARD"
    elif quality_failures:
        status = "RITHMIC_CONNECTED_BUT_DATA_QUALITY_BAD"
    else:
        status = "RITHMIC_DATA_QUALITY_VALIDATED_OBSERVE_ONLY"

    return {
        "symbol": symbol,
        "status": status,
        "state_path": str(state_path),
        "bridge_path": str(bridge_path),
        "checks": checks,
        "hard_failures": hard_failures,
        "quality_failures": quality_failures,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_live_decision": False,
        "safe_for_execution": False,
        "metrics": {
            "trade_count": trade_count,
            "bbo_count": bbo_count,
            "nonzero_bbo_count": nonzero_bbo_count,
            "order_book_count": order_book_count,
            "last_bid": last_bid,
            "last_ask": last_ask,
            "spread": spread,
            "max_allowed_spread": max_bbo_spread,
            "dom_available": dom_available,
            "dom_bid_depth": dom_bid_depth,
            "dom_ask_depth": dom_ask_depth,
            "dom_depth_imbalance": metrics.get("dom_depth_imbalance"),
            "order_book_update_type": order_book.get("last_update_type_name"),
            "delta": metrics.get("delta"),
            "cumulative_delta": metrics.get("cumulative_delta"),
            "last_trade_age_seconds": freshness.get("last_trade_age_seconds"),
            "last_bbo_age_seconds": freshness.get("last_bbo_age_seconds"),
            "last_order_book_age_seconds": freshness.get("last_order_book_age_seconds"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="GCQ6,MGCQ6")
    parser.add_argument("--max-bbo-spread", type=float, default=5.0)
    parser.add_argument("--min-trades", type=int, default=5)
    parser.add_argument("--require-two-sided-dom", action="store_true")
    args = parser.parse_args()

    RITHMIC_DIR.mkdir(parents=True, exist_ok=True)

    symbols = parse_symbols(args.symbols)

    validations = [
        validate_symbol(
            symbol,
            max_bbo_spread=args.max_bbo_spread,
            min_trades=args.min_trades,
            require_two_sided_dom=args.require_two_sided_dom,
        )
        for symbol in symbols
    ]

    all_hard_ok = all(not item["hard_failures"] for item in validations)
    all_quality_ok = all(not item["quality_failures"] for item in validations)

    if not all_hard_ok:
        overall_status = "RITHMIC_DATA_GATE_FAILED_HARD"
        recommendation = "Fix connection/snapshot/safety problems before continuing."
    elif not all_quality_ok:
        overall_status = "RITHMIC_CONNECTED_BUT_DATA_QUALITY_BAD"
        recommendation = "Rithmic parser works, but feed quality is not reliable enough for decision logic. Keep observe-only."
    else:
        overall_status = "RITHMIC_DATA_QUALITY_VALIDATED_OBSERVE_ONLY"
        recommendation = "Rithmic data quality passed observe-only validation. Still do not enable decision impact without a separate approval phase."

    report = {
        "phase": "PHASE_5L_RITHMIC_DATA_QUALITY_GATE",
        "mode": "OBSERVE_ONLY",
        "updated_at": now_iso(),
        "symbols": symbols,
        "max_bbo_spread": args.max_bbo_spread,
        "min_trades": args.min_trades,
        "require_two_sided_dom": args.require_two_sided_dom,
        "overall_status": overall_status,
        "all_hard_ok": all_hard_ok,
        "all_quality_ok": all_quality_ok,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_live_decision": False,
        "safe_for_execution": False,
        "validations": validations,
        "recommendation": recommendation,
    }

    report_path = RITHMIC_DIR / "phase5l_rithmic_data_quality_gate_report.json"
    summary_path = RITHMIC_DIR / "phase5l_rithmic_data_quality_gate_summary.txt"

    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 5L RITHMIC DATA QUALITY GATE]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"symbols = {', '.join(symbols)}",
        f"max_bbo_spread = {args.max_bbo_spread}",
        f"min_trades = {args.min_trades}",
        f"require_two_sided_dom = {args.require_two_sided_dom}",
        f"overall_status = {overall_status}",
        f"all_hard_ok = {all_hard_ok}",
        f"all_quality_ok = {all_quality_ok}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        f"recommendation = {recommendation}",
        "",
        "[SYMBOLS]",
    ]

    for item in validations:
        m = item["metrics"]
        lines += [
            f"{item['symbol']} status = {item['status']}",
            f"{item['symbol']} hard_failures = {item['hard_failures']}",
            f"{item['symbol']} quality_failures = {item['quality_failures']}",
            f"{item['symbol']} trade_count = {m['trade_count']}",
            f"{item['symbol']} bbo_count = {m['bbo_count']}",
            f"{item['symbol']} nonzero_bbo_count = {m['nonzero_bbo_count']}",
            f"{item['symbol']} order_book_count = {m['order_book_count']}",
            f"{item['symbol']} last_bid = {m['last_bid']}",
            f"{item['symbol']} last_ask = {m['last_ask']}",
            f"{item['symbol']} spread = {m['spread']}",
            f"{item['symbol']} dom_available = {m['dom_available']}",
            f"{item['symbol']} dom_bid_depth = {m['dom_bid_depth']}",
            f"{item['symbol']} dom_ask_depth = {m['dom_ask_depth']}",
            f"{item['symbol']} order_book_update_type = {m['order_book_update_type']}",
            f"{item['symbol']} delta = {m['delta']}",
            f"{item['symbol']} cumulative_delta = {m['cumulative_delta']}",
            "",
        ]

    summary_path.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"report = {report_path}")
    print(f"summary = {summary_path}")


if __name__ == "__main__":
    main()