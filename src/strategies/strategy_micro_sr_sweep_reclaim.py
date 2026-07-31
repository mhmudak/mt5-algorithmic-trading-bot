import hashlib
import MetaTrader5 as mt5
import pandas as pd

from config.settings import SYMBOL, EMA_PERIOD, ATR_PERIOD, ATR_MIN, ATR_MAX
from src.indicators import calculate_ema, calculate_atr
from src.strategy_debug import reject_strategy
from src.logger import logger



PHASE6P3A_PRIORITY_LEGACY_STANDARDIZATION = True
PHASE6P3A_STRATEGY_NAME = "MICRO_SR_SWEEP_RECLAIM"
PHASE6P3A_FALLBACK_PHASE_NAME = "PHASE_6P3A_MICRO_SR_SWEEP_RECLAIM_STANDARDIZED_COMPLETION"
PHASE6P3A_SETUP_PREFIX = "MSR"
PHASE6P3A_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

MICRO_SR_TIMEFRAME = mt5.TIMEFRAME_M5
MICRO_SR_BARS = 120

MICRO_SR_LOOKBACK = 30
MICRO_SR_SWING_LOOKBACK = 8

MIN_SWEEP_ATR = 0.08
MAX_SWEEP_ATR = 1.20

MIN_RECLAIM_BODY_ATR = 0.15
MIN_CLOSE_QUALITY = 0.55

ENABLE_SOFT_RECLAIM_BODY_EXCEPTION = True
SOFT_RECLAIM_BODY_ATR = 0.12
SOFT_RECLAIM_MIN_CLOSE_QUALITY = 0.75

SL_ATR_BUFFER = 0.20
MIN_SL_BUFFER = 1.5
MAX_SL_BUFFER = 5.0

TARGET_ATR_MIN = 1.2
TARGET_ATR_MAX = 3.0


def _fetch_m5_data():
    rates = mt5.copy_rates_from_pos(SYMBOL, MICRO_SR_TIMEFRAME, 0, MICRO_SR_BARS)

    if rates is None or len(rates) < MICRO_SR_LOOKBACK + 10:
        logger.info("[MICRO_SR_SWEEP] M5 data unavailable")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)

    return df


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, structure_range):
    return min(
        max(structure_range * 0.70, atr * TARGET_ATR_MIN),
        atr * TARGET_ATR_MAX,
    )


def _recent_levels(df):
    recent = df.iloc[-(MICRO_SR_LOOKBACK + 2):-2]

    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    micro_high = df.iloc[-(MICRO_SR_SWING_LOOKBACK + 2):-2]["high"].max()
    micro_low = df.iloc[-(MICRO_SR_SWING_LOOKBACK + 2):-2]["low"].min()

    return recent_high, recent_low, micro_high, micro_low


def _score_setup(base_score, body, atr, sweep_depth, close_quality, ema_aligned):
    score = base_score

    if body > atr * 0.25:
        score += 2

    if body > atr * 0.45:
        score += 2

    if sweep_depth > atr * 0.20:
        score += 2

    if close_quality:
        score += 2

    if ema_aligned:
        score += 2

    return min(score, 99)


