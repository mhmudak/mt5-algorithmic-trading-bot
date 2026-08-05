
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


PHASE = "PHASE_6T1_STRATEGY_EVIDENCE_DASHBOARD"


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_str(value: Any, default: str = "UNKNOWN") -> str:
    if value is None:
        return default

    text = str(value).strip()
    if not text:
        return default

    return text


def _safe_upper(value: Any, default: str = "UNKNOWN") -> str:
    return _safe_str(value, default).upper()


def load_phase6s_attribution_report(
    path: str | Path = "data/reports/market_outlook/outcome_attribution/phase6s_outcome_attribution_latest.json",
) -> Dict[str, Any]:
    target = Path(path)

    if not target.exists():
        return {
            "exists": False,
            "path": str(target),
            "report": None,
        }

    try:
        return {
            "exists": True,
            "path": str(target),
            "report": json.loads(target.read_text(encoding="utf-8")),
        }
    except Exception as exc:
        return {
            "exists": True,
            "path": str(target),
            "error": str(exc),
            "report": None,
        }


def classify_strategy_evidence(
    summary: Dict[str, Any],
    *,
    min_matched_samples: int = 5,
    promising_min_win_rate: float = 55.0,
    weak_max_win_rate: float = 40.0,
) -> str:
    matched = _to_int(summary.get("matched_outcomes"))
    wins = _to_int(summary.get("wins"))
    losses = _to_int(summary.get("losses"))
    net_profit = _to_float(summary.get("net_profit"), 0.0) or 0.0
    win_rate = _to_float(summary.get("win_rate_pct"))

    resolved = wins + losses + _to_int(summary.get("breakeven"))

    if matched < min_matched_samples or resolved < min_matched_samples:
        return "INSUFFICIENT_EVIDENCE"

    if net_profit > 0 and win_rate is not None and win_rate >= promising_min_win_rate:
        return "PROMISING_EVIDENCE"

    if net_profit < 0 and win_rate is not None and win_rate <= weak_max_win_rate:
        return "WEAK_EVIDENCE"

    if net_profit > 0:
        return "POSITIVE_BUT_MIXED"

    if net_profit < 0:
        return "NEGATIVE_BUT_MIXED"

    return "NEUTRAL_OR_MIXED"


def _evidence_score(summary: Dict[str, Any]) -> float:
    matched = _to_int(summary.get("matched_outcomes"))
    net_profit = _to_float(summary.get("net_profit"), 0.0) or 0.0
    win_rate = _to_float(summary.get("win_rate_pct"), 0.0) or 0.0
    avg_profit = _to_float(summary.get("avg_profit"), 0.0) or 0.0

    return round(net_profit + avg_profit + (win_rate / 10.0) + min(matched, 50) * 0.1, 4)


def _summary_to_row(
    key: str,
    summary: Dict[str, Any],
    *,
    row_type: str,
    min_matched_samples: int,
    promising_min_win_rate: float,
    weak_max_win_rate: float,
) -> Dict[str, Any]:
    strategy = key
    outlook_tag = ""

    if row_type == "strategy_tag" and "|" in key:
        strategy, outlook_tag = key.split("|", 1)

    classification = classify_strategy_evidence(
        summary,
        min_matched_samples=min_matched_samples,
        promising_min_win_rate=promising_min_win_rate,
        weak_max_win_rate=weak_max_win_rate,
    )

    return {
        "row_type": row_type,
        "key": key,
        "strategy": strategy,
        "outlook_tag": outlook_tag,
        "classification": classification,
        "evidence_score": _evidence_score(summary),
        "count": _to_int(summary.get("count")),
        "matched_outcomes": _to_int(summary.get("matched_outcomes")),
        "unmatched": _to_int(summary.get("unmatched")),
        "closed": _to_int(summary.get("closed")),
        "wins": _to_int(summary.get("wins")),
        "losses": _to_int(summary.get("losses")),
        "breakeven": _to_int(summary.get("breakeven")),
        "unknown": _to_int(summary.get("unknown")),
        "net_profit": _to_float(summary.get("net_profit"), 0.0),
        "avg_profit": _to_float(summary.get("avg_profit")),
        "win_rate_pct": _to_float(summary.get("win_rate_pct")),
        "loss_rate_pct": _to_float(summary.get("loss_rate_pct")),
    }


