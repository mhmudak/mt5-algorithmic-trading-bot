import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run_command(name, cmd, timeout=180):
    print()
    print(f"[PHASE 1 VALIDATION] running: {name}")
    print("command =", " ".join(str(part) for part in cmd))

    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    completed = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
        env=env,
        encoding="utf-8",
        errors="replace",
    )

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()

    if stdout:
        print(stdout)

    if stderr:
        print("[STDERR]")
        print(stderr)

    ok = completed.returncode == 0

    print(f"[PHASE 1 VALIDATION] {name} ok = {ok}")

    return {
        "name": name,
        "command": [str(part) for part in cmd],
        "returncode": completed.returncode,
        "ok": ok,
        "stdout_tail": stdout[-5000:] if stdout else "",
        "stderr_tail": stderr[-5000:] if stderr else "",
    }


def load_json(path):
    path = Path(path)

    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)

    return path


def resolve_output_dir(source_dir):
    account_name = Path(source_dir).name
    return PROJECT_ROOT / "data" / "strategy_intelligence" / account_name


def check_required_files():
    required_files = [
        "src/confirmation_engine.py",
        "src/confirmation_observation_logger.py",
        "src/confirmation_risk_notifier.py",
        "scripts/analyze_confirmation_observations.py",
        "scripts/smoke_confirmation_pipeline.py",
        "scripts/audit_confirmation_coverage.py",
        "scripts/test_confirmation_risk_telegram.py",
        "scripts/check_confirmation_runtime_safety.py",
        "scripts/analyze_strategy_performance.py",
        "src/live_bot.py",
        "config/settings.py",
    ]

    results = {}

    for item in required_files:
        path = PROJECT_ROOT / item
        results[item] = path.exists()

    return results


def check_source_markers():
    markers = {}

    files_and_markers = {
        "src/confirmation_engine.py": [
            "run_universal_confirmation",
            "CONSOLIDATION_POLICY_AUDIT",
            "COMEX_ORDER_FLOW",
            "SOURCE_TRUE_ORDER_FLOW",
            "MT5_VOLUME_PROXY",
        ],
        "src/live_bot.py": [
            "observe_universal_confirmation_for_setup",
            "observe_universal_confirmation_from_scope",
            "log_confirmation_observation",
            "maybe_notify_confirmation_risk",
            "ENABLE_CONFIRMATION_ENGINE_OBSERVE_ONLY",
        ],
        "src/confirmation_risk_notifier.py": [
            "build_confirmation_risk_alert",
            "maybe_notify_confirmation_risk",
            "resolve_telegram_sender",
            "get_telegram_sender_diagnostics",
        ],
        "scripts/analyze_strategy_performance.py": [
            "run_confirmation_observation_analyzer_from_strategy_analyzer",
            "inject_confirmation_summary_into_strategy_report",
        ],
        "config/settings.py": [
            "TELEGRAM_NOTIFY_CONFIRMATION_ENGINE_RISK",
            "ENABLE_CONFIRMATION_OBSERVATION_ANALYZER_IN_MAIN_ANALYZER",
            "ENABLE_CONFIRMATION_SUMMARY_IN_STRATEGY_REPORT",
            "ENABLE_CONFIRMATION_ENGINE_OBSERVE_ONLY",
            "CONFIRMATION_ENGINE_OBSERVE_ONLY_MODE",
        ],
    }

    for relative_path, required_markers in files_and_markers.items():
        path = PROJECT_ROOT / relative_path
        text = path.read_text(encoding="utf-8") if path.exists() else ""

        markers[relative_path] = {
            marker: marker in text
            for marker in required_markers
        }

    return markers


