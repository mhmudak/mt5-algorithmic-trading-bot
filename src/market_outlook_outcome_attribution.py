
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


PHASE = "PHASE_6S9_OUTLOOK_OUTCOME_ATTRIBUTION_REPORT"


SETUP_ID_KEYS = (
    "setup_id",
    "candidate_setup_id",
    "source_setup_id",
    "executed_setup_id",
    "signal_id",
    "id",
)

STRATEGY_KEYS = (
    "strategy",
    "strategy_name",
    "setup_source",
    "setup_type",
)

SIGNAL_KEYS = (
    "signal",
    "direction",
    "side",
)

PROFIT_KEYS = (
    "realized_profit",
    "profit",
    "pnl",
    "net_profit",
    "net_pnl",
    "closed_profit",
    "pl",
)

STATUS_KEYS = (
    "status",
    "event",
    "outcome",
    "result",
    "close_reason",
)

TIME_KEYS = (
    "closed_at",
    "close_time",
    "exit_time",
    "updated_at",
    "timestamp",
    "created_at",
)


def _pick(record: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return default


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any, default: str = "UNKNOWN") -> str:
    if value is None:
        return default

    text = str(value).strip()
    if not text:
        return default

    return text


def _safe_upper(value: Any, default: str = "UNKNOWN") -> str:
    return _safe_str(value, default).upper()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []

    if not path.exists():
        return rows

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(row, dict):
            rows.append(row)

    return rows


def _looks_like_outcome_record(record: Dict[str, Any]) -> bool:
    keys = set(record.keys())

    return bool(
        keys.intersection(SETUP_ID_KEYS)
        or keys.intersection(PROFIT_KEYS)
        or keys.intersection(STATUS_KEYS)
    )


def _flatten_records(obj: Any, source_key: Optional[str] = None) -> List[Dict[str, Any]]:
    records = []

    if isinstance(obj, list):
        for item in obj:
            records.extend(_flatten_records(item))
        return records

    if isinstance(obj, dict):
        if _looks_like_outcome_record(obj):
            record = dict(obj)
            if source_key and "__source_key" not in record:
                record["__source_key"] = source_key
            records.append(record)
            return records

        for key, value in obj.items():
            records.extend(_flatten_records(value, source_key=str(key)))

    return records


def find_default_outcome_files(source_root: str | Path = "data") -> List[Path]:
    root = Path(source_root)

    if not root.exists():
        return []

    candidates = []

    patterns = [
        "data/accounts/**/trades.json",
        "data/accounts/**/setup_outcomes.json",
        "data/strategy_intelligence/**/setup_outcomes.json",
        "data/strategy_intelligence/**/trades.json",
    ]

    for pattern in patterns:
        candidates.extend(Path(".").glob(pattern))

    unique = []
    seen = set()

    for path in candidates:
        resolved = str(path.resolve())
        if resolved in seen:
            continue

        if path.exists() and path.is_file():
            seen.add(resolved)
            unique.append(path)

    return unique


def load_phase6s_execution_annotations(
    directory: str | Path = "data/reports/market_outlook/execution_annotations",
) -> List[Dict[str, Any]]:
    target = Path(directory)

    if not target.exists():
        return []

    rows = []

    for path in sorted(target.glob("*.jsonl")):
        for row in _read_jsonl(path):
            if row.get("phase") == "PHASE_6S8_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION":
                row = dict(row)
                row["_source_file"] = str(path)
                rows.append(row)

    return rows


