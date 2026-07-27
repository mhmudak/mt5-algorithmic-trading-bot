from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_NAME = "Tickmill-Demo_25323531"
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / ACCOUNT_NAME

REPORT_PATH = INTEL_DIR / "phase5u_rithmic_real_orderflow_acceptance_report.json"
SUMMARY_PATH = INTEL_DIR / "phase5u_rithmic_real_orderflow_acceptance_summary.txt"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_command(name: str, args: list[str], timeout_seconds: int) -> dict[str, Any]:
    started = time.time()

    result = subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )

    return {
        "name": name,
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "duration_seconds": round(time.time() - started, 2),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def load_json_file(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    data["_source_path"] = str(path)
    return data


def looks_like_phase5l_report(data: dict[str, Any], path: Path) -> bool:
    phase = str(data.get("phase") or "").upper()
    overall_status = str(data.get("overall_status") or "").upper()
    filename = path.name.lower()

    has_validations = isinstance(data.get("validations"), list)

    return (
        "PHASE_5L" in phase
        or "phase5l" in filename
        or "rithmic_data_quality" in filename
        or (
            overall_status.startswith("RITHMIC_")
            and has_validations
            and "acceptance" not in filename
            and "phase5u" not in filename
        )
    )


def extract_json_paths_from_text(text: str) -> list[Path]:
    paths: list[Path] = []

    for match in re.findall(r"([A-Za-z]:\\\\[^\\r\\n]+?\\.json)", text or ""):
        paths.append(Path(match.strip()))

    for match in re.findall(r"([A-Za-z]:/[^\\r\\n]+?\\.json)", text or ""):
        paths.append(Path(match.strip()))

    return paths


def latest_phase5l_report(command_output: str = "") -> dict[str, Any] | None:
    # First: trust paths printed by Phase 5L itself.
    for path in extract_json_paths_from_text(command_output):
        if not path.exists():
            continue

        data = load_json_file(path)

        if data and looks_like_phase5l_report(data, path):
            return data

    # Second: search the account intelligence folder.
    candidates = sorted(
        INTEL_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for path in candidates:
        data = load_json_file(path)

        if data and looks_like_phase5l_report(data, path):
            return data

    # Third: fallback search all data JSON files.
    data_root = ROOT / "data"

    if data_root.exists():
        candidates = sorted(
            data_root.rglob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for path in candidates[:300]:
            data = load_json_file(path)

            if data and looks_like_phase5l_report(data, path):
                return data

    return None


def symbol_metrics_from_quality(quality: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    validations = quality.get("validations") or []

    if not isinstance(validations, list):
        return out

    for item in validations:
        if not isinstance(item, dict):
            continue

        symbol = str(item.get("symbol") or "UNKNOWN")
        metrics = item.get("metrics") or {}

        out[symbol] = {
            "status": item.get("status"),
            "hard_failures": item.get("hard_failures") or [],
            "quality_failures": item.get("quality_failures") or [],
            "trade_count": metrics.get("trade_count"),
            "bbo_count": metrics.get("bbo_count"),
            "nonzero_bbo_count": metrics.get("nonzero_bbo_count"),
            "spread": metrics.get("spread"),
            "last_bid": metrics.get("last_bid"),
            "last_ask": metrics.get("last_ask"),
            "dom_available": metrics.get("dom_available"),
            "dom_bid_depth": metrics.get("dom_bid_depth"),
            "dom_ask_depth": metrics.get("dom_ask_depth"),
            "dom_depth_imbalance": metrics.get("dom_depth_imbalance"),
            "delta": metrics.get("delta"),
            "cumulative_delta": metrics.get("cumulative_delta"),
        }

    return out


def bool_rate(values: list[bool]) -> float:
    if not values:
        return 0.0
    return round(sum(1 for v in values if v) / len(values), 4)


def calculate_acceptance(cycles: list[dict[str, Any]], min_quality_pass_ratio: float) -> dict[str, Any]:
    completed = [c for c in cycles if c.get("quality_report_loaded")]
    hard_ok_values = [bool(c.get("all_hard_ok")) for c in completed]
    quality_ok_values = [bool(c.get("all_quality_ok")) for c in completed]

    hard_ok_rate = bool_rate(hard_ok_values)
    quality_ok_rate = bool_rate(quality_ok_values)

    symbols: dict[str, dict[str, Any]] = {}

    for cycle in completed:
        for symbol, metrics in (cycle.get("symbols") or {}).items():
            s = symbols.setdefault(
                symbol,
                {
                    "cycles": 0,
                    "dom_available_values": [],
                    "two_sided_dom_values": [],
                    "positive_bbo_values": [],
                    "trade_count_values": [],
                    "spread_values": [],
                },
            )

            s["cycles"] += 1

            dom_bid = metrics.get("dom_bid_depth") or 0
            dom_ask = metrics.get("dom_ask_depth") or 0
            last_bid = metrics.get("last_bid") or 0
            last_ask = metrics.get("last_ask") or 0

            s["dom_available_values"].append(bool(metrics.get("dom_available")))
            s["two_sided_dom_values"].append(dom_bid > 0 and dom_ask > 0)
            s["positive_bbo_values"].append(last_bid > 0 and last_ask > 0)
            s["trade_count_values"].append(metrics.get("trade_count") or 0)

            if metrics.get("spread") is not None:
                s["spread_values"].append(metrics.get("spread"))

    symbol_summary: dict[str, dict[str, Any]] = {}

    for symbol, data in symbols.items():
        spreads = data["spread_values"]
        trade_counts = data["trade_count_values"]

        symbol_summary[symbol] = {
            "cycles": data["cycles"],
            "dom_available_rate": bool_rate(data["dom_available_values"]),
            "two_sided_dom_rate": bool_rate(data["two_sided_dom_values"]),
            "positive_bbo_rate": bool_rate(data["positive_bbo_values"]),
            "avg_trade_count": round(sum(trade_counts) / len(trade_counts), 2) if trade_counts else 0.0,
            "max_trade_count": max(trade_counts) if trade_counts else 0,
            "avg_spread": round(sum(spreads) / len(spreads), 4) if spreads else None,
            "max_spread": max(spreads) if spreads else None,
        }

    enough_cycles = len(completed) >= 3
    hard_ok_required = hard_ok_rate == 1.0
    quality_ok_required = quality_ok_rate >= min_quality_pass_ratio

    symbol_quality_required = True

    for data in symbol_summary.values():
        if data["positive_bbo_rate"] < min_quality_pass_ratio:
            symbol_quality_required = False
        if data["dom_available_rate"] < min_quality_pass_ratio:
            symbol_quality_required = False
        if data["two_sided_dom_rate"] < min_quality_pass_ratio:
            symbol_quality_required = False
        if data["avg_trade_count"] <= 0:
            symbol_quality_required = False

    accepted = (
        enough_cycles
        and hard_ok_required
        and quality_ok_required
        and symbol_quality_required
    )

    if accepted:
        overall_status = "READY_FOR_PHASE5V_OBSERVE_ONLY_PROVIDER_REGISTRATION"
        recommendation = (
            "Rithmic feed passed repeated acceptance checks. Next step can register "
            "Rithmic as the observe-only real order-flow provider, still with decision_impact NONE."
        )
    else:
        overall_status = "NOT_READY_PRODUCTION_DATA_REQUIRED_OR_FEED_BAD"
        recommendation = (
            "Do not connect Rithmic to decision logic. Use production/entitled COMEX data "
            "or retest during a highly active market session."
        )

    return {
        "overall_status": overall_status,
        "accepted": accepted,
        "completed_cycles": len(completed),
        "hard_ok_rate": hard_ok_rate,
        "quality_ok_rate": quality_ok_rate,
        "min_quality_pass_ratio": min_quality_pass_ratio,
        "symbol_summary": symbol_summary,
        "recommendation": recommendation,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="GCQ6,MGCQ6")
    parser.add_argument("--exchange", default="COMEX")
    parser.add_argument("--cycles", type=int, default=5)
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--sleep-seconds", type=int, default=60)
    parser.add_argument("--include-order-book", action="store_true")
    parser.add_argument("--min-trades", type=int, default=5)
    parser.add_argument("--max-bbo-spread", type=float, default=5.0)
    parser.add_argument("--require-two-sided-dom", action="store_true")
    parser.add_argument("--min-quality-pass-ratio", type=float, default=0.80)
    args = parser.parse_args()

    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    cycles: list[dict[str, Any]] = []

    print("[PHASE 5U RITHMIC REAL ORDER-FLOW ACCEPTANCE]")
    print(f"started_at = {now_iso()}")
    print(f"symbols = {args.symbols}")
    print(f"exchange = {args.exchange}")
    print(f"cycles = {args.cycles}")
    print(f"duration_seconds = {args.duration_seconds}")
    print(f"sleep_seconds = {args.sleep_seconds}")
    print("decision_impact = NONE")
    print("can_influence_decision = False")
    print("trade_action = NO_AUTO_TRADE")
    print("")

    for cycle_number in range(1, args.cycles + 1):
        print(f"[CYCLE {cycle_number}/{args.cycles}]")

        refresh_cmd = [
            "scripts/run_phase5j_rithmic_manual_refresh_pipeline.py",
            "--symbols",
            args.symbols,
            "--exchange",
            args.exchange,
            "--duration-seconds",
            str(args.duration_seconds),
        ]

        if args.include_order_book:
            refresh_cmd.append("--include-order-book")

        refresh = run_command(
            "phase5j_rithmic_refresh",
            refresh_cmd,
            timeout_seconds=args.duration_seconds * 4 + 120,
        )

        quality_cmd = [
            "scripts/check_phase5l_rithmic_data_quality_gate.py",
            "--symbols",
            args.symbols,
            "--max-bbo-spread",
            str(args.max_bbo_spread),
            "--min-trades",
            str(args.min_trades),
        ]

        if args.require_two_sided_dom:
            quality_cmd.append("--require-two-sided-dom")

        quality_command = run_command(
            "phase5l_rithmic_data_quality_gate",
            quality_cmd,
            timeout_seconds=120,
        )

        quality_output = (quality_command.get('stdout_tail') or '') + '\n' + (quality_command.get('stderr_tail') or '')
        quality = latest_phase5l_report(quality_output)
        quality_loaded = quality is not None

        cycle = {
            "cycle_number": cycle_number,
            "updated_at": now_iso(),
            "refresh_command": refresh,
            "quality_command": quality_command,
            "quality_report_loaded": quality_loaded,
            "quality_report_path": quality.get("_source_path") if quality else None,
            "overall_status": quality.get("overall_status") if quality else "QUALITY_REPORT_NOT_FOUND",
            "all_hard_ok": quality.get("all_hard_ok") if quality else False,
            "all_quality_ok": quality.get("all_quality_ok") if quality else False,
            "symbols": symbol_metrics_from_quality(quality) if quality else {},
        }

        cycles.append(cycle)

        print(f"refresh_success = {refresh['success']}")
        print(f"quality_success = {quality_command['success']}")
        print(f"quality_report_loaded = {quality_loaded}")
        print(f"quality_report_path = {cycle.get('quality_report_path')}")
        print(f"quality_status = {cycle['overall_status']}")
        print(f"all_hard_ok = {cycle['all_hard_ok']}")
        print(f"all_quality_ok = {cycle['all_quality_ok']}")

        for symbol, metrics in cycle["symbols"].items():
            print(
                f"- {symbol}: trades={metrics.get('trade_count')} "
                f"spread={metrics.get('spread')} "
                f"bid={metrics.get('last_bid')} ask={metrics.get('last_ask')} "
                f"dom={metrics.get('dom_available')} "
                f"bid_depth={metrics.get('dom_bid_depth')} "
                f"ask_depth={metrics.get('dom_ask_depth')}"
            )

        print("")

        if cycle_number < args.cycles:
            time.sleep(args.sleep_seconds)

    acceptance = calculate_acceptance(cycles, args.min_quality_pass_ratio)

    report = {
        "phase": "PHASE_5U_RITHMIC_REAL_ORDERFLOW_ACCEPTANCE",
        "updated_at": now_iso(),
        "mode": "OBSERVE_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "trade_action": "NO_AUTO_TRADE",
        "inputs": vars(args),
        "acceptance": acceptance,
        "cycles": cycles,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 5U RITHMIC REAL ORDER-FLOW ACCEPTANCE]",
        f"updated_at = {report['updated_at']}",
        "mode = OBSERVE_ONLY",
        "decision_impact = NONE",
        "can_influence_decision = False",
        "trade_action = NO_AUTO_TRADE",
        "",
        "[ACCEPTANCE]",
        f"overall_status = {acceptance['overall_status']}",
        f"accepted = {acceptance['accepted']}",
        f"completed_cycles = {acceptance['completed_cycles']}",
        f"hard_ok_rate = {acceptance['hard_ok_rate']}",
        f"quality_ok_rate = {acceptance['quality_ok_rate']}",
        f"min_quality_pass_ratio = {acceptance['min_quality_pass_ratio']}",
        "",
        "[SYMBOL SUMMARY]",
    ]

    for symbol, summary in acceptance["symbol_summary"].items():
        lines += [
            f"- {symbol}",
            f"  cycles = {summary['cycles']}",
            f"  positive_bbo_rate = {summary['positive_bbo_rate']}",
            f"  dom_available_rate = {summary['dom_available_rate']}",
            f"  two_sided_dom_rate = {summary['two_sided_dom_rate']}",
            f"  avg_trade_count = {summary['avg_trade_count']}",
            f"  max_trade_count = {summary['max_trade_count']}",
            f"  avg_spread = {summary['avg_spread']}",
            f"  max_spread = {summary['max_spread']}",
        ]

    lines += [
        "",
        "[RECOMMENDATION]",
        acceptance["recommendation"],
        "",
        "[REPORTS]",
        f"json = {REPORT_PATH}",
        f"summary = {SUMMARY_PATH}",
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))


if __name__ == "__main__":
    main()