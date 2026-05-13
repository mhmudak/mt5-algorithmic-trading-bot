from config.settings import ATR_MIN, ATR_MAX


FAILED_FVG_LOOKBACK = 30

MIN_FVG_SIZE_ATR = 0.12
MIN_FAILURE_BODY_ATR = 0.25
MIN_DISPLACEMENT_BODY_ATR = 0.35

MAX_IMMEDIATE_EXTENSION_ATR = 0.45
RETEST_BUFFER_ATR = 0.25

SL_ATR_BUFFER = 0.20
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 5.0

TARGET_ATR_MIN = 1.5
TARGET_ATR_MAX = 3.0


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, fvg_size):
    return min(
        max(fvg_size * 2.0, atr * TARGET_ATR_MIN),
        atr * TARGET_ATR_MAX,
    )


def _score_setup(base_score, body, atr, fvg_size, displacement_ok, close_quality, entry_model):
    score = base_score

    if body > atr * 0.35:
        score += 2

    if body > atr * 0.55:
        score += 2

    if fvg_size > atr * 0.20:
        score += 2

    if displacement_ok:
        score += 3

    if close_quality:
        score += 2

    if entry_model in ["FAILED_BULLISH_FVG_RETEST", "FAILED_BEARISH_FVG_RETEST"]:
        score += 2

    return min(score, 99)


def _find_recent_bullish_fvg(df, atr):
    closed = df.iloc[:-1].reset_index(drop=True)

    for i in range(len(closed) - 4, max(2, len(closed) - FAILED_FVG_LOOKBACK), -1):
        c1 = closed.iloc[i - 2]
        c2 = closed.iloc[i - 1]
        c3 = closed.iloc[i]

        body_c2 = abs(c2["close"] - c2["open"])

        fvg_bottom = c1["high"]
        fvg_top = c3["low"]
        fvg_size = fvg_top - fvg_bottom

        if (
            fvg_size > atr * MIN_FVG_SIZE_ATR
            and c2["close"] > c2["open"]
            and body_c2 > atr * MIN_DISPLACEMENT_BODY_ATR
        ):
            return {
                "fvg_top": fvg_top,
                "fvg_bottom": fvg_bottom,
                "fvg_mid": (fvg_top + fvg_bottom) / 2,
                "fvg_size": fvg_size,
            }

    return None


def _find_recent_bearish_fvg(df, atr):
    closed = df.iloc[:-1].reset_index(drop=True)

    for i in range(len(closed) - 4, max(2, len(closed) - FAILED_FVG_LOOKBACK), -1):
        c1 = closed.iloc[i - 2]
        c2 = closed.iloc[i - 1]
        c3 = closed.iloc[i]

        body_c2 = abs(c2["close"] - c2["open"])

        fvg_top = c1["low"]
        fvg_bottom = c3["high"]
        fvg_size = fvg_top - fvg_bottom

        if (
            fvg_size > atr * MIN_FVG_SIZE_ATR
            and c2["close"] < c2["open"]
            and body_c2 > atr * MIN_DISPLACEMENT_BODY_ATR
        ):
            return {
                "fvg_top": fvg_top,
                "fvg_bottom": fvg_bottom,
                "fvg_mid": (fvg_top + fvg_bottom) / 2,
                "fvg_size": fvg_size,
            }

    return None


def _recent_close_below(df, level, bars=5):
    recent = df.iloc[-(bars + 2):-2]
    return any(recent["close"] < level)


def _recent_close_above(df, level, bars=5):
    recent = df.iloc[-(bars + 2):-2]
    return any(recent["close"] > level)


