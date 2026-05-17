import MetaTrader5 as mt5

from config.settings import (
    EXECUTION_MODE,
    MAX_SLIPPAGE,
    ENABLE_PRICE_DRIFT_GUARD,
    MAX_ENTRY_PRICE_DRIFT,
)
from src.notifier import send_telegram_message
from src.trade_tracker import register_executed_trade


def get_supported_filling_modes(symbol):
    symbol_info = mt5.symbol_info(symbol)

    fallback_modes = [
        mt5.ORDER_FILLING_RETURN,
        mt5.ORDER_FILLING_IOC,
        mt5.ORDER_FILLING_FOK,
    ]

    if symbol_info is None:
        return fallback_modes

    broker_mode = getattr(symbol_info, "filling_mode", None)

    modes = []

    if broker_mode in fallback_modes:
        modes.append(broker_mode)

    for mode in fallback_modes:
        if mode not in modes:
            modes.append(mode)

    return modes


def execute_trade(signal, trade_plan, symbol):
    if EXECUTION_MODE == "SIMULATION":
        print("\n[SIMULATION MODE]")
        print(f"Would execute {signal} trade:")

        for key, value in trade_plan.items():
            print(f"{key}: {value}")

        send_telegram_message(
            f"🧪 Simulation Trade\n"
            f"Symbol: {symbol}\n"
            f"Signal: {signal}\n"
            f"Entry: {trade_plan['entry_price']}\n"
            f"SL: {trade_plan['stop_loss']}\n"
            f"TP: {trade_plan['take_profit']}\n"
            f"Lot: {trade_plan['lot']}"
        )
        return True

    if EXECUTION_MODE != "LIVE":
        send_telegram_message(
            f"❌ Execution Failed\n"
            f"Reason: Unknown EXECUTION_MODE={EXECUTION_MODE}"
        )
        return False

    tick = mt5.symbol_info_tick(symbol)

    if tick is None:
        error_message = f"❌ Order failed: no tick data for {symbol} | {mt5.last_error()}"
        print(error_message)
        send_telegram_message(error_message)
        return False

    request_price = tick.ask if signal == "BUY" else tick.bid
    expected_price = trade_plan["entry_price"]

    if signal == "BUY":
        adverse_drift = request_price - expected_price
    else:
        adverse_drift = expected_price - request_price

    if ENABLE_PRICE_DRIFT_GUARD and adverse_drift > MAX_ENTRY_PRICE_DRIFT:
        error_message = (
            f"🚫 Execution Blocked by Price Drift\n"
            f"Symbol: {symbol}\n"
            f"Signal: {signal}\n"
            f"Expected Entry: {expected_price}\n"
            f"Current Price: {round(request_price, 2)}\n"
            f"Adverse Drift: {round(adverse_drift, 2)}\n"
            f"Max Allowed: {MAX_ENTRY_PRICE_DRIFT}"
        )

        print(error_message)
        send_telegram_message(error_message)
        return False

    base_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": trade_plan["lot"],
        "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": request_price,
        "sl": trade_plan["stop_loss"],
        "tp": trade_plan["take_profit"],
        "deviation": 10,
        "magic": 123456,
        "comment": trade_plan.get("comment", "MhMudBot")[:31],
        "type_time": mt5.ORDER_TIME_GTC,
    }

    result = None
    successful_filling_mode = None
    last_error_message = None

    for filling_mode in get_supported_filling_modes(symbol):
        request = base_request.copy()
        request["type_filling"] = filling_mode

        result = mt5.order_send(request)

        if result is None:
            last_error_message = (
                f"Order failed with filling={filling_mode}: {mt5.last_error()}"
            )
            continue

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            successful_filling_mode = filling_mode
            break

        last_error_message = f"Order rejected with filling={filling_mode}: {result}"

        if result.retcode == 10030:
            continue

        break

    if result is None:
        error_message = f"❌ Order failed: {last_error_message}"
        print(error_message)
        send_telegram_message(error_message)
        return False

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        error_message = f"❌ Order rejected: {result}"
        print(error_message)
        send_telegram_message(error_message)
        return False

    executed_price = result.price
    slippage = abs(executed_price - expected_price)

    print(f"[EXECUTION] Expected: {expected_price}")
    print(f"[EXECUTION] Request Price: {request_price}")
    print(f"[EXECUTION] Executed: {executed_price}")
    print(f"[EXECUTION] Slippage: {slippage}")
    print(f"[EXECUTION] Filling Mode: {successful_filling_mode}")
    print("Order result:", result)

    if slippage > MAX_SLIPPAGE:
        print("[WARNING] High slippage detected!")
        send_telegram_message(
            f"⚠️ High Slippage Detected\n"
            f"Symbol: {symbol}\n"
            f"Signal: {signal}\n"
            f"Expected: {expected_price}\n"
            f"Executed: {executed_price}\n"
            f"Slippage: {round(slippage, 2)}"
        )

    register_executed_trade(symbol, signal, trade_plan, result)

    send_telegram_message(
        f"✅ Trade Executed\n"
        f"Symbol: {symbol}\n"
        f"Signal: {signal}\n"
        f"Expected: {expected_price}\n"
        f"Executed: {executed_price}\n"
        f"SL: {trade_plan['stop_loss']}\n"
        f"TP: {trade_plan['take_profit']}\n"
        f"Lot: {trade_plan['lot']}\n"
        f"Slippage: {round(slippage, 2)}\n"
        f"Filling Mode: {successful_filling_mode}"
    )

    return True