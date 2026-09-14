from __future__ import annotations

import math

import MetaTrader5 as mt5
import pandas as pd

from src.logger import logger


# ============================================================
# LIVE BIAS V1.1
#
# OBSERVATION / DISPLAY ONLY.
#
# Answers:
# "What direction is price trading in now?"
#
# This is deliberately separate from the broad HTF outlook.
#
# It cannot:
# - execute
# - block trades
# - modify risk
# - modify entry
# - modify SL / TP
# ============================================================


MIN_DIRECTIONAL_COVERAGE = 0.70
MIN_VALID_TIMEFRAMES = 2


REGIME_WEIGHTS = {
    "TRENDING": {
        "H1": 0.50,
        "M15": 0.30,
        "H4": 0.20,
    },
    "PULLBACK_TREND": {
        "H1": 0.45,
        "M15": 0.40,
        "H4": 0.15,
    },
    "CONSOLIDATION": {
        "H1": 0.35,
        "M15": 0.50,
        "H4": 0.15,
    },
    "RANGING": {
        "H1": 0.40,
        "M15": 0.45,
        "H4": 0.15,
    },
    "VOLATILE": {
        "H1": 0.45,
        "M15": 0.40,
        "H4": 0.15,
    },
}


DEFAULT_WEIGHTS = {
    "H1": 0.50,
    "M15": 0.35,
    "H4": 0.15,
}


TIMEFRAMES = {
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
}


def _safe_float(value, default=None):
    try:
        value = float(value)

        if math.isfinite(value):
            return value

    except Exception:
        pass

    return default


def _normalize_market_condition(value):
    condition = str(
        value or "UNKNOWN"
    ).upper().strip()

    # Heartbeat may display:
    # CONSOLIDATION -> BREAKOUT_UP_PENDING
    #
    # Weighting must continue to use the authoritative
    # closed-candle regime, not the observer suffix.
    if "->" in condition:
        condition = (
            condition
            .split("->", 1)[0]
            .strip()
        )

    return condition


def get_live_bias_weights(
    market_condition,
):
    condition = (
        _normalize_market_condition(
            market_condition
        )
    )

    return dict(
        REGIME_WEIGHTS.get(
            condition,
            DEFAULT_WEIGHTS,
        )
    )


def _atr(df, period=14):
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    previous_close = close.shift(1)

    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return true_range.rolling(
        period
    ).mean()


def _signed_component(
    value,
    deadband,
):
    if value is None:
        return 0.0

    if value > deadband:
        return 1.0

    if value < -deadband:
        return -1.0

    return 0.0


def _label_from_score(score):
    score = _safe_float(
        score,
        0.0,
    )

    if score >= 0.55:
        return "BULLISH"

    if score >= 0.15:
        return "MIXED_BULLISH"

    if score <= -0.55:
        return "BEARISH"

    if score <= -0.15:
        return "MIXED_BEARISH"

    return "MIXED"


def classify_timeframe_bias(df):
    """
    Classify one timeframe using CLOSED candles only.

    Components:
    1. close vs EMA20
    2. EMA20 slope
    3. EMA20 vs EMA50

    ATR-relative deadbands reduce small/noisy flips.
    """

    if df is None or len(df) < 60:
        return {
            "bias": "UNKNOWN",
            "score": None,
            "reason": "not_enough_data",
        }

    required = {
        "high",
        "low",
        "close",
    }

    if not required.issubset(
        set(df.columns)
    ):
        return {
            "bias": "UNKNOWN",
            "score": None,
            "reason": "missing_ohlc",
        }

    # Exclude the currently-forming candle.
    closed = (
        df.iloc[:-1]
        .copy()
        .reset_index(drop=True)
    )

    if len(closed) < 55:
        return {
            "bias": "UNKNOWN",
            "score": None,
            "reason": "not_enough_closed_data",
        }

    close = closed[
        "close"
    ].astype(float)

    ema20 = close.ewm(
        span=20,
        adjust=False,
    ).mean()

    ema50 = close.ewm(
        span=50,
        adjust=False,
    ).mean()

    atr_series = _atr(
        closed,
        14,
    )

    current_close = _safe_float(
        close.iloc[-1]
    )

    ema20_now = _safe_float(
        ema20.iloc[-1]
    )

    ema20_past = _safe_float(
        ema20.iloc[-5]
    )

    ema50_now = _safe_float(
        ema50.iloc[-1]
    )

    atr = _safe_float(
        atr_series.iloc[-1]
    )

    if (
        current_close is None
        or ema20_now is None
        or ema20_past is None
        or ema50_now is None
        or atr is None
        or atr <= 0
    ):
        return {
            "bias": "UNKNOWN",
            "score": None,
            "reason": "invalid_indicator_state",
        }

    price_delta = (
        current_close
        - ema20_now
    )

    ema_slope = (
        ema20_now
        - ema20_past
    )

    ema_structure = (
        ema20_now
        - ema50_now
    )

    price_component = _signed_component(
        price_delta,
        atr * 0.10,
    )

    slope_component = _signed_component(
        ema_slope,
        atr * 0.08,
    )

    structure_component = _signed_component(
        ema_structure,
        atr * 0.05,
    )

    score = (
        price_component
        + slope_component
        + structure_component
    ) / 3.0

    score = round(
        max(
            -1.0,
            min(1.0, score),
        ),
        4,
    )

    return {
        "bias": _label_from_score(
            score
        ),
        "score": score,
        "close": round(
            current_close,
            2,
        ),
        "ema20": round(
            ema20_now,
            2,
        ),
        "ema50": round(
            ema50_now,
            2,
        ),
        "ema20_slope": round(
            ema_slope,
            4,
        ),
        "atr": round(
            atr,
            4,
        ),
        "components": {
            "price_vs_ema20": (
                price_component
            ),
            "ema20_slope": (
                slope_component
            ),
            "ema20_vs_ema50": (
                structure_component
            ),
        },
        "reason": (
            "price_ema20_slope_ema50"
        ),
    }


