from __future__ import annotations

from datetime import datetime
import math
from typing import Any

import MetaTrader5 as mt5

from src.logger import logger
from src.trade_tracker import load_trades, save_trades


STRATEGY = "INTRABAR_MICRO_MOMENTUM"
RUNNER_POLICY = "LOW_MAE_MOMENTUM_RUNNER_V1"

_STATES: dict[str, dict[str, Any]] = {}
_REHYDRATED = False


def _setting(name: str, default: Any) -> Any:
    try:
        from config import settings
        return getattr(settings, name, default)
    except Exception:
        return default


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        value = float(value)
        return value if math.isfinite(value) else None
    except Exception:
        return None


def _notify(message: str) -> None:
    try:
        from src.notifier import send_telegram_message
        send_telegram_message(message)
    except Exception as exc:
        logger.warning(
            "[LOW MAE RUNNER] Telegram notification failed open "
            f"| error={exc}"
        )


def reset_low_mae_runner_state() -> None:
    global _REHYDRATED
    _STATES.clear()
    _REHYDRATED = False


def evaluate_low_mae_runner_snapshot(
    *,
    risk_distance: float,
    current_favorable: float,
    max_favorable: float,
    max_adverse: float,
    sample_count: int,
    spread: float,
    trigger_r: float = 1.50,
    max_mae_r: float = 0.50,
    min_efficiency: float = 3.0,
    min_samples: int = 4,
    max_spread: float = 0.20,
) -> dict[str, Any]:
    risk = float(risk_distance)
    if risk <= 0:
        return {"qualified": False, "reason": "invalid_risk"}

    current_favorable = max(0.0, float(current_favorable))
    max_favorable = max(0.0, float(max_favorable))
    max_adverse = max(0.0, float(max_adverse))
    spread = max(0.0, float(spread))
    sample_count = int(sample_count)

    current_r = current_favorable / risk
    mfe_r = max_favorable / risk
    mae_r = max_adverse / risk
    efficiency = max_favorable / max(max_adverse, 0.01)

    qualified = (
        sample_count >= int(min_samples)
        and spread <= float(max_spread)
        and current_r >= float(trigger_r)
        and mae_r <= float(max_mae_r)
        and efficiency >= float(min_efficiency)
    )

    if sample_count < int(min_samples):
        reason = "insufficient_samples"
    elif spread > float(max_spread):
        reason = "spread_too_wide"
    elif current_r < float(trigger_r):
        reason = "favorable_expansion_not_reached"
    elif mae_r > float(max_mae_r):
        reason = "mae_too_high"
    elif efficiency < float(min_efficiency):
        reason = "efficiency_too_low"
    else:
        reason = "qualified"

    return {
        "qualified": bool(qualified),
        "reason": reason,
        "current_r": round(current_r, 6),
        "mfe_r": round(mfe_r, 6),
        "mae_r": round(mae_r, 6),
        "efficiency": round(efficiency, 6),
        "sample_count": sample_count,
        "spread": round(spread, 6),
    }


def build_runner_levels(
    *,
    signal: str,
    entry_price: float,
    risk_distance: float,
    lock_r: float,
    target_price_distance: float = 2.0,
) -> dict[str, float]:
    signal = str(signal or "").upper()
    entry = float(entry_price)
    risk = float(risk_distance)
    lock_distance = risk * float(lock_r)
    target_distance = min(2.0, max(0.0, float(target_price_distance)))

    if signal == "BUY":
        sl = entry + lock_distance
        tp = entry + target_distance
    elif signal == "SELL":
        sl = entry - lock_distance
        tp = entry - target_distance
    else:
        raise ValueError(f"Unsupported signal: {signal}")

    return {
        "sl": round(sl, 2),
        "tp": round(tp, 2),
        "lock_distance": round(lock_distance, 6),
        "target_distance": round(target_distance, 6),
    }


def _position_map(symbol: str) -> dict[str, Any] | None:
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return None
    return {str(position.ticket): position for position in positions}


