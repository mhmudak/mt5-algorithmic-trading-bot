import argparse
import json
from collections import Counter, defaultdict

from ai_export_common import (
    add_account_argument,
    get_ai_account_file,
    load_json_file,
)

def _safe_float(value, default=None):
    try:
        if value in [None, ""]:
            return default

        return float(value)
    except Exception:
        return default


def _rate(count, total):
    if not total:
        return 0.0

    return round(count / total, 4)


def _load_ai_memory_dataset(account=None):
    path = get_ai_account_file("ai_memory_dataset.json", account)

    if not path.exists():
        print(f"Dataset not found: {path}")
        return []

    return load_json_file(path, [])


def _is_favorable(record):
    return bool(record.get("hit_plus_10")) or bool(record.get("hit_tp"))


def _is_bad(record):
    return bool(record.get("hit_sl"))


def _evaluate_record(record):
    recommendation = str(record.get("ai_recommendation") or "NO_ADVICE").upper()

    favorable = _is_favorable(record)
    bad = _is_bad(record)

    if recommendation == "ALLOW":
        if favorable and not bad:
            result = "GOOD_ALLOW"
        elif bad:
            result = "BAD_ALLOW"
        else:
            result = "UNPROVEN_ALLOW"

    elif recommendation == "BLOCK":
        if bad:
            result = "GOOD_BLOCK_PROTECTED_FROM_SL"
        elif favorable:
            result = "BAD_BLOCK_BLOCKED_WINNER"
        else:
            result = "UNPROVEN_BLOCK"

    elif recommendation == "WARN":
        if bad:
            result = "GOOD_WARN_RISK_CONFIRMED"
        elif favorable:
            result = "WARN_BUT_SETUP_WORKED"
        else:
            result = "NEUTRAL_WARN"

    else:
        result = "NO_ADVICE_OR_UNKNOWN"

    return {
        "setup_id": record.get("setup_id"),
        "created_at": record.get("created_at"),
        "strategy": record.get("strategy"),
        "signal": record.get("signal"),
        "session": record.get("session"),
        "market_condition": record.get("market_condition"),
        "decision": record.get("decision"),

        "ai_recommendation": recommendation,
        "ai_reason": record.get("ai_reason"),
        "ai_match_type": record.get("ai_match_type"),
        "ai_samples": record.get("ai_samples"),
        "ai_w10_rate": record.get("ai_w10_rate"),
        "ai_tp_rate": record.get("ai_tp_rate"),
        "ai_sl_rate": record.get("ai_sl_rate"),

        "hit_plus_10": record.get("hit_plus_10"),
        "hit_tp": record.get("hit_tp"),
        "hit_sl": record.get("hit_sl"),
        "final_outcome": record.get("final_outcome"),

        "evaluation_result": result,
    }


def _summarize(records, group_key):
    groups = defaultdict(list)

    for item in records:
        key = item.get(group_key) or "UNKNOWN"
        groups[key].append(item)

    summary = {}

    for key, items in groups.items():
        total = len(items)

        good_allow = sum(1 for item in items if item["evaluation_result"] == "GOOD_ALLOW")
        bad_allow = sum(1 for item in items if item["evaluation_result"] == "BAD_ALLOW")
        good_block = sum(1 for item in items if item["evaluation_result"] == "GOOD_BLOCK_PROTECTED_FROM_SL")
        bad_block = sum(1 for item in items if item["evaluation_result"] == "BAD_BLOCK_BLOCKED_WINNER")

        favorable = sum(1 for item in items if item.get("hit_plus_10") or item.get("hit_tp"))
        sl = sum(1 for item in items if item.get("hit_sl"))

        recommendations = Counter(item.get("ai_recommendation") or "NO_ADVICE" for item in items)
        results = Counter(item.get("evaluation_result") for item in items)

        summary[key] = {
            "total": total,
            "recommendations": dict(recommendations),
            "results": dict(results),

            "favorable_count": favorable,
            "sl_count": sl,
            "favorable_rate": _rate(favorable, total),
            "sl_rate": _rate(sl, total),

            "good_allow": good_allow,
            "bad_allow": bad_allow,
            "good_block": good_block,
            "bad_block": bad_block,

            "allow_precision": _rate(
                good_allow,
                good_allow + bad_allow,
            ),
            "block_precision": _rate(
                good_block,
                good_block + bad_block,
            ),
        }

    return dict(
        sorted(
            summary.items(),
            key=lambda item: item[1]["total"],
            reverse=True,
        )
    )


def evaluate_ai_shadow_advisor(account=None):
    dataset = _load_ai_memory_dataset(account)

    if not dataset:
        print("No AI memory dataset to evaluate.")
        return

    evaluated = [
        _evaluate_record(record)
        for record in dataset
        if record.get("ai_recommendation")
    ]

    report = {
        "total_dataset_records": len(dataset),
        "total_ai_evaluated_records": len(evaluated),
        "by_ai_recommendation": _summarize(evaluated, "ai_recommendation"),
        "by_ai_match_type": _summarize(evaluated, "ai_match_type"),
        "by_strategy": _summarize(evaluated, "strategy"),
        "by_session": _summarize(evaluated, "session"),
        "by_market_condition": _summarize(evaluated, "market_condition"),
        "records": evaluated,
    }

    output_path = get_ai_account_file("ai_shadow_advisor_evaluation.json", account)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"Dataset records: {len(dataset)}")
    print(f"AI evaluated records: {len(evaluated)}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    add_account_argument(parser)
    args = parser.parse_args()

    evaluate_ai_shadow_advisor(account=args.account)