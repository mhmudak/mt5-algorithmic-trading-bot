import MetaTrader5 as mt5
from config.settings import EXECUTION_MODE, MAX_SLIPPAGE


def execute_trade(signal, trade_plan, symbol):
    if EXECUTION_MODE == "SIMULATION":
        print("\n[SIMULATION MODE]")
        print(f"Would execute {signal} trade:")
        for key, value in trade_plan.items():
            print(f"{key}: {value}")
        return True

    if EXECUTION_MODE == "LIVE":
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": trade_plan["lot"],
            "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": trade_plan["entry_price"],
            "sl": trade_plan["stop_loss"],
            "tp": trade_plan["take_profit"],
            "deviation": 10,
            "magic": 123456,
            "comment": "MT5 Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        if result is None:
            print("Order failed:", mt5.last_error())
            return False

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print("Order failed:", result)
            return False

        executed_price = result.price
        expected_price = trade_plan["entry_price"]

        slippage = abs(executed_price - expected_price)

        print(f"[EXECUTION] Expected: {expected_price}")
        print(f"[EXECUTION] Executed: {executed_price}")
        print(f"[EXECUTION] Slippage: {slippage}")

        if slippage > MAX_SLIPPAGE:
            print("[WARNING] High slippage detected!")

        print("Order result:", result)
        return True

    return False