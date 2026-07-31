import hashlib
import MetaTrader5 as mt5
import pandas as pd

from src.indicators import calculate_ema, calculate_atr
from src.logger import logger
from config.settings import (
    SYMBOL,
    EMA_PERIOD,
    ATR_PERIOD,
    ATR_MIN,
    ATR_MAX,
    ENABLE_EXTERNAL_SMT,
    SMT_CONFIRMATION_SYMBOL,
    SMT_LOOKBACK_BARS,
    TIMEFRAME,
)



PHASE6P2_RR_STRATEGY_STANDARDIZATION = True
PHASE6P2_STRATEGY_NAME = "SMT_PRO"
PHASE6P2_FALLBACK_PHASE_NAME = "PHASE_6P2_SMT_PRO_STANDARDIZED_COMPLETION"
PHASE6P2_SETUP_PREFIX = "SMTP"
PHASE6P2_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

SMT_PRO_SL_ATR_MULTIPLIER = 0.20
SMT_PRO_MIN_SL_BUFFER = 2.0
SMT_PRO_MAX_SL_BUFFER = 5.0


def _sl_buffer(atr):
    return min(
        max(atr * SMT_PRO_SL_ATR_MULTIPLIER, SMT_PRO_MIN_SL_BUFFER),
        SMT_PRO_MAX_SL_BUFFER,
    )


def _score_setup(base_score, body, atr, external_confirmed, close_aligned):
    score = base_score

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.50:
        score += 2

    if external_confirmed:
        score += 3

    if close_aligned:
        score += 2

    return min(score, 99)


def _fetch_symbol_df(symbol: str, bars: int):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, bars)
    if rates is None:
        logger.error(f"[SMT PRO] Failed to fetch rates for {symbol}: {mt5.last_error()}")
        return None

    df = pd.DataFrame(rates)
    if df.empty:
        return None

    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)
    return df


