from __future__ import annotations

import math
from typing import Any


STRATEGY_NAME = "PSYCH_ROUND_NUMBER_REJECTION"
ENTRY_MODEL = "PSYCHOLOGICAL_LEVEL_REJECTION"
PHASE = "PHASE_6C_PSYCH_ROUND_NUMBER_REJECTION"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        value = float(value)
        if math.isnan(value):
            return default
        return value
    except Exception:
        return default


def _is_demo_account() -> bool:
    try:
        import MetaTrader5 as mt5

        info = mt5.account_info()

        if info is None:
            return False

        trade_mode = getattr(info, "trade_mode", None)
        demo_constant = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)

        if demo_constant is not None and trade_mode == demo_constant:
            return True

        server = str(getattr(info, "server", "") or "").lower()
        name = str(getattr(info, "name", "") or "").lower()

        return "demo" in server or "demo" in name

    except Exception:
        return False


def _atr_from_rows(rows: list[dict[str, Any]], period: int) -> float:
    if len(rows) < period + 1:
        return 0.0

    trs = []

    sample = rows[-(period + 1):]

    for idx in range(1, len(sample)):
        current = sample[idx]
        previous = sample[idx - 1]

        high = safe_float(current.get("high"))
        low = safe_float(current.get("low"))
        prev_close = safe_float(previous.get("close"))

        if high <= 0 or low <= 0 or prev_close <= 0:
            continue

        trs.append(
            max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
        )

    return sum(trs) / len(trs) if trs else 0.0


def _nearest_round_level(price: float, major_step: float, minor_step: float, use_minor: bool) -> tuple[float, str]:
    step = minor_step if use_minor else major_step

    nearest = round(price / step) * step

    if major_step > 0 and abs(nearest % major_step) < 1e-9:
        level_type = "MAJOR_ROUND_NUMBER"
    else:
        level_type = "MINOR_ROUND_NUMBER"

    return float(nearest), level_type


def _score_signal(
    *,
    min_score: int,
    level_type: str,
    wick_atr_ratio: float,
    body_atr_ratio: float,
    close_distance: float,
    rr: float,
) -> int:
    score = int(min_score)

    if level_type == "MAJOR_ROUND_NUMBER":
        score += 1

    if wick_atr_ratio >= 0.55:
        score += 1

    if body_atr_ratio >= 0.25:
        score += 1

    if close_distance <= 0.60:
        score += 1

    if rr >= 2.2:
        score += 1

    return int(min(score, 98))


def _build_signal(
    *,
    signal: str,
    entry: dict[str, Any],
    level: float,
    level_type: str,
    atr: float,
    min_score: int,
    sl_buffer: float,
    target_rr: float,
    min_rr: float,
    max_sl_distance: float,
    rejection_distance: float,
    wick_atr_ratio: float,
    body_atr_ratio: float,
    close_distance: float,
) -> dict[str, Any] | None:
    close = safe_float(entry.get("close"))
    high = safe_float(entry.get("high"))
    low = safe_float(entry.get("low"))
    open_price = safe_float(entry.get("open"))

    if min(close, high, low, open_price) <= 0:
        return None

    if signal == "BUY":
        sl_reference = low - sl_buffer
        sl_distance = close - sl_reference
        tp_reference = close + (sl_distance * target_rr)

        if not (sl_reference < close < tp_reference):
            return None

    elif signal == "SELL":
        sl_reference = high + sl_buffer
        sl_distance = sl_reference - close
        tp_reference = close - (sl_distance * target_rr)

        if not (tp_reference < close < sl_reference):
            return None

    else:
        return None

    if sl_distance <= 0:
        return None

    if sl_distance > max_sl_distance:
        return None

    rr = abs(tp_reference - close) / sl_distance if sl_distance else 0.0

    if rr < min_rr:
        return None

    score = _score_signal(
        min_score=min_score,
        level_type=level_type,
        wick_atr_ratio=wick_atr_ratio,
        body_atr_ratio=body_atr_ratio,
        close_distance=close_distance,
        rr=rr,
    )

    return {
        "phase": PHASE,
        "signal": signal,
        "score": score,
        "strategy": STRATEGY_NAME,
        "family": "PSYCHOLOGICAL_ROUND_NUMBER_REJECTION",
        "entry_model": ENTRY_MODEL,
        "setup_source_bucket": "PSYCH_ROUND_NUMBER_REJECTION",
        "execution_mode": "GLOBAL_RUNTIME_CONTROLLED",
        "entry_reference": round(close, 2),
        "sl_reference": round(sl_reference, 2),
        "tp_reference": round(tp_reference, 2),
        "pattern_height": round(abs(tp_reference - close), 2),
        "rr": round(rr, 2),
        "psych_level": round(level, 2),
        "psych_level_type": level_type,
        "rejection_distance": round(rejection_distance, 2),
        "wick_atr_ratio": round(wick_atr_ratio, 3),
        "body_atr_ratio": round(body_atr_ratio, 3),
        "close_distance_from_level": round(close_distance, 2),
        "atr": round(atr, 2),
        "target_model": "ROUND_NUMBER_REJECTION_RR_TARGET",
        "orderflow_status": "NOT_CONNECTED_MT5_ONLY",
        "funded_suitable": True,
        "demo_execution_suitable": True,
        "auto_trade_allowed": True,
        "decision_impact": "MAIN_BOT_RUNTIME_CONTROLLED",
        "reason": (
            f"Psychological round number rejection {signal} -> "
            f"level={round(level, 2)} type={level_type} "
            f"rejection={round(rejection_distance, 2)} "
            f"wick/ATR={round(wick_atr_ratio, 3)} body/ATR={round(body_atr_ratio, 3)} -> "
            f"SL {round(sl_reference, 2)} -> TP {round(tp_reference, 2)} score={score}"
        ),
    }


