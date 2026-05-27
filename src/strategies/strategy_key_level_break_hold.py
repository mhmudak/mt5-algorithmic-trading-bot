from config.settings import ATR_MIN, ATR_MAX


KEY_LEVEL_LOOKBACK = 48
KEY_LEVEL_BREAK_BUFFER_ATR = 0.12
KEY_LEVEL_MIN_BREAK_BODY_ATR = 0.25
KEY_LEVEL_MAX_EXTENSION_ATR = 0.80
KEY_LEVEL_SL_BUFFER_ATR = 0.20
KEY_LEVEL_MIN_SL_BUFFER = 1.0
KEY_LEVEL_MAX_SL_BUFFER = 4.0


def _buffer(atr, multiplier, min_value=0.0, max_value=None):
    value = atr * multiplier
    value = max(value, min_value)

    if max_value is not None:
        value = min(value, max_value)

    return value


def _score_setup(base_score, break_body, hold_body, atr, ema_aligned, level_retest):
    score = base_score

    if break_body > atr * 0.40:
        score += 4

    if hold_body > atr * 0.20:
        score += 3

    if ema_aligned:
        score += 3

    if level_retest:
        score += 3

    return min(score, 99)


def generate_signal(df):
    if len(df) < KEY_LEVEL_LOOKBACK + 5:
        return None

    break_candle = df.iloc[-3]
    hold_candle = df.iloc[-2]

    atr = hold_candle["atr_14"]
    ema = hold_candle["ema_20"]
    price = hold_candle["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    break_body = abs(break_candle["close"] - break_candle["open"])
    hold_body = abs(hold_candle["close"] - hold_candle["open"])

    if break_body <= 0 or hold_body <= 0:
        return None

    structure = df.iloc[-(KEY_LEVEL_LOOKBACK + 3):-3]

    resistance = structure["high"].max()
    support = structure["low"].min()

    break_buffer = _buffer(atr, KEY_LEVEL_BREAK_BUFFER_ATR)
    sl_buffer = _buffer(
        atr,
        KEY_LEVEL_SL_BUFFER_ATR,
        KEY_LEVEL_MIN_SL_BUFFER,
        KEY_LEVEL_MAX_SL_BUFFER,
    )

    recent_range = resistance - support

    if recent_range <= 0:
        return None

    # =========================
    # BUY: resistance break + hold
    # =========================
    broke_resistance = (
        break_candle["close"] > resistance + break_buffer
        and break_candle["close"] > break_candle["open"]
        and break_body >= atr * KEY_LEVEL_MIN_BREAK_BODY_ATR
    )

    held_above_resistance = (
        hold_candle["close"] > resistance + break_buffer
        and hold_candle["close"] > hold_candle["open"]
    )

    buy_extension = hold_candle["close"] - resistance

    buy_too_extended = buy_extension > atr * KEY_LEVEL_MAX_EXTENSION_ATR

    buy_retest = hold_candle["low"] <= resistance + break_buffer

    if (
        broke_resistance
        and held_above_resistance
        and not buy_too_extended
        and price > ema
    ):
        sl_reference = round(resistance - sl_buffer, 2)
        tp_reference = round(price + min(recent_range * 0.50, atr * 2.2), 2)

        score = _score_setup(
            base_score=88,
            break_body=break_body,
            hold_body=hold_body,
            atr=atr,
            ema_aligned=price > ema,
            level_retest=buy_retest,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "KEY_LEVEL_BREAK_HOLD",
            "entry_model": "RESISTANCE_BREAK_HOLD",
            "pattern_height": recent_range,
            "key_level": round(resistance, 2),
            "recent_high": round(resistance, 2),
            "recent_low": round(support, 2),
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "MEASURED_KEY_LEVEL_EXTENSION",
            "momentum": "bullish_key_level_break_hold",
            "direction_context": "price_above_ema",
            "reason": (
                f"Key level BUY -> resistance {round(resistance, 2)} broken "
                f"and held -> SL below level {sl_reference} -> "
                f"TP measured extension {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # SELL: support break + hold
    # =========================
    broke_support = (
        break_candle["close"] < support - break_buffer
        and break_candle["close"] < break_candle["open"]
        and break_body >= atr * KEY_LEVEL_MIN_BREAK_BODY_ATR
    )

    held_below_support = (
        hold_candle["close"] < support - break_buffer
        and hold_candle["close"] < hold_candle["open"]
    )

    sell_extension = support - hold_candle["close"]

    sell_too_extended = sell_extension > atr * KEY_LEVEL_MAX_EXTENSION_ATR

    sell_retest = hold_candle["high"] >= support - break_buffer

    if (
        broke_support
        and held_below_support
        and not sell_too_extended
        and price < ema
    ):
        sl_reference = round(support + sl_buffer, 2)
        tp_reference = round(price - min(recent_range * 0.50, atr * 2.2), 2)

        score = _score_setup(
            base_score=88,
            break_body=break_body,
            hold_body=hold_body,
            atr=atr,
            ema_aligned=price < ema,
            level_retest=sell_retest,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "KEY_LEVEL_BREAK_HOLD",
            "entry_model": "SUPPORT_BREAK_HOLD",
            "pattern_height": recent_range,
            "key_level": round(support, 2),
            "recent_high": round(resistance, 2),
            "recent_low": round(support, 2),
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "MEASURED_KEY_LEVEL_EXTENSION",
            "momentum": "bearish_key_level_break_hold",
            "direction_context": "price_below_ema",
            "reason": (
                f"Key level SELL -> support {round(support, 2)} broken "
                f"and held -> SL above level {sl_reference} -> "
                f"TP measured extension {tp_reference} -> price below EMA"
            ),
        }

    return None