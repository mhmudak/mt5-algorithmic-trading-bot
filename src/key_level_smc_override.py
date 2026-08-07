from __future__ import annotations

import re
from typing import Any, Mapping


ENABLE_KEY_LEVEL_STRONG_SMC_OVERRIDE = True

STRATEGY_NAME = "KEY_LEVEL_BREAK_HOLD"
MINIMUM_SCORE = 100.0
MINIMUM_RR = 1.80
MINIMUM_TOUCHES = 3
MAX_EXTENSION_ATR_RATIO = 0.75


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


def _combined_text(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item) for item in value).upper()

    return str(value or "").upper()


def _calculate_rr(
    setup_data: Mapping[str, Any],
    signal: str,
) -> float | None:
    direct_rr = _float(
        _first(
            setup_data,
            "rr",
            "risk_reward",
            "rr_value",
            "original_rr",
        )
    )

    if direct_rr is not None:
        return direct_rr

    entry = _float(
        _first(
            setup_data,
            "entry_reference",
            "entry_price",
            "entry",
        )
    )
    stop = _float(
        _first(
            setup_data,
            "sl_reference",
            "stop_loss",
            "sl",
        )
    )
    target = _float(
        _first(
            setup_data,
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


def _touch_count(
    setup_data: Mapping[str, Any],
) -> int | None:
    direct = _first(
        setup_data,
        "key_level_touches",
        "level_touches",
        "touch_count",
        "touches",
        "level_strength",
    )

    direct_float = _float(direct)

    if direct_float is not None:
        return int(direct_float)

    reason = str(setup_data.get("reason") or "")

    match = re.search(
        r"\btouches?\s*[:=]?\s*(\d+)\b",
        reason,
        flags=re.IGNORECASE,
    )

    if match:
        return int(match.group(1))

    return None


def _normalize_bias(value: Any) -> str | None:
    text = str(value or "").strip().upper()

    if text in {"BUY", "BULL", "BULLISH", "LONG"}:
        return "BUY"

    if text in {"SELL", "BEAR", "BEARISH", "SHORT"}:
        return "SELL"

    return None


def _opposite_htf_context(
    setup_data: Mapping[str, Any],
    signal: str,
) -> tuple[bool, str | None, str | None]:
    if setup_data.get("mtf_conflict") is True:
        return True, "mtf_conflict", "TRUE"

    for key in (
        "mtf_bias",
        "htf_bias",
        "higher_timeframe_bias",
        "m15_bias",
        "m15_direction_lock",
        "direction_lock",
    ):
        bias = _normalize_bias(setup_data.get(key))

        if bias is not None and bias != signal:
            return True, key, bias

    return False, None, None


def evaluate_key_level_strong_smc_override(
    setup_data: Mapping[str, Any] | None,
    signal: str | None,
) -> dict[str, Any]:
    data = dict(setup_data or {})
    signal_key = str(signal or data.get("signal") or "").upper()
    strategy = str(data.get("strategy") or "").upper()

    score = _float(data.get("score")) or 0.0
    rr = _calculate_rr(data, signal_key)
    touches = _touch_count(data)

    entry_model = str(
        data.get("entry_model") or ""
    ).upper()

    reason = str(data.get("reason") or "")
    reason_upper = reason.upper()

    smc_text = " ".join(
        (
            _combined_text(data.get("smc")),
            _combined_text(data.get("smc_reasons")),
            reason_upper,
        )
    )

    break_hold_confirmed = bool(
        "KEY_LEVEL_BREAK_HOLD" in entry_model
        or "BREAK_HOLD" in entry_model
        or (
            "BROKEN" in reason_upper
            and "HELD" in reason_upper
        )
    )

    required_ema = (
        "EMA_BULLISH"
        if signal_key == "BUY"
        else "EMA_BEARISH"
    )

    ema_aligned = required_ema in smc_text

    extension_ratio = _float(
        _first(
            data,
            "extension_atr_ratio",
            "break_extension_atr_ratio",
            "key_level_extension_atr_ratio",
        )
    )

    explicitly_overextended = bool(
        data.get("too_extended") is True
        or data.get("overextended") is True
        or (
            extension_ratio is not None
            and extension_ratio >
            MAX_EXTENSION_ATR_RATIO
        )
    )

    opposite_htf, opposite_key, opposite_value = (
        _opposite_htf_context(
            data,
            signal_key,
        )
    )

    snapshot = {
        "strategy": strategy,
        "signal": signal_key,
        "score": score,
        "minimum_score": MINIMUM_SCORE,
        "rr": rr,
        "minimum_rr": MINIMUM_RR,
        "touches": touches,
        "minimum_touches": MINIMUM_TOUCHES,
        "entry_model": entry_model,
        "break_hold_confirmed": break_hold_confirmed,
        "required_ema": required_ema,
        "ema_aligned": ema_aligned,
        "extension_atr_ratio": extension_ratio,
        "maximum_extension_atr_ratio":
            MAX_EXTENSION_ATR_RATIO,
        "explicitly_overextended":
            explicitly_overextended,
        "opposite_htf_context": opposite_htf,
        "opposite_htf_key": opposite_key,
        "opposite_htf_value": opposite_value,
        "orders_sent": 0,
    }

    if not ENABLE_KEY_LEVEL_STRONG_SMC_OVERRIDE:
        return {
            "allowed": False,
            "reason":
                "key_level_strong_smc_override_disabled",
            "snapshot": snapshot,
        }

    if strategy != STRATEGY_NAME:
        return {
            "allowed": False,
            "reason":
                "key_level_strategy_not_applicable",
            "snapshot": snapshot,
        }

    if signal_key not in {"BUY", "SELL"}:
        return {
            "allowed": False,
            "reason": "key_level_invalid_signal",
            "snapshot": snapshot,
        }

    if score < MINIMUM_SCORE:
        return {
            "allowed": False,
            "reason":
                "key_level_override_score_too_low",
            "snapshot": snapshot,
        }

    if rr is None or rr < MINIMUM_RR:
        return {
            "allowed": False,
            "reason":
                "key_level_override_rr_too_low",
            "snapshot": snapshot,
        }

    if touches is None or touches < MINIMUM_TOUCHES:
        return {
            "allowed": False,
            "reason":
                "key_level_override_touches_too_low",
            "snapshot": snapshot,
        }

    if not break_hold_confirmed:
        return {
            "allowed": False,
            "reason":
                "key_level_break_hold_not_confirmed",
            "snapshot": snapshot,
        }

    if not ema_aligned:
        return {
            "allowed": False,
            "reason":
                "key_level_ema_alignment_missing",
            "snapshot": snapshot,
        }

    if explicitly_overextended:
        return {
            "allowed": False,
            "reason":
                "key_level_setup_overextended",
            "snapshot": snapshot,
        }

    if opposite_htf:
        return {
            "allowed": False,
            "reason":
                "key_level_opposite_htf_context",
            "snapshot": snapshot,
        }

    return {
        "allowed": True,
        "reason":
            "key_level_strong_smc_override_allowed",
        "snapshot": snapshot,
    }
