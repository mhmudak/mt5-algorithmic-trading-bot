from __future__ import annotations

from datetime import datetime
import json
import math
import time
from typing import Any

import MetaTrader5 as mt5

from config import settings as runtime_settings
from src.account_context import get_account_file
from src.logger import logger

STRATEGIES = {"INTRABAR_MICRO_MOMENTUM", "INTRABAR_STEP_TRAIL"}
SCHEMA_VERSION = 1
_PENDING: dict[str, dict[str, Any]] = {}
_ACTIVE: dict[str, dict[str, Any]] = {}
_RUNTIME_LOADED = False
_LAST_FLUSH_MONOTONIC = 0.0
_LAST_TICK_KEY: dict[str, tuple[Any, ...]] = {}


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _enabled() -> bool:
    return bool(getattr(runtime_settings, "ENABLE_INTRABAR_OPTIMIZATION_TELEMETRY", True))


def _runtime_path():
    return get_account_file("intrabar_optimization_runtime.json")


def _history_path():
    return get_account_file("intrabar_optimization_history.jsonl")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def _iso(epoch: float | None) -> str | None:
    if not epoch or epoch <= 0:
        return None
    try:
        return datetime.fromtimestamp(epoch).isoformat()
    except Exception:
        return None


def build_excursion_snapshot(*, signal: str, entry_price: float, current_price: float) -> dict[str, float]:
    side = str(signal or "").upper()
    entry = float(entry_price)
    current = float(current_price)
    signed = current - entry if side == "BUY" else entry - current if side == "SELL" else 0.0
    return {
        "signed_excursion": round(signed, 6),
        "favorable": round(max(0.0, signed), 6),
        "adverse": round(max(0.0, -signed), 6),
    }


def _features(setup: dict[str, Any]) -> dict[str, Any]:
    strategy = str(setup.get("strategy") or "").upper()
    extra = setup.get("extra") if isinstance(setup.get("extra"), dict) else {}
    if strategy == "INTRABAR_MICRO_MOMENTUM":
        keys = (
            "strength", "sample_count", "span_seconds", "net_move", "absolute_move",
            "velocity_price_per_sec", "signed_velocity_price_per_sec", "persistence",
            "acceleration_ratio", "spread", "micro_breakout", "sl_distance",
            "tp_distance", "runner_research_role",
        )
        out = {k: _json_safe(extra.get(k)) for k in keys if k in extra}
        if isinstance(extra.get("daily_level_context"), dict):
            out["daily_level_context"] = _json_safe(extra["daily_level_context"])
        return out
    if strategy == "INTRABAR_STEP_TRAIL":
        keys = (
            "impulse", "pullback", "resume", "quality", "span_seconds",
            "sample_count", "spread", "extreme", "retrace_extreme", "entry_reference",
        )
        out = {k: _json_safe(setup.get(k)) for k in keys if k in setup}
        impulse = _safe_float(setup.get("impulse"))
        pullback = _safe_float(setup.get("pullback"))
        resume = _safe_float(setup.get("resume"))
        if impulse and impulse > 0:
            if pullback is not None:
                out["pullback_to_impulse"] = round(pullback / impulse, 6)
            if resume is not None:
                out["resume_to_impulse"] = round(resume / impulse, 6)
        return out
    return {}


