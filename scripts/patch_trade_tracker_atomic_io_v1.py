from pathlib import Path
from datetime import datetime
import os
import py_compile
import shutil
import sys
import tempfile

SOURCE = Path("src/trade_tracker.py")

old_import = """import json
import time
from datetime import datetime, timedelta
"""

new_import = """import json
import os
import time
from datetime import datetime, timedelta
"""

old_block = '''def load_trades():
    tracker_file = get_tracker_file()

    if not tracker_file.exists():
        return {}

    try:
        with open(tracker_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[TRACKER] Failed to load trades: {e}")
        return {}


def save_trades(trades):
    tracker_file = get_tracker_file()

    try:
        tracker_file.parent.mkdir(parents=True, exist_ok=True)
        with open(tracker_file, "w", encoding="utf-8") as f:
            json.dump(trades, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[TRACKER] Failed to save trades: {e}")
'''

new_block = '''def load_trades():
    tracker_file = get_tracker_file()

    if not tracker_file.exists():
        return {}

    try:
        with open(tracker_file, "r", encoding="utf-8") as f:
            trades = json.load(f)
    except Exception as e:
        logger.error(
            f"[TRACKER] Failed to load trades: {e} | "
            "refusing to continue with empty tracker state"
        )
        raise RuntimeError(
            f"Trade tracker load failed: {tracker_file}"
        ) from e

    if not isinstance(trades, dict):
        logger.error(
            "[TRACKER] Invalid tracker root type | "
            f"path={tracker_file} type={type(trades).__name__}"
        )
        raise RuntimeError(
            f"Trade tracker root must be a JSON object: {tracker_file}"
        )

    return trades


def save_trades(trades):
    tracker_file = get_tracker_file()

    if not isinstance(trades, dict):
        raise TypeError(
            "Trade tracker save refused: trades must be a dict"
        )

    tracker_file.parent.mkdir(parents=True, exist_ok=True)

    temp_file = tracker_file.with_name(
        f".{tracker_file.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )

    try:
        with open(temp_file, "w", encoding="utf-8", newline="\\n") as f:
            json.dump(
                trades,
                f,
                indent=2,
                ensure_ascii=False,
            )
            f.flush()
            os.fsync(f.fileno())

        # Validate the complete temporary payload before it can
        # replace the authoritative tracker file.
        with open(temp_file, "r", encoding="utf-8") as f:
            validated = json.load(f)

        if not isinstance(validated, dict):
            raise RuntimeError(
                "Temporary tracker payload is not a JSON object"
            )

        if len(validated) != len(trades):
            raise RuntimeError(
                "Temporary tracker validation count mismatch | "
                f"expected={len(trades)} actual={len(validated)}"
            )

        # Same-directory replace is atomic: readers see either
        # the old complete JSON or the new complete JSON.
        os.replace(temp_file, tracker_file)

    except Exception as e:
        logger.error(
            f"[TRACKER] Failed to save trades atomically: {e}"
        )

        try:
            if temp_file.exists():
                temp_file.unlink()
        except Exception:
            pass

        raise
'''

text = SOURCE.read_text(encoding="utf-8")

if text.count(old_import) != 1:
    print(
        f"[STOP] import anchor count={text.count(old_import)} expected=1"
    )
    sys.exit(1)

if text.count(old_block) != 1:
    print(
        f"[STOP] tracker I/O anchor count={text.count(old_block)} expected=1"
    )
    sys.exit(1)

patched = text.replace(old_import, new_import, 1)
patched = patched.replace(old_block, new_block, 1)

# Compile proposed source BEFORE touching the real source file.
try:
    compile(patched, str(SOURCE), "exec")
except Exception as exc:
    print(f"[STOP] proposed source does not compile: {exc}")
    sys.exit(1)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_dir = Path(
    "local_backups"
) / f"trade_tracker_atomic_io_{stamp}"

backup_dir.mkdir(parents=True, exist_ok=False)

backup = backup_dir / "trade_tracker.py"
shutil.copy2(SOURCE, backup)

fd, temp_name = tempfile.mkstemp(
    prefix="trade_tracker.",
    suffix=".tmp",
    dir=str(SOURCE.parent),
)

try:
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(patched)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp_name, SOURCE)

except Exception:
    try:
        os.unlink(temp_name)
    except Exception:
        pass
    raise

# Post-write compile verification.
py_compile.compile(
    str(SOURCE),
    doraise=True,
)

print("[OK] trade_tracker.py patched")
print(f"[OK] backup={backup}")
print("[OK] malformed tracker loads now fail closed")
print("[OK] tracker writes now use validated atomic replacement")
print("[OK] post-write compile passed")
