import json

from datetime import datetime

from config.settings import (
    ENABLE_SETUP_SIMILARITY_MEMORY,
    SETUP_SIMILARITY_MIN_SAMPLES,
    SETUP_SIMILARITY_MIN_W10_RATE,
    SETUP_SIMILARITY_MAX_SL_RATE,
    ENABLE_SETUP_SIMILARITY_SCORING,
    SETUP_SIMILARITY_FAVORABLE_SCORE_BOOST,
    SETUP_SIMILARITY_DANGEROUS_SCORE_PENALTY,
    SETUP_SIMILARITY_NEUTRAL_SCORE_BOOST,
)

from src.account_context import get_account_file
from src.logger import logger
from src.notifier import send_telegram_message
from src.setup_outcome_tracker import load_setup_outcomes


def get_similarity_alerts_file():
    return get_account_file("setup_similarity_alerts.json")


def load_similarity_alerts():
    path = get_similarity_alerts_file()

    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[SIMILARITY MEMORY] Failed to load alerts: {e}")
        return {}


def save_similarity_alerts(items):
    path = get_similarity_alerts_file()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[SIMILARITY MEMORY] Failed to save alerts: {e}")


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _avg(values):
    values = [value for value in values if value is not None]

    if not values:
        return 0.0

    return round(sum(values) / len(values), 2)


def _same_context_matches(current_item, items):
    current_setup_id = current_item.get("setup_id")
    context_key = current_item.get("context_key")

    if not context_key:
        return []

    matches = []

    for setup_id, item in items.items():
        if setup_id == current_setup_id:
            continue

        if item.get("context_key") != context_key:
            continue

        # Only use setups that already had enough time to move or close.
        if item.get("status") == "TRACKING":
            continue

        matches.append(item)

    return matches


def build_similarity_stats(matches):
    total = len(matches)

    if total == 0:
        return None

    w10_count = sum(1 for item in matches if item.get("hit_plus_10"))
    tp_count = sum(1 for item in matches if item.get("hit_tp"))
    sl_count = sum(1 for item in matches if item.get("hit_sl"))

    w10_rate = round(w10_count / total, 2)
    tp_rate = round(tp_count / total, 2)
    sl_rate = round(sl_count / total, 2)

    avg_favorable = _avg([
        _safe_float(item.get("max_favorable_usd"))
        for item in matches
    ])

    avg_adverse = _avg([
        _safe_float(item.get("max_adverse_usd"))
        for item in matches
    ])

    avg_recovery_swing = _avg([
        _safe_float(item.get("max_recovery_swing_usd"))
        for item in matches
    ])

    return {
        "total": total,
        "w10_count": w10_count,
        "tp_count": tp_count,
        "sl_count": sl_count,
        "w10_rate": w10_rate,
        "tp_rate": tp_rate,
        "sl_rate": sl_rate,
        "avg_favorable": avg_favorable,
        "avg_adverse": avg_adverse,
        "avg_recovery_swing": avg_recovery_swing,
    }


def classify_similarity(stats):
    if not stats:
        return "NO_DATA"

    if stats["total"] < SETUP_SIMILARITY_MIN_SAMPLES:
        return "LOW_SAMPLE"

    if (
        stats["w10_rate"] >= SETUP_SIMILARITY_MIN_W10_RATE
        and stats["sl_rate"] <= SETUP_SIMILARITY_MAX_SL_RATE
    ):
        return "FAVORABLE_REPETITIVE_PATTERN"

    if stats["sl_rate"] > SETUP_SIMILARITY_MAX_SL_RATE:
        return "DANGEROUS_REPETITIVE_PATTERN"

    return "NEUTRAL_REPETITIVE_PATTERN"


def already_alerted(setup_id):
    alerts = load_similarity_alerts()
    return bool(alerts.get(setup_id))


def mark_alerted(setup_id, report):
    alerts = load_similarity_alerts()
    alerts[setup_id] = report
    save_similarity_alerts(alerts)


def analyze_setup_similarity(setup_id):
    if not ENABLE_SETUP_SIMILARITY_MEMORY:
        return None

    items = load_setup_outcomes()

    current_item = items.get(setup_id)

    if not current_item:
        return None

    matches = _same_context_matches(current_item, items)
    stats = build_similarity_stats(matches)

    if not stats:
        return None

    classification = classify_similarity(stats)

    return {
        "setup_id": setup_id,
        "classification": classification,
        "context_key": current_item.get("context_key"),
        "scenario_key": current_item.get("scenario_key"),
        "nearby_strategies": current_item.get("nearby_strategies"),
        "strategy": current_item.get("strategy"),
        "signal": current_item.get("signal"),
        "entry_model": current_item.get("entry_model"),
        "session": current_item.get("session"),
        "market_condition": current_item.get("market_condition"),
        "score": current_item.get("score"),
        "stats": stats,
    }


