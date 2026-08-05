from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import MetaTrader5 as mt5

from src.account_context import (
    get_account_key,
    get_account_data_dir,
    get_account_intelligence_dir,
)


def run_once(min_samples: int) -> int:
    source_dir = get_account_data_dir()
    output_dir = get_account_intelligence_dir()

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "analyze_strategy_performance.py"),
        "--source-dir",
        str(source_dir),
        "--output-dir",
        str(output_dir),
        "--min-samples",
        str(min_samples),
    ]

    print("\n=== CURRENT ACCOUNT STAT REFRESH ===")
    print("account_key =", get_account_key())
    print("source_dir =", source_dir)
    print("output_dir =", output_dir)
    print("command =", " ".join(cmd))

    completed = subprocess.run(cmd, cwd=str(ROOT))
    return completed.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval-seconds", type=int, default=900)
    parser.add_argument("--min-samples", type=int, default=5)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    initialized = mt5.initialize()
    print("mt5 initialized:", initialized)
    print("last_error:", mt5.last_error())

    if not initialized:
        raise SystemExit("[STOP] MT5 initialization failed. Open MT5 and log into the target account first.")

    if args.once:
        raise SystemExit(run_once(args.min_samples))

    while True:
        rc = run_once(args.min_samples)
        if rc != 0:
            print("[WARN] analyzer returned non-zero exit code:", rc)

        print("sleeping_seconds =", args.interval_seconds)
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
