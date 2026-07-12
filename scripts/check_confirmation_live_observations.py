import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


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


def resolve_paths(source_dir):
    source_dir = Path(source_dir)

    if not source_dir.is_absolute():
        source_dir = PROJECT_ROOT / source_dir

    account_name = source_dir.name
    output_dir = PROJECT_ROOT / "data" / "strategy_intelligence" / account_name

    return {
        "source_dir": source_dir,
        "account_name": account_name,
        "output_dir": output_dir,
        "observations_file": source_dir / "confirmation_observations.jsonl",
        "summary_file": output_dir / "confirmation_observation_summary.json",
        "validation_report_file": output_dir / "phase1_confirmation_validation_report.json",
        "coverage_summary_file": output_dir / "confirmation_coverage_summary.json",
        "runtime_safety_file": output_dir / "confirmation_runtime_safety_report.json",
        "live_check_report_file": output_dir / "confirmation_live_observation_check.json",
    }


def get_nested(row, keys, default=None):
    current = row

    for key in keys:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

    return current if current is not None else default


def extract_modules(row):
    candidates = [
        row.get("results"),
        row.get("module_results"),
        get_nested(row, ["report", "results"]),
        get_nested(row, ["confirmation_report", "results"]),
    ]

    for value in candidates:
        if isinstance(value, list):
            return value

    return []


def extract_value(row, names, nested_candidates=None, default=None):
    for name in names:
        if isinstance(row, dict) and row.get(name) is not None:
            return row.get(name)

    nested_candidates = nested_candidates or []

    for path in nested_candidates:
        value = get_nested(row, path)

        if value is not None:
            return value

    return default


