from __future__ import annotations

import pandas as pd


def _safe_float(value):
    try:
        value = float(value)

        if not pd.notna(value):
            return None

        return value

    except Exception:
        return None


def calculate_classic_pivots_from_ohlc(
    high,
    low,
    close,
):
    # Classic daily pivots from one completed D1 candle.
    high = _safe_float(high)
    low = _safe_float(low)
    close = _safe_float(close)

    if (
        high is None
        or low is None
        or close is None
        or high <= low
    ):
        return None

    p = (
        high
        + low
        + close
    ) / 3.0

    r1 = 2 * p - low
    s1 = 2 * p - high

    r2 = p + (high - low)
    s2 = p - (high - low)

    r3 = high + 2 * (p - low)
    s3 = low - 2 * (high - p)

    levels = {
        "S3": round(s3, 2),
        "S2": round(s2, 2),
        "S1": round(s1, 2),
        "P": round(p, 2),
        "R1": round(r1, 2),
        "R2": round(r2, 2),
        "R3": round(r3, 2),
    }

    return {
        "levels": levels,
        "ordered": sorted(
            levels.items(),
            key=lambda item: item[1],
        ),
    }


def calculate_five_level_daily_range_from_ohlc(
    high,
    low,
    close,
    *,
    high_diap=2000.0,
    low_diap=500.0,
):
    # Exact mathematical port of the uploaded levels.mq5.
    #
    # These are structural levels, not probabilities.
    #
    # NORMAL   -> inner 0.236, outer 0.382
    # REDUCED  -> inner 0.146, outer 0.236
    # EXTENDED -> inner 0.382, outer 0.618

    high = _safe_float(high)
    low = _safe_float(low)
    close = _safe_float(close)

    high_diap = _safe_float(
        high_diap
    )

    low_diap = _safe_float(
        low_diap
    )

    if (
        high is None
        or low is None
        or close is None
        or high_diap is None
        or low_diap is None
        or high <= low
    ):
        return None

    daily_range = high - low

    if daily_range > high_diap:
        mode = "REDUCED"
        inner = 0.146
        outer = 0.236

    elif daily_range < low_diap:
        mode = "EXTENDED"
        inner = 0.382
        outer = 0.618

    else:
        mode = "NORMAL"
        inner = 0.236
        outer = 0.382

    s1 = (
        close
        - daily_range
        * inner
        / 2.0
    )

    r1 = (
        close
        + daily_range
        * inner
        / 2.0
    )

    r2 = (
        r1
        + daily_range
        * outer
    )

    r3 = (
        r1
        + 2.0
        * daily_range
        * outer
    )

    r4 = (
        r3
        + (
            r1
            - s1
        )
    )

    r5 = (
        r4
        + daily_range
        * outer
    )

    s2 = (
        s1
        - daily_range
        * outer
    )

    s3 = (
        s1
        - 2.0
        * daily_range
        * outer
    )

    s4 = (
        s3
        - (
            r1
            - s1
        )
    )

    s5 = (
        s4
        - daily_range
        * outer
    )

    levels = {
        "S5": round(s5, 2),
        "S4": round(s4, 2),
        "S3": round(s3, 2),
        "S2": round(s2, 2),
        "S1": round(s1, 2),
        "R1": round(r1, 2),
        "R2": round(r2, 2),
        "R3": round(r3, 2),
        "R4": round(r4, 2),
        "R5": round(r5, 2),
    }

    return {
        "mode": mode,
        "daily_range": round(
            daily_range,
            2,
        ),
        "levels": levels,
        "ordered": sorted(
            levels.items(),
            key=lambda item: item[1],
        ),
    }


def calculate_daily_context_from_d1(
    d1_df: pd.DataFrame,
    *,
    high_diap=2000.0,
    low_diap=500.0,
):
    # Expected MT5 ordering:
    # iloc[-1] = current/forming D1
    # iloc[-2] = latest completed D1

    if (
        d1_df is None
        or len(d1_df) < 2
    ):
        return None

    try:
        completed = d1_df.iloc[-2]

        high = _safe_float(
            completed["high"]
        )

        low = _safe_float(
            completed["low"]
        )

        close = _safe_float(
            completed["close"]
        )

    except Exception:
        return None

    if (
        high is None
        or low is None
        or close is None
        or high <= low
    ):
        return None

    classic = (
        calculate_classic_pivots_from_ohlc(
            high,
            low,
            close,
        )
    )

    five_level = (
        calculate_five_level_daily_range_from_ohlc(
            high,
            low,
            close,
            high_diap=high_diap,
            low_diap=low_diap,
        )
    )

    if (
        classic is None
        or five_level is None
    ):
        return None

    candle_time = None

    try:
        candle_time = completed.get(
            "time"
        )

        if candle_time is not None:
            candle_time = str(
                candle_time
            )

    except Exception:
        candle_time = None

    return {
        "source": "BROKER_COMPLETED_D1",
        "time": candle_time,
        "previous_day_high": round(
            high,
            2,
        ),
        "previous_day_low": round(
            low,
            2,
        ),
        "previous_day_close": round(
            close,
            2,
        ),
        "classic": classic,
        "five_level": five_level,
    }
