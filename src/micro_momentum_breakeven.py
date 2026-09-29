from __future__ import annotations

from typing import Any

import MetaTrader5 as mt5

from config import settings as runtime_settings
from src.logger import logger
from src.position_manager import close_position_volume, modify_sl
from src.trade_tracker import load_trades, save_trades


STRATEGY_NAME = "INTRABAR_MICRO_MOMENTUM"


def evaluate_micro_momentum_breakeven(
    *,
    signal: str,
    entry_price: float,
    original_take_profit: float,
    current_price: float,
    current_stop: float | None,
    trigger_fraction: float = 0.50,
    lock_price: float = 0.0,
) -> dict[str, Any]:
    side = str(signal or "").upper()
    entry = float(entry_price)
    tp = float(original_take_profit)
    current = float(current_price)
    current_sl = (
        None
        if current_stop in (None, 0, 0.0)
        else float(current_stop)
    )

    result = {
        "strategy": STRATEGY_NAME,
        "signal": side,
        "entry_price": round(entry, 2),
        "original_take_profit": round(tp, 2),
        "current_price": round(current, 2),
        "current_stop": current_sl,
        "trigger_fraction": float(trigger_fraction),
        "lock_price": float(lock_price),
        "target_distance": None,
        "trigger_distance": None,
        "favorable_distance": None,
        "desired_stop": current_sl,
        "should_modify": False,
        "reason": "invalid_geometry",
    }

    if side == "BUY":
        target_distance = tp - entry
        favorable_distance = current - entry
        desired_stop = entry + float(lock_price)

        if target_distance <= 0:
            return result

        trigger_distance = target_distance * float(trigger_fraction)

        result.update(
            {
                "target_distance": round(target_distance, 6),
                "trigger_distance": round(trigger_distance, 6),
                "favorable_distance": round(favorable_distance, 6),
                "desired_stop": round(desired_stop, 2),
            }
        )

        if favorable_distance + 1e-9 < trigger_distance:
            result["reason"] = "tp_progress_not_reached"
            return result

        if current_sl is not None and current_sl >= desired_stop - 1e-9:
            result["reason"] = "stop_already_at_or_better_than_be"
            return result

    elif side == "SELL":
        target_distance = entry - tp
        favorable_distance = entry - current
        desired_stop = entry - float(lock_price)

        if target_distance <= 0:
            return result

        trigger_distance = target_distance * float(trigger_fraction)

        result.update(
            {
                "target_distance": round(target_distance, 6),
                "trigger_distance": round(trigger_distance, 6),
                "favorable_distance": round(favorable_distance, 6),
                "desired_stop": round(desired_stop, 2),
            }
        )

        if favorable_distance + 1e-9 < trigger_distance:
            result["reason"] = "tp_progress_not_reached"
            return result

        if (
            current_sl is not None
            and current_sl <= desired_stop + 1e-9
        ):
            result["reason"] = "stop_already_at_or_better_than_be"
            return result

    else:
        result["reason"] = "invalid_signal"
        return result

    result["should_modify"] = True
    result["reason"] = "breakeven_protection_triggered"
    return result


def evaluate_micro_momentum_profit_capture(
    *,
    signal: str,
    entry_price: float,
    original_take_profit: float,
    current_price: float,
    capture_price: float = 1.50,
) -> dict[str, Any]:
    side = str(signal or "").upper()
    entry = float(entry_price)
    tp = float(original_take_profit)
    current = float(current_price)
    capture = max(0.0, float(capture_price))

    result = {
        "strategy": STRATEGY_NAME,
        "signal": side,
        "entry_price": round(entry, 2),
        "original_take_profit": round(tp, 2),
        "current_price": round(current, 2),
        "capture_price": round(capture, 2),
        "target_distance": None,
        "favorable_distance": None,
        "should_close": False,
        "reason": "invalid_geometry",
    }

    if capture <= 0:
        result["reason"] = "capture_disabled"
        return result

    if side == "BUY":
        target_distance = tp - entry
        favorable_distance = current - entry
    elif side == "SELL":
        target_distance = entry - tp
        favorable_distance = entry - current
    else:
        result["reason"] = "invalid_signal"
        return result

    result["target_distance"] = round(target_distance, 6)
    result["favorable_distance"] = round(favorable_distance, 6)

    if target_distance <= 0:
        return result

    if target_distance <= capture + 1e-9:
        result["reason"] = "original_tp_not_beyond_capture"
        return result

    if favorable_distance + 1e-9 < capture:
        result["reason"] = "capture_price_not_reached"
        return result

    result["should_close"] = True
    result["reason"] = "profit_capture_reached"
    return result

