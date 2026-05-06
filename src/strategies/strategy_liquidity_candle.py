from config.settings import ATR_MIN, ATR_MAX


LIQUIDITY_CANDLE_SL_ATR_MULTIPLIER = 0.20
LIQUIDITY_CANDLE_MIN_SL_BUFFER = 2.0
LIQUIDITY_CANDLE_MAX_SL_BUFFER = 5.0


def _sl_buffer(atr):
    return min(
        max(atr * LIQUIDITY_CANDLE_SL_ATR_MULTIPLIER, LIQUIDITY_CANDLE_MIN_SL_BUFFER),
        LIQUIDITY_CANDLE_MAX_SL_BUFFER,
    )


def _score_setup(base_score, entry_body, atr, breakout_strength, close_aligned):
    score = base_score

    if entry_body > atr * 0.30:
        score += 2

    if entry_body > atr * 0.50:
        score += 2

    if breakout_strength > atr * 0.20:
        score += 2

    if close_aligned:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < 30:
        return None

    # candles
    entry = df.iloc[-2]
    liquidity = df.iloc[-3]
    prev = df.iloc[-4]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    # basic measures
    liquidity_range = liquidity["high"] - liquidity["low"]
    liquidity_body = abs(liquidity["close"] - liquidity["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if liquidity_range <= 0 or entry_body <= 0:
        return None

    upper_wick = liquidity["high"] - max(liquidity["open"], liquidity["close"])
    lower_wick = min(liquidity["open"], liquidity["close"]) - liquidity["low"]

    structure = df.iloc[-24:-4]
    recent_high = structure["high"].max()
    recent_low = structure["low"].min()

    sl_buffer = _sl_buffer(atr)

    # =========================================================
    # ANTI LATE ENTRY FILTER
    # =========================================================
    extension_up = abs(entry["close"] - liquidity["high"])
    extension_down = abs(entry["close"] - liquidity["low"])

    if extension_up > atr * 0.60 or extension_down > atr * 0.60:
        return None

    # =========================================================
    # BREAKOUT STRENGTH FILTER
    # =========================================================
    breakout_up_strength = entry["close"] - liquidity["high"]
    breakout_down_strength = liquidity["low"] - entry["close"]

    # =========================================================
    # SMT-LIKE BEHAVIOR
    # =========================================================
    failed_continuation_up = (
        prev["high"] < liquidity["high"]
        and entry["close"] < liquidity["high"] + atr * 0.05
    )

    failed_continuation_down = (
        prev["low"] > liquidity["low"]
        and entry["close"] > liquidity["low"] - atr * 0.05
    )

    # =========================================================
    # BULLISH SETUP
    # =========================================================
    bullish_liquidity = (
        lower_wick > liquidity_body * 1.5
        and liquidity_range > atr * 0.60
    )

    bullish_confirmation = (
        entry["close"] > entry["open"]
        and entry["close"] > liquidity["high"]
        and price > ema
        and entry_body > atr * 0.20
        and breakout_up_strength > atr * 0.10
        and not failed_continuation_up
    )

    if bullish_liquidity and bullish_confirmation:
        risk_height = entry["close"] - liquidity["low"]

        if risk_height <= 0:
            return None

        sl_reference = round(liquidity["low"] - sl_buffer, 2)

        if recent_high > entry["close"]:
            tp_reference = recent_high
            target_model = "RECENT_STRUCTURE_HIGH"
        else:
            tp_reference = entry["close"] + max(risk_height * 1.5, atr * 1.5)
            target_model = "MEASURED_LIQUIDITY_CANDLE_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=90,
            entry_body=entry_body,
            atr=atr,
            breakout_strength=breakout_up_strength,
            close_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "LIQUIDITY_CANDLE",
            "entry_model": "LIQUIDITY_CANDLE_BREAKOUT_RECLAIM",
            "pattern_height": risk_height,
            "liquidity_high": liquidity["high"],
            "liquidity_low": liquidity["low"],
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_liquidity_reclaim",
            "direction_context": "price_above_ema",
            "reason": (
                f"Bullish liquidity candle -> strong rejection from "
                f"{round(liquidity['low'], 2)} -> validated breakout above "
                f"{round(liquidity['high'], 2)} -> SL below liquidity low "
                f"{sl_reference} -> TP {target_model} {tp_reference} -> EMA aligned"
            ),
        }

    # =========================================================
    # BEARISH SETUP
    # =========================================================
    bearish_liquidity = (
        upper_wick > liquidity_body * 1.5
        and liquidity_range > atr * 0.60
    )

    bearish_confirmation = (
        entry["close"] < entry["open"]
        and entry["close"] < liquidity["low"]
        and price < ema
        and entry_body > atr * 0.20
        and breakout_down_strength > atr * 0.10
        and not failed_continuation_down
    )

    if bearish_liquidity and bearish_confirmation:
        risk_height = liquidity["high"] - entry["close"]

        if risk_height <= 0:
            return None

        sl_reference = round(liquidity["high"] + sl_buffer, 2)

        if recent_low < entry["close"]:
            tp_reference = recent_low
            target_model = "RECENT_STRUCTURE_LOW"
        else:
            tp_reference = entry["close"] - max(risk_height * 1.5, atr * 1.5)
            target_model = "MEASURED_LIQUIDITY_CANDLE_MOVE"

        tp_reference = round(tp_reference, 2)

        score = _score_setup(
            base_score=90,
            entry_body=entry_body,
            atr=atr,
            breakout_strength=breakout_down_strength,
            close_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "LIQUIDITY_CANDLE",
            "entry_model": "LIQUIDITY_CANDLE_BREAKDOWN_RECLAIM",
            "pattern_height": risk_height,
            "liquidity_high": liquidity["high"],
            "liquidity_low": liquidity["low"],
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_liquidity_reclaim",
            "direction_context": "price_below_ema",
            "reason": (
                f"Bearish liquidity candle -> strong rejection from "
                f"{round(liquidity['high'], 2)} -> validated breakdown below "
                f"{round(liquidity['low'], 2)} -> SL above liquidity high "
                f"{sl_reference} -> TP {target_model} {tp_reference} -> EMA aligned"
            ),
        }

    return None