def _select_trade_for_setup(
    trades: dict[str, Any],
    setup_id: str,
) -> tuple[str, dict[str, Any]] | tuple[None, None]:
    matches = []
    for position_id, trade in trades.items():
        if not isinstance(trade, dict):
            continue
        if trade.get("setup_id") != setup_id:
            continue
        if str(trade.get("strategy") or "").upper() != STRATEGY:
            continue
        if str(trade.get("status") or "").upper() != "OPEN":
            continue
        matches.append((position_id, trade))

    if not matches:
        return None, None

    return matches[-1]


def register_low_mae_momentum_trade(
    *,
    symbol: str,
    setup_id: str,
    signal: str,
    fallback_risk_distance: float,
    strength: str | None = None,
) -> bool:
    if not bool(_setting("ENABLE_LOW_MAE_MOMENTUM_RUNNER_LIVE", True)):
        return False

    trades = load_trades()
    if not isinstance(trades, dict):
        return False

    position_id, trade = _select_trade_for_setup(trades, setup_id)
    if not position_id or not trade:
        logger.warning(
            "[LOW MAE RUNNER] Registration missed "
            f"| setup_id={setup_id} reason=tracked_trade_not_found"
        )
        return False

    positions = _position_map(symbol)
    if positions is None:
        return False

    position = positions.get(str(position_id))

    entry = (
        float(position.price_open)
        if position is not None
        else _safe_float(trade.get("entry_price"))
    )
    if entry is None:
        return False

    position_sl = (
        _safe_float(position.sl)
        if position is not None
        else _safe_float(trade.get("stop_loss"))
    )
    position_tp = (
        _safe_float(position.tp)
        if position is not None
        else _safe_float(trade.get("take_profit"))
    )

    risk = (
        abs(entry - position_sl)
        if position_sl not in (None, 0.0)
        else float(fallback_risk_distance)
    )
    if risk <= 0:
        return False

    state = {
        "position_id": str(position_id),
        "setup_id": setup_id,
        "symbol": symbol,
        "signal": str(signal or "").upper(),
        "entry_price": float(entry),
        "risk_distance": float(risk),
        "original_tp": position_tp,
        "strength": str(strength or "UNKNOWN"),
        "sample_count": 0,
        "max_favorable": 0.0,
        "max_adverse": 0.0,
        "promoted": False,
        "lock_stage": 0,
        "registered_at": datetime.now().isoformat(),
        "rehydrated": False,
    }

    _STATES[str(position_id)] = state

    trade["low_mae_runner_registered"] = True
    trade["low_mae_runner_policy"] = RUNNER_POLICY
    trade["low_mae_runner_active"] = False
    trade["low_mae_runner_strength"] = state["strength"]
    trade["low_mae_runner_risk_distance"] = round(risk, 6)
    trade["low_mae_runner_registered_at"] = state["registered_at"]
    save_trades(trades)

    logger.info(
        "[LOW MAE RUNNER] Registered "
        f"| position={position_id} setup_id={setup_id} "
        f"signal={state['signal']} risk={round(risk, 4)} "
        f"strength={state['strength']}"
    )
    return True


