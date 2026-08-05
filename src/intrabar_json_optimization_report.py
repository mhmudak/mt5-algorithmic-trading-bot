
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


PHASE = "PHASE_6U2_INTRABAR_JSON_OPTIMIZATION_REPORT"

KNOWN_BUCKETS = {
    "INTRABAR",
    "NORMAL_OR_TRACKED",
    "REJECTED_CANDIDATE_TRACKED",
    "MTF_CONFLICT_TRACKED",
}

DEFAULT_INTRABAR_TERMS = (
    "INTRABAR",
    "AUTO_STRUCTURAL_LEVEL_SCALP",
    "FAILED_FVG_REVERSAL",
    "MICRO_SR_SWEEP_RECLAIM",
    "RANGE_SWEEP_RECLAIM",
    "LIQUIDITY_SWEEP",
    "LIQUIDITY_TRAP",
    "VWAP_RECLAIM",
)


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _upper(value: Any) -> str:
    return _safe_str(value).upper()


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _normalize_strategy_name(value: Any) -> str:
    return _upper(value)


def _normalize_allowlist(values: Optional[Iterable[Any]]) -> Tuple[str, ...]:
    if not values:
        return tuple()

    normalized = []
    for value in values:
        name = _normalize_strategy_name(value)
        if name:
            normalized.append(name)

    return tuple(dict.fromkeys(normalized))


def _load_json(path: str | Path) -> Any:
    target = Path(path)
    if not target.exists():
        return None

    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return None


