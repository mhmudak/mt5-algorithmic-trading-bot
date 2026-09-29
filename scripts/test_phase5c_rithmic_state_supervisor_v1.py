from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR_PATH = ROOT / "scripts" / "run_phase5c_rithmic_state_supervisor.py"
WORKER_PATH = ROOT / "scripts" / "run_phase5c_rithmic_state_cache.py"


def _load_supervisor():
    spec = importlib.util.spec_from_file_location(
        "phase5c_rithmic_state_supervisor_test_target",
        SUPERVISOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load supervisor module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    _assert(SUPERVISOR_PATH.exists(), "supervisor script missing")
    _assert(WORKER_PATH.exists(), "Phase 5C worker missing")

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
            "--max-cycles",
            "1",
        ]
    )

    command = module.build_worker_command(args)

    _assert(command[0] == sys.executable, "supervisor must use current Python interpreter")
    _assert(
        str(WORKER_PATH) in command,
        "supervisor must launch the existing Phase 5C worker",
    )
    _assert("--include-order-book" in command, "DOM subscription must be mandatory")
    _assert(command[command.index("--symbol") + 1] == "GCZ6", "symbol plumbing mismatch")
    _assert(command[command.index("--exchange") + 1] == "COMEX", "exchange plumbing mismatch")
    _assert(
        command[command.index("--duration-seconds") + 1] == "120",
        "worker duration plumbing mismatch",
    )
    _assert(
        command[command.index("--snapshot-interval-seconds") + 1] == "2",
        "snapshot interval plumbing mismatch",
    )

    source = SUPERVISOR_PATH.read_text(encoding="utf-8")
    forbidden = [
        "src.live_bot",
        "import MetaTrader5",
        "order_send(",
        "place_order(",
        "execute_trade(",
    ]
    for marker in forbidden:
        _assert(marker not in source, f"forbidden execution coupling found: {marker}")

    for marker in (
        "decision_impact = NONE",
        "can_influence_decision = False",
        "execution_allowed = False",
        "never starts live_bot",
    ):
        _assert(marker in source, f"safety marker missing: {marker}")

    env_symbol = os.environ.get("RITHMIC_SYMBOL")
    os.environ["RITHMIC_SYMBOL"] = "GCZ6"
    try:
        env_args = module.parse_args([])
        _assert(env_args.symbol == "GCZ6", "RITHMIC_SYMBOL env default not honored")
    finally:
        if env_symbol is None:
            os.environ.pop("RITHMIC_SYMBOL", None)
        else:
            os.environ["RITHMIC_SYMBOL"] = env_symbol

    invalid = module.parse_args(
        ["--symbol", "GCZ6", "--worker-duration-seconds", "0"]
    )
    try:
        module.validate_args(invalid)
    except SystemExit as exc:
        _assert(
            "worker-duration-seconds must be > 0" in str(exc),
            "invalid-duration guard message mismatch",
        )
    else:
        raise AssertionError("zero worker duration must be rejected")

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(SUPERVISOR_PATH)],
        cwd=ROOT,
        check=True,
    )

    print(
        "[PASS] Phase 5C Rithmic supervisor: existing worker reuse, mandatory DOM, "
        "finite-child restart model, environment/CLI plumbing, validation, "
        "and zero MT5 execution coupling verified."
    )


if __name__ == "__main__":
    main()