def _rehydrate_active_runner_states(symbol: str) -> None:
    global _REHYDRATED

    if _REHYDRATED:
        return

    _REHYDRATED = True

    try:
        trades = load_trades()
        if not isinstance(trades, dict):
            return

        positions = _position_map(symbol)
        if positions is None:
            return

        for position_id, trade in trades.items():
            if not isinstance(trade, dict):
                continue
            if str(trade.get("strategy") or "").upper() != STRATEGY:
                continue
            if str(trade.get("status") or "").upper() != "OPEN":
                continue
            if trade.get("low_mae_runner_active") is not True:
                continue

            position = positions.get(str(position_id))
            if position is None:
                continue

            risk = _safe_float(trade.get("low_mae_runner_risk_distance"))
            if risk is None or risk <= 0:
                continue

            _STATES[str(position_id)] = {
                "position_id": str(position_id),
                "setup_id": trade.get("setup_id"),
                "symbol": symbol,
                "signal": str(trade.get("signal") or "").upper(),
                "entry_price": float(position.price_open),
                "risk_distance": float(risk),
                "original_tp": _safe_float(trade.get("take_profit")),
                "strength": str(
                    trade.get("low_mae_runner_strength") or "UNKNOWN"
                ),
                "sample_count": int(
                    trade.get("low_mae_runner_sample_count") or 0
                ),
                "max_favorable": float(
                    trade.get("low_mae_runner_max_favorable") or 0.0
                ),
                "max_adverse": float(
                    trade.get("low_mae_runner_max_adverse") or 0.0
                ),
                "promoted": True,
                "lock_stage": int(
                    trade.get("low_mae_runner_lock_stage") or 1
                ),
                "registered_at": trade.get(
                    "low_mae_runner_registered_at"
                ),
                "rehydrated": True,
            }

            logger.info(
                "[LOW MAE RUNNER] Rehydrated active runner "
                f"| position={position_id} "
                f"stage={_STATES[str(position_id)]['lock_stage']}"
            )
    except Exception as exc:
        logger.warning(
            "[LOW MAE RUNNER] Rehydrate failed open "
            f"| error={exc}"
        )


def _persist_runner_state(
    state: dict[str, Any],
    *,
    current_sl: float | None = None,
    current_tp: float | None = None,
) -> None:
    try:
        trades = load_trades()
        if not isinstance(trades, dict):
            return

        trade = trades.get(str(state["position_id"]))
        if not isinstance(trade, dict):
            return

        risk = float(state["risk_distance"])
        max_favorable = float(state["max_favorable"])
        max_adverse = float(state["max_adverse"])

        trade["low_mae_runner_registered"] = True
        trade["low_mae_runner_policy"] = RUNNER_POLICY
        trade["low_mae_runner_active"] = bool(state["promoted"])
        trade["low_mae_runner_lock_stage"] = int(state["lock_stage"])
        trade["low_mae_runner_sample_count"] = int(state["sample_count"])
        trade["low_mae_runner_max_favorable"] = round(max_favorable, 4)
        trade["low_mae_runner_max_adverse"] = round(max_adverse, 4)
        trade["low_mae_runner_mfe_r"] = round(max_favorable / risk, 4)
        trade["low_mae_runner_mae_r"] = round(max_adverse / risk, 4)
        trade["low_mae_runner_efficiency"] = round(
            max_favorable / max(max_adverse, 0.01),
            4,
        )

        if state.get("promoted_at"):
            trade["low_mae_runner_promoted_at"] = state["promoted_at"]

        if current_sl is not None:
            trade["low_mae_runner_current_sl"] = round(
                float(current_sl),
                2,
            )
        if current_tp is not None:
            trade["low_mae_runner_current_tp"] = round(
                float(current_tp),
                2,
            )

        save_trades(trades)
    except Exception as exc:
        logger.warning(
            "[LOW MAE RUNNER] State persistence failed open "
            f"| position={state.get('position_id')} error={exc}"
        )


def _modify_runner_levels(
    *,
    position: Any,
    signal: str,
    desired_sl: float,
    desired_tp: float,
    reason: str,
) -> bool:
    current_sl = _safe_float(position.sl) or 0.0

    if signal == "BUY":
        effective_sl = max(current_sl, float(desired_sl))
    else:
        effective_sl = (
            float(desired_sl)
            if current_sl <= 0
            else min(current_sl, float(desired_sl))
        )

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": position.ticket,
        "sl": round(effective_sl, 2),
        "tp": round(float(desired_tp), 2),
    }

    result = mt5.order_send(request)

    if result is None:
        logger.error(
            "[LOW MAE RUNNER] SL/TP modification failed "
            f"| position={position.ticket} error={mt5.last_error()}"
        )
        return False

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(
            "[LOW MAE RUNNER] SL/TP modification rejected "
            f"| position={position.ticket} result={result}"
        )
        return False

    logger.warning(
        "[LOW MAE RUNNER] "
        f"{reason} | position={position.ticket} "
        f"new_sl={round(effective_sl, 2)} "
        f"new_tp={round(float(desired_tp), 2)}"
    )
    return True


