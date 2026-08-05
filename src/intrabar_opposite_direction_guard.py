from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


BUY = "BUY"
SELL = "SELL"


DEFAULT_INTRABAR_BLOCK_SOURCES = (
    "INTRABAR",
    "ORB_TICK_WATCHER",
    "TICK_SNIPER",
    "SCALP_FALLBACK",
    "INTRABAR_STRUCTURAL_LEVEL_SCALP",
)


EXECUTION_ENGINE_ACTIVE_GETTERS = (
    ("WAIT_BETTER_ENTRY", "get_wait_better_entry_setups"),
    ("WAIT_TICK_SNIPER", "get_wait_tick_sniper_setups"),
    ("WAIT_DELAYED_ENTRY", "get_wait_delayed_entry_setups"),
    ("WAIT_ORB_TICK", "get_wait_orb_tick_breakout_setups"),
    ("WAIT_SPLIT_DELAYED", "get_wait_split_delayed_entry_setups"),
)


def normalize_signal(value: Any) -> Optional[str]:
    signal = str(value or "").strip().upper()
    if signal in {BUY, SELL}:
        return signal
    return None


def is_opposite_signal(left: Any, right: Any) -> bool:
    left_signal = normalize_signal(left)
    right_signal = normalize_signal(right)
    return bool(left_signal and right_signal and left_signal != right_signal)


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def merge_setup_payload(item: Any) -> Dict[str, Any]:
    item_dict = _as_dict(item)
    payload: Dict[str, Any] = {}

    for key in ("signal_data", "setup_data", "candidate", "trade_plan"):
        nested = _as_dict(item_dict.get(key))
        payload.update(nested)

    payload.update(item_dict)
    return payload


def is_intrabar_trade_plan(
    trade_plan: Any,
    block_sources: Optional[Iterable[str]] = None,
) -> bool:
    plan = _as_dict(trade_plan)

    if not plan:
        return False

    if bool(plan.get("intrabar_live_executor")):
        return True

    sources = tuple(str(item).upper() for item in (block_sources or DEFAULT_INTRABAR_BLOCK_SOURCES))

    source_bucket = str(
        plan.get("setup_source_bucket")
        or plan.get("source_bucket")
        or plan.get("bucket")
        or ""
    ).upper()

    market_condition = str(plan.get("market_condition") or "").upper()

    if source_bucket in sources:
        return True

    if "INTRABAR" in source_bucket:
        return True

    if "INTRABAR" in market_condition:
        return True

    return False


def _payload_is_intrabar(payload: Dict[str, Any]) -> bool:
    return is_intrabar_trade_plan(payload)


def iter_execution_engine_active_setups(execution_engine: Any) -> List[Dict[str, Any]]:
    if execution_engine is None:
        return []

    active: List[Dict[str, Any]] = []

    for source_name, getter_name in EXECUTION_ENGINE_ACTIVE_GETTERS:
        getter = getattr(execution_engine, getter_name, None)
        if not callable(getter):
            continue

        try:
            records = getter() or []
        except Exception:
            continue

        if isinstance(records, dict):
            iterable = records.values()
        else:
            iterable = records

        for item in iterable:
            payload = merge_setup_payload(item)
            signal = normalize_signal(payload.get("signal"))
            if not signal:
                continue

            active.append(
                {
                    "source": source_name,
                    "signal": signal,
                    "strategy": payload.get("strategy"),
                    "setup_id": payload.get("setup_id") or payload.get("id"),
                    "entry_model": payload.get("entry_model"),
                    "setup_source_bucket": payload.get("setup_source_bucket"),
                    "market_condition": payload.get("market_condition"),
                    "session": payload.get("session"),
                    "raw": payload,
                }
            )

    return active


def find_opposing_active_setup(
    *,
    signal: Any,
    setup_id: Any = None,
    execution_engine: Any = None,
    active_setups: Optional[Iterable[Any]] = None,
    ignore_intrabar_active_setups: bool = True,
) -> Optional[Dict[str, Any]]:
    candidate_signal = normalize_signal(signal)
    if not candidate_signal:
        return None

    current_setup_id = str(setup_id or "")

    if active_setups is None:
        candidates = iter_execution_engine_active_setups(execution_engine)
    else:
        candidates = [merge_setup_payload(item) for item in active_setups]

    for item in candidates:
        payload = merge_setup_payload(item)
        active_signal = normalize_signal(payload.get("signal"))

        if not active_signal:
            continue

        active_setup_id = str(payload.get("setup_id") or payload.get("id") or "")

        if current_setup_id and active_setup_id and current_setup_id == active_setup_id:
            continue

        if ignore_intrabar_active_setups and _payload_is_intrabar(payload):
            continue

        if is_opposite_signal(candidate_signal, active_signal):
            return {
                "source": payload.get("source"),
                "signal": active_signal,
                "strategy": payload.get("strategy"),
                "setup_id": active_setup_id or None,
                "entry_model": payload.get("entry_model"),
                "setup_source_bucket": payload.get("setup_source_bucket"),
                "market_condition": payload.get("market_condition"),
                "session": payload.get("session"),
            }

    return None


def evaluate_intrabar_opposite_direction_guard(
    *,
    signal: Any,
    trade_plan: Any,
    execution_engine: Any = None,
    active_setups: Optional[Iterable[Any]] = None,
    enabled: bool = True,
    block_sources: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    if not enabled:
        return {
            "allowed": True,
            "reason": "guard_disabled",
            "opposing_setup": None,
        }

    if not is_intrabar_trade_plan(trade_plan, block_sources=block_sources):
        return {
            "allowed": True,
            "reason": "not_intrabar_trade_plan",
            "opposing_setup": None,
        }

    plan = _as_dict(trade_plan)
    opposing_setup = find_opposing_active_setup(
        signal=signal,
        setup_id=plan.get("setup_id"),
        execution_engine=execution_engine,
        active_setups=active_setups,
        ignore_intrabar_active_setups=True,
    )

    if opposing_setup:
        return {
            "allowed": False,
            "reason": "intrabar_opposite_active_setup_blocked",
            "opposing_setup": opposing_setup,
        }

    return {
        "allowed": True,
        "reason": "no_opposing_active_setup",
        "opposing_setup": None,
    }
