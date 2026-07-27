from __future__ import annotations

import math
from datetime import datetime

import MetaTrader5 as mt5

from config.settings import (
    ATR_MIN,
    ATR_MAX,
    ENABLE_PRO_TRADER_REPLICATION,
    PRO_TRADER_REPLICATION_MIN_SCORE,
    PRO_TRADER_REPLICATION_DEFAULT_RR,
    PRO_TRADER_REPLICATION_MIN_STOP_DISTANCE_PRICE,
    PRO_TRADER_REPLICATION_MAX_STOP_DISTANCE_PRICE,
    PRO_TRADER_REPLICATION_MIN_TARGET_DISTANCE_PRICE,
)


STRATEGY_NAME = "PRO_TRADER_REPLICATION"
SOURCE_BUCKET = "MANUAL_FULL_MARGIN_FORENSIC"
EXECUTION_MODE = "DEMO_EXECUTION_ONLY"

LEVEL_LOOKBACK_BARS = 48
SWEEP_LOOKBACK_BARS = 12
VWAP_LOOKBACK_BARS = 40


def _safe_float(value, default=None):
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


def _calculate_vwap(window):
    typical_price = (window["high"] + window["low"] + window["close"]) / 3

    if "tick_volume" in window.columns:
        volume = window["tick_volume"].replace(0, 1)
    elif "real_volume" in window.columns:
        volume = window["real_volume"].replace(0, 1)
    else:
        return float(typical_price.mean())

    try:
        return float((typical_price * volume).sum() / volume.sum())
    except Exception:
        return float(typical_price.mean())


def _volume_state(closed_window, entry):
    if "tick_volume" not in closed_window.columns:
        return "UNKNOWN_VOLUME", 0.0

    volumes = closed_window["tick_volume"].tail(30)

    if len(volumes) < 10:
        return "UNKNOWN_VOLUME", 0.0

    avg_volume = float(volumes.mean()) or 1.0
    current_volume = _safe_float(entry.get("tick_volume"), 0.0) or 0.0
    ratio = current_volume / avg_volume

    if ratio >= 1.8:
        return "HIGH_TICK_VOLUME", ratio

    if ratio >= 1.15:
        return "NORMAL_TICK_VOLUME", ratio

    return "LOW_TICK_VOLUME", ratio


def _nearest_round_distance(price, step=10.0):
    if price is None:
        return None

    nearest = round(price / step) * step
    return abs(price - nearest)


def _family_from_time(candle_time):
    try:
        if hasattr(candle_time, "hour"):
            hour = int(candle_time.hour)
        else:
            hour = datetime.fromtimestamp(float(candle_time)).hour
    except Exception:
        return "FM_UNKNOWN_SESSION"

    if hour < 7:
        return "FM_ASIA_GLOBEX_REJECTION"

    if 7 <= hour < 12:
        return "FM_LONDON_SWEEP_REVERSAL"

    if 12 <= hour < 17:
        return "FM_NY_OPEN_RECLAIM"

    return "FM_NY_MIDDAY_LATE_STRUCTURE"