def _promote_runner(
    *,
    state: dict[str, Any],
    position: Any,
    snapshot: dict[str, Any],
) -> bool:
    risk = float(state["risk_distance"])
    signal = state["signal"]
    entry = float(position.price_open)

    levels = build_runner_levels(
        signal=signal,
        entry_price=entry,
        risk_distance=risk,
        lock_r=float(
            _setting("LOW_MAE_RUNNER_INITIAL_LOCK_R", 0.50)
        ),
        target_price_distance=float(
            _setting("LOW_MAE_RUNNER_TARGET_PRICE", 2.00)
        ),
    )

    if signal == "BUY" and float(position.price_current) >= levels["tp"]:
        return False
    if signal == "SELL" and float(position.price_current) <= levels["tp"]:
        return False

    if not _modify_runner_levels(
        position=position,
        signal=signal,
        desired_sl=levels["sl"],
        desired_tp=levels["tp"],
        reason="PROMOTED",
    ):
        return False

    state["promoted"] = True
    state["lock_stage"] = 1
    state["promoted_at"] = datetime.now().isoformat()

    _persist_runner_state(
        state,
        current_sl=levels["sl"],
        current_tp=levels["tp"],
    )

    logger.warning(
        "[LOW MAE RUNNER PROMOTED] "
        f"position={position.ticket} "
        f"setup_id={state.get('setup_id')} "
        f"signal={signal} "
        f"mfe_r={snapshot.get('mfe_r')} "
        f"mae_r={snapshot.get('mae_r')} "
        f"efficiency={snapshot.get('efficiency')} "
        f"lock_stage=1 target_distance={levels['target_distance']}"
    )

    _notify(
        f"🏃 Low-MAE Momentum Runner Promoted\n"
        f"Setup: {state.get('setup_id')}\n"
        f"Position: {position.ticket}\n"
        f"Signal: {signal}\n"
        f"MFE: {snapshot.get('mfe_r')}R\n"
        f"MAE: {snapshot.get('mae_r')}R\n"
        f"Efficiency: {snapshot.get('efficiency')}x\n"
        f"SL: {levels['sl']}\n"
        f"TP: {levels['tp']}"
    )
    return True


def _advance_runner_lock(
    *,
    state: dict[str, Any],
    position: Any,
    trigger_r: float,
    lock_r: float,
    stage: int,
) -> bool:
    levels = build_runner_levels(
        signal=state["signal"],
        entry_price=float(position.price_open),
        risk_distance=float(state["risk_distance"]),
        lock_r=lock_r,
        target_price_distance=float(
            _setting("LOW_MAE_RUNNER_TARGET_PRICE", 2.00)
        ),
    )

    if not _modify_runner_levels(
        position=position,
        signal=state["signal"],
        desired_sl=levels["sl"],
        desired_tp=levels["tp"],
        reason=f"LOCK_STAGE_{stage}",
    ):
        return False

    state["lock_stage"] = stage

    _persist_runner_state(
        state,
        current_sl=levels["sl"],
        current_tp=levels["tp"],
    )

    logger.warning(
        "[LOW MAE RUNNER LOCK] "
        f"position={position.ticket} "
        f"stage={stage} trigger={trigger_r}R "
        f"locked={lock_r}R sl={levels['sl']} tp={levels['tp']}"
    )
    return True


