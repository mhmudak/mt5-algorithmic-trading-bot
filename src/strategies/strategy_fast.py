from config.settings import (
    ATR_MIN,
    ATR_MAX,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
)


FAST_MIN_BREAKOUT_BODY_ATR = 0.30
FAST_MIN_ENTRY_BODY_ATR = 0.20
FAST_MAX_EXTENSION_ATR = 0.60

FAST_SL_ATR_MULTIPLIER = 0.20
FAST_MIN_SL_BUFFER = 1.5
FAST_MAX_SL_BUFFER = 4.0

FAST_TARGET_RANGE_MULTIPLIER = 0.60
FAST_MIN_TARGET_ATR = 1.0
FAST_MAX_TARGET_ATR = 2.2


def _sl_buffer(atr):
    return min(
        max(atr * FAST_SL_ATR_MULTIPLIER, FAST_MIN_SL_BUFFER),
        FAST_MAX_SL_BUFFER,
    )


def _target_distance(atr, structure_range):
    return min(
        max(structure_range * FAST_TARGET_RANGE_MULTIPLIER, atr * FAST_MIN_TARGET_ATR),
        atr * FAST_MAX_TARGET_ATR,
    )


def _score_setup(base_score, breakout_body, entry_body, atr, close_aligned):
    score = base_score

    if breakout_body > atr * 0.45:
        score += 3

    if entry_body > atr * 0.30:
        score += 2

    if close_aligned:
        score += 3

    return min(score, 90)


def generate_signal(df):
    if len(df) < BREAKOUT_LOOKBACK + 5:
        return None

    # Closed candles only:
    # entry = latest closed candle
    # breakout = candle before entry
    entry = df.iloc[-2]
    breakout = df.iloc[-3]

    price = entry["close"]
    ema = entry["ema_20"]
    atr = entry["atr_14"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    if abs(price - ema) > atr * 1.20:
        return None

    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 3):-3]
    resistance = recent_data["high"].max()
    support = recent_data["low"].min()

    structure_range = resistance - support
    if structure_range <= 0:
        return None

    breakout_body = abs(breakout["close"] - breakout["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if breakout_body < atr * FAST_MIN_BREAKOUT_BODY_ATR:
        return None

    if entry_body < atr * FAST_MIN_ENTRY_BODY_ATR:
        return None

    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, structure_range)

    # =========================
    # BUY fast continuation
    # =========================
    breakout_up = (
        breakout["close"] > resistance + BREAKOUT_BUFFER
        and breakout["close"] > breakout["open"]
    )

    bullish_continuation = (
        entry["close"] > entry["open"]
        and entry["close"] > resistance
        and price > ema
    )

    extension = entry["close"] - resistance
    not_chasing = extension >= 0 and extension <= atr * FAST_MAX_EXTENSION_ATR

    if breakout_up and bullish_continuation and not_chasing:
        sl_reference = round(resistance - sl_buffer, 2)
        tp_reference = round(entry["close"] + target_distance, 2)

        if sl_reference >= entry["close"]:
            return None

        if tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=55,
            breakout_body=breakout_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "FAST",
            "entry_model": "FAST_BREAKOUT_CONTINUATION",
            "pattern_height": target_distance,
            "breakout_level": resistance,
            "support": support,
            "resistance": resistance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "FAST_RANGE_EXTENSION",
            "momentum": "bullish_fast_breakout",
            "direction_context": "price_above_ema",
            "reason": (
                f"Fast BUY continuation -> resistance {round(resistance, 2)} broken -> "
                f"closed continuation above level -> "
                f"SL below breakout level {sl_reference} -> "
                f"TP fast extension {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # SELL fast continuation
    # =========================
    breakout_down = (
        breakout["close"] < support - BREAKOUT_BUFFER
        and breakout["close"] < breakout["open"]
    )

    bearish_continuation = (
        entry["close"] < entry["open"]
        and entry["close"] < support
        and price < ema
    )

    extension = support - entry["close"]
    not_chasing = extension >= 0 and extension <= atr * FAST_MAX_EXTENSION_ATR

    if breakout_down and bearish_continuation and not_chasing:
        sl_reference = round(support + sl_buffer, 2)
        tp_reference = round(entry["close"] - target_distance, 2)

        if sl_reference <= entry["close"]:
            return None

        if tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=55,
            breakout_body=breakout_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "FAST",
            "entry_model": "FAST_BREAKDOWN_CONTINUATION",
            "pattern_height": target_distance,
            "breakout_level": support,
            "support": support,
            "resistance": resistance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "FAST_RANGE_EXTENSION",
            "momentum": "bearish_fast_breakdown",
            "direction_context": "price_below_ema",
            "reason": (
                f"Fast SELL continuation -> support {round(support, 2)} broken -> "
                f"closed continuation below level -> "
                f"SL above breakdown level {sl_reference} -> "
                f"TP fast extension {tp_reference} -> price below EMA"
            ),
        }

    return None