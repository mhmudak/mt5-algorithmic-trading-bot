import csv
import json
import logging
import re
from datetime import datetime
from pathlib import Path


logger = logging.getLogger(__name__)


try:
    from src.account_context import get_account_file
except Exception:
    get_account_file = None


DEFAULT_OBSERVATIONS_FILENAME = "confirmation_observations.jsonl"
DEFAULT_OBSERVATIONS_CSV_FILENAME = "confirmation_observations.csv"

# Phase 2AH:
# Prevent duplicate confirmation observations from inflating shadow statistics.
# This affects observation logging only. It must never block trade execution.
CONFIRMATION_OBSERVATION_DUPLICATE_GUARD_ENABLED = True
CONFIRMATION_OBSERVATION_DUPLICATE_LOOKBACK_ROWS = 50


def _project_root():
    return Path(__file__).resolve().parents[1]


def get_confirmation_observations_file(filename=DEFAULT_OBSERVATIONS_FILENAME):
    """
    Resolve account-specific confirmation observation file.

    Preferred:
        data/accounts/<current_account>/confirmation_observations.jsonl

    Fallback:
        data/confirmation_observations.jsonl

    This module must never break live execution if account context is unavailable.
    """

    if get_account_file is not None:
        try:
            path = get_account_file(filename)
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        except Exception as exc:
            logger.warning(
                "[CONFIRMATION OBSERVATION] account-specific path unavailable: %s",
                exc,
            )

    fallback = _project_root() / "data" / filename
    fallback.parent.mkdir(parents=True, exist_ok=True)
    return fallback


def _module_key(value):
    value = str(value or "UNKNOWN").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")
    return value or "unknown"


def _json_safe(value):
    """
    Convert values to JSON-safe objects without importing heavy dependencies.
    Handles normal Python types, Path, datetime, numpy-like scalars, dict/list.
    """

    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {
            str(k): _json_safe(v)
            for k, v in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            _json_safe(item)
            for item in value
        ]

    # numpy / pandas scalar compatibility
    try:
        if hasattr(value, "item"):
            return _json_safe(value.item())
    except Exception:
        pass

    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)


def _csv_safe(value):
    value = _json_safe(value)

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    return value


def _safe_get(mapping, key, default=None):
    try:
        if mapping is None:
            return default
        return mapping.get(key, default)
    except Exception:
        return default


def _failed_module_names(items):
    return [
        item.get("module")
        for item in items or []
        if item and item.get("module")
    ]


