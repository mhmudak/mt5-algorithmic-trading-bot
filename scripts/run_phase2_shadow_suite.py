import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_paths(source_dir):
    source_dir = Path(source_dir)

    if not source_dir.is_absolute():
        source_dir = PROJECT_ROOT / source_dir

    account_name = source_dir.name
    output_dir = PROJECT_ROOT / "data" / "strategy_intelligence" / account_name
    output_dir.mkdir(parents=True, exist_ok=True)

    return {
        "source_dir": source_dir,
        "account_name": account_name,
        "output_dir": output_dir,
        "suite_json": output_dir / "phase2_shadow_suite_report.json",
        "suite_txt": output_dir / "phase2_shadow_suite_output.txt",
        "history_jsonl": output_dir / "phase2_shadow_suite_history.jsonl",
        "history_csv": output_dir / "phase2_shadow_suite_history.csv",
        "phase2_shadow_report": output_dir / "phase2_shadow_policy_report.json",
        "phase2_shadow_readiness": output_dir / "phase2_shadow_readiness_report.json",
        "phase2_base_readiness": output_dir / "phase2_readiness_report.json",
        "outcome_quality_debug": output_dir / "confirmation_outcome_quality_debug.json",
        "duplicate_audit": output_dir / "confirmation_duplicate_observation_audit.json",
        "shadow_persistence": output_dir / "confirmation_shadow_persistence_report.json",
        "shadow_observe_only_safety": output_dir / "confirmation_shadow_observe_only_safety_report.json",
        "live_observation_staleness": output_dir / "confirmation_live_observation_staleness_report.json",
        "actual_shadow_maturity": output_dir / "actual_shadow_maturity_report.json",
        "trade_tracker_close_safety": output_dir / "trade_tracker_close_reconciliation_safety_report.json",
    }


def load_json(path):
    path = Path(path)

    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        return {
            "load_error": str(exc),
            "path": str(path),
        }


def run_step(name, command, cwd):
    started_at = datetime.now()

    print()
    print("=" * 100)
    print(f"[RUN] {name}")
    print(" ".join(str(x) for x in command))
    print("=" * 100)

    proc = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
    )

    ended_at = datetime.now()

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    if stdout:
        print(stdout.rstrip())

    if stderr:
        print()
        print("[STDERR]")
        print(stderr.rstrip())

    print(f"[EXIT CODE] {proc.returncode}")

    return {
        "name": name,
        "command": [str(x) for x in command],
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "exit_code": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout": stdout,
        "stderr": stderr,
    }


def compact_step_output(step):
    stdout = step.get("stdout") or ""
    stderr = step.get("stderr") or ""

    return {
        "name": step.get("name"),
        "exit_code": step.get("exit_code"),
        "ok": step.get("ok"),
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-2000:],
    }


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)

    return path


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        f.write(text)

    return path


