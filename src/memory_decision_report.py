import json
from datetime import datetime

from config.settings import (
    ENABLE_MEMORY_DECISION_REPORT,
    MEMORY_DECISION_REPORT_MAX_ITEMS,
)
from src.account_context import get_account_file
from src.logger import logger


def get_memory_decision_report_file():
    return get_account_file("memory_decision_reports.json")


def load_memory_decision_reports():
    path = get_memory_decision_report_file()

    if not path.exists():
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[MEMORY DECISION REPORT] Failed to load: {e}")
        return []


def save_memory_decision_reports(items):
    path = get_memory_decision_report_file()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        if len(items) > MEMORY_DECISION_REPORT_MAX_ITEMS:
            items = items[-MEMORY_DECISION_REPORT_MAX_ITEMS:]

        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[MEMORY DECISION REPORT] Failed to save: {e}")


def build_memory_decision_report(
    *,
    setup_id,
    strategy,
    signal,
    score,
    session,
    market_condition,
    reason,
    signal_data=None,
    trade_plan=None,
    decision="OBSERVE",
    decision_reason=None,
):
    signal_data = signal_data or {}
    trade_plan = trade_plan or {}

    return {
        "created_at": datetime.now().isoformat(),
        "setup_id": setup_id,
        "strategy": strategy,
        "signal": signal,
        "score": score,
        "session": session,
        "market_condition": market_condition,
        "reason": reason,
        "decision": decision,
        "decision_reason": decision_reason,

        "entry_model": signal_data.get("entry_model"),
        "setup_news_tag": signal_data.get("news_tag"),
        "news_context": signal_data.get("news_context"),

        "entry": trade_plan.get("entry_price"),
        "sl": trade_plan.get("stop_loss"),
        "tp": trade_plan.get("take_profit"),
        "rr": trade_plan.get("rr") or trade_plan.get("risk_reward"),

        "memory": {
            "similarity": signal_data.get("similarity_memory"),
            "scenario_cluster": signal_data.get("scenario_cluster_memory"),
            "scenario_signature": signal_data.get("scenario_signature_memory"),
        },

        "adjustments": {
            "similarity_reasons": signal_data.get("similarity_reasons", []),
            "scenario_cluster_reasons": signal_data.get("scenario_cluster_reasons", []),
            "scenario_signature_reasons": signal_data.get("scenario_signature_reasons", []),
        },

        "context": {
            "nearby_strategies": signal_data.get("nearby_strategies"),
            "confluence_strategies": signal_data.get("confluence_strategies"),
            "top_candidates": signal_data.get("top_candidates"),
        },
    }


def save_memory_decision_report(report):
    if not ENABLE_MEMORY_DECISION_REPORT:
        return False

    if not report:
        return False

    items = load_memory_decision_reports()
    items.append(report)
    save_memory_decision_reports(items)

    logger.info(
        f"[MEMORY DECISION REPORT] Saved | "
        f"setup_id={report.get('setup_id')} decision={report.get('decision')}"
    )

    return True