def _micro_momentum_strength_from_trade(
    trade: dict[str, Any],
) -> str:
    optimization = trade.get("intrabar_optimization")
    if isinstance(optimization, dict):
        detector = optimization.get("detector_features")
        if isinstance(detector, dict):
            strength = str(detector.get("strength") or "").upper()
            if strength:
                return strength

    direct = str(
        trade.get("micro_momentum_strength") or ""
    ).upper()
    if direct:
        return direct

    reason = str(trade.get("reason") or "").upper()
    for strength in ("WEAK_VALID", "NORMAL", "EXPLOSIVE"):
        if (
            f"STRENGTH={strength}" in reason
            or f"STRENGTH: {strength}" in reason
        ):
            return strength

    return "UNKNOWN"


def evaluate_micro_momentum_aggressive_early_be(
    *,
    signal: str,
    strength: str,
    entry_price: float,
    current_price: float,
    current_stop: float | None,
    enabled: bool,
    trigger_price: float = 0.10,
    lock_price: float = 0.0,
    allowed_strengths: tuple[str, ...] = (
        "NORMAL",
        "EXPLOSIVE",
    ),
    stage2_profiles: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """
    Two-stage Micro Momentum protection.

    Stage 1:
      favorable move >= trigger_price -> protect at entry +/− lock_price.

    Stage 2:
      strength-specific trigger -> tighten to a strength-specific
      positive-price lock.

    Never loosens an already tighter stop.
    """
    side = str(signal or "").upper()
    strength_name = str(strength or "").upper()
    allowed = {
        str(item or "").upper()
        for item in allowed_strengths
    }

    entry = float(entry_price)
    current = float(current_price)
    stage1_trigger = max(0.0, float(trigger_price))
    stage1_lock = max(0.0, float(lock_price))

    if stage2_profiles is None:
        try:
            from config import settings as runtime_settings
            raw_profiles = getattr(
                runtime_settings,
                "MICRO_MOMENTUM_AGGRESSIVE_STAGE2_PROFILES",
                {},
            )
            stage2_profiles = (
                dict(raw_profiles)
                if isinstance(raw_profiles, dict)
                else {}
            )
        except Exception:
            stage2_profiles = {}

    result = {
        "should_modify": False,
        "desired_stop": entry,
        "reason": "not_triggered",
        "strength": strength_name,
        "trigger_price": stage1_trigger,
        "lock_price": stage1_lock,
        "stage": 0,
        "stage2_trigger_price": None,
        "stage2_lock_price": None,
        "favorable_distance": 0.0,
    }

    if not enabled:
        result["reason"] = "disabled"
        return result

    if stage1_lock > stage1_trigger + 1e-9:
        result["reason"] = "invalid_stage1_geometry"
        return result

    if strength_name not in allowed:
        result["reason"] = "strength_not_enabled"
        return result

    if side == "BUY":
        favorable = current - entry
    elif side == "SELL":
        favorable = entry - current
    else:
        result["reason"] = "invalid_signal"
        return result

    result["favorable_distance"] = round(favorable, 6)

    selected_trigger = stage1_trigger
    selected_lock = stage1_lock
    selected_stage = 1

    profile = (
        stage2_profiles.get(strength_name)
        if isinstance(stage2_profiles, dict)
        else None
    )

    if isinstance(profile, dict):
        try:
            stage2_trigger = max(
                0.0,
                float(profile.get("trigger_price", 0.0)),
            )
            stage2_lock = max(
                0.0,
                float(profile.get("lock_price", 0.0)),
            )
        except (TypeError, ValueError):
            stage2_trigger = None
            stage2_lock = None

        if (
            stage2_trigger is not None
            and stage2_lock is not None
        ):
            result["stage2_trigger_price"] = stage2_trigger
            result["stage2_lock_price"] = stage2_lock

            if stage2_lock > stage2_trigger + 1e-9:
                result["reason"] = "invalid_stage2_geometry"
                return result

            if favorable + 1e-9 >= stage2_trigger:
                selected_trigger = stage2_trigger
                selected_lock = stage2_lock
                selected_stage = 2

    if favorable + 1e-9 < selected_trigger:
        result["reason"] = "trigger_not_reached"
        return result

    if side == "BUY":
        desired_stop = entry + selected_lock
    else:
        desired_stop = entry - selected_lock

    result["desired_stop"] = desired_stop
    result["trigger_price"] = selected_trigger
    result["lock_price"] = selected_lock
    result["stage"] = selected_stage

    if current_stop is not None:
        stop = float(current_stop)

        if side == "BUY" and stop >= desired_stop - 1e-9:
            result["reason"] = "already_at_or_better_than_lock"
            return result

        if side == "SELL" and stop <= desired_stop + 1e-9:
            result["reason"] = "already_at_or_better_than_lock"
            return result

    result["should_modify"] = True
    result["reason"] = (
        "stage2_profit_lock_triggered"
        if selected_stage == 2
        else "aggressive_be_triggered"
    )
    return result


def _position_price(position: Any, tick: Any) -> float:
    if position.type == mt5.POSITION_TYPE_BUY:
        return float(tick.bid)
    return float(tick.ask)


def _position_signal(position: Any) -> str:
    if position.type == mt5.POSITION_TYPE_BUY:
        return "BUY"
    return "SELL"


def manage_micro_momentum_breakeven(
    *,
    symbol: str,
    tick: Any,
) -> list[dict[str, Any]]:
    if not bool(
        getattr(
            runtime_settings,
            "ENABLE_MICRO_MOMENTUM_BREAKEVEN_PROTECTION",
            True,
        )
    ):
        return []

    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return []

    trades = load_trades()
    if not isinstance(trades, dict):
        return []

    trigger_fraction = float(
        getattr(
            runtime_settings,
            "MICRO_MOMENTUM_BREAKEVEN_TP_PROGRESS",
            0.50,
        )
    )
    lock_price = float(
        getattr(
            runtime_settings,
            "MICRO_MOMENTUM_BREAKEVEN_LOCK_PRICE",
            0.0,
        )
    )
    profit_capture_enabled = bool(
        getattr(
            runtime_settings,
            "ENABLE_MICRO_MOMENTUM_PROFIT_CAPTURE",
            True,
        )
    )
    profit_capture_price = float(
        getattr(
            runtime_settings,
            "MICRO_MOMENTUM_PROFIT_CAPTURE_PRICE",
            1.50,
        )
    )

    changed_tracker = False
    events: list[dict[str, Any]] = []

    for position in positions:
        position_id = str(position.ticket)
        trade = trades.get(position_id)

        if not isinstance(trade, dict):
            continue

        if str(trade.get("strategy") or "").upper() != STRATEGY_NAME:
            continue

        if str(trade.get("status") or "OPEN").upper() != "OPEN":
            continue

        signal = _position_signal(position)
        tracked_signal = str(trade.get("signal") or signal).upper()
        if tracked_signal != signal:
            logger.warning(
                "[MICRO MOMENTUM BE] tracker/position direction mismatch | "
                f"position={position_id} tracker={tracked_signal} mt5={signal}"
            )
            continue

        try:
            original_tp = float(trade.get("take_profit"))
        except (TypeError, ValueError):
            continue

        current_price = _position_price(position, tick)
        current_sl_raw = float(getattr(position, "sl", 0.0) or 0.0)
        current_sl = current_sl_raw if current_sl_raw > 0 else None

        aggressive_be_enabled = bool(
            getattr(
                runtime_settings,
                "ENABLE_MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE",
                False,
            )
        )
        aggressive_be_trigger = float(
            getattr(
                runtime_settings,
                "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE_TRIGGER_PRICE",
                0.10,
            )
        )
        aggressive_be_lock = float(
            getattr(
                runtime_settings,
                "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE_LOCK_PRICE",
                0.0,
            )
        )
        aggressive_be_strengths = tuple(
            getattr(
                runtime_settings,
                "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE_STRENGTHS",
                ("NORMAL", "EXPLOSIVE"),
            )
        )
        aggressive_be_strength = (
            _micro_momentum_strength_from_trade(trade)
        )

        experiment_fields = {
            "micro_momentum_aggressive_early_be_enabled": (
                aggressive_be_enabled
            ),
            "micro_momentum_aggressive_early_be_trigger_price": (
                aggressive_be_trigger
            ),
            "micro_momentum_aggressive_early_be_lock_price": (
                aggressive_be_lock
            ),
            "micro_momentum_aggressive_early_be_allowed_strengths": list(
                aggressive_be_strengths
            ),
            "micro_momentum_aggressive_early_be_strength": (
                aggressive_be_strength
            ),
        }
        for field_name, field_value in experiment_fields.items():
            if trade.get(field_name) != field_value:
                trade[field_name] = field_value
                changed_tracker = True

        aggressive_be = (
            evaluate_micro_momentum_aggressive_early_be(
                signal=signal,
                strength=aggressive_be_strength,
                entry_price=float(position.price_open),
                current_price=current_price,
                current_stop=current_sl,
                enabled=aggressive_be_enabled,
                trigger_price=aggressive_be_trigger,
                lock_price=aggressive_be_lock,
                allowed_strengths=aggressive_be_strengths,
            )
        )

        if aggressive_be["should_modify"]:
            if modify_sl(
                position,
                aggressive_be["desired_stop"],
                original_tp,
                reason=(
                    "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE "
                    f"strength={aggressive_be_strength} "
                    f"favorable={aggressive_be['favorable_distance']}"
                ),
            ):
                trade[
                    "micro_momentum_aggressive_early_be_applied"
                ] = True
                trade[
                    "micro_momentum_aggressive_early_be_trigger_price"
                ] = aggressive_be_trigger
                trade[
                    "micro_momentum_aggressive_early_be_strength"
                ] = aggressive_be_strength
                changed_tracker = True
                events.append(
                    {
                        "event": (
                            "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE"
                        ),
                        "position_id": position_id,
                        **aggressive_be,
                    }
                )
                logger.info(
                    "[MICRO MOMENTUM AGGRESSIVE EARLY BE] "
                    f"position={position_id} "
                    f"strength={aggressive_be_strength} "
                    f"signal={signal} "
                    f"favorable={aggressive_be['favorable_distance']} "
                    f"new_sl={aggressive_be['desired_stop']}"
                )
                current_sl = float(
                    aggressive_be["desired_stop"]
                )

        if profit_capture_enabled:
            capture = evaluate_micro_momentum_profit_capture(
                signal=signal,
                entry_price=float(position.price_open),
                original_take_profit=original_tp,
                current_price=current_price,
                capture_price=profit_capture_price,
            )

            if capture["should_close"]:
                if close_position_volume(
                    position,
                    float(position.volume),
                    tick,
                    reason="MICRO_MOMENTUM_PROFIT_CAPTURE_1_50",
                ):
                    trade["micro_momentum_profit_capture_applied"] = True
                    trade["micro_momentum_profit_capture_price"] = (
                        profit_capture_price
                    )
                    changed_tracker = True
                    events.append(
                        {
                            "event": "MICRO_MOMENTUM_PROFIT_CAPTURE",
                            "position_id": position_id,
                            **capture,
                        }
                    )
                    logger.info(
                        "[MICRO MOMENTUM PROFIT CAPTURE] full close | "
                        f"position={position_id} signal={signal} "
                        f"entry={capture['entry_price']} "
                        f"original_tp={capture['original_take_profit']} "
                        f"favorable={capture['favorable_distance']}"
                    )
                    continue

        decision = evaluate_micro_momentum_breakeven(
            signal=signal,
            entry_price=float(position.price_open),
            original_take_profit=original_tp,
            current_price=current_price,
            current_stop=current_sl,
            trigger_fraction=trigger_fraction,
            lock_price=lock_price,
        )

        if not decision["should_modify"]:
            continue

        if modify_sl(
            position,
            decision["desired_stop"],
            float(getattr(position, "tp", 0.0) or 0.0),
            reason=(
                "MICRO_MOMENTUM_BREAKEVEN "
                f"{int(round(trigger_fraction * 100.0))}%_TP_PROGRESS"
            ),
        ):
            trade["micro_momentum_be_applied"] = True
            trade["micro_momentum_be_trigger_fraction"] = trigger_fraction
            trade["micro_momentum_be_price"] = decision["desired_stop"]
            trade["micro_momentum_be_trigger_distance"] = (
                decision["trigger_distance"]
            )
            changed_tracker = True

            event = {
                "event": "MICRO_MOMENTUM_BREAKEVEN_APPLIED",
                "position_id": position_id,
                **decision,
            }
            events.append(event)

            logger.info(
                "[MICRO MOMENTUM BE] applied | "
                f"position={position_id} signal={signal} "
                f"entry={decision['entry_price']} "
                f"tp={decision['original_take_profit']} "
                f"trigger_distance={decision['trigger_distance']} "
                f"new_sl={decision['desired_stop']}"
            )

    if changed_tracker:
        save_trades(trades)

    return events