def _build_signal(
    *,
    signal,
    entry,
    ref_level,
    sweep_extreme,
    vwap,
    atr,
    score,
    reasons,
    family,
    volume_state,
    volume_ratio,
):
    close = _safe_float(entry.get("close"))
    high = _safe_float(entry.get("high"))
    low = _safe_float(entry.get("low"))

    if close is None or high is None or low is None:
        return None

    sl_buffer = min(max(atr * 0.20, 1.0), 4.0)

    if signal == "BUY":
        sl_reference = min(low, sweep_extreme) - sl_buffer
        stop_distance = close - sl_reference

        if stop_distance <= 0:
            return None

        tp_distance = max(
            stop_distance * PRO_TRADER_REPLICATION_DEFAULT_RR,
            atr * 1.30,
            PRO_TRADER_REPLICATION_MIN_TARGET_DISTANCE_PRICE,
        )
        tp_reference = close + tp_distance

    else:
        sl_reference = max(high, sweep_extreme) + sl_buffer
        stop_distance = sl_reference - close

        if stop_distance <= 0:
            return None

        tp_distance = max(
            stop_distance * PRO_TRADER_REPLICATION_DEFAULT_RR,
            atr * 1.30,
            PRO_TRADER_REPLICATION_MIN_TARGET_DISTANCE_PRICE,
        )
        tp_reference = close - tp_distance

    if stop_distance < PRO_TRADER_REPLICATION_MIN_STOP_DISTANCE_PRICE:
        return None

    if stop_distance > PRO_TRADER_REPLICATION_MAX_STOP_DISTANCE_PRICE:
        return None

    if score < PRO_TRADER_REPLICATION_MIN_SCORE:
        return None

    return {
        "signal": signal,
        "score": int(min(score, 99)),
        "strategy": STRATEGY_NAME,
        "entry_model": "FM_SWEEP_RECLAIM_DEMO",
        "setup_source_bucket": SOURCE_BUCKET,
        "execution_mode": EXECUTION_MODE,
        "family": family,
        "sl_reference": round(sl_reference, 2),
        "tp_reference": round(tp_reference, 2),
        "pattern_height": round(abs(tp_reference - close), 2),
        "reference_level": round(ref_level, 2),
        "sweep_extreme": round(sweep_extreme, 2),
        "session_vwap_proxy": round(vwap, 2),
        "volume_state": volume_state,
        "volume_ratio": round(volume_ratio, 2),
        "orderflow_status": "NOT_CONNECTED_MT5_ONLY",
        "reason": (
            f"{family} {signal} -> pro trader replication demo -> "
            f"level={round(ref_level, 2)} sweep_extreme={round(sweep_extreme, 2)} "
            f"vwap={round(vwap, 2)} volume={volume_state} "
            f"reasons={','.join(reasons)} -> "
            f"SL {round(sl_reference, 2)} -> TP {round(tp_reference, 2)}"
        ),
    }