def build_confirmation_observation_record(
    *,
    report,
    signal_data=None,
    trade_plan=None,
    setup_source_bucket=None,
    notes=None,
):
    """
    Build one flat + nested record for downstream analysis.

    The JSONL keeps nested module evidence.
    The flattened module_* fields make CSV/pandas analysis easier.
    """

    signal_data = signal_data or {}
    trade_plan = trade_plan or {}
    report = report or {}

    results = report.get("results", []) or []

    record = {
        "created_at": datetime.now().isoformat(),
        "record_type": "CONFIRMATION_ENGINE_OBSERVATION",
        "engine_version": report.get("engine_version"),
        "mode": report.get("mode"),
        "approved": report.get("approved"),
        "confidence": report.get("confidence"),
        "score_delta": report.get("score_delta"),

        # Phase 2M: persist shadow policy fields.
        # These are observe-only labels and must not affect execution.
        "shadow_decision": report.get("shadow_decision"),
        "shadow_score": report.get("shadow_score"),
        "shadow_action": report.get("shadow_action"),
        "shadow_reason": report.get("shadow_reason"),
        "shadow_policy_version": report.get("shadow_policy_version"),
        "shadow_blocking_allowed": report.get("shadow_blocking_allowed"),

        "summary": report.get("summary"),
        "enforce_required": report.get("enforce_required"),
        "strategy": report.get("strategy") or signal_data.get("strategy") or trade_plan.get("strategy"),
        "signal": report.get("signal") or signal_data.get("signal") or trade_plan.get("signal"),
        "entry_model": report.get("entry_model") or signal_data.get("entry_model") or trade_plan.get("entry_model"),
        "setup_id": report.get("setup_id") or signal_data.get("setup_id") or trade_plan.get("setup_id"),
        "setup_source_bucket": (
            setup_source_bucket
            or signal_data.get("setup_source_bucket")
            or signal_data.get("execution_bucket")
            or trade_plan.get("setup_source_bucket")
            or trade_plan.get("execution_bucket")
        ),
        "session": signal_data.get("session") or trade_plan.get("session"),
        "market_condition": signal_data.get("market_condition") or trade_plan.get("market_condition"),
        "score": signal_data.get("score") or trade_plan.get("score"),
        "entry": trade_plan.get("entry_price") or trade_plan.get("entry"),
        "sl": trade_plan.get("stop_loss") or trade_plan.get("sl"),
        "tp": trade_plan.get("take_profit") or trade_plan.get("tp"),
        "rr": trade_plan.get("rr") or trade_plan.get("risk_reward"),
        "disabled_layers": report.get("disabled_layers", []) or [],
        "required_failed_modules": _failed_module_names(report.get("required_failed", [])),
        "optional_failed_modules": _failed_module_names(report.get("optional_failed", [])),
        "module_count": len(results),
        "pass_count": sum(1 for item in results if item.get("status") == "PASS"),
        "fail_count": sum(1 for item in results if item.get("status") == "FAIL"),
        "neutral_count": sum(1 for item in results if item.get("status") == "NEUTRAL"),
        "disabled_count": sum(1 for item in results if item.get("status") == "DISABLED"),
        "error_count": sum(1 for item in results if item.get("status") == "ERROR"),
        "positive_module_count": sum(1 for item in results if float(item.get("score_delta") or 0) > 0),
        "negative_module_count": sum(1 for item in results if float(item.get("score_delta") or 0) < 0),
        "positive_modules": [
            item.get("module")
            for item in results
            if float(item.get("score_delta") or 0) > 0
        ],
        "negative_modules": [
            item.get("module")
            for item in results
            if float(item.get("score_delta") or 0) < 0
        ],
        "modules": results,
        "notes": notes,
    }

    for item in results:
        module = _module_key(item.get("module"))
        prefix = f"module_{module}"

        record[f"{prefix}_status"] = item.get("status")
        record[f"{prefix}_confidence"] = item.get("confidence")
        record[f"{prefix}_score_delta"] = item.get("score_delta")
        record[f"{prefix}_required"] = item.get("required")
        record[f"{prefix}_source_type"] = item.get("source_type")
        record[f"{prefix}_reason"] = item.get("reason")

        evidence = item.get("evidence") or {}

        # High-value evidence shortcuts for fast analysis.
        if module == "consolidation_policy_audit":
            record["consolidation_policy_family"] = evidence.get("policy_family")
            record["consolidation_mid_range"] = evidence.get("mid_range")
            record["consolidation_edge_location_confirms"] = evidence.get("edge_location_confirms")
            record["consolidation_sweep_confirms"] = evidence.get("sweep_confirms")
            record["consolidation_bos_confirms"] = evidence.get("bos_confirms")
            record["consolidation_volume_expansion"] = evidence.get("volume_expansion")
            record["consolidation_risk_flags"] = evidence.get("risk_flags")
            record["consolidation_support_flags"] = evidence.get("support_flags")

        elif module == "mt5_volume_proxy":
            record["mt5_volume_proxy_source"] = evidence.get("volume_col")
            record["mt5_relative_volume_ratio"] = evidence.get("relative_volume_ratio")
            record["mt5_volume_proxy_warning"] = evidence.get("proxy_warning")

        elif module == "price_action_structure":
            record["price_action_displacement"] = evidence.get("displacement")
            record["price_action_bos_bullish"] = evidence.get("bullish_bos")
            record["price_action_bos_bearish"] = evidence.get("bearish_bos")
            record["price_action_sweep_confirms_signal"] = evidence.get("sweep_confirms_signal")

        elif module == "entry_quality":
            record["entry_quality_rr"] = evidence.get("rr")
            record["entry_quality_spread"] = evidence.get("spread")

        elif module == "comex_order_flow":
            record["comex_order_flow_available"] = item.get("status") != "DISABLED"
            record["comex_order_flow_source_type"] = item.get("source_type")
            record["comex_order_flow_provider"] = evidence.get("provider")
            record["comex_order_flow_symbol"] = evidence.get("symbol")

    return _json_safe(record)


def _observation_duplicate_key(record):
    """
    Build a stable duplicate key for confirmation observation rows.

    The guard intentionally uses setup identity + shadow label, not created_at,
    because repeated observations of the exact same setup in the same live loop
    should not inflate post-shadow statistics.
    """

    record = record or {}

    return (
        str(record.get("setup_id") or "").strip(),
        str(record.get("strategy") or "").strip(),
        str(record.get("signal") or "").strip(),
        str(record.get("setup_source_bucket") or "").strip(),
        str(record.get("shadow_decision") or "").strip(),
    )


