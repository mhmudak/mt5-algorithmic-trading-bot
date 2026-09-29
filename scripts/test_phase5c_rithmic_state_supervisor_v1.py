from __future__ import annotations

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
