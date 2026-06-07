import json
import sys
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.account_context import get_account_file
from src.logger import logger
from src.memory_decision_report import load_memory_decision_reports
from src.setup_outcome_tracker import load_setup_outcomes


def _safe_get(data, key, default=None):
    if not isinstance(data, dict):
        return default

    return data.get(key, default)


def _build_ai_record(report, outcome):
    extra = _safe_get(report, "extra", {}) or {}
    memory = _safe_get(report, "memory", {}) or {}
    adjustments = _safe_get(report, "adjustments", {}) or {}
    context = _safe_get(report, "context", {}) or {}

    return {
        "exported_at": datetime.now().isoformat(),

        "setup_id": report.get("setup_id"),
        "created_at": report.get("created_at"),

        "strategy": report.get("strategy"),
        "signal": report.get("signal"),
        "entry_model": report.get("entry_model"),
        "session": report.get("session"),
        "market_condition": report.get("market_condition"),
        "score": report.get("score"),

        "decision": report.get("decision"),
        "decision_reason": report.get("decision_reason"),
        "reason": report.get("reason"),

        "entry": report.get("entry"),
        "sl": report.get("sl"),
        "tp": report.get("tp"),
        "lot": report.get("lot"),
        "rr": report.get("rr") or extra.get("rr"),
        "required_rr": report.get("required_rr") or extra.get("required_rr"),

        "memory": memory,
        "adjustments": adjustments,
        "context": context,
        "extra": extra,

        "outcome_status": _safe_get(outcome, "status"),
        "final_outcome": _safe_get(outcome, "final_outcome"),
        "first_hit": _safe_get(outcome, "first_hit"),
        "hit_plus_10": _safe_get(outcome, "hit_plus_10"),
        "hit_tp": _safe_get(outcome, "hit_tp"),
        "hit_sl": _safe_get(outcome, "hit_sl"),

        "max_favorable_usd": _safe_get(outcome, "max_favorable_usd"),
        "max_adverse_usd": _safe_get(outcome, "max_adverse_usd"),
        "max_recovery_swing_usd": _safe_get(outcome, "max_recovery_swing_usd"),

        "context_key": _safe_get(outcome, "context_key"),
        "scenario_key": _safe_get(outcome, "scenario_key"),
        "nearby_strategies": _safe_get(outcome, "nearby_strategies"),
    }


def export_ai_memory_dataset():
    reports = load_memory_decision_reports()
    outcomes = load_setup_outcomes()

    output_jsonl = get_account_file("ai_memory_dataset.jsonl")
    output_json = get_account_file("ai_memory_dataset.json")

    records = []

    for report in reports:
        setup_id = report.get("setup_id")
        outcome = outcomes.get(setup_id, {}) if setup_id else {}

        records.append(_build_ai_record(report, outcome))

    output_jsonl.parent.mkdir(parents=True, exist_ok=True)

    with open(output_jsonl, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    logger.info(
        f"[AI MEMORY DATASET] Exported {len(records)} records | "
        f"jsonl={output_jsonl} json={output_json}"
    )

    print(f"Exported records: {len(records)}")
    print(f"JSONL: {output_jsonl}")
    print(f"JSON: {output_json}")


if __name__ == "__main__":
    export_ai_memory_dataset()