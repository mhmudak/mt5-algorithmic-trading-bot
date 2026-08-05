
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


PHASE = "PHASE_6T2_STRATEGY_EVIDENCE_DIGEST"


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


def load_phase6t_strategy_evidence_dashboard(
    path: str | Path = "data/reports/strategy_evidence_dashboard/phase6t_strategy_evidence_dashboard_latest.json",
) -> Dict[str, Any]:
    target = Path(path)

    if not target.exists():
        return {
            "exists": False,
            "path": str(target),
            "dashboard": None,
        }

    try:
        return {
            "exists": True,
            "path": str(target),
            "dashboard": json.loads(target.read_text(encoding="utf-8")),
        }
    except Exception as exc:
        return {
            "exists": True,
            "path": str(target),
            "error": str(exc),
            "dashboard": None,
        }


def _row_score(row: Dict[str, Any]) -> float:
    return _to_float(row.get("evidence_score"), 0.0) or 0.0


def _matched(row: Dict[str, Any]) -> int:
    return _to_int(row.get("matched_outcomes"))


def _net_profit(row: Dict[str, Any]) -> float:
    return _to_float(row.get("net_profit"), 0.0) or 0.0


def _format_pct(value: Any) -> str:
    numeric = _to_float(value)

    if numeric is None:
        return "n/a"

    return f"{numeric:.1f}%"


def _format_money(value: Any) -> str:
    numeric = _to_float(value, 0.0) or 0.0
    return f"{numeric:.2f}"


def _compact_row(row: Dict[str, Any]) -> str:
    strategy = _safe_str(row.get("strategy"))
    outlook_tag = _safe_str(row.get("outlook_tag"), "")

    label = strategy
    if outlook_tag:
        label = f"{strategy} / {outlook_tag}"

    return (
        f"- {label}: "
        f"{_safe_str(row.get('classification'))}, "
        f"matched={_matched(row)}, "
        f"W={_to_int(row.get('wins'))}, "
        f"L={_to_int(row.get('losses'))}, "
        f"WR={_format_pct(row.get('win_rate_pct'))}, "
        f"net={_format_money(row.get('net_profit'))}"
    )


def select_digest_rows(
    dashboard: Dict[str, Any],
    *,
    top_n: int = 5,
) -> Dict[str, List[Dict[str, Any]]]:
    strategy_tag_rows = dashboard.get("strategy_tag_rows", [])
    strategy_rows = dashboard.get("strategy_rows", [])

    if not isinstance(strategy_tag_rows, list):
        strategy_tag_rows = []

    if not isinstance(strategy_rows, list):
        strategy_rows = []

    promising = [
        row for row in strategy_tag_rows
        if row.get("classification") in {"PROMISING_EVIDENCE", "POSITIVE_BUT_MIXED"}
    ]
    weak = [
        row for row in strategy_tag_rows
        if row.get("classification") in {"WEAK_EVIDENCE", "NEGATIVE_BUT_MIXED"}
    ]
    neutral_mixed = [
        row for row in strategy_tag_rows
        if row.get("classification") == "NEUTRAL_OR_MIXED"
    ]
    sample_needed = [
        row for row in strategy_tag_rows
        if row.get("classification") == "INSUFFICIENT_EVIDENCE"
    ]

    promising.sort(key=lambda row: (-_row_score(row), -_matched(row), _safe_str(row.get("strategy"))))
    weak.sort(key=lambda row: (_net_profit(row), _row_score(row), _safe_str(row.get("strategy"))))
    neutral_mixed.sort(key=lambda row: (-_matched(row), -_row_score(row), _safe_str(row.get("strategy"))))
    sample_needed.sort(key=lambda row: (-_matched(row), _safe_str(row.get("strategy")), _safe_str(row.get("outlook_tag"))))

    overall = list(strategy_rows)
    overall.sort(key=lambda row: (-_row_score(row), -_matched(row), _safe_str(row.get("strategy"))))

    return {
        "promising": promising[:top_n],
        "weak": weak[:top_n],
        "neutral_mixed": neutral_mixed[:top_n],
        "sample_needed": sample_needed[:top_n],
        "overall": overall[:top_n],
    }

