from config.settings import (
    VWAP_RANGE_LOOKBACK_BARS,
    VWAP_RANGE_EDGE_ZONE_PCT,
    VWAP_RANGE_MIN_DEVIATION_ATR,
    VWAP_RANGE_SL_BUFFER_PRICE,
    VWAP_RANGE_MEAN_REVERSION_BASE_MIN_SCORE,
)


def _calculate_vwap(window):
    typical_price = (window["high"] + window["low"] + window["close"]) / 3

    if "tick_volume" in window.columns:
        volume = window["tick_volume"].replace(0, 1)
    elif "real_volume" in window.columns:
        volume = window["real_volume"].replace(0, 1)
    else:
        volume = 1

    try:
        return float((typical_price * volume).sum() / volume.sum())
    except Exception:
        return float(typical_price.mean())


def _range_context(df):
    if len(df) < VWAP_RANGE_LOOKBACK_BARS + 5:
        return None

    closed_window = df.iloc[-VWAP_RANGE_LOOKBACK_BARS - 1:-1]
    signal_candle = df.iloc[-2]

    range_window = closed_window.iloc[:-1]

    range_high = float(range_window["high"].max())
    range_low = float(range_window["low"].min())
    range_mid = (range_high + range_low) / 2
    range_width = range_high - range_low

    if range_width <= 0:
        return None

    atr = float(signal_candle["atr_14"])

    if atr <= 0:
        return None

    vwap = _calculate_vwap(closed_window)

    return {
        "signal_candle": signal_candle,
        "range_high": range_high,
        "range_low": range_low,
        "range_mid": range_mid,
        "range_width": range_width,
        "atr": atr,
        "vwap": vwap,
    }


def generate_signal(df):
    context = _range_context(df)

    if context is None:
        return None

    candle = context["signal_candle"]
    range_high = context["range_high"]
    range_low = context["range_low"]
    range_mid = context["range_mid"]
    range_width = context["range_width"]
    atr = context["atr"]
    vwap = context["vwap"]

    open_price = float(candle["open"])
    high = float(candle["high"])
    low = float(candle["low"])
    close = float(candle["close"])

    upper_edge = range_high - range_width * VWAP_RANGE_EDGE_ZONE_PCT
    lower_edge = range_low + range_width * VWAP_RANGE_EDGE_ZONE_PCT

    min_deviation = atr * VWAP_RANGE_MIN_DEVIATION_ATR
    sl_buffer = max(VWAP_RANGE_SL_BUFFER_PRICE, atr * 0.15)

    body = abs(close - open_price)
    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low

    # =========================
    # BUY: lower range + below VWAP + bullish rejection
    # =========================
    buy_location = low <= lower_edge
    buy_deviation = close < vwap - min_deviation
    buy_rejection = close > open_price and lower_wick >= max(body * 0.35, atr * 0.08)

    if buy_location and buy_deviation and buy_rejection:
        tp_reference = round(vwap, 2)

        if tp_reference <= close:
            tp_reference = round(range_mid, 2)

        if tp_reference <= close:
            return None

        sl_reference = round(low - sl_buffer, 2)

        score = VWAP_RANGE_MEAN_REVERSION_BASE_MIN_SCORE

        if low <= range_low + atr * 0.30:
            score += 5

        if lower_wick >= atr * 0.25:
            score += 4

        score = min(score, 100)

        return {
            "signal": "BUY",
            "score": score,
            "entry_model": "VWAP_RANGE_MEAN_REVERSION_BUY",
            "sl_model": "RANGE_REJECTION_SL",
            "tp_model": "VWAP_REVERSION_TP",
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "vwap": round(vwap, 2),
            "range_high": round(range_high, 2),
            "range_low": round(range_low, 2),
            "range_mid": round(range_mid, 2),
            "reason": (
                f"VWAP Range Mean Reversion BUY -> price at lower range edge "
                f"and below VWAP {round(vwap, 2)} with bullish rejection -> "
                f"SL {sl_reference} -> TP VWAP/mean {tp_reference}"
            ),
        }

    # =========================
    # SELL: upper range + above VWAP + bearish rejection
    # =========================
    sell_location = high >= upper_edge
    sell_deviation = close > vwap + min_deviation
    sell_rejection = close < open_price and upper_wick >= max(body * 0.35, atr * 0.08)

    if sell_location and sell_deviation and sell_rejection:
        tp_reference = round(vwap, 2)

        if tp_reference >= close:
            tp_reference = round(range_mid, 2)

        if tp_reference >= close:
            return None

        sl_reference = round(high + sl_buffer, 2)

        score = VWAP_RANGE_MEAN_REVERSION_BASE_MIN_SCORE

        if high >= range_high - atr * 0.30:
            score += 5

        if upper_wick >= atr * 0.25:
            score += 4

        score = min(score, 100)

        return {
            "signal": "SELL",
            "score": score,
            "entry_model": "VWAP_RANGE_MEAN_REVERSION_SELL",
            "sl_model": "RANGE_REJECTION_SL",
            "tp_model": "VWAP_REVERSION_TP",
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "vwap": round(vwap, 2),
            "range_high": round(range_high, 2),
            "range_low": round(range_low, 2),
            "range_mid": round(range_mid, 2),
            "reason": (
                f"VWAP Range Mean Reversion SELL -> price at upper range edge "
                f"and above VWAP {round(vwap, 2)} with bearish rejection -> "
                f"SL {sl_reference} -> TP VWAP/mean {tp_reference}"
            ),
        }

    return None