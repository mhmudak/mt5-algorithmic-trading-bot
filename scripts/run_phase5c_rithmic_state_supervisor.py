from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKER_PATH = PROJECT_ROOT / "scripts" / "run_phase5c_rithmic_state_cache.py"
EVIDENCE_WATCHER_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "run_phase5g_rithmic_evidence_watcher.py"
)

DEFAULT_WORKER_DURATION_SECONDS = 86400
DEFAULT_RESTART_DELAY_SECONDS = 5.0
DEFAULT_RAPID_EXIT_THRESHOLD_SECONDS = 30.0
DEFAULT_RAPID_EXIT_BACKOFF_SECONDS = 30.0
DEFAULT_EVIDENCE_POLL_INTERVAL_SECONDS = 0.5
DEFAULT_EVIDENCE_REFRESH_INTERVAL_SECONDS = 2.0
DEFAULT_EVIDENCE_RESTART_DELAY_SECONDS = 5.0
DEFAULT_EVIDENCE_RAPID_EXIT_THRESHOLD_SECONDS = 30.0
DEFAULT_EVIDENCE_RAPID_EXIT_BACKOFF_SECONDS = 30.0
SUPERVISOR_MONITOR_INTERVAL_SECONDS = 0.25


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Continuously supervise the observe-only Phase 5C Rithmic state-cache "
            "worker. This process has no MT5 execution authority."
        )
    )
    parser.add_argument("--symbol", default=os.getenv("RITHMIC_SYMBOL") or None)
    parser.add_argument("--exchange", default=os.getenv("RITHMIC_EXCHANGE") or "COMEX")
    parser.add_argument(
        "--worker-duration-seconds",
        type=int,
        default=DEFAULT_WORKER_DURATION_SECONDS,
        help="Finite child-worker duration. Supervisor restarts after normal expiry.",
    )
    parser.add_argument("--rolling-window-seconds", type=int, default=300)
    parser.add_argument("--bucket-seconds", type=int, default=60)
    parser.add_argument("--stale-after-seconds", type=int, default=15)
    parser.add_argument("--tick-size", type=float, default=0.1)
    parser.add_argument("--snapshot-interval-seconds", type=int, default=2)
    parser.add_argument(
        "--restart-delay-seconds",
        type=float,
        default=DEFAULT_RESTART_DELAY_SECONDS,
    )
    parser.add_argument(
        "--rapid-exit-threshold-seconds",
        type=float,
        default=DEFAULT_RAPID_EXIT_THRESHOLD_SECONDS,
    )
    parser.add_argument(
        "--rapid-exit-backoff-seconds",
        type=float,
        default=DEFAULT_RAPID_EXIT_BACKOFF_SECONDS,
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="0 = unlimited supervisor cycles; positive values are useful for testing.",
    )
    parser.add_argument(
        "--evidence-poll-interval-seconds",
        type=float,
        default=DEFAULT_EVIDENCE_POLL_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--evidence-refresh-interval-seconds",
        type=float,
        default=DEFAULT_EVIDENCE_REFRESH_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--evidence-restart-delay-seconds",
        type=float,
        default=DEFAULT_EVIDENCE_RESTART_DELAY_SECONDS,
    )
    parser.add_argument(
        "--evidence-rapid-exit-threshold-seconds",
        type=float,
        default=DEFAULT_EVIDENCE_RAPID_EXIT_THRESHOLD_SECONDS,
    )
    parser.add_argument(
        "--evidence-rapid-exit-backoff-seconds",
        type=float,
        default=DEFAULT_EVIDENCE_RAPID_EXIT_BACKOFF_SECONDS,
    )
    parser.add_argument("--output-dir", default="data/order_flow/rithmic")
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if not args.symbol:
        raise SystemExit(
            "[STOP] RITHMIC_SYMBOL is not configured. "
            "Pass --symbol explicitly or set RITHMIC_SYMBOL in .env."
        )
    if args.worker_duration_seconds <= 0:
        raise SystemExit("[STOP] --worker-duration-seconds must be > 0.")
    if args.rolling_window_seconds <= 0:
        raise SystemExit("[STOP] --rolling-window-seconds must be > 0.")
    if args.bucket_seconds <= 0:
        raise SystemExit("[STOP] --bucket-seconds must be > 0.")
    if args.stale_after_seconds <= 0:
        raise SystemExit("[STOP] --stale-after-seconds must be > 0.")
    if args.tick_size <= 0:
        raise SystemExit("[STOP] --tick-size must be > 0.")
    if args.snapshot_interval_seconds <= 0:
        raise SystemExit("[STOP] --snapshot-interval-seconds must be > 0.")
    if args.restart_delay_seconds < 0:
        raise SystemExit("[STOP] --restart-delay-seconds must be >= 0.")
    if args.rapid_exit_threshold_seconds < 0:
        raise SystemExit("[STOP] --rapid-exit-threshold-seconds must be >= 0.")
    if args.rapid_exit_backoff_seconds < 0:
        raise SystemExit("[STOP] --rapid-exit-backoff-seconds must be >= 0.")
    if args.max_cycles < 0:
        raise SystemExit("[STOP] --max-cycles must be >= 0.")
    if args.evidence_poll_interval_seconds <= 0:
        raise SystemExit(
            "[STOP] --evidence-poll-interval-seconds must be > 0."
        )
    if args.evidence_refresh_interval_seconds <= 0:
        raise SystemExit(
            "[STOP] --evidence-refresh-interval-seconds must be > 0."
        )
    if args.evidence_restart_delay_seconds < 0:
        raise SystemExit(
            "[STOP] --evidence-restart-delay-seconds must be >= 0."
        )
    if args.evidence_rapid_exit_threshold_seconds < 0:
        raise SystemExit(
            "[STOP] --evidence-rapid-exit-threshold-seconds must be >= 0."
        )
    if args.evidence_rapid_exit_backoff_seconds < 0:
        raise SystemExit(
            "[STOP] --evidence-rapid-exit-backoff-seconds must be >= 0."
        )