def normalize_trade_outcome_record(record: Dict[str, Any]) -> Dict[str, Any]:
    setup_id = _pick(record, SETUP_ID_KEYS)

    if setup_id is None:
        source_key = record.get("__source_key")
        if source_key and source_key not in {"trades", "items", "records", "outcomes", "data"}:
            setup_id = source_key

    profit = _to_float(_pick(record, PROFIT_KEYS))
    status = _safe_upper(_pick(record, STATUS_KEYS, "UNKNOWN"))

    if profit is not None:
        if profit > 0:
            outcome_class = "WIN"
        elif profit < 0:
            outcome_class = "LOSS"
        else:
            outcome_class = "BREAKEVEN"
    elif "WIN" in status or "TP" in status or "PROFIT" in status:
        outcome_class = "WIN"
    elif "LOSS" in status or "SL" in status or "STOP" in status:
        outcome_class = "LOSS"
    else:
        outcome_class = "UNKNOWN"

    is_closed = profit is not None or any(
        token in status
        for token in ("CLOSED", "CLOSE", "TP", "SL", "STOP", "MANUAL", "WIN", "LOSS", "BREAKEVEN")
    )

    if "OPEN" in status:
        is_closed = False

    return {
        "setup_id": _safe_str(setup_id, ""),
        "strategy": _safe_str(_pick(record, STRATEGY_KEYS, "")),
        "signal": _safe_upper(_pick(record, SIGNAL_KEYS, "")),
        "profit": profit,
        "status": status,
        "outcome_class": outcome_class,
        "is_closed": is_closed,
        "closed_at": _pick(record, TIME_KEYS),
        "raw": record,
    }


def load_trade_outcomes(paths: Iterable[str | Path]) -> List[Dict[str, Any]]:
    outcomes = []

    for raw_path in paths:
        path = Path(raw_path)

        if not path.exists() or not path.is_file():
            continue

        try:
            data = _read_json(path)
        except Exception:
            continue

        for record in _flatten_records(data):
            normalized = normalize_trade_outcome_record(record)

            if normalized["setup_id"]:
                normalized["_source_file"] = str(path)
                outcomes.append(normalized)

    return outcomes


