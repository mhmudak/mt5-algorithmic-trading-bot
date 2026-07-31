from __future__ import annotations

import math
from typing import Any


STRATEGY_NAME = "SESSION_EXHAUSTION_REVERSAL"
ENTRY_MODEL = "SESSION_EXTENSION_EXHAUSTION_REVERSAL"
PHASE = "PHASE_6D_SESSION_EXHAUSTION_REVERSAL"


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


def _vwap_proxy(rows: list[dict[str, Any]]) -> float:
    weighted_sum = 0.0
    volume_sum = 0.0
    simple_prices = []

    for row in rows:
        high = safe_float(row.get("high"))
        low = safe_float(row.get("low"))
        close = safe_float(row.get("close"))
        volume = safe_float(row.get("tick_volume"), 1.0)

        if min(high, low, close) <= 0:
            continue

        typical = (high + low + close) / 3
        simple_prices.append(typical)

        if volume <= 0:
            volume = 1.0

        weighted_sum += typical * volume
        volume_sum += volume

    if volume_sum > 0:
        return weighted_sum / volume_sum

    return sum(simple_prices) / len(simple_prices) if simple_prices else 0.0


def _score_signal(
    *,
    min_score: int,
    move_atr_ratio: float,
    extension_atr_ratio: float,
    wick_atr_ratio: float,
    body_atr_ratio: float,
    rr: float,
) -> int:
    score = int(min_score)

    if move_atr_ratio >= 2.8:
        score += 1

    if extension_atr_ratio >= 1.5:
        score += 1

    if wick_atr_ratio >= 0.55:
        score += 1

    if body_atr_ratio >= 0.25:
        score += 1

    if rr >= 2.2:
        score += 1

    return int(min(score, 98))


def _build_signal(
    *,
    signal: str,
    entry: dict[str, Any],
    atr: float,
    recent_vwap_proxy: float,
    session_move: float,
    move_atr_ratio: float,
    extension_atr_ratio: float,
    wick_atr_ratio: float,
    body_atr_ratio: float,
    min_score: int,
    sl_buffer: float,
    min_rr: float,
    target_rr: float,
    max_sl_distance: float,
) -> dict[str, Any] | None:
    open_price = safe_float(entry.get("open"))
    high = safe_float(entry.get("high"))
    low = safe_float(entry.get("low"))
    close = safe_float(entry.get("close"))

    if min(open_price, high, low, close) <= 0:
        return None

    if signal == "SELL":
        sl_reference = high + sl_buffer
        sl_distance = sl_reference - close
        tp_reference = close - (sl_distance * target_rr)

        if not (tp_reference < close < sl_reference):
            return None

    elif signal == "BUY":
        sl_reference = low - sl_buffer
        sl_distance = close - sl_reference
        tp_reference = close + (sl_distance * target_rr)

        if not (sl_reference < close < tp_reference):
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
        move_atr_ratio=move_atr_ratio,
        extension_atr_ratio=extension_atr_ratio,
        wick_atr_ratio=wick_atr_ratio,
        body_atr_ratio=body_atr_ratio,
        rr=rr,
    )

    return {
        "phase": PHASE,
        "signal": signal,
        "score": score,
        "strategy": STRATEGY_NAME,
        "family": "SESSION_EXHAUSTION_REVERSAL",
        "entry_model": ENTRY_MODEL,
        "setup_source_bucket": "SESSION_EXHAUSTION_REVERSAL",
        "execution_mode": "GLOBAL_RUNTIME_CONTROLLED",
        "entry_reference": round(close, 2),
        "sl_reference": round(sl_reference, 2),
        "tp_reference": round(tp_reference, 2),
        "pattern_height": round(abs(tp_reference - close), 2),
        "rr": round(rr, 2),
        "atr": round(atr, 2),
        "recent_vwap_proxy": round(recent_vwap_proxy, 2),
        "session_move": round(session_move, 2),
        "move_atr_ratio": round(move_atr_ratio, 3),
        "extension_atr_ratio": round(extension_atr_ratio, 3),
        "wick_atr_ratio": round(wick_atr_ratio, 3),
        "body_atr_ratio": round(body_atr_ratio, 3),
        "target_model": "SESSION_EXHAUSTION_RR_TARGET",
        "orderflow_status": "NOT_CONNECTED_MT5_ONLY",
        "funded_suitable": True,
        "demo_execution_suitable": True,
        "auto_trade_allowed": True,
        "decision_impact": "MAIN_BOT_RUNTIME_CONTROLLED",
        "reason": (
            f"Session exhaustion reversal {signal} -> "
            f"move/ATR={round(move_atr_ratio, 3)} "
            f"extension/ATR={round(extension_atr_ratio, 3)} "
            f"wick/ATR={round(wick_atr_ratio, 3)} "
            f"vwap_proxy={round(recent_vwap_proxy, 2)} -> "
            f"SL {round(sl_reference, 2)} -> TP {round(tp_reference, 2)} score={score}"
        ),
    }


