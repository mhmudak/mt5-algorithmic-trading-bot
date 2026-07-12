import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def check_text_contains(path, required_items):
    text = Path(path).read_text(encoding="utf-8")
    results = {}

    for item in required_items:
        results[item] = item in text

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Check confirmation-engine runtime safety markers."
    )

    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory for JSON safety report.",
    )

    args = parser.parse_args()

    live_bot = PROJECT_ROOT / "src" / "live_bot.py"
    settings = PROJECT_ROOT / "config" / "settings.py"

    live_checks = check_text_contains(
        live_bot,
        [
            "ENABLE_CONFIRMATION_ENGINE_OBSERVE_ONLY",
            "CONFIRMATION ENGINE] Observe-only layer disabled by settings",
            "raw_selected_signal_data",
            "raw_trade_plan",
            "selected_signal_data = dict(raw_selected_signal_data)",
            "trade_plan = dict(raw_trade_plan)",
            "observe_universal_confirmation_from_scope",
            "observe_universal_confirmation_for_setup",
        ],
    )

    settings_checks = check_text_contains(
        settings,
        [
            "ENABLE_CONFIRMATION_ENGINE_OBSERVE_ONLY = True",
            "CONFIRMATION_ENGINE_OBSERVE_ONLY_MODE = True",
        ],
    )

    try:
        from scripts.audit_confirmation_coverage import audit_live_bot

        coverage_summary, _, _ = audit_live_bot(
            "src/live_bot.py",
            observe_window_lines=120,
        )

    except Exception as exc:
        coverage_summary = {
            "error": str(exc),
            "coverage_rate": None,
            "missing_observe_before_execute_trade_count": None,
        }

    failed_live = [
        item
        for item, ok in live_checks.items()
        if not ok
    ]

    failed_settings = [
        item
        for item, ok in settings_checks.items()
        if not ok
    ]

    coverage_ok = (
        coverage_summary.get("missing_observe_before_execute_trade_count") == 0
        and coverage_summary.get("coverage_rate") == 1.0
    )

    all_ok = not failed_live and not failed_settings and coverage_ok

    report = {
        "all_ok": all_ok,
        "live_bot_checks": live_checks,
        "settings_checks": settings_checks,
        "failed_live_checks": failed_live,
        "failed_settings_checks": failed_settings,
        "coverage_summary": coverage_summary,
        "notes": [
            "This script does not open MT5 orders.",
            "It checks source-code safety markers and static confirmation coverage.",
            "Confirmation engine remains observe-only.",
        ],
    }

    print("[CONFIRMATION RUNTIME SAFETY] all_ok =", all_ok)
    print("coverage_rate =", coverage_summary.get("coverage_rate"))
    print("missing_observe_before_execute_trade_count =", coverage_summary.get("missing_observe_before_execute_trade_count"))

    if failed_live:
        print("failed_live_checks =", failed_live)

    if failed_settings:
        print("failed_settings_checks =", failed_settings)

    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        path = output_dir / "confirmation_runtime_safety_report.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, sort_keys=True)

        print("report =", path)

    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