def summarize_observations(rows, latest_limit=10):
    parse_errors = [row for row in rows if row.get("_parse_error")]

    valid_rows = [row for row in rows if not row.get("_parse_error")]

    bucket_counter = Counter()
    strategy_counter = Counter()
    signal_counter = Counter()
    mode_counter = Counter()
    module_counter = Counter()
    risk_module_counter = Counter()

    missing_setup_id = 0
    missing_strategy = 0
    missing_signal = 0
    rows_with_modules = 0
    rows_with_risk = 0

    latest = []

    for row in valid_rows:
        setup_id = extract_value(
            row,
            ["setup_id"],
            nested_candidates=[
                ["signal_data", "setup_id"],
                ["report", "setup_id"],
                ["confirmation_report", "setup_id"],
            ],
        )

        strategy = extract_value(
            row,
            ["strategy"],
            nested_candidates=[
                ["signal_data", "strategy"],
                ["report", "strategy"],
                ["confirmation_report", "strategy"],
            ],
        )

        signal = extract_value(
            row,
            ["signal"],
            nested_candidates=[
                ["signal_data", "signal"],
                ["report", "signal"],
                ["confirmation_report", "signal"],
            ],
        )

        bucket = extract_value(
            row,
            ["setup_source_bucket", "execution_bucket"],
            nested_candidates=[
                ["signal_data", "setup_source_bucket"],
                ["signal_data", "execution_bucket"],
                ["trade_plan", "setup_source_bucket"],
                ["trade_plan", "execution_bucket"],
            ],
            default="UNKNOWN",
        )

        mode = extract_value(
            row,
            ["mode"],
            nested_candidates=[
                ["report", "mode"],
                ["confirmation_report", "mode"],
            ],
            default="UNKNOWN",
        )

        if not setup_id:
            missing_setup_id += 1

        if not strategy:
            missing_strategy += 1

        if not signal:
            missing_signal += 1

        bucket_counter[str(bucket)] += 1
        strategy_counter[str(strategy or "UNKNOWN")] += 1
        signal_counter[str(signal or "UNKNOWN")] += 1
        mode_counter[str(mode)] += 1

        modules = extract_modules(row)

        if modules:
            rows_with_modules += 1

        risky_modules = []

        for module in modules:
            if not isinstance(module, dict):
                continue

            module_name = module.get("module") or "UNKNOWN_MODULE"
            status = module.get("status")
            score_delta = module.get("score_delta")
            risk_flags = module.get("risk_flags") or module.get("risk_flags_triggered") or []

            module_counter[str(module_name)] += 1

            is_risk = False

            if status in {"FAIL", "ERROR"}:
                is_risk = True

            try:
                if float(score_delta or 0) < 0:
                    is_risk = True
            except Exception:
                pass

            if isinstance(risk_flags, list) and risk_flags:
                is_risk = True

            if is_risk:
                risk_module_counter[str(module_name)] += 1
                risky_modules.append({
                    "module": module_name,
                    "status": status,
                    "score_delta": score_delta,
                    "risk_flags": risk_flags,
                    "reason": module.get("reason"),
                })

        if risky_modules:
            rows_with_risk += 1

        latest.append({
            "line_no": row.get("_line_no"),
            "created_at": row.get("created_at") or row.get("timestamp") or row.get("time"),
            "setup_id": setup_id,
            "strategy": strategy,
            "signal": signal,
            "bucket": bucket,
            "mode": mode,
            "approved": extract_value(
                row,
                ["approved"],
                nested_candidates=[
                    ["report", "approved"],
                    ["confirmation_report", "approved"],
                ],
            ),
            "confidence": extract_value(
                row,
                ["confidence"],
                nested_candidates=[
                    ["report", "confidence"],
                    ["confirmation_report", "confidence"],
                ],
            ),
            "score_delta": extract_value(
                row,
                ["score_delta"],
                nested_candidates=[
                    ["report", "score_delta"],
                    ["confirmation_report", "score_delta"],
                ],
            ),
            "module_count": len(modules),
            "risky_modules": risky_modules,
        })

    latest = latest[-latest_limit:]

    return {
        "observation_count": len(valid_rows),
        "parse_error_count": len(parse_errors),
        "rows_with_modules": rows_with_modules,
        "rows_with_risk": rows_with_risk,
        "missing_setup_id_count": missing_setup_id,
        "missing_strategy_count": missing_strategy,
        "missing_signal_count": missing_signal,
        "bucket_counts": dict(bucket_counter.most_common()),
        "strategy_counts": dict(strategy_counter.most_common()),
        "signal_counts": dict(signal_counter.most_common()),
        "mode_counts": dict(mode_counter.most_common()),
        "module_counts": dict(module_counter.most_common()),
        "risk_module_counts": dict(risk_module_counter.most_common()),
        "latest": latest,
        "parse_errors": parse_errors[:10],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check live confirmation-engine observations after running live_bot."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
        help="Account data directory.",
    )

    parser.add_argument(
        "--latest",
        type=int,
        default=10,
        help="Number of latest observations to print/summarize.",
    )

    parser.add_argument(
        "--fail-if-empty",
        action="store_true",
        help="Exit with code 1 if no live observations exist.",
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)

    rows = read_jsonl(paths["observations_file"])
    observation_summary = summarize_observations(rows, latest_limit=args.latest)

    analyzer_summary = load_json(paths["summary_file"]) or {}
    validation_report = load_json(paths["validation_report_file"]) or {}
    coverage_summary = load_json(paths["coverage_summary_file"]) or {}
    runtime_safety = load_json(paths["runtime_safety_file"]) or {}

    live_ready = (
        validation_report.get("all_ok") is True
        and coverage_summary.get("missing_observe_before_execute_trade_count") == 0
        and (runtime_safety.get("all_ok") is True or runtime_safety == {})
    )

    report = {
        "created_at": datetime.now().isoformat(),
        "account_name": paths["account_name"],
        "source_dir": str(paths["source_dir"]),
        "observations_file": str(paths["observations_file"]),
        "live_ready": live_ready,
        "observation_file_exists": paths["observations_file"].exists(),
        "observation_summary": observation_summary,
        "analyzer_summary": {
            "observation_count": analyzer_summary.get("observation_count"),
            "module_row_count": analyzer_summary.get("module_row_count"),
            "matched_outcome_count": analyzer_summary.get("matched_outcome_count"),
            "known_outcome_count": analyzer_summary.get("known_outcome_count"),
            "min_samples": analyzer_summary.get("min_samples"),
        },
        "phase1_validation_all_ok": validation_report.get("all_ok"),
        "coverage": {
            "coverage_rate": coverage_summary.get("coverage_rate"),
            "execute_trade_call_count": coverage_summary.get("execute_trade_call_count"),
            "covered_execute_trade_call_count": coverage_summary.get("covered_execute_trade_call_count"),
            "missing_observe_before_execute_trade_count": coverage_summary.get("missing_observe_before_execute_trade_count"),
        },
        "runtime_safety_all_ok": runtime_safety.get("all_ok"),
        "notes": [
            "This script does not open MT5 orders.",
            "Observation count may remain 0 until live_bot reaches an execution path.",
            "Confirmation engine is observe-only and does not block trades.",
            "Run analyze_confirmation_observations.py after live observations accumulate.",
        ],
    }

    write_json(paths["live_check_report_file"], report)

    print("[CONFIRMATION LIVE OBSERVATION CHECK]")
    print("live_ready =", live_ready)
    print("observations_file =", paths["observations_file"])
    print("observation_file_exists =", paths["observations_file"].exists())
    print("observation_count =", observation_summary["observation_count"])
    print("parse_error_count =", observation_summary["parse_error_count"])
    print("rows_with_modules =", observation_summary["rows_with_modules"])
    print("rows_with_risk =", observation_summary["rows_with_risk"])
    print("bucket_counts =", observation_summary["bucket_counts"])
    print("module_counts_top =", dict(list(observation_summary["module_counts"].items())[:10]))
    print("report =", paths["live_check_report_file"])

    if observation_summary["latest"]:
        print()
        print("[LATEST OBSERVATIONS]")

        for item in observation_summary["latest"]:
            print(
                f"line={item.get('line_no')} "
                f"setup_id={item.get('setup_id')} "
                f"strategy={item.get('strategy')} "
                f"signal={item.get('signal')} "
                f"bucket={item.get('bucket')} "
                f"confidence={item.get('confidence')} "
                f"score_delta={item.get('score_delta')} "
                f"modules={item.get('module_count')}"
            )

    if args.fail_if_empty and observation_summary["observation_count"] <= 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
