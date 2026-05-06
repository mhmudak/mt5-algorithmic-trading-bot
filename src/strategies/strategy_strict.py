from config.settings import (
    ATR_MIN,
    ATR_MAX,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
)


STRICT_MIN_BREAKOUT_BODY_ATR = 0.50
STRICT_MIN_ENTRY_BODY_ATR = 0.25
STRICT_MAX_EXTENSION_ATR = 0.80

STRICT_SL_ATR_MULTIPLIER = 0.20
STRICT_MIN_SL_BUFFER = 1.5
STRICT_MAX_SL_BUFFER = 5.0

STRICT_TARGET_RANGE_MULTIPLIER = 0.75
STRICT_MIN_TARGET_ATR = 1.3
STRICT_MAX_TARGET_ATR = 3.0


def _sl_buffer(atr):
    return min(
        max(atr * STRICT_SL_ATR_MULTIPLIER, STRICT_MIN_SL_BUFFER),
        STRICT_MAX_SL_BUFFER,
    )


def _target_distance(atr, structure_range):
    return min(
        max(structure_range * STRICT_TARGET_RANGE_MULTIPLIER, atr * STRICT_MIN_TARGET_ATR),
        atr * STRICT_MAX_TARGET_ATR,
    )


def _score_setup(base_score, breakout_body, entry_body, atr, close_aligned):
    score = base_score

    if breakout_body > atr * 0.70:
        score += 2

    if breakout_body > atr * 1.00:
        score += 2

    if entry_body > atr * 0.35:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < BREAKOUT_LOOKBACK + 8:
        return None

    entry = df.iloc[-2]
    breakout = df.iloc[-3]

    price = entry["close"]
    ema = entry["ema_20"]
    atr = entry["atr_14"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    if abs(price - ema) > atr * 1.5:
        return None

    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 3):-3]
    resistance = recent_data["high"].max()
    support = recent_data["low"].min()

    structure_range = resistance - support
    if structure_range <= 0:
        return None

    breakout_body = abs(breakout["close"] - breakout["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if breakout_body < atr * STRICT_MIN_BREAKOUT_BODY_ATR:
        return None

    if entry_body < atr * STRICT_MIN_ENTRY_BODY_ATR:
        return None

    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, structure_range)

    # =========================
    # BUY: strict breakout above resistance
    # =========================
    breakout_up = (
        breakout["close"] > resistance + BREAKOUT_BUFFER
        and breakout["close"] > breakout["open"]
    )

    bullish_entry = (
        entry["close"] > entry["open"]
        and entry["close"] > resistance
        and price > ema
    )

    extension = entry["close"] - resistance
    not_chasing = extension >= 0 and extension <= atr * STRICT_MAX_EXTENSION_ATR

    if breakout_up and bullish_entry and not_chasing:
        sl_reference = round(resistance - sl_buffer, 2)
        tp_reference = round(entry["close"] + target_distance, 2)

        if sl_reference >= entry["close"]:
            return None

        if tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=90,
            breakout_body=breakout_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "STRICT",
            "entry_model": "STRICT_BREAKOUT_CONTINUATION",
            "pattern_height": target_distance,
            "breakout_level": resistance,
            "support": support,
            "resistance": resistance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "STRICT_RANGE_EXTENSION",
            "momentum": "bullish_strict_breakout",
            "direction_context": "price_above_ema",
            "reason": (
                f"Strict BUY breakout -> resistance {round(resistance, 2)} broken -> "
                f"strong breakout body {round(breakout_body, 2)} -> "
                f"SL below breakout level {sl_reference} -> "
                f"TP strict extension {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # SELL: strict breakdown below support
    # =========================
    breakout_down = (
        breakout["close"] < support - BREAKOUT_BUFFER
        and breakout["close"] < breakout["open"]
    )

    bearish_entry = (
        entry["close"] < entry["open"]
        and entry["close"] < support
        and price < ema
    )

    extension = support - entry["close"]
    not_chasing = extension >= 0 and extension <= atr * STRICT_MAX_EXTENSION_ATR

    if breakout_down and bearish_entry and not_chasing:
        sl_reference = round(support + sl_buffer, 2)
        tp_reference = round(entry["close"] - target_distance, 2)

        if sl_reference <= entry["close"]:
            return None

        if tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=90,
            breakout_body=breakout_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "STRICT",
            "entry_model": "STRICT_BREAKDOWN_CONTINUATION",
            "pattern_height": target_distance,
            "breakout_level": support,
            "support": support,
            "resistance": resistance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "STRICT_RANGE_EXTENSION",
            "momentum": "bearish_strict_breakdown",
            "direction_context": "price_below_ema",
            "reason": (
                f"Strict SELL breakdown -> support {round(support, 2)} broken -> "
                f"strong breakout body {round(breakout_body, 2)} -> "
                f"SL above breakdown level {sl_reference} -> "
                f"TP strict extension {tp_reference} -> price below EMA"
            ),
        }

    return None