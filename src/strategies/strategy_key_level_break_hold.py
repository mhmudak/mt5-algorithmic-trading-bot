from config.settings import (
    ATR_MIN,
    ATR_MAX,
    KEY_LEVEL_BREAK_HOLD_LOOKBACK_BARS,
    KEY_LEVEL_BREAK_HOLD_MIN_SCORE,
    KEY_LEVEL_BREAK_HOLD_MIN_LEVEL_TOUCHES,
    KEY_LEVEL_BREAK_HOLD_TOUCH_TOLERANCE_ATR,
    KEY_LEVEL_BREAK_HOLD_BREAK_BUFFER_ATR,
    KEY_LEVEL_BREAK_HOLD_HOLD_BUFFER_ATR,
    KEY_LEVEL_BREAK_HOLD_MAX_EXTENSION_ATR,
    KEY_LEVEL_BREAK_HOLD_MIN_BODY_ATR,
    KEY_LEVEL_BREAK_HOLD_SL_BUFFER_ATR,
    KEY_LEVEL_BREAK_HOLD_MIN_SL_BUFFER_PRICE,
    KEY_LEVEL_BREAK_HOLD_MAX_SL_DISTANCE_PRICE,
    KEY_LEVEL_BREAK_HOLD_TARGET_RR,
    KEY_LEVEL_BREAK_HOLD_MIN_TP_DISTANCE_PRICE,
)


STRATEGY_NAME = "KEY_LEVEL_BREAK_HOLD"


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _count_level_touches(values, level, tolerance):
    if tolerance <= 0:
        return 0

    count = 0

    for value in values:
        value = _safe_float(value)

        if value is None:
            continue

        if abs(value - level) <= tolerance:
            count += 1

    return count


def _build_context(df):
    required = KEY_LEVEL_BREAK_HOLD_LOOKBACK_BARS + 6

    if len(df) < required:
        return None

    # closed candles only:
    # - level window excludes the latest breakout/hold candles
    # - breakout candle = df.iloc[-3]
    # - hold candle = df.iloc[-2]
    level_window = df.iloc[-KEY_LEVEL_BREAK_HOLD_LOOKBACK_BARS - 4:-4]
    breakout_candle = df.iloc[-3]
    hold_candle = df.iloc[-2]

    atr = _safe_float(hold_candle.get("atr_14"))
    ema = _safe_float(hold_candle.get("ema_20"))

    if atr is None or atr <= 0:
        return None

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    resistance = float(level_window["high"].max())
    support = float(level_window["low"].min())

    touch_tolerance = max(atr * KEY_LEVEL_BREAK_HOLD_TOUCH_TOLERANCE_ATR, 0.50)

    resistance_touches = _count_level_touches(
        level_window["high"].tail(KEY_LEVEL_BREAK_HOLD_LOOKBACK_BARS),
        resistance,
        touch_tolerance,
    )

    support_touches = _count_level_touches(
        level_window["low"].tail(KEY_LEVEL_BREAK_HOLD_LOOKBACK_BARS),
        support,
        touch_tolerance,
    )

    return {
        "level_window": level_window,
        "breakout_candle": breakout_candle,
        "hold_candle": hold_candle,
        "atr": atr,
        "ema": ema,
        "resistance": resistance,
        "support": support,
        "resistance_touches": resistance_touches,
        "support_touches": support_touches,
    }


def _score_base(touches, breakout_distance, atr, hold_quality_bonus):
    score = KEY_LEVEL_BREAK_HOLD_MIN_SCORE

    if touches >= KEY_LEVEL_BREAK_HOLD_MIN_LEVEL_TOUCHES + 1:
        score += 3

    if touches >= KEY_LEVEL_BREAK_HOLD_MIN_LEVEL_TOUCHES + 2:
        score += 3

    if breakout_distance <= atr * 0.35:
        score += 3

    if hold_quality_bonus:
        score += 3

    return min(score, 100)


