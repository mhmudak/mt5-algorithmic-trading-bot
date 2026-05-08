from config.settings import ATR_MIN, ATR_MAX, BREAKOUT_LOOKBACK, BREAKOUT_BUFFER
from src.execution_engine import get_recent_invalidated_setups


FAILED_BREAKOUT_MIN_BODY_ATR = 0.30
FAILED_BREAKOUT_MIN_SWEEP_ATR = 0.15
FAILED_BREAKOUT_MAX_EXTENSION_ATR = 1.50

SL_ATR_BUFFER = 0.20
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 5.0

TARGET_ATR_MIN = 1.5
TARGET_ATR_MAX = 3.0


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, structure_range):
    return min(
        max(structure_range * 0.70, atr * TARGET_ATR_MIN),
        atr * TARGET_ATR_MAX,
    )


def _score_setup(base_score, body, atr, sweep_depth, reclaim_strength, ema_aligned):
    score = base_score

    if body > atr * 0.40:
        score += 2

    if body > atr * 0.60:
        score += 2

    if sweep_depth > atr * 0.30:
        score += 2

    if reclaim_strength:
        score += 3

    if ema_aligned:
        score += 2

    return min(score, 99)


def _from_invalidated_orb(df):
    invalidated_orbs = get_recent_invalidated_setups(
        strategy="ORB",
        max_age_minutes=30,
    )

    if not invalidated_orbs:
        return None

    if len(df) < BREAKOUT_LOOKBACK + 8:
        return None

    entry = df.iloc[-2]
    prev = df.iloc[-3]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return None

    if body < atr * FAILED_BREAKOUT_MIN_BODY_ATR:
        return None

    recent = df.iloc[-(BREAKOUT_LOOKBACK + 4):-4]
    support = recent["low"].min()
    resistance = recent["high"].max()
    structure_range = resistance - support

    if structure_range <= 0:
        return None

    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, structure_range)

    latest_invalidated = invalidated_orbs[-1]
    original_signal = latest_invalidated.get("signal")
    data = latest_invalidated.get("data", {})

    orb_high = data.get("orb_high")
    orb_low = data.get("orb_low")

    if orb_high is None or orb_low is None:
        return None

    # =========================================================
    # Invalidated ORB BUY -> SELL reversal
    # =========================================================
    if original_signal == "BUY":
        failed_level = orb_high

        bearish_reversal = (
            entry["close"] < entry["open"]
            and entry["close"] < failed_level
            and entry["close"] < prev["low"]
        )

        if not bearish_reversal:
            return None

        sl_reference = round(max(entry["high"], failed_level) + sl_buffer, 2)

        if orb_low < entry["close"]:
            tp_reference = round(orb_low, 2)
            target_model = "ORB_LOW_TARGET"
        elif support < entry["close"]:
            tp_reference = round(support, 2)
            target_model = "RECENT_SUPPORT"
        else:
            tp_reference = round(entry["close"] - target_distance, 2)
            target_model = "FAILED_ORB_EXTENSION"

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        sweep_depth = abs(entry["high"] - failed_level)

        score = _score_setup(
            base_score=93,
            body=body,
            atr=atr,
            sweep_depth=sweep_depth,
            reclaim_strength=entry["close"] < prev["low"],
            ema_aligned=price < ema,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "FAILED_BREAKOUT_REVERSAL",
            "entry_model": "FAILED_ORB_BUY_REVERSAL",
            "pattern_height": abs(entry["close"] - tp_reference),
            "failed_breakout_level": failed_level,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "support": support,
            "resistance": resistance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_failed_orb_buy",
            "direction_context": "invalidated_orb_buy_reversal",
            "reason": (
                f"Failed ORB BUY reversal -> ORB high {round(failed_level, 2)} failed -> "
                f"bearish close below level and previous low -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
            ),
        }

    # =========================================================
    # Invalidated ORB SELL -> BUY reversal
    # =========================================================
    if original_signal == "SELL":
        failed_level = orb_low

        bullish_reversal = (
            entry["close"] > entry["open"]
            and entry["close"] > failed_level
            and entry["close"] > prev["high"]
        )

        if not bullish_reversal:
            return None

        sl_reference = round(min(entry["low"], failed_level) - sl_buffer, 2)

        if orb_high > entry["close"]:
            tp_reference = round(orb_high, 2)
            target_model = "ORB_HIGH_TARGET"
        elif resistance > entry["close"]:
            tp_reference = round(resistance, 2)
            target_model = "RECENT_RESISTANCE"
        else:
            tp_reference = round(entry["close"] + target_distance, 2)
            target_model = "FAILED_ORB_EXTENSION"

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        sweep_depth = abs(failed_level - entry["low"])

        score = _score_setup(
            base_score=93,
            body=body,
            atr=atr,
            sweep_depth=sweep_depth,
            reclaim_strength=entry["close"] > prev["high"],
            ema_aligned=price > ema,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "FAILED_BREAKOUT_REVERSAL",
            "entry_model": "FAILED_ORB_SELL_REVERSAL",
            "pattern_height": abs(tp_reference - entry["close"]),
            "failed_breakout_level": failed_level,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "support": support,
            "resistance": resistance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_failed_orb_sell",
            "direction_context": "invalidated_orb_sell_reversal",
            "reason": (
                f"Failed ORB SELL reversal -> ORB low {round(failed_level, 2)} failed -> "
                f"bullish close above level and previous high -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
            ),
        }

    return None


