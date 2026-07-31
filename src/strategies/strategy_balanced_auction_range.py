from __future__ import annotations
import hashlib

import math

import MetaTrader5 as mt5

from config.settings import (
    ATR_MIN,
    ATR_MAX,
    ENABLE_BALANCED_AUCTION_RANGE,
    BALANCED_AUCTION_RANGE_DEMO_ONLY,
    BALANCED_AUCTION_RANGE_LOOKBACK_BARS,
    BALANCED_AUCTION_RANGE_MIN_WIDTH_ATR,
    BALANCED_AUCTION_RANGE_MAX_WIDTH_ATR,
    BALANCED_AUCTION_RANGE_EDGE_ZONE_PCT,
    BALANCED_AUCTION_RANGE_NO_TRADE_MIDDLE_PCT,
    BALANCED_AUCTION_RANGE_MIN_SCORE,
    BALANCED_AUCTION_RANGE_DEFAULT_RR,
    BALANCED_AUCTION_RANGE_MIN_STOP_DISTANCE_PRICE,
    BALANCED_AUCTION_RANGE_MAX_STOP_DISTANCE_PRICE,
    BALANCED_AUCTION_RANGE_MIN_TARGET_DISTANCE_PRICE,
)



PHASE6P2_RR_STRATEGY_STANDARDIZATION = True
PHASE6P2_STRATEGY_NAME = "BALANCED_AUCTION_RANGE"
PHASE6P2_FALLBACK_PHASE_NAME = "PHASE_6P2_BALANCED_AUCTION_RANGE_STANDARDIZED_COMPLETION"
PHASE6P2_SETUP_PREFIX = "BAR"
PHASE6P2_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

STRATEGY_NAME = "BALANCED_AUCTION_RANGE"
ENTRY_MODEL = "RANGE_EDGE_SWEEP_RECLAIM"


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


def _volume_state(window, entry):
    if "tick_volume" not in window.columns:
        return "UNKNOWN_VOLUME", 0.0

    volumes = window["tick_volume"].tail(30)

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


