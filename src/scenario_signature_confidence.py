from config.settings import (
    ENABLE_SCENARIO_SIGNATURE_CONFIDENCE,
    SCENARIO_SIGNATURE_MIN_SAMPLES,
    SCENARIO_SIGNATURE_FAVORABLE_SCORE_BOOST,
    SCENARIO_SIGNATURE_DANGEROUS_SCORE_PENALTY,
    SCENARIO_SIGNATURE_NEUTRAL_SCORE_BOOST,
    SCENARIO_SIGNATURE_MIN_W10_RATE,
    SCENARIO_SIGNATURE_MAX_SL_RATE,
    SCENARIO_SIGNATURE_REQUIRE_MULTI_STRATEGY,
    SCENARIO_SIGNATURE_MIN_STRATEGIES,
)

from src.logger import logger
from src.setup_outcome_tracker import load_setup_outcomes
from src.setup_similarity_memory import build_similarity_stats


def _normalize_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        raw = value
    else:
        raw = str(value).split(",")

    cleaned = []

    for item in raw:
        key = str(item or "").strip().upper()

        if key and key not in cleaned:
            cleaned.append(key)

    return sorted(cleaned)


def _safe_text(value):
    return str(value or "").strip().upper()


def _detect_news_tag(item):
    text = " ".join([
        _safe_text(item.get("reason")),
        _safe_text(item.get("context_key")),
        _safe_text(item.get("scenario_key")),
        _safe_text(item.get("extra")),
    ])

    news_keywords = {
        "NFP": ["NFP", "NON FARM", "NONFARM", "PAYROLL"],
        "CPI": ["CPI", "INFLATION"],
        "FOMC": ["FOMC", "FED", "POWELL", "RATE DECISION", "INTEREST RATE"],
        "NEWS": ["NEWS", "HIGH_IMPACT", "BLACKOUT"],
    }

    for tag, keywords in news_keywords.items():
        for keyword in keywords:
            if keyword in text:
                return tag

    return "NO_NEWS_TAG"


def build_scenario_signature_keys(item):
    if not item:
        return []

    strategies = _normalize_list(item.get("nearby_strategies"))

    current_strategy = _safe_text(item.get("strategy"))

    if current_strategy and current_strategy not in strategies:
        strategies.append(current_strategy)

    strategies = sorted(strategies)

    if SCENARIO_SIGNATURE_REQUIRE_MULTI_STRATEGY:
        if len(strategies) < SCENARIO_SIGNATURE_MIN_STRATEGIES:
            return []

    combo = "+".join(strategies)

    symbol = _safe_text(item.get("symbol"))
    signal = _safe_text(item.get("signal"))
    session = _safe_text(item.get("session"))
    market_condition = _safe_text(item.get("market_condition"))
    day_of_week = _safe_text(item.get("day_of_week"))
    time_window = _safe_text(item.get("time_window"))
    entry_model = _safe_text(item.get("entry_model"))
    news_tag = _detect_news_tag(item)

    keys = [
        f"SIG_STRICT|{symbol}|{signal}|{session}|{market_condition}|{day_of_week}|{time_window}|{combo}",
        f"SIG_SESSION_MARKET|{symbol}|{signal}|{session}|{market_condition}|{combo}",
        f"SIG_SESSION|{symbol}|{signal}|{session}|{combo}",
        f"SIG_MARKET|{symbol}|{signal}|{market_condition}|{combo}",
        f"SIG_COMBO|{symbol}|{signal}|{combo}",
        f"SIG_ENTRY_MODEL|{symbol}|{signal}|{session}|{market_condition}|{entry_model}|{combo}",
    ]

    if news_tag != "NO_NEWS_TAG":
        keys.append(
            f"SIG_NEWS|{symbol}|{signal}|{news_tag}|{session}|{market_condition}|{combo}"
        )

    return keys


def _signature_matches(current_item, items):
    current_setup_id = current_item.get("setup_id")
    current_keys = build_scenario_signature_keys(current_item)

    if not current_keys:
        return [], None

    best_matches = []
    best_key = None

    for key in current_keys:
        matches = []

        for setup_id, item in items.items():
            if setup_id == current_setup_id:
                continue

            if item.get("status") == "TRACKING":
                continue

            item_keys = build_scenario_signature_keys(item)

            if key in item_keys:
                matches.append(item)

        if len(matches) > len(best_matches):
            best_matches = matches
            best_key = key

        if len(matches) >= SCENARIO_SIGNATURE_MIN_SAMPLES:
            return matches, key

    return best_matches, best_key


def classify_scenario_signature(stats):
    if not stats:
        return "NO_DATA"

    if stats.get("total", 0) < SCENARIO_SIGNATURE_MIN_SAMPLES:
        return "LOW_SAMPLE"

    if (
        stats.get("w10_rate", 0) >= SCENARIO_SIGNATURE_MIN_W10_RATE
        and stats.get("sl_rate", 0) <= SCENARIO_SIGNATURE_MAX_SL_RATE
    ):
        return "FAVORABLE_SCENARIO_SIGNATURE"

    if stats.get("sl_rate", 0) > SCENARIO_SIGNATURE_MAX_SL_RATE:
        return "DANGEROUS_SCENARIO_SIGNATURE"

    return "NEUTRAL_SCENARIO_SIGNATURE"


def analyze_scenario_signature(setup_id):
    if not ENABLE_SCENARIO_SIGNATURE_CONFIDENCE:
        return None

    items = load_setup_outcomes()
    current_item = items.get(setup_id)

    if not current_item:
        return None

    matches, signature_key = _signature_matches(current_item, items)

    if not signature_key:
        return None

    stats = build_similarity_stats(matches)

    if not stats:
        return None

    classification = classify_scenario_signature(stats)

    return {
        "setup_id": setup_id,
        "classification": classification,
        "signature_key": signature_key,
        "strategy": current_item.get("strategy"),
        "signal": current_item.get("signal"),
        "session": current_item.get("session"),
        "market_condition": current_item.get("market_condition"),
        "nearby_strategies": current_item.get("nearby_strategies"),
        "stats": stats,
    }


def get_scenario_signature_score_adjustment(setup_id):
    if not ENABLE_SCENARIO_SIGNATURE_CONFIDENCE:
        return 0, [], None

    report = analyze_scenario_signature(setup_id)

    if not report:
        return 0, [], None

    classification = report.get("classification")
    stats = report.get("stats", {})

    if classification == "FAVORABLE_SCENARIO_SIGNATURE":
        adjustment = SCENARIO_SIGNATURE_FAVORABLE_SCORE_BOOST

    elif classification == "DANGEROUS_SCENARIO_SIGNATURE":
        adjustment = -abs(SCENARIO_SIGNATURE_DANGEROUS_SCORE_PENALTY)

    elif classification == "NEUTRAL_SCENARIO_SIGNATURE":
        adjustment = SCENARIO_SIGNATURE_NEUTRAL_SCORE_BOOST

    else:
        adjustment = 0

    if adjustment == 0:
        return 0, [], report

    reasons = [
        (
            f"scenario_signature_{classification.lower()} "
            f"samples={stats.get('total')} "
            f"w10_rate={stats.get('w10_rate')} "
            f"tp_rate={stats.get('tp_rate')} "
            f"sl_rate={stats.get('sl_rate')} "
            f"adjustment={adjustment}"
        )
    ]

    logger.info(
        f"[SCENARIO SIGNATURE] "
        f"setup_id={setup_id} classification={classification} "
        f"adjustment={adjustment} stats={stats}"
    )

    return adjustment, reasons, report