def generate_signal(df):
    if len(df) < BREAKOUT_LOOKBACK + 8:
        return None

    # Priority 1:
    # Use exact invalidated ORB high/low if an ORB setup failed recently.
    invalidated_orb_signal = _from_invalidated_orb(df)
    if invalidated_orb_signal is not None:
        return invalidated_orb_signal

    entry = df.iloc[-2]
    failed_break = df.iloc[-3]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return None

    if body < atr * FAILED_BREAKOUT_MIN_BODY_ATR:
        return None

    recent = df.iloc[-(BREAKOUT_LOOKBACK + 4):-4]
    resistance = recent["high"].max()
    support = recent["low"].min()
    structure_range = resistance - support

    if structure_range <= 0:
        return None

    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, structure_range)

    # =========================
    # SELL: failed bullish breakout
    # =========================
    broke_above = failed_break["high"] > resistance + BREAKOUT_BUFFER
    failed_hold = failed_break["close"] < resistance

    bearish_reclaim = (
        entry["close"] < entry["open"]
        and entry["close"] < resistance
        and entry["close"] < failed_break["low"]
    )

    sweep_depth = failed_break["high"] - resistance
    valid_sweep = (
        sweep_depth >= atr * FAILED_BREAKOUT_MIN_SWEEP_ATR
        and sweep_depth <= atr * FAILED_BREAKOUT_MAX_EXTENSION_ATR
    )

    ema_aligned = price < ema

    if broke_above and failed_hold and bearish_reclaim and valid_sweep:
        sl_reference = round(max(failed_break["high"], entry["high"]) + sl_buffer, 2)

        if support < entry["close"]:
            tp_reference = support
            target_model = "RECENT_SUPPORT"
        else:
            tp_reference = entry["close"] - target_distance
            target_model = "FAILED_BREAKOUT_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            body=body,
            atr=atr,
            sweep_depth=sweep_depth,
            reclaim_strength=entry["close"] < failed_break["low"],
            ema_aligned=ema_aligned,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "FAILED_BREAKOUT_REVERSAL",
            "entry_model": "FAILED_BUY_BREAKOUT_REVERSAL",
            "pattern_height": abs(entry["close"] - tp_reference),
            "failed_breakout_level": resistance,
            "sweep_high": failed_break["high"],
            "support": support,
            "resistance": resistance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_failed_breakout_reclaim",
            "direction_context": "failed_bullish_breakout",
            "reason": (
                f"Failed breakout SELL -> price swept above resistance {round(resistance, 2)} "
                f"then closed back below -> bearish reclaim confirmed -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
            ),
        }

    # =========================
    # BUY: failed bearish breakdown
    # =========================
    broke_below = failed_break["low"] < support - BREAKOUT_BUFFER
    failed_hold = failed_break["close"] > support

    bullish_reclaim = (
        entry["close"] > entry["open"]
        and entry["close"] > support
        and entry["close"] > failed_break["high"]
    )

    sweep_depth = support - failed_break["low"]
    valid_sweep = (
        sweep_depth >= atr * FAILED_BREAKOUT_MIN_SWEEP_ATR
        and sweep_depth <= atr * FAILED_BREAKOUT_MAX_EXTENSION_ATR
    )

    ema_aligned = price > ema

    if broke_below and failed_hold and bullish_reclaim and valid_sweep:
        sl_reference = round(min(failed_break["low"], entry["low"]) - sl_buffer, 2)

        if resistance > entry["close"]:
            tp_reference = resistance
            target_model = "RECENT_RESISTANCE"
        else:
            tp_reference = entry["close"] + target_distance
            target_model = "FAILED_BREAKOUT_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            body=body,
            atr=atr,
            sweep_depth=sweep_depth,
            reclaim_strength=entry["close"] > failed_break["high"],
            ema_aligned=ema_aligned,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "FAILED_BREAKOUT_REVERSAL",
            "entry_model": "FAILED_SELL_BREAKDOWN_REVERSAL",
            "pattern_height": abs(tp_reference - entry["close"]),
            "failed_breakout_level": support,
            "sweep_low": failed_break["low"],
            "support": support,
            "resistance": resistance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_failed_breakdown_reclaim",
            "direction_context": "failed_bearish_breakdown",
            "reason": (
                f"Failed breakout BUY -> price swept below support {round(support, 2)} "
                f"then closed back above -> bullish reclaim confirmed -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
            ),
        }

    return None