def _phase6p3a_generate_signal_raw(df):
    m5_df = _fetch_m5_data()

    if m5_df is None:
        return reject_strategy("MICRO_SR_SWEEP_RECLAIM", "m5_data_unavailable")

    entry = m5_df.iloc[-2]
    prev = m5_df.iloc[-3]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return reject_strategy(
            "MICRO_SR_SWEEP_RECLAIM",
            "atr_out_of_range",
            atr=round(atr, 2),
        )

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return reject_strategy("MICRO_SR_SWEEP_RECLAIM", "invalid_candle_range")

    close_from_low = (entry["close"] - entry["low"]) / candle_range
    close_from_high = (entry["high"] - entry["close"]) / candle_range

    normal_body_ok = body >= atr * MIN_RECLAIM_BODY_ATR

    soft_body_ok_for_sell = (
        ENABLE_SOFT_RECLAIM_BODY_EXCEPTION
        and body >= atr * SOFT_RECLAIM_BODY_ATR
        and close_from_high >= SOFT_RECLAIM_MIN_CLOSE_QUALITY
    )

    soft_body_ok_for_buy = (
        ENABLE_SOFT_RECLAIM_BODY_EXCEPTION
        and body >= atr * SOFT_RECLAIM_BODY_ATR
        and close_from_low >= SOFT_RECLAIM_MIN_CLOSE_QUALITY
    )

    if not normal_body_ok and not soft_body_ok_for_sell and not soft_body_ok_for_buy:
        return reject_strategy(
            "MICRO_SR_SWEEP_RECLAIM",
            "body_too_small",
            body=round(body, 2),
            required=round(atr * MIN_RECLAIM_BODY_ATR, 2),
            soft_required=round(atr * SOFT_RECLAIM_BODY_ATR, 2),
            close_from_high=round(close_from_high, 2),
            close_from_low=round(close_from_low, 2),
        )

    recent_high, recent_low, micro_high, micro_low = _recent_levels(m5_df)
    structure_range = recent_high - recent_low

    if structure_range <= 0:
        return reject_strategy("MICRO_SR_SWEEP_RECLAIM", "invalid_structure_range")

    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, structure_range)

    # =========================================================
    # SELL: sweep above micro resistance, close back below
    # =========================================================
    swept_above = entry["high"] > micro_high + atr * MIN_SWEEP_ATR
    sweep_depth = entry["high"] - micro_high

    valid_sweep = (
        sweep_depth >= atr * MIN_SWEEP_ATR
        and sweep_depth <= atr * MAX_SWEEP_ATR
    )

    bearish_body_ok = normal_body_ok or soft_body_ok_for_sell
    
    bearish_reclaim = (
        bearish_body_ok
        and entry["close"] < entry["open"]
        and entry["close"] < micro_high
        and entry["close"] < prev["low"]
        and close_from_high >= MIN_CLOSE_QUALITY
    )

    ema_aligned = price < ema

    if swept_above and valid_sweep and bearish_reclaim:
        sl_reference = round(max(entry["high"], micro_high) + sl_buffer, 2)

        if recent_low < entry["close"]:
            tp_reference = recent_low
            target_model = "RECENT_MICRO_SUPPORT"
        else:
            tp_reference = entry["close"] - target_distance
            target_model = "MICRO_SWEEP_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=91,
            body=body,
            atr=atr,
            sweep_depth=sweep_depth,
            close_quality=close_from_high >= 0.65,
            ema_aligned=ema_aligned,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "MICRO_SR_SWEEP_RECLAIM",
            "entry_model": "MICRO_RESISTANCE_SWEEP_RECLAIM",
            "pattern_height": abs(entry["close"] - tp_reference),
            "micro_level": micro_high,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sweep_high": entry["high"],
            "sweep_depth": round(sweep_depth, 2),
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_micro_resistance_sweep_reclaim",
            "direction_context": "m5_micro_sweep_reclaim",
            "reason": (
                f"Micro SR sweep SELL -> swept above resistance {round(micro_high, 2)} "
                f"then closed back below and broke previous low -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
            ),
        }

    # =========================================================
    # BUY: sweep below micro support, close back above
    # =========================================================
    swept_below = entry["low"] < micro_low - atr * MIN_SWEEP_ATR
    sweep_depth = micro_low - entry["low"]

    valid_sweep = (
        sweep_depth >= atr * MIN_SWEEP_ATR
        and sweep_depth <= atr * MAX_SWEEP_ATR
    )

    bullish_body_ok = normal_body_ok or soft_body_ok_for_buy
    
    bullish_reclaim = (
        bullish_body_ok
        and entry["close"] > entry["open"]
        and entry["close"] > micro_low
        and entry["close"] > prev["high"]
        and close_from_low >= MIN_CLOSE_QUALITY
    )

    ema_aligned = price > ema

    if swept_below and valid_sweep and bullish_reclaim:
        sl_reference = round(min(entry["low"], micro_low) - sl_buffer, 2)

        if recent_high > entry["close"]:
            tp_reference = recent_high
            target_model = "RECENT_MICRO_RESISTANCE"
        else:
            tp_reference = entry["close"] + target_distance
            target_model = "MICRO_SWEEP_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=91,
            body=body,
            atr=atr,
            sweep_depth=sweep_depth,
            close_quality=close_from_low >= 0.65,
            ema_aligned=ema_aligned,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "MICRO_SR_SWEEP_RECLAIM",
            "entry_model": "MICRO_SUPPORT_SWEEP_RECLAIM",
            "pattern_height": abs(tp_reference - entry["close"]),
            "micro_level": micro_low,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sweep_low": entry["low"],
            "sweep_depth": round(sweep_depth, 2),
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_micro_support_sweep_reclaim",
            "direction_context": "m5_micro_sweep_reclaim",
            "reason": (
                f"Micro SR sweep BUY -> swept below support {round(micro_low, 2)} "
                f"then closed back above and broke previous high -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
            ),
        }

    return reject_strategy(
        "MICRO_SR_SWEEP_RECLAIM",
        "no_valid_micro_sr_sweep_setup",
        price=round(price, 2),
        micro_high=round(micro_high, 2),
        micro_low=round(micro_low, 2),
        close_from_high=round(close_from_high, 2),
        close_from_low=round(close_from_low, 2),
    )


