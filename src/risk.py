from config.settings import (
    POSITION_MODE,
    FIXED_LOT,
    RISK_PER_TRADE_PCT,
    STOP_LOSS_ATR_MULTIPLIER,
    TAKE_PROFIT_R_MULTIPLIER,
)


def calculate_trade_plan(df, signal, tick, account_balance):
    if signal not in ["BUY", "SELL"]:
        return None

    last = df.iloc[-1]
    atr = last["atr_14"]

    entry_price = tick.ask if signal == "BUY" else tick.bid
    stop_distance = atr * STOP_LOSS_ATR_MULTIPLIER

    if signal == "BUY":
        stop_loss = entry_price - stop_distance
        take_profit = entry_price + (stop_distance * TAKE_PROFIT_R_MULTIPLIER)
    else:
        stop_loss = entry_price + stop_distance
        take_profit = entry_price - (stop_distance * TAKE_PROFIT_R_MULTIPLIER)

    if POSITION_MODE == "fixed":
        lot = FIXED_LOT
    else:
        # Placeholder for later true risk-based sizing
        # For now, keep simple fallback
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
    }