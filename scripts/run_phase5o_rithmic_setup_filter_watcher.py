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

REPORT_PATH = RITHMIC_DIR / "phase5o_rithmic_setup_filter_watcher_report.json"
SUMMARY_PATH = RITHMIC_DIR / "phase5o_rithmic_setup_filter_watcher_summary.txt"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_command(name: str, cmd: list[str]) -> dict[str, Any]:
    started = time.time()

    result: dict[str, Any] = {
        "name": name,
        "cmd": cmd,
        "started_at": now_iso(),
        "success": False,
        "returncode": None,
        "duration_seconds": None,
        "stdout_tail": "",
        "stderr_tail": "",
    }

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        result["returncode"] = proc.returncode
        result["success"] = proc.returncode == 0
        result["stdout_tail"] = (proc.stdout or "")[-3000:]
        result["stderr_tail"] = (proc.stderr or "")[-3000:]

    except Exception as exc:
        result["returncode"] = "ERROR"
        result["success"] = False
        result["stderr_tail"] = repr(exc)

    result["duration_seconds"] = round(time.time() - started, 2)
    result["finished_at"] = now_iso()

    return result


def run_cycle(args: argparse.Namespace) -> dict[str, Any]:
    RITHMIC_DIR.mkdir(parents=True, exist_ok=True)

    commands: list[tuple[str, list[str]]] = []

    refresh_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_phase5j_rithmic_manual_refresh_pipeline.py"),
        "--symbols",
        args.symbols,
        "--exchange",
        args.exchange,
        "--duration-seconds",
        str(args.duration_seconds),
    ]

    if args.include_order_book:
        refresh_cmd.append("--include-order-book")

    commands.append(("phase5j_rithmic_refresh", refresh_cmd))

    commands.append((
        "phase5l_rithmic_data_quality_gate",
        [
            sys.executable,
            str(ROOT / "scripts" / "check_phase5l_rithmic_data_quality_gate.py"),
            "--symbols",
            args.symbols,
            "--max-bbo-spread",
            str(args.max_bbo_spread),
            "--min-trades",
            str(args.min_trades),
            "--require-two-sided-dom",
        ],
    ))

    phase5n_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "notify_phase5n_setup_gated_rithmic_filter.py"),
    ]

    if args.send_telegram:
        phase5n_cmd.append("--send-telegram")

    commands.append(("phase5n_setup_gated_rithmic_filter", phase5n_cmd))

    results = []

    for name, cmd in commands:
        print(f"[RUN] {name}")
        result = run_command(name, cmd)
        results.append(result)
        print(f"{name} | success={result['success']} | returncode={result['returncode']} | duration={result['duration_seconds']}")

    all_ok = all(item["success"] for item in results)

    report = {
        "phase": "PHASE_5O_RITHMIC_SETUP_FILTER_WATCHER",
        "mode": "OBSERVE_ONLY",
        "updated_at": now_iso(),
        "symbols": args.symbols,
        "exchange": args.exchange,
        "duration_seconds": args.duration_seconds,
        "include_order_book": args.include_order_book,
        "send_telegram": args.send_telegram,
        "all_ok": all_ok,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "trade_action": "NO_AUTO_TRADE",
        "manual_review_only": True,
        "results": results,
        "recommendation": "Run as a separate observe-only watcher. Do not connect to live_bot decisions.",
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 5O RITHMIC SETUP-FILTER WATCHER]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"symbols = {report['symbols']}",
        f"exchange = {report['exchange']}",
        f"duration_seconds = {report['duration_seconds']}",
        f"include_order_book = {report['include_order_book']}",
        f"send_telegram = {report['send_telegram']}",
        f"all_ok = {report['all_ok']}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        f"trade_action = {report['trade_action']}",
        f"manual_review_only = {report['manual_review_only']}",
        "",
        "[COMMANDS]",
    ]

    for item in results:
        lines.append(
            f"{item['name']} | success={item['success']} | returncode={item['returncode']} | duration={item['duration_seconds']}"
        )

    lines += [
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nreport = {REPORT_PATH}")
    print(f"summary = {SUMMARY_PATH}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="GCQ6,MGCQ6")
    parser.add_argument("--exchange", default="COMEX")
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--interval-seconds", type=int, default=900)
    parser.add_argument("--include-order-book", action="store_true")
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--max-bbo-spread", type=float, default=5.0)
    parser.add_argument("--min-trades", type=int, default=5)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if args.interval_seconds < 300 and not args.once:
        raise SystemExit("[STOP] Use interval >= 300 seconds for Rithmic watcher to avoid excessive reconnects.")

    while True:
        cycle_started = time.time()
        run_cycle(args)

        if args.once:
            break

        elapsed = time.time() - cycle_started
        sleep_for = max(30, args.interval_seconds - elapsed)

        print(f"\n[SLEEP] next Rithmic watcher cycle in {round(sleep_for, 1)} seconds")
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()