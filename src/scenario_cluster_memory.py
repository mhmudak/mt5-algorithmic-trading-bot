import json

from config.settings import (
    ENABLE_SCENARIO_CLUSTER_MEMORY,
    SCENARIO_CLUSTER_MIN_STRATEGIES,
    SCENARIO_CLUSTER_MIN_SAMPLES,
    SCENARIO_CLUSTER_MIN_W10_RATE,
    SCENARIO_CLUSTER_MAX_SL_RATE,
    ENABLE_SCENARIO_CLUSTER_SCORING,
    SCENARIO_CLUSTER_FAVORABLE_SCORE_BOOST,
    SCENARIO_CLUSTER_DANGEROUS_SCORE_PENALTY,
    SCENARIO_CLUSTER_NEUTRAL_SCORE_BOOST,
)

from src.account_context import get_account_file
from src.logger import logger
from src.notifier import send_telegram_message
from src.setup_outcome_tracker import load_setup_outcomes
from src.setup_similarity_memory import build_similarity_stats


def get_cluster_alerts_file():
    return get_account_file("scenario_cluster_alerts.json")


def load_cluster_alerts():
    path = get_cluster_alerts_file()

    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[SCENARIO CLUSTER] Failed to load alerts: {e}")
        return {}


def save_cluster_alerts(items):
    path = get_cluster_alerts_file()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[SCENARIO CLUSTER] Failed to save alerts: {e}")


def _normalize_strategy_combo(strategies):
    if not strategies:
        return []

    cleaned = []

    for strategy in strategies:
        strategy = str(strategy or "").upper().strip()

        if strategy and strategy not in cleaned:
            cleaned.append(strategy)

    return sorted(cleaned)


def build_cluster_key(item):
    strategies = _normalize_strategy_combo(item.get("nearby_strategies", []))

    if len(strategies) < SCENARIO_CLUSTER_MIN_STRATEGIES:
        return None

    parts = [
        item.get("session", "UNKNOWN"),
        item.get("market_condition", "UNKNOWN"),
        item.get("day_of_week", "UNKNOWN"),
        item.get("time_window", "UNKNOWN"),
        item.get("signal", "NA"),
        "+".join(strategies),
    ]

    return "|".join(str(part).upper() for part in parts)


def _cluster_matches(current_item, items):
    current_setup_id = current_item.get("setup_id")
    cluster_key = build_cluster_key(current_item)

    if not cluster_key:
        return [], None

    matches = []

    for setup_id, item in items.items():
        if setup_id == current_setup_id:
            continue

        if item.get("status") == "TRACKING":
            continue

        if build_cluster_key(item) != cluster_key:
            continue

        matches.append(item)

    return matches, cluster_key


def classify_cluster(stats):
    if not stats:
        return "NO_DATA"

    if stats["total"] < SCENARIO_CLUSTER_MIN_SAMPLES:
        return "LOW_SAMPLE"

    if (
        stats["w10_rate"] >= SCENARIO_CLUSTER_MIN_W10_RATE
        and stats["sl_rate"] <= SCENARIO_CLUSTER_MAX_SL_RATE
    ):
        return "FAVORABLE_CLUSTER_PATTERN"

    if stats["sl_rate"] > SCENARIO_CLUSTER_MAX_SL_RATE:
        return "DANGEROUS_CLUSTER_PATTERN"

    return "NEUTRAL_CLUSTER_PATTERN"


def already_alerted(setup_id):
    alerts = load_cluster_alerts()
    return bool(alerts.get(setup_id))


def mark_alerted(setup_id, report):
    alerts = load_cluster_alerts()
    alerts[setup_id] = report
    save_cluster_alerts(alerts)