def append_jsonl(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    return path


def append_csv_row(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    headers = [
        "created_at",
        "account_name",
        "all_steps_ok",
        "shadow_monitoring_ready",
        "shadow_calibration_ready",
        "blocking_ready",
        "recommendation",
        "raw_observation_count",
        "unique_setup_count",
        "duplicate_observation_count",
        "known_outcome_count_unique",
        "clean_known_outcome_count_unique",
        "mixed_tp_sl_count_unique",
        "outcome_quality_issue_count",
        "unique_setup_progress",
        "clean_known_outcome_progress",
        "remaining_unique_setups",
        "remaining_clean_known_outcomes",
        "duplicate_audit_rate",
        "duplicate_audit_group_count",
        "duplicate_audit_observation_count",
        "duplicate_audit_recommendation",
        "shadow_persistence_code_level_ready",
        "shadow_persistence_live_present",
        "shadow_persistence_recommendation",
        "shadow_persistence_populated_count",
        "shadow_persistence_missing_count",
        "shadow_persistence_populated_rate",
        "shadow_observe_only_safety_all_ok",
        "shadow_observe_only_safety_recommendation",
        "shadow_observe_only_settings_ok",
        "shadow_observe_only_policy_sample_ok",
        "shadow_observe_only_live_violation_count",
        "shadow_observe_only_live_status",
        "live_observation_staleness_status",
        "live_observation_staleness_recommendation",
        "live_observation_file_age_minutes",
        "live_observation_file_stale",
        "live_observation_file_mtime",
        "live_observation_shadow_count",
        "actual_shadow_maturity_ready",
        "actual_shadow_maturity_recommendation",
        "actual_shadow_observation_count",
        "actual_shadow_unique_setup_count",
        "actual_shadow_min_rows",
        "actual_shadow_min_unique_setups",
        "actual_shadow_rows_ready",
        "actual_shadow_unique_ready",
        "actual_shadow_legacy_or_missing_count",
        "trade_tracker_close_safety_all_ok",
        "trade_tracker_close_safety_recommendation",
        "trade_tracker_detect_before_closed",
        "trade_tracker_unresolved_keeps_open",
        "trade_tracker_resolved_saves_close_price",
        "trade_tracker_unresolved_pending_flag",
    ]

    exists = path.exists()

    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")

        if not exists:
            writer.writeheader()

        writer.writerow(row)

    return path


def safe_number(value, default=0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def build_progress_snapshot(summary, min_unique_setups, min_clean_known_outcomes):
    counts = summary.get("counts") or {}

    unique_setup_count = safe_number(counts.get("unique_setup_count"), 0)
    clean_known = safe_number(counts.get("clean_known_outcome_count_unique"), 0)

    unique_progress = round(unique_setup_count / min_unique_setups, 4) if min_unique_setups else None
    clean_progress = round(clean_known / min_clean_known_outcomes, 4) if min_clean_known_outcomes else None

    remaining_unique = max(0, int(min_unique_setups - unique_setup_count))
    remaining_clean = max(0, int(min_clean_known_outcomes - clean_known))

    return {
        "created_at": summary.get("created_at"),
        "account_name": summary.get("account_name"),
        "all_steps_ok": summary.get("all_steps_ok"),
        "shadow_monitoring_ready": summary.get("shadow_monitoring_ready"),
        "shadow_calibration_ready": summary.get("shadow_calibration_ready"),
        "blocking_ready": summary.get("blocking_ready"),
        "recommendation": summary.get("recommendation"),
        "raw_observation_count": counts.get("raw_observation_count"),
        "unique_setup_count": counts.get("unique_setup_count"),
        "duplicate_observation_count": counts.get("duplicate_observation_count"),
        "known_outcome_count_unique": counts.get("known_outcome_count_unique"),
        "clean_known_outcome_count_unique": counts.get("clean_known_outcome_count_unique"),
        "mixed_tp_sl_count_unique": counts.get("mixed_tp_sl_count_unique"),
        "outcome_quality_issue_count": counts.get("outcome_quality_issue_count"),
        "unique_setup_progress": unique_progress,
        "clean_known_outcome_progress": clean_progress,
        "remaining_unique_setups": remaining_unique,
        "remaining_clean_known_outcomes": remaining_clean,
        "duplicate_audit_rate": counts.get("duplicate_audit_rate"),
        "duplicate_audit_group_count": counts.get("duplicate_audit_group_count"),
        "duplicate_audit_observation_count": counts.get("duplicate_audit_observation_count"),
        "duplicate_audit_recommendation": counts.get("duplicate_audit_recommendation"),
        "shadow_persistence_code_level_ready": counts.get("shadow_persistence_code_level_ready"),
        "shadow_persistence_live_present": counts.get("shadow_persistence_live_present"),
        "shadow_persistence_recommendation": counts.get("shadow_persistence_recommendation"),
        "shadow_persistence_populated_count": counts.get("shadow_persistence_populated_count"),
        "shadow_persistence_missing_count": counts.get("shadow_persistence_missing_count"),
        "shadow_persistence_populated_rate": counts.get("shadow_persistence_populated_rate"),
        "shadow_observe_only_safety_all_ok": counts.get("shadow_observe_only_safety_all_ok"),
        "shadow_observe_only_safety_recommendation": counts.get("shadow_observe_only_safety_recommendation"),
        "shadow_observe_only_settings_ok": counts.get("shadow_observe_only_settings_ok"),
        "shadow_observe_only_policy_sample_ok": counts.get("shadow_observe_only_policy_sample_ok"),
        "shadow_observe_only_live_violation_count": counts.get("shadow_observe_only_live_violation_count"),
        "shadow_observe_only_live_status": counts.get("shadow_observe_only_live_status"),
        "live_observation_staleness_status": counts.get("live_observation_staleness_status"),
        "live_observation_staleness_recommendation": counts.get("live_observation_staleness_recommendation"),
        "live_observation_file_age_minutes": counts.get("live_observation_file_age_minutes"),
        "live_observation_file_stale": counts.get("live_observation_file_stale"),
        "live_observation_file_mtime": counts.get("live_observation_file_mtime"),
        "live_observation_shadow_count": counts.get("live_observation_shadow_count"),
        "actual_shadow_maturity_ready": counts.get("actual_shadow_maturity_ready"),
        "actual_shadow_maturity_recommendation": counts.get("actual_shadow_maturity_recommendation"),
        "actual_shadow_observation_count": counts.get("actual_shadow_observation_count"),
        "actual_shadow_unique_setup_count": counts.get("actual_shadow_unique_setup_count"),
        "actual_shadow_min_rows": counts.get("actual_shadow_min_rows"),
        "actual_shadow_min_unique_setups": counts.get("actual_shadow_min_unique_setups"),
        "actual_shadow_rows_ready": counts.get("actual_shadow_rows_ready"),
        "actual_shadow_unique_ready": counts.get("actual_shadow_unique_ready"),
        "actual_shadow_legacy_or_missing_count": counts.get("actual_shadow_legacy_or_missing_count"),
        "trade_tracker_close_safety_all_ok": counts.get("trade_tracker_close_safety_all_ok"),
        "trade_tracker_close_safety_recommendation": counts.get("trade_tracker_close_safety_recommendation"),
        "trade_tracker_detect_before_closed": counts.get("trade_tracker_detect_before_closed"),
        "trade_tracker_unresolved_keeps_open": counts.get("trade_tracker_unresolved_keeps_open"),
        "trade_tracker_resolved_saves_close_price": counts.get("trade_tracker_resolved_saves_close_price"),
        "trade_tracker_unresolved_pending_flag": counts.get("trade_tracker_unresolved_pending_flag"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run the Phase 2 shadow confirmation analysis suite."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--min-samples",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--min-known-outcomes",
        type=int,
        default=10,
    )

    parser.add_argument(
        "--min-unique-setups",
        type=int,
        default=30,
    )

    parser.add_argument(
        "--min-clean-known-outcomes",
        type=int,
        default=10,
    )

    parser.add_argument(
        "--max-mixed-outcome-rate",
        type=float,
        default=0.10,
    )

    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)
    python_exe = sys.executable

    source_dir_arg = str(paths["source_dir"])

    steps = [
        {
            "name": "Analyze confirmation observations",
            "command": [
                python_exe,
                "scripts/analyze_confirmation_observations.py",
                "--source-dir",
                source_dir_arg,
                "--min-samples",
                str(args.min_samples),
            ],
        },
        {
            "name": "Analyze shadow policy performance",
            "command": [
                python_exe,
                "scripts/analyze_confirmation_shadow_policy.py",
                "--source-dir",
                source_dir_arg,
                "--min-samples",
                str(args.min_samples),
                "--min-known-outcomes",
                str(args.min_known_outcomes),
            ],
        },
        {
            "name": "Check base Phase 2 readiness",
            "command": [
                python_exe,
                "scripts/check_phase2_readiness.py",
                "--source-dir",
                source_dir_arg,
            ],
        },
        {
            "name": "Check shadow Phase 2 readiness",
            "command": [
                python_exe,
                "scripts/check_phase2_shadow_readiness.py",
                "--source-dir",
                source_dir_arg,
                "--min-unique-setups",
                str(args.min_unique_setups),
                "--min-clean-known-outcomes",
                str(args.min_clean_known_outcomes),
                "--max-mixed-outcome-rate",
                str(args.max_mixed_outcome_rate),
            ],
        },
        {
            "name": "Debug outcome quality",
            "command": [
                python_exe,
                "scripts/debug_confirmation_outcome_quality.py",
                "--source-dir",
                source_dir_arg,
            ],
        },
        {
            "name": "Audit duplicate observations",
            "command": [
                python_exe,
                "scripts/audit_confirmation_duplicate_observations.py",
                "--source-dir",
                source_dir_arg,
                "--top",
                "20",
            ],
        },
        {
            "name": "Check shadow persistence",
            "command": [
                python_exe,
                "scripts/check_confirmation_shadow_persistence.py",
                "--source-dir",
                source_dir_arg,
            ],
        },
        {
            "name": "Check shadow observe-only safety",
            "command": [
                python_exe,
                "scripts/check_shadow_observe_only_safety.py",
                "--source-dir",
                source_dir_arg,
            ],
        },
        {
            "name": "Check live observation staleness",
            "command": [
                python_exe,
                "scripts/check_confirmation_live_observation_staleness.py",
                "--source-dir",
                source_dir_arg,
                "--stale-minutes",
                "60",
            ],
        },
        {
            "name": "Check actual shadow maturity",
            "command": [
                python_exe,
                "scripts/check_actual_shadow_maturity.py",
                "--source-dir",
                source_dir_arg,
            ],
        },
        {
            "name": "Check trade tracker close reconciliation safety",
            "command": [
                python_exe,
                "scripts/check_trade_tracker_close_reconciliation_safety.py",
                "--source-dir",
                source_dir_arg,
            ],
        },
    ]

    results = []

    for step in steps:
        result = run_step(step["name"], step["command"], PROJECT_ROOT)
        results.append(result)

        if args.stop_on_failure and result["exit_code"] != 0:
            break

    shadow_policy_report = load_json(paths["phase2_shadow_report"]) or {}
    shadow_readiness = load_json(paths["phase2_shadow_readiness"]) or {}
    base_readiness = load_json(paths["phase2_base_readiness"]) or {}
    outcome_debug = load_json(paths["outcome_quality_debug"]) or {}
    duplicate_audit = load_json(paths["duplicate_audit"]) or {}
    shadow_persistence = load_json(paths["shadow_persistence"]) or {}
    shadow_observe_only_safety = load_json(paths["shadow_observe_only_safety"]) or {}
    live_observation_staleness = load_json(paths["live_observation_staleness"]) or {}
    actual_shadow_maturity = load_json(paths["actual_shadow_maturity"]) or {}
    trade_tracker_close_safety = load_json(paths["trade_tracker_close_safety"]) or {}

    all_steps_ok = all(step.get("ok") for step in results)

    summary = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2H",
        "account_name": paths["account_name"],
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "all_steps_ok": all_steps_ok,
        "step_count": len(results),
        "failed_step_count": sum(1 for step in results if not step.get("ok")),
        "shadow_monitoring_ready": shadow_readiness.get("shadow_monitoring_ready"),
        "shadow_calibration_ready": shadow_readiness.get("shadow_calibration_ready"),
        "blocking_ready": shadow_readiness.get("blocking_ready"),
        "recommendation": shadow_readiness.get("recommendation"),
        "base_phase2_recommendation": base_readiness.get("recommendation"),
        "counts": {
            "raw_observation_count": shadow_policy_report.get("raw_observation_count"),
            "unique_setup_count": shadow_policy_report.get("unique_setup_count"),
            "duplicate_observation_count": shadow_policy_report.get("duplicate_observation_count"),
            "known_outcome_count_unique": shadow_policy_report.get("known_outcome_count_unique"),
            "clean_known_outcome_count_unique": shadow_policy_report.get("clean_known_outcome_count_unique"),
            "mixed_tp_sl_count_unique": shadow_policy_report.get("mixed_tp_sl_count_unique"),
            "outcome_quality_issue_count": shadow_policy_report.get("outcome_quality_issue_count"),
            "debugged_outcome_issue_count": outcome_debug.get("debugged_issue_count"),
            "debug_mixed_tp_sl_count": outcome_debug.get("mixed_tp_sl_count"),
            "duplicate_audit_rate": duplicate_audit.get("duplicate_rate"),
            "duplicate_audit_group_count": duplicate_audit.get("duplicate_group_count"),
            "duplicate_audit_observation_count": duplicate_audit.get("duplicate_observation_count"),
            "duplicate_audit_recommendation": duplicate_audit.get("recommendation"),
            "shadow_persistence_code_level_ready": shadow_persistence.get("code_level_ready"),
            "shadow_persistence_live_present": shadow_persistence.get("live_shadow_observations_present"),
            "shadow_persistence_recommendation": shadow_persistence.get("recommendation"),
            "shadow_persistence_populated_count": (shadow_persistence.get("counts") or {}).get("shadow_populated_observation_count"),
            "shadow_persistence_missing_count": (shadow_persistence.get("counts") or {}).get("shadow_missing_observation_count"),
            "shadow_persistence_populated_rate": (shadow_persistence.get("counts") or {}).get("shadow_populated_rate"),
            "shadow_observe_only_safety_all_ok": shadow_observe_only_safety.get("all_ok"),
            "shadow_observe_only_safety_recommendation": shadow_observe_only_safety.get("recommendation"),
            "shadow_observe_only_settings_ok": (shadow_observe_only_safety.get("settings_check") or {}).get("ok"),
            "shadow_observe_only_policy_sample_ok": (shadow_observe_only_safety.get("policy_sample_check") or {}).get("ok"),
            "shadow_observe_only_live_violation_count": (shadow_observe_only_safety.get("live_rows_check") or {}).get("violation_count"),
            "shadow_observe_only_live_status": (shadow_observe_only_safety.get("live_rows_check") or {}).get("status"),
            "live_observation_staleness_status": live_observation_staleness.get("status"),
            "live_observation_staleness_recommendation": live_observation_staleness.get("recommendation"),
            "live_observation_file_age_minutes": (live_observation_staleness.get("file_status") or {}).get("file_age_minutes"),
            "live_observation_file_stale": (live_observation_staleness.get("file_status") or {}).get("file_stale"),
            "live_observation_file_mtime": (live_observation_staleness.get("file_status") or {}).get("file_mtime"),
            "live_observation_shadow_count": (live_observation_staleness.get("counts") or {}).get("shadow_populated_observation_count"),
            "actual_shadow_maturity_ready": actual_shadow_maturity.get("live_shadow_maturity_ready"),
            "actual_shadow_maturity_recommendation": actual_shadow_maturity.get("recommendation"),
            "actual_shadow_observation_count": (actual_shadow_maturity.get("counts") or {}).get("actual_shadow_observation_count"),
            "actual_shadow_unique_setup_count": (actual_shadow_maturity.get("counts") or {}).get("actual_shadow_unique_setup_count"),
            "actual_shadow_min_rows": (actual_shadow_maturity.get("counts") or {}).get("min_actual_shadow_rows"),
            "actual_shadow_min_unique_setups": (actual_shadow_maturity.get("counts") or {}).get("min_actual_shadow_unique_setups"),
            "actual_shadow_rows_ready": (actual_shadow_maturity.get("counts") or {}).get("actual_shadow_rows_ready"),
            "actual_shadow_unique_ready": (actual_shadow_maturity.get("counts") or {}).get("actual_shadow_unique_ready"),
            "actual_shadow_legacy_or_missing_count": (actual_shadow_maturity.get("counts") or {}).get("legacy_or_missing_shadow_count"),
            "trade_tracker_close_safety_all_ok": trade_tracker_close_safety.get("all_ok"),
            "trade_tracker_close_safety_recommendation": trade_tracker_close_safety.get("recommendation"),
            "trade_tracker_detect_before_closed": (trade_tracker_close_safety.get("checks") or {}).get("detect_close_before_marking_closed"),
            "trade_tracker_unresolved_keeps_open": (trade_tracker_close_safety.get("checks") or {}).get("unresolved_keeps_status_open"),
            "trade_tracker_resolved_saves_close_price": (trade_tracker_close_safety.get("checks") or {}).get("resolved_saves_close_price"),
            "trade_tracker_unresolved_pending_flag": (trade_tracker_close_safety.get("checks") or {}).get("unresolved_sets_pending_true"),
        },
        "next_actions": shadow_readiness.get("next_actions") or [],
        "steps": [compact_step_output(step) for step in results],
        "generated_files": {
            "suite_json": str(paths["suite_json"]),
            "suite_txt": str(paths["suite_txt"]),
            "history_jsonl": str(paths["history_jsonl"]),
            "history_csv": str(paths["history_csv"]),
            "phase2_shadow_report": str(paths["phase2_shadow_report"]),
            "phase2_shadow_readiness": str(paths["phase2_shadow_readiness"]),
            "phase2_base_readiness": str(paths["phase2_base_readiness"]),
            "outcome_quality_debug": str(paths["outcome_quality_debug"]),
            "duplicate_audit": str(paths["duplicate_audit"]),
            "shadow_persistence": str(paths["shadow_persistence"]),
            "shadow_observe_only_safety": str(paths["shadow_observe_only_safety"]),
            "live_observation_staleness": str(paths["live_observation_staleness"]),
            "actual_shadow_maturity": str(paths["actual_shadow_maturity"]),
            "trade_tracker_close_safety": str(paths["trade_tracker_close_safety"]),
        },
        "notes": [
            "This runner does not modify live trading behavior.",
            "This runner does not block trades.",
            "Blocking readiness must remain false until enough unique clean outcomes exist.",
        ],
    }

    text_lines = []
    text_lines.append("[PHASE 2H SHADOW SUITE SUMMARY]")
    text_lines.append(f"created_at = {summary['created_at']}")
    text_lines.append(f"account_name = {summary['account_name']}")
    text_lines.append(f"all_steps_ok = {summary['all_steps_ok']}")
    text_lines.append(f"shadow_monitoring_ready = {summary['shadow_monitoring_ready']}")
    text_lines.append(f"shadow_calibration_ready = {summary['shadow_calibration_ready']}")
    text_lines.append(f"blocking_ready = {summary['blocking_ready']}")
    text_lines.append(f"recommendation = {summary['recommendation']}")
    text_lines.append("")
    text_lines.append("[COUNTS]")

    for key, value in summary["counts"].items():
        text_lines.append(f"{key} = {value}")

    text_lines.append("")
    text_lines.append("[PROGRESS]")
    text_lines.append(f"unique_setup_progress = {round((summary['counts'].get('unique_setup_count') or 0) / args.min_unique_setups, 4) if args.min_unique_setups else None}")
    text_lines.append(f"clean_known_outcome_progress = {round((summary['counts'].get('clean_known_outcome_count_unique') or 0) / args.min_clean_known_outcomes, 4) if args.min_clean_known_outcomes else None}")
    text_lines.append(f"remaining_unique_setups = {max(0, args.min_unique_setups - int(summary['counts'].get('unique_setup_count') or 0))}")
    text_lines.append(f"remaining_clean_known_outcomes = {max(0, args.min_clean_known_outcomes - int(summary['counts'].get('clean_known_outcome_count_unique') or 0))}")
    text_lines.append("")
    text_lines.append("[DUPLICATE AUDIT]")
    text_lines.append(f"duplicate_audit_rate = {summary['counts'].get('duplicate_audit_rate')}")
    text_lines.append(f"duplicate_audit_group_count = {summary['counts'].get('duplicate_audit_group_count')}")
    text_lines.append(f"duplicate_audit_observation_count = {summary['counts'].get('duplicate_audit_observation_count')}")
    text_lines.append(f"duplicate_audit_recommendation = {summary['counts'].get('duplicate_audit_recommendation')}")
    text_lines.append("")
    text_lines.append("[SHADOW PERSISTENCE]")
    text_lines.append(f"code_level_ready = {summary['counts'].get('shadow_persistence_code_level_ready')}")
    text_lines.append(f"live_shadow_observations_present = {summary['counts'].get('shadow_persistence_live_present')}")
    text_lines.append(f"shadow_populated_observation_count = {summary['counts'].get('shadow_persistence_populated_count')}")
    text_lines.append(f"shadow_missing_observation_count = {summary['counts'].get('shadow_persistence_missing_count')}")
    text_lines.append(f"shadow_populated_rate = {summary['counts'].get('shadow_persistence_populated_rate')}")
    text_lines.append(f"shadow_persistence_recommendation = {summary['counts'].get('shadow_persistence_recommendation')}")
    text_lines.append("")
    text_lines.append("[SHADOW OBSERVE-ONLY SAFETY]")
    text_lines.append(f"all_ok = {summary['counts'].get('shadow_observe_only_safety_all_ok')}")
    text_lines.append(f"settings_ok = {summary['counts'].get('shadow_observe_only_settings_ok')}")
    text_lines.append(f"policy_sample_ok = {summary['counts'].get('shadow_observe_only_policy_sample_ok')}")
    text_lines.append(f"live_violation_count = {summary['counts'].get('shadow_observe_only_live_violation_count')}")
    text_lines.append(f"live_status = {summary['counts'].get('shadow_observe_only_live_status')}")
    text_lines.append(f"recommendation = {summary['counts'].get('shadow_observe_only_safety_recommendation')}")
    text_lines.append("")
    text_lines.append("[LIVE OBSERVATION STALENESS]")
    text_lines.append(f"status = {summary['counts'].get('live_observation_staleness_status')}")
    text_lines.append(f"recommendation = {summary['counts'].get('live_observation_staleness_recommendation')}")
    text_lines.append(f"file_mtime = {summary['counts'].get('live_observation_file_mtime')}")
    text_lines.append(f"file_age_minutes = {summary['counts'].get('live_observation_file_age_minutes')}")
    text_lines.append(f"file_stale = {summary['counts'].get('live_observation_file_stale')}")
    text_lines.append(f"shadow_populated_observation_count = {summary['counts'].get('live_observation_shadow_count')}")
    text_lines.append("")
    text_lines.append("[ACTUAL SHADOW MATURITY]")
    text_lines.append(f"ready = {summary['counts'].get('actual_shadow_maturity_ready')}")
    text_lines.append(f"recommendation = {summary['counts'].get('actual_shadow_maturity_recommendation')}")
    text_lines.append(f"actual_shadow_observation_count = {summary['counts'].get('actual_shadow_observation_count')}")
    text_lines.append(f"actual_shadow_unique_setup_count = {summary['counts'].get('actual_shadow_unique_setup_count')}")
    text_lines.append(f"min_actual_shadow_rows = {summary['counts'].get('actual_shadow_min_rows')}")
    text_lines.append(f"min_actual_shadow_unique_setups = {summary['counts'].get('actual_shadow_min_unique_setups')}")
    text_lines.append(f"actual_shadow_rows_ready = {summary['counts'].get('actual_shadow_rows_ready')}")
    text_lines.append(f"actual_shadow_unique_ready = {summary['counts'].get('actual_shadow_unique_ready')}")
    text_lines.append(f"legacy_or_missing_shadow_count = {summary['counts'].get('actual_shadow_legacy_or_missing_count')}")
    text_lines.append("")
    text_lines.append("[TRADE TRACKER CLOSE SAFETY]")
    text_lines.append(f"all_ok = {summary['counts'].get('trade_tracker_close_safety_all_ok')}")
    text_lines.append(f"recommendation = {summary['counts'].get('trade_tracker_close_safety_recommendation')}")
    text_lines.append(f"detect_close_before_marking_closed = {summary['counts'].get('trade_tracker_detect_before_closed')}")
    text_lines.append(f"unresolved_keeps_status_open = {summary['counts'].get('trade_tracker_unresolved_keeps_open')}")
    text_lines.append(f"unresolved_pending_flag = {summary['counts'].get('trade_tracker_unresolved_pending_flag')}")
    text_lines.append(f"resolved_saves_close_price = {summary['counts'].get('trade_tracker_resolved_saves_close_price')}")
    text_lines.append("")
    text_lines.append("[NEXT ACTIONS]")

    if summary["next_actions"]:
        for item in summary["next_actions"]:
            text_lines.append(f"- {item}")
    else:
        text_lines.append("- None")

    text_lines.append("")
    text_lines.append("[STEPS]")

    for step in results:
        text_lines.append(f"- {step['name']}: exit_code={step['exit_code']} ok={step['ok']}")

    text_output = "\n".join(text_lines) + "\n"

    progress_snapshot = build_progress_snapshot(
        summary,
        min_unique_setups=args.min_unique_setups,
        min_clean_known_outcomes=args.min_clean_known_outcomes,
    )

    summary["progress_snapshot"] = progress_snapshot

    write_json(paths["suite_json"], summary)
    write_text(paths["suite_txt"], text_output)
    append_jsonl(paths["history_jsonl"], progress_snapshot)
    append_csv_row(paths["history_csv"], progress_snapshot)

    print()
    print("=" * 100)
    print(text_output.rstrip())
    print("=" * 100)
    print("suite_json =", paths["suite_json"])
    print("suite_txt =", paths["suite_txt"])
    print("history_jsonl =", paths["history_jsonl"])
    print("history_csv =", paths["history_csv"])

    if not all_steps_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