def generate_signal(df):
    if not ENABLE_PRO_TRADER_REPLICATION:
        return None

    if len(df) < LEVEL_LOOKBACK_BARS + SWEEP_LOOKBACK_BARS + 5:
        return None

    if not _is_demo_account():
        return None

    closed = df.iloc[:-1].reset_index(drop=True)

    if len(closed) < LEVEL_LOOKBACK_BARS + SWEEP_LOOKBACK_BARS + 3:
        return None

    entry = closed.iloc[-1]
    prev = closed.iloc[-2]

    atr = _safe_float(entry.get("atr_14"))

    if atr is None or atr <= 0:
        return None

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    level_window = closed.iloc[-(LEVEL_LOOKBACK_BARS + SWEEP_LOOKBACK_BARS):-SWEEP_LOOKBACK_BARS]
    recent_window = closed.iloc[-SWEEP_LOOKBACK_BARS:]
    vwap_window = closed.iloc[-VWAP_LOOKBACK_BARS:]

    ref_high = float(level_window["high"].max())
    ref_low = float(level_window["low"].min())
    recent_high = float(recent_window["high"].max())
    recent_low = float(recent_window["low"].min())

    open_price = _safe_float(entry.get("open"))
    high = _safe_float(entry.get("high"))
    low = _safe_float(entry.get("low"))
    close = _safe_float(entry.get("close"))

    prev_close = _safe_float(prev.get("close"))

    if None in {open_price, high, low, close, prev_close}:
        return None

    candle_range = high - low
    body = abs(close - open_price)

    if candle_range <= 0 or body <= 0:
        return None

    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low

    sweep_buffer = max(0.30, atr * 0.10)
    reclaim_buffer = max(0.20, atr * 0.05)

    vwap = _calculate_vwap(vwap_window)
    volume_state, volume_ratio = _volume_state(closed, entry)

    micro_high = float(recent_window.iloc[:-1]["high"].tail(5).max())
    micro_low = float(recent_window.iloc[:-1]["low"].tail(5).min())

    body_ok = body >= max(0.25, atr * 0.12)
    near_round = (_nearest_round_distance(close, step=10.0) or 999.0) <= max(2.0, atr * 0.25)

    family = _family_from_time(entry.get("time"))

    # =========================
    # BUY: sell-side sweep/reclaim + micro confirmation
    # =========================
    buy_reasons = []

    sellside_sweep = recent_low < ref_low - sweep_buffer
    buy_reclaim = close > ref_low + reclaim_buffer
    bullish_candle = close > open_price
    bullish_rejection = lower_wick >= max(body * 0.50, atr * 0.05)
    bullish_bos = close > micro_high
    vwap_reclaim = prev_close <= vwap and close > vwap

    if sellside_sweep:
        buy_reasons.append("sellside_sweep_recent")
    if buy_reclaim:
        buy_reasons.append("reclaim_above_reference_low")
    if bullish_rejection:
        buy_reasons.append("bullish_rejection_wick")
    if bullish_bos:
        buy_reasons.append("m1_micro_bos_proxy")
    if vwap_reclaim:
        buy_reasons.append("vwap_reclaim_proxy")
    if near_round:
        buy_reasons.append("near_round_number")
    if volume_state in {"NORMAL_TICK_VOLUME", "HIGH_TICK_VOLUME"}:
        buy_reasons.append(f"volume_state_{volume_state.lower()}")

    buy_score = 70
    buy_score += 10 if sellside_sweep else 0
    buy_score += 8 if buy_reclaim else 0
    buy_score += 6 if bullish_rejection else 0
    buy_score += 6 if bullish_bos else 0
    buy_score += 5 if vwap_reclaim else 0
    buy_score += 4 if near_round else 0
    buy_score += 3 if volume_state == "NORMAL_TICK_VOLUME" else 0
    buy_score += 5 if volume_state == "HIGH_TICK_VOLUME" else 0

    buy_candidate = (
        sellside_sweep
        and buy_reclaim
        and bullish_candle
        and body_ok
        and (bullish_bos or vwap_reclaim or bullish_rejection)
    )

    # =========================
    # SELL: buy-side sweep/reclaim + micro confirmation
    # =========================
    sell_reasons = []

    buyside_sweep = recent_high > ref_high + sweep_buffer
    sell_reclaim = close < ref_high - reclaim_buffer
    bearish_candle = close < open_price
    bearish_rejection = upper_wick >= max(body * 0.50, atr * 0.05)
    bearish_bos = close < micro_low
    vwap_rejection = prev_close >= vwap and close < vwap

    if buyside_sweep:
        sell_reasons.append("buyside_sweep_recent")
    if sell_reclaim:
        sell_reasons.append("reclaim_below_reference_high")
    if bearish_rejection:
        sell_reasons.append("bearish_rejection_wick")
    if bearish_bos:
        sell_reasons.append("m1_micro_bos_proxy")
    if vwap_rejection:
        sell_reasons.append("vwap_rejection_proxy")
    if near_round:
        sell_reasons.append("near_round_number")
    if volume_state in {"NORMAL_TICK_VOLUME", "HIGH_TICK_VOLUME"}:
        sell_reasons.append(f"volume_state_{volume_state.lower()}")

    sell_score = 70
    sell_score += 10 if buyside_sweep else 0
    sell_score += 8 if sell_reclaim else 0
    sell_score += 6 if bearish_rejection else 0
    sell_score += 6 if bearish_bos else 0
    sell_score += 5 if vwap_rejection else 0
    sell_score += 4 if near_round else 0
    sell_score += 3 if volume_state == "NORMAL_TICK_VOLUME" else 0
    sell_score += 5 if volume_state == "HIGH_TICK_VOLUME" else 0

    sell_candidate = (
        buyside_sweep
        and sell_reclaim
        and bearish_candle
        and body_ok
        and (bearish_bos or vwap_rejection or bearish_rejection)
    )

    if buy_candidate and sell_candidate:
        return None

    if buy_candidate:
        return _build_signal(
            signal="BUY",
            entry=entry,
            ref_level=ref_low,
            sweep_extreme=recent_low,
            vwap=vwap,
            atr=atr,
            score=buy_score,
            reasons=buy_reasons,
            family=family,
            volume_state=volume_state,
            volume_ratio=volume_ratio,
        )

    if sell_candidate:
        return _build_signal(
            signal="SELL",
            entry=entry,
            ref_level=ref_high,
            sweep_extreme=recent_high,
            vwap=vwap,
            atr=atr,
            score=sell_score,
            reasons=sell_reasons,
            family=family,
            volume_state=volume_state,
            volume_ratio=volume_ratio,
        )

    return None
