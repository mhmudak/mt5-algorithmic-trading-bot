from config.settings import (
    POSITION_MODE,
    FIXED_LOT,
    RISK_PER_TRADE_PCT,
    TAKE_PROFIT_R_MULTIPLIER,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
    STOP_BUFFER,
    USE_STRUCTURE_STOP,
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

    if USE_STRUCTURE_STOP:
        if signal == "BUY":
            stop_loss = recent_support - STOP_BUFFER
        else:
            stop_loss = recent_resistance + STOP_BUFFER
    else:
        # fallback to ATR-style stop if needed later
        if signal == "BUY":
            stop_loss = entry_price - atr
        else:
            stop_loss = entry_price + atr

    stop_distance = abs(entry_price - stop_loss)

    if stop_distance <= 0:
        return None

    if signal == "BUY":
        take_profit = entry_price + (stop_distance * TAKE_PROFIT_R_MULTIPLIER)
    else:
        take_profit = entry_price - (stop_distance * TAKE_PROFIT_R_MULTIPLIER)

    if POSITION_MODE == "fixed":
        lot = FIXED_LOT
    else:
        # Placeholder for later true risk-based sizing
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
    }