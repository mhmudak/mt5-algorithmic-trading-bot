from __future__ import annotations

from typing import Any, Mapping


STRATEGY_NAME = "FVG"
ENTRY_MODEL = "FVG_RETRACE_REACTION"
MINIMUM_SCORE = 98.0
MINIMUM_RR = 1.80


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None

        return float(value)
    except (TypeError, ValueError):
        return None


def _first(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)

        if value is not None and value != "":
            return value

    return None


def _calculate_rr(
    data: Mapping[str, Any],
    signal: str,
) -> float | None:
    direct = _float(
        _first(
            data,
            "rr",
            "risk_reward",
            "rr_value",
            "original_rr",
        )
    )

    if direct is not None:
        return direct

    entry = _float(
        _first(
            data,
            "entry_reference",
            "entry_price",
            "entry",
        )
    )
    stop = _float(
        _first(
            data,
            "sl_reference",
            "stop_loss",
            "sl",
        )
    )
    target = _float(
        _first(
            data,
            "tp_reference",
            "take_profit",
            "tp",
            "tp1",
        )
    )

    if entry is None or stop is None or target is None:
        return None

    if signal == "BUY":
        risk = entry - stop
        reward = target - entry
    elif signal == "SELL":
        risk = stop - entry
        reward = entry - target
    else:
        return None

    if risk <= 0 or reward <= 0:
        return None

    return reward / risk


def _smc_tags(data: Mapping[str, Any]) -> set[str]:
    raw = data.get("smc") or []

    if isinstance(raw, str):
        values = raw.replace("|", ",").split(",")
    elif isinstance(raw, (list, tuple, set)):
        values = raw
    else:
        values = [raw]

    return {
        str(value).strip().lower()
        for value in values
        if str(value).strip()
    }


def evaluate_fvg_retrace_smc_override(
    setup_data: Mapping[str, Any] | None,
    signal: str | None,
) -> dict[str, Any]:
    data = dict(setup_data or {})
    strategy = str(data.get("strategy") or "").upper()
    entry_model = str(data.get("entry_model") or "").upper()
    signal_key = str(signal or data.get("signal") or "").upper()
    score = _float(data.get("score")) or 0.0
    rr = _calculate_rr(data, signal_key)

    top = _float(data.get("fvg_top"))
    bottom = _float(data.get("fvg_bottom"))
    valid_zone = (
        top is not None
        and bottom is not None
        and abs(top - bottom) > 0
    )

    tags = _smc_tags(data)

    if signal_key == "BUY":
        required_tags = {
            "ema_bullish",
            "bullish_bos",
            "fvg_present",
            "fvg_reclaimed",
        }
        required_momentum = "bullish_displacement_reaction"
        required_direction = "price_above_ema"
    elif signal_key == "SELL":
        required_tags = {
            "ema_bearish",
            "bearish_bos",
            "fvg_present",
            "fvg_reclaimed",
        }
        required_momentum = "bearish_displacement_reaction"
        required_direction = "price_below_ema"
    else:
        required_tags = set()
        required_momentum = ""
        required_direction = ""

    momentum = str(data.get("momentum") or "").lower()
    direction_context = str(
        data.get("direction_context") or ""
    ).lower()
    missing_tags = sorted(required_tags - tags)

    snapshot = {
        "strategy": strategy,
        "entry_model": entry_model,
        "signal": signal_key,
        "score": score,
        "minimum_score": MINIMUM_SCORE,
        "rr": rr,
        "minimum_rr": MINIMUM_RR,
        "fvg_top": top,
        "fvg_bottom": bottom,
        "valid_zone": valid_zone,
        "momentum": momentum,
        "required_momentum": required_momentum,
        "direction_context": direction_context,
        "required_direction_context": required_direction,
        "smc_tags": sorted(tags),
        "missing_smc_tags": missing_tags,
        "orders_sent": 0,
    }

    checks = (
        (
            strategy == STRATEGY_NAME,
            "fvg_retrace_strategy_not_applicable",
        ),
        (
            entry_model == ENTRY_MODEL,
            "fvg_retrace_entry_model_not_applicable",
        ),
        (
            signal_key in {"BUY", "SELL"},
            "fvg_retrace_invalid_signal",
        ),
        (
            score >= MINIMUM_SCORE,
            "fvg_retrace_score_too_low",
        ),
        (
            rr is not None and rr >= MINIMUM_RR,
            "fvg_retrace_rr_too_low",
        ),
        (
            valid_zone,
            "fvg_retrace_zone_invalid",
        ),
        (
            momentum == required_momentum,
            "fvg_retrace_momentum_mismatch",
        ),
        (
            direction_context == required_direction,
            "fvg_retrace_direction_context_mismatch",
        ),
        (
            not missing_tags,
            "fvg_retrace_smc_evidence_missing",
        ),
    )

    for allowed, reason in checks:
        if not allowed:
            return {
                "allowed": False,
                "reason": reason,
                "snapshot": snapshot,
            }

    return {
        "allowed": True,
        "reason": "fvg_retrace_strategy_smc_override_allowed",
        "snapshot": snapshot,
    }
