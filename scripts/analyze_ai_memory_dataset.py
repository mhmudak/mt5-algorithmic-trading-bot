import json
import sys
from pathlib import Path
from collections import defaultdict, Counter

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.account_context import get_account_file
from src.logger import logger


def _safe_float(value):
    try:
        if value in [None, ""]:
            return None

        return float(value)
    except Exception:
        return None


def _rate(count, total):
    if not total:
        return 0.0

    return round(count / total, 4)


def _load_dataset():
    path = get_account_file("ai_memory_dataset.json")

    if not path.exists():
        print(f"Dataset not found: {path}")
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[AI MEMORY ANALYSIS] Failed to load dataset: {e}")
        return []


def _summarize_group(records, group_key):
    groups = defaultdict(list)

    for record in records:
        key = record.get(group_key) or "UNKNOWN"
        groups[key].append(record)

    summary = {}

    for key, items in groups.items():
        total = len(items)

        hit_w10 = sum(1 for item in items if item.get("hit_plus_10"))
        hit_tp = sum(1 for item in items if item.get("hit_tp"))
        hit_sl = sum(1 for item in items if item.get("hit_sl"))

        final_outcomes = Counter(item.get("final_outcome") or "UNKNOWN" for item in items)

        rr_values = [_safe_float(item.get("rr")) for item in items]
        rr_values = [value for value in rr_values if value is not None]

        scores = [_safe_float(item.get("score")) for item in items]
        scores = [value for value in scores if value is not None]

        favorable = [_safe_float(item.get("max_favorable_usd")) for item in items]
        favorable = [value for value in favorable if value is not None]

        adverse = [_safe_float(item.get("max_adverse_usd")) for item in items]
        adverse = [value for value in adverse if value is not None]

        summary[key] = {
            "total": total,
            "w10_count": hit_w10,
            "tp_count": hit_tp,
            "sl_count": hit_sl,
            "w10_rate": _rate(hit_w10, total),
            "tp_rate": _rate(hit_tp, total),
            "sl_rate": _rate(hit_sl, total),
            "final_outcomes": dict(final_outcomes),
            "avg_rr": round(sum(rr_values) / len(rr_values), 4) if rr_values else None,
            "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
            "avg_favorable": round(sum(favorable) / len(favorable), 2) if favorable else None,
            "avg_adverse": round(sum(adverse) / len(adverse), 2) if adverse else None,
        }

    return dict(sorted(summary.items(), key=lambda item: item[1]["total"], reverse=True))


def _build_insights(records):
    insights = []

    for record in records:
        decision = str(record.get("decision") or "")
        strategy = record.get("strategy")
        signal = record.get("signal")
        setup_id = record.get("setup_id")
        rr = _safe_float(record.get("rr"))
        required_rr = _safe_float(record.get("required_rr"))

        hit_tp = bool(record.get("hit_tp"))
        hit_sl = bool(record.get("hit_sl"))
        hit_w10 = bool(record.get("hit_plus_10"))

        if decision == "CANDIDATE_REJECTED_LOW_RR" and (hit_w10 or hit_tp):
            insights.append({
                "type": "LOW_RR_REJECTION_LATER_WORKED",
                "setup_id": setup_id,
                "strategy": strategy,
                "signal": signal,
                "rr": rr,
                "required_rr": required_rr,
                "hit_w10": hit_w10,
                "hit_tp": hit_tp,
                "message": "Candidate rejected for low RR but later moved favorably",
            })

        if "EXECUTION_SUCCESS" in decision and hit_sl:
            insights.append({
                "type": "EXECUTED_TRADE_HIT_SL",
                "setup_id": setup_id,
                "strategy": strategy,
                "signal": signal,
                "decision": decision,
                "message": "Executed trade later hit SL",
            })

        if "BLOCKED_BY_MEMORY" in decision and (hit_w10 or hit_tp):
            insights.append({
                "type": "MEMORY_BLOCK_MAY_HAVE_BLOCKED_WINNER",
                "setup_id": setup_id,
                "strategy": strategy,
                "signal": signal,
                "decision": decision,
                "hit_w10": hit_w10,
                "hit_tp": hit_tp,
                "message": "Memory blocked setup but outcome later became favorable",
            })

        if "BLOCKED_BY_MEMORY" in decision and hit_sl:
            insights.append({
                "type": "MEMORY_BLOCK_PROTECTED_FROM_SL",
                "setup_id": setup_id,
                "strategy": strategy,
                "signal": signal,
                "decision": decision,
                "message": "Memory block appears justified because setup later hit SL",
            })

    return insights


def analyze_ai_memory_dataset():
    records = _load_dataset()

    if not records:
        print("No records to analyze.")
        return

    report = {
        "total_records": len(records),
        "by_decision": _summarize_group(records, "decision"),
        "by_strategy": _summarize_group(records, "strategy"),
        "by_signal": _summarize_group(records, "signal"),
        "by_session": _summarize_group(records, "session"),
        "by_market_condition": _summarize_group(records, "market_condition"),
        "by_final_outcome": _summarize_group(records, "final_outcome"),
        "insights": _build_insights(records),
    }

    output_path = get_account_file("ai_memory_dataset_analysis.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"Analyzed records: {len(records)}")
    print(f"Insights: {len(report['insights'])}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    analyze_ai_memory_dataset()