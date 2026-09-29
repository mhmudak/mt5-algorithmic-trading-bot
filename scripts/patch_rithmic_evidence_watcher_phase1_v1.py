from pathlib import Path
import datetime
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_BRANCH = "feature/rithmic-setup-verdict-supervisor"
EXPECTED_HEAD = "1c08471"

BUILDER = ROOT / "scripts" / "build_phase5g_rithmic_monitoring_bridge.py"
WATCHER = ROOT / "scripts" / "run_phase5g_rithmic_evidence_watcher.py"
TEST = ROOT / "scripts" / "test_phase5g_rithmic_evidence_watcher_v1.py"

stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    ROOT
    / "local_backups"
    / f"rithmic_evidence_watcher_phase1_{stamp}"
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

if not BUILDER.exists():
    raise SystemExit(f"[STOP] missing builder: {BUILDER}")

require_clean_target(BUILDER)

if WATCHER.exists():
    raise SystemExit(
        f"[STOP] watcher already exists: {WATCHER}"
    )

if TEST.exists():
    raise SystemExit(
        f"[STOP] test already exists: {TEST}"
    )

BACKUP.mkdir(parents=True, exist_ok=False)
shutil.copy2(BUILDER, BACKUP / BUILDER.name)

watcher_source = r'''from __future__ import annotations

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
'''

test_source = r'''from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from scripts import run_phase5g_rithmic_evidence_watcher as watcher


def make_args(
    root: Path,
    *,
    max_builds: int = 1,
) -> argparse.Namespace:
    return argparse.Namespace(
        symbol="GCZ6",
        input_dir=str(root),
        output_dir=str(root),
        stale_after_seconds=15,
        tick_size=0.1,
        poll_interval_seconds=0.001,
        refresh_interval_seconds=0.001,
        signal=None,
        session="UNSPECIFIED",
        max_builds=max_builds,
        verbose_build_output=False,
    )


def seed_snapshot(root: Path) -> Path:
    path = (
        root
        / "GCZ6_phase5c_rithmic_state_latest.json"
    )

    path.write_text(
        '{"updated_at_epoch": 1.0}\n',
        encoding="utf-8",
    )

    return path


def test_argument_validation() -> None:
    args = make_args(Path("."))

    watcher.validate_args(args)

    args.refresh_interval_seconds = 0

    try:
        watcher.validate_args(args)
    except SystemExit:
        pass
    else:
        raise AssertionError(
            "zero refresh interval must fail validation"
        )


def test_bridge_argv_is_observe_only_context() -> None:
    args = make_args(Path("example"))

    argv = watcher.build_bridge_argv(args)

    assert "--symbol" in argv
    assert "GCZ6" in argv
    assert "--input-dir" in argv
    assert "--output-dir" in argv

    # No execution-side parameters belong here.
    joined = " ".join(argv).lower()

    assert "live_bot" not in joined
    assert "execute" not in joined
    assert "order_send" not in joined


def test_new_snapshot_builds_once() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        seed_snapshot(root)

        calls: list[list[str]] = []

        original = watcher.build_phase5g_bridge_main

        def fake_builder(argv):
            calls.append(list(argv))

        watcher.build_phase5g_bridge_main = fake_builder

        try:
            rc = watcher.run_watcher(
                make_args(root)
            )
        finally:
            watcher.build_phase5g_bridge_main = original

        assert rc == 0
        assert len(calls) == 1
        assert "GCZ6" in calls[0]


def test_builder_failure_is_fail_open_and_retries() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        seed_snapshot(root)

        attempts = {"count": 0}

        original = watcher.build_phase5g_bridge_main

        def flaky_builder(argv):
            attempts["count"] += 1

            if attempts["count"] == 1:
                raise RuntimeError(
                    "synthetic bridge failure"
                )

        watcher.build_phase5g_bridge_main = flaky_builder

        try:
            rc = watcher.run_watcher(
                make_args(root)
            )
        finally:
            watcher.build_phase5g_bridge_main = original

        assert rc == 0
        assert attempts["count"] == 2


def test_source_has_no_mt5_execution_coupling() -> None:
    source = Path(
        watcher.__file__
    ).read_text(
        encoding="utf-8-sig"
    )

    forbidden = (
        "import MetaTrader5",
        "from src.live_bot",
        "order_send(",
        "execute_trade(",
    )

    for token in forbidden:
        assert token not in source


def main() -> None:
    test_argument_validation()
    print("PASS: watcher argument validation")

    test_bridge_argv_is_observe_only_context()
    print("PASS: bridge invocation is context-only")

    test_new_snapshot_builds_once()
    print("PASS: new Phase 5C snapshot triggers one evidence build")

    test_builder_failure_is_fail_open_and_retries()
    print("PASS: evidence build failure is fail-open and retried")

    test_source_has_no_mt5_execution_coupling()
    print("PASS: watcher has zero MT5 execution coupling")


if __name__ == "__main__":
    main()
'''

