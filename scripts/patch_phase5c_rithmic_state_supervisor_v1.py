from __future__ import annotations

import os
import py_compile
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


EXPECTED_BRANCH = "feature/better-entry-optimizer"
ROOT = Path(__file__).resolve().parents[1]

SUPERVISOR_PATH = ROOT / "scripts" / "run_phase5c_rithmic_state_supervisor.py"
TEST_PATH = ROOT / "scripts" / "test_phase5c_rithmic_state_supervisor_v1.py"
WORKER_PATH = ROOT / "scripts" / "run_phase5c_rithmic_state_cache.py"
PROTOCOL_PATH = ROOT / "src" / "order_flow_providers" / "rithmic_protocol.py"

SUPERVISOR_SOURCE = 'from __future__ import annotations\n\nimport argparse\nimport os\nimport subprocess\nimport sys\nimport time\nfrom pathlib import Path\nfrom typing import Sequence\n\n\nPROJECT_ROOT = Path(__file__).resolve().parents[1]\nWORKER_PATH = PROJECT_ROOT / "scripts" / "run_phase5c_rithmic_state_cache.py"\n\nDEFAULT_WORKER_DURATION_SECONDS = 86400\nDEFAULT_RESTART_DELAY_SECONDS = 5.0\nDEFAULT_RAPID_EXIT_THRESHOLD_SECONDS = 30.0\nDEFAULT_RAPID_EXIT_BACKOFF_SECONDS = 30.0\n\n\ndef parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:\n    parser = argparse.ArgumentParser(\n        description=(\n            "Continuously supervise the observe-only Phase 5C Rithmic state-cache "\n            "worker. This process has no MT5 execution authority."\n        )\n    )\n    parser.add_argument("--symbol", default=os.getenv("RITHMIC_SYMBOL") or None)\n    parser.add_argument("--exchange", default=os.getenv("RITHMIC_EXCHANGE") or "COMEX")\n    parser.add_argument(\n        "--worker-duration-seconds",\n        type=int,\n        default=DEFAULT_WORKER_DURATION_SECONDS,\n        help="Finite child-worker duration. Supervisor restarts after normal expiry.",\n    )\n    parser.add_argument("--rolling-window-seconds", type=int, default=300)\n    parser.add_argument("--bucket-seconds", type=int, default=60)\n    parser.add_argument("--stale-after-seconds", type=int, default=15)\n    parser.add_argument("--tick-size", type=float, default=0.1)\n    parser.add_argument("--snapshot-interval-seconds", type=int, default=2)\n    parser.add_argument(\n        "--restart-delay-seconds",\n        type=float,\n        default=DEFAULT_RESTART_DELAY_SECONDS,\n    )\n    parser.add_argument(\n        "--rapid-exit-threshold-seconds",\n        type=float,\n        default=DEFAULT_RAPID_EXIT_THRESHOLD_SECONDS,\n    )\n    parser.add_argument(\n        "--rapid-exit-backoff-seconds",\n        type=float,\n        default=DEFAULT_RAPID_EXIT_BACKOFF_SECONDS,\n    )\n    parser.add_argument(\n        "--max-cycles",\n        type=int,\n        default=0,\n        help="0 = unlimited supervisor cycles; positive values are useful for testing.",\n    )\n    parser.add_argument("--output-dir", default="data/order_flow/rithmic")\n    return parser.parse_args(argv)\n\n\ndef validate_args(args: argparse.Namespace) -> None:\n    if not args.symbol:\n        raise SystemExit(\n            "[STOP] RITHMIC_SYMBOL is not configured. "\n            "Pass --symbol explicitly or set RITHMIC_SYMBOL in .env."\n        )\n    if args.worker_duration_seconds <= 0:\n        raise SystemExit("[STOP] --worker-duration-seconds must be > 0.")\n    if args.rolling_window_seconds <= 0:\n        raise SystemExit("[STOP] --rolling-window-seconds must be > 0.")\n    if args.bucket_seconds <= 0:\n        raise SystemExit("[STOP] --bucket-seconds must be > 0.")\n    if args.stale_after_seconds <= 0:\n        raise SystemExit("[STOP] --stale-after-seconds must be > 0.")\n    if args.tick_size <= 0:\n        raise SystemExit("[STOP] --tick-size must be > 0.")\n    if args.snapshot_interval_seconds <= 0:\n        raise SystemExit("[STOP] --snapshot-interval-seconds must be > 0.")\n    if args.restart_delay_seconds < 0:\n        raise SystemExit("[STOP] --restart-delay-seconds must be >= 0.")\n    if args.rapid_exit_threshold_seconds < 0:\n        raise SystemExit("[STOP] --rapid-exit-threshold-seconds must be >= 0.")\n    if args.rapid_exit_backoff_seconds < 0:\n        raise SystemExit("[STOP] --rapid-exit-backoff-seconds must be >= 0.")\n    if args.max_cycles < 0:\n        raise SystemExit("[STOP] --max-cycles must be >= 0.")\n\n\ndef build_worker_command(args: argparse.Namespace) -> list[str]:\n    validate_args(args)\n    return [\n        sys.executable,\n        str(WORKER_PATH),\n        "--symbol",\n        str(args.symbol),\n        "--exchange",\n        str(args.exchange),\n        "--duration-seconds",\n        str(args.worker_duration_seconds),\n        "--rolling-window-seconds",\n        str(args.rolling_window_seconds),\n        "--bucket-seconds",\n        str(args.bucket_seconds),\n        "--stale-after-seconds",\n        str(args.stale_after_seconds),\n        "--tick-size",\n        str(args.tick_size),\n        "--snapshot-interval-seconds",\n        str(args.snapshot_interval_seconds),\n        "--include-order-book",\n        "--output-dir",\n        str(args.output_dir),\n    ]\n\n\ndef _stop_child_after_interrupt(process: subprocess.Popen) -> None:\n    if process.poll() is not None:\n        return\n\n    # Ctrl+C is normally delivered to both parent and child in the same console.\n    # Give the Phase 5C worker a short grace period to execute its own cleanup/finally.\n    try:\n        process.wait(timeout=5.0)\n        return\n    except subprocess.TimeoutExpired:\n        pass\n\n    try:\n        process.terminate()\n        process.wait(timeout=5.0)\n        return\n    except Exception:\n        pass\n\n    try:\n        process.kill()\n    except Exception:\n        pass\n\n\ndef run_supervisor(args: argparse.Namespace) -> int:\n    command = build_worker_command(args)\n    cycle = 0\n\n    print("[START] Phase 5C Rithmic state-cache supervisor")\n    print("symbol =", args.symbol)\n    print("exchange =", args.exchange)\n    print("worker_duration_seconds =", args.worker_duration_seconds)\n    print("snapshot_interval_seconds =", args.snapshot_interval_seconds)\n    print("include_order_book = True")\n    print("max_cycles =", args.max_cycles)\n    print("decision_impact = NONE")\n    print("can_influence_decision = False")\n    print("execution_allowed = False")\n    print("[SAFETY] Supervisor manages market-data lifecycle only; it never starts live_bot.")\n\n    while True:\n        cycle += 1\n        print("")\n        print(f"[SUPERVISOR] Starting Phase 5C worker cycle={cycle}")\n        started_at = time.monotonic()\n\n        process = subprocess.Popen(\n            command,\n            cwd=str(PROJECT_ROOT),\n        )\n\n        try:\n            return_code = process.wait()\n        except KeyboardInterrupt:\n            print("")\n            print("[SUPERVISOR] Stop requested by user.")\n            _stop_child_after_interrupt(process)\n            print("[STOPPED] Rithmic state-cache supervisor stopped.")\n            return 0\n\n        runtime_seconds = max(0.0, time.monotonic() - started_at)\n        print(\n            "[SUPERVISOR] Worker exited "\n            f"cycle={cycle} return_code={return_code} "\n            f"runtime_seconds={runtime_seconds:.1f}"\n        )\n\n        if args.max_cycles > 0 and cycle >= args.max_cycles:\n            print("[DONE] max_cycles reached; supervisor exiting.")\n            return int(return_code or 0)\n\n        rapid_exit = runtime_seconds < args.rapid_exit_threshold_seconds\n        delay = (\n            args.rapid_exit_backoff_seconds\n            if rapid_exit\n            else args.restart_delay_seconds\n        )\n        reason = "rapid_exit_backoff" if rapid_exit else "normal_restart_delay"\n\n        print(\n            "[SUPERVISOR] Restart scheduled "\n            f"in {delay:.1f}s reason={reason}"\n        )\n\n        try:\n            time.sleep(delay)\n        except KeyboardInterrupt:\n            print("")\n            print("[STOPPED] Rithmic state-cache supervisor stopped during restart delay.")\n            return 0\n\n\ndef main(argv: Sequence[str] | None = None) -> int:\n    args = parse_args(argv)\n    validate_args(args)\n\n    if not WORKER_PATH.exists():\n        raise SystemExit(\n            f"[STOP] Phase 5C worker not found: {WORKER_PATH}"\n        )\n\n    return run_supervisor(args)\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
TEST_SOURCE = 'from __future__ import annotations\n\nimport importlib.util\nimport os\nimport subprocess\nimport sys\nfrom pathlib import Path\nfrom types import SimpleNamespace\n\n\nROOT = Path(__file__).resolve().parents[1]\nSUPERVISOR_PATH = ROOT / "scripts" / "run_phase5c_rithmic_state_supervisor.py"\nWORKER_PATH = ROOT / "scripts" / "run_phase5c_rithmic_state_cache.py"\n\n\ndef _load_supervisor():\n    spec = importlib.util.spec_from_file_location(\n        "phase5c_rithmic_state_supervisor_test_target",\n        SUPERVISOR_PATH,\n    )\n    if spec is None or spec.loader is None:\n        raise AssertionError("cannot load supervisor module")\n    module = importlib.util.module_from_spec(spec)\n    spec.loader.exec_module(module)\n    return module\n\n\ndef _assert(condition: bool, message: str) -> None:\n    if not condition:\n        raise AssertionError(message)\n\n\ndef main() -> None:\n    _assert(SUPERVISOR_PATH.exists(), "supervisor script missing")\n    _assert(WORKER_PATH.exists(), "Phase 5C worker missing")\n\n    module = _load_supervisor()\n\n    args = module.parse_args(\n        [\n            "--symbol",\n            "GCZ6",\n            "--exchange",\n            "COMEX",\n            "--worker-duration-seconds",\n            "120",\n            "--rolling-window-seconds",\n            "300",\n            "--bucket-seconds",\n            "60",\n            "--stale-after-seconds",\n            "15",\n            "--tick-size",\n            "0.1",\n            "--snapshot-interval-seconds",\n            "2",\n            "--restart-delay-seconds",\n            "5",\n            "--rapid-exit-threshold-seconds",\n            "30",\n            "--rapid-exit-backoff-seconds",\n            "30",\n            "--max-cycles",\n            "1",\n        ]\n    )\n\n    command = module.build_worker_command(args)\n\n    _assert(command[0] == sys.executable, "supervisor must use current Python interpreter")\n    _assert(\n        str(WORKER_PATH) in command,\n        "supervisor must launch the existing Phase 5C worker",\n    )\n    _assert("--include-order-book" in command, "DOM subscription must be mandatory")\n    _assert(command[command.index("--symbol") + 1] == "GCZ6", "symbol plumbing mismatch")\n    _assert(command[command.index("--exchange") + 1] == "COMEX", "exchange plumbing mismatch")\n    _assert(\n        command[command.index("--duration-seconds") + 1] == "120",\n        "worker duration plumbing mismatch",\n    )\n    _assert(\n        command[command.index("--snapshot-interval-seconds") + 1] == "2",\n        "snapshot interval plumbing mismatch",\n    )\n\n    source = SUPERVISOR_PATH.read_text(encoding="utf-8")\n    forbidden = [\n        "src.live_bot",\n        "import MetaTrader5",\n        "order_send(",\n        "place_order(",\n        "execute_trade(",\n    ]\n    for marker in forbidden:\n        _assert(marker not in source, f"forbidden execution coupling found: {marker}")\n\n    for marker in (\n        "decision_impact = NONE",\n        "can_influence_decision = False",\n        "execution_allowed = False",\n        "never starts live_bot",\n    ):\n        _assert(marker in source, f"safety marker missing: {marker}")\n\n    env_symbol = os.environ.get("RITHMIC_SYMBOL")\n    os.environ["RITHMIC_SYMBOL"] = "GCZ6"\n    try:\n        env_args = module.parse_args([])\n        _assert(env_args.symbol == "GCZ6", "RITHMIC_SYMBOL env default not honored")\n    finally:\n        if env_symbol is None:\n            os.environ.pop("RITHMIC_SYMBOL", None)\n        else:\n            os.environ["RITHMIC_SYMBOL"] = env_symbol\n\n    invalid = module.parse_args(\n        ["--symbol", "GCZ6", "--worker-duration-seconds", "0"]\n    )\n    try:\n        module.validate_args(invalid)\n    except SystemExit as exc:\n        _assert(\n            "worker-duration-seconds must be > 0" in str(exc),\n            "invalid-duration guard message mismatch",\n        )\n    else:\n        raise AssertionError("zero worker duration must be rejected")\n\n    subprocess.run(\n        [sys.executable, "-m", "py_compile", str(SUPERVISOR_PATH)],\n        cwd=ROOT,\n        check=True,\n    )\n\n    print(\n        "[PASS] Phase 5C Rithmic supervisor: existing worker reuse, mandatory DOM, "\n        "finite-child restart model, environment/CLI plumbing, validation, "\n        "and zero MT5 execution coupling verified."\n    )\n\n\nif __name__ == "__main__":\n    main()\n'