def build_worker_command(args: argparse.Namespace) -> list[str]:
    validate_args(args)
    return [
        sys.executable,
        str(WORKER_PATH),
        "--symbol",
        str(args.symbol),
        "--exchange",
        str(args.exchange),
        "--duration-seconds",
        str(args.worker_duration_seconds),
        "--rolling-window-seconds",
        str(args.rolling_window_seconds),
        "--bucket-seconds",
        str(args.bucket_seconds),
        "--stale-after-seconds",
        str(args.stale_after_seconds),
        "--tick-size",
        str(args.tick_size),
        "--snapshot-interval-seconds",
        str(args.snapshot_interval_seconds),
        "--include-order-book",
        "--output-dir",
        str(args.output_dir),
    ]


def build_evidence_command(
    args: argparse.Namespace,
) -> list[str]:
    validate_args(args)

    return [
        sys.executable,
        str(EVIDENCE_WATCHER_PATH),
        "--symbol",
        str(args.symbol),
        "--input-dir",
        str(args.output_dir),
        "--output-dir",
        str(args.output_dir),
        "--stale-after-seconds",
        str(args.stale_after_seconds),
        "--tick-size",
        str(args.tick_size),
        "--poll-interval-seconds",
        str(args.evidence_poll_interval_seconds),
        "--refresh-interval-seconds",
        str(args.evidence_refresh_interval_seconds),
    ]


def evidence_restart_delay(
    args: argparse.Namespace,
    runtime_seconds: float,
) -> float:
    rapid_exit = (
        runtime_seconds
        < args.evidence_rapid_exit_threshold_seconds
    )

    if rapid_exit:
        return float(
            args.evidence_rapid_exit_backoff_seconds
        )

    return float(
        args.evidence_restart_delay_seconds
    )


def _maintain_evidence_child(
    *,
    args: argparse.Namespace,
    command: list[str],
    process: subprocess.Popen | None,
    started_at: float | None,
    restart_at: float | None,
    now: float | None = None,
) -> tuple[
    subprocess.Popen | None,
    float | None,
    float | None,
]:
    current = (
        time.monotonic()
        if now is None
        else float(now)
    )

    if process is not None:
        return_code = process.poll()

        if return_code is not None:
            runtime_seconds = max(
                0.0,
                current - float(started_at or current),
            )

            delay = evidence_restart_delay(
                args,
                runtime_seconds,
            )

            print(
                "[EVIDENCE SUPERVISOR] Watcher exited "
                f"return_code={return_code} "
                f"runtime_seconds={runtime_seconds:.1f}"
            )

            print(
                "[EVIDENCE SUPERVISOR] Restart scheduled "
                f"in {delay:.1f}s"
            )

            process = None
            started_at = None
            restart_at = current + delay

    if (
        process is None
        and (
            restart_at is None
            or current >= restart_at
        )
    ):
        try:
            process = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
            )

        except Exception as exc:
            delay = float(
                args.evidence_rapid_exit_backoff_seconds
            )

            print(
                "[EVIDENCE SUPERVISOR] Watcher launch "
                "failed-open | "
                f"error={type(exc).__name__}: {exc}"
            )

            print(
                "[EVIDENCE SUPERVISOR] Restart scheduled "
                f"in {delay:.1f}s"
            )

            restart_at = current + delay

            return (
                None,
                None,
                restart_at,
            )

        started_at = current
        restart_at = None

        print(
            "[EVIDENCE SUPERVISOR] Phase 5G watcher started"
        )

    return (
        process,
        started_at,
        restart_at,
    )