def _phase6p3a_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _phase6p3a_entry_reference(df, payload):
    for key in ("entry_reference", "entry_price", "entry", "price"):
        value = _phase6p3a_float(payload.get(key))

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


def _phase6p3a_risk_reward(signal, entry_reference, sl_reference, tp_reference):
    entry_reference = _phase6p3a_float(entry_reference)
    sl_reference = _phase6p3a_float(sl_reference)
    tp_reference = _phase6p3a_float(tp_reference)

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


def _phase6p3a_setup_id(payload, entry_reference):
    signal = payload.get("signal", "NA")
    entry_model = payload.get("entry_model", payload.get("type", "NA"))
    sl_reference = payload.get("sl_reference", payload.get("stop_loss", ""))
    tp_reference = payload.get("tp_reference", payload.get("take_profit", ""))

    raw = (
        f"{PHASE6P3A_STRATEGY_NAME}:{signal}:{entry_model}:"
        f"{round(float(entry_reference), 2)}:{sl_reference}:{tp_reference}"
    )
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]

    return f"{PHASE6P3A_SETUP_PREFIX}-{signal}-{digest}"


def _phase6p3a_standardize_signal(payload, df):
    if not payload:
        return payload

    signal = payload.get("signal")
    entry_reference = _phase6p3a_entry_reference(df, payload)

    if entry_reference is None:
        return payload

    existing_rr = _phase6p3a_float(payload.get("rr"))
    existing_risk_reward = _phase6p3a_float(payload.get("risk_reward"))

    computed_rr = _phase6p3a_risk_reward(
        signal=signal,
        entry_reference=entry_reference,
        sl_reference=payload.get("sl_reference", payload.get("stop_loss")),
        tp_reference=payload.get("tp_reference", payload.get("take_profit")),
    )

    final_rr = existing_rr if existing_rr is not None else existing_risk_reward
    final_rr = final_rr if final_rr is not None else computed_rr

    payload.setdefault("strategy", PHASE6P3A_STRATEGY_NAME)
    payload.setdefault("phase", PHASE6P3A_FALLBACK_PHASE_NAME)
    payload.setdefault("setup_id", _phase6p3a_setup_id(payload, entry_reference))
    payload.setdefault("entry_reference", round(float(entry_reference), 2))

    if final_rr is not None:
        payload.setdefault("rr", final_rr)
        payload.setdefault("risk_reward", final_rr)

    payload.setdefault("auto_trade_allowed", True)
    payload.setdefault("decision_impact", "MAIN_BOT_RUNTIME_CONTROLLED")
    payload.setdefault("duplicate_policy", PHASE6P3A_DUPLICATE_POLICY)

    return payload


def generate_signal(df):
    return _phase6p3a_standardize_signal(_phase6p3a_generate_signal_raw(df), df)

