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