def _sl_buffer(atr):
    return max(KEY_LEVEL_BREAK_HOLD_MIN_SL_BUFFER_PRICE, atr * KEY_LEVEL_BREAK_HOLD_SL_BUFFER_ATR)


def _build_trade_references(signal, entry_price, level, breakout_candle, hold_candle, atr):
    sl_buffer = _sl_buffer(atr)

    if signal == "BUY":
        structural_low = min(
            _safe_float(breakout_candle.get("low"), entry_price),
            _safe_float(hold_candle.get("low"), entry_price),
            level,
        )
        sl_reference = round(structural_low - sl_buffer, 2)
        stop_distance = entry_price - sl_reference

        if stop_distance <= 0:
            return None

        if stop_distance > KEY_LEVEL_BREAK_HOLD_MAX_SL_DISTANCE_PRICE:
            return None

        tp_distance = max(
            stop_distance * KEY_LEVEL_BREAK_HOLD_TARGET_RR,
            KEY_LEVEL_BREAK_HOLD_MIN_TP_DISTANCE_PRICE,
        )
        tp_reference = round(entry_price + tp_distance, 2)

    else:
        structural_high = max(
            _safe_float(breakout_candle.get("high"), entry_price),
            _safe_float(hold_candle.get("high"), entry_price),
            level,
        )
        sl_reference = round(structural_high + sl_buffer, 2)
        stop_distance = sl_reference - entry_price

        if stop_distance <= 0:
            return None

        if stop_distance > KEY_LEVEL_BREAK_HOLD_MAX_SL_DISTANCE_PRICE:
            return None

        tp_distance = max(
            stop_distance * KEY_LEVEL_BREAK_HOLD_TARGET_RR,
            KEY_LEVEL_BREAK_HOLD_MIN_TP_DISTANCE_PRICE,
        )
        tp_reference = round(entry_price - tp_distance, 2)

    return {
        "sl_reference": sl_reference,
        "tp_reference": tp_reference,
        "stop_distance": round(stop_distance, 2),
        "tp_distance": round(tp_distance, 2),
    }


