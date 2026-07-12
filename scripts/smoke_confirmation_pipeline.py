import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.confirmation_engine import run_universal_confirmation, format_confirmation_report
from src.confirmation_observation_logger import (
    get_confirmation_observations_file,
    log_confirmation_observation,
)
from src.confirmation_risk_notifier import build_confirmation_risk_alert


def build_test_dataframe():
    rows = []
    base = 2400.0

    for i in range(40):
        rows.append({
            "open": base + ((i % 5) - 2) * 0.4,
            "high": base + 5 + (i % 3) * 0.2,
            "low": base - 5 - (i % 2) * 0.2,
            "close": base + ((i % 7) - 3) * 0.35,
            "atr_14": 2.5,
            "ema_20": base,
            "tick_volume": 100 + (i % 8) * 10,
            "real_volume": 0,
        })

    return pd.DataFrame(rows)


def read_jsonl(path):
    path = Path(path)

    if not path.exists():
        return []

    records = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                records.append(json.loads(line))
            except Exception:
                continue

    return records


def restore_file(path, original_bytes):
    path = Path(path)

    if original_bytes is None:
        path.unlink(missing_ok=True)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(original_bytes)


def run_analyzer(source_dir, min_samples=1):
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "analyze_confirmation_observations.py"),
        "--source-dir",
        str(source_dir),
        "--min-samples",
        str(min_samples),
    ]

    completed = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
    )

    return completed


def read_summary_for_account(account_dir):
    account_name = Path(account_dir).name
    summary_path = (
        PROJECT_ROOT
        / "data"
        / "strategy_intelligence"
        / account_name
        / "confirmation_observation_summary.json"
    )

    if not summary_path.exists():
        return summary_path, None

    with summary_path.open("r", encoding="utf-8") as f:
        return summary_path, json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Smoke-test confirmation observation pipeline without opening a trade."
    )

    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep the synthetic smoke observation in confirmation_observations.jsonl.",
    )

    parser.add_argument(
        "--source-dir",
        default=None,
        help="Optional account directory. If omitted, uses account_context default.",
    )

    parser.add_argument(
        "--min-samples",
        type=int,
        default=1,
    )

    args = parser.parse_args()

    if args.source_dir:
        account_dir = Path(args.source_dir)
        observations_file = account_dir / "confirmation_observations.jsonl"
    else:
        observations_file = get_confirmation_observations_file()
        account_dir = observations_file.parent

    observations_file = Path(observations_file)
    account_dir = Path(account_dir)

    original_bytes = observations_file.read_bytes() if observations_file.exists() else None

    smoke_setup_id = "SMOKE-CONFIRMATION-PIPELINE-" + datetime.now().strftime("%Y%m%d%H%M%S")

    signal_data = {
        "setup_id": smoke_setup_id,
        "strategy": "RANGE_SWEEP_RECLAIM",
        "signal": "BUY",
        "entry_model": "SWEEP_RECLAIM",
        "market_condition": "RANGING",
        "session": "NEWYORK_OPEN",
        "setup_source_bucket": "PIPELINE_SMOKE_TEST",
    }

    trade_plan = {
        "setup_id": smoke_setup_id,
        "strategy": "RANGE_SWEEP_RECLAIM",
        "signal": "BUY",
        "entry_price": 2397.0,
        "stop_loss": 2392.0,
        "take_profit": 2406.0,
        "rr": 1.8,
        "setup_source_bucket": "PIPELINE_SMOKE_TEST",
    }

    try:
        report = run_universal_confirmation(
            signal_data=signal_data,
            trade_plan=trade_plan,
            df=build_test_dataframe(),
            tick=None,
            session="NEWYORK_OPEN",
            market_condition="RANGING",
            orderflow_snapshot=None,
            min_rr=1.2,
            max_spread=0.5,
            enforce_required=False,
        )

        print(format_confirmation_report(report))
        print()

        alert = build_confirmation_risk_alert(
            report=report,
            signal_data=signal_data,
            trade_plan=trade_plan,
            setup_source_bucket="PIPELINE_SMOKE_TEST",
        )

        print("risk_alert_should_notify =", alert.get("should_notify"))
        print("risk_alert_module =", alert.get("module"))
        print()

        saved_path = log_confirmation_observation(
            report=report,
            signal_data=signal_data,
            trade_plan=trade_plan,
            setup_source_bucket="PIPELINE_SMOKE_TEST",
            notes="Phase 1J smoke test. No trade opened.",
            file_path=observations_file,
        )

        records = read_jsonl(saved_path)
        matching = [
            record
            for record in records
            if record.get("setup_id") == smoke_setup_id
        ]

        print("observations_file =", saved_path)
        print("account_dir =", account_dir)
        print("smoke_setup_id =", smoke_setup_id)
        print("smoke_record_written =", bool(matching))
        print("observation_count_after_write =", len(records))

        if not matching:
            raise SystemExit("Smoke observation was not found in confirmation_observations.jsonl")

        completed = run_analyzer(account_dir, min_samples=args.min_samples)

        print()
        print("[ANALYZER STDOUT]")
        print(completed.stdout.strip())

        if completed.stderr.strip():
            print()
            print("[ANALYZER STDERR]")
            print(completed.stderr.strip())

        if completed.returncode != 0:
            raise SystemExit(f"Analyzer failed with return code {completed.returncode}")

        summary_path, summary = read_summary_for_account(account_dir)

        print()
        print("summary_path =", summary_path)

        if not summary:
            raise SystemExit("Analyzer summary was not created.")

        print("summary_observation_count =", summary.get("observation_count"))
        print("summary_module_row_count =", summary.get("module_row_count"))

        if int(summary.get("observation_count") or 0) < 1:
            raise SystemExit("Analyzer did not see the smoke observation.")

        if int(summary.get("module_row_count") or 0) < 1:
            raise SystemExit("Analyzer did not build module rows.")

        print()
        print("[PIPELINE SMOKE] OK")
        print("No MT5 order was opened. This test used only synthetic confirmation data.")

    finally:
        if not args.keep:
            restore_file(observations_file, original_bytes)

            # Reset analyzer outputs back to the restored observation file state.
            reset = run_analyzer(account_dir, min_samples=args.min_samples)

            print()
            print("[PIPELINE SMOKE] Restored confirmation_observations.jsonl")
            print("restore_analyzer_returncode =", reset.returncode)
        else:
            print()
            print("[PIPELINE SMOKE] --keep used, smoke observation was kept.")


if __name__ == "__main__":
    main()