def generate_signal(df):
    from config.settings import (
        ENABLE_PSYCH_ROUND_NUMBER_REJECTION,
        PSYCH_RNR_ATR_PERIOD,
        PSYCH_RNR_LOOKBACK_BARS,
        PSYCH_RNR_MAJOR_STEP,
        PSYCH_RNR_MAX_CLOSE_DISTANCE_FROM_LEVEL,
        PSYCH_RNR_MAX_SL_DISTANCE,
        PSYCH_RNR_MIN_BODY_ATR_RATIO,
        PSYCH_RNR_MIN_REJECTION_DISTANCE,
        PSYCH_RNR_MIN_RR,
        PSYCH_RNR_MIN_SCORE,
        PSYCH_RNR_MIN_WICK_ATR_RATIO,
        PSYCH_RNR_MINOR_STEP,
        PSYCH_RNR_SL_BUFFER,
        PSYCH_RNR_TARGET_RR,
        PSYCH_RNR_USE_MINOR_LEVELS,
    )

    if not ENABLE_PSYCH_ROUND_NUMBER_REJECTION:
        return None

    min_required = max(PSYCH_RNR_LOOKBACK_BARS, PSYCH_RNR_ATR_PERIOD + 5)

    if df is None or len(df) < min_required:
        return None

    closed = df.iloc[:-1].reset_index(drop=True)

    if len(closed) < min_required:
        return None

    rows = [row.to_dict() for _, row in closed.iterrows()]
    entry = rows[-1]

    atr = _atr_from_rows(rows, PSYCH_RNR_ATR_PERIOD)

    if atr <= 0:
        return None

    open_price = safe_float(entry.get("open"))
    high = safe_float(entry.get("high"))
    low = safe_float(entry.get("low"))
    close = safe_float(entry.get("close"))

    if min(open_price, high, low, close) <= 0:
        return None

    body = abs(close - open_price)

    if body <= 0:
        return None

    level, level_type = _nearest_round_level(
        close,
        PSYCH_RNR_MAJOR_STEP,
        PSYCH_RNR_MINOR_STEP,
        PSYCH_RNR_USE_MINOR_LEVELS,
    )

    close_distance = abs(close - level)

    if close_distance > PSYCH_RNR_MAX_CLOSE_DISTANCE_FROM_LEVEL:
        return None

    body_atr_ratio = body / atr if atr else 0.0

    if body_atr_ratio < PSYCH_RNR_MIN_BODY_ATR_RATIO:
        return None

    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low

    # Rejection from resistance round number:
    # price probes above/near the level but closes back below/near it with upper wick.
    bearish_probe = high >= level + PSYCH_RNR_MIN_REJECTION_DISTANCE
    bearish_reject = close < level or close < open_price
    bearish_wick_ratio = upper_wick / atr if atr else 0.0

    if bearish_probe and bearish_reject and bearish_wick_ratio >= PSYCH_RNR_MIN_WICK_ATR_RATIO:
        return _build_signal(
            signal="SELL",
            entry=entry,
            level=level,
            level_type=level_type,
            atr=atr,
            min_score=PSYCH_RNR_MIN_SCORE,
            sl_buffer=PSYCH_RNR_SL_BUFFER,
            target_rr=PSYCH_RNR_TARGET_RR,
            min_rr=PSYCH_RNR_MIN_RR,
            max_sl_distance=PSYCH_RNR_MAX_SL_DISTANCE,
            rejection_distance=high - level,
            wick_atr_ratio=bearish_wick_ratio,
            body_atr_ratio=body_atr_ratio,
            close_distance=close_distance,
        )

    # Rejection from support round number:
    # price probes below/near the level but closes back above/near it with lower wick.
    bullish_probe = low <= level - PSYCH_RNR_MIN_REJECTION_DISTANCE
    bullish_reject = close > level or close > open_price
    bullish_wick_ratio = lower_wick / atr if atr else 0.0

    if bullish_probe and bullish_reject and bullish_wick_ratio >= PSYCH_RNR_MIN_WICK_ATR_RATIO:
        return _build_signal(
            signal="BUY",
            entry=entry,
            level=level,
            level_type=level_type,
            atr=atr,
            min_score=PSYCH_RNR_MIN_SCORE,
            sl_buffer=PSYCH_RNR_SL_BUFFER,
            target_rr=PSYCH_RNR_TARGET_RR,
            min_rr=PSYCH_RNR_MIN_RR,
            max_sl_distance=PSYCH_RNR_MAX_SL_DISTANCE,
            rejection_distance=level - low,
            wick_atr_ratio=bullish_wick_ratio,
            body_atr_ratio=body_atr_ratio,
            close_distance=close_distance,
        )

    return None
