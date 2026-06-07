import json
from collections import Counter

from config.settings import (
    ENABLE_AI_SHADOW_ADVISOR,
    AI_SHADOW_ADVISOR_MIN_SAMPLES,
    AI_SHADOW_ADVISOR_BLOCK_SL_RATE,
    AI_SHADOW_ADVISOR_ALLOW_W10_RATE,
)
from src.account_context import get_account_file
from src.logger import logger


def _safe_float(value, default=0.0):
    try:
        if value in [None, ""]:
            return default

        return float(value)
    except Exception:
        return default


def _normalize(value):
    return str(value or "").strip().upper()


def load_ai_memory_dataset():
    path = get_account_file("ai_memory_dataset.json")

    if not path.exists():
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[AI SHADOW ADVISOR] Failed to load dataset: {e}")
        return []


def _candidate_keys(candidate, session_name=None, market_condition=None):
    strategy = _normalize(candidate.get("strategy"))
    signal = _normalize(candidate.get("signal"))
    entry_model = _normalize(candidate.get("entry_model"))
    session = _normalize(candidate.get("session") or session_name)
    market = _normalize(candidate.get("market_condition") or market_condition)

    return {
        "strategy_signal": (strategy, signal),
        "strategy_signal_session": (strategy, signal, session),
        "strategy_signal_market": (strategy, signal, market),
        "strategy_signal_session_market": (strategy, signal, session, market),
        "strategy_signal_entry": (strategy, signal, entry_model),
    }


def _record_matches(record, key_name, key_value):
    strategy = _normalize(record.get("strategy"))
    signal = _normalize(record.get("signal"))
    entry_model = _normalize(record.get("entry_model"))
    session = _normalize(record.get("session"))
    market = _normalize(record.get("market_condition"))

    record_keys = {
        "strategy_signal": (strategy, signal),
        "strategy_signal_session": (strategy, signal, session),
        "strategy_signal_market": (strategy, signal, market),
        "strategy_signal_session_market": (strategy, signal, session, market),
        "strategy_signal_entry": (strategy, signal, entry_model),
    }

    return record_keys.get(key_name) == key_value


def _summarize_matches(matches):
    total = len(matches)

    if total == 0:
        return None

    w10_count = sum(1 for item in matches if item.get("hit_plus_10"))
    tp_count = sum(1 for item in matches if item.get("hit_tp"))
    sl_count = sum(1 for item in matches if item.get("hit_sl"))

    decisions = Counter(item.get("decision") or "UNKNOWN" for item in matches)
    outcomes = Counter(item.get("final_outcome") or "UNKNOWN" for item in matches)

    avg_rr_values = [
        _safe_float(item.get("rr"), None)
        for item in matches
        if item.get("rr") not in [None, ""]
    ]

    avg_score_values = [
        _safe_float(item.get("score"), None)
        for item in matches
        if item.get("score") not in [None, ""]
    ]

    return {
        "total": total,
        "w10_count": w10_count,
        "tp_count": tp_count,
        "sl_count": sl_count,
        "w10_rate": round(w10_count / total, 4),
        "tp_rate": round(tp_count / total, 4),
        "sl_rate": round(sl_count / total, 4),
        "decisions": dict(decisions),
        "outcomes": dict(outcomes),
        "avg_rr": round(sum(avg_rr_values) / len(avg_rr_values), 4) if avg_rr_values else None,
        "avg_score": round(sum(avg_score_values) / len(avg_score_values), 2) if avg_score_values else None,
    }


def get_ai_shadow_advice(candidate, session_name=None, market_condition=None):
    if not ENABLE_AI_SHADOW_ADVISOR:
        return {
            "enabled": False,
            "recommendation": "NO_ADVICE",
            "reason": "ai_shadow_advisor_disabled",
        }

    dataset = load_ai_memory_dataset()

    if not dataset:
        return {
            "enabled": True,
            "recommendation": "NO_ADVICE",
            "reason": "no_ai_memory_dataset",
        }

    keys = _candidate_keys(candidate, session_name, market_condition)

    best_match = None

    priority = [
        "strategy_signal_session_market",
        "strategy_signal_entry",
        "strategy_signal_session",
        "strategy_signal_market",
        "strategy_signal",
    ]

    for key_name in priority:
        key_value = keys.get(key_name)

        if not key_value:
            continue

        matches = [
            record for record in dataset
            if _record_matches(record, key_name, key_value)
        ]

        stats = _summarize_matches(matches)

        if not stats:
            continue

        if stats["total"] >= AI_SHADOW_ADVISOR_MIN_SAMPLES:
            best_match = {
                "match_type": key_name,
                "match_key": key_value,
                "stats": stats,
            }
            break

    if not best_match:
        return {
            "enabled": True,
            "recommendation": "NO_ADVICE",
            "reason": "not_enough_similar_samples",
            "min_samples": AI_SHADOW_ADVISOR_MIN_SAMPLES,
        }

    stats = best_match["stats"]

    if stats["sl_rate"] >= AI_SHADOW_ADVISOR_BLOCK_SL_RATE:
        recommendation = "BLOCK"
        reason = "historical_sl_rate_too_high"

    elif stats["w10_rate"] >= AI_SHADOW_ADVISOR_ALLOW_W10_RATE:
        recommendation = "ALLOW"
        reason = "historical_w10_rate_favorable"

    else:
        recommendation = "WARN"
        reason = "mixed_historical_performance"

    advice = {
        "enabled": True,
        "recommendation": recommendation,
        "reason": reason,
        "match_type": best_match["match_type"],
        "match_key": list(best_match["match_key"]),
        "stats": stats,
    }

    logger.info(
        f"[AI SHADOW ADVISOR] recommendation={recommendation} "
        f"reason={reason} match={best_match['match_type']} stats={stats}"
    )

    return advice