def _flatten_dicts(obj: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    if isinstance(obj, dict):
        rows.append(obj)

        for value in obj.values():
            if isinstance(value, (dict, list)):
                rows.extend(_flatten_dicts(value))

    elif isinstance(obj, list):
        for item in obj:
            rows.extend(_flatten_dicts(item))

    return rows


def _pick(row: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        value = row.get(key)

        if value in (None, ""):
            continue

        # This report only normalizes scalar strategy/stat rows.
        # Container/list fields must not become fake policy keys or strategy names.
        if isinstance(value, (dict, list, tuple, set)):
            continue

        return value

    return default


def _is_valid_strategy_name(value: Any) -> bool:
    text = _normalize_strategy_name(value)

    if not text:
        return False

    if text in {"UNKNOWN", "INTRABAR"}:
        return False

    if len(text) > 80:
        return False

    if any(char in text for char in "[]{}:,'"):
        return False

    return all(char.isalnum() or char == "_" for char in text)


def _is_strategy_specific_policy_key(value: Any) -> bool:
    text = _safe_str(value).upper()

    if not text:
        return False

    if text in {"UNKNOWN", "INTRABAR"}:
        return False

    if len(text) > 180:
        return False

    if any(char in text for char in "[]{}"):
        return False

    return True

def parse_policy_key(policy_key: Any) -> Dict[str, Any]:
    text = _safe_str(policy_key)
    parts = [part.strip() for part in text.split("|") if part.strip()]

    parsed = {
        "policy_key": text,
        "strategy": _upper(parts[0]) if len(parts) >= 1 else "",
        "direction": _upper(parts[1]) if len(parts) >= 2 else "",
        "setup_type": _upper(parts[2]) if len(parts) >= 3 else "",
        "session": _upper(parts[3]) if len(parts) >= 4 else "",
        "regime_or_profile": _upper(parts[4]) if len(parts) >= 5 else "",
        "source_bucket": "",
    }

    if parts:
        last = _upper(parts[-1])
        if last in KNOWN_BUCKETS:
            parsed["source_bucket"] = last

    if not parsed["source_bucket"] and "INTRABAR" in text.upper():
        parsed["source_bucket"] = "INTRABAR"

    return parsed


def row_looks_intrabar(row: Dict[str, Any], intrabar_terms: Iterable[str] = DEFAULT_INTRABAR_TERMS) -> bool:
    text = json.dumps(row, ensure_ascii=False, default=str).upper()
    return any(term.upper() in text for term in intrabar_terms)


def normalize_performance_row(row: Dict[str, Any], *, source_name: str) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None

    policy_key = _pick(row, ("policy_key", "key", "name"))
    parsed = parse_policy_key(policy_key)

    strategy = _upper(
        _pick(
            row,
            ("strategy", "strategy_name", "setup_source", "setup_type"),
            parsed.get("strategy"),
        )
    )

    if not strategy:
        strategy = parsed.get("strategy", "")

    if not _is_valid_strategy_name(strategy):
        return None

    if policy_key and not _is_strategy_specific_policy_key(policy_key):
        return None

    normalized = {
        "source_name": source_name,
        "policy_key": _safe_str(policy_key),
        "strategy": strategy,
        "direction": _upper(_pick(row, ("direction", "signal", "side"), parsed.get("direction"))),
        "setup_type": _upper(_pick(row, ("pattern", "setup_name", "setup_type"), parsed.get("setup_type"))),
        "session": _upper(_pick(row, ("session", "session_name", "market_session"), parsed.get("session"))),
        "regime_or_profile": _upper(parsed.get("regime_or_profile")),
        "source_bucket": _upper(_pick(row, ("source_bucket", "setup_source_bucket", "bucket"), parsed.get("source_bucket"))),

        "sample_count": _to_int(_pick(row, ("sample_count", "count", "rows"))),
        "closed_count": _to_int(_pick(row, ("closed_count", "closed"))),
        "realized_count": _to_int(_pick(row, ("realized_count", "profit_records"))),
        "main_count": _to_int(_pick(row, ("main_count",))),
        "extra_count": _to_int(_pick(row, ("extra_count",))),

        "decision": _safe_str(_pick(row, ("decision", "recommendation", "policy_decision"))),
        "decision_reason": _safe_str(_pick(row, ("decision_reason", "reason"))),

        "synthetic_expectancy": _to_float(_pick(row, ("synthetic_expectancy", "expectancy"))),
        "actual_expectancy": _to_float(_pick(row, ("actual_expectancy",))),
        "realized_expectancy": _to_float(_pick(row, ("realized_expectancy",))),
        "total_profit": _to_float(_pick(row, ("total_profit", "net_profit", "profit_sum"))),
        "w10_rate": _to_float(_pick(row, ("w10_rate",))),
        "tp_rate": _to_float(_pick(row, ("tp_rate",))),
        "sl_rate": _to_float(_pick(row, ("sl_rate",))),
        "win_rate": _to_float(_pick(row, ("win_rate", "win_rate_pct"))),
        "loss_rate": _to_float(_pick(row, ("loss_rate", "loss_rate_pct"))),
        "breakeven_rate": _to_float(_pick(row, ("breakeven_rate",))),
    }

    if not row_looks_intrabar(normalized) and not row_looks_intrabar(row):
        return None

    return normalized


def extract_intrabar_performance_rows(
    *,
    strategy_performance_report_path: str | Path,
    setup_outcomes_path: str | Path,
) -> Dict[str, Any]:
    performance_report = _load_json(strategy_performance_report_path)
    setup_outcomes = _load_json(setup_outcomes_path)

    rows: List[Dict[str, Any]] = []

    for row in _flatten_dicts(performance_report):
        normalized = normalize_performance_row(row, source_name="strategy_performance_report")
        if normalized:
            rows.append(normalized)

    for row in _flatten_dicts(setup_outcomes):
        normalized = normalize_performance_row(row, source_name="setup_outcomes")
        if normalized:
            rows.append(normalized)

    # De-duplicate broad report rows by source/policy_key/metrics.
    seen = set()
    deduped = []

    for row in rows:
        key = (
            row.get("source_name"),
            row.get("policy_key"),
            row.get("strategy"),
            row.get("sample_count"),
            row.get("decision"),
            row.get("synthetic_expectancy"),
            row.get("w10_rate"),
            row.get("tp_rate"),
            row.get("sl_rate"),
        )

        if key in seen:
            continue

        seen.add(key)
        deduped.append(row)

    return {
        "performance_report_exists": Path(strategy_performance_report_path).exists(),
        "setup_outcomes_exists": Path(setup_outcomes_path).exists(),
        "rows": deduped,
    }


def build_recommendation_for_row(
    row: Dict[str, Any],
    *,
    allowed_strategies: Iterable[Any],
    block_others: bool = True,
) -> Dict[str, Any]:
    allowed = set(_normalize_allowlist(allowed_strategies))
    strategy = _normalize_strategy_name(row.get("strategy"))

    user_allowlisted = strategy in allowed
    sample_count = _to_int(row.get("sample_count"))
    realized_count = _to_int(row.get("realized_count"))
    decision_reason = _safe_str(row.get("decision_reason")).lower()

    reliability_warnings = []

    if realized_count == 0:
        reliability_warnings.append("realized_profit_not_reliable_yet")

    if "not reliable" in decision_reason or "diagnostic" in decision_reason:
        reliability_warnings.append("diagnostic_only_trade_tracker_warning")

    if sample_count < 5:
        reliability_warnings.append("low_sample_count")

    if user_allowlisted:
        action = "KEEP_EXECUTING_BY_USER_ALLOWLIST"
    elif block_others:
        action = "BLOCK_INTRABAR_DETECTION_AND_EXECUTION_BY_USER_RULE"
    else:
        action = "TRACK_ONLY_NOT_ALLOWLISTED"

    return {
        "strategy": strategy,
        "policy_key": row.get("policy_key"),
        "session": row.get("session"),
        "direction": row.get("direction"),
        "setup_type": row.get("setup_type"),
        "source_bucket": row.get("source_bucket"),
        "recommended_action": action,
        "user_allowlisted": user_allowlisted,
        "statistics_reliability": "DIAGNOSTIC" if reliability_warnings else "USABLE",
        "reliability_warnings": reliability_warnings,
        "sample_count": sample_count,
        "closed_count": _to_int(row.get("closed_count")),
        "realized_count": realized_count,
        "synthetic_expectancy": row.get("synthetic_expectancy"),
        "actual_expectancy": row.get("actual_expectancy"),
        "w10_rate": row.get("w10_rate"),
        "tp_rate": row.get("tp_rate"),
        "sl_rate": row.get("sl_rate"),
        "decision": row.get("decision"),
        "decision_reason": row.get("decision_reason"),
    }


def build_phase6u_intrabar_json_optimization_report(
    *,
    strategy_performance_report_path: str | Path = "data/strategy_intelligence/Tickmill-Demo_25323531/strategy_performance_report.json",
    setup_outcomes_path: str | Path = "data/accounts/Tickmill-Demo_25323531/setup_outcomes.json",
    allowed_strategies: Iterable[Any] = ("AUTO_STRUCTURAL_LEVEL_SCALP", "FAILED_FVG_REVERSAL"),
    block_others: bool = True,
) -> Dict[str, Any]:
    extracted = extract_intrabar_performance_rows(
        strategy_performance_report_path=strategy_performance_report_path,
        setup_outcomes_path=setup_outcomes_path,
    )

    rows = extracted["rows"]
    recommendations = [
        build_recommendation_for_row(
            row,
            allowed_strategies=allowed_strategies,
            block_others=block_others,
        )
        for row in rows
    ]

    action_counter = Counter(row["recommended_action"] for row in recommendations)
    strategy_counter = Counter(row["strategy"] for row in recommendations)

    keep_rows = [row for row in recommendations if row["recommended_action"] == "KEEP_EXECUTING_BY_USER_ALLOWLIST"]
    blocked_rows = [row for row in recommendations if row["recommended_action"] == "BLOCK_INTRABAR_DETECTION_AND_EXECUTION_BY_USER_RULE"]

    keep_rows.sort(key=lambda row: (-row["sample_count"], row["strategy"], row["session"]))
    blocked_rows.sort(key=lambda row: (-row["sample_count"], row["strategy"], row["session"]))

    return {
        "phase": PHASE,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),

        # Safety contract
        "decision_impact": "REPORT_ONLY",
        "auto_trade_allowed": False,
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
        "can_modify_detection": False,

        "input_files": {
            "strategy_performance_report_path": str(strategy_performance_report_path),
            "strategy_performance_report_exists": extracted["performance_report_exists"],
            "setup_outcomes_path": str(setup_outcomes_path),
            "setup_outcomes_exists": extracted["setup_outcomes_exists"],
        },
        "user_rule": {
            "allowed_strategies": list(_normalize_allowlist(allowed_strategies)),
            "block_others": bool(block_others),
        },
        "counts": {
            "intrabar_rows": len(rows),
            "recommendation_rows": len(recommendations),
            "keep_rows": len(keep_rows),
            "blocked_rows": len(blocked_rows),
        },
        "by_recommended_action": dict(action_counter.most_common()),
        "by_strategy": dict(strategy_counter.most_common()),
        "keep_executing": keep_rows[:50],
        "block_or_disable": blocked_rows[:100],
        "all_recommendations": recommendations,
        "warning": "This is an optimization report only. It does not change execution. Profit fields remain diagnostic if realized_count is zero.",
    }


def write_phase6u_intrabar_json_optimization_report(
    report: Dict[str, Any],
    *,
    output_dir: str | Path = "data/reports/intrabar_json_optimization",
) -> Dict[str, str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = target / f"phase6u_intrabar_json_optimization_{timestamp}.json"
    latest_json_path = target / "phase6u_intrabar_json_optimization_latest.json"
    txt_path = target / f"phase6u_intrabar_json_optimization_{timestamp}.txt"
    latest_txt_path = target / "phase6u_intrabar_json_optimization_latest.txt"

    json_text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    message = format_phase6u_intrabar_json_optimization_report(report)

    json_path.write_text(json_text, encoding="utf-8")
    latest_json_path.write_text(json_text, encoding="utf-8")
    txt_path.write_text(message, encoding="utf-8")
    latest_txt_path.write_text(message, encoding="utf-8")

    return {
        "json": str(json_path),
        "latest_json": str(latest_json_path),
        "text": str(txt_path),
        "latest_text": str(latest_txt_path),
    }


def format_phase6u_intrabar_json_optimization_report(report: Dict[str, Any]) -> str:
    lines = [
        "⚡ Phase 6U Intrabar JSON Optimization Report",
        "",
        "Mode: REPORT ONLY",
        "Can execute: False",
        "Can block trade: False",
        "Can modify risk: False",
        "Can modify detection: False",
        "",
        "User rule:",
    ]

    user_rule = report.get("user_rule", {})
    for strategy in user_rule.get("allowed_strategies", []):
        lines.append(f"- KEEP: {strategy}")

    lines.append(f"- BLOCK OTHERS: {user_rule.get('block_others')}")
    lines.append("")

    counts = report.get("counts", {})
    lines.extend([
        f"Intrabar rows found: {counts.get('intrabar_rows', 0)}",
        f"Keep rows: {counts.get('keep_rows', 0)}",
        f"Blocked rows: {counts.get('blocked_rows', 0)}",
        "",
        "Keep executing evidence:",
    ])

    keep = report.get("keep_executing", [])
    if keep:
        for row in keep[:10]:
            lines.append(
                f"- {row.get('strategy')} | {row.get('direction')} | {row.get('session')} | "
                f"samples={row.get('sample_count')} | W10={row.get('w10_rate')} | "
                f"TP={row.get('tp_rate')} | SL={row.get('sl_rate')} | "
                f"reliability={row.get('statistics_reliability')}"
            )
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Disable/block intrabar evidence:")

    blocked = report.get("block_or_disable", [])
    if blocked:
        for row in blocked[:15]:
            lines.append(
                f"- {row.get('strategy')} | {row.get('direction')} | {row.get('session')} | "
                f"samples={row.get('sample_count')} | action={row.get('recommended_action')}"
            )
    else:
        lines.append("- none")

    lines.append("")
    lines.append(str(report.get("warning", "")))

    return "\n".join(lines)