def _recent_confirmation_observation_keys(path, lookback_rows=None):
    path = Path(path)

    if not path.exists():
        return set()

    if lookback_rows is None:
        lookback_rows = CONFIRMATION_OBSERVATION_DUPLICATE_LOOKBACK_ROWS

    try:
        lookback_rows = int(lookback_rows)
    except Exception:
        lookback_rows = CONFIRMATION_OBSERVATION_DUPLICATE_LOOKBACK_ROWS

    if lookback_rows <= 0:
        lookback_rows = CONFIRMATION_OBSERVATION_DUPLICATE_LOOKBACK_ROWS

    try:
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-lookback_rows:]
    except Exception as exc:
        logger.warning(
            "[CONFIRMATION OBSERVATION] duplicate guard read failed: %s",
            exc,
        )
        return set()

    keys = set()

    for line in lines:
        line = line.strip()

        if not line:
            continue

        try:
            existing = json.loads(line)
        except Exception:
            continue

        key = _observation_duplicate_key(existing)

        if all(key):
            keys.add(key)

    return keys


def is_duplicate_confirmation_observation(record, file_path=None, lookback_rows=None):
    if not CONFIRMATION_OBSERVATION_DUPLICATE_GUARD_ENABLED:
        return False

    path = Path(file_path) if file_path else get_confirmation_observations_file()
    key = _observation_duplicate_key(record)

    if not all(key):
        return False

    recent_keys = _recent_confirmation_observation_keys(
        path,
        lookback_rows=lookback_rows,
    )

    return key in recent_keys


def append_jsonl_record(record, file_path=None):
    path = Path(file_path) if file_path else get_confirmation_observations_file()
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_json_safe(record), ensure_ascii=False, sort_keys=True))
        f.write("\n")

    return path


def log_confirmation_observation(
    *,
    report,
    signal_data=None,
    trade_plan=None,
    setup_source_bucket=None,
    notes=None,
    file_path=None,
):
    """
    Persist one confirmation observation.

    Must never raise to live_bot. If logging fails, execution continues.
    """

    try:
        record = build_confirmation_observation_record(
            report=report,
            signal_data=signal_data,
            trade_plan=trade_plan,
            setup_source_bucket=setup_source_bucket,
            notes=notes,
        )

        path = Path(file_path) if file_path else get_confirmation_observations_file()

        if is_duplicate_confirmation_observation(record, file_path=path):
            logger.info(
                "[CONFIRMATION OBSERVATION] duplicate skipped | "
                "setup_id=%s strategy=%s signal=%s shadow=%s path=%s",
                record.get("setup_id"),
                record.get("strategy"),
                record.get("signal"),
                record.get("shadow_decision"),
                path,
            )

            return path

        path = append_jsonl_record(record, file_path=path)

        logger.info(
            "[CONFIRMATION OBSERVATION] saved | setup_id=%s | path=%s",
            record.get("setup_id"),
            path,
        )

        return path

    except Exception as exc:
        logger.error("[CONFIRMATION OBSERVATION] save failed: %s", exc)
        return None


def read_confirmation_observations(source_file=None, limit=None):
    path = Path(source_file) if source_file else get_confirmation_observations_file()

    if not path.exists():
        return []

    records = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                records.append(json.loads(line))
            except Exception:
                continue

    if limit is not None:
        return records[-int(limit):]

    return records


def export_confirmation_observations_to_csv(
    *,
    source_file=None,
    output_file=None,
    limit=None,
):
    records = read_confirmation_observations(
        source_file=source_file,
        limit=limit,
    )

    source_path = Path(source_file) if source_file else get_confirmation_observations_file()

    if output_file is None:
        output_path = source_path.with_suffix(".csv")
    else:
        output_path = Path(output_file)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not records:
        with output_path.open("w", encoding="utf-8", newline="") as f:
            f.write("")
        return output_path

    headers = []

    for record in records:
        for key in record.keys():
            if key not in headers:
                headers.append(key)

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=headers,
            extrasaction="ignore",
        )
        writer.writeheader()

        for record in records:
            writer.writerow({
                key: _csv_safe(record.get(key))
                for key in headers
            })

    return output_path


if __name__ == "__main__":
    output = export_confirmation_observations_to_csv()
    print(f"[CONFIRMATION OBSERVATION] exported CSV: {output}")


__all__ = [
    "get_confirmation_observations_file",
    "build_confirmation_observation_record",
    "log_confirmation_observation",
    "is_duplicate_confirmation_observation",
    "read_confirmation_observations",
    "export_confirmation_observations_to_csv",
]
