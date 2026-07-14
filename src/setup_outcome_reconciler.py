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


def _merge_final_outcome(existing_outcome, new_outcome):
    """
    Merge setup-level outcomes safely.

    A setup may have MAIN + EXTRA positions. If MAIN wins and extras close
    at breakeven, the setup-level outcome must remain TP_TOUCH.

    Decisive outcomes should not be downgraded by BREAKEVEN.
    """

    existing = str(existing_outcome or "").strip().upper()
    new = str(new_outcome or "").strip().upper()

    if not existing:
        return new_outcome

    if existing in ["TP_TOUCH", "SL_TOUCH"] and new == "BREAKEVEN":
        return existing

    if existing in ["TP_TOUCH", "SL_TOUCH"] and not new:
        return existing

    if existing in ["W10", "EXPIRED", "TRACKING", "PENDING", "NONE", "NULL"]:
        return new_outcome

    if new in ["TP_TOUCH", "SL_TOUCH"]:
        return new_outcome

    return new_outcome or existing_outcome


def _apply_reconciled_fields(existing, fields):
    """
    Apply reconciled trade fields without letting BREAKEVEN overwrite
    a decisive setup-level TP_TOUCH / SL_TOUCH result.

    Important:
    final_outcome must be merged from the previous value BEFORE any
    field-copy loop overwrites it.
    """

    previous_final_outcome = existing.get("final_outcome")

    for field_key, value in fields.items():
        if field_key == "final_outcome":
            continue

        if value is not None:
            existing[field_key] = value

    existing["status"] = "CLOSED"
    existing["final_outcome"] = _merge_final_outcome(
        previous_final_outcome,
        fields.get("final_outcome"),
    )

    return existing


def _container_kind(payload):
    if isinstance(payload, list):
        return "list"

    if isinstance(payload, dict):
        # Native project format:
        # {
        #   "SETUP-ID": {...},
        #   "OTHER-SETUP-ID": {...}
        # }
        if all(isinstance(value, dict) for value in payload.values()):
            return "dict_by_setup_id"

        # Alternate wrapped-list formats, kept for compatibility.
        for key in ["setup_outcomes", "outcomes", "rows", "setups", "data"]:
            value = payload.get(key)

            if isinstance(value, list):
                return f"wrapped_list:{key}"

    return "unsupported"


def _find_latest_list_row_index(rows, setup_id):
    candidates = set(_setup_id_candidates(setup_id))

    latest_index = None

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        row_setup_id = str(row.get("setup_id") or "").strip()

        if row_setup_id in candidates:
            latest_index = index

    return latest_index


def _find_dict_key(payload, setup_id):
    candidates = _setup_id_candidates(setup_id)

    for candidate in candidates:
        if candidate in payload and isinstance(payload.get(candidate), dict):
            return candidate

    return None


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


def reconcile_setup_outcome_from_closed_trade(trade, setup_outcomes_file=None):
    """
    Reconcile setup_outcomes.json from a clean CLOSED trade.

    Runtime use:
        setup_outcomes_file=None -> account-context path.

    Script/backfill use:
        pass explicit setup_outcomes_file to avoid unknown_account fallback.

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

        path = Path(setup_outcomes_file) if setup_outcomes_file else get_setup_outcomes_file()
        payload = _read_json(path, default={})

        kind = _container_kind(payload)
        fields = _build_reconciled_fields(trade)

        if kind == "dict_by_setup_id":
            key = _find_dict_key(payload, trade.get("setup_id"))

            if key is None:
                new_row = _build_minimal_row(trade)
                reconciled_setup_id = new_row.get("setup_id")
                payload[reconciled_setup_id] = new_row
                action = "APPENDED_MISSING_SETUP_OUTCOME"
            else:
                existing = payload[key]

                _apply_reconciled_fields(existing, fields)
                reconciled_setup_id = existing.get("setup_id") or key
                action = "UPDATED_EXISTING_SETUP_OUTCOME"

            output_payload = payload

        elif kind == "list":
            rows = payload
            row_index = _find_latest_list_row_index(rows, trade.get("setup_id"))

            if row_index is None:
                new_row = _build_minimal_row(trade)
                rows.append(new_row)
                action = "APPENDED_MISSING_SETUP_OUTCOME"
                reconciled_setup_id = new_row.get("setup_id")
            else:
                existing = rows[row_index]

                _apply_reconciled_fields(existing, fields)
                action = "UPDATED_EXISTING_SETUP_OUTCOME"
                reconciled_setup_id = existing.get("setup_id")

            output_payload = rows

        elif kind.startswith("wrapped_list:"):
            container_key = kind.split(":", 1)[1]
            rows = payload[container_key]
            row_index = _find_latest_list_row_index(rows, trade.get("setup_id"))

            if row_index is None:
                new_row = _build_minimal_row(trade)
                rows.append(new_row)
                action = "APPENDED_MISSING_SETUP_OUTCOME"
                reconciled_setup_id = new_row.get("setup_id")
            else:
                existing = rows[row_index]

                _apply_reconciled_fields(existing, fields)
                action = "UPDATED_EXISTING_SETUP_OUTCOME"
                reconciled_setup_id = existing.get("setup_id")

            output_payload = payload
            output_payload[container_key] = rows

        else:
            logger.warning(
                f"[SETUP OUTCOME RECONCILER] unsupported setup_outcomes structure: {type(payload).__name__}"
            )
            return {
                "ok": False,
                "action": "SKIPPED",
                "reason": "unsupported_setup_outcomes_structure",
            }

        _write_json(path, output_payload)

        logger.info(
            f"[SETUP OUTCOME RECONCILER] {action} | "
            f"trade_setup_id={trade.get('setup_id')} | "
            f"reconciled_setup_id={reconciled_setup_id} | "
            f"final_outcome={fields.get('final_outcome')} | "
            f"path={path}"
        )

        return {
            "ok": True,
            "action": action,
            "setup_id": reconciled_setup_id,
            "trade_setup_id": trade.get("setup_id"),
            "final_outcome": (
                (payload.get(reconciled_setup_id) or {}).get("final_outcome")
                if isinstance(payload, dict)
                else fields.get("final_outcome")
            ),
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