def _stop_child_after_interrupt(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return

    # Ctrl+C is normally delivered to both parent and child in the same console.
    # Give the Phase 5C worker a short grace period to execute its own cleanup/finally.
    try:
        process.wait(timeout=5.0)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        process.terminate()
        process.wait(timeout=5.0)
        return
    except Exception:
        pass

    try:
        process.kill()
    except Exception:
        pass


def run_supervisor(args: argparse.Namespace) -> int:
    worker_command = build_worker_command(args)
    evidence_command = build_evidence_command(args)

    cycle = 0

    evidence_process: subprocess.Popen | None = None
    evidence_started_at: float | None = None
    evidence_restart_at: float | None = None

    print("[START] Phase 5C + Phase 5G Rithmic supervisor")
    print("symbol =", args.symbol)
    print("exchange =", args.exchange)
    print(
        "worker_duration_seconds =",
        args.worker_duration_seconds,
    )
    print(
        "snapshot_interval_seconds =",
        args.snapshot_interval_seconds,
    )
    print(
        "evidence_refresh_interval_seconds =",
        args.evidence_refresh_interval_seconds,
    )
    print("include_order_book = True")
    print("max_cycles =", args.max_cycles)
    print("decision_impact = NONE")
    print("can_influence_decision = False")
    print("execution_allowed = False")
    print(
        "[SAFETY] Supervisor manages Rithmic market-data "
        "and observe-only evidence lifecycle only; "
        "it never starts live_bot."
    )
    print(
        "[SAFETY] Evidence watcher failures never stop "
        "Phase 5C market-data collection."
    )

    while True:
        cycle += 1

        print("")
        print(
            f"[SUPERVISOR] Starting Phase 5C "
            f"worker cycle={cycle}"
        )

        worker_started_at = time.monotonic()

        worker_process = subprocess.Popen(
            worker_command,
            cwd=str(PROJECT_ROOT),
        )

        (
            evidence_process,
            evidence_started_at,
            evidence_restart_at,
        ) = _maintain_evidence_child(
            args=args,
            command=evidence_command,
            process=evidence_process,
            started_at=evidence_started_at,
            restart_at=evidence_restart_at,
        )

        try:
            while worker_process.poll() is None:
                (
                    evidence_process,
                    evidence_started_at,
                    evidence_restart_at,
                ) = _maintain_evidence_child(
                    args=args,
                    command=evidence_command,
                    process=evidence_process,
                    started_at=evidence_started_at,
                    restart_at=evidence_restart_at,
                )

                time.sleep(
                    SUPERVISOR_MONITOR_INTERVAL_SECONDS
                )

        except KeyboardInterrupt:
            print("")
            print(
                "[SUPERVISOR] Stop requested by user."
            )

            _stop_child_after_interrupt(
                worker_process
            )

            if evidence_process is not None:
                _stop_child_after_interrupt(
                    evidence_process
                )

            print(
                "[STOPPED] Rithmic market-data + "
                "evidence supervisor stopped."
            )

            return 0

        return_code = worker_process.returncode

        runtime_seconds = max(
            0.0,
            time.monotonic() - worker_started_at,
        )

        print(
            "[SUPERVISOR] Worker exited "
            f"cycle={cycle} "
            f"return_code={return_code} "
            f"runtime_seconds={runtime_seconds:.1f}"
        )

        if (
            args.max_cycles > 0
            and cycle >= args.max_cycles
        ):
            if evidence_process is not None:
                _stop_child_after_interrupt(
                    evidence_process
                )

            print(
                "[DONE] max_cycles reached; "
                "supervisor exiting."
            )

            return int(return_code or 0)

        rapid_exit = (
            runtime_seconds
            < args.rapid_exit_threshold_seconds
        )

        delay = (
            args.rapid_exit_backoff_seconds
            if rapid_exit
            else args.restart_delay_seconds
        )

        reason = (
            "rapid_exit_backoff"
            if rapid_exit
            else "normal_restart_delay"
        )

        print(
            "[SUPERVISOR] Phase 5C restart scheduled "
            f"in {delay:.1f}s reason={reason}"
        )

        restart_deadline = (
            time.monotonic() + delay
        )

        try:
            while True:
                now = time.monotonic()

                if now >= restart_deadline:
                    break

                (
                    evidence_process,
                    evidence_started_at,
                    evidence_restart_at,
                ) = _maintain_evidence_child(
                    args=args,
                    command=evidence_command,
                    process=evidence_process,
                    started_at=evidence_started_at,
                    restart_at=evidence_restart_at,
                    now=now,
                )

                remaining = max(
                    0.0,
                    restart_deadline - now,
                )

                time.sleep(
                    min(
                        SUPERVISOR_MONITOR_INTERVAL_SECONDS,
                        remaining,
                    )
                )

        except KeyboardInterrupt:
            print("")

            if evidence_process is not None:
                _stop_child_after_interrupt(
                    evidence_process
                )

            print(
                "[STOPPED] Rithmic supervisor stopped "
                "during Phase 5C restart delay."
            )

            return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    validate_args(args)

    if not WORKER_PATH.exists():
        raise SystemExit(
            f"[STOP] Phase 5C worker not found: {WORKER_PATH}"
        )

    if not EVIDENCE_WATCHER_PATH.exists():
        raise SystemExit(
            f"[STOP] Phase 5G evidence watcher not found: "
            f"{EVIDENCE_WATCHER_PATH}"
        )

    return run_supervisor(args)


if __name__ == "__main__":
    raise SystemExit(main())
