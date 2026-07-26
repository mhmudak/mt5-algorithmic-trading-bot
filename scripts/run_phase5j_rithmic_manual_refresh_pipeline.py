from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "order_flow" / "rithmic"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_symbols(value: str) -> list[str]:
    symbols = []

    for part in str(value or "").replace(";", ",").split(","):
        symbol = part.strip()
        if symbol:
            symbols.append(symbol)

    return symbols or ["GCQ6"]


def run_command(label: str, command: list[str], *, env: dict[str, str] | None = None, timeout: int = 240) -> dict:
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
            env=env,
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="GCQ6,MGCQ6")
    parser.add_argument("--exchange", default="COMEX")
    parser.add_argument("--duration-seconds", type=int, default=30)
    parser.add_argument("--include-order-book", action="store_true")
    parser.add_argument("--telegram-check", action="store_true")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    python = sys.executable
    symbols = parse_symbols(args.symbols)
    primary_symbol = symbols[0]

    env = os.environ.copy()
    env["RITHMIC_SYMBOL"] = primary_symbol

    commands: list[tuple[str, list[str], int]] = []

    for symbol in symbols:
        state_command = [
            python,
            str(ROOT / "scripts" / "run_phase5c_rithmic_state_cache.py"),
            "--symbol",
            symbol,
            "--exchange",
            args.exchange,
            "--duration-seconds",
            str(args.duration_seconds),
        ]

        if args.include_order_book:
            state_command.append("--include-order-book")

        commands.extend([
            (
                f"phase5j_state_cache_{symbol}",
                state_command,
                max(90, args.duration_seconds + 60),
            ),
            (
                f"phase5f_provider_status_{symbol}",
                [
                    python,
                    str(ROOT / "scripts" / "build_phase5f_rithmic_provider_status.py"),
                    "--symbol",
                    symbol,
                ],
                120,
            ),
            (
                f"phase5g_monitoring_bridge_{symbol}",
                [
                    python,
                    str(ROOT / "scripts" / "build_phase5g_rithmic_monitoring_bridge.py"),
                    "--symbol",
                    symbol,
                ],
                120,
            ),
        ])

    commands.extend([
        (
            "phase4_orderflow_status",
            [python, str(ROOT / "scripts" / "build_phase4_orderflow_status.py")],
            120,
        ),
        (
            "phase3_dashboard_summary",
            [python, str(ROOT / "scripts" / "build_phase3_dashboard_summary.py")],
            120,
        ),
    ])

    if args.telegram_check:
        commands.append(
            (
                "phase4_unified_telegram_monitoring",
                [python, str(ROOT / "scripts" / "notify_phase4_unified_monitoring_telegram.py")],
                120,
            )
        )

    print("[START] Phase 5J Rithmic manual refresh pipeline")
    print("symbols =", ", ".join(symbols))
    print("primary_symbol =", primary_symbol)
    print("exchange =", args.exchange)
    print("duration_seconds =", args.duration_seconds)
    print("include_order_book =", args.include_order_book)
    print("telegram_check =", args.telegram_check)
    print("decision_impact = NONE")
    print("can_influence_decision = False")
    print("")

    results = []

    for label, command, timeout in commands:
        print("[RUN]", label)
        result = run_command(label, command, env=env, timeout=timeout)
        results.append(result)
        print(
            label,
            "| success=",
            result["success"],
            "| returncode=",
            result["returncode"],
            "| duration=",
            result["duration_seconds"],
        )

        if not result["success"]:
            print("[STDERR]")
            print(result.get("stderr_tail") or "")
            print("[STDOUT]")
            print(result.get("stdout_tail") or "")

    report = {
        "phase": "PHASE_5J_RITHMIC_MANUAL_REFRESH_PIPELINE",
        "mode": "OBSERVE_ONLY",
        "updated_at": now_iso(),
        "symbols": symbols,
        "primary_symbol": primary_symbol,
        "exchange": args.exchange,
        "duration_seconds": args.duration_seconds,
        "include_order_book": args.include_order_book,
        "telegram_check": args.telegram_check,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_live_decision": False,
        "safe_for_execution": False,
        "all_commands_ok": all(item.get("success") for item in results),
        "commands": results,
        "recommendation": (
            "RITHMIC_MANUAL_REFRESH_OK_OBSERVE_ONLY"
            if all(item.get("success") for item in results)
            else "REVIEW_FAILED_PHASE5J_COMMANDS"
        ),
    }

    report_path = OUTPUT_DIR / "phase5j_rithmic_manual_refresh_pipeline_report.json"
    summary_path = OUTPUT_DIR / "phase5j_rithmic_manual_refresh_pipeline_summary.txt"

    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 5J RITHMIC MANUAL REFRESH PIPELINE]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"symbols = {', '.join(symbols)}",
        f"primary_symbol = {primary_symbol}",
        f"exchange = {args.exchange}",
        f"duration_seconds = {args.duration_seconds}",
        f"include_order_book = {args.include_order_book}",
        f"telegram_check = {args.telegram_check}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        f"all_commands_ok = {report['all_commands_ok']}",
        f"recommendation = {report['recommendation']}",
        "",
        "[COMMANDS]",
    ]

    for item in results:
        lines.append(
            f"{item.get('label')} | success={item.get('success')} | "
            f"returncode={item.get('returncode')} | duration={item.get('duration_seconds')}"
        )

    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("")
    print("\n".join(lines))
    print("")
    print("report =", report_path)
    print("summary =", summary_path)

    if not report["all_commands_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()