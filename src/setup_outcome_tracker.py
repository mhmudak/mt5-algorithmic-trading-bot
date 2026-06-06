import json
from datetime import datetime, timedelta

from config.settings import (
    ENABLE_SETUP_OUTCOME_TRACKER,
    SETUP_OUTCOME_EXPIRY_MINUTES,
    SETUP_OUTCOME_WIN_PRICE_MOVE,
    SETUP_OUTCOME_TRACK_EVENTS,
    SETUP_OUTCOME_SCENARIO_WINDOW_MINUTES,
    SETUP_OUTCOME_MIN_ADVERSE_FOR_REENTRY,
    SETUP_OUTCOME_REENTRY_PROFIT_TRIGGER,
)

from src.account_context import get_account_file
from src.logger import logger


def get_setup_outcomes_file():
    return get_account_file("setup_outcomes.json")


def load_setup_outcomes():
    path = get_setup_outcomes_file()

    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[SETUP OUTCOME] Failed to load file: {e}")
        return {}


def save_setup_outcomes(items):
    path = get_setup_outcomes_file()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[SETUP OUTCOME] Failed to save file: {e}")


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


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
    minute = dt.minute

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

    if hour >= 20:
        return "OFF_HOURS"

    return f"{hour:02d}:{minute:02d}"