def _build_signal(
    *,
    signal,
    entry,
    range_high,
    range_low,
    range_mid,
    vwap,
    atr,
    score,
    reasons,
    sweep_extreme,
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
        sl_reference = min(low, sweep_extreme, range_low) - sl_buffer
        stop_distance = close - sl_reference

        if stop_distance <= 0:
            return None

        tp_reference = max(
            range_mid,
            close + max(stop_distance * BALANCED_AUCTION_RANGE_DEFAULT_RR, BALANCED_AUCTION_RANGE_MIN_TARGET_DISTANCE_PRICE),
        )

        tp_reference = min(tp_reference, range_high)

    else:
        sl_reference = max(high, sweep_extreme, range_high) + sl_buffer
        stop_distance = sl_reference - close

        if stop_distance <= 0:
            return None

        tp_reference = min(
            range_mid,
            close - max(stop_distance * BALANCED_AUCTION_RANGE_DEFAULT_RR, BALANCED_AUCTION_RANGE_MIN_TARGET_DISTANCE_PRICE),
        )

        tp_reference = max(tp_reference, range_low)

    target_distance = abs(tp_reference - close)

    if stop_distance < BALANCED_AUCTION_RANGE_MIN_STOP_DISTANCE_PRICE:
        return None

    if stop_distance > BALANCED_AUCTION_RANGE_MAX_STOP_DISTANCE_PRICE:
        return None

    if target_distance < BALANCED_AUCTION_RANGE_MIN_TARGET_DISTANCE_PRICE:
        return None

    if score < BALANCED_AUCTION_RANGE_MIN_SCORE:
        return None

    return {
        "signal": signal,
        "score": int(min(score, 99)),
        "strategy": STRATEGY_NAME,
        "entry_model": ENTRY_MODEL,
        "setup_source_bucket": "BALANCED_AUCTION_RANGE",
        "execution_mode": "DEMO_EXECUTION_ONLY",
        "sl_reference": round(sl_reference, 2),
        "tp_reference": round(tp_reference, 2),
        "pattern_height": round(target_distance, 2),
        "range_high": round(range_high, 2),
        "range_low": round(range_low, 2),
        "range_mid": round(range_mid, 2),
        "session_vwap_proxy": round(vwap, 2),
        "sweep_extreme": round(sweep_extreme, 2),
        "volume_state": volume_state,
        "volume_ratio": round(volume_ratio, 2),
        "orderflow_status": "NOT_CONNECTED_MT5_ONLY",
        "reason": (
            f"Balanced auction range {signal} -> edge sweep/reclaim -> "
            f"range={round(range_low, 2)}-{round(range_high, 2)} "
            f"mid={round(range_mid, 2)} vwap={round(vwap, 2)} "
            f"volume={volume_state} reasons={','.join(reasons)} -> "
            f"SL {round(sl_reference, 2)} -> TP {round(tp_reference, 2)}"
        ),
    }


def _phase6p2_generate_signal_raw(df):
    if not ENABLE_BALANCED_AUCTION_RANGE:
        return None

    if BALANCED_AUCTION_RANGE_DEMO_ONLY and not _is_demo_account():
        return None

    min_bars = BALANCED_AUCTION_RANGE_LOOKBACK_BARS + 8

    if len(df) < min_bars:
        return None

    closed = df.iloc[:-1].reset_index(drop=True)

    if len(closed) < min_bars:
        return None

    entry = closed.iloc[-1]
    prev = closed.iloc[-2]

    atr = _safe_float(entry.get("atr_14"))

    if atr is None or atr <= 0:
        return None

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    range_window = closed.iloc[-(BALANCED_AUCTION_RANGE_LOOKBACK_BARS + 2):-2]

    range_high = float(range_window["high"].max())
    range_low = float(range_window["low"].min())
    range_width = range_high - range_low

    if range_width <= 0:
        return None

    if range_width < atr * BALANCED_AUCTION_RANGE_MIN_WIDTH_ATR:
        return None

    if range_width > atr * BALANCED_AUCTION_RANGE_MAX_WIDTH_ATR:
        return None

    range_mid = (range_high + range_low) / 2
    upper_edge = range_high - range_width * BALANCED_AUCTION_RANGE_EDGE_ZONE_PCT
    lower_edge = range_low + range_width * BALANCED_AUCTION_RANGE_EDGE_ZONE_PCT

    middle_low = range_mid - range_width * BALANCED_AUCTION_RANGE_NO_TRADE_MIDDLE_PCT / 2
    middle_high = range_mid + range_width * BALANCED_AUCTION_RANGE_NO_TRADE_MIDDLE_PCT / 2

    open_price = _safe_float(entry.get("open"))
    high = _safe_float(entry.get("high"))
    low = _safe_float(entry.get("low"))
    close = _safe_float(entry.get("close"))
    prev_close = _safe_float(prev.get("close"))

    if None in {open_price, high, low, close, prev_close}:
        return None

    if middle_low <= close <= middle_high:
        return None

    body = abs(close - open_price)
    candle_range = high - low

    if body <= 0 or candle_range <= 0:
        return None

    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low

    sweep_buffer = max(0.30, atr * 0.10)
    reclaim_buffer = max(0.20, atr * 0.05)

    vwap = _calculate_vwap(closed.tail(BALANCED_AUCTION_RANGE_LOOKBACK_BARS))
    volume_state, volume_ratio = _volume_state(closed, entry)

    recent = closed.iloc[-8:]
    recent_high = float(recent["high"].max())
    recent_low = float(recent["low"].min())

    # =========================
    # BUY lower edge
    # =========================
    buy_reasons = []

    buy_edge_location = close <= lower_edge
    buy_sweep = low < range_low - sweep_buffer
    buy_reclaim = close > range_low + reclaim_buffer
    bullish_candle = close > open_price
    bullish_rejection = lower_wick >= max(body * 0.60, atr * 0.06)
    vwap_magnet_room = close < vwap or close < range_mid

    if buy_edge_location:
        buy_reasons.append("lower_edge_location")
    if buy_sweep:
        buy_reasons.append("sellside_sweep_below_range")
    if buy_reclaim:
        buy_reasons.append("reclaim_inside_range")
    if bullish_rejection:
        buy_reasons.append("bullish_rejection_wick")
    if vwap_magnet_room:
        buy_reasons.append("room_to_vwap_or_mid")
    if volume_state in {"NORMAL_TICK_VOLUME", "HIGH_TICK_VOLUME"}:
        buy_reasons.append(f"volume_state_{volume_state.lower()}")

    buy_score = 72
    buy_score += 9 if buy_edge_location else 0
    buy_score += 10 if buy_sweep else 0
    buy_score += 8 if buy_reclaim else 0
    buy_score += 6 if bullish_rejection else 0
    buy_score += 4 if vwap_magnet_room else 0
    buy_score += 3 if volume_state == "NORMAL_TICK_VOLUME" else 0
    buy_score += 5 if volume_state == "HIGH_TICK_VOLUME" else 0

    buy_candidate = (
        buy_edge_location
        and buy_sweep
        and buy_reclaim
        and bullish_candle
        and bullish_rejection
        and vwap_magnet_room
    )

    # =========================
    # SELL upper edge
    # =========================
    sell_reasons = []

    sell_edge_location = close >= upper_edge
    sell_sweep = high > range_high + sweep_buffer
    sell_reclaim = close < range_high - reclaim_buffer
    bearish_candle = close < open_price
    bearish_rejection = upper_wick >= max(body * 0.60, atr * 0.06)
    downside_room = close > vwap or close > range_mid

    if sell_edge_location:
        sell_reasons.append("upper_edge_location")
    if sell_sweep:
        sell_reasons.append("buyside_sweep_above_range")
    if sell_reclaim:
        sell_reasons.append("reclaim_inside_range")
    if bearish_rejection:
        sell_reasons.append("bearish_rejection_wick")
    if downside_room:
        sell_reasons.append("room_to_vwap_or_mid")
    if volume_state in {"NORMAL_TICK_VOLUME", "HIGH_TICK_VOLUME"}:
        sell_reasons.append(f"volume_state_{volume_state.lower()}")

    sell_score = 72
    sell_score += 9 if sell_edge_location else 0
    sell_score += 10 if sell_sweep else 0
    sell_score += 8 if sell_reclaim else 0
    sell_score += 6 if bearish_rejection else 0
    sell_score += 4 if downside_room else 0
    sell_score += 3 if volume_state == "NORMAL_TICK_VOLUME" else 0
    sell_score += 5 if volume_state == "HIGH_TICK_VOLUME" else 0

    sell_candidate = (
        sell_edge_location
        and sell_sweep
        and sell_reclaim
        and bearish_candle
        and bearish_rejection
        and downside_room
    )

    if buy_candidate and sell_candidate:
        return None

    if buy_candidate:
        return _build_signal(
            signal="BUY",
            entry=entry,
            range_high=range_high,
            range_low=range_low,
            range_mid=range_mid,
            vwap=vwap,
            atr=atr,
            score=buy_score,
            reasons=buy_reasons,
            sweep_extreme=recent_low,
            volume_state=volume_state,
            volume_ratio=volume_ratio,
        )

    if sell_candidate:
        return _build_signal(
            signal="SELL",
            entry=entry,
            range_high=range_high,
            range_low=range_low,
            range_mid=range_mid,
            vwap=vwap,
            atr=atr,
            score=sell_score,
            reasons=sell_reasons,
            sweep_extreme=recent_high,
            volume_state=volume_state,
            volume_ratio=volume_ratio,
        )

    return None


def _phase6p2_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _phase6p2_entry_reference(df, payload):
    for key in ("entry_reference", "entry_price", "entry", "price"):
        value = _phase6p2_float(payload.get(key))

        if value is not None:
            return value

    try:
        if df is not None and len(df) >= 2:
            return float(df.iloc[-2]["close"])
    except Exception:
        pass

    try:
        if df is not None and len(df) >= 1:
            return float(df.iloc[-1]["close"])
    except Exception:
        pass

    return None


def _phase6p2_risk_reward(signal, entry_reference, sl_reference, tp_reference):
    entry_reference = _phase6p2_float(entry_reference)
    sl_reference = _phase6p2_float(sl_reference)
    tp_reference = _phase6p2_float(tp_reference)

    if entry_reference is None or sl_reference is None or tp_reference is None:
        return None

    if signal == "BUY":
        risk = entry_reference - sl_reference
        reward = tp_reference - entry_reference
    else:
        risk = sl_reference - entry_reference
        reward = entry_reference - tp_reference

    if risk <= 0:
        return None

    return round(reward / risk, 2)


def _phase6p2_setup_id(payload, entry_reference):
    signal = payload.get("signal", "NA")
    entry_model = payload.get("entry_model", payload.get("type", "NA"))
    sl_reference = payload.get("sl_reference", payload.get("stop_loss", ""))
    tp_reference = payload.get("tp_reference", payload.get("take_profit", ""))

    raw = (
        f"{PHASE6P2_STRATEGY_NAME}:{signal}:{entry_model}:"
        f"{round(float(entry_reference), 2)}:{sl_reference}:{tp_reference}"
    )
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]

    return f"{PHASE6P2_SETUP_PREFIX}-{signal}-{digest}"


