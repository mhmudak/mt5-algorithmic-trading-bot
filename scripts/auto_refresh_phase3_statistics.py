import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ACCOUNT_DIR = ROOT / "data" / "accounts" / "Tickmill-Demo_25323531"
DEFAULT_INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

WATCH_FILES = [
    "trades.json",
    "setup_outcomes.json",
    "confirmation_observations.jsonl",
]


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def file_state(account_dir):
    state = {}

    for name in WATCH_FILES:
        path = account_dir / name
        if path.exists():
            stat = path.stat()
            state[name] = {
                "exists": True,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }
        else:
            state[name] = {
                "exists": False,
                "size": 0,
                "mtime": None,
            }

    return state


def count_json_records(path):
    try:
        if not path.exists():
            return 0

        data = json.loads(path.read_text(encoding="utf-8"))

        if isinstance(data, list):
            return len(data)

        if isinstance(data, dict):
            for key in ("trades", "setups", "outcomes", "items", "records"):
                if isinstance(data.get(key), list):
                    return len(data[key])
            return len(data)

        return 0
    except Exception:
        return None


def count_jsonl_records(path):
    try:
        if not path.exists():
            return 0

        count = 0
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
    except Exception:
        return None


def run_command(label, command, timeout=180):
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
        result["stdout_tail"] = (proc.stdout or "")[-4000:]
        result["stderr_tail"] = (proc.stderr or "")[-4000:]

    except subprocess.TimeoutExpired as exc:
        result["returncode"] = "TIMEOUT"
        result["stderr_tail"] = str(exc)

    except Exception as exc:
        result["returncode"] = "ERROR"
        result["stderr_tail"] = repr(exc)

    result["duration_seconds"] = round(time.time() - started, 2)
    return result