def build_candidate_context(setup: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(setup, dict):
        return None
    strategy = str(setup.get("strategy") or "").upper()
    setup_id = str(setup.get("setup_id") or "")
    if strategy not in STRATEGIES or not setup_id:
        return None
    detected = (
        _safe_float(setup.get("detected_ts"))
        or _safe_float(setup.get("observed_at_epoch"))
        or time.time()
    )
    entry_ref = _safe_float(
        setup.get("entry_reference")
        if setup.get("entry_reference") is not None
        else setup.get("entry")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "telemetry_only": True,
        "live_authority": False,
        "strategy": strategy,
        "setup_id": setup_id,
        "signal": str(setup.get("signal") or "").upper(),
        "entry_model": setup.get("entry_model"),
        "score": _safe_float(setup.get("score"), 0.0),
        "session": setup.get("session"),
        "market_condition": setup.get("market_condition"),
        "detected_at_epoch": detected,
        "detected_at": _iso(detected),
        "entry_reference": entry_ref,
        "detector_features": _features(setup),
    }


def register_intrabar_candidate_snapshot(setup: dict[str, Any]) -> bool:
    if not _enabled():
        return False
    context = build_candidate_context(setup)
    if not context:
        return False
    _PENDING[context["setup_id"]] = context
    if len(_PENDING) > 512:
        ordered = sorted(_PENDING, key=lambda k: float(_PENDING[k].get("detected_at_epoch") or 0.0))
        for key in ordered[:128]:
            _PENDING.pop(key, None)
    return True


def attach_pending_intrabar_context(tracked_trade: dict[str, Any], trade_plan: dict[str, Any]) -> bool:
    if not _enabled() or not isinstance(tracked_trade, dict) or not isinstance(trade_plan, dict):
        return False
    strategy = str(tracked_trade.get("strategy") or trade_plan.get("strategy") or "").upper()
    if strategy not in STRATEGIES:
        return False
    setup_id = str(tracked_trade.get("setup_id") or trade_plan.get("setup_id") or "")
    context = _PENDING.pop(setup_id, None) or {
        "schema_version": SCHEMA_VERSION,
        "telemetry_only": True,
        "live_authority": False,
        "strategy": strategy,
        "setup_id": setup_id,
        "signal": tracked_trade.get("signal"),
        "entry_model": tracked_trade.get("entry_model"),
        "score": tracked_trade.get("setup_score"),
        "session": tracked_trade.get("session"),
        "market_condition": tracked_trade.get("market_condition"),
        "detector_features": {},
    }
    context.update({
        "position_id": str(tracked_trade.get("position_id") or ""),
        "entry_price": _safe_float(tracked_trade.get("entry_price"), 0.0),
        "initial_stop_loss": _safe_float(tracked_trade.get("stop_loss"), 0.0),
        "original_take_profit": _safe_float(tracked_trade.get("take_profit"), 0.0),
        "lot": _safe_float(tracked_trade.get("initial_volume"), 0.0),
        "session": tracked_trade.get("session") or trade_plan.get("session") or context.get("session") or "UNKNOWN",
        "market_condition": tracked_trade.get("market_condition") or trade_plan.get("market_condition") or context.get("market_condition") or "UNKNOWN",
        "open_time": tracked_trade.get("open_time"),
    })
    context["runtime"] = {
        "sample_count": 0,
        "mfe_price": 0.0,
        "mae_price": 0.0,
        "spread_samples": 0,
        "spread_sum": 0.0,
        "average_spread": None,
        "max_spread": 0.0,
        "min_spread": None,
        "time_to_mfe_seconds": None,
        "time_to_mae_seconds": None,
        "profit_milestones": {},
        "max_locked_profit": 0.0,
        "step_trail_activation_at": None,
    }
    tracked_trade["intrabar_optimization"] = context
    tracked_trade["intrabar_optimization_schema_version"] = SCHEMA_VERSION
    return True


def _load_runtime_once() -> None:
    global _RUNTIME_LOADED
    if _RUNTIME_LOADED:
        return
    _RUNTIME_LOADED = True
    path = _runtime_path()
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    active = payload.get("active") if isinstance(payload, dict) else None
    if isinstance(active, dict):
        for key, value in active.items():
            if isinstance(value, dict):
                _ACTIVE[str(key)] = value


def _flush_runtime(force: bool = False) -> bool:
    global _LAST_FLUSH_MONOTONIC
    now = time.monotonic()
    interval = max(0.5, float(getattr(runtime_settings, "INTRABAR_OPTIMIZATION_PERSIST_SECONDS", 2.0)))
    if not force and now - _LAST_FLUSH_MONOTONIC < interval:
        return False
    try:
        path = _runtime_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(
                {"schema_version": SCHEMA_VERSION, "updated_at": datetime.now().isoformat(), "active": _json_safe(_ACTIVE)},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        tmp.replace(path)
        _LAST_FLUSH_MONOTONIC = now
        return True
    except Exception as exc:
        logger.warning(f"[INTRABAR OPTIMIZATION] runtime persistence failed open | error={exc}")
        return False


def _position_signal(position: Any) -> str:
    return "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"


def _position_price(position: Any, tick: Any) -> float:
    return float(tick.bid) if position.type == mt5.POSITION_TYPE_BUY else float(tick.ask)


def _opened_epoch(position: Any, trade: dict[str, Any]) -> float:
    value = _safe_float(getattr(position, "time", None))
    if value and value > 0:
        return value
    try:
        return datetime.fromisoformat(str(trade.get("open_time"))).timestamp()
    except Exception:
        return time.time()


def observe_intrabar_open_positions(*, symbol: str, tick: Any) -> int:
    if not _enabled() or tick is None:
        return 0
    key = (
        getattr(tick, "time_msc", None),
        round(float(getattr(tick, "bid", 0.0) or 0.0), 6),
        round(float(getattr(tick, "ask", 0.0) or 0.0), 6),
    )
    if _LAST_TICK_KEY.get(symbol) == key:
        return 0
    _LAST_TICK_KEY[symbol] = key
    _load_runtime_once()
    try:
        from src.trade_tracker import load_trades
        trades = load_trades()
    except Exception:
        return 0
    positions = mt5.positions_get(symbol=symbol)
    if not isinstance(trades, dict) or positions is None:
        return 0
    positions_map = {str(p.ticket): p for p in positions}
    tmsc = _safe_float(getattr(tick, "time_msc", None), 0.0) or 0.0
    now_epoch = tmsc / 1000.0 if tmsc > 0 else (_safe_float(getattr(tick, "time", None), time.time()) or time.time())
    spread = max(0.0, float(tick.ask) - float(tick.bid))
    count = 0

    for position_id, trade in trades.items():
        if not isinstance(trade, dict) or str(trade.get("status") or "OPEN").upper() != "OPEN":
            continue
        strategy = str(trade.get("strategy") or "").upper()
        if strategy not in STRATEGIES:
            continue
        position = positions_map.get(str(position_id))
        if position is None:
            continue

        signal = _position_signal(position)
        entry = float(position.price_open)
        current = _position_price(position, tick)
        ex = build_excursion_snapshot(signal=signal, entry_price=entry, current_price=current)

        state = _ACTIVE.get(str(position_id))
        if not isinstance(state, dict):
            base = trade.get("intrabar_optimization")
            state = dict(base) if isinstance(base, dict) else {
                "schema_version": SCHEMA_VERSION,
                "telemetry_only": True,
                "live_authority": False,
                "strategy": strategy,
                "setup_id": trade.get("setup_id"),
                "signal": signal,
                "entry_model": trade.get("entry_model"),
                "session": trade.get("session"),
                "market_condition": trade.get("market_condition"),
                "entry_price": entry,
                "detector_features": {},
            }
            state["runtime"] = dict(state.get("runtime") or {})
            _ACTIVE[str(position_id)] = state

        runtime = state.setdefault("runtime", {})
        opened = _safe_float(runtime.get("opened_epoch"), _opened_epoch(position, trade)) or now_epoch
        runtime["opened_epoch"] = opened
        runtime["sample_count"] = int(runtime.get("sample_count", 0) or 0) + 1
        runtime["current_price"] = round(current, 6)
        runtime["current_signed_excursion"] = ex["signed_excursion"]
        runtime["last_observed_at"] = _iso(now_epoch)

        old_mfe = float(runtime.get("mfe_price", 0.0) or 0.0)
        old_mae = float(runtime.get("mae_price", 0.0) or 0.0)
        if ex["favorable"] > old_mfe + 1e-9:
            runtime["mfe_price"] = ex["favorable"]
            runtime["time_to_mfe_seconds"] = round(max(0.0, now_epoch - opened), 3)
            runtime["mfe_reached_at"] = _iso(now_epoch)
            runtime["best_price"] = round(current, 6)
        else:
            runtime["mfe_price"] = round(old_mfe, 6)
        if ex["adverse"] > old_mae + 1e-9:
            runtime["mae_price"] = ex["adverse"]
            runtime["time_to_mae_seconds"] = round(max(0.0, now_epoch - opened), 3)
            runtime["mae_reached_at"] = _iso(now_epoch)
            runtime["worst_price"] = round(current, 6)
        else:
            runtime["mae_price"] = round(old_mae, 6)

        runtime["spread_samples"] = int(runtime.get("spread_samples", 0) or 0) + 1
        runtime["spread_sum"] = round(float(runtime.get("spread_sum", 0.0) or 0.0) + spread, 8)
        runtime["average_spread"] = round(runtime["spread_sum"] / runtime["spread_samples"], 6)
        runtime["max_spread"] = round(max(float(runtime.get("max_spread", 0.0) or 0.0), spread), 6)
        prev_min = runtime.get("min_spread")
        runtime["min_spread"] = round(spread if prev_min is None else min(float(prev_min), spread), 6)

        stop = float(getattr(position, "sl", 0.0) or 0.0)
        locked = max(0.0, stop - entry) if signal == "BUY" and stop > 0 else max(0.0, entry - stop) if signal == "SELL" and stop > 0 else 0.0
        runtime["current_stop_loss"] = round(stop, 6)
        runtime["max_locked_profit"] = round(max(float(runtime.get("max_locked_profit", 0.0) or 0.0), locked), 6)

        milestones = runtime.setdefault("profit_milestones", {})
        for threshold in (0.10, 0.30, 0.60, 1.00, 1.50, 2.00):
            name = f"{threshold:.2f}"
            if ex["favorable"] + 1e-9 >= threshold and name not in milestones:
                milestones[name] = {
                    "reached_at": _iso(now_epoch),
                    "seconds_from_open": round(max(0.0, now_epoch - opened), 3),
                }

        if strategy == "INTRABAR_STEP_TRAIL":
            activation = float(getattr(runtime_settings, "INTRABAR_STEP_TRAIL_ACTIVATION_PROFIT", 0.60))
            if ex["favorable"] + 1e-9 >= activation and not runtime.get("step_trail_activation_at"):
                runtime["step_trail_activation_at"] = _iso(now_epoch)
                runtime["step_trail_activation_seconds"] = round(max(0.0, now_epoch - opened), 3)

        if strategy == "INTRABAR_MICRO_MOMENTUM":
            if trade.get("micro_momentum_be_applied") and not runtime.get("micro_be_observed_at"):
                runtime["micro_be_observed_at"] = _iso(now_epoch)
                runtime["micro_be_observed_seconds"] = round(max(0.0, now_epoch - opened), 3)
            if trade.get("runner_mode_active"):
                runtime["low_mae_runner_activated"] = True

        count += 1

    if count:
        _flush_runtime(False)
    return count


def finalize_intrabar_optimization_trade(*, position_id: Any, trade: dict[str, Any], close_details: dict[str, Any]) -> bool:
    if not _enabled() or not isinstance(trade, dict):
        return False
    strategy = str(trade.get("strategy") or "").upper()
    if strategy not in STRATEGIES:
        return False
    if trade.get("intrabar_optimization_history_written"):
        return True

    _load_runtime_once()
    key = str(position_id)
    state = _ACTIVE.get(key)
    if not isinstance(state, dict):
        existing = trade.get("intrabar_optimization")
        state = dict(existing) if isinstance(existing, dict) else {
            "schema_version": SCHEMA_VERSION,
            "telemetry_only": True,
            "live_authority": False,
            "strategy": strategy,
            "setup_id": trade.get("setup_id"),
            "signal": trade.get("signal"),
            "entry_model": trade.get("entry_model"),
            "session": trade.get("session"),
            "market_condition": trade.get("market_condition"),
            "entry_price": trade.get("entry_price"),
            "detector_features": {},
            "runtime": {},
        }

    state["position_id"] = key
    state["final_result"] = trade.get("final_result")
    state["close_reason"] = close_details.get("close_reason")
    state["realized_profit"] = close_details.get("realized_profit")
    state["close_price"] = close_details.get("close_price")
    state["close_time"] = close_details.get("close_time") or datetime.now().isoformat()
    state["session"] = trade.get("session") or state.get("session")
    state["market_condition"] = trade.get("market_condition") or state.get("market_condition")

    runtime = state.setdefault("runtime", {})
    close_price = _safe_float(close_details.get("close_price"), 0.0) or 0.0
    entry = _safe_float(trade.get("entry_price"), 0.0) or 0.0
    if close_price > 0 and entry > 0:
        ex = build_excursion_snapshot(signal=str(trade.get("signal") or ""), entry_price=entry, current_price=close_price)
        runtime["mfe_price"] = round(max(float(runtime.get("mfe_price", 0.0) or 0.0), ex["favorable"]), 6)
        runtime["mae_price"] = round(max(float(runtime.get("mae_price", 0.0) or 0.0), ex["adverse"]), 6)
        runtime["final_signed_excursion"] = ex["signed_excursion"]

    if trade.get("micro_momentum_be_applied"):
        runtime["micro_be_applied"] = True
    if trade.get("micro_momentum_profit_capture_applied"):
        runtime["micro_profit_capture_applied"] = True
    if trade.get("runner_mode_active"):
        runtime["low_mae_runner_activated"] = True

    try:
        opened = datetime.fromisoformat(str(trade.get("open_time")))
        closed = datetime.fromisoformat(str(state["close_time"]))
        runtime["hold_seconds"] = round(max(0.0, (closed - opened).total_seconds()), 3)
    except Exception:
        pass

    trade["intrabar_optimization"] = state

    try:
        path = _history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(_json_safe({"position_id": key, **state}), sort_keys=True, separators=(",", ":")) + "\n")
        trade["intrabar_optimization_history_written"] = True
    except Exception as exc:
        logger.warning(f"[INTRABAR OPTIMIZATION] history append failed open | position={key} error={exc}")
        return False

    _ACTIVE.pop(key, None)
    _flush_runtime(True)
    return True

def note_intrabar_management_event(
    *,
    position_id: Any,
    event: str,
    details: dict[str, Any] | None = None,
) -> bool:
    # TELEMETRY ONLY: no entry/exit/SL/TP/risk authority.
    if not _enabled():
        return False

    try:
        _load_runtime_once()

        key = str(position_id)
        state = _ACTIVE.setdefault(
            key,
            {
                "schema_version": SCHEMA_VERSION,
                "telemetry_only": True,
                "live_authority": False,
                "position_id": key,
                "runtime": {},
            },
        )
        runtime = state.setdefault("runtime", {})
        event_name = str(event or "UNKNOWN")
        raw_details = details if isinstance(details, dict) else {}
        safe_details = _json_safe(raw_details)

        events = runtime.setdefault("management_events", [])
        events.append(
            {
                "event": event_name,
                "observed_at": datetime.now().isoformat(),
                "details": safe_details,
            }
        )
        if len(events) > 64:
            del events[:-64]

        if event_name == "STEP_TRAIL_SL_ADVANCED":
            stage = raw_details.get("stage")
            if stage is not None:
                runtime["highest_step_trail_stage"] = str(stage)

            mfe = _safe_float(raw_details.get("mfe"))
            if mfe is not None:
                runtime["last_step_trail_mfe"] = round(mfe, 6)

            desired_stop = _safe_float(
                raw_details.get("desired_stop")
            )
            if desired_stop is not None:
                runtime["last_step_trail_desired_stop"] = round(
                    desired_stop,
                    6,
                )

        elif event_name == "STEP_TRAIL_EARLY_FAILURE_EXIT":
            runtime["step_trail_early_failure_exit"] = True
            runtime["step_trail_early_failure_at"] = (
                datetime.now().isoformat()
            )
            runtime["step_trail_early_failure_reason"] = (
                raw_details.get("reason")
            )

            adverse = _safe_float(raw_details.get("adverse"))
            if adverse is not None:
                runtime["step_trail_early_failure_adverse"] = round(
                    adverse,
                    6,
                )

            recent_move = _safe_float(
                raw_details.get("recent_move")
            )
            if recent_move is not None:
                runtime[
                    "step_trail_early_failure_recent_move"
                ] = round(recent_move, 6)

        _flush_runtime(force=True)
        return True

    except Exception as exc:
        logger.warning(
            "[INTRABAR OPTIMIZATION] management-event capture "
            f"failed open | position={position_id} "
            f"event={event} error={exc}"
        )
        return False