def _authority_fields():
    return {
        "decision_impact": "DISPLAY_ONLY",
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
    }


def combine_live_bias(
    timeframe_states,
    market_condition,
):
    """
    Combine M15/H1/H4 with regime-aware weights.

    Missing data is fail-open.

    A directional label is suppressed when coverage is too
    weak. This prevents one incomplete timeframe feed from
    being presented as a trustworthy Live Bias.

    Directional Strength is NOT a probability.
    It is the absolute normalized directional score.
    """

    condition = (
        _normalize_market_condition(
            market_condition
        )
    )

    weights = (
        get_live_bias_weights(
            condition
        )
    )

    weighted_score = 0.0
    available_weight = 0.0
    valid_timeframes = 0

    for timeframe, weight in (
        weights.items()
    ):
        state = (
            timeframe_states.get(
                timeframe
            )
            or {}
        )

        score = _safe_float(
            state.get("score")
        )

        if score is None:
            continue

        weighted_score += (
            score * weight
        )

        available_weight += weight
        valid_timeframes += 1

    coverage = int(
        round(
            available_weight
            * 100
        )
    )

    enough_coverage = (
        available_weight
        >= MIN_DIRECTIONAL_COVERAGE
        and valid_timeframes
        >= MIN_VALID_TIMEFRAMES
    )

    if available_weight <= 0:
        result = {
            "bias": "UNKNOWN",
            "score": None,
            "raw_score": None,
            "directional_strength": 0,
            "coverage": 0,
            "valid_timeframes": 0,
            "minimum_coverage": int(
                MIN_DIRECTIONAL_COVERAGE
                * 100
            ),
            "market_condition": condition,
            "weights": weights,
            "timeframes": timeframe_states,
            "reason": "no_valid_timeframes",
        }

        result.update(
            _authority_fields()
        )

        return result

    raw_score = (
        weighted_score
        / available_weight
    )

    raw_score = round(
        max(
            -1.0,
            min(1.0, raw_score),
        ),
        4,
    )

    if not enough_coverage:
        result = {
            "bias": "UNKNOWN",
            "score": None,
            "raw_score": raw_score,
            "directional_strength": 0,
            "coverage": coverage,
            "valid_timeframes": (
                valid_timeframes
            ),
            "minimum_coverage": int(
                MIN_DIRECTIONAL_COVERAGE
                * 100
            ),
            "market_condition": condition,
            "weights": weights,
            "timeframes": timeframe_states,
            "reason": (
                "insufficient_timeframe_coverage"
            ),
        }

        result.update(
            _authority_fields()
        )

        return result

    final_score = raw_score

    directional_strength = int(
        round(
            abs(final_score)
            * 100
        )
    )

    result = {
        "bias": _label_from_score(
            final_score
        ),
        "score": final_score,
        "raw_score": raw_score,
        "directional_strength": (
            directional_strength
        ),
        "coverage": coverage,
        "valid_timeframes": (
            valid_timeframes
        ),
        "minimum_coverage": int(
            MIN_DIRECTIONAL_COVERAGE
            * 100
        ),
        "market_condition": condition,
        "weights": weights,
        "timeframes": timeframe_states,
        "reason": "sufficient_coverage",
    }

    result.update(
        _authority_fields()
    )

    return result


def _load_timeframe_state(
    symbol,
    timeframe_name,
):
    timeframe = TIMEFRAMES[
        timeframe_name
    ]

    rates = mt5.copy_rates_from_pos(
        symbol,
        timeframe,
        0,
        90,
    )

    if (
        rates is None
        or len(rates) < 60
    ):
        return {
            "bias": "UNKNOWN",
            "score": None,
            "reason": (
                "mt5_rates_unavailable"
            ),
        }

    df = pd.DataFrame(
        rates
    )

    return classify_timeframe_bias(
        df
    )


def get_live_bias_snapshot(
    symbol,
    market_condition,
):
    """
    Fresh heartbeat-time observation.

    Uses only closed M15/H1/H4 candles.
    Zero trading authority.
    """

    states = {}

    for timeframe_name in (
        "M15",
        "H1",
        "H4",
    ):
        try:
            states[
                timeframe_name
            ] = _load_timeframe_state(
                symbol,
                timeframe_name,
            )

        except Exception as exc:
            states[
                timeframe_name
            ] = {
                "bias": "UNKNOWN",
                "score": None,
                "reason": (
                    f"failed_open:{exc}"
                ),
            }

    snapshot = combine_live_bias(
        states,
        market_condition,
    )

    state_text = " | ".join(
        (
            f"{timeframe}="
            f"{states.get(timeframe, {}).get('bias', 'UNKNOWN')}"
        )
        for timeframe in (
            "M15",
            "H1",
            "H4",
        )
    )

    logger.info(
        "[LIVE BIAS] "
        f"condition={snapshot['market_condition']} "
        f"bias={snapshot['bias']} "
        f"score={snapshot['score']} "
        f"directional_strength="
        f"{snapshot['directional_strength']} "
        f"coverage={snapshot['coverage']} "
        f"valid_timeframes="
        f"{snapshot['valid_timeframes']} "
        f"{state_text}"
    )

    return snapshot