def _phase6p2_generate_signal_raw(df):
    if not ENABLE_EXTERNAL_SMT:
        return None

    if len(df) < SMT_LOOKBACK_BARS + 8:
        return None

    confirm_df = _fetch_symbol_df(SMT_CONFIRMATION_SYMBOL, len(df))
    if confirm_df is None or len(confirm_df) < SMT_LOOKBACK_BARS + 8:
        return None

    # Use closed candles only
    df = df.iloc[:-1].reset_index(drop=True)
    confirm_df = confirm_df.iloc[:-1].reset_index(drop=True)

    min_len = min(len(df), len(confirm_df))
    df = df.iloc[-min_len:].reset_index(drop=True)
    confirm_df = confirm_df.iloc[-min_len:].reset_index(drop=True)

    entry = df.iloc[-1]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    main_high_1 = df.iloc[-(SMT_LOOKBACK_BARS + 5):-5]["high"].max()
    main_high_2 = df.iloc[-5:]["high"].max()

    main_low_1 = df.iloc[-(SMT_LOOKBACK_BARS + 5):-5]["low"].min()
    main_low_2 = df.iloc[-5:]["low"].min()

    conf_high_1 = confirm_df.iloc[-(SMT_LOOKBACK_BARS + 5):-5]["high"].max()
    conf_high_2 = confirm_df.iloc[-5:]["high"].max()

    conf_low_1 = confirm_df.iloc[-(SMT_LOOKBACK_BARS + 5):-5]["low"].min()
    conf_low_2 = confirm_df.iloc[-5:]["low"].min()

    structure_high = df.iloc[-20:]["high"].max()
    structure_low = df.iloc[-20:]["low"].min()

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if body <= 0 or candle_range <= 0:
        return None

    upper_wick = entry["high"] - max(entry["open"], entry["close"])
    lower_wick = min(entry["open"], entry["close"]) - entry["low"]

    sl_buffer = _sl_buffer(atr)

    # =========================================================
    # Bearish SMT PRO
    # Main symbol makes higher high, confirmation symbol does not
    # =========================================================
    main_higher_high = main_high_2 > main_high_1
    confirm_no_higher_high = conf_high_2 <= conf_high_1

    bearish_rejection = (
        entry["high"] >= main_high_2
        and entry["close"] < entry["open"]
        and entry["close"] < entry["high"] - atr * 0.20
        and upper_wick > body * 1.0
    )

    bearish_context = price < ema
    bearish_momentum = body > atr * 0.20

    if (
        main_higher_high
        and confirm_no_higher_high
        and bearish_rejection
        and bearish_context
        and bearish_momentum
    ):
        pattern_height = abs(main_high_2 - main_low_2)

        if pattern_height <= 0:
            return None

        sl_reference = round(main_high_2 + sl_buffer, 2)

        if structure_low < entry["close"]:
            tp_reference = structure_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = entry["close"] - max(pattern_height, atr * 1.5)
            target_model = "MEASURED_SMT_PRO_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=95,
            body=body,
            atr=atr,
            external_confirmed=confirm_no_higher_high,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "SMT_PRO",
            "entry_model": "SMT_EXTERNAL_DIVERGENCE_REVERSAL",
            "pattern_height": pattern_height,
            "main_high_1": main_high_1,
            "main_high_2": main_high_2,
            "confirm_high_1": conf_high_1,
            "confirm_high_2": conf_high_2,
            "structure_high": structure_high,
            "structure_low": structure_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "smt_reference_symbol": SMT_CONFIRMATION_SYMBOL,
            "divergence_type": "main_higher_high_confirm_symbol_no_higher_high",
            "momentum": "bearish_external_smt_rejection",
            "direction_context": "price_below_ema",
            "reason": (
                f"SMT PRO bearish -> {SYMBOL} made higher high {round(main_high_2, 2)} "
                f"while {SMT_CONFIRMATION_SYMBOL} failed to confirm "
                f"({round(conf_high_1, 2)} vs {round(conf_high_2, 2)}) -> "
                f"SL above SMT high {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price below EMA"
            ),
        }

    # =========================================================
    # Bullish SMT PRO
    # Main symbol makes lower low, confirmation symbol does not
    # =========================================================
    main_lower_low = main_low_2 < main_low_1
    confirm_no_lower_low = conf_low_2 >= conf_low_1

    bullish_rejection = (
        entry["low"] <= main_low_2
        and entry["close"] > entry["open"]
        and entry["close"] > entry["low"] + atr * 0.20
        and lower_wick > body * 1.0
    )

    bullish_context = price > ema
    bullish_momentum = body > atr * 0.20

    if (
        main_lower_low
        and confirm_no_lower_low
        and bullish_rejection
        and bullish_context
        and bullish_momentum
    ):
        pattern_height = abs(main_high_2 - main_low_2)

        if pattern_height <= 0:
            return None

        sl_reference = round(main_low_2 - sl_buffer, 2)

        if structure_high > entry["close"]:
            tp_reference = structure_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = entry["close"] + max(pattern_height, atr * 1.5)
            target_model = "MEASURED_SMT_PRO_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=95,
            body=body,
            atr=atr,
            external_confirmed=confirm_no_lower_low,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "SMT_PRO",
            "entry_model": "SMT_EXTERNAL_DIVERGENCE_REVERSAL",
            "pattern_height": pattern_height,
            "main_low_1": main_low_1,
            "main_low_2": main_low_2,
            "confirm_low_1": conf_low_1,
            "confirm_low_2": conf_low_2,
            "structure_high": structure_high,
            "structure_low": structure_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "smt_reference_symbol": SMT_CONFIRMATION_SYMBOL,
            "divergence_type": "main_lower_low_confirm_symbol_no_lower_low",
            "momentum": "bullish_external_smt_rejection",
            "direction_context": "price_above_ema",
            "reason": (
                f"SMT PRO bullish -> {SYMBOL} made lower low {round(main_low_2, 2)} "
                f"while {SMT_CONFIRMATION_SYMBOL} failed to confirm "
                f"({round(conf_low_1, 2)} vs {round(conf_low_2, 2)}) -> "
                f"SL below SMT low {sl_reference} -> "
                f"TP {target_model} {tp_reference} -> price above EMA"
            ),
        }

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