def main():
    parser = argparse.ArgumentParser(
        description="Run final Phase 1 confirmation-engine validation."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
        help="Account data directory.",
    )

    parser.add_argument(
        "--min-samples",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--skip-main-analyzer",
        action="store_true",
        help="Skip analyze_strategy_performance.py run.",
    )

    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    output_dir = resolve_output_dir(source_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    commands = []

    commands.append(
        run_command(
            "compileall",
            [sys.executable, "-m", "compileall", "config", "src", "scripts"],
            timeout=180,
        )
    )

    commands.append(
        run_command(
            "confirmation_pipeline_smoke",
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "smoke_confirmation_pipeline.py"),
                "--source-dir",
                str(source_dir),
            ],
            timeout=180,
        )
    )

    commands.append(
        run_command(
            "telegram_risk_dry_run",
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "test_confirmation_risk_telegram.py"),
            ],
            timeout=120,
        )
    )

    commands.append(
        run_command(
            "runtime_safety",
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "check_confirmation_runtime_safety.py"),
                "--output-dir",
                str(output_dir),
            ],
            timeout=120,
        )
    )

    commands.append(
        run_command(
            "coverage_audit",
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "audit_confirmation_coverage.py"),
                "--observe-window-lines",
                "120",
                "--output-dir",
                str(output_dir),
            ],
            timeout=120,
        )
    )

    commands.append(
        run_command(
            "confirmation_observation_analyzer",
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "analyze_confirmation_observations.py"),
                "--source-dir",
                str(source_dir),
                "--min-samples",
                str(args.min_samples),
            ],
            timeout=180,
        )
    )

    if not args.skip_main_analyzer:
        commands.append(
            run_command(
                "main_strategy_analyzer_with_confirmation_integration",
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts" / "analyze_strategy_performance.py"),
                    "--source-dir",
                    str(source_dir),
                    "--min-samples",
                    str(args.min_samples),
                ],
                timeout=240,
            )
        )

    required_files = check_required_files()
    source_markers = check_source_markers()

    coverage_summary_path = output_dir / "confirmation_coverage_summary.json"
    runtime_safety_path = output_dir / "confirmation_runtime_safety_report.json"
    confirmation_summary_path = output_dir / "confirmation_observation_summary.json"
    strategy_report_path = output_dir / "strategy_performance_report.json"

    coverage_summary = load_json(coverage_summary_path) or {}
    runtime_safety = load_json(runtime_safety_path) or {}
    confirmation_summary = load_json(confirmation_summary_path) or {}
    strategy_report = load_json(strategy_report_path) or {}

    coverage_ok = (
        coverage_summary.get("missing_observe_before_execute_trade_count") == 0
        and coverage_summary.get("coverage_rate") == 1.0
    )

    runtime_safety_ok = runtime_safety.get("all_ok") is True

    confirmation_summary_in_strategy_report = "confirmation_engine" in strategy_report

    required_files_ok = all(required_files.values())

    source_markers_ok = all(
        all(markers.values())
        for markers in source_markers.values()
    )

    commands_ok = all(item["ok"] for item in commands)

    all_ok = all([
        commands_ok,
        required_files_ok,
        source_markers_ok,
        coverage_ok,
        runtime_safety_ok,
        confirmation_summary_in_strategy_report or args.skip_main_analyzer,
    ])

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 1P",
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "all_ok": all_ok,
        "commands_ok": commands_ok,
        "required_files_ok": required_files_ok,
        "source_markers_ok": source_markers_ok,
        "coverage_ok": coverage_ok,
        "runtime_safety_ok": runtime_safety_ok,
        "confirmation_summary_in_strategy_report": confirmation_summary_in_strategy_report,
        "required_files": required_files,
        "source_markers": source_markers,
        "coverage_summary": {
            "execute_trade_call_count": coverage_summary.get("execute_trade_call_count"),
            "observe_call_count": coverage_summary.get("observe_call_count"),
            "covered_execute_trade_call_count": coverage_summary.get("covered_execute_trade_call_count"),
            "missing_observe_before_execute_trade_count": coverage_summary.get("missing_observe_before_execute_trade_count"),
            "coverage_rate": coverage_summary.get("coverage_rate"),
        },
        "runtime_safety_summary": {
            "all_ok": runtime_safety.get("all_ok"),
            "coverage_rate": (runtime_safety.get("coverage_summary") or {}).get("coverage_rate"),
            "missing_observe_before_execute_trade_count": (
                runtime_safety.get("coverage_summary") or {}
            ).get("missing_observe_before_execute_trade_count"),
        },
        "confirmation_observation_summary": {
            "observation_count": confirmation_summary.get("observation_count"),
            "module_row_count": confirmation_summary.get("module_row_count"),
            "matched_outcome_count": confirmation_summary.get("matched_outcome_count"),
            "known_outcome_count": confirmation_summary.get("known_outcome_count"),
            "min_samples": confirmation_summary.get("min_samples"),
        },
        "strategy_report_confirmation_engine": strategy_report.get("confirmation_engine"),
        "commands": commands,
        "notes": [
            "No MT5 order is opened by this validation script.",
            "Telegram test is dry-run only unless scripts/test_confirmation_risk_telegram.py is run with --send.",
            "Confirmation engine remains observe-only.",
            "Coverage means every execute_trade path has an observation call before execution.",
            "COMEX_ORDER_FLOW remains disabled until a real COMEX futures provider is connected.",
        ],
    }

    report_path = output_dir / "phase1_confirmation_validation_report.json"
    write_json(report_path, report)

    print()
    print("[PHASE 1 VALIDATION REPORT]")
    print("all_ok =", all_ok)
    print("commands_ok =", commands_ok)
    print("required_files_ok =", required_files_ok)
    print("source_markers_ok =", source_markers_ok)
    print("coverage_ok =", coverage_ok)
    print("runtime_safety_ok =", runtime_safety_ok)
    print("confirmation_summary_in_strategy_report =", confirmation_summary_in_strategy_report)
    print("report =", report_path)

    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