def _phase6p2_standardize_signal(payload, df):
    if not payload:
        return payload

    signal = payload.get("signal")
    entry_reference = _phase6p2_entry_reference(df, payload)

    if entry_reference is None:
        return payload

    existing_rr = _phase6p2_float(payload.get("rr"))
    existing_risk_reward = _phase6p2_float(payload.get("risk_reward"))

    computed_rr = _phase6p2_risk_reward(
        signal=signal,
        entry_reference=entry_reference,
        sl_reference=payload.get("sl_reference", payload.get("stop_loss")),
        tp_reference=payload.get("tp_reference", payload.get("take_profit")),
    )

    final_rr = existing_rr if existing_rr is not None else existing_risk_reward
    final_rr = final_rr if final_rr is not None else computed_rr

    payload.setdefault("strategy", PHASE6P2_STRATEGY_NAME)
    payload.setdefault("phase", PHASE6P2_FALLBACK_PHASE_NAME)
    payload.setdefault("setup_id", _phase6p2_setup_id(payload, entry_reference))
    payload.setdefault("entry_reference", round(float(entry_reference), 2))

    if final_rr is not None:
        payload.setdefault("rr", final_rr)
        payload.setdefault("risk_reward", final_rr)

    payload.setdefault("auto_trade_allowed", True)
    payload.setdefault("decision_impact", "MAIN_BOT_RUNTIME_CONTROLLED")
    payload.setdefault("duplicate_policy", PHASE6P2_DUPLICATE_POLICY)

    return payload


def generate_signal(df):
    return _phase6p2_standardize_signal(_phase6p2_generate_signal_raw(df), df)

