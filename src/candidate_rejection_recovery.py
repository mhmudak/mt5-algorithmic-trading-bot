import json
from datetime import datetime, timedelta

from config.settings import (
    ENABLE_CANDIDATE_REJECTION_RECOVERY,
    CANDIDATE_REJECTION_RECOVERY_EXPIRY_MINUTES,
    CANDIDATE_REJECTION_RECOVERY_MIN_SCORE,
    CANDIDATE_REJECTION_RECOVERY_REASONS,
    CANDIDATE_REJECTION_RECOVERY_STRATEGIES,
)
from src.account_context import get_account_file
from src.logger import logger


def get_recovery_file():
    return get_account_file("candidate_rejection_recovery.json")


def _json_safe(value):
    try:
        if hasattr(value, "item"):
            return value.item()
    except Exception:
        pass

    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_json_safe(v) for v in value]

    return value


def load_recovery_candidates():
    file_path = get_recovery_file()

    if not file_path.exists() or file_path.stat().st_size == 0:
        return {}

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[CANDIDATE RECOVERY] Failed to load file: {e}")
        return {}


def save_recovery_candidates(entries):
    file_path = get_recovery_file()
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(_json_safe(entries), f, indent=2, ensure_ascii=False)

        temp_path.replace(file_path)
    except Exception as e:
        logger.error(f"[CANDIDATE RECOVERY] Failed to save file: {e}")


def cleanup_expired_recovery_candidates(entries):
    now = datetime.now()
    changed = False

    for recovery_id, item in list(entries.items()):
        try:
            expires_at = datetime.fromisoformat(item["expires_at"])
        except Exception:
            item["status"] = "EXPIRED"
            changed = True
            continue

        if now > expires_at:
            item["status"] = "EXPIRED"
            changed = True

    return changed


def register_rejected_candidate_for_recovery(
    *,
    symbol,
    signal,
    strategy,
    score,
    reason_type,
    rejection_reason,
    signal_data,
    required_rr=None,
    current_rr=None,
):
    if not ENABLE_CANDIDATE_REJECTION_RECOVERY:
        return False

    strategy_key = str(strategy or "UNKNOWN").upper()
    reason_key = str(reason_type or "UNKNOWN").upper()

    if strategy_key not in CANDIDATE_REJECTION_RECOVERY_STRATEGIES:
        return False

    if reason_key not in CANDIDATE_REJECTION_RECOVERY_REASONS:
        return False

    try:
        score_value = float(score or 0)
    except Exception:
        score_value = 0

    if score_value < CANDIDATE_REJECTION_RECOVERY_MIN_SCORE:
        return False

    setup_id = str(
        signal_data.get(
            "setup_id",
            f"REC-{strategy_key}-{signal}-{datetime.now().timestamp()}",
        )
    )

    recovery_id = f"{setup_id}-{reason_key}"

    entries = load_recovery_candidates()
    cleanup_expired_recovery_candidates(entries)

    if recovery_id in entries and entries[recovery_id].get("status") == "WAITING_RECOVERY":
        return False

    expires_at = datetime.now() + timedelta(
        minutes=CANDIDATE_REJECTION_RECOVERY_EXPIRY_MINUTES
    )

    entries[recovery_id] = {
        "recovery_id": recovery_id,
        "setup_id": setup_id,
        "status": "WAITING_RECOVERY",
        "created_at": datetime.now().isoformat(),
        "expires_at": expires_at.isoformat(),
        "symbol": symbol,
        "strategy": strategy_key,
        "signal": signal,
        "score": score_value,
        "reason_type": reason_key,
        "rejection_reason": rejection_reason,
        "required_rr": required_rr,
        "current_rr": current_rr,
        "signal_data": _json_safe(signal_data),
    }

    save_recovery_candidates(entries)

    logger.info(
        f"[CANDIDATE RECOVERY] Registered | "
        f"id={recovery_id} strategy={strategy_key} signal={signal} "
        f"reason={reason_key} score={score_value}"
    )

    return True


def mark_recovery_candidate_executed(recovery_id):
    entries = load_recovery_candidates()

    if recovery_id not in entries:
        return

    entries[recovery_id]["status"] = "EXECUTED"
    entries[recovery_id]["executed_at"] = datetime.now().isoformat()

    save_recovery_candidates(entries)


def mark_recovery_candidate_failed(recovery_id, reason):
    entries = load_recovery_candidates()

    if recovery_id not in entries:
        return

    entries[recovery_id]["status"] = "EXECUTION_FAILED"
    entries[recovery_id]["failed_at"] = datetime.now().isoformat()
    entries[recovery_id]["failure_reason"] = reason

    save_recovery_candidates(entries)


def get_waiting_recovery_candidates(symbol):
    entries = load_recovery_candidates()
    changed = cleanup_expired_recovery_candidates(entries)

    waiting = []

    for recovery_id, item in entries.items():
        if item.get("symbol") != symbol:
            continue

        if item.get("status") != "WAITING_RECOVERY":
            continue

        waiting.append(item)

    if changed:
        save_recovery_candidates(entries)

    return sorted(
        waiting,
        key=lambda item: item.get("score", 0),
        reverse=True,
    )