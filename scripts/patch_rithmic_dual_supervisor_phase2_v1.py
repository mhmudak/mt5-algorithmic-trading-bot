from pathlib import Path
import datetime
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_BRANCH = "feature/rithmic-setup-verdict-supervisor"
EXPECTED_HEAD = "1c08471"

SUPERVISOR = ROOT / "scripts" / "run_phase5c_rithmic_state_supervisor.py"
SUPERVISOR_TEST = ROOT / "scripts" / "test_phase5c_rithmic_state_supervisor_v1.py"
WATCHER = ROOT / "scripts" / "run_phase5g_rithmic_evidence_watcher.py"
WATCHER_TEST = ROOT / "scripts" / "test_phase5g_rithmic_evidence_watcher_v1.py"

stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    ROOT
    / "local_backups"
    / f"rithmic_dual_supervisor_phase2_{stamp}"
)


def run(*args, check=True):
    result = subprocess.run(
        list(args),
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    if check and result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(
            f"command failed rc={result.returncode}: {' '.join(args)}"
        )

    return result


def require_clean_target(path: Path):
    rel = str(path.relative_to(ROOT))

    unstaged = run(
        "git",
        "diff",
        "--quiet",
        "--",
        rel,
        check=False,
    )

    if unstaged.returncode != 0:
        raise RuntimeError(
            f"tracked target has unstaged changes: {rel}"
        )

    staged = run(
        "git",
        "diff",
        "--cached",
        "--quiet",
        "--",
        rel,
        check=False,
    )

    if staged.returncode != 0:
        raise RuntimeError(
            f"tracked target has staged changes: {rel}"
        )


branch = run(
    "git",
    "rev-parse",
    "--abbrev-ref",
    "HEAD",
).stdout.strip()

head = run(
    "git",
    "rev-parse",
    "--short",
    "HEAD",
).stdout.strip()

if branch != EXPECTED_BRANCH:
    raise SystemExit(
        f"[STOP] branch mismatch: expected={EXPECTED_BRANCH} got={branch}"
    )

if head != EXPECTED_HEAD:
    raise SystemExit(
        f"[STOP] HEAD mismatch: expected={EXPECTED_HEAD} got={head}"
    )

for path in (
    SUPERVISOR,
    SUPERVISOR_TEST,
    WATCHER,
    WATCHER_TEST,
):
    if not path.exists():
        raise SystemExit(f"[STOP] required file missing: {path}")

require_clean_target(SUPERVISOR)
require_clean_target(SUPERVISOR_TEST)

BACKUP.mkdir(parents=True, exist_ok=False)

shutil.copy2(
    SUPERVISOR,
    BACKUP / SUPERVISOR.name,
)
shutil.copy2(
    SUPERVISOR_TEST,
    BACKUP / SUPERVISOR_TEST.name,
)

original_supervisor = SUPERVISOR.read_text(
    encoding="utf-8-sig"
)

original_test = SUPERVISOR_TEST.read_text(
    encoding="utf-8-sig"
)

try:
    text = original_supervisor

    # ------------------------------------------------------------
    # 1. Add watcher path + defaults
    # ------------------------------------------------------------

    old = (
        'WORKER_PATH = PROJECT_ROOT / "scripts" / '
        '"run_phase5c_rithmic_state_cache.py"\n'
    )

    new = (
        'WORKER_PATH = PROJECT_ROOT / "scripts" / '
        '"run_phase5c_rithmic_state_cache.py"\n'
        'EVIDENCE_WATCHER_PATH = (\n'
        '    PROJECT_ROOT\n'
        '    / "scripts"\n'
        '    / "run_phase5g_rithmic_evidence_watcher.py"\n'
        ')\n'
    )

    if old not in text:
        raise RuntimeError("worker path anchor missing")

    text = text.replace(old, new, 1)

    old = (
        "DEFAULT_RAPID_EXIT_BACKOFF_SECONDS = 30.0\n"
    )

    new = (
        "DEFAULT_RAPID_EXIT_BACKOFF_SECONDS = 30.0\n"
        "DEFAULT_EVIDENCE_POLL_INTERVAL_SECONDS = 0.5\n"
        "DEFAULT_EVIDENCE_REFRESH_INTERVAL_SECONDS = 2.0\n"
        "DEFAULT_EVIDENCE_RESTART_DELAY_SECONDS = 5.0\n"
        "DEFAULT_EVIDENCE_RAPID_EXIT_THRESHOLD_SECONDS = 30.0\n"
        "DEFAULT_EVIDENCE_RAPID_EXIT_BACKOFF_SECONDS = 30.0\n"
        "SUPERVISOR_MONITOR_INTERVAL_SECONDS = 0.25\n"
    )

    if old not in text:
        raise RuntimeError("constant anchor missing")

    text = text.replace(old, new, 1)

    # ------------------------------------------------------------
    # 2. Add CLI options
    # ------------------------------------------------------------

    old = (
        '    parser.add_argument("--output-dir", '
        'default="data/order_flow/rithmic")\n'
    )

    new = (
        "    parser.add_argument(\n"
        '        "--evidence-poll-interval-seconds",\n'
        "        type=float,\n"
        "        default=DEFAULT_EVIDENCE_POLL_INTERVAL_SECONDS,\n"
        "    )\n"
        "    parser.add_argument(\n"
        '        "--evidence-refresh-interval-seconds",\n'
        "        type=float,\n"
        "        default=DEFAULT_EVIDENCE_REFRESH_INTERVAL_SECONDS,\n"
        "    )\n"
        "    parser.add_argument(\n"
        '        "--evidence-restart-delay-seconds",\n'
        "        type=float,\n"
        "        default=DEFAULT_EVIDENCE_RESTART_DELAY_SECONDS,\n"
        "    )\n"
        "    parser.add_argument(\n"
        '        "--evidence-rapid-exit-threshold-seconds",\n'
        "        type=float,\n"
        "        default=DEFAULT_EVIDENCE_RAPID_EXIT_THRESHOLD_SECONDS,\n"
        "    )\n"
        "    parser.add_argument(\n"
        '        "--evidence-rapid-exit-backoff-seconds",\n'
        "        type=float,\n"
        "        default=DEFAULT_EVIDENCE_RAPID_EXIT_BACKOFF_SECONDS,\n"
        "    )\n"
        '    parser.add_argument("--output-dir", '
        'default="data/order_flow/rithmic")\n'
    )

    if old not in text:
        raise RuntimeError("CLI output-dir anchor missing")

    text = text.replace(old, new, 1)

    # ------------------------------------------------------------
    # 3. Validate evidence watcher arguments
    # ------------------------------------------------------------

    old = (
        "    if args.max_cycles < 0:\n"
        '        raise SystemExit("[STOP] --max-cycles must be >= 0.")\n'
    )

    new = (
        "    if args.max_cycles < 0:\n"
        '        raise SystemExit("[STOP] --max-cycles must be >= 0.")\n'
        "    if args.evidence_poll_interval_seconds <= 0:\n"
        "        raise SystemExit(\n"
        '            "[STOP] --evidence-poll-interval-seconds must be > 0."\n'
        "        )\n"
        "    if args.evidence_refresh_interval_seconds <= 0:\n"
        "        raise SystemExit(\n"
        '            "[STOP] --evidence-refresh-interval-seconds must be > 0."\n'
        "        )\n"
        "    if args.evidence_restart_delay_seconds < 0:\n"
        "        raise SystemExit(\n"
        '            "[STOP] --evidence-restart-delay-seconds must be >= 0."\n'
        "        )\n"
        "    if args.evidence_rapid_exit_threshold_seconds < 0:\n"
        "        raise SystemExit(\n"
        '            "[STOP] --evidence-rapid-exit-threshold-seconds must be >= 0."\n'
        "        )\n"
        "    if args.evidence_rapid_exit_backoff_seconds < 0:\n"
        "        raise SystemExit(\n"
        '            "[STOP] --evidence-rapid-exit-backoff-seconds must be >= 0."\n'
        "        )\n"
    )

    if old not in text:
        raise RuntimeError("validation anchor missing")

    text = text.replace(old, new, 1)

    # ------------------------------------------------------------
    # 4. Add evidence watcher command builder
    # ------------------------------------------------------------

    anchor = "\n\ndef _stop_child_after_interrupt"

    if anchor not in text:
        raise RuntimeError("child-stop function anchor missing")

    evidence_helpers = r'''

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
'''

    text = text.replace(
        anchor,
        evidence_helpers + anchor,
        1,
    )

    # ------------------------------------------------------------
    # 5. Replace supervisor runtime loop
    # ------------------------------------------------------------

    start = text.index("def run_supervisor(")
    end = text.index("\ndef main(", start)

    new_run_supervisor = r'''def run_supervisor(args: argparse.Namespace) -> int:
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
'''

    text = (
        text[:start]
        + new_run_supervisor
        + "\n\n"
        + text[end + 1:]
    )

    # ------------------------------------------------------------
    # 6. Ensure watcher exists at startup
    # ------------------------------------------------------------

    old = (
        "    if not WORKER_PATH.exists():\n"
        "        raise SystemExit(\n"
        '            f"[STOP] Phase 5C worker not found: {WORKER_PATH}"\n'
        "        )\n"
        "\n"
        "    return run_supervisor(args)\n"
    )

    new = (
        "    if not WORKER_PATH.exists():\n"
        "        raise SystemExit(\n"
        '            f"[STOP] Phase 5C worker not found: {WORKER_PATH}"\n'
        "        )\n"
        "\n"
        "    if not EVIDENCE_WATCHER_PATH.exists():\n"
        "        raise SystemExit(\n"
        "            f\"[STOP] Phase 5G evidence watcher not found: \"\n"
        "            f\"{EVIDENCE_WATCHER_PATH}\"\n"
        "        )\n"
        "\n"
        "    return run_supervisor(args)\n"
    )

    if old not in text:
        raise RuntimeError("main startup-check anchor missing")

    text = text.replace(
        old,
        new,
        1,
    )

    SUPERVISOR.write_text(
        text,
        encoding="utf-8",
        newline="\n",
    )

    # ------------------------------------------------------------
    # Updated supervisor regression test
    # ------------------------------------------------------------

    test_source = r'''from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SUPERVISOR_PATH = (
    ROOT
    / "scripts"
    / "run_phase5c_rithmic_state_supervisor.py"
)

WORKER_PATH = (
    ROOT
    / "scripts"
    / "run_phase5c_rithmic_state_cache.py"
)

EVIDENCE_WATCHER_PATH = (
    ROOT
    / "scripts"
    / "run_phase5g_rithmic_evidence_watcher.py"
)


def _load_supervisor():
    spec = importlib.util.spec_from_file_location(
        "phase5c_rithmic_state_supervisor_test_target",
        SUPERVISOR_PATH,
    )

    if spec is None or spec.loader is None:
        raise AssertionError(
            "cannot load supervisor module"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def _assert(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(message)


class _ExitedProcess:
    def __init__(self, return_code: int):
        self.return_code = return_code

    def poll(self):
        return self.return_code


class _RunningProcess:
    def poll(self):
        return None


def main() -> None:
    _assert(
        SUPERVISOR_PATH.exists(),
        "supervisor script missing",
    )

    _assert(
        WORKER_PATH.exists(),
        "Phase 5C worker missing",
    )

    _assert(
        EVIDENCE_WATCHER_PATH.exists(),
        "Phase 5G watcher missing",
    )

    module = _load_supervisor()

    args = module.parse_args(
        [
            "--symbol",
            "GCZ6",
            "--exchange",
            "COMEX",
            "--worker-duration-seconds",
            "120",
            "--rolling-window-seconds",
            "300",
            "--bucket-seconds",
            "60",
            "--stale-after-seconds",
            "15",
            "--tick-size",
            "0.1",
            "--snapshot-interval-seconds",
            "2",
            "--restart-delay-seconds",
            "5",
            "--rapid-exit-threshold-seconds",
            "30",
            "--rapid-exit-backoff-seconds",
            "30",
            "--evidence-poll-interval-seconds",
            "0.5",
            "--evidence-refresh-interval-seconds",
            "2",
            "--evidence-restart-delay-seconds",
            "5",
            "--evidence-rapid-exit-threshold-seconds",
            "30",
            "--evidence-rapid-exit-backoff-seconds",
            "30",
            "--max-cycles",
            "1",
        ]
    )

    worker_command = module.build_worker_command(
        args
    )

    evidence_command = (
        module.build_evidence_command(args)
    )

    _assert(
        worker_command[0] == sys.executable,
        "worker must use current Python interpreter",
    )

    _assert(
        str(WORKER_PATH) in worker_command,
        "supervisor must launch existing Phase 5C worker",
    )

    _assert(
        "--include-order-book" in worker_command,
        "DOM subscription must remain mandatory",
    )

    _assert(
        worker_command[
            worker_command.index("--symbol") + 1
        ]
        == "GCZ6",
        "worker symbol plumbing mismatch",
    )

    _assert(
        worker_command[
            worker_command.index("--exchange") + 1
        ]
        == "COMEX",
        "worker exchange plumbing mismatch",
    )

    _assert(
        worker_command[
            worker_command.index(
                "--duration-seconds"
            )
            + 1
        ]
        == "120",
        "worker duration plumbing mismatch",
    )

    _assert(
        worker_command[
            worker_command.index(
                "--snapshot-interval-seconds"
            )
            + 1
        ]
        == "2",
        "snapshot interval plumbing mismatch",
    )

    _assert(
        evidence_command[0] == sys.executable,
        "evidence watcher must use current Python interpreter",
    )

    _assert(
        str(EVIDENCE_WATCHER_PATH)
        in evidence_command,
        "supervisor must launch Phase 5G watcher",
    )

    _assert(
        evidence_command[
            evidence_command.index("--symbol") + 1
        ]
        == "GCZ6",
        "evidence symbol plumbing mismatch",
    )

    _assert(
        evidence_command[
            evidence_command.index(
                "--refresh-interval-seconds"
            )
            + 1
        ]
        == "2.0",
        "evidence refresh plumbing mismatch",
    )

    _assert(
        evidence_command[
            evidence_command.index(
                "--stale-after-seconds"
            )
            + 1
        ]
        == "15",
        "evidence freshness plumbing mismatch",
    )

    source = SUPERVISOR_PATH.read_text(
        encoding="utf-8"
    )

    forbidden = [
        "src.live_bot",
        "import MetaTrader5",
        "order_send(",
        "place_order(",
        "execute_trade(",
    ]

    for marker in forbidden:
        _assert(
            marker not in source,
            f"forbidden execution coupling found: {marker}",
        )

    for marker in (
        "decision_impact = NONE",
        "can_influence_decision = False",
        "execution_allowed = False",
        "never starts live_bot",
        "Evidence watcher failures never stop",
    ):
        _assert(
            marker in source,
            f"safety marker missing: {marker}",
        )

    env_symbol = os.environ.get(
        "RITHMIC_SYMBOL"
    )

    os.environ["RITHMIC_SYMBOL"] = "GCZ6"

    try:
        env_args = module.parse_args([])

        _assert(
            env_args.symbol == "GCZ6",
            "RITHMIC_SYMBOL env default not honored",
        )

    finally:
        if env_symbol is None:
            os.environ.pop(
                "RITHMIC_SYMBOL",
                None,
            )
        else:
            os.environ[
                "RITHMIC_SYMBOL"
            ] = env_symbol

    invalid = module.parse_args(
        [
            "--symbol",
            "GCZ6",
            "--worker-duration-seconds",
            "0",
        ]
    )

    try:
        module.validate_args(invalid)

    except SystemExit as exc:
        _assert(
            "worker-duration-seconds must be > 0"
            in str(exc),
            "invalid worker-duration guard mismatch",
        )

    else:
        raise AssertionError(
            "zero worker duration must be rejected"
        )

    invalid_evidence = module.parse_args(
        [
            "--symbol",
            "GCZ6",
            "--evidence-refresh-interval-seconds",
            "0",
        ]
    )

    try:
        module.validate_args(
            invalid_evidence
        )

    except SystemExit as exc:
        _assert(
            "evidence-refresh-interval-seconds "
            "must be > 0"
            in str(exc),
            "invalid evidence refresh guard mismatch",
        )

    else:
        raise AssertionError(
            "zero evidence refresh interval "
            "must be rejected"
        )

    # --------------------------------------------------------
    # Independent evidence restart contract
    # --------------------------------------------------------

    dead = _ExitedProcess(7)

    (
        evidence_process,
        evidence_started_at,
        evidence_restart_at,
    ) = module._maintain_evidence_child(
        args=args,
        command=evidence_command,
        process=dead,
        started_at=0.0,
        restart_at=None,
        now=10.0,
    )

    _assert(
        evidence_process is None,
        "exited watcher should be cleared",
    )

    _assert(
        evidence_restart_at == 40.0,
        "rapid evidence exit must use backoff",
    )

    original_popen = module.subprocess.Popen
    launches = []

    def fake_popen(
        command,
        cwd=None,
    ):
        launches.append(
            (list(command), cwd)
        )

        return _RunningProcess()

    module.subprocess.Popen = fake_popen

    try:
        (
            evidence_process,
            evidence_started_at,
            evidence_restart_at,
        ) = module._maintain_evidence_child(
            args=args,
            command=evidence_command,
            process=None,
            started_at=None,
            restart_at=40.0,
            now=39.0,
        )

        _assert(
            evidence_process is None,
            "watcher must not restart before deadline",
        )

        _assert(
            len(launches) == 0,
            "watcher restarted too early",
        )

        (
            evidence_process,
            evidence_started_at,
            evidence_restart_at,
        ) = module._maintain_evidence_child(
            args=args,
            command=evidence_command,
            process=None,
            started_at=None,
            restart_at=40.0,
            now=40.0,
        )

        _assert(
            evidence_process is not None,
            "watcher must restart at deadline",
        )

        _assert(
            len(launches) == 1,
            "watcher restart count mismatch",
        )

    finally:
        module.subprocess.Popen = (
            original_popen
        )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(SUPERVISOR_PATH),
            str(EVIDENCE_WATCHER_PATH),
        ],
        cwd=ROOT,
        check=True,
    )

    print(
        "[PASS] Phase 5C/5G Rithmic supervisor: "
        "existing finite Phase 5C worker model, "
        "mandatory DOM, independently restartable "
        "Phase 5G evidence watcher, environment/CLI "
        "plumbing, fail-open evidence lifecycle, "
        "and zero MT5 execution coupling verified."
    )


if __name__ == "__main__":
    main()
'''

    SUPERVISOR_TEST.write_text(
        test_source,
        encoding="utf-8",
        newline="\n",
    )

    # ------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------

    compile_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(SUPERVISOR),
            str(SUPERVISOR_TEST),
            str(WATCHER),
            str(WATCHER_TEST),
        ],
        cwd=ROOT,
    )

    if compile_result.returncode != 0:
        raise RuntimeError(
            "compile validation failed"
        )

    supervisor_test_result = subprocess.run(
        [
            sys.executable,
            str(SUPERVISOR_TEST),
        ],
        cwd=ROOT,
    )

    if supervisor_test_result.returncode != 0:
        raise RuntimeError(
            "dual supervisor regression failed"
        )

    watcher_test_result = subprocess.run(
        [
            sys.executable,
            str(WATCHER_TEST),
        ],
        cwd=ROOT,
    )

    if watcher_test_result.returncode != 0:
        raise RuntimeError(
            "evidence watcher regression failed"
        )

    diff_check = subprocess.run(
        [
            "git",
            "diff",
            "--check",
            "--",
            str(SUPERVISOR.relative_to(ROOT)),
            str(SUPERVISOR_TEST.relative_to(ROOT)),
        ],
        cwd=ROOT,
    )

    if diff_check.returncode != 0:
        raise RuntimeError(
            "git diff --check failed"
        )

except Exception:
    shutil.copy2(
        BACKUP / SUPERVISOR.name,
        SUPERVISOR,
    )

    shutil.copy2(
        BACKUP / SUPERVISOR_TEST.name,
        SUPERVISOR_TEST,
    )

    print(
        "[ROLLBACK] Phase 2 supervisor changes reverted."
    )

    raise

print("")
print("[PASS] Rithmic dual-supervisor Phase 2 applied")
print("[BACKUP]", BACKUP.relative_to(ROOT))
print("[CHANGED]", SUPERVISOR.relative_to(ROOT))
print("[CHANGED]", SUPERVISOR_TEST.relative_to(ROOT))
print("[UNCHANGED] src/live_bot.py")
print("[UNCHANGED] Phase 5C market-data worker")
print("[UNCHANGED] Rithmic evidence engines")
print("[SAFETY] Phase 5G watcher failures cannot stop Phase 5C")
print("[SAFETY] No MT5 execution authority added")