def stop(message: str) -> None:
    raise SystemExit(f"[STOP] {message}")


def current_branch() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stop("Unable to determine Git branch.")
    return result.stdout.strip()


def require_anchor(path: Path, anchor: str, count: int = 1) -> None:
    if not path.exists():
        stop(f"Required file missing: {path.relative_to(ROOT)}")
    text = path.read_text(encoding="utf-8")
    actual = text.count(anchor)
    if actual != count:
        stop(
            f"Anchor mismatch in {path.relative_to(ROOT)}: "
            f"expected {count}, found {actual}: {anchor!r}"
        )


def compile_source(label: str, source: str) -> None:
    try:
        compile(source, label, "exec")
    except SyntaxError as exc:
        stop(f"In-memory compile failed for {label}: {exc}")


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def main() -> None:
    branch = current_branch()
    if branch != EXPECTED_BRANCH:
        stop(f"Wrong branch: {branch!r}; expected {EXPECTED_BRANCH!r}")
    print(f"[OK] Branch={branch}")

    require_anchor(
        WORKER_PATH,
        'async for event in client.stream(duration_seconds=args.duration_seconds, include_order_book=args.include_order_book):',
    )
    require_anchor(
        WORKER_PATH,
        'parser.add_argument("--include-order-book", action="store_true")',
    )
    require_anchor(
        PROTOCOL_PATH,
        "end_time = time.time() + duration_seconds",
    )
    require_anchor(
        PROTOCOL_PATH,
        'status="RECONNECT_EXHAUSTED"',
    )
    require_anchor(
        PROTOCOL_PATH,
        "finally:\n            await self.logout()",
    )
    print("[OK] Existing Phase 5C worker/reconnect lifecycle anchors validated")

    compile_source(str(SUPERVISOR_PATH.relative_to(ROOT)), SUPERVISOR_SOURCE)
    compile_source(str(TEST_PATH.relative_to(ROOT)), TEST_SOURCE)
    print("[OK] New supervisor/test sources compile in-memory")

    changed_existing = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = ROOT / "local_backups" / f"rithmic_phase5c_supervisor_v1_{timestamp}"

    for path, content in (
        (SUPERVISOR_PATH, SUPERVISOR_SOURCE),
        (TEST_PATH, TEST_SOURCE),
    ):
        existing = path.read_text(encoding="utf-8") if path.exists() else None
        if existing == content:
            print(f"[OK] Unchanged {path.relative_to(ROOT)}")
            continue

        if existing is not None:
            backup = backup_root / path.relative_to(ROOT)
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(existing, encoding="utf-8", newline="\n")
            changed_existing.append(path)
            print(f"[BACKUP] {backup}")

        atomic_write(path, content)
        print(
            f"[UPDATED] {path.relative_to(ROOT)}"
            if existing is not None
            else f"[CREATED] {path.relative_to(ROOT)}"
        )

    for path in (SUPERVISOR_PATH, TEST_PATH):
        py_compile.compile(str(path), doraise=True)

    print("[OK] Post-write py_compile passed")
    print("[DONE] Phase 5C Rithmic continuous supervisor V1 installed.")
    print("[SAFETY] Supervisor starts only the observe-only Phase 5C data worker.")
    print("[SAFETY] It never imports or starts live_bot and has no MT5 execution authority.")
    print("[NO BOT RESTART] Test the supervisor before starting live_bot.")
    print("[NO COMMIT] Review/test before staging or committing.")


if __name__ == "__main__":
    main()
