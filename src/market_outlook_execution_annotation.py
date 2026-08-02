
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


PHASE = "PHASE_6S8_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION"


def _safe_upper(value: Any, default: str = "UNKNOWN") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return text.upper()


def classify_phase6s_outlook_execution_tag(advisory_summary: Optional[Dict[str, Any]]) -> str:
    """
    Convert Phase 6S advisory context into a stable evidence tag.

    This is annotation only. It must never approve, block, or modify a trade.
    """
    if not advisory_summary:
        return "OUTLOOK_NOT_AVAILABLE"

    if advisory_summary.get("enabled") is False:
        return "OUTLOOK_ADVISORY_DISABLED"

    if advisory_summary.get("ready") is False:
        return "OUTLOOK_NOT_READY"

    alignment = _safe_upper(advisory_summary.get("alignment"))
    risk_level = _safe_upper(advisory_summary.get("risk_level"))

    if risk_level in {"CRITICAL", "HIGH"}:
        return "OUTLOOK_HIGH_RISK"

    if alignment in {"AGAINST_OUTLOOK_LEADER", "OPPOSITE_OUTLOOK_LEADER"}:
        return "OUTLOOK_HIGH_RISK"

    if alignment in {"ALIGNED_WITH_OUTLOOK_LEADER", "WITH_OUTLOOK_LEADER"}:
        if risk_level in {"LOW", "MEDIUM", "INFO"}:
            return "OUTLOOK_ALIGNED"
        return "OUTLOOK_CAUTION"

    return "OUTLOOK_CAUTION"


def build_phase6s_execution_annotation(
    *,
    advisory_summary: Optional[Dict[str, Any]],
    setup_payload: Optional[Dict[str, Any]],
    execution_result: Any,
    trigger_context: str = "after_execute_trade",
) -> Dict[str, Any]:
    setup_payload = setup_payload if isinstance(setup_payload, dict) else {}
    advisory_summary = advisory_summary if isinstance(advisory_summary, dict) else {}

    tag = classify_phase6s_outlook_execution_tag(advisory_summary)

    return {
        "phase": PHASE,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "trigger_context": trigger_context,
        "tag": tag,

        # Safety contract
        "decision_impact": "ANNOTATION_ONLY",
        "auto_trade_allowed": False,
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,

        # Execution evidence
        "execution_result_bool": bool(execution_result),
        "execution_result_repr": repr(execution_result)[:500],

        # Setup references
        "symbol": setup_payload.get("symbol"),
        "setup_id": setup_payload.get("setup_id"),
        "strategy": setup_payload.get("strategy"),
        "signal": setup_payload.get("signal"),
        "entry_reference": setup_payload.get("entry_reference"),
        "sl_reference": setup_payload.get("sl_reference"),
        "tp_reference": setup_payload.get("tp_reference"),
        "rr": setup_payload.get("rr"),

        # Outlook/advisory evidence
        "outlook_alignment": advisory_summary.get("alignment"),
        "outlook_risk_level": advisory_summary.get("risk_level"),
        "outlook_ready": advisory_summary.get("ready"),
        "outlook_enabled": advisory_summary.get("enabled"),
        "outlook_reason": advisory_summary.get("reason"),
        "outlook_decision_impact": advisory_summary.get("decision_impact"),
        "outlook_can_block_trade": advisory_summary.get("can_block_trade"),
        "outlook_can_modify_risk": advisory_summary.get("can_modify_risk"),
    }


def append_phase6s_execution_annotation(
    annotation: Dict[str, Any],
    *,
    directory: str | Path = "data/reports/market_outlook/execution_annotations",
) -> Path:
    """
    Append annotation to JSONL evidence file.

    This function writes evidence only. It must never call execution, risk, or notifier code.
    """
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"phase6s_execution_annotations_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
    path = target_dir / file_name

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(annotation, ensure_ascii=False, default=str) + "\n")

    return path
