from config.settings import ATR_MIN, ATR_MAX


HS_LOOKBACK = 45
SHOULDER_TOLERANCE = 0.012

MIN_BODY_ATR_RATIO = 0.20
MAX_BREAKOUT_EXTENSION_ATR = 0.80

RETEST_PROXIMITY_ATR = 0.35
RETEST_MIN_REJECTION_WICK_BODY = 1.0

HS_SL_ATR_BUFFER = 0.20
HS_MIN_SL_BUFFER = 2.0


def _sl_buffer(atr):
    return max(atr * HS_SL_ATR_BUFFER, HS_MIN_SL_BUFFER)


def _score_setup(base_score, body, atr, close_aligned, measured_height, retest_entry=False):
    score = base_score

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.50:
        score += 2

    if close_aligned:
        score += 2

    if measured_height > atr:
        score += 2

    if retest_entry:
        score += 3

    return min(score, 99)


def _find_peaks_and_troughs(data):
    highs = data["high"]
    lows = data["low"]

    peaks = []
    troughs = []

    for i in range(2, len(data) - 2):
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            peaks.append(i)

        if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            troughs.append(i)

    return peaks, troughs


def generate_signal(df):
    if len(df) < HS_LOOKBACK:
        return None

    data = df.iloc[-HS_LOOKBACK:].reset_index(drop=True)

    peaks, troughs = _find_peaks_and_troughs(data)

    entry = data.iloc[-2]      # last closed candle
    prev = data.iloc[-3]       # candle before entry
    retest_prev = data.iloc[-4]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return None

    if body < atr * MIN_BODY_ATR_RATIO:
        return None

    upper_wick = entry["high"] - max(entry["open"], entry["close"])
    lower_wick = min(entry["open"], entry["close"]) - entry["low"]

    # =========================================================
    # Bearish Head & Shoulders
    # =========================================================
    if len(peaks) >= 3:
        p1, p2, p3 = peaks[-3:]

        left = data.iloc[p1]
        head = data.iloc[p2]
        right = data.iloc[p3]

        shoulders_close_enough = (
            abs(left["high"] - right["high"]) / head["high"]
            <= SHOULDER_TOLERANCE
        )

        structure_ok = (
            p1 < p2 < p3
            and head["high"] > left["high"]
            and head["high"] > right["high"]
            and shoulders_close_enough
        )

        if structure_ok:
            relevant_troughs = [t for t in troughs if p1 < t < p3]

            if relevant_troughs:
                neckline_idx = min(relevant_troughs, key=lambda x: data["low"][x])
                neckline = data.iloc[neckline_idx]["low"]
                measured_height = head["high"] - neckline

                if measured_height > 0:
                    sl_reference = round(right["high"] + _sl_buffer(atr), 2)
                    tp_reference = round(neckline - measured_height, 2)

                    # -----------------------------------------
                    # Entry Model 1: Neckline breakout
                    # -----------------------------------------
                    breakout_distance = neckline - entry["close"]

                    neckline_breakout = (
                        entry["close"] < neckline
                        and prev["close"] >= neckline
                    )

                    bearish_breakout_momentum = (
                        entry["close"] < entry["open"]
                        and price < ema
                        and breakout_distance >= 0
                        and breakout_distance <= atr * MAX_BREAKOUT_EXTENSION_ATR
                    )

                    if neckline_breakout and bearish_breakout_momentum:
                        score = _score_setup(
                            base_score=90,
                            body=body,
                            atr=atr,
                            close_aligned=price < ema,
                            measured_height=measured_height,
                            retest_entry=False,
                        )

                        return {
                            "signal": "SELL",
                            "score": score,
                            "strategy": "HEAD_SHOULDERS",
                            "entry_model": "HS_NECKLINE_BREAKOUT",
                            "pattern_height": measured_height,
                            "head": head["high"],
                            "left_shoulder": left["high"],
                            "right_shoulder": right["high"],
                            "neckline": neckline,
                            "sl_reference": sl_reference,
                            "tp_reference": tp_reference,
                            "target_model": "MEASURED_MOVE_FROM_NECKLINE",
                            "momentum": "bearish_neckline_break",
                            "direction_context": "price_below_ema",
                            "reason": (
                                f"Head & Shoulders SELL breakout -> "
                                f"head={round(head['high'], 2)} neckline={round(neckline, 2)} broken -> "
                                f"SL above right shoulder {sl_reference} -> "
                                f"TP measured move {tp_reference} -> price below EMA"
                            ),
                        }

                    # -----------------------------------------
                    # Entry Model 2: Neckline retest rejection
                    # -----------------------------------------
                    prior_break = (
                        retest_prev["close"] < neckline
                        or prev["close"] < neckline
                    )

                    retested_neckline = (
                        entry["high"] >= neckline - atr * RETEST_PROXIMITY_ATR
                        and entry["high"] <= neckline + atr * RETEST_PROXIMITY_ATR
                    )

                    bearish_rejection = (
                        entry["close"] < entry["open"]
                        and entry["close"] < neckline
                        and upper_wick > body * RETEST_MIN_REJECTION_WICK_BODY
                        and price < ema
                    )

                    if prior_break and retested_neckline and bearish_rejection:
                        score = _score_setup(
                            base_score=92,
                            body=body,
                            atr=atr,
                            close_aligned=price < ema,
                            measured_height=measured_height,
                            retest_entry=True,
                        )

                        return {
                            "signal": "SELL",
                            "score": score,
                            "strategy": "HEAD_SHOULDERS",
                            "entry_model": "HS_NECKLINE_RETEST",
                            "pattern_height": measured_height,
                            "head": head["high"],
                            "left_shoulder": left["high"],
                            "right_shoulder": right["high"],
                            "neckline": neckline,
                            "sl_reference": sl_reference,
                            "tp_reference": tp_reference,
                            "target_model": "MEASURED_MOVE_FROM_NECKLINE",
                            "momentum": "bearish_neckline_retest_rejection",
                            "direction_context": "price_below_ema",
                            "reason": (
                                f"Head & Shoulders SELL retest -> "
                                f"neckline {round(neckline, 2)} retested and rejected -> "
                                f"SL above right shoulder {sl_reference} -> "
                                f"TP measured move {tp_reference} -> price below EMA"
                            ),
                        }

    # =========================================================
    # Bullish Inverse Head & Shoulders
    # =========================================================
    if len(troughs) >= 3:
        t1, t2, t3 = troughs[-3:]

        left = data.iloc[t1]
        head = data.iloc[t2]
        right = data.iloc[t3]

        shoulders_close_enough = (
            abs(left["low"] - right["low"]) / head["low"]
            <= SHOULDER_TOLERANCE
        )

        structure_ok = (
            t1 < t2 < t3
            and head["low"] < left["low"]
            and head["low"] < right["low"]
            and shoulders_close_enough
        )

        if structure_ok:
            relevant_peaks = [p for p in peaks if t1 < p < t3]

            if relevant_peaks:
                neckline_idx = max(relevant_peaks, key=lambda x: data["high"][x])
                neckline = data.iloc[neckline_idx]["high"]
                measured_height = neckline - head["low"]

                if measured_height > 0:
                    sl_reference = round(right["low"] - _sl_buffer(atr), 2)
                    tp_reference = round(neckline + measured_height, 2)

                    # -----------------------------------------
                    # Entry Model 1: Neckline breakout
                    # -----------------------------------------
                    breakout_distance = entry["close"] - neckline

                    neckline_breakout = (
                        entry["close"] > neckline
                        and prev["close"] <= neckline
                    )

                    bullish_breakout_momentum = (
                        entry["close"] > entry["open"]
                        and price > ema
                        and breakout_distance >= 0
                        and breakout_distance <= atr * MAX_BREAKOUT_EXTENSION_ATR
                    )

                    if neckline_breakout and bullish_breakout_momentum:
                        score = _score_setup(
                            base_score=90,
                            body=body,
                            atr=atr,
                            close_aligned=price > ema,
                            measured_height=measured_height,
                            retest_entry=False,
                        )

                        return {
                            "signal": "BUY",
                            "score": score,
                            "strategy": "HEAD_SHOULDERS",
                            "entry_model": "INVERSE_HS_NECKLINE_BREAKOUT",
                            "pattern_height": measured_height,
                            "head": head["low"],
                            "left_shoulder": left["low"],
                            "right_shoulder": right["low"],
                            "neckline": neckline,
                            "sl_reference": sl_reference,
                            "tp_reference": tp_reference,
                            "target_model": "MEASURED_MOVE_FROM_NECKLINE",
                            "momentum": "bullish_neckline_break",
                            "direction_context": "price_above_ema",
                            "reason": (
                                f"Inverse Head & Shoulders BUY breakout -> "
                                f"head={round(head['low'], 2)} neckline={round(neckline, 2)} broken -> "
                                f"SL below right shoulder {sl_reference} -> "
                                f"TP measured move {tp_reference} -> price above EMA"
                            ),
                        }

                    # -----------------------------------------
                    # Entry Model 2: Neckline retest rejection
                    # -----------------------------------------
                    prior_break = (
                        retest_prev["close"] > neckline
                        or prev["close"] > neckline
                    )

                    retested_neckline = (
                        entry["low"] <= neckline + atr * RETEST_PROXIMITY_ATR
                        and entry["low"] >= neckline - atr * RETEST_PROXIMITY_ATR
                    )

                    bullish_rejection = (
                        entry["close"] > entry["open"]
                        and entry["close"] > neckline
                        and lower_wick > body * RETEST_MIN_REJECTION_WICK_BODY
                        and price > ema
                    )

                    if prior_break and retested_neckline and bullish_rejection:
                        score = _score_setup(
                            base_score=92,
                            body=body,
                            atr=atr,
                            close_aligned=price > ema,
                            measured_height=measured_height,
                            retest_entry=True,
                        )

                        return {
                            "signal": "BUY",
                            "score": score,
                            "strategy": "HEAD_SHOULDERS",
                            "entry_model": "INVERSE_HS_NECKLINE_RETEST",
                            "pattern_height": measured_height,
                            "head": head["low"],
                            "left_shoulder": left["low"],
                            "right_shoulder": right["low"],
                            "neckline": neckline,
                            "sl_reference": sl_reference,
                            "tp_reference": tp_reference,
                            "target_model": "MEASURED_MOVE_FROM_NECKLINE",
                            "momentum": "bullish_neckline_retest_rejection",
                            "direction_context": "price_above_ema",
                            "reason": (
                                f"Inverse Head & Shoulders BUY retest -> "
                                f"neckline {round(neckline, 2)} retested and rejected -> "
                                f"SL below right shoulder {sl_reference} -> "
                                f"TP measured move {tp_reference} -> price above EMA"
                            ),
                        }

    return None