from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import time
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_phase5g_rithmic_monitoring_bridge import (
    main as build_phase5g_bridge_main,
)


DEFAULT_POLL_INTERVAL_SECONDS = 0.50
DEFAULT_REFRESH_INTERVAL_SECONDS = 2.0
DEFAULT_STALE_AFTER_SECONDS = 15


def parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Observe the Phase 5C Rithmic state snapshot and refresh "
            "the observe-only Phase 5G evidence bridge when new state "
            "is available. This process has no MT5 execution authority."
        )
    )

    parser.add_argument(
        "--symbol",
        default=os.getenv("RITHMIC_SYMBOL") or None,
    )
    parser.add_argument(
        "--input-dir",
        default="data/order_flow/rithmic",
    )
    parser.add_argument(
        "--output-dir",
        default="data/order_flow/rithmic",
    )
    parser.add_argument(
        "--stale-after-seconds",
        type=int,
        default=DEFAULT_STALE_AFTER_SECONDS,
    )
    parser.add_argument(
        "--tick-size",
        type=float,
        default=0.1,
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--refresh-interval-seconds",
        type=float,
        default=DEFAULT_REFRESH_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--signal",
        choices=("BUY", "SELL"),
        default=None,
    )
    parser.add_argument(
        "--session",
        default="UNSPECIFIED",
    )
    parser.add_argument(
        "--max-builds",
        type=int,
        default=0,
        help="0 = unlimited; positive values are for deterministic tests.",
    )
    parser.add_argument(
        "--verbose-build-output",
        action="store_true",
    )

    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if not args.symbol:
        raise SystemExit(
            "[STOP] RITHMIC_SYMBOL is not configured. "
            "Pass --symbol explicitly or set RITHMIC_SYMBOL."
        )

    if args.stale_after_seconds <= 0:
        raise SystemExit(
            "[STOP] --stale-after-seconds must be > 0."
        )

    if args.tick_size <= 0:
        raise SystemExit(
            "[STOP] --tick-size must be > 0."
        )

    if args.poll_interval_seconds <= 0:
        raise SystemExit(
            "[STOP] --poll-interval-seconds must be > 0."
        )

    if args.refresh_interval_seconds <= 0:
        raise SystemExit(
            "[STOP] --refresh-interval-seconds must be > 0."
        )

    if args.max_builds < 0:
        raise SystemExit(
            "[STOP] --max-builds must be >= 0."
        )


def state_path_for(args: argparse.Namespace) -> Path:
    safe_symbol = (
        str(args.symbol)
        .replace("/", "_")
        .replace("\\", "_")
        .replace(".", "_")
    )

    return (
        Path(args.input_dir)
        / f"{safe_symbol}_phase5c_rithmic_state_latest.json"
    )


def snapshot_identity(path: Path) -> tuple[int, int]:
    stat = path.stat()

    return (
        int(stat.st_mtime_ns),
        int(stat.st_size),
    )


def build_bridge_argv(
    args: argparse.Namespace,
) -> list[str]:
    argv = [
        "--symbol",
        str(args.symbol),
        "--input-dir",
        str(args.input_dir),
        "--output-dir",
        str(args.output_dir),
        "--stale-after-seconds",
        str(args.stale_after_seconds),
        "--tick-size",
        str(args.tick_size),
        "--session",
        str(args.session),
    ]

    if args.signal:
        argv.extend(
            [
                "--signal",
                str(args.signal),
            ]
        )

    return argv


def _run_bridge_once(
    args: argparse.Namespace,
) -> None:
    argv = build_bridge_argv(args)

    if args.verbose_build_output:
        build_phase5g_bridge_main(argv)
        return

    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        build_phase5g_bridge_main(argv)


def run_watcher(args: argparse.Namespace) -> int:
    validate_args(args)

    snapshot_path = state_path_for(args)

    last_successful_identity: tuple[int, int] | None = None
    last_attempt_at = 0.0
    successful_builds = 0
    failed_builds = 0

    print("[START] Phase 5G Rithmic evidence watcher")
    print("symbol =", args.symbol)
    print("snapshot =", snapshot_path)
    print(
        "refresh_interval_seconds =",
        args.refresh_interval_seconds,
    )
    print(
        "poll_interval_seconds =",
        args.poll_interval_seconds,
    )
    print("decision_impact = NONE")
    print("can_influence_decision = False")
    print("safe_for_execution = False")
    print("execution_allowed = False")
    print(
        "[SAFETY] Evidence refresh is isolated from "
        "Phase 5C market-data collection and MT5 execution."
    )

    waiting_logged = False

    while True:
        now = time.monotonic()

        if not snapshot_path.exists():
            if not waiting_logged:
                print(
                    "[EVIDENCE] Waiting for Phase 5C snapshot:",
                    snapshot_path,
                )
                waiting_logged = True

            time.sleep(args.poll_interval_seconds)
            continue

        waiting_logged = False

        try:
            identity = snapshot_identity(snapshot_path)
        except OSError as exc:
            print(
                "[EVIDENCE] Snapshot stat failed; retrying |",
                repr(exc),
            )
            time.sleep(args.poll_interval_seconds)
            continue

        changed = identity != last_successful_identity

        refresh_due = (
            now - last_attempt_at
            >= args.refresh_interval_seconds
        )

        if changed and refresh_due:
            last_attempt_at = now

            try:
                _run_bridge_once(args)

            except SystemExit as exc:
                code = int(exc.code or 0)

                if code != 0:
                    failed_builds += 1
                    print(
                        "[EVIDENCE] Bridge build failed-open | "
                        f"system_exit={code} "
                        f"failed_builds={failed_builds}"
                    )

                    time.sleep(args.poll_interval_seconds)
                    continue

            except Exception as exc:
                failed_builds += 1

                print(
                    "[EVIDENCE] Bridge build failed-open | "
                    f"error={type(exc).__name__}: {exc} "
                    f"failed_builds={failed_builds}"
                )

                time.sleep(args.poll_interval_seconds)
                continue

            last_successful_identity = identity
            successful_builds += 1

            print(
                "[EVIDENCE] Bridge refreshed | "
                f"successful_builds={successful_builds} "
                f"failed_builds={failed_builds}"
            )

            if (
                args.max_builds > 0
                and successful_builds >= args.max_builds
            ):
                print(
                    "[DONE] max_builds reached; "
                    "evidence watcher exiting."
                )
                return 0

        time.sleep(args.poll_interval_seconds)


def main(
    argv: Sequence[str] | None = None,
) -> int:
    args = parse_args(argv)

    try:
        return run_watcher(args)
    except KeyboardInterrupt:
        print("")
        print(
            "[STOPPED] Rithmic evidence watcher "
            "stopped by user."
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
