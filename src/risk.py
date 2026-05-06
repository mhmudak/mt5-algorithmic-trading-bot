from config.settings import (
    POSITION_MODE,
    FIXED_LOT,
    RISK_PER_TRADE_PCT,
    BREAKOUT_LOOKBACK,
    STOP_BUFFER,
    USE_STRUCTURE_STOP,
    USE_STRUCTURE_TAKE_PROFIT,
    STOP_EXTRA_BUFFER_PRICE,
    TP_EARLY_BUFFER_PRICE,
    ENABLE_ATR_ADAPTIVE_TP,
    TP_ATR_BUFFER_MULTIPLIER,
    MIN_TP_BUFFER_PRICE,
    MAX_TP_BUFFER_PRICE,
    LIQUIDITY_CANDLE_R_MULTIPLIER,
)


STRATEGY_SL_REFERENCE_MODELS = {
    "ORB",
    "LIQUIDITY_CANDLE",
    "LIQUIDITY_SWEEP",
    "FRACTAL_SWEEP",
    "CRT_TBS",
    "LIQUIDITY_TRAP",
    "ORDER_BLOCK",
    "SMT",
    "SMT_PRO",
    "OB_FVG_COMBO",
    "RELIEF_RALLY",
    "FVG",
    "HEAD_SHOULDERS",
    "TRIANGLE_PENNANT",
    "WAVETREND_PIVOT",
    "FLAG",
    "FLAG_REFINED",
    "SNIPER_V2",
    "STRICT",
    "FAST",
    "HTF_TREND_PULLBACK",
    "SESSION_ORB_RETEST",
    "VWAP_RECLAIM",
    "BREAKER_BLOCK",
    "MTF_OB_ENTRY",
    "FCR_M1_FVG",
}


def _valid_stop_loss(signal, entry_price, stop_loss):
    if stop_loss is None:
        return False

    if signal == "BUY" and stop_loss >= entry_price:
        return False

    if signal == "SELL" and stop_loss <= entry_price:
        return False

    return True


def _valid_take_profit(signal, entry_price, take_profit):
    if take_profit is None:
        return False

    if signal == "BUY" and take_profit <= entry_price:
        return False

    if signal == "SELL" and take_profit >= entry_price:
        return False

    return True


def _rr_target(signal, entry_price, stop_distance, rr):
    if signal == "BUY":
        return entry_price + (stop_distance * rr)

    return entry_price - (stop_distance * rr)


def _structure_stop(signal, recent_support, recent_resistance):
    if signal == "BUY":
        return recent_support - STOP_BUFFER - STOP_EXTRA_BUFFER_PRICE

    return recent_resistance + STOP_BUFFER + STOP_EXTRA_BUFFER_PRICE


def _fallback_atr_stop(signal, entry_price, atr):
    if signal == "BUY":
        return entry_price - atr

    return entry_price + atr


def _fallback_structure_take_profit(signal, entry_price, recent_support, recent_resistance, tp_buffer):
    if signal == "BUY":
        take_profit = recent_resistance - tp_buffer
        if take_profit <= entry_price:
            return None
        return take_profit

    take_profit = recent_support + tp_buffer
    if take_profit >= entry_price:
        return None
    return take_profit


def _pattern_height_take_profit(signal, entry_price, height):
    if height is None or height <= 0:
        return None

    if signal == "BUY":
        return entry_price + height

    return entry_price - height


def _strategy_fallback_take_profit(strategy, signal, entry_price, stop_distance, signal_data, recent_support, recent_resistance):
    height = signal_data.get("pattern_height", 0) if signal_data else 0

    if strategy == "LIQUIDITY_CANDLE":
        return _rr_target(signal, entry_price, stop_distance, LIQUIDITY_CANDLE_R_MULTIPLIER)

    if strategy == "FVG":
        if height <= 0:
            return None

        if signal == "BUY":
            return min(recent_resistance, entry_price + height)

        return max(recent_support, entry_price - height)

    if strategy == "LIQUIDITY_SWEEP":
        return _rr_target(signal, entry_price, stop_distance, 1.5)

    if strategy == "ORB":
        entry_model = signal_data.get("entry_model", "BREAKOUT") if signal_data else "BREAKOUT"
        rr = 1.8 if entry_model == "BREAKOUT" else 2.2
        return _rr_target(signal, entry_price, stop_distance, rr)

    if strategy == "WAVETREND_PIVOT":
        pivot_target_level = signal_data.get("pivot_target_level") if signal_data else None
        return pivot_target_level

    if strategy in [
        "HEAD_SHOULDERS",
        "TRIANGLE_PENNANT",
        "ORDER_BLOCK",
        "SMT",
        "SMT_PRO",
        "CRT_TBS",
        "OB_FVG_COMBO",
        "LIQUIDITY_TRAP",
        "RELIEF_RALLY",
        "FRACTAL_SWEEP",
    ]:
        pattern_tp = _pattern_height_take_profit(signal, entry_price, height)

        if pattern_tp is not None:
            return pattern_tp

        if strategy in ["HEAD_SHOULDERS", "RELIEF_RALLY"]:
            return _rr_target(signal, entry_price, stop_distance, 1.5)

        return None

    return _rr_target(signal, entry_price, stop_distance, 1.5)