def _build_outcome_index(outcomes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index = {}

    for outcome in outcomes:
        setup_id = outcome.get("setup_id")
        if not setup_id:
            continue

        existing = index.get(setup_id)

        if existing is None:
            index[setup_id] = outcome
            continue

        existing_has_profit = existing.get("profit") is not None
        new_has_profit = outcome.get("profit") is not None

        if new_has_profit and not existing_has_profit:
            index[setup_id] = outcome

    return index


def _empty_summary() -> Dict[str, Any]:
    return {
        "count": 0,
        "matched_outcomes": 0,
        "unmatched": 0,
        "closed": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "unknown": 0,
        "net_profit": 0.0,
        "avg_profit": None,
        "win_rate_pct": None,
        "loss_rate_pct": None,
    }


def _update_summary(summary: Dict[str, Any], match: Optional[Dict[str, Any]]) -> None:
    summary["count"] += 1

    if not match:
        summary["unmatched"] += 1
        return

    summary["matched_outcomes"] += 1

    if match.get("is_closed"):
        summary["closed"] += 1

    outcome_class = match.get("outcome_class", "UNKNOWN")

    if outcome_class == "WIN":
        summary["wins"] += 1
    elif outcome_class == "LOSS":
        summary["losses"] += 1
    elif outcome_class == "BREAKEVEN":
        summary["breakeven"] += 1
    else:
        summary["unknown"] += 1

    profit = match.get("profit")

    if profit is not None:
        summary["net_profit"] = round(float(summary["net_profit"]) + float(profit), 2)


def _finalize_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    matched = summary["matched_outcomes"]

    if matched > 0:
        summary["avg_profit"] = round(summary["net_profit"] / matched, 2)

    resolved = summary["wins"] + summary["losses"] + summary["breakeven"]

    if resolved > 0:
        summary["win_rate_pct"] = round((summary["wins"] / resolved) * 100, 2)
        summary["loss_rate_pct"] = round((summary["losses"] / resolved) * 100, 2)

    summary["net_profit"] = round(float(summary["net_profit"]), 2)

    return summary


def build_phase6s_outcome_attribution_report(
    *,
    annotation_dir: str | Path = "data/reports/market_outlook/execution_annotations",
    outcome_paths: Optional[Iterable[str | Path]] = None,
    source_root: str | Path = "data",
    min_samples: int = 5,
) -> Dict[str, Any]:
    annotations = load_phase6s_execution_annotations(annotation_dir)

    if outcome_paths is None:
        outcome_paths = find_default_outcome_files(source_root)

    outcome_paths = list(outcome_paths)
    outcomes = load_trade_outcomes(outcome_paths)
    outcome_index = _build_outcome_index(outcomes)

    by_tag = defaultdict(_empty_summary)
    by_strategy = defaultdict(_empty_summary)
    by_strategy_tag = defaultdict(_empty_summary)

    matched_rows = []
    unmatched_rows = []

    for annotation in annotations:
        setup_id = _safe_str(annotation.get("setup_id"), "")
        tag = _safe_upper(annotation.get("tag"), "OUTLOOK_UNKNOWN")
        strategy = _safe_str(annotation.get("strategy"), "UNKNOWN")
        signal = _safe_upper(annotation.get("signal"), "UNKNOWN")

        match = outcome_index.get(setup_id) if setup_id else None

        _update_summary(by_tag[tag], match)
        _update_summary(by_strategy[strategy], match)
        _update_summary(by_strategy_tag[f"{strategy}|{tag}"], match)

        row = {
            "setup_id": setup_id,
            "tag": tag,
            "strategy": strategy,
            "signal": signal,
            "annotation_created_at_utc": annotation.get("created_at_utc"),
            "matched": bool(match),
            "outcome_class": match.get("outcome_class") if match else None,
            "profit": match.get("profit") if match else None,
            "status": match.get("status") if match else None,
            "closed_at": match.get("closed_at") if match else None,
            "annotation_source_file": annotation.get("_source_file"),
            "outcome_source_file": match.get("_source_file") if match else None,
        }

        if match:
            matched_rows.append(row)
        else:
            unmatched_rows.append(row)

    report = {
        "phase": PHASE,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision_impact": "REPORT_ONLY",
        "auto_trade_allowed": False,
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
        "min_samples": int(min_samples),
        "source": {
            "annotation_dir": str(annotation_dir),
            "outcome_paths": [str(path) for path in outcome_paths],
        },
        "counts": {
            "annotations": len(annotations),
            "outcome_records": len(outcomes),
            "matched": len(matched_rows),
            "unmatched": len(unmatched_rows),
        },
        "by_tag": {
            tag: _finalize_summary(summary)
            for tag, summary in sorted(by_tag.items())
        },
        "by_strategy": {
            strategy: _finalize_summary(summary)
            for strategy, summary in sorted(by_strategy.items())
        },
        "by_strategy_tag": {
            key: _finalize_summary(summary)
            for key, summary in sorted(by_strategy_tag.items())
        },
        "sample_warning": "Use only as evidence after enough matched closed trades exist.",
        "matched_rows": matched_rows,
        "unmatched_rows": unmatched_rows[:200],
    }

    return report


def write_phase6s_outcome_attribution_report(
    report: Dict[str, Any],
    *,
    output_dir: str | Path = "data/reports/market_outlook/outcome_attribution",
) -> Dict[str, str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = target / f"phase6s_outcome_attribution_{timestamp}.json"
    latest_json_path = target / "phase6s_outcome_attribution_latest.json"
    tag_csv_path = target / f"phase6s_outcome_attribution_by_tag_{timestamp}.csv"
    strategy_tag_csv_path = target / f"phase6s_outcome_attribution_by_strategy_tag_{timestamp}.csv"

    json_text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    json_path.write_text(json_text, encoding="utf-8")
    latest_json_path.write_text(json_text, encoding="utf-8")

    _write_summary_csv(tag_csv_path, report.get("by_tag", {}), key_name="tag")
    _write_summary_csv(strategy_tag_csv_path, report.get("by_strategy_tag", {}), key_name="strategy_tag")

    return {
        "json": str(json_path),
        "latest_json": str(latest_json_path),
        "by_tag_csv": str(tag_csv_path),
        "by_strategy_tag_csv": str(strategy_tag_csv_path),
    }


def _write_summary_csv(path: Path, summary_map: Dict[str, Dict[str, Any]], *, key_name: str) -> None:
    fieldnames = [
        key_name,
        "count",
        "matched_outcomes",
        "unmatched",
        "closed",
        "wins",
        "losses",
        "breakeven",
        "unknown",
        "net_profit",
        "avg_profit",
        "win_rate_pct",
        "loss_rate_pct",
    ]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for key, summary in sorted(summary_map.items()):
            row = {key_name: key}
            row.update(summary)
            writer.writerow(row)