def build_phase6t_strategy_evidence_digest(
    dashboard: Optional[Dict[str, Any]],
    *,
    top_n: int = 5,
) -> Dict[str, Any]:
    dashboard = dashboard if isinstance(dashboard, dict) else {}

    source = dashboard.get("source", {}) if isinstance(dashboard.get("source"), dict) else {}
    attribution_counts = source.get("attribution_counts") if isinstance(source.get("attribution_counts"), dict) else {}
    classification_counts = dashboard.get("classification_counts", {})
    classification_counts = classification_counts if isinstance(classification_counts, dict) else {}

    selected = select_digest_rows(dashboard, top_n=top_n)

    lines = [
        "📊 Phase 6T Strategy Evidence Digest",
        "",
        "Mode: DASHBOARD ONLY",
        "Decision impact: NONE",
        "Can execute: False",
        "Can block trade: False",
        "Can modify risk: False",
        "",
        "Attribution:",
        f"- annotations={_to_int(attribution_counts.get('annotations'))}",
        f"- matched={_to_int(attribution_counts.get('matched'))}",
        f"- unmatched={_to_int(attribution_counts.get('unmatched'))}",
        "",
        "Classifications:",
    ]

    if classification_counts:
        for key, value in sorted(classification_counts.items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")

    lines.append("")

    lines.append("Promising / Positive:")
    if selected["promising"]:
        lines.extend(_compact_row(row) for row in selected["promising"])
    else:
        lines.append("- none yet")

    lines.append("")
    lines.append("Weak / Negative:")
    if selected["weak"]:
        lines.extend(_compact_row(row) for row in selected["weak"])
    else:
        lines.append("- none confirmed yet")

    lines.append("")
    lines.append("Neutral / Mixed:")
    if selected["neutral_mixed"]:
        lines.extend(_compact_row(row) for row in selected["neutral_mixed"])
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Needs more samples:")
    if selected["sample_needed"]:
        lines.extend(_compact_row(row) for row in selected["sample_needed"])
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Warning: evidence only. Do not use for blocking/risk changes until sample size is strong.")

    message = "\n".join(lines)

    return {
        "phase": PHASE,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision_impact": "DIGEST_ONLY",
        "auto_trade_allowed": False,
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
        "can_modify_strategy_policy": False,
        "top_n": int(top_n),
        "source": source,
        "classification_counts": classification_counts,
        "selected": selected,
        "message": message,
    }


def write_phase6t_strategy_evidence_digest(
    digest: Dict[str, Any],
    *,
    output_dir: str | Path = "data/reports/strategy_evidence_digest",
) -> Dict[str, str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = target / f"phase6t_strategy_evidence_digest_{timestamp}.json"
    latest_json_path = target / "phase6t_strategy_evidence_digest_latest.json"
    txt_path = target / f"phase6t_strategy_evidence_digest_{timestamp}.txt"
    latest_txt_path = target / "phase6t_strategy_evidence_digest_latest.txt"

    json_text = json.dumps(digest, indent=2, ensure_ascii=False, default=str)
    message = str(digest.get("message") or "")

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


def maybe_send_phase6t_strategy_evidence_digest(
    digest: Dict[str, Any],
    *,
    send_telegram: bool = False,
    notifier=None,
) -> Dict[str, Any]:
    if not send_telegram:
        return {
            "phase": PHASE,
            "send_telegram": False,
            "telegram_sent": False,
            "reason": "telegram_send_disabled",
            "decision_impact": "DIGEST_ONLY",
            "can_execute": False,
            "can_block_trade": False,
            "can_modify_risk": False,
        }

    if notifier is None:
        return {
            "phase": PHASE,
            "send_telegram": True,
            "telegram_sent": False,
            "reason": "notifier_missing",
            "decision_impact": "DIGEST_ONLY",
            "can_execute": False,
            "can_block_trade": False,
            "can_modify_risk": False,
        }

    notifier(str(digest.get("message") or ""))

    return {
        "phase": PHASE,
        "send_telegram": True,
        "telegram_sent": True,
        "reason": "sent",
        "decision_impact": "DIGEST_ONLY",
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_risk": False,
    }