original_builder = BUILDER.read_text(
    encoding="utf-8-sig"
)

try:
    builder_text = original_builder

    old = "from pathlib import Path\n"
    new = (
        "from pathlib import Path\n"
        "from typing import Sequence\n"
    )

    if old not in builder_text:
        raise RuntimeError(
            "builder pathlib import anchor not found"
        )

    builder_text = builder_text.replace(
        old,
        new,
        1,
    )

    old = "def main() -> None:\n"
    new = (
        "def main(\n"
        "    argv: Sequence[str] | None = None,\n"
        ") -> None:\n"
    )

    if old not in builder_text:
        raise RuntimeError(
            "builder main() anchor not found"
        )

    builder_text = builder_text.replace(
        old,
        new,
        1,
    )

    old = "    args = parser.parse_args()\n"
    new = "    args = parser.parse_args(argv)\n"

    if old not in builder_text:
        raise RuntimeError(
            "builder parse_args() anchor not found"
        )

    builder_text = builder_text.replace(
        old,
        new,
        1,
    )

    BUILDER.write_text(
        builder_text,
        encoding="utf-8",
        newline="\n",
    )

    WATCHER.write_text(
        watcher_source,
        encoding="utf-8",
        newline="\n",
    )

    TEST.write_text(
        test_source,
        encoding="utf-8",
        newline="\n",
    )

    compile_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(BUILDER),
            str(WATCHER),
            str(TEST),
        ],
        cwd=ROOT,
    )

    if compile_result.returncode != 0:
        raise RuntimeError(
            "compile validation failed"
        )

    test_result = subprocess.run(
        [
            sys.executable,
            str(TEST),
        ],
        cwd=ROOT,
    )

    if test_result.returncode != 0:
        raise RuntimeError(
            "focused watcher test failed"
        )

    diff_check = subprocess.run(
        [
            "git",
            "diff",
            "--check",
            "--",
            str(BUILDER.relative_to(ROOT)),
        ],
        cwd=ROOT,
    )

    if diff_check.returncode != 0:
        raise RuntimeError(
            "git diff --check failed"
        )

except Exception:
    shutil.copy2(
        BACKUP / BUILDER.name,
        BUILDER,
    )

    if WATCHER.exists():
        WATCHER.unlink()

    if TEST.exists():
        TEST.unlink()

    print(
        "[ROLLBACK] Phase 1 changes reverted."
    )

    raise

print("")
print("[PASS] Rithmic Evidence Watcher Phase 1 applied")
print("[BACKUP]", BACKUP.relative_to(ROOT))
print("[CHANGED]", BUILDER.relative_to(ROOT))
print("[CREATED]", WATCHER.relative_to(ROOT))
print("[CREATED]", TEST.relative_to(ROOT))
print("[SAFETY] No live_bot or execution source modified")
print("[SAFETY] Existing Rithmic supervisor not modified")
print("[SAFETY] Evidence failures remain fail-open")
