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
)


def calculate_trade_plan(df, signal, tick, account_balance):
    if signal not in ["BUY", "SELL"]:
        return None

    last = df.iloc[-1]
    atr = last["atr_14"]

    entry_price = tick.ask if signal == "BUY" else tick.bid

    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 1):-1]
    recent_resistance = recent_data["high"].max()
    recent_support = recent_data["low"].min()

    # =========================
    # STOP LOSS
    # =========================
    if USE_STRUCTURE_STOP:
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
    # TAKE PROFIT
    # =========================
    if USE_STRUCTURE_TAKE_PROFIT:
        if signal == "BUY":
            take_profit = recent_resistance - TP_EARLY_BUFFER_PRICE
            if take_profit <= entry_price:
                return None
        else:
            take_profit = recent_support + TP_EARLY_BUFFER_PRICE
            if take_profit >= entry_price:
                return None
    else:
        if signal == "BUY":
            take_profit = entry_price + (stop_distance * 1.5)
        else:
            take_profit = entry_price - (stop_distance * 1.5)

    if POSITION_MODE == "fixed":
        lot = FIXED_LOT
    else:
        lot = FIXED_LOT

    return {
        "signal": signal,
        "entry_price": round(entry_price, 2),
        "stop_loss": round(stop_loss, 2),
        "take_profit": round(take_profit, 2),
        "stop_distance": round(stop_distance, 2),
        "lot": lot,
        "risk_mode": POSITION_MODE,
        "risk_pct": RISK_PER_TRADE_PCT,
        "account_balance": account_balance,
        "recent_resistance": round(recent_resistance, 2),
        "recent_support": round(recent_support, 2),
        "atr": round(atr, 2),
    }