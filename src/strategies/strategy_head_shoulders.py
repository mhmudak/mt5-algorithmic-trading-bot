from config.settings import BREAKOUT_LOOKBACK


def generate_signal(df):
    if len(df) < 30:
        return None

    data = df.iloc[-30:].reset_index(drop=True)

    highs = data["high"]
    lows = data["low"]

    # =========================
    # Find local peaks
    # =========================
    peaks = []
    troughs = []

    for i in range(2, len(data) - 2):
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            peaks.append(i)
        if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            troughs.append(i)

    if len(peaks) < 3:
        return None

    # Take last 3 peaks
    p1, p2, p3 = peaks[-3:]

    left = data.iloc[p1]
    head = data.iloc[p2]
    right = data.iloc[p3]

    # =========================
    # Bearish Head & Shoulders
    # =========================
    cond_structure = (
        head["high"] > left["high"]
        and head["high"] > right["high"]
        and abs(left["high"] - right["high"]) / head["high"] < 0.01
    )

    if cond_structure:
        # find neckline (lowest trough between peaks)
        relevant_troughs = [t for t in troughs if p1 < t < p3]
        if not relevant_troughs:
            return None

        neckline_idx = min(relevant_troughs, key=lambda x: lows[x])
        neckline = data.iloc[neckline_idx]["low"]

        last_close = data.iloc[-2]["close"]

        # breakout confirmation
        if last_close < neckline:
            pattern_height = head["high"] - neckline

            return {
                "signal": "SELL",
                "score": 90,
                "strategy": "HEAD_SHOULDERS",
                "pattern_height": pattern_height,
                "neckline": neckline,
                "reason": (
                    f"Head & Shoulders -> head={round(head['high'],2)} "
                    f"neckline={round(neckline,2)} breakout confirmed"
                ),
            }

    # =========================
    # Bullish Inverse H&S
    # =========================
    if len(troughs) < 3:
        return None

    t1, t2, t3 = troughs[-3:]

    left = data.iloc[t1]
    head = data.iloc[t2]
    right = data.iloc[t3]

    cond_structure = (
        head["low"] < left["low"]
        and head["low"] < right["low"]
        and abs(left["low"] - right["low"]) / head["low"] < 0.01
    )

    if cond_structure:
        relevant_peaks = [p for p in peaks if t1 < p < t3]
        if not relevant_peaks:
            return None

        neckline_idx = max(relevant_peaks, key=lambda x: highs[x])
        neckline = data.iloc[neckline_idx]["high"]

        last_close = data.iloc[-2]["close"]

        if last_close > neckline:
            pattern_height = neckline - head["low"]

            return {
                "signal": "BUY",
                "score": 90,
                "strategy": "HEAD_SHOULDERS",
                "pattern_height": pattern_height,
                "neckline": neckline,
                "reason": (
                    f"Inverse H&S -> head={round(head['low'],2)} "
                    f"neckline={round(neckline,2)} breakout confirmed"
                ),
            }

    return None