def calculate_trade_plan(df, signal, tick, account_balance, signal_data=None):
    if signal not in ["BUY", "SELL"]:
        return None

    if len(df) < BREAKOUT_LOOKBACK + 2:
        return None

    # Use closed candle for ATR/context, and tick only for the actual entry price.
    last_closed = df.iloc[-2]
    atr = last_closed["atr_14"]

    if atr <= 0:
        return None

    entry_price = tick.ask if signal == "BUY" else tick.bid

    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 1):-1]
    recent_resistance = recent_data["high"].max()
    recent_support = recent_data["low"].min()

    strategy = signal_data.get("strategy") if signal_data else None

    # =========================
    # STOP LOSS
    # =========================
    stop_loss = None

    if strategy in STRATEGY_SL_REFERENCE_MODELS and signal_data:
        sl_reference = signal_data.get("sl_reference")

        if not _valid_stop_loss(signal, entry_price, sl_reference):
            return None

        stop_loss = sl_reference

    elif USE_STRUCTURE_STOP:
        stop_loss = _structure_stop(signal, recent_support, recent_resistance)

    else:
        stop_loss = _fallback_atr_stop(signal, entry_price, atr)

    if not _valid_stop_loss(signal, entry_price, stop_loss):
        return None

    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0:
        return None

    # =========================
    # ADAPTIVE TP BUFFER
    # =========================
    if ENABLE_ATR_ADAPTIVE_TP:
        tp_buffer = atr * TP_ATR_BUFFER_MULTIPLIER
        tp_buffer = max(MIN_TP_BUFFER_PRICE, tp_buffer)
        tp_buffer = min(MAX_TP_BUFFER_PRICE, tp_buffer)
    else:
        tp_buffer = TP_EARLY_BUFFER_PRICE

    # =========================
    # TAKE PROFIT
    # =========================
    take_profit = None

    tp_reference = signal_data.get("tp_reference") if signal_data else None

    if _valid_take_profit(signal, entry_price, tp_reference):
        take_profit = tp_reference

    else:
        take_profit = _strategy_fallback_take_profit(
            strategy=strategy,
            signal=signal,
            entry_price=entry_price,
            stop_distance=stop_distance,
            signal_data=signal_data,
            recent_support=recent_support,
            recent_resistance=recent_resistance,
        )

    if not _valid_take_profit(signal, entry_price, take_profit):
        if USE_STRUCTURE_TAKE_PROFIT:
            take_profit = _fallback_structure_take_profit(
                signal=signal,
                entry_price=entry_price,
                recent_support=recent_support,
                recent_resistance=recent_resistance,
                tp_buffer=tp_buffer,
            )

    if not _valid_take_profit(signal, entry_price, take_profit):
        return None

    min_tp_distance = 0.3
    if abs(take_profit - entry_price) < min_tp_distance:
        return None

    if POSITION_MODE == "fixed":
        lot = FIXED_LOT
    else:
        lot = round((account_balance * RISK_PER_TRADE_PCT) / stop_distance, 2)

    return {
        "signal": signal,
        "entry_price": round(entry_price, 2),
        "stop_loss": round(stop_loss, 2),
        "take_profit": round(take_profit, 2),
        "stop_distance": round(stop_distance, 2),
        "tp_buffer": round(tp_buffer, 2),
        "lot": lot,
        "risk_mode": POSITION_MODE,
        "risk_pct": RISK_PER_TRADE_PCT,
        "account_balance": account_balance,
        "recent_resistance": round(recent_resistance, 2),
        "recent_support": round(recent_support, 2),
        "atr": round(atr, 2),
    }