def notify_setup_similarity_if_relevant(setup_id):
    if not ENABLE_SETUP_SIMILARITY_MEMORY:
        return False

    if already_alerted(setup_id):
        return False

    report = analyze_setup_similarity(setup_id)

    if not report:
        return False

    stats = report.get("stats", {})
    classification = report.get("classification")

    if classification == "LOW_SAMPLE":
        return False

    mark_alerted(setup_id, report)

    if classification == "FAVORABLE_REPETITIVE_PATTERN":
        title = "🧠 Favorable Similar Setup Found"
    elif classification == "DANGEROUS_REPETITIVE_PATTERN":
        title = "⚠️ Dangerous Similar Setup Found"
    else:
        title = "🧠 Similar Setup Memory"

    send_telegram_message(
        f"{title}\n"
        f"Setup ID: {setup_id}\n"
        f"Strategy: {report.get('strategy')}\n"
        f"Signal: {report.get('signal')}\n"
        f"Entry Model: {report.get('entry_model')}\n"
        f"Session: {report.get('session')}\n"
        f"Market: {report.get('market_condition')}\n"
        f"Score: {report.get('score')}\n\n"
        f"Similar Samples: {stats.get('total')}\n"
        f"W10: {stats.get('w10_count')} / {stats.get('total')} "
        f"({round(stats.get('w10_rate', 0) * 100, 1)}%)\n"
        f"TP Touch: {stats.get('tp_count')} / {stats.get('total')}\n"
        f"SL Touch: {stats.get('sl_count')} / {stats.get('total')} "
        f"({round(stats.get('sl_rate', 0) * 100, 1)}%)\n"
        f"Avg Favorable: {stats.get('avg_favorable')}\n"
        f"Avg Adverse: {stats.get('avg_adverse')}\n"
        f"Avg After Adverse: {stats.get('avg_after_adverse')}\n\n"
        f"Nearby Strategies: {report.get('nearby_strategies')}\n"
        f"Context: {report.get('context_key')}"
    )

    logger.info(
        f"[SIMILARITY MEMORY] Alert sent | "
        f"setup_id={setup_id} classification={classification} stats={stats}"
    )

    return True

def _score_bucket(score):
    try:
        score = int(float(score))
    except Exception:
        return "SCORE_UNKNOWN"

    if score >= 95:
        return "SCORE_95_100"

    if score >= 90:
        return "SCORE_90_94"

    if score >= 80:
        return "SCORE_80_89"

    return "SCORE_LOW"


def _time_window(dt):
    hour = dt.hour

    if hour < 7:
        return "ASIA_HOURS"

    if 7 <= hour < 10:
        return "LONDON_OPEN"

    if 10 <= hour < 13:
        return "MIDDAY"

    if 13 <= hour < 16:
        return "NEWYORK_OPEN"

    if 16 <= hour < 20:
        return "NEWYORK_LATE"

    return "OFF_HOURS"


def build_candidate_context_key(candidate, session_name, market_condition, current_time=None):
    now = current_time or datetime.now()

    parts = [
        candidate.get("strategy", "UNKNOWN"),
        candidate.get("signal", "NA"),
        candidate.get("entry_model", "NA"),
        session_name or candidate.get("session", "UNKNOWN"),
        market_condition or candidate.get("market_condition", "UNKNOWN"),
        now.strftime("%A").upper(),
        _time_window(now),
        _score_bucket(candidate.get("score")),
    ]

    return "|".join(str(part).upper() for part in parts)


def _matches_for_context_key(context_key, items):
    matches = []

    for item in items.values():
        if item.get("context_key") != context_key:
            continue

        if item.get("status") == "TRACKING":
            continue

        matches.append(item)

    return matches


def analyze_candidate_similarity(candidate, session_name, market_condition, current_time=None):
    if not ENABLE_SETUP_SIMILARITY_MEMORY:
        return None

    context_key = build_candidate_context_key(
        candidate=candidate,
        session_name=session_name,
        market_condition=market_condition,
        current_time=current_time,
    )

    items = load_setup_outcomes()
    matches = _matches_for_context_key(context_key, items)
    stats = build_similarity_stats(matches)

    if not stats:
        return None

    classification = classify_similarity(stats)

    return {
        "classification": classification,
        "context_key": context_key,
        "strategy": candidate.get("strategy"),
        "signal": candidate.get("signal"),
        "entry_model": candidate.get("entry_model"),
        "session": session_name,
        "market_condition": market_condition,
        "score": candidate.get("score"),
        "stats": stats,
    }


def get_setup_similarity_score_adjustment(candidate, session_name, market_condition, current_time=None):
    if not ENABLE_SETUP_SIMILARITY_SCORING:
        return 0, [], None

    report = analyze_candidate_similarity(
        candidate=candidate,
        session_name=session_name,
        market_condition=market_condition,
        current_time=current_time,
    )

    if not report:
        return 0, [], None

    classification = report.get("classification")
    stats = report.get("stats", {})

    if classification == "FAVORABLE_REPETITIVE_PATTERN":
        adjustment = SETUP_SIMILARITY_FAVORABLE_SCORE_BOOST

    elif classification == "DANGEROUS_REPETITIVE_PATTERN":
        adjustment = -abs(SETUP_SIMILARITY_DANGEROUS_SCORE_PENALTY)

    elif classification == "NEUTRAL_REPETITIVE_PATTERN":
        adjustment = SETUP_SIMILARITY_NEUTRAL_SCORE_BOOST

    else:
        adjustment = 0

    if adjustment == 0:
        return 0, [], report

    reasons = [
        (
            f"similarity_memory_{classification.lower()} "
            f"samples={stats.get('total')} "
            f"w10_rate={stats.get('w10_rate')} "
            f"sl_rate={stats.get('sl_rate')} "
            f"adjustment={adjustment}"
        )
    ]

    return adjustment, reasons, report