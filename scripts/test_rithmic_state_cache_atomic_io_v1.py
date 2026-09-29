from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.order_flow_features.rithmic_state_cache as state_module

from src.order_flow_features.rithmic_state_cache import (
    RithmicRollingStateCache,
    write_state_json,
    write_state_text,
)


def temp_artifacts(
    directory: Path,
    destination: Path,
) -> list[Path]:
    return list(
        directory.glob(
            f".{destination.name}.*.tmp"
        )
    )


def test_json_atomic_replacement() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        path = root / "state.json"

        path.write_text(
            '{"version":"old"}',
            encoding="utf-8",
        )

        payload = {
            "version": "new",
            "symbol": "GCZ6",
            "nested": {
                "values": list(range(100)),
            },
        }

        write_state_json(
            payload,
            path,
        )

        loaded = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )

        assert loaded == payload
        assert not temp_artifacts(
            root,
            path,
        )

    print(
        "PASS: JSON state replacement is "
        "complete and leaves no temp files"
    )


def test_text_writer_uses_atomic_path() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        path = root / "state.txt"

        cache = RithmicRollingStateCache(
            symbol="GCZ6",
            exchange="COMEX",
            tick_size=0.1,
            rolling_window_seconds=300,
            bucket_seconds=60,
            stale_after_seconds=15,
        )

        snapshot = cache.snapshot()

        write_state_text(
            snapshot,
            path,
        )

        rendered = path.read_text(
            encoding="utf-8",
        )

        assert "GCZ6" in rendered
        assert "COMEX" in rendered
        assert "decision_impact" in rendered
        assert not temp_artifacts(
            root,
            path,
        )

    print(
        "PASS: text state writer uses atomic "
        "replacement successfully"
    )


def test_replace_failure_preserves_old_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        path = root / "state.json"

        original = (
            '{"version":"known-good"}'
        )

        path.write_text(
            original,
            encoding="utf-8",
        )

        real_replace = (
            state_module.os.replace
        )

        def fail_replace(
            source,
            destination,
        ):
            raise OSError(
                "synthetic replace failure"
            )

        state_module.os.replace = (
            fail_replace
        )

        try:
            try:
                state_module._atomic_write_text(
                    path,
                    '{"version":"new"}',
                )

            except OSError as exc:
                assert (
                    "synthetic replace failure"
                    in str(exc)
                )

            else:
                raise AssertionError(
                    "expected replace failure"
                )

        finally:
            state_module.os.replace = (
                real_replace
            )

        # Critical property:
        # failed replacement never truncates the
        # already-good destination.
        assert (
            path.read_text(
                encoding="utf-8"
            )
            == original
        )

        assert not temp_artifacts(
            root,
            path,
        )

    print(
        "PASS: replacement failure preserves "
        "previous complete snapshot"
    )


def test_repeated_json_writes_are_parseable() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        path = root / "state.json"

        for i in range(200):
            payload = {
                "iteration": i,
                "symbol": "GCZ6",
                "values": list(
                    range(250)
                ),
            }

            write_state_json(
                payload,
                path,
            )

            observed = json.loads(
                path.read_text(
                    encoding="utf-8",
                )
            )

            assert (
                observed["iteration"]
                == i
            )

        assert not temp_artifacts(
            root,
            path,
        )

    print(
        "PASS: repeated state writes remain "
        "fully parseable"
    )


def test_source_contract() -> None:
    source = Path(
        state_module.__file__
    ).read_text(
        encoding="utf-8-sig",
    )

    assert (
        "tempfile.NamedTemporaryFile"
        in source
    )

    assert "os.fsync" in source
    assert "os.replace" in source

    # The two public writers must no longer
    # write directly to their destinations.
    json_start = source.index(
        "def write_state_json("
    )

    text_start = source.index(
        "def write_state_text("
    )

    assert (
        "Path(output_path).write_text"
        not in source[text_start:]
    )

    assert (
        "_atomic_write_text("
        in source[json_start:]
    )

    print(
        "PASS: writer source enforces temp + "
        "fsync + atomic replace contract"
    )


def main() -> None:
    test_json_atomic_replacement()
    test_text_writer_uses_atomic_path()
    test_replace_failure_preserves_old_file()
    test_repeated_json_writes_are_parseable()
    test_source_contract()

    print("")
    print(
        "[PASS] Rithmic state-cache atomic I/O "
        "hardening verified."
    )


if __name__ == "__main__":
    main()