def generate_signal(df):
    from config.settings import (
        ENABLE_SESSION_EXHAUSTION_REVERSAL,
        SER_ATR_PERIOD,
        SER_CLOSE_REVERSAL_RATIO,
        SER_LOOKBACK_BARS,
        SER_MAX_SL_DISTANCE,
        SER_MIN_BODY_ATR_RATIO,
        SER_MIN_EXTENSION_ATR_RATIO,
        SER_MIN_MOVE_ATR_RATIO,
        SER_MIN_RR,
        SER_MIN_SCORE,
        SER_MIN_WICK_ATR_RATIO,
        SER_SL_BUFFER,
        SER_TARGET_RR,
    )

    if not ENABLE_SESSION_EXHAUSTION_REVERSAL:
        return None

    min_required = max(SER_LOOKBACK_BARS, SER_ATR_PERIOD + 8)

    if df is None or len(df) < min_required + 1:
        return None

    closed = df.iloc[:-1].reset_index(drop=True)

    if len(closed) < min_required:
        return None

    rows = [row.to_dict() for _, row in closed.iterrows()]
    window = rows[-SER_LOOKBACK_BARS:]
    entry = window[-1]
    previous_window = window[:-1]

    atr = _atr_from_rows(rows, SER_ATR_PERIOD)

    if atr <= 0:
        return None

    first_close = safe_float(previous_window[0].get("close"))
    close = safe_float(entry.get("close"))
    open_price = safe_float(entry.get("open"))
    high = safe_float(entry.get("high"))
    low = safe_float(entry.get("low"))

    if min(first_close, close, open_price, high, low) <= 0:
        return None

    session_move = close - first_close
    move_atr_ratio = abs(session_move) / atr if atr else 0.0

    if move_atr_ratio < SER_MIN_MOVE_ATR_RATIO:
        return None

    recent_vwap_proxy = _vwap_proxy(previous_window)

    if recent_vwap_proxy <= 0:
        return None

    extension = close - recent_vwap_proxy
    extension_atr_ratio = abs(extension) / atr if atr else 0.0

    if extension_atr_ratio < SER_MIN_EXTENSION_ATR_RATIO:
        return None

    body = abs(close - open_price)
    body_atr_ratio = body / atr if atr else 0.0

    if body_atr_ratio < SER_MIN_BODY_ATR_RATIO:
        return None

    candle_range = high - low

    if candle_range <= 0:
        return None

    close_position = (close - low) / candle_range

    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low

    upper_wick_atr_ratio = upper_wick / atr if atr else 0.0
    lower_wick_atr_ratio = lower_wick / atr if atr else 0.0

    strong_up_move = session_move > 0 and extension > 0
    strong_down_move = session_move < 0 and extension < 0

    # Exhausted bullish session -> SELL reversal.
    bearish_exhaustion = (
        strong_up_move
        and upper_wick_atr_ratio >= SER_MIN_WICK_ATR_RATIO
        and close < open_price
        and close_position <= SER_CLOSE_REVERSAL_RATIO
    )

    if bearish_exhaustion:
        return _build_signal(
            signal="SELL",
            entry=entry,
            atr=atr,
            recent_vwap_proxy=recent_vwap_proxy,
            session_move=session_move,
            move_atr_ratio=move_atr_ratio,
            extension_atr_ratio=extension_atr_ratio,
            wick_atr_ratio=upper_wick_atr_ratio,
            body_atr_ratio=body_atr_ratio,
            min_score=SER_MIN_SCORE,
            sl_buffer=SER_SL_BUFFER,
            min_rr=SER_MIN_RR,
            target_rr=SER_TARGET_RR,
            max_sl_distance=SER_MAX_SL_DISTANCE,
        )

    # Exhausted bearish session -> BUY reversal.
    bullish_exhaustion = (
        strong_down_move
        and lower_wick_atr_ratio >= SER_MIN_WICK_ATR_RATIO
        and close > open_price
        and close_position >= (1 - SER_CLOSE_REVERSAL_RATIO)
    )

    if bullish_exhaustion:
        return _build_signal(
            signal="BUY",
            entry=entry,
            atr=atr,
            recent_vwap_proxy=recent_vwap_proxy,
            session_move=session_move,
            move_atr_ratio=move_atr_ratio,
            extension_atr_ratio=extension_atr_ratio,
            wick_atr_ratio=lower_wick_atr_ratio,
            body_atr_ratio=body_atr_ratio,
            min_score=SER_MIN_SCORE,
            sl_buffer=SER_SL_BUFFER,
            min_rr=SER_MIN_RR,
            target_rr=SER_TARGET_RR,
            max_sl_distance=SER_MAX_SL_DISTANCE,
        )

    return None
