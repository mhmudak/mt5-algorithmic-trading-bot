import argparse
import importlib
import json
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.confirmation_shadow_policy import apply_confirmation_shadow_policy


def read_jsonl(path):
    path = Path(path)

    if not path.exists():
        return []

    rows = []

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                row = json.loads(line)
                row["_line_no"] = line_no
                rows.append(row)
            except Exception as exc:
                rows.append({
                    "_line_no": line_no,
                    "_parse_error": str(exc),
                    "_raw": line[:500],
                })

    return rows


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)

    return path


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
        "observations_file": source_dir / "confirmation_observations.jsonl",
        "report_json": output_dir / "confirmation_shadow_observe_only_safety_report.json",
    }


def has_shadow_fields(row):
    return bool(
        row.get("shadow_decision")
        or row.get("shadow_action")
        or row.get("shadow_score") is not None
        or row.get("shadow_policy_version")
    )


def load_settings_check():
    result = {
        "ok": False,
        "settings_loaded": False,
        "enable_shadow_policy": None,
        "observe_only": None,
        "blocking_allowed_by_settings": None,
        "errors": [],
    }

    try:
        settings = importlib.import_module("config.settings")
        result["settings_loaded"] = True

        enable_shadow_policy = getattr(settings, "ENABLE_CONFIRMATION_SHADOW_POLICY", None)
        observe_only = getattr(settings, "CONFIRMATION_SHADOW_POLICY_OBSERVE_ONLY", None)

        result["enable_shadow_policy"] = enable_shadow_policy
        result["observe_only"] = observe_only
        result["blocking_allowed_by_settings"] = observe_only is False

        result["ok"] = (
            enable_shadow_policy is True
            and observe_only is True
        )

        if enable_shadow_policy is not True:
            result["errors"].append("ENABLE_CONFIRMATION_SHADOW_POLICY is not True")

        if observe_only is not True:
            result["errors"].append("CONFIRMATION_SHADOW_POLICY_OBSERVE_ONLY is not True")

    except Exception as exc:
        result["errors"].append(str(exc))

    return result


def run_policy_sample_check():
    report = {
        "engine_version": "OBSERVE_ONLY_SAFETY_TEST",
        "mode": "MT5_ONLY",
        "approved": True,
        "confidence": 90,
        "score_delta": 6.0,
        "summary": "observe-only safety sample",
        "results": [
            {"module": "SETUP_SCHEMA", "status": "PASS", "score_delta": 0},
            {"module": "ENTRY_QUALITY", "status": "PASS", "score_delta": 2},
            {"module": "PRICE_ACTION_STRUCTURE", "status": "PASS", "score_delta": 2},
        ],
    }

    apply_confirmation_shadow_policy(report)

    ok = (
        report.get("shadow_action") == "OBSERVE_ONLY"
        and report.get("shadow_blocking_allowed") is False
    )

    return {
        "ok": ok,
        "shadow_decision": report.get("shadow_decision"),
        "shadow_score": report.get("shadow_score"),
        "shadow_action": report.get("shadow_action"),
        "shadow_blocking_allowed": report.get("shadow_blocking_allowed"),
        "shadow_reason": report.get("shadow_reason"),
    }


def check_live_shadow_rows(rows):
    parsed = [row for row in rows if not row.get("_parse_error")]
    shadow_rows = [row for row in parsed if has_shadow_fields(row)]

    violations = []

    for row in shadow_rows:
        action = row.get("shadow_action")
        blocking_allowed = row.get("shadow_blocking_allowed")

        if action != "OBSERVE_ONLY":
            violations.append({
                "line_no": row.get("_line_no"),
                "setup_id": row.get("setup_id"),
                "field": "shadow_action",
                "value": action,
                "expected": "OBSERVE_ONLY",
            })

        if blocking_allowed is not False:
            violations.append({
                "line_no": row.get("_line_no"),
                "setup_id": row.get("setup_id"),
                "field": "shadow_blocking_allowed",
                "value": blocking_allowed,
                "expected": False,
            })

    return {
        "ok": len(violations) == 0,
        "parsed_observation_count": len(parsed),
        "shadow_observation_count": len(shadow_rows),
        "shadow_missing_observation_count": len(parsed) - len(shadow_rows),
        "violation_count": len(violations),
        "violations": violations[:50],
        "status": "CHECKED" if shadow_rows else "WAITING_FOR_LIVE_SHADOW_ROWS",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Verify that shadow confirmation policy remains observe-only."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if safety check is not fully OK.",
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)

    settings_check = load_settings_check()
    policy_sample_check = run_policy_sample_check()
    live_rows_check = check_live_shadow_rows(read_jsonl(paths["observations_file"]))

    all_ok = all([
        settings_check.get("ok"),
        policy_sample_check.get("ok"),
        live_rows_check.get("ok"),
    ])

    if not settings_check.get("ok"):
        recommendation = "FIX_SHADOW_POLICY_SETTINGS"
    elif not policy_sample_check.get("ok"):
        recommendation = "FIX_SHADOW_POLICY_OUTPUT"
    elif not live_rows_check.get("ok"):
        recommendation = "FIX_LIVE_SHADOW_OBSERVATION_SAFETY"
    elif live_rows_check.get("shadow_observation_count", 0) == 0:
        recommendation = "OBSERVE_ONLY_SAFE_WAITING_FOR_LIVE_SHADOW_ROWS"
    else:
        recommendation = "OBSERVE_ONLY_SAFETY_CONFIRMED"

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2Q",
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "all_ok": all_ok,
        "recommendation": recommendation,
        "settings_check": settings_check,
        "policy_sample_check": policy_sample_check,
        "live_rows_check": live_rows_check,
        "generated_files": {
            "report_json": str(paths["report_json"]),
        },
        "notes": [
            "This check does not modify live trading behavior.",
            "Shadow policy must remain OBSERVE_ONLY during Phase 2.",
            "shadow_blocking_allowed must remain False.",
            "No live shadow rows yet is not a safety failure.",
        ],
    }

    write_json(paths["report_json"], report)

    print("[PHASE 2Q SHADOW OBSERVE-ONLY SAFETY]")
    print("all_ok =", all_ok)
    print("recommendation =", recommendation)

    print()
    print("[SETTINGS]")
    print("settings_loaded =", settings_check.get("settings_loaded"))
    print("ENABLE_CONFIRMATION_SHADOW_POLICY =", settings_check.get("enable_shadow_policy"))
    print("CONFIRMATION_SHADOW_POLICY_OBSERVE_ONLY =", settings_check.get("observe_only"))
    print("settings_ok =", settings_check.get("ok"))
    print("settings_errors =", settings_check.get("errors"))

    print()
    print("[POLICY SAMPLE]")
    print("sample_ok =", policy_sample_check.get("ok"))
    print("shadow_decision =", policy_sample_check.get("shadow_decision"))
    print("shadow_score =", policy_sample_check.get("shadow_score"))
    print("shadow_action =", policy_sample_check.get("shadow_action"))
    print("shadow_blocking_allowed =", policy_sample_check.get("shadow_blocking_allowed"))

    print()
    print("[LIVE ROWS]")
    print("status =", live_rows_check.get("status"))
    print("parsed_observation_count =", live_rows_check.get("parsed_observation_count"))
    print("shadow_observation_count =", live_rows_check.get("shadow_observation_count"))
    print("violation_count =", live_rows_check.get("violation_count"))

    print()
    print("report =", paths["report_json"])

    if args.strict and not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
