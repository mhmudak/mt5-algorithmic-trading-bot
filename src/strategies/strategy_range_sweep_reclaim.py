from config.settings import (
    RANGE_SWEEP_LOOKBACK_BARS,
    RANGE_SWEEP_BUFFER_PRICE,
    RANGE_SWEEP_RECLAIM_BUFFER_PRICE,
    RANGE_SWEEP_SL_BUFFER_PRICE,
    RANGE_SWEEP_MIN_RANGE_ATR,
    RANGE_SWEEP_MAX_RANGE_ATR,
    RANGE_SWEEP_RECLAIM_BASE_MIN_SCORE,
)


def _valid_range(range_high, range_low, atr):
    if atr is None or atr <= 0:
        return False

    range_width = range_high - range_low

    if range_width <= 0:
        return False

    range_atr = range_width / atr

    return RANGE_SWEEP_MIN_RANGE_ATR <= range_atr <= RANGE_SWEEP_MAX_RANGE_ATR


def _range_context(df):
    if len(df) < RANGE_SWEEP_LOOKBACK_BARS + 5:
        return None

    signal_candle = df.iloc[-2]
    range_window = df.iloc[-RANGE_SWEEP_LOOKBACK_BARS - 2:-2]

    range_high = float(range_window["high"].max())
    range_low = float(range_window["low"].min())
    range_mid = (range_high + range_low) / 2
    atr = float(signal_candle["atr_14"])

    if not _valid_range(range_high, range_low, atr):
        return None

    return {
        "signal_candle": signal_candle,
        "range_high": range_high,
        "range_low": range_low,
        "range_mid": range_mid,
        "atr": atr,
    }


def generate_signal(df):
    context = _range_context(df)

    if context is None:
        return None

    candle = context["signal_candle"]
    range_high = context["range_high"]
    range_low = context["range_low"]
    range_mid = context["range_mid"]
    atr = context["atr"]

    open_price = float(candle["open"])
    high = float(candle["high"])
    low = float(candle["low"])
    close = float(candle["close"])

    sweep_buffer = max(RANGE_SWEEP_BUFFER_PRICE, atr * 0.10)
    reclaim_buffer = max(RANGE_SWEEP_RECLAIM_BUFFER_PRICE, atr * 0.05)
    sl_buffer = max(RANGE_SWEEP_SL_BUFFER_PRICE, atr * 0.15)

    lower_wick = min(open_price, close) - low
    upper_wick = high - max(open_price, close)
    body = abs(close - open_price)

    # =========================
    # BUY: Spring below range low then reclaim
    # =========================
    buy_sweep = low < range_low - sweep_buffer
    buy_reclaim = close > range_low + reclaim_buffer
    buy_rejection = close > open_price and lower_wick >= max(body * 0.40, atr * 0.08)

    if buy_sweep and buy_reclaim and buy_rejection:
        score = RANGE_SWEEP_RECLAIM_BASE_MIN_SCORE

        if close > range_low + (range_high - range_low) * 0.15:
            score += 4

        if lower_wick >= atr * 0.25:
            score += 4

        score = min(score, 100)

        sl_reference = round(low - sl_buffer, 2)
        tp_reference = round(range_mid, 2)

        return {
            "signal": "BUY",
            "score": score,
            "entry_model": "RANGE_SWEEP_RECLAIM_BUY",
            "sl_model": "SWEEP_WICK_SL",
            "tp_model": "RANGE_MIDPOINT_TP",
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "range_high": round(range_high, 2),
            "range_low": round(range_low, 2),
            "range_mid": round(range_mid, 2),
            "sweep_low": round(low, 2),
            "reason": (
                f"Range Sweep Reclaim BUY -> price swept below range low "
                f"{round(range_low, 2)} then closed back inside range -> "
                f"SL below sweep wick {sl_reference} -> TP range midpoint {tp_reference}"
            ),
        }

    # =========================
    # SELL: Upthrust above range high then reject
    # =========================
    sell_sweep = high > range_high + sweep_buffer
    sell_reclaim = close < range_high - reclaim_buffer
    sell_rejection = close < open_price and upper_wick >= max(body * 0.40, atr * 0.08)

    if sell_sweep and sell_reclaim and sell_rejection:
        score = RANGE_SWEEP_RECLAIM_BASE_MIN_SCORE

        if close < range_high - (range_high - range_low) * 0.15:
            score += 4

        if upper_wick >= atr * 0.25:
            score += 4

        score = min(score, 100)

        sl_reference = round(high + sl_buffer, 2)
        tp_reference = round(range_mid, 2)

        return {
            "signal": "SELL",
            "score": score,
            "entry_model": "RANGE_SWEEP_RECLAIM_SELL",
            "sl_model": "SWEEP_WICK_SL",
            "tp_model": "RANGE_MIDPOINT_TP",
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "range_high": round(range_high, 2),
            "range_low": round(range_low, 2),
            "range_mid": round(range_mid, 2),
            "sweep_high": round(high, 2),
            "reason": (
                f"Range Sweep Reclaim SELL -> price swept above range high "
                f"{round(range_high, 2)} then closed back inside range -> "
                f"SL above sweep wick {sl_reference} -> TP range midpoint {tp_reference}"
            ),
        }

    return None