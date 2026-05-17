from config.settings import (
    ENABLE_CHOCH_MSS_CONTEXT,
    CHOCH_MSS_LOOKBACK,
    CHOCH_MSS_SWING_LOOKBACK,
    CHOCH_MSS_BOOST,
    CHOCH_MSS_CONFLICT_PENALTY,
    CHOCH_MSS_REVERSAL_STRATEGIES,
)
from src.logger import logger


def _find_recent_swing_high(df, end_index, lookback):
    start = max(0, end_index - lookback)
    window = df.iloc[start:end_index]

    if window.empty:
        return None

    return window["high"].max()


def _find_recent_swing_low(df, end_index, lookback):
    start = max(0, end_index - lookback)
    window = df.iloc[start:end_index]

    if window.empty:
        return None

    return window["low"].min()


def _detect_structure_bias(df):
    closed = df.iloc[:-1].reset_index(drop=True)

    if len(closed) < CHOCH_MSS_LOOKBACK:
        return "NEUTRAL"

    recent = closed.iloc[-CHOCH_MSS_LOOKBACK:].reset_index(drop=True)

    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    first_close = recent.iloc[0]["close"]
    last_close = recent.iloc[-1]["close"]

    if last_close > first_close and recent.iloc[-1]["close"] > recent["close"].mean():
        return "BUY"

    if last_close < first_close and recent.iloc[-1]["close"] < recent["close"].mean():
        return "SELL"

    return "NEUTRAL"


def analyze_choch_mss_context(df):
    """
    Detects simple CHoCH / MSS context from closed candles.

    CHoCH:
    Structure bias was one way, then price breaks the opposite swing.

    MSS:
    Stronger version where break happens with directional displacement.
    """
    if not ENABLE_CHOCH_MSS_CONTEXT:
        return None

    if df is None or len(df) < CHOCH_MSS_LOOKBACK + 5:
        return None

    closed = df.iloc[:-1].reset_index(drop=True)

    entry = closed.iloc[-1]
    prev = closed.iloc[-2]

    atr = entry["atr_14"]

    if atr <= 0:
        return None

    prior = closed.iloc[-(CHOCH_MSS_LOOKBACK + 1):-1].reset_index(drop=True)

    if len(prior) < CHOCH_MSS_SWING_LOOKBACK + 5:
        return None

    structure_bias = _detect_structure_bias(df)

    recent_swing_high = _find_recent_swing_high(
        prior,
        end_index=len(prior),
        lookback=CHOCH_MSS_SWING_LOOKBACK,
    )

    recent_swing_low = _find_recent_swing_low(
        prior,
        end_index=len(prior),
        lookback=CHOCH_MSS_SWING_LOOKBACK,
    )

    if recent_swing_high is None or recent_swing_low is None:
        return None

    body = abs(entry["close"] - entry["open"])

    bullish_break = entry["close"] > recent_swing_high
    bearish_break = entry["close"] < recent_swing_low

    bullish_displacement = (
        entry["close"] > entry["open"]
        and body > atr * 0.25
        and entry["close"] > prev["high"]
    )

    bearish_displacement = (
        entry["close"] < entry["open"]
        and body > atr * 0.25
        and entry["close"] < prev["low"]
    )

    bias = "NEUTRAL"
    signal_type = None
    reasons = []

    if bullish_break:
        bias = "BUY"

        if structure_bias == "SELL":
            signal_type = "BULLISH_CHOCH"
            reasons.append("bullish_choch")

        if bullish_displacement:
            signal_type = "BULLISH_MSS"
            reasons.append("bullish_mss")

    elif bearish_break:
        bias = "SELL"

        if structure_bias == "BUY":
            signal_type = "BEARISH_CHOCH"
            reasons.append("bearish_choch")

        if bearish_displacement:
            signal_type = "BEARISH_MSS"
            reasons.append("bearish_mss")

    if bias == "NEUTRAL":
        logger.info(
            f"[CHOCH MSS] No structure shift | "
            f"structure_bias={structure_bias} "
            f"swing_high={round(recent_swing_high, 2)} "
            f"swing_low={round(recent_swing_low, 2)}"
        )
        return {
            "bias": "NEUTRAL",
            "type": None,
            "structure_bias": structure_bias,
            "recent_swing_high": recent_swing_high,
            "recent_swing_low": recent_swing_low,
            "reasons": [],
        }

    context = {
        "bias": bias,
        "type": signal_type,
        "structure_bias": structure_bias,
        "recent_swing_high": recent_swing_high,
        "recent_swing_low": recent_swing_low,
        "bullish_break": bullish_break,
        "bearish_break": bearish_break,
        "bullish_displacement": bullish_displacement,
        "bearish_displacement": bearish_displacement,
        "reasons": reasons,
    }

    logger.info(
        f"[CHOCH MSS] bias={bias} type={signal_type} "
        f"structure_bias={structure_bias} reasons={reasons}"
    )

    return context


def apply_choch_mss_confirmation(signal_data, context):
    if not ENABLE_CHOCH_MSS_CONTEXT:
        return 0, []

    if not signal_data or context is None:
        return 0, []

    signal = signal_data.get("signal")
    strategy = signal_data.get("strategy")

    if signal not in ["BUY", "SELL"]:
        return 0, []

    context_bias = context.get("bias")
    reasons = context.get("reasons", [])

    if context_bias == "NEUTRAL":
        return 0, []

    if context_bias == signal:
        boost = CHOCH_MSS_BOOST

        if strategy in CHOCH_MSS_REVERSAL_STRATEGIES:
            boost += 1

        return boost, [
            "choch_mss_aligned",
            *reasons,
        ]

    if context_bias in ["BUY", "SELL"] and context_bias != signal:
        penalty = CHOCH_MSS_CONFLICT_PENALTY

        if strategy in CHOCH_MSS_REVERSAL_STRATEGIES:
            penalty += 1

        return -penalty, [
            f"choch_mss_conflict_{context_bias.lower()}",
            *reasons,
        ]

    return 0, []