import MetaTrader5 as mt5

from config.settings import EXECUTION_MODE, MAX_SLIPPAGE
from src.notifier import send_telegram_message
from src.trade_tracker import register_executed_trade


def execute_trade(signal, trade_plan, symbol):
    if EXECUTION_MODE == "SIMULATION":
        print("\n[SIMULATION MODE]")
        print(f"Would execute {signal} trade:")
        for key, value in trade_plan.items():
            print(f"{key}: {value}")

        send_telegram_message(
            f"🧪 *Simulation Trade*\n"
            f"Symbol: {symbol}\n"
            f"Signal: {signal}\n"
            f"Entry: {trade_plan['entry_price']}\n"
            f"SL: {trade_plan['stop_loss']}\n"
            f"TP: {trade_plan['take_profit']}\n"
            f"Lot: {trade_plan['lot']}"
        )
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
            "comment": "🤖 MhMud Bot MT5",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        if result is None:
            error_message = f"❌ Order failed: {mt5.last_error()}"
            print(error_message)
            send_telegram_message(error_message)
            return False

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            error_message = f"❌ Order rejected: {result}"
            print(error_message)
            send_telegram_message(error_message)
            return False

        executed_price = result.price
        expected_price = trade_plan["entry_price"]
        slippage = abs(executed_price - expected_price)

        print(f"[EXECUTION] Expected: {expected_price}")
        print(f"[EXECUTION] Executed: {executed_price}")
        print(f"[EXECUTION] Slippage: {slippage}")

        if slippage > MAX_SLIPPAGE:
            print("[WARNING] High slippage detected!")
            send_telegram_message(
                f"⚠️ *High Slippage Detected*\n"
                f"Symbol: {symbol}\n"
                f"Signal: {signal}\n"
                f"Expected: {expected_price}\n"
                f"Executed: {executed_price}\n"
                f"Slippage: {slippage}"
            )

        print("Order result:", result)

        register_executed_trade(symbol, signal, trade_plan, result)

        send_telegram_message(
            f"✅ *Trade Executed*\n"
            f"Symbol: {symbol}\n"
            f"Signal: {signal}\n"
            f"Expected: {expected_price}\n"
            f"Executed: {executed_price}\n"
            f"SL: {trade_plan['stop_loss']}\n"
            f"TP: {trade_plan['take_profit']}\n"
            f"Lot: {trade_plan['lot']}\n"
            f"Slippage: {slippage}"
        )

        return True

    return False