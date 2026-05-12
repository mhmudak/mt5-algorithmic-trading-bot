import json
from datetime import datetime

from src.google_sheets_logger import send_setup_event_to_google_sheets
from src.account_context import get_account_file
from src.logger import logger

def get_setup_audit_file():
    return get_account_file("setup_audit.json")


def load_setup_audit():
    audit_file = get_setup_audit_file()

    if not audit_file.exists():
        return {}

    try:
        with open(audit_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[SETUP AUDIT] Failed to load audit file: {e}")
        return {}


def save_setup_audit(data):
    audit_file = get_setup_audit_file()

    try:
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        with open(audit_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[SETUP AUDIT] Failed to save audit file: {e}")


def log_setup_event(
    *,
    setup_id,
    event,
    strategy=None,
    signal=None,
    entry_model=None,
    score=None,
    session=None,
    market_condition=None,
    entry=None,
    sl=None,
    tp=None,
    rr=None,
    required_rr=None,
    reason=None,
    extra=None,
):
    if not setup_id:
        setup_id = "N/A"

    data = load_setup_audit()

    if setup_id not in data:
        data[setup_id] = {
            "setup_id": setup_id,
            "strategy": strategy,
            "signal": signal,
            "entry_model": entry_model,
            "score": score,
            "session": session,
            "market_condition": market_condition,
            "created_at": datetime.now().isoformat(),
            "latest_event": None,
            "events": [],
        }

    setup = data[setup_id]

    setup["latest_event"] = event
    setup["updated_at"] = datetime.now().isoformat()

    # Keep latest known values updated
    for key, value in {
        "strategy": strategy,
        "signal": signal,
        "entry_model": entry_model,
        "score": score,
        "session": session,
        "market_condition": market_condition,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rr": rr,
        "required_rr": required_rr,
        "reason": reason,
    }.items():
        if value is not None:
            setup[key] = value

    setup["events"].append(
        {
            "time": datetime.now().isoformat(),
            "event": event,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "rr": rr,
            "required_rr": required_rr,
            "reason": reason,
            "extra": extra or {},
        }
    )

    save_setup_audit(data)
    
    try:
        send_setup_event_to_google_sheets({
            "setup_id": setup_id,
            "event": event,
            "strategy": strategy,
            "signal": signal,
            "entry_model": entry_model,
            "score": score,
            "session": session,
            "market_condition": market_condition,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "rr": rr,
            "required_rr": required_rr,
            "reason": reason,
            "extra": extra or {},
        })
    except Exception as e:
        logger.error(f"[SETUP AUDIT] Google Sheets sync failed: {e}")