def generate_signal(df):
    if len(df) < FAILED_FVG_LOOKBACK + 5:
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

    if body < atr * MIN_FAILURE_BODY_ATR:
        return None

    recent = df.iloc[-25:-2]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    sl_buffer = _sl_buffer(atr)
    retest_buffer = atr * RETEST_BUFFER_ATR

    # =========================================================
    # SELL: bullish FVG fails
    # =========================================================
    bullish_fvg = _find_recent_bullish_fvg(df, atr)

    if bullish_fvg is not None:
        fvg_top = bullish_fvg["fvg_top"]
        fvg_bottom = bullish_fvg["fvg_bottom"]
        fvg_mid = bullish_fvg["fvg_mid"]
        fvg_size = bullish_fvg["fvg_size"]

        close_below_fvg = entry["close"] < fvg_bottom
        prior_failure = _recent_close_below(df, fvg_bottom)

        immediate_extension = fvg_bottom - entry["close"]
        immediate_not_late = (
            immediate_extension >= 0
            and immediate_extension <= atr * MAX_IMMEDIATE_EXTENSION_ATR
        )

        immediate_failure = (
            close_below_fvg
            and prev["low"] <= fvg_top
            and immediate_not_late
        )

        retest_failure = (
            prior_failure
            and entry["high"] >= fvg_bottom - retest_buffer
            and entry["close"] < fvg_bottom
        )

        bearish_displacement = (
            entry["close"] < entry["open"]
            and body > atr * MIN_DISPLACEMENT_BODY_ATR
        )

        bearish_structure_shift = entry["close"] < prev["low"]
        ema_context = price < ema
        close_quality = entry["close"] <= entry["high"] - candle_range * 0.65

        entry_model = None

        if immediate_failure and bearish_displacement and bearish_structure_shift and close_quality:
            entry_model = "FAILED_BULLISH_FVG_IMMEDIATE"

        elif retest_failure and bearish_displacement and close_quality:
            entry_model = "FAILED_BULLISH_FVG_RETEST"

        if entry_model:
            sl_reference = round(max(entry["high"], fvg_top) + sl_buffer, 2)

            if recent_low < entry["close"]:
                tp_reference = recent_low
                target_model = "RECENT_STRUCTURE_LOW"
            else:
                tp_reference = entry["close"] - _target_distance(atr, fvg_size)
                target_model = "FAILED_FVG_EXTENSION"

            tp_reference = round(tp_reference, 2)

            if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
                return None

            score = _score_setup(
                base_score=92,
                body=body,
                atr=atr,
                fvg_size=fvg_size,
                displacement_ok=bearish_displacement,
                close_quality=close_quality,
                entry_model=entry_model,
            )

            return {
                "signal": "SELL",
                "score": score,
                "strategy": "FAILED_FVG_REVERSAL",
                "entry_model": entry_model,
                "pattern_height": abs(entry["close"] - tp_reference),
                "failed_fvg_top": fvg_top,
                "failed_fvg_bottom": fvg_bottom,
                "failed_fvg_mid": fvg_mid,
                "recent_high": recent_high,
                "recent_low": recent_low,
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": target_model,
                "momentum": "bearish_failed_bullish_fvg",
                "direction_context": (
                    "price_below_ema" if ema_context else "counter_ema_failed_fvg"
                ),
                "reason": (
                    f"Failed bullish FVG SELL -> bullish FVG "
                    f"{round(fvg_bottom, 2)}-{round(fvg_top, 2)} failed -> "
                    f"entry_model={entry_model} -> bearish displacement confirmed -> "
                    f"SL {sl_reference} -> TP {target_model} {tp_reference}"
                ),
            }

    # =========================================================
    # BUY: bearish FVG fails
    # =========================================================
    bearish_fvg = _find_recent_bearish_fvg(df, atr)

    if bearish_fvg is not None:
        fvg_top = bearish_fvg["fvg_top"]
        fvg_bottom = bearish_fvg["fvg_bottom"]
        fvg_mid = bearish_fvg["fvg_mid"]
        fvg_size = bearish_fvg["fvg_size"]

        close_above_fvg = entry["close"] > fvg_top
        prior_failure = _recent_close_above(df, fvg_top)

        immediate_extension = entry["close"] - fvg_top
        immediate_not_late = (
            immediate_extension >= 0
            and immediate_extension <= atr * MAX_IMMEDIATE_EXTENSION_ATR
        )

        immediate_failure = (
            close_above_fvg
            and prev["high"] >= fvg_bottom
            and immediate_not_late
        )

        retest_failure = (
            prior_failure
            and entry["low"] <= fvg_top + retest_buffer
            and entry["close"] > fvg_top
        )

        bullish_displacement = (
            entry["close"] > entry["open"]
            and body > atr * MIN_DISPLACEMENT_BODY_ATR
        )

        bullish_structure_shift = entry["close"] > prev["high"]
        ema_context = price > ema
        close_quality = entry["close"] >= entry["low"] + candle_range * 0.65

        entry_model = None

        if immediate_failure and bullish_displacement and bullish_structure_shift and close_quality:
            entry_model = "FAILED_BEARISH_FVG_IMMEDIATE"

        elif retest_failure and bullish_displacement and close_quality:
            entry_model = "FAILED_BEARISH_FVG_RETEST"

        if entry_model:
            sl_reference = round(min(entry["low"], fvg_bottom) - sl_buffer, 2)

            if recent_high > entry["close"]:
                tp_reference = recent_high
                target_model = "RECENT_STRUCTURE_HIGH"
            else:
                tp_reference = entry["close"] + _target_distance(atr, fvg_size)
                target_model = "FAILED_FVG_EXTENSION"

            tp_reference = round(tp_reference, 2)

            if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
                return None

            score = _score_setup(
                base_score=92,
                body=body,
                atr=atr,
                fvg_size=fvg_size,
                displacement_ok=bullish_displacement,
                close_quality=close_quality,
                entry_model=entry_model,
            )

            return {
                "signal": "BUY",
                "score": score,
                "strategy": "FAILED_FVG_REVERSAL",
                "entry_model": entry_model,
                "pattern_height": abs(tp_reference - entry["close"]),
                "failed_fvg_top": fvg_top,
                "failed_fvg_bottom": fvg_bottom,
                "failed_fvg_mid": fvg_mid,
                "recent_high": recent_high,
                "recent_low": recent_low,
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": target_model,
                "momentum": "bullish_failed_bearish_fvg",
                "direction_context": (
                    "price_above_ema" if ema_context else "counter_ema_failed_fvg"
                ),
                "reason": (
                    f"Failed bearish FVG BUY -> bearish FVG "
                    f"{round(fvg_bottom, 2)}-{round(fvg_top, 2)} failed -> "
                    f"entry_model={entry_model} -> bullish displacement confirmed -> "
                    f"SL {sl_reference} -> TP {target_model} {tp_reference}"
                ),
            }

    return None