def manage_low_mae_momentum_runners(
    *,
    symbol: str,
    tick: Any,
) -> list[dict[str, Any]]:
    if not bool(_setting("ENABLE_LOW_MAE_MOMENTUM_RUNNER_LIVE", True)):
        return []

    _rehydrate_active_runner_states(symbol)

    if not _STATES:
        return []

    positions = _position_map(symbol)
    if positions is None:
        return []

    bid = _safe_float(getattr(tick, "bid", None))
    ask = _safe_float(getattr(tick, "ask", None))
    if bid is None or ask is None or ask < bid:
        return []

    spread = ask - bid
    max_spread = float(
        _setting("MICRO_MOMENTUM_SHADOW_MAX_SPREAD_PRICE", 0.20)
    )

    events = []

    for position_id in list(_STATES):
        state = _STATES.get(position_id)
        position = positions.get(position_id)

        if state is None:
            continue

        if position is None:
            _STATES.pop(position_id, None)
            continue

        signal = state["signal"]
        entry = float(position.price_open)
        risk = float(state["risk_distance"])

        if signal == "BUY":
            current_price = bid
            favorable = max(0.0, current_price - entry)
            adverse = max(0.0, entry - current_price)
        else:
            current_price = ask
            favorable = max(0.0, entry - current_price)
            adverse = max(0.0, current_price - entry)

        state["sample_count"] += 1
        state["max_favorable"] = max(
            float(state["max_favorable"]),
            favorable,
        )
        state["max_adverse"] = max(
            float(state["max_adverse"]),
            adverse,
        )

        current_r = favorable / risk if risk > 0 else 0.0

        if not state["promoted"]:
            snapshot = evaluate_low_mae_runner_snapshot(
                risk_distance=risk,
                current_favorable=favorable,
                max_favorable=state["max_favorable"],
                max_adverse=state["max_adverse"],
                sample_count=state["sample_count"],
                spread=spread,
                trigger_r=float(
                    _setting(
                        "LOW_MAE_RUNNER_PROMOTION_TRIGGER_R",
                        1.50,
                    )
                ),
                max_mae_r=float(
                    _setting("LOW_MAE_RUNNER_MAX_MAE_R", 0.50)
                ),
                min_efficiency=float(
                    _setting(
                        "LOW_MAE_RUNNER_MIN_EFFICIENCY",
                        3.0,
                    )
                ),
                min_samples=int(
                    _setting("LOW_MAE_RUNNER_MIN_SAMPLES", 4)
                ),
                max_spread=max_spread,
            )

            if snapshot["qualified"] and _promote_runner(
                state=state,
                position=position,
                snapshot=snapshot,
            ):
                events.append(
                    {
                        "event": "LOW_MAE_RUNNER_PROMOTED",
                        "position_id": position_id,
                        "setup_id": state.get("setup_id"),
                        **snapshot,
                    }
                )
            continue

        stage3_trigger = float(
            _setting("LOW_MAE_RUNNER_STAGE3_TRIGGER_R", 4.0)
        )
        stage3_lock = float(
            _setting("LOW_MAE_RUNNER_STAGE3_LOCK_R", 2.5)
        )
        stage2_trigger = float(
            _setting("LOW_MAE_RUNNER_STAGE2_TRIGGER_R", 3.0)
        )
        stage2_lock = float(
            _setting("LOW_MAE_RUNNER_STAGE2_LOCK_R", 1.5)
        )

        if state["lock_stage"] < 3 and current_r >= stage3_trigger:
            if _advance_runner_lock(
                state=state,
                position=position,
                trigger_r=stage3_trigger,
                lock_r=stage3_lock,
                stage=3,
            ):
                events.append(
                    {
                        "event": "LOW_MAE_RUNNER_LOCK_STAGE_3",
                        "position_id": position_id,
                        "setup_id": state.get("setup_id"),
                        "current_r": round(current_r, 6),
                    }
                )
            continue

        if state["lock_stage"] < 2 and current_r >= stage2_trigger:
            if _advance_runner_lock(
                state=state,
                position=position,
                trigger_r=stage2_trigger,
                lock_r=stage2_lock,
                stage=2,
            ):
                events.append(
                    {
                        "event": "LOW_MAE_RUNNER_LOCK_STAGE_2",
                        "position_id": position_id,
                        "setup_id": state.get("setup_id"),
                        "current_r": round(current_r, 6),
                    }
                )

    return events
