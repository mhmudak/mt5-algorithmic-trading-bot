import argparse
import ast
import json
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


SETTINGS_NAMES = [
    "ENABLE_EXTRA_ENTRY_MANAGEMENT",
    "EXTRA_ENTRY_BREAK_EVEN_TRIGGER_PRICE",
    "EXTRA_ENTRY_LOCK_TRIGGER_PRICE",
    "EXTRA_ENTRY_LOCK_PRICE",
    "EXTRA_ENTRY_TAKE_PROFIT_PRICE",
    "ENABLE_WORST_EXTRA_LOCK",
    "WORST_EXTRA_LOCK_TRIGGER_PRICE",
    "WORST_EXTRA_LOCK_PROFIT_PRICE",
    "REQUIRE_MAIN_PROTECTED_FOR_EXTRA",
    "MIN_MAIN_PROFIT_FOR_EXTRA_PRICE",
]


def read_text(path):
    return Path(path).read_text(encoding="utf-8")


def extract_assignment_values(settings_text):
    values = {}

    tree = ast.parse(settings_text)

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue

        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue

            name = target.id

            if name not in SETTINGS_NAMES:
                continue

            try:
                values[name] = ast.literal_eval(node.value)
            except Exception:
                values[name] = "<UNREADABLE>"

    return values


def contains_all(text, snippets):
    missing = []

    for snippet in snippets:
        if snippet not in text:
            missing.append(snippet)

    return missing


def classify(values, source_checks):
    extra_be_trigger = values.get("EXTRA_ENTRY_BREAK_EVEN_TRIGGER_PRICE")
    worst_extra_trigger = values.get("WORST_EXTRA_LOCK_TRIGGER_PRICE")
    worst_extra_enabled = values.get("ENABLE_WORST_EXTRA_LOCK")
    extra_management_enabled = values.get("ENABLE_EXTRA_ENTRY_MANAGEMENT")

    warnings = []

    if extra_management_enabled is True:
        warnings.append("extra_entry_management_enabled")

    if isinstance(extra_be_trigger, (int, float)) and extra_be_trigger <= 3.0:
        warnings.append("extra_be_trigger_very_early")

    if worst_extra_enabled is True:
        warnings.append("worst_extra_lock_enabled")

    if isinstance(worst_extra_trigger, (int, float)) and worst_extra_trigger <= 2.0:
        warnings.append("worst_extra_lock_trigger_very_early")

    if source_checks.get("extra_be_code_present"):
        warnings.append("extra_be_lock_code_present")

    if source_checks.get("worst_extra_lock_code_present"):
        warnings.append("worst_extra_lock_code_present")

    if (
        "extra_be_trigger_very_early" in warnings
        and "worst_extra_lock_trigger_very_early" in warnings
    ):
        recommendation = "BE_PROTECTION_LIKELY_TOO_AGGRESSIVE_FOR_EXTRAS"
    elif "extra_be_trigger_very_early" in warnings:
        recommendation = "REVIEW_EXTRA_BE_TRIGGER"
    else:
        recommendation = "BE_PROTECTION_SOURCE_OK_OBSERVE_MORE"

    return recommendation, warnings


def main():
    parser = argparse.ArgumentParser(
        description="Audit source/config responsible for breakeven protection behavior."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    args = parser.parse_args()

    account_name = Path(args.source_dir).name
    output_dir = PROJECT_ROOT / "data" / "strategy_intelligence" / account_name
    output_dir.mkdir(parents=True, exist_ok=True)

    settings_path = PROJECT_ROOT / "config" / "settings.py"
    position_manager_path = PROJECT_ROOT / "src" / "position_manager.py"

    settings_text = read_text(settings_path)
    position_manager_text = read_text(position_manager_path)

    values = extract_assignment_values(settings_text)

    source_checks = {
        "manage_extra_entry_present": "def manage_extra_entry" in position_manager_text,
        "extra_be_code_present": (
            "EXTRA_ENTRY_BREAK_EVEN_TRIGGER_PRICE" in position_manager_text
            and "lock_profit_price=0.0" in position_manager_text
            and "reason=\"Extra BE lock\"" in position_manager_text
        ),
        "extra_plus2_code_present": (
            "EXTRA_ENTRY_LOCK_TRIGGER_PRICE" in position_manager_text
            and "EXTRA_ENTRY_LOCK_PRICE" in position_manager_text
            and "reason=\"Extra +2 lock\"" in position_manager_text
        ),
        "extra_full_close_code_present": (
            "EXTRA_ENTRY_TAKE_PROFIT_PRICE" in position_manager_text
            and "reason=\"Extra entry full close\"" in position_manager_text
        ),
        "worst_extra_lock_code_present": (
            "ENABLE_WORST_EXTRA_LOCK" in position_manager_text
            and "WORST_EXTRA_LOCK_TRIGGER_PRICE" in position_manager_text
            and "WORST_EXTRA_LOCK_PROFIT_PRICE" in position_manager_text
            and "reason=\"Worst extra lock\"" in position_manager_text
        ),
        "apply_price_lock_present": "def apply_price_lock" in position_manager_text,
        "modify_sl_uses_sltp": (
            "mt5.TRADE_ACTION_SLTP" in position_manager_text
            and "mt5.order_send" in position_manager_text
        ),
    }

    recommendation, warnings = classify(values, source_checks)

    all_ok = all(source_checks.values())

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2AU",
        "all_ok": all_ok,
        "recommendation": recommendation,
        "warnings": warnings,
        "settings": values,
        "source_checks": source_checks,
        "source_files": {
            "settings": str(settings_path),
            "position_manager": str(position_manager_path),
        },
        "notes": [
            "This is source/config audit only.",
            "No live trading behavior is changed.",
            "If extra BE trigger is very low, extras may close at breakeven before enough structure develops.",
            "Next step should be simulation before changing thresholds.",
        ],
    }

    report_path = output_dir / "breakeven_protection_source_safety_report.json"

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, sort_keys=True)

    print("[PHASE 2AU BREAKEVEN PROTECTION SOURCE SAFETY]")
    print("all_ok =", all_ok)
    print("recommendation =", recommendation)

    print()
    print("[SETTINGS]")
    for name in SETTINGS_NAMES:
        print(f"{name} = {values.get(name)}")

    print()
    print("[SOURCE CHECKS]")
    for key, value in source_checks.items():
        print(f"{key} = {value}")

    print()
    print("[WARNINGS]")
    for warning in warnings:
        print("-", warning)

    print()
    print("report =", report_path)


if __name__ == "__main__":
    main()
