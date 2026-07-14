import json
from datetime import datetime
from pathlib import Path

from src.account_context import get_account_file
from src.logger import logger


SETUP_OUTCOME_RECONCILER_VERSION = "phase_2am_runtime_close_reconciler_v1"


def get_setup_outcomes_file():
    return get_account_file("setup_outcomes.json")


def _read_json(path, default):
    path = Path(path)

    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error("[SETUP OUTCOME RECONCILER] failed to read %s: %s", path, exc)
        return default


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _base_setup_id(setup_id):
    setup_id = str(setup_id or "").strip()

    for suffix in [
        "-MTFOVERRIDE",
        "-EXTRA",
        "-MAIN",
    ]:
        if setup_id.endswith(suffix):
            return setup_id[: -len(suffix)]

    return setup_id


def _setup_id_candidates(setup_id):
    raw = str(setup_id or "").strip()
    base = _base_setup_id(raw)

    candidates = []

    for item in [raw, base]:
        if item and item not in candidates:
            candidates.append(item)

    return candidates


def _final_outcome_from_trade(trade):
    close_reason = str(trade.get("close_reason") or "").upper()
    final_result = str(trade.get("final_result") or "").upper()

    try:
        realized_profit = float(trade.get("realized_profit") or 0.0)
    except Exception:
        realized_profit = 0.0

    if close_reason in ["TP", "TP_LIKELY"] or final_result == "WIN" or realized_profit > 0:
        return "TP_TOUCH"

    if close_reason in ["SL", "SL_LIKELY", "STOP_OUT"] or final_result == "LOSS" or realized_profit < 0:
        return "SL_TOUCH"

    if final_result == "BREAKEVEN" or close_reason == "BREAKEVEN" or realized_profit == 0:
        return "BREAKEVEN"

    return final_result or close_reason or "CLOSED"


def _find_list_container(payload):
    if isinstance(payload, list):
        return payload, None

    if isinstance(payload, dict):
        for key in ["setup_outcomes", "outcomes", "rows", "setups", "data"]:
            value = payload.get(key)

            if isinstance(value, list):
                return value, key

    return None, None


def _find_latest_row_index(rows, setup_id):
    candidates = set(_setup_id_candidates(setup_id))

    latest_index = None

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        row_setup_id = str(row.get("setup_id") or "").strip()

        if row_setup_id in candidates:
            latest_index = index

    return latest_index


def _build_reconciled_fields(trade):
    now = datetime.now().isoformat()
    setup_id = str(trade.get("setup_id") or "").strip()
    base_setup_id = _base_setup_id(setup_id)

    return {
        "setup_id": base_setup_id or setup_id,
        "strategy": trade.get("strategy"),
        "signal": trade.get("signal"),
        "entry_model": trade.get("entry_model"),
        "score": trade.get("setup_score"),
        "session": trade.get("session"),
        "market_condition": trade.get("market_condition"),
        "entry": trade.get("entry_price"),
        "sl": trade.get("stop_loss"),
        "tp": trade.get("take_profit"),
        "status": "CLOSED",
        "final_outcome": _final_outcome_from_trade(trade),
        "reason": trade.get("reason"),
        "updated_at": now,
        "reconciled_at": now,
        "reconciled_from_trade_tracker": True,
        "reconciler_version": SETUP_OUTCOME_RECONCILER_VERSION,
        "trade_setup_id": setup_id,
        "trade_position_id": trade.get("position_id"),
        "trade_main_position_id": trade.get("main_position_id"),
        "trade_role": trade.get("trade_role"),
        "trade_final_result": trade.get("final_result"),
        "trade_close_reason": trade.get("close_reason"),
        "trade_close_price": trade.get("close_price"),
        "trade_realized_profit": trade.get("realized_profit"),
        "trade_close_time": trade.get("close_time"),
    }


def _build_minimal_row(trade):
    row = _build_reconciled_fields(trade)

    row.setdefault("created_at", trade.get("open_time") or datetime.now().isoformat())
    row["source"] = "TRADE_TRACKER_RECONCILIATION"
    row["status_history_note"] = (
        "Minimal setup_outcomes row appended because no matching setup outcome "
        "row existed when the post-fix trade closed."
    )

    return row


def reconcile_setup_outcome_from_closed_trade(trade):
    """
    Reconcile setup_outcomes.json from a clean CLOSED trade.

    This function is intentionally best-effort and must never break live execution.
    """

    try:
        if not trade:
            return {
                "ok": False,
                "action": "SKIPPED",
                "reason": "missing_trade",
            }

        if trade.get("status") != "CLOSED":
            return {
                "ok": True,
                "action": "SKIPPED",
                "reason": "trade_not_closed",
            }

        required = ["final_result", "close_reason", "close_price", "realized_profit"]

        missing = [
            field
            for field in required
            if trade.get(field) in [None, ""]
        ]

        if missing:
            return {
                "ok": True,
                "action": "SKIPPED",
                "reason": "closed_trade_not_clean",
                "missing_fields": missing,
            }

        path = get_setup_outcomes_file()
        payload = _read_json(path, default=[])

        rows, container_key = _find_list_container(payload)

        if rows is None:
            logger.warning(
                "[SETUP OUTCOME RECONCILER] unsupported setup_outcomes structure: %s",
                type(payload).__name__,
            )
            return {
                "ok": False,
                "action": "SKIPPED",
                "reason": "unsupported_setup_outcomes_structure",
            }

        fields = _build_reconciled_fields(trade)
        row_index = _find_latest_row_index(rows, trade.get("setup_id"))

        if row_index is None:
            new_row = _build_minimal_row(trade)
            rows.append(new_row)
            action = "APPENDED_MISSING_SETUP_OUTCOME"
            reconciled_setup_id = new_row.get("setup_id")
        else:
            existing = rows[row_index]

            for key, value in fields.items():
                if value is not None:
                    existing[key] = value

            existing["status"] = "CLOSED"
            existing["final_outcome"] = fields["final_outcome"]
            action = "UPDATED_EXISTING_SETUP_OUTCOME"
            reconciled_setup_id = existing.get("setup_id")

        if isinstance(payload, list):
            output_payload = rows
        else:
            output_payload = payload
            output_payload[container_key] = rows

        _write_json(path, output_payload)

        logger.info(
            "[SETUP OUTCOME RECONCILER] %s | trade_setup_id=%s | reconciled_setup_id=%s | final_outcome=%s",
            action,
            trade.get("setup_id"),
            reconciled_setup_id,
            fields.get("final_outcome"),
        )

        return {
            "ok": True,
            "action": action,
            "setup_id": reconciled_setup_id,
            "trade_setup_id": trade.get("setup_id"),
            "final_outcome": fields.get("final_outcome"),
            "path": str(path),
        }

    except Exception as exc:
        logger.error("[SETUP OUTCOME RECONCILER] failed: %s", exc)
        return {
            "ok": False,
            "action": "ERROR",
            "reason": str(exc),
        }


__all__ = [
    "SETUP_OUTCOME_RECONCILER_VERSION",
    "reconcile_setup_outcome_from_closed_trade",
]
