import requests

from config.settings import (
    ENABLE_GOOGLE_SHEETS_LOGGING,
    GOOGLE_SHEETS_WEBHOOK_URL,
    GOOGLE_SHEETS_WEBHOOK_SECRET,
)
from src.logger import logger


def send_setup_event_to_google_sheets(event_data):
    if not ENABLE_GOOGLE_SHEETS_LOGGING:
        return False

    if not GOOGLE_SHEETS_WEBHOOK_URL:
        logger.info("[GOOGLE SHEETS] Webhook URL missing")
        return False

    payload = {
        "secret": GOOGLE_SHEETS_WEBHOOK_SECRET,
        "sheet": "Events",
        **event_data,
    }

    try:
        response = requests.post(
            GOOGLE_SHEETS_WEBHOOK_URL,
            json=payload,
            timeout=5,
        )

        if response.status_code != 200:
            logger.error(
                f"[GOOGLE SHEETS] HTTP {response.status_code}: {response.text}"
            )
            return False

        data = response.json()

        if not data.get("ok"):
            logger.error(f"[GOOGLE SHEETS] API error: {data}")
            return False

        logger.info("[GOOGLE SHEETS] Setup event logged")
        return True

    except Exception as e:
        logger.error(f"[GOOGLE SHEETS] Failed to send event: {e}")
        return False
    
def send_setup_outcome_to_google_sheets(item):
    if not ENABLE_GOOGLE_SHEETS_LOGGING:
        return False

    if not GOOGLE_SHEETS_WEBHOOK_URL:
        logger.info("[GOOGLE SHEETS] Webhook URL missing")
        return False

    payload = {
        "secret": GOOGLE_SHEETS_WEBHOOK_SECRET,
        "sheet": "SetupOutcomes",
        "action": "UPSERT",
        "key": "setup_id",
        "setup_id": item.get("setup_id"),
        "symbol": item.get("symbol"),
        "source_events": ",".join(item.get("source_events", [])),
        "strategy": item.get("strategy"),
        "signal": item.get("signal"),
        "entry_model": item.get("entry_model"),
        "session": item.get("session"),
        "market_condition": item.get("market_condition"),
        "score": item.get("score"),
        "entry": item.get("entry"),
        "sl": item.get("sl"),
        "tp": item.get("tp"),
        "max_favorable_usd": item.get("max_favorable_usd"),
        "max_adverse_usd": item.get("max_adverse_usd"),
        "max_favorable_after_max_adverse": item.get("max_favorable_after_max_adverse"),
        "hit_plus_10": item.get("hit_plus_10"),
        "hit_tp": item.get("hit_tp"),
        "hit_sl": item.get("hit_sl"),
        "first_hit": item.get("first_hit"),
        "final_outcome": item.get("final_outcome"),
        "status": item.get("status"),
        "context_key": item.get("context_key"),
        "scenario_key": item.get("scenario_key"),
        "nearby_strategies": ",".join(item.get("nearby_strategies", [])),
        "created_at": item.get("created_at"),
        "last_seen_at": item.get("last_seen_at"),
        "updated_at": item.get("updated_at"),
    }

    try:
        response = requests.post(
            GOOGLE_SHEETS_WEBHOOK_URL,
            json=payload,
            timeout=5,
        )

        if response.status_code != 200:
            logger.error(
                f"[GOOGLE SHEETS] Setup outcome HTTP {response.status_code}: {response.text}"
            )
            return False

        data = response.json()

        if not data.get("ok"):
            logger.error(f"[GOOGLE SHEETS] Setup outcome API error: {data}")
            return False

        logger.info("[GOOGLE SHEETS] Setup outcome upserted")
        return True

    except Exception as e:
        logger.error(f"[GOOGLE SHEETS] Failed to send setup outcome: {e}")
        return False