def refresh_statistics(account_dir, intel_dir):
    intel_dir.mkdir(parents=True, exist_ok=True)

    python = sys.executable

    commands = [
        (
            "postfix_trade_reconciliation",
            [python, str(ROOT / "scripts" / "check_postfix_trade_reconciliation.py"), "--source-dir", str(account_dir)],
        ),
        (
            "postfix_outcome_reconciliation",
            [python, str(ROOT / "scripts" / "check_postfix_outcome_reconciliation.py"), "--source-dir", str(account_dir)],
        ),
        (
            "clean_postfix_trade_statistics",
            [python, str(ROOT / "scripts" / "analyze_clean_postfix_trade_statistics.py"), "--source-dir", str(account_dir)],
        ),
        (
            "clean_strategy_setup_profitability",
            [python, str(ROOT / "scripts" / "analyze_clean_strategy_setup_profitability.py"), "--source-dir", str(account_dir)],
        ),
        (
            "post_extra_be_tuning_performance",
            [python, str(ROOT / "scripts" / "check_post_extra_be_tuning_performance.py"), "--source-dir", str(account_dir)],
        ),
        (
            "phase3_post_baseline",
            [python, str(ROOT / "scripts" / "analyze_phase3_post_baseline.py")],
        ),
        (
            "phase3_readiness_gate",
            [python, str(ROOT / "scripts" / "check_phase3_readiness_gate.py")],
        ),
        (
            "phase3_confirmation_patterns",
            [python, str(ROOT / "scripts" / "analyze_phase3_confirmation_patterns.py")],
        ),
        (
            "phase3_mtf_conflicts",
            [python, str(ROOT / "scripts" / "analyze_phase3_mtf_conflicts.py")],
        ),
        (
            "phase3_low_rr_slippage_recovery",
            [python, str(ROOT / "scripts" / "analyze_phase3_low_rr_slippage_recovery.py")],
        ),
        (
            "phase3_poc_context",
            [python, str(ROOT / "scripts" / "analyze_phase3_poc_context.py"), "--symbol", "XAUUSD", "--timeframe", "M15", "--bars", "500", "--bin-size", "0.50"],
        ),
        (
            "phase3_liquidity_poc_context",
            [python, str(ROOT / "scripts" / "analyze_phase3_liquidity_poc_context.py"), "--symbol", "XAUUSD", "--timeframe", "M15", "--bars", "500", "--bin-size", "0.50"],
        ),
        (
            "phase3_session_poc_confirmation",
            [python, str(ROOT / "scripts" / "analyze_phase3_session_poc_confirmation.py"), "--symbol", "XAUUSD", "--timeframe", "M15", "--bars", "500", "--bin-size", "0.50"],
        ),
        (
            "phase3_confirmation_coverage_audit",
            [python, str(ROOT / "scripts" / "audit_phase3_confirmation_coverage.py")],
        ),
        (
            "phase3_decision_candidates",
            [python, str(ROOT / "scripts" / "build_phase3_decision_candidates.py")],
        ),
        (
            "phase3_dashboard_summary",
            [python, str(ROOT / "scripts" / "build_phase3_dashboard_summary.py")],
        ),
    ]

    results = []

    for label, command in commands:
        script_path = Path(command[1])

        if not script_path.exists():
            results.append({
                "label": label,
                "success": False,
                "returncode": "MISSING_SCRIPT",
                "command": command,
                "stderr_tail": f"Missing script: {script_path}",
            })
            continue

        results.append(run_command(label, command))

    trades_count = count_json_records(account_dir / "trades.json")
    outcomes_count = count_json_records(account_dir / "setup_outcomes.json")
    confirmations_count = count_jsonl_records(account_dir / "confirmation_observations.jsonl")

    report = {
        "phase": "PHASE_3A_AUTO_STATISTICS",
        "mode": "OBSERVE_ONLY",
        "updated_at": now_iso(),
        "account_dir": str(account_dir),
        "intel_dir": str(intel_dir),
        "counts": {
            "trades_json_records": trades_count,
            "setup_outcomes_records": outcomes_count,
            "confirmation_observations_records": confirmations_count,
        },
        "commands": results,
        "all_commands_ok": all(item.get("success") for item in results),
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": "COLLECT_MORE_POST_UPDATE_EVIDENCE",
    }

    report_path = intel_dir / "phase3_auto_statistics_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    summary_path = intel_dir / "phase3_auto_statistics_summary.txt"
    summary_lines = [
        "[PHASE 3A AUTO STATISTICS]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"trades = {trades_count}",
        f"setup_outcomes = {outcomes_count}",
        f"confirmation_observations = {confirmations_count}",
        f"all_commands_ok = {report['all_commands_ok']}",
        f"recommendation = {report['recommendation']}",
        "",
        "[COMMANDS]",
    ]

    for item in results:
        summary_lines.append(
            f"{item.get('label')} | success={item.get('success')} | returncode={item.get('returncode')} | duration={item.get('duration_seconds')}"
        )

    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

    print("\n".join(summary_lines))
    print(f"\nreport = {report_path}")
    print(f"summary = {summary_path}")

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-dir", default=str(DEFAULT_ACCOUNT_DIR))
    parser.add_argument("--intel-dir", default=str(DEFAULT_INTEL_DIR))
    parser.add_argument("--interval-seconds", type=int, default=900)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    account_dir = Path(args.account_dir)
    intel_dir = Path(args.intel_dir)
    state_path = intel_dir / "phase3_auto_statistics_state.json"

    intel_dir.mkdir(parents=True, exist_ok=True)

    last_state = None
    if state_path.exists():
        try:
            last_state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            last_state = None

    while True:
        current_state = file_state(account_dir)

        changed = current_state != last_state

        if changed:
            print(f"[{now_iso()}] Data changed. Refreshing Phase 3A statistics...")
            refresh_statistics(account_dir, intel_dir)
            state_path.write_text(json.dumps(current_state, indent=2), encoding="utf-8")
            last_state = current_state
        else:
            print(f"[{now_iso()}] No data change. Phase 3A statistics not refreshed.")

        if args.once:
            break

        time.sleep(max(60, args.interval_seconds))


if __name__ == "__main__":
    main()