def generate_signal(df):
    context = _build_context(df)

    if context is None:
        return None

    breakout = context["breakout_candle"]
    hold = context["hold_candle"]

    atr = context["atr"]
    ema = context["ema"]

    resistance = context["resistance"]
    support = context["support"]
    resistance_touches = context["resistance_touches"]
    support_touches = context["support_touches"]

    break_buffer = max(atr * KEY_LEVEL_BREAK_HOLD_BREAK_BUFFER_ATR, 0.40)
    hold_buffer = max(atr * KEY_LEVEL_BREAK_HOLD_HOLD_BUFFER_ATR, 0.20)

    breakout_open = _safe_float(breakout.get("open"))
    breakout_high = _safe_float(breakout.get("high"))
    breakout_low = _safe_float(breakout.get("low"))
    breakout_close = _safe_float(breakout.get("close"))

    hold_open = _safe_float(hold.get("open"))
    hold_high = _safe_float(hold.get("high"))
    hold_low = _safe_float(hold.get("low"))
    hold_close = _safe_float(hold.get("close"))

    if None in {
        breakout_open,
        breakout_high,
        breakout_low,
        breakout_close,
        hold_open,
        hold_high,
        hold_low,
        hold_close,
        ema,
    }:
        return None

    breakout_body = abs(breakout_close - breakout_open)
    hold_body = abs(hold_close - hold_open)

    min_body = atr * KEY_LEVEL_BREAK_HOLD_MIN_BODY_ATR

    if breakout_body < min_body and hold_body < min_body:
        return None

    # =========================
    # BUY: resistance break, then hold above broken level
    # =========================
    buy_level_valid = resistance_touches >= KEY_LEVEL_BREAK_HOLD_MIN_LEVEL_TOUCHES
    buy_break = (
        breakout_close > resistance + break_buffer
        and breakout_high > resistance + break_buffer
        and breakout_close > breakout_open
    )
    buy_hold = (
        hold_low >= resistance - hold_buffer
        and hold_close > resistance + hold_buffer
        and hold_close > ema
    )

    if buy_level_valid and buy_break and buy_hold:
        breakout_distance = hold_close - resistance

        if breakout_distance <= 0:
            return None

        if breakout_distance > atr * KEY_LEVEL_BREAK_HOLD_MAX_EXTENSION_ATR:
            return None

        refs = _build_trade_references("BUY", hold_close, resistance, breakout, hold, atr)

        if refs is None:
            return None

        hold_quality_bonus = hold_close > breakout_close or hold_low >= resistance
        score = _score_base(resistance_touches, breakout_distance, atr, hold_quality_bonus)

        return {
            "signal": "BUY",
            "score": score,
            "strategy": STRATEGY_NAME,
            "entry_model": "KEY_LEVEL_BREAK_HOLD_BUY",
            "sl_model": "BROKEN_RESISTANCE_HOLD_SL",
            "tp_model": "RR_EXTENSION_TP",
            "sl_reference": refs["sl_reference"],
            "tp_reference": refs["tp_reference"],
            "key_level": round(resistance, 2),
            "level_type": "BROKEN_RESISTANCE",
            "level_touches": resistance_touches,
            "breakout_distance": round(breakout_distance, 2),
            "stop_distance": refs["stop_distance"],
            "tp_distance": refs["tp_distance"],
            "breakout_close": round(breakout_close, 2),
            "hold_close": round(hold_close, 2),
            "reason": (
                f"KEY_LEVEL_BREAK_HOLD BUY -> resistance {round(resistance, 2)} "
                f"broken and held -> touches {resistance_touches} -> "
                f"SL {refs['sl_reference']} -> TP {refs['tp_reference']}"
            ),
        }

    # =========================
    # SELL: support break, then hold below broken level
    # =========================
    sell_level_valid = support_touches >= KEY_LEVEL_BREAK_HOLD_MIN_LEVEL_TOUCHES
    sell_break = (
        breakout_close < support - break_buffer
        and breakout_low < support - break_buffer
        and breakout_close < breakout_open
    )
    sell_hold = (
        hold_high <= support + hold_buffer
        and hold_close < support - hold_buffer
        and hold_close < ema
    )

    if sell_level_valid and sell_break and sell_hold:
        breakout_distance = support - hold_close

        if breakout_distance <= 0:
            return None

        if breakout_distance > atr * KEY_LEVEL_BREAK_HOLD_MAX_EXTENSION_ATR:
            return None

        refs = _build_trade_references("SELL", hold_close, support, breakout, hold, atr)

        if refs is None:
            return None

        hold_quality_bonus = hold_close < breakout_close or hold_high <= support
        score = _score_base(support_touches, breakout_distance, atr, hold_quality_bonus)

        return {
            "signal": "SELL",
            "score": score,
            "strategy": STRATEGY_NAME,
            "entry_model": "KEY_LEVEL_BREAK_HOLD_SELL",
            "sl_model": "BROKEN_SUPPORT_HOLD_SL",
            "tp_model": "RR_EXTENSION_TP",
            "sl_reference": refs["sl_reference"],
            "tp_reference": refs["tp_reference"],
            "key_level": round(support, 2),
            "level_type": "BROKEN_SUPPORT",
            "level_touches": support_touches,
            "breakout_distance": round(breakout_distance, 2),
            "stop_distance": refs["stop_distance"],
            "tp_distance": refs["tp_distance"],
            "breakout_close": round(breakout_close, 2),
            "hold_close": round(hold_close, 2),
            "reason": (
                f"KEY_LEVEL_BREAK_HOLD SELL -> support {round(support, 2)} "
                f"broken and held -> touches {support_touches} -> "
                f"SL {refs['sl_reference']} -> TP {refs['tp_reference']}"
            ),
        }

    return None