def _scenario_bucket(dt):
    minutes = SETUP_OUTCOME_SCENARIO_WINDOW_MINUTES

    bucket_minute = (dt.minute // minutes) * minutes

    return dt.replace(
        minute=bucket_minute,
        second=0,
        microsecond=0,
    ).isoformat()


def build_context_key(item):
    parts = [
        item.get("strategy", "UNKNOWN"),
        item.get("signal", "NA"),
        item.get("entry_model", "NA"),
        item.get("session", "UNKNOWN"),
        item.get("market_condition", "UNKNOWN"),
        item.get("day_of_week", "UNKNOWN"),
        item.get("time_window", "UNKNOWN"),
        item.get("score_bucket", "SCORE_UNKNOWN"),
    ]

    return "|".join(str(part).upper() for part in parts)


def _build_scenario_key(symbol, dt):
    return f"{symbol}|{_scenario_bucket(dt)}"


def _get_nearby_strategies(items, scenario_key):
    strategies = []

    for item in items.values():
        if item.get("scenario_key") != scenario_key:
            continue

        strategy = item.get("strategy")

        if strategy and strategy not in strategies:
            strategies.append(strategy)

    return strategies


def register_setup_outcome(
    *,
    symbol,
    setup_id,
    event,
    strategy,
    signal,
    entry_model=None,
    score=None,
    session=None,
    market_condition=None,
    entry=None,
    sl=None,
    tp=None,
    reason=None,
    extra=None,
):
    if not ENABLE_SETUP_OUTCOME_TRACKER:
        return False

    if event not in SETUP_OUTCOME_TRACK_EVENTS:
        return False

    if not setup_id or setup_id == "N/A":
        return False

    if signal not in ["BUY", "SELL"]:
        return False

    entry = _safe_float(entry)
    sl = _safe_float(sl)
    tp = _safe_float(tp)

    if entry is None:
        return False

    items = load_setup_outcomes()

    now = datetime.now()
    scenario_key = _build_scenario_key(symbol, now)

    existing = items.get(setup_id)

    if existing:
        source_events = existing.get("source_events", [])

        if event not in source_events:
            source_events.append(event)

        existing["source_events"] = source_events
        existing["last_seen_at"] = now.isoformat()

        save_setup_outcomes(items)
        return True

    item = {
        "setup_id": setup_id,
        "symbol": symbol,
        "source_events": [event],
        "status": "TRACKING",
        "created_at": now.isoformat(),
        "last_seen_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=SETUP_OUTCOME_EXPIRY_MINUTES)).isoformat(),

        "strategy": strategy,
        "signal": signal,
        "entry_model": entry_model,
        "score": score,
        "score_bucket": _score_bucket(score),
        "session": session,
        "market_condition": market_condition,
        "day_of_week": now.strftime("%A").upper(),
        "time_window": _time_window(now),

        "entry": round(entry, 2),
        "sl": round(sl, 2) if sl is not None else None,
        "tp": round(tp, 2) if tp is not None else None,
        "reason": reason,
        "extra": extra or {},

        "context_key": None,
        "scenario_key": scenario_key,
        "nearby_strategies": [],

        "max_favorable_usd": 0.0,
        "max_adverse_usd": 0.0,

        "hit_plus_10": False,
        "hit_tp": False,
        "hit_sl": False,
        "first_hit": None,

        "time_to_plus_10_min": None,
        "time_to_tp_min": None,
        "time_to_sl_min": None,

        "max_adverse_seen": False,
        "max_favorable_after_max_adverse": 0.0,
        "recovered_from_adverse": False,
        "reentry_candidate_after_adverse": False,

        "final_outcome": None,
    }

    item["context_key"] = build_context_key(item)

    items[setup_id] = item

    nearby = _get_nearby_strategies(items, scenario_key)

    for stored_item in items.values():
        if stored_item.get("scenario_key") == scenario_key:
            stored_item["nearby_strategies"] = nearby

    save_setup_outcomes(items)

    logger.info(
        f"[SETUP OUTCOME] Registered | "
        f"setup_id={setup_id} strategy={strategy} signal={signal} "
        f"event={event} context={item['context_key']}"
    )

    return True


def _calculate_moves(item, tick):
    signal = item.get("signal")
    entry = float(item.get("entry"))

    if signal == "BUY":
        current_price = float(tick.bid)
        favorable = current_price - entry
        adverse = entry - current_price

    elif signal == "SELL":
        current_price = float(tick.ask)
        favorable = entry - current_price
        adverse = current_price - entry

    else:
        return None, None, None

    return round(current_price, 2), round(favorable, 2), round(adverse, 2)


def _minutes_since(created_at):
    try:
        created = datetime.fromisoformat(created_at)
        return round((datetime.now() - created).total_seconds() / 60, 2)
    except Exception:
        return None


def _mark_first_hit(item, hit_name):
    if item.get("first_hit") is None:
        item["first_hit"] = hit_name


def _check_tp_sl(item, current_price):
    signal = item.get("signal")
    sl = _safe_float(item.get("sl"))
    tp = _safe_float(item.get("tp"))

    hit_tp = False
    hit_sl = False

    if signal == "BUY":
        if tp is not None and current_price >= tp:
            hit_tp = True

        if sl is not None and current_price <= sl:
            hit_sl = True

    elif signal == "SELL":
        if tp is not None and current_price <= tp:
            hit_tp = True

        if sl is not None and current_price >= sl:
            hit_sl = True

    return hit_tp, hit_sl


def update_setup_outcomes(symbol, tick):
    if not ENABLE_SETUP_OUTCOME_TRACKER:
        return []

    items = load_setup_outcomes()

    if not items:
        return []

    changed = False
    milestones = []
    now = datetime.now()

    for setup_id, item in items.items():
        if item.get("symbol") != symbol:
            continue

        if item.get("status") != "TRACKING":
            continue

        try:
            expires_at = datetime.fromisoformat(item.get("expires_at"))
        except Exception:
            expires_at = now

        if now > expires_at:
            item["status"] = "EXPIRED"
            item["final_outcome"] = item.get("final_outcome") or "EXPIRED"
            changed = True
            continue

        current_price, favorable, adverse = _calculate_moves(item, tick)

        if current_price is None:
            continue

        previous_favorable = float(item.get("max_favorable_usd", 0.0))
        previous_adverse = float(item.get("max_adverse_usd", 0.0))

        if favorable > previous_favorable:
            item["max_favorable_usd"] = favorable
            changed = True

        if adverse > previous_adverse:
            item["max_adverse_usd"] = adverse
            item["max_adverse_seen"] = True
            changed = True

        if item.get("max_adverse_seen") and favorable > float(item.get("max_favorable_after_max_adverse", 0.0)):
            item["max_favorable_after_max_adverse"] = favorable
            changed = True

        if (
            item.get("max_adverse_usd", 0.0) >= SETUP_OUTCOME_MIN_ADVERSE_FOR_REENTRY
            and item.get("max_favorable_after_max_adverse", 0.0) >= SETUP_OUTCOME_REENTRY_PROFIT_TRIGGER
            and not item.get("reentry_candidate_after_adverse")
        ):
            item["recovered_from_adverse"] = True
            item["reentry_candidate_after_adverse"] = True
            changed = True

            milestones.append({
                "event": "SETUP_OUTCOME_REENTRY_CANDIDATE",
                "setup_id": setup_id,
                "item": item.copy(),
                "current_price": current_price,
                "favorable": favorable,
                "adverse": adverse,
            })

        if favorable >= SETUP_OUTCOME_WIN_PRICE_MOVE and not item.get("hit_plus_10"):
            item["hit_plus_10"] = True
            item["time_to_plus_10_min"] = _minutes_since(item.get("created_at"))
            item["final_outcome"] = item.get("final_outcome") or "W10"
            _mark_first_hit(item, "W10")
            changed = True

            milestones.append({
                "event": "SETUP_OUTCOME_W10",
                "setup_id": setup_id,
                "item": item.copy(),
                "current_price": current_price,
                "favorable": favorable,
                "adverse": adverse,
            })

        hit_tp, hit_sl = _check_tp_sl(item, current_price)

        if hit_tp and not item.get("hit_tp"):
            item["hit_tp"] = True
            item["time_to_tp_min"] = _minutes_since(item.get("created_at"))
            item["final_outcome"] = item.get("final_outcome") or "TP_TOUCH"
            _mark_first_hit(item, "TP_TOUCH")
            changed = True

            milestones.append({
                "event": "SETUP_OUTCOME_TP_TOUCH",
                "setup_id": setup_id,
                "item": item.copy(),
                "current_price": current_price,
                "favorable": favorable,
                "adverse": adverse,
            })

        if hit_sl and not item.get("hit_sl"):
            item["hit_sl"] = True
            item["time_to_sl_min"] = _minutes_since(item.get("created_at"))
            item["final_outcome"] = item.get("final_outcome") or "SL_TOUCH"
            _mark_first_hit(item, "SL_TOUCH")
            changed = True

            milestones.append({
                "event": "SETUP_OUTCOME_SL_TOUCH",
                "setup_id": setup_id,
                "item": item.copy(),
                "current_price": current_price,
                "favorable": favorable,
                "adverse": adverse,
            })

    if changed:
        save_setup_outcomes(items)

    return milestones