import json
from datetime import datetime, timedelta

from config.settings import (
    ENABLE_EXECUTION_BLOCK_MEMORY,
    EXECUTION_BLOCK_MEMORY_EXPIRY_MINUTES,
    EXECUTION_BLOCK_MEMORY_REASONS,
)
from src.account_context import get_account_file
from src.logger import logger


def get_execution_block_file():
    return get_account_file("execution_block_memory.json")


def load_execution_blocks():
    file_path = get_execution_block_file()

    if not file_path.exists() or file_path.stat().st_size == 0:
        return {}

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[EXECUTION BLOCK MEMORY] Failed to load file: {e}")
        return {}


def save_execution_blocks(blocks):
    file_path = get_execution_block_file()
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(blocks, f, indent=2, ensure_ascii=False)

        temp_path.replace(file_path)
    except Exception as e:
        logger.error(f"[EXECUTION BLOCK MEMORY] Failed to save file: {e}")


def cleanup_expired_blocks(blocks):
    now = datetime.now()
    changed = False

    for setup_id, block in list(blocks.items()):
        try:
            expires_at = datetime.fromisoformat(block["expires_at"])
        except Exception:
            continue

        if now > expires_at:
            blocks.pop(setup_id, None)
            changed = True

    return changed


def remember_blocked_setup(
    *,
    setup_id,
    strategy,
    signal,
    reason,
    symbol=None,
    expected_price=None,
    current_price=None,
    slippage=None,
    max_allowed=None,
):
    if not ENABLE_EXECUTION_BLOCK_MEMORY:
        return False

    if reason not in EXECUTION_BLOCK_MEMORY_REASONS:
        return False

    if not setup_id:
        logger.warning(
            f"[EXECUTION BLOCK MEMORY] Cannot remember blocked setup without setup_id | "
            f"strategy={strategy} signal={signal} reason={reason}"
        )
        return False

    blocks = load_execution_blocks()
    changed = cleanup_expired_blocks(blocks)

    expires_at = datetime.now() + timedelta(
        minutes=EXECUTION_BLOCK_MEMORY_EXPIRY_MINUTES
    )

    blocks[str(setup_id)] = {
        "setup_id": str(setup_id),
        "symbol": symbol,
        "strategy": strategy,
        "signal": signal,
        "reason": reason,
        "expected_price": expected_price,
        "current_price": current_price,
        "slippage": slippage,
        "max_allowed": max_allowed,
        "created_at": datetime.now().isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    save_execution_blocks(blocks)

    logger.warning(
        f"[EXECUTION BLOCK MEMORY] Setup remembered | "
        f"setup_id={setup_id} strategy={strategy} signal={signal} reason={reason}"
    )

    return True


def is_setup_execution_blocked(setup_id):
    if not ENABLE_EXECUTION_BLOCK_MEMORY:
        return False, None

    if not setup_id:
        return False, None

    blocks = load_execution_blocks()
    changed = cleanup_expired_blocks(blocks)

    block = blocks.get(str(setup_id))

    if changed:
        save_execution_blocks(blocks)

    if block is None:
        return False, None

    return True, block