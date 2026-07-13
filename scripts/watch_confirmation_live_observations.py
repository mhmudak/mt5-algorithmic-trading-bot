import argparse
import json
import time
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def configure_utf8_console_output():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


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
        "monitor_report_file": output_dir / "confirmation_live_observation_monitor.json",
    }


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


def get_nested(row, keys, default=None):
    current = row

    for key in keys:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

    return current if current is not None else default


def extract_modules(row):
    candidates = [
        row.get("modules"),
        row.get("results"),
        row.get("module_results"),
        get_nested(row, ["report", "results"]),
        get_nested(row, ["report", "modules"]),
        get_nested(row, ["confirmation_report", "results"]),
        get_nested(row, ["confirmation_report", "modules"]),
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


def summarize_latest(rows):
    valid_rows = [row for row in rows if not row.get("_parse_error")]
    parse_error_count = len(rows) - len(valid_rows)

    if not valid_rows:
        return {
            "observation_count": 0,
            "parse_error_count": parse_error_count,
            "latest": None,
        }

    row = valid_rows[-1]
    modules = extract_modules(row)

    risky_modules = []

    for module in modules:
        if not isinstance(module, dict):
            continue

        module_name = module.get("module") or "UNKNOWN_MODULE"
        status = module.get("status")
        score_delta = module.get("score_delta")
        risk_flags = module.get("risk_flags") or module.get("risk_flags_triggered") or []

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
            risky_modules.append({
                "module": module_name,
                "status": status,
                "score_delta": score_delta,
                "risk_flags": risk_flags,
                "reason": module.get("reason"),
            })

    latest = {
        "line_no": row.get("_line_no"),
        "created_at": row.get("created_at") or row.get("timestamp") or row.get("time"),
        "setup_id": extract_value(
            row,
            ["setup_id"],
            nested_candidates=[
                ["signal_data", "setup_id"],
                ["report", "setup_id"],
                ["confirmation_report", "setup_id"],
            ],
        ),
        "strategy": extract_value(
            row,
            ["strategy"],
            nested_candidates=[
                ["signal_data", "strategy"],
                ["report", "strategy"],
                ["confirmation_report", "strategy"],
            ],
        ),
        "signal": extract_value(
            row,
            ["signal"],
            nested_candidates=[
                ["signal_data", "signal"],
                ["report", "signal"],
                ["confirmation_report", "signal"],
            ],
        ),
        "bucket": extract_value(
            row,
            ["setup_source_bucket", "execution_bucket"],
            nested_candidates=[
                ["signal_data", "setup_source_bucket"],
                ["signal_data", "execution_bucket"],
                ["trade_plan", "setup_source_bucket"],
                ["trade_plan", "execution_bucket"],
            ],
            default="UNKNOWN",
        ),
        "mode": extract_value(
            row,
            ["mode"],
            nested_candidates=[
                ["report", "mode"],
                ["confirmation_report", "mode"],
            ],
            default="UNKNOWN",
        ),
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
    }

    return {
        "observation_count": len(valid_rows),
        "parse_error_count": parse_error_count,
        "latest": latest,
    }


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)


def format_mtime(path):
    path = Path(path)

    if not path.exists():
        return None

    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def print_snapshot(snapshot):
    latest = snapshot.get("latest")

    print()
    print("=" * 72)
    print("[CONFIRMATION LIVE MONITOR]")
    print("time =", snapshot.get("checked_at"))
    print("observations_file =", snapshot.get("observations_file"))
    print("file_exists =", snapshot.get("file_exists"))
    print("file_mtime =", snapshot.get("file_mtime"))
    print("observation_count =", snapshot.get("observation_count"))
    print("parse_error_count =", snapshot.get("parse_error_count"))

    if not latest:
        print("latest = none yet")
        print("status = waiting for live_bot to reach an execute_trade path")
        return

    print()
    print("[LATEST]")
    print("line_no =", latest.get("line_no"))
    print("created_at =", latest.get("created_at"))
    print("setup_id =", latest.get("setup_id"))
    print("strategy =", latest.get("strategy"))
    print("signal =", latest.get("signal"))
    print("bucket =", latest.get("bucket"))
    print("mode =", latest.get("mode"))
    print("approved =", latest.get("approved"))
    print("confidence =", latest.get("confidence"))
    print("score_delta =", latest.get("score_delta"))
    print("module_count =", latest.get("module_count"))

    risky_modules = latest.get("risky_modules") or []

    if risky_modules:
        print()
        print("[RISK MODULES]")
        for item in risky_modules[:8]:
            print(
                f"- {item.get('module')} | "
                f"status={item.get('status')} | "
                f"score_delta={item.get('score_delta')} | "
                f"risk_flags={item.get('risk_flags')}"
            )
    else:
        print("risk_modules = none")


def main():
    configure_utf8_console_output()

    parser = argparse.ArgumentParser(
        description="Watch live confirmation observations while live_bot runs."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
        help="Account data directory.",
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Seconds between checks.",
    )

    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Number of iterations. 0 = run until Ctrl+C.",
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one check only.",
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)

    iteration = 0

    while True:
        iteration += 1

        rows = read_jsonl(paths["observations_file"])
        summary = summarize_latest(rows)

        snapshot = {
            "checked_at": datetime.now().isoformat(timespec="seconds"),
            "account_name": paths["account_name"],
            "observations_file": str(paths["observations_file"]),
            "file_exists": paths["observations_file"].exists(),
            "file_mtime": format_mtime(paths["observations_file"]),
            "observation_count": summary.get("observation_count"),
            "parse_error_count": summary.get("parse_error_count"),
            "latest": summary.get("latest"),
            "notes": [
                "Read-only monitor.",
                "This script does not open MT5 orders.",
                "Confirmation engine remains observe-only.",
            ],
        }

        write_json(paths["monitor_report_file"], snapshot)
        print_snapshot(snapshot)

        if args.once:
            break

        if args.iterations and iteration >= args.iterations:
            break

        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()
