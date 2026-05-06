from src.logger import logger


SR_LOOKBACK = 30
STRUCTURE_LOOKBACK = 8

MIN_BODY_ATR_RATIO = 0.18
MIN_WICK_BODY_RATIO = 1.0
MIN_CLOSE_POSITION = 0.60

SL_ATR_BUFFER = 0.20
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 5.0

TARGET_ATR_MIN = 1.5
TARGET_ATR_MAX = 3.0


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, structure_range):
    return min(
        max(structure_range * 0.60, atr * TARGET_ATR_MIN),
        atr * TARGET_ATR_MAX,
    )


def _score_context(base_score, body, atr, liquidity_sweep, structure_shift, rejection_quality):
    score = base_score

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.50:
        score += 2

    if liquidity_sweep:
        score += 3

    if structure_shift:
        score += 3

    if rejection_quality:
        score += 2

    return min(score, 99)


def analyze_structure_liquidity(df):
    """
    Combines support/resistance, structure shift, and liquidity sweep.

    Uses closed candles only.
    Returns a context dict if a valid BUY/SELL confluence exists.
    """
    if len(df) < SR_LOOKBACK + 5:
        return None

    closed = df.iloc[:-1]

    entry = closed.iloc[-1]
    prev = closed.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]

    if atr <= 0:
        return None

    sr_data = closed.iloc[-(SR_LOOKBACK + 1):-1]
    structure_data = closed.iloc[-(STRUCTURE_LOOKBACK + 1):-1]

    support = sr_data["low"].min()
    resistance = sr_data["high"].max()
    structure_range = resistance - support

    if structure_range <= 0:
        return None

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return None

    if body < atr * MIN_BODY_ATR_RATIO:
        return None

    upper_wick = entry["high"] - max(entry["open"], entry["close"])
    lower_wick = min(entry["open"], entry["close"]) - entry["low"]

    close_from_low = (entry["close"] - entry["low"]) / candle_range
    close_from_high = (entry["high"] - entry["close"]) / candle_range

    recent_structure_high = structure_data["high"].max()
    recent_structure_low = structure_data["low"].min()

    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, structure_range)

    # =========================
    # BUY confluence
    # =========================
    sell_side_sweep = entry["low"] < support
    reclaim_support = entry["close"] > support
    bullish_rejection = (
        entry["close"] > entry["open"]
        and lower_wick > body * MIN_WICK_BODY_RATIO
        and close_from_low >= MIN_CLOSE_POSITION
    )
    bullish_structure_shift = entry["close"] > prev["high"] or entry["close"] > recent_structure_high
    bullish_context = entry["close"] > ema or bullish_structure_shift

    if (
        sell_side_sweep
        and reclaim_support
        and bullish_rejection
        and bullish_structure_shift
        and bullish_context
    ):
        sl_reference = round(entry["low"] - sl_buffer, 2)

        if resistance > entry["close"]:
            tp_reference = resistance
            target_model = "NEXT_RESISTANCE"
        else:
            tp_reference = entry["close"] + target_distance
            target_model = "STRUCTURE_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _score_context(
            base_score=92,
            body=body,
            atr=atr,
            liquidity_sweep=True,
            structure_shift=True,
            rejection_quality=close_from_low >= 0.70,
        )

        return {
            "bias": "BUY",
            "score": score,
            "support": support,
            "resistance": resistance,
            "sweep_level": entry["low"],
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_sweep_reclaim_bos",
            "direction_context": "support_sweep_bullish_structure_shift",
            "reasons": [
                "support_swept",
                "support_reclaimed",
                "bullish_rejection",
                "bullish_structure_shift",
            ],
        }

    # =========================
    # SELL confluence
    # =========================
    buy_side_sweep = entry["high"] > resistance
    reject_resistance = entry["close"] < resistance
    bearish_rejection = (
        entry["close"] < entry["open"]
        and upper_wick > body * MIN_WICK_BODY_RATIO
        and close_from_high >= MIN_CLOSE_POSITION
    )
    bearish_structure_shift = entry["close"] < prev["low"] or entry["close"] < recent_structure_low
    bearish_context = entry["close"] < ema or bearish_structure_shift

    if (
        buy_side_sweep
        and reject_resistance
        and bearish_rejection
        and bearish_structure_shift
        and bearish_context
    ):
        sl_reference = round(entry["high"] + sl_buffer, 2)

        if support < entry["close"]:
            tp_reference = support
            target_model = "NEXT_SUPPORT"
        else:
            tp_reference = entry["close"] - target_distance
            target_model = "STRUCTURE_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _score_context(
            base_score=92,
            body=body,
            atr=atr,
            liquidity_sweep=True,
            structure_shift=True,
            rejection_quality=close_from_high >= 0.70,
        )

        return {
            "bias": "SELL",
            "score": score,
            "support": support,
            "resistance": resistance,
            "sweep_level": entry["high"],
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_sweep_reclaim_bos",
            "direction_context": "resistance_sweep_bearish_structure_shift",
            "reasons": [
                "resistance_swept",
                "resistance_rejected",
                "bearish_rejection",
                "bearish_structure_shift",
            ],
        }

    logger.info("[STRUCTURE LIQUIDITY] No valid confluence")
    return None

def apply_structure_liquidity_confirmation(signal_data, context):
    """
    Uses structure/liquidity confluence as a confirmation layer.

    It does not generate a new signal here.
    It only adjusts score/reasons for another strategy.
    """
    if not signal_data or context is None:
        return 0, []

    signal = signal_data.get("signal")
    strategy = signal_data.get("strategy")

    if signal not in ["BUY", "SELL"]:
        return 0, []

    # Do not confirm itself
    if strategy == "STRUCTURE_LIQUIDITY":
        return 0, []

    context_bias = context.get("bias")
    context_score = context.get("score", 0)
    context_reasons = context.get("reasons", [])

    if context_bias == signal:
        return 3, [
            "structure_liquidity_aligned",
            *context_reasons,
        ]

    if context_bias in ["BUY", "SELL"] and context_bias != signal:
        return -2, [
            f"structure_liquidity_conflict_{context_bias.lower()}",
        ]

    return 0, []