from config.settings import (
    ATR_MIN,
    ATR_MAX,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
)


SNIPER_MIN_BREAKOUT_BODY_ATR = 0.35
SNIPER_MIN_ENTRY_BODY_ATR = 0.20

SNIPER_RETEST_ATR_BUFFER = 0.25
SNIPER_MIN_RETEST_BUFFER = 0.8

SNIPER_MAX_EXTENSION_ATR = 0.65

SNIPER_SL_ATR_MULTIPLIER = 0.20
SNIPER_MIN_SL_BUFFER = 1.5
SNIPER_MAX_SL_BUFFER = 5.0

SNIPER_TARGET_RANGE_MULTIPLIER = 0.75
SNIPER_MIN_TARGET_ATR = 1.2
SNIPER_MAX_TARGET_ATR = 3.0


def _sl_buffer(atr):
    return min(
        max(atr * SNIPER_SL_ATR_MULTIPLIER, SNIPER_MIN_SL_BUFFER),
        SNIPER_MAX_SL_BUFFER,
    )


def _target_distance(atr, breakout_range):
    return min(
        max(breakout_range * SNIPER_TARGET_RANGE_MULTIPLIER, atr * SNIPER_MIN_TARGET_ATR),
        atr * SNIPER_MAX_TARGET_ATR,
    )


def _score_setup(base_score, breakout_body, entry_body, atr, close_aligned, clean_retest):
    score = base_score

    if breakout_body > atr * 0.50:
        score += 3

    if breakout_body > atr * 0.75:
        score += 2

    if entry_body > atr * 0.30:
        score += 2

    if clean_retest:
        score += 3

    if close_aligned:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < BREAKOUT_LOOKBACK + 8:
        return None

    entry = df.iloc[-2]       # retest / reclaim candle
    breakout = df.iloc[-3]    # breakout candle

    price = entry["close"]
    ema = entry["ema_20"]
    atr = entry["atr_14"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    if abs(price - ema) > atr * 1.8:
        return None

    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 3):-3]
    resistance = recent_data["high"].max()
    support = recent_data["low"].min()

    breakout_range = resistance - support
    if breakout_range <= 0:
        return None

    breakout_body = abs(breakout["close"] - breakout["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if breakout_body < atr * SNIPER_MIN_BREAKOUT_BODY_ATR:
        return None

    if entry_body < atr * SNIPER_MIN_ENTRY_BODY_ATR:
        return None

    retest_buffer = max(atr * SNIPER_RETEST_ATR_BUFFER, SNIPER_MIN_RETEST_BUFFER)
    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, breakout_range)

    # =========================
    # BUY: breakout above resistance + retest/reclaim
    # =========================
    breakout_up = (
        breakout["close"] > resistance + BREAKOUT_BUFFER
        and breakout["close"] > breakout["open"]
    )

    retest_buy = (
        entry["low"] <= resistance + retest_buffer
        and entry["close"] > resistance
    )

    bullish_reclaim = (
        entry["close"] > entry["open"]
        and price > ema
    )

    extension_from_level = entry["close"] - resistance
    not_chasing = (
        extension_from_level >= 0
        and extension_from_level <= atr * SNIPER_MAX_EXTENSION_ATR
    )

    if breakout_up and retest_buy and bullish_reclaim and not_chasing:
        sl_reference = round(min(entry["low"], resistance) - sl_buffer, 2)
        tp_reference = round(entry["close"] + target_distance, 2)

        if sl_reference >= entry["close"]:
            return None

        if tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=75,
            breakout_body=breakout_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price > ema,
            clean_retest=retest_buy,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "SNIPER_V2",
            "entry_model": "SNIPER_BREAKOUT_RETEST",
            "pattern_height": target_distance,
            "breakout_level": resistance,
            "support": support,
            "resistance": resistance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "RANGE_EXTENSION_AFTER_RETEST",
            "momentum": "bullish_breakout_retest_reclaim",
            "direction_context": "price_above_ema",
            "reason": (
                f"Sniper BUY -> breakout above resistance {round(resistance, 2)} -> "
                f"retest/reclaim confirmed near {round(entry['low'], 2)} -> "
                f"SL below retest {sl_reference} -> "
                f"TP range extension {tp_reference} -> price above EMA"
            ),
        }

    # =========================
    # SELL: breakout below support + retest/reclaim
    # =========================
    breakout_down = (
        breakout["close"] < support - BREAKOUT_BUFFER
        and breakout["close"] < breakout["open"]
    )

    retest_sell = (
        entry["high"] >= support - retest_buffer
        and entry["close"] < support
    )

    bearish_reclaim = (
        entry["close"] < entry["open"]
        and price < ema
    )

    extension_from_level = support - entry["close"]
    not_chasing = (
        extension_from_level >= 0
        and extension_from_level <= atr * SNIPER_MAX_EXTENSION_ATR
    )

    if breakout_down and retest_sell and bearish_reclaim and not_chasing:
        sl_reference = round(max(entry["high"], support) + sl_buffer, 2)
        tp_reference = round(entry["close"] - target_distance, 2)

        if sl_reference <= entry["close"]:
            return None

        if tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=75,
            breakout_body=breakout_body,
            entry_body=entry_body,
            atr=atr,
            close_aligned=price < ema,
            clean_retest=retest_sell,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "SNIPER_V2",
            "entry_model": "SNIPER_BREAKDOWN_RETEST",
            "pattern_height": target_distance,
            "breakout_level": support,
            "support": support,
            "resistance": resistance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "RANGE_EXTENSION_AFTER_RETEST",
            "momentum": "bearish_breakdown_retest_reclaim",
            "direction_context": "price_below_ema",
            "reason": (
                f"Sniper SELL -> breakout below support {round(support, 2)} -> "
                f"retest/reclaim confirmed near {round(entry['high'], 2)} -> "
                f"SL above retest {sl_reference} -> "
                f"TP range extension {tp_reference} -> price below EMA"
            ),
        }

    return None