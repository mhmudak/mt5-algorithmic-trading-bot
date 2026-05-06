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


def calculate_trade_plan(df, signal, tick, account_balance, signal_data=None):
    if signal not in ["BUY", "SELL"]:
        return None

    last = df.iloc[-1]
    atr = last["atr_14"]

    entry_price = tick.ask if signal == "BUY" else tick.bid

    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 1):-1]
    recent_resistance = recent_data["high"].max()
    recent_support = recent_data["low"].min()

    strategy = signal_data.get("strategy") if signal_data else None

    # =========================
    # STOP LOSS
    # =========================
    if strategy == "ORB" and signal_data:
        orb_high = signal_data.get("orb_high")
        orb_low = signal_data.get("orb_low")
        entry_model = signal_data.get("entry_model", "BREAKOUT")

        if orb_high is None or orb_low is None:
            return None

        orb_width = orb_high - orb_low
        breakout_buffer = max(atr * 0.15, orb_width * 0.05, 1.5)
        execution_buffer = max(atr * 0.10, 1.0)

        if entry_model == "BREAKOUT":
            if signal == "SELL":
                stop_loss = orb_high + breakout_buffer
            else:
                stop_loss = orb_low - breakout_buffer
        else:
            # WAIT_RETEST / EXTRA / tighter execution mode
            if signal == "SELL":
                stop_loss = entry_price + execution_buffer
            else:
                stop_loss = entry_price - execution_buffer

    elif strategy == "LIQUIDITY_CANDLE" and signal_data:
        sl_reference = signal_data.get("sl_reference")
        if sl_reference is None:
            return None
        stop_loss = sl_reference

    elif strategy == "LIQUIDITY_SWEEP" and signal_data:
        sweep_low = signal_data.get("sweep_low")
        sweep_high = signal_data.get("sweep_high")

        if signal == "BUY" and sweep_low is not None:
            stop_loss = sweep_low - max(atr * 0.15, 1.0)
        elif signal == "SELL" and sweep_high is not None:
            stop_loss = sweep_high + max(atr * 0.15, 1.0)
        else:
            return None

    elif strategy == "FRACTAL_SWEEP" and signal_data:
        sl_reference = signal_data.get("sl_reference")

        if sl_reference is None:
            return None

        if signal == "BUY" and sl_reference >= entry_price:
            return None

        if signal == "SELL" and sl_reference <= entry_price:
            return None

        stop_loss = sl_reference
        
    elif strategy == "CRT_TBS" and signal_data:
        sl_reference = signal_data.get("sl_reference")

        if sl_reference is None:
            return None

        if signal == "BUY" and sl_reference >= entry_price:
            return None

        if signal == "SELL" and sl_reference <= entry_price:
            return None

        stop_loss = sl_reference

    elif strategy == "RELIEF_RALLY" and signal_data:
        sl_reference = signal_data.get("sl_reference")

        if sl_reference is None:
            return None

        if signal == "BUY" and sl_reference >= entry_price:
            return None

        if signal == "SELL" and sl_reference <= entry_price:
            return None

        stop_loss = sl_reference

    elif strategy == "FVG" and signal_data and signal_data.get("sl_reference") is not None:
        stop_loss = signal_data["sl_reference"]

    elif strategy == "HEAD_SHOULDERS" and signal_data:
        neckline = signal_data.get("neckline")
        if neckline is None:
            return None

        if signal == "SELL":
            stop_loss = max(recent_resistance + STOP_EXTRA_BUFFER_PRICE, neckline + atr * 0.25)
        else:
            stop_loss = min(recent_support - STOP_EXTRA_BUFFER_PRICE, neckline - atr * 0.25)

    elif strategy == "TRIANGLE_PENNANT" and signal_data:
        triangle_high = signal_data.get("triangle_high")
        triangle_low = signal_data.get("triangle_low")

        if triangle_high is None or triangle_low is None:
            return None

        if signal == "BUY":
            stop_loss = triangle_low - atr * 0.25
        else:
            stop_loss = triangle_high + atr * 0.25

    elif strategy == "WAVETREND_PIVOT" and signal_data:
        sl_reference = signal_data.get("sl_reference")
        if sl_reference is None:
            return None
        stop_loss = sl_reference
        
    elif USE_STRUCTURE_STOP:
        if signal == "BUY":
            stop_loss = recent_support - STOP_BUFFER - STOP_EXTRA_BUFFER_PRICE
        else:
            stop_loss = recent_resistance + STOP_BUFFER + STOP_EXTRA_BUFFER_PRICE

    else:
        if signal == "BUY":
            stop_loss = entry_price - atr
        else:
            stop_loss = entry_price + atr

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
    if strategy == "LIQUIDITY_CANDLE" and signal_data:
        if signal == "BUY":
            take_profit = entry_price + (stop_distance * LIQUIDITY_CANDLE_R_MULTIPLIER)
        else:
            take_profit = entry_price - (stop_distance * LIQUIDITY_CANDLE_R_MULTIPLIER)

    elif strategy == "FVG" and signal_data:
        height = signal_data.get("pattern_height", 0)
        if height <= 0:
            return None

        if signal == "BUY":
            take_profit = min(recent_resistance, entry_price + height)
        else:
            take_profit = max(recent_support, entry_price - height)

    elif strategy == "LIQUIDITY_SWEEP" and signal_data:
        rr = 1.5

        if signal == "BUY":
            take_profit = entry_price + (stop_distance * rr)
        else:
            take_profit = entry_price - (stop_distance * rr)

    elif strategy == "ORB" and signal_data:
        entry_model = signal_data.get("entry_model", "BREAKOUT")

        # based on your real ORB cases:
        # breakout entries deserve safer RR
        # retest entries can target higher RR
        if entry_model == "BREAKOUT":
            rr = 1.8
        else:
            rr = 2.2

        if signal == "BUY":
            take_profit = entry_price + (stop_distance * rr)
        else:
            take_profit = entry_price - (stop_distance * rr)

    elif strategy == "WAVETREND_PIVOT" and signal_data:
        pivot_target_level = signal_data.get("pivot_target_level")
        if pivot_target_level is None:
            return None
        take_profit = pivot_target_level

    elif strategy in [
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
    ] and signal_data:
        height = signal_data.get("pattern_height", 0)

        if height and height > 0:
            if signal == "BUY":
                take_profit = entry_price + height
            else:
                take_profit = entry_price - height

        elif strategy in ["HEAD_SHOULDERS", "RELIEF_RALLY"]:
            rr = 1.5

            if signal == "BUY":
                take_profit = entry_price + (stop_distance * rr)
            else:
                take_profit = entry_price - (stop_distance * rr)

        else:
            return None

    elif USE_STRUCTURE_TAKE_PROFIT:
        if signal == "BUY":
            take_profit = recent_resistance - tp_buffer
            if take_profit <= entry_price:
                return None
        else:
            take_profit = recent_support + tp_buffer
            if take_profit >= entry_price:
                return None

    else:
        if signal == "BUY":
            take_profit = entry_price + (stop_distance * 1.5)
        else:
            take_profit = entry_price - (stop_distance * 1.5)

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