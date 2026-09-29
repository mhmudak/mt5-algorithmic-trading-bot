from pathlib import Path
import datetime
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_BRANCH = "feature/rithmic-setup-verdict-supervisor"
EXPECTED_HEAD = "1c08471"

SOURCE = (
    ROOT
    / "src"
    / "order_flow_features"
    / "rithmic_state_cache.py"
)

TEST = (
    ROOT
    / "scripts"
    / "test_rithmic_state_cache_atomic_io_v1.py"
)

FEED_TEST = (
    ROOT
    / "scripts"
    / "test_rithmic_feed_integrity_v1.py"
)

stamp = datetime.datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

backup_dir = (
    ROOT
    / "local_backups"
    / f"rithmic_state_cache_atomic_io_{stamp}"
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
        print(
            result.stderr,
            file=sys.stderr,
        )
        raise RuntimeError(
            f"command failed rc={result.returncode}: "
            f"{' '.join(args)}"
        )

    return result


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
        f"[STOP] branch mismatch: {branch}"
    )

if head != EXPECTED_HEAD:
    raise SystemExit(
        f"[STOP] HEAD mismatch: {head}"
    )

if not SOURCE.exists():
    raise SystemExit(
        "[STOP] rithmic_state_cache.py missing"
    )

if TEST.exists():
    raise SystemExit(
        "[STOP] atomic-I/O test already exists"
    )


# Writer module was clean in the audit.
dirty = subprocess.run(
    [
        "git",
        "diff",
        "--quiet",
        "--",
        str(SOURCE.relative_to(ROOT)),
    ],
    cwd=ROOT,
)

if dirty.returncode != 0:
    raise SystemExit(
        "[STOP] rithmic_state_cache.py is no "
        "longer clean; no changes made"
    )


cached = subprocess.run(
    [
        "git",
        "diff",
        "--cached",
        "--quiet",
        "--",
        str(SOURCE.relative_to(ROOT)),
    ],
    cwd=ROOT,
)

if cached.returncode != 0:
    raise SystemExit(
        "[STOP] staged state-cache changes detected"
    )


text = SOURCE.read_text(
    encoding="utf-8-sig",
)


# ============================================================
# IMPORTS
# ============================================================

if "import os\n" not in text:
    if text.count("import json\n") != 1:
        raise SystemExit(
            "[STOP] import-json anchor mismatch"
        )

    text = text.replace(
        "import json\n",
        "import json\nimport os\nimport tempfile\n",
        1,
    )

elif "import tempfile\n" not in text:
    if text.count("import os\n") != 1:
        raise SystemExit(
            "[STOP] import-os anchor mismatch"
        )

    text = text.replace(
        "import os\n",
        "import os\nimport tempfile\n",
        1,
    )


# ============================================================
# ATOMIC HELPER
# ============================================================

write_text_anchor = (
    "def write_state_text("
)

if text.count(write_text_anchor) != 1:
    raise SystemExit(
        "[STOP] write_state_text anchor mismatch"
    )


atomic_helper = '''def _atomic_write_text(
    output_path: str | Path,
    content: str,
) -> None:
    """
    Atomically replace a small state-cache text file.

    The temporary file is created in the destination directory so
    os.replace() stays on the same filesystem. Readers therefore see
    either the previous complete snapshot or the new complete snapshot,
    never a partially truncated destination file.
    """

    destination = Path(output_path)
    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\\n",
            dir=str(destination.parent),
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)

            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            temp_path,
            destination,
        )

        temp_path = None

    finally:
        if (
            temp_path is not None
            and temp_path.exists()
        ):
            try:
                temp_path.unlink()
            except OSError:
                pass


'''


text = text.replace(
    write_text_anchor,
    atomic_helper + write_text_anchor,
    1,
)


# ============================================================
# REPLACE DIRECT WRITES
# ============================================================

old_text_write = '''    Path(output_path).write_text("\\n".join(lines) + "\\n", encoding="utf-8")
'''

new_text_write = '''    _atomic_write_text(
        output_path,
        "\\n".join(lines) + "\\n",
    )
'''

if text.count(old_text_write) != 1:
    raise SystemExit(
        "[STOP] direct text-write anchor mismatch"
    )

text = text.replace(
    old_text_write,
    new_text_write,
    1,
)


old_json_write = '''    Path(output_path).write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
'''

new_json_write = '''    _atomic_write_text(
        output_path,
        json.dumps(
            snapshot,
            indent=2,
            ensure_ascii=False,
        ),
    )
'''

if text.count(old_json_write) != 1:
    raise SystemExit(
        "[STOP] direct JSON-write anchor mismatch"
    )

text = text.replace(
    old_json_write,
    new_json_write,
    1,
)


# ============================================================
# TEST
# ============================================================

test_source = r'''from __future__ import annotations

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
'''


# ============================================================
# BACKUP / APPLY / VERIFY
# ============================================================

backup_dir.mkdir(
    parents=True,
    exist_ok=False,
)

shutil.copy2(
    SOURCE,
    backup_dir / SOURCE.name,
)

try:
    SOURCE.write_text(
        text,
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
            str(SOURCE),
            str(TEST),
        ],
        cwd=ROOT,
    )

    if compile_result.returncode != 0:
        raise RuntimeError(
            "compile validation failed"
        )

    tests = [
        TEST,
    ]

    if FEED_TEST.exists():
        tests.append(
            FEED_TEST
        )

    for test in tests:
        print("")
        print("=" * 80)
        print(test.relative_to(ROOT))
        print("=" * 80)

        result = subprocess.run(
            [
                sys.executable,
                str(test),
            ],
            cwd=ROOT,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"regression failed: "
                f"{test.relative_to(ROOT)}"
            )

    diff_check = subprocess.run(
        [
            "git",
            "diff",
            "--check",
            "--",
            str(SOURCE.relative_to(ROOT)),
        ],
        cwd=ROOT,
    )

    if diff_check.returncode != 0:
        raise RuntimeError(
            "git diff --check failed"
        )

except Exception:
    shutil.copy2(
        backup_dir / SOURCE.name,
        SOURCE,
    )

    if TEST.exists():
        TEST.unlink()

    print("")
    print(
        "[ROLLBACK] Rithmic state-cache "
        "writer restored."
    )

    raise


print("")
print(
    "[PASS] Phase 5C state-cache atomic "
    "write hardening applied"
)

print(
    "[BACKUP]",
    backup_dir.relative_to(ROOT),
)

print(
    "[CHANGED]",
    SOURCE.relative_to(ROOT),
)

print(
    "[CREATED]",
    TEST.relative_to(ROOT),
)

print(
    "[SAFETY] destination is never truncated "
    "before replacement"
)

print(
    "[SAFETY] failed replacement preserves "
    "previous complete snapshot"
)

print(
    "[SAFETY] JSON and TXT use same atomic "
    "write primitive"
)

print(
    "[UNCHANGED] Rithmic evidence logic"
)

print(
    "[UNCHANGED] MT5 decision/execution authority"
)
