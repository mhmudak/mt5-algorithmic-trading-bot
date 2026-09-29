from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