def build_phase6t_strategy_evidence_dashboard(
    *,
    attribution_report_path: str | Path = "data/reports/market_outlook/outcome_attribution/phase6s_outcome_attribution_latest.json",
    min_matched_samples: int = 5,
    promising_min_win_rate: float = 55.0,
    weak_max_win_rate: float = 40.0,
) -> Dict[str, Any]:
    loaded = load_phase6s_attribution_report(attribution_report_path)
    report = loaded.get("report") or {}

    by_strategy = report.get("by_strategy", {}) if isinstance(report, dict) else {}
    by_strategy_tag = report.get("by_strategy_tag", {}) if isinstance(report, dict) else {}
    by_tag = report.get("by_tag", {}) if isinstance(report, dict) else {}

    strategy_rows = [
        _summary_to_row(
            strategy,
            summary,
            row_type="strategy",
            min_matched_samples=min_matched_samples,
            promising_min_win_rate=promising_min_win_rate,
            weak_max_win_rate=weak_max_win_rate,
        )
        for strategy, summary in by_strategy.items()
        if isinstance(summary, dict)
    ]

    strategy_tag_rows = [
        _summary_to_row(
            key,
            summary,
            row_type="strategy_tag",
            min_matched_samples=min_matched_samples,
            promising_min_win_rate=promising_min_win_rate,
            weak_max_win_rate=weak_max_win_rate,
        )
        for key, summary in by_strategy_tag.items()
        if isinstance(summary, dict)
    ]

    tag_rows = [
        _summary_to_row(
            tag,
            summary,
            row_type="outlook_tag",
            min_matched_samples=min_matched_samples,
            promising_min_win_rate=promising_min_win_rate,
            weak_max_win_rate=weak_max_win_rate,
        )
        for tag, summary in by_tag.items()
        if isinstance(summary, dict)
    ]

    strategy_rows.sort(key=lambda row: (row["classification"], -row["evidence_score"], row["strategy"]))
    strategy_tag_rows.sort(key=lambda row: (row["classification"], -row["evidence_score"], row["strategy"], row["outlook_tag"]))
    tag_rows.sort(key=lambda row: (row["classification"], -row["evidence_score"], row["key"]))

    classification_counts: Dict[str, int] = {}

    for row in strategy_tag_rows:
        classification_counts[row["classification"]] = classification_counts.get(row["classification"], 0) + 1

    return {
        "phase": PHASE,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),

        # Safety contract
        "decision_impact": "DASHBOARD_ONLY",
        "auto_trade_allowed": False,
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
        "can_modify_strategy_policy": False,

        "settings": {
            "min_matched_samples": int(min_matched_samples),
            "promising_min_win_rate": float(promising_min_win_rate),
            "weak_max_win_rate": float(weak_max_win_rate),
        },
        "source": {
            "attribution_report_path": str(attribution_report_path),
            "attribution_report_exists": loaded.get("exists"),
            "attribution_report_error": loaded.get("error"),
            "attribution_counts": report.get("counts") if isinstance(report, dict) else None,
        },
        "classification_counts": classification_counts,
        "strategy_rows": strategy_rows,
        "strategy_tag_rows": strategy_tag_rows,
        "tag_rows": tag_rows,
        "interpretation_warning": "Dashboard only. Do not promote to blocking/risk changes until matched closed samples are large enough.",
    }


def write_phase6t_strategy_evidence_dashboard(
    dashboard: Dict[str, Any],
    *,
    output_dir: str | Path = "data/reports/strategy_evidence_dashboard",
) -> Dict[str, str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = target / f"phase6t_strategy_evidence_dashboard_{timestamp}.json"
    latest_json_path = target / "phase6t_strategy_evidence_dashboard_latest.json"
    strategy_csv_path = target / f"phase6t_strategy_evidence_by_strategy_{timestamp}.csv"
    strategy_tag_csv_path = target / f"phase6t_strategy_evidence_by_strategy_tag_{timestamp}.csv"
    tag_csv_path = target / f"phase6t_strategy_evidence_by_tag_{timestamp}.csv"

    text = json.dumps(dashboard, indent=2, ensure_ascii=False, default=str)
    json_path.write_text(text, encoding="utf-8")
    latest_json_path.write_text(text, encoding="utf-8")

    _write_rows_csv(strategy_csv_path, dashboard.get("strategy_rows", []))
    _write_rows_csv(strategy_tag_csv_path, dashboard.get("strategy_tag_rows", []))
    _write_rows_csv(tag_csv_path, dashboard.get("tag_rows", []))

    return {
        "json": str(json_path),
        "latest_json": str(latest_json_path),
        "by_strategy_csv": str(strategy_csv_path),
        "by_strategy_tag_csv": str(strategy_tag_csv_path),
        "by_tag_csv": str(tag_csv_path),
    }


def _write_rows_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fieldnames = [
        "row_type",
        "key",
        "strategy",
        "outlook_tag",
        "classification",
        "evidence_score",
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

        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})