def analyze_scenario_cluster(setup_id):
    if not ENABLE_SCENARIO_CLUSTER_MEMORY:
        return None

    items = load_setup_outcomes()
    current_item = items.get(setup_id)

    if not current_item:
        return None

    matches, cluster_key = _cluster_matches(current_item, items)

    if not cluster_key:
        return None

    stats = build_similarity_stats(matches)

    if not stats:
        return None

    classification = classify_cluster(stats)

    return {
        "setup_id": setup_id,
        "classification": classification,
        "cluster_key": cluster_key,
        "nearby_strategies": current_item.get("nearby_strategies", []),
        "strategy": current_item.get("strategy"),
        "signal": current_item.get("signal"),
        "entry_model": current_item.get("entry_model"),
        "session": current_item.get("session"),
        "market_condition": current_item.get("market_condition"),
        "time_window": current_item.get("time_window"),
        "score": current_item.get("score"),
        "stats": stats,
    }


def notify_scenario_cluster_if_relevant(setup_id):
    if not ENABLE_SCENARIO_CLUSTER_MEMORY:
        return False

    if already_alerted(setup_id):
        return False

    report = analyze_scenario_cluster(setup_id)

    if not report:
        return False

    classification = report.get("classification")

    if classification == "LOW_SAMPLE":
        return False

    stats = report.get("stats", {})

    mark_alerted(setup_id, report)

    if classification == "FAVORABLE_CLUSTER_PATTERN":
        title = "🧠 Favorable Scenario Cluster"
    elif classification == "DANGEROUS_CLUSTER_PATTERN":
        title = "⚠️ Dangerous Scenario Cluster"
    else:
        title = "🧠 Scenario Cluster Memory"

    send_telegram_message(
        f"{title}\n"
        f"Setup ID: {setup_id}\n"
        f"Strategy: {report.get('strategy')}\n"
        f"Signal: {report.get('signal')}\n"
        f"Session: {report.get('session')}\n"
        f"Market: {report.get('market_condition')}\n"
        f"Time Window: {report.get('time_window')}\n\n"
        f"Cluster Strategies: {report.get('nearby_strategies')}\n\n"
        f"Similar Clusters: {stats.get('total')}\n"
        f"W10: {stats.get('w10_count')} / {stats.get('total')} "
        f"({round(stats.get('w10_rate', 0) * 100, 1)}%)\n"
        f"TP Touch: {stats.get('tp_count')} / {stats.get('total')}\n"
        f"SL Touch: {stats.get('sl_count')} / {stats.get('total')} "
        f"({round(stats.get('sl_rate', 0) * 100, 1)}%)\n"
        f"Avg Favorable: {stats.get('avg_favorable')}\n"
        f"Avg Adverse: {stats.get('avg_adverse')}\n\n"
        f"Cluster Key: {report.get('cluster_key')}"
    )

    logger.info(
        f"[SCENARIO CLUSTER] Alert sent | "
        f"setup_id={setup_id} classification={classification} stats={stats}"
    )

    return True

def get_scenario_cluster_score_adjustment(setup_id):
    if not ENABLE_SCENARIO_CLUSTER_SCORING:
        return 0, [], None

    report = analyze_scenario_cluster(setup_id)

    if not report:
        return 0, [], None

    classification = report.get("classification")
    stats = report.get("stats", {})

    if classification == "FAVORABLE_CLUSTER_PATTERN":
        adjustment = SCENARIO_CLUSTER_FAVORABLE_SCORE_BOOST

    elif classification == "DANGEROUS_CLUSTER_PATTERN":
        adjustment = -abs(SCENARIO_CLUSTER_DANGEROUS_SCORE_PENALTY)

    elif classification == "NEUTRAL_CLUSTER_PATTERN":
        adjustment = SCENARIO_CLUSTER_NEUTRAL_SCORE_BOOST

    else:
        adjustment = 0

    if adjustment == 0:
        return 0, [], report

    reasons = [
        (
            f"scenario_cluster_{classification.lower()} "
            f"samples={stats.get('total')} "
            f"w10_rate={stats.get('w10_rate')} "
            f"sl_rate={stats.get('sl_rate')} "
            f"adjustment={adjustment}"
        )
    ]

    return adjustment, reasons, report