from config.settings import ATR_MIN, ATR_MAX


EXTREME_LOOKBACK = 30

MIN_EXTREME_MOVE_ATR = 1.8
MIN_BODY_ATR = 0.25
MIN_RECLAIM_BODY_ATR = 0.20

SWEEP_BUFFER_ATR = 0.10

SL_ATR_BUFFER = 0.20
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 6.0

TARGET_ATR_MIN = 1.5
TARGET_ATR_MAX = 3.5


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, structure_range):
    return min(
        max(structure_range * 0.50, atr * TARGET_ATR_MIN),
        atr * TARGET_ATR_MAX,
    )


def _score_setup(base_score, extreme_move, atr, reclaim_body, structure_shift, ema_reclaim):
    score = base_score

    if extreme_move > atr * 2.2:
        score += 2

    if extreme_move > atr * 2.8:
        score += 2

    if reclaim_body > atr * 0.35:
        score += 2

    if structure_shift:
        score += 3

    if ema_reclaim:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < EXTREME_LOOKBACK + 5:
        return None

    entry = df.iloc[-2]
    prev = df.iloc[-3]
    impulse = df.iloc[-4]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    recent = df.iloc[-EXTREME_LOOKBACK:-4]

    recent_high = recent["high"].max()
    recent_low = recent["low"].min()
    structure_range = recent_high - recent_low

    if structure_range <= 0:
        return None

    impulse_body = abs(impulse["close"] - impulse["open"])
    entry_body = abs(entry["close"] - entry["open"])
    entry_range = entry["high"] - entry["low"]

    if impulse_body < atr * MIN_BODY_ATR:
        return None

    if entry_body < atr * MIN_RECLAIM_BODY_ATR:
        return None

    if entry_range <= 0:
        return None

    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, structure_range)

    # =========================
    # BUY: extreme sell-side sweep + bullish reclaim
    # =========================
    extreme_selloff = (
        impulse["close"] < impulse["open"]
        and impulse_body >= atr * MIN_EXTREME_MOVE_ATR
    )

    swept_recent_low = (
        impulse["low"] < recent_low - atr * SWEEP_BUFFER_ATR
        or entry["low"] < recent_low - atr * SWEEP_BUFFER_ATR
    )

    bullish_reclaim = (
        entry["close"] > entry["open"]
        and entry["close"] > recent_low
        and entry["close"] > prev["high"]
    )

    bullish_structure_shift = entry["close"] > prev["high"]
    ema_reclaim = price > ema

    if extreme_selloff and swept_recent_low and bullish_reclaim:
        sl_reference = round(min(impulse["low"], entry["low"]) - sl_buffer, 2)

        if recent_high > entry["close"]:
            tp_reference = recent_high
            target_model = "RECENT_STRUCTURE_HIGH"
        elif ema > entry["close"]:
            tp_reference = ema
            target_model = "EMA_RECLAIM_TARGET"
        else:
            tp_reference = entry["close"] + target_distance
            target_model = "EXTREME_RECLAIM_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            extreme_move=impulse_body,
            atr=atr,
            reclaim_body=entry_body,
            structure_shift=bullish_structure_shift,
            ema_reclaim=ema_reclaim,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "EXTREME_SWEEP_RECLAIM",
            "entry_model": "EXTREME_SELLSIDE_SWEEP_BULLISH_RECLAIM",
            "pattern_height": abs(tp_reference - entry["close"]),
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sweep_low": min(impulse["low"], entry["low"]),
            "impulse_body": round(impulse_body, 2),
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_reclaim_after_extreme_selloff",
            "direction_context": "sell_side_sweep_reclaim",
            "reason": (
                f"Extreme sweep reclaim BUY -> selloff swept recent low {round(recent_low, 2)} -> "
                f"bullish reclaim above previous high -> SL {sl_reference} -> "
                f"TP {target_model} {tp_reference}"
            ),
        }

    # =========================
    # SELL: extreme buy-side sweep + bearish reclaim
    # =========================
    extreme_buyup = (
        impulse["close"] > impulse["open"]
        and impulse_body >= atr * MIN_EXTREME_MOVE_ATR
    )

    swept_recent_high = (
        impulse["high"] > recent_high + atr * SWEEP_BUFFER_ATR
        or entry["high"] > recent_high + atr * SWEEP_BUFFER_ATR
    )

    bearish_reclaim = (
        entry["close"] < entry["open"]
        and entry["close"] < recent_high
        and entry["close"] < prev["low"]
    )

    bearish_structure_shift = entry["close"] < prev["low"]
    ema_reclaim = price < ema

    if extreme_buyup and swept_recent_high and bearish_reclaim:
        sl_reference = round(max(impulse["high"], entry["high"]) + sl_buffer, 2)

        if recent_low < entry["close"]:
            tp_reference = recent_low
            target_model = "RECENT_STRUCTURE_LOW"
        elif ema < entry["close"]:
            tp_reference = ema
            target_model = "EMA_RECLAIM_TARGET"
        else:
            tp_reference = entry["close"] - target_distance
            target_model = "EXTREME_RECLAIM_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            extreme_move=impulse_body,
            atr=atr,
            reclaim_body=entry_body,
            structure_shift=bearish_structure_shift,
            ema_reclaim=ema_reclaim,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "EXTREME_SWEEP_RECLAIM",
            "entry_model": "EXTREME_BUYSIDE_SWEEP_BEARISH_RECLAIM",
            "pattern_height": abs(entry["close"] - tp_reference),
            "recent_high": recent_high,
            "recent_low": recent_low,
            "sweep_high": max(impulse["high"], entry["high"]),
            "impulse_body": round(impulse_body, 2),
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_reclaim_after_extreme_buyup",
            "direction_context": "buy_side_sweep_reclaim",
            "reason": (
                f"Extreme sweep reclaim SELL -> buyup swept recent high {round(recent_high, 2)} -> "
                f"bearish reclaim below previous low -> SL {sl_reference} -> "
                f"TP {target_model} {tp_reference}"
            ),
        }

    return None