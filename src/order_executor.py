import time
from time import perf_counter

from src.logger import logger
from datetime import datetime
import MetaTrader5 as mt5

from config.settings import (
    EXECUTION_MODE,
    MAX_SLIPPAGE,
    ENABLE_EXECUTION_FAVORABLE_DRIFT_GUARD,
    MAX_FAVORABLE_EXECUTION_DRIFT,
    ENABLE_LOW_RR_STRICT_ADVERSE_SLIPPAGE_GUARD,
    LOW_RR_STRICT_SLIPPAGE_RR_THRESHOLD,
    LOW_RR_MAX_ADVERSE_SLIPPAGE,
    ENABLE_PRICE_DRIFT_GUARD,
    MAX_ENTRY_PRICE_DRIFT,
    ENABLE_HIGH_SLIPPAGE_RETRACEMENT,
    HIGH_SLIPPAGE_RETRACEMENT_PRICE,
    HIGH_SLIPPAGE_EXTRA_SL_PRICE,
    HIGH_SLIPPAGE_WAIT_TIMEOUT_SECONDS,
    HIGH_SLIPPAGE_WAIT_POLL_SECONDS,
    ENABLE_MOMENTUM_CONTINUATION_ON_PRICE_DRIFT,
    MOMENTUM_CONTINUATION_MAX_DRIFT_PRICE,
    MOMENTUM_CONTINUATION_MIN_RR,
    FVG_CE_MITIGATION_ALLOW_MOMENTUM_DRIFT,
    ENABLE_BREAKER_BLOCK_EXTRA_SL,
    BREAKER_BLOCK_EXTRA_SL_PRICE,
    ENABLE_WAVETREND_STRICT_SL,
    WAVETREND_MOMENTUM_MAX_STOP_DISTANCE,
    ENABLE_ROLLOVER_TRADING_BLOCK,
    ROLLOVER_BLOCK_WINDOWS,
)
from src.notifier import send_telegram_message
from src.trade_tracker import register_executed_trade
from src.execution_block_memory import remember_blocked_setup

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


def get_current_request_price(symbol, signal):
    tick = mt5.symbol_info_tick(symbol)

    if tick is None:
        return None

    if signal == "BUY":
        return tick.ask

    if signal == "SELL":
        return tick.bid

    return None


def calculate_adverse_drift(signal, expected_price, current_price):
    if signal == "BUY":
        return current_price - expected_price

    if signal == "SELL":
        return expected_price - current_price

    return None


def get_high_slippage_target(signal, current_price):
    if signal == "BUY":
        return round(current_price - HIGH_SLIPPAGE_RETRACEMENT_PRICE, 2)

    if signal == "SELL":
        return round(current_price + HIGH_SLIPPAGE_RETRACEMENT_PRICE, 2)

    return None


def is_retracement_reached(signal, current_price, target_price):
    if signal == "BUY":
        return current_price <= target_price

    if signal == "SELL":
        return current_price >= target_price

    return False


def adjust_sl_after_retracement(signal, original_entry, original_sl, new_entry):
    original_stop_distance = abs(original_entry - original_sl)
    new_stop_distance = original_stop_distance + HIGH_SLIPPAGE_EXTRA_SL_PRICE

    if signal == "BUY":
        return round(new_entry - new_stop_distance, 2)

    if signal == "SELL":
        return round(new_entry + new_stop_distance, 2)

    return original_sl


def wait_for_high_slippage_retracement(
    signal,
    trade_plan,
    symbol,
    current_price,
    slippage,
):
    expected_price = trade_plan["entry_price"]
    original_sl = trade_plan["stop_loss"]
    target_price = get_high_slippage_target(signal, current_price)

    send_telegram_message(
        f"⏳ High Slippage Retracement Mode\n"
        f"Symbol: {symbol}\n"
        f"Signal: {signal}\n"
        f"Expected: {expected_price}\n"
        f"Current: {round(current_price, 2)}\n"
        f"Slippage: {round(slippage, 2)}\n\n"
        f"Waiting for target: {target_price}\n"
        f"SL will be moved {HIGH_SLIPPAGE_EXTRA_SL_PRICE} USD farther."
    )

    start_time = time.time()

    while time.time() - start_time <= HIGH_SLIPPAGE_WAIT_TIMEOUT_SECONDS:
        latest_price = get_current_request_price(symbol, signal)

        if latest_price is None:
            time.sleep(HIGH_SLIPPAGE_WAIT_POLL_SECONDS)
            continue

        if is_retracement_reached(signal, latest_price, target_price):
            adjusted_plan = trade_plan.copy()
            adjusted_plan["entry_price"] = round(latest_price, 2)
            adjusted_plan["stop_loss"] = adjust_sl_after_retracement(
                signal=signal,
                original_entry=expected_price,
                original_sl=original_sl,
                new_entry=latest_price,
            )
            adjusted_plan["reason"] = (
                f"{trade_plan.get('reason', '')} | HIGH_SLIPPAGE_RETRACEMENT"
            )
            adjusted_plan["comment"] = trade_plan.get("comment", "HighSlipRetrace")[:31]

            send_telegram_message(
                f"✅ High Slippage Retracement Reached\n"
                f"Symbol: {symbol}\n"
                f"Signal: {signal}\n"
                f"Target: {target_price}\n"
                f"Current: {round(latest_price, 2)}\n"
                f"New SL: {adjusted_plan['stop_loss']}"
            )

            return adjusted_plan

        time.sleep(HIGH_SLIPPAGE_WAIT_POLL_SECONDS)

    send_telegram_message(
        f"⌛ High Slippage Retracement Expired\n"
        f"Symbol: {symbol}\n"
        f"Signal: {signal}\n"
        f"Expected: {expected_price}\n"
        f"Initial Current: {round(current_price, 2)}\n"
        f"Target was: {target_price}\n\n"
        f"No trade executed."
    )

    return None


def calculate_rr(signal, entry, sl, tp):
    try:
        if tp in [None, 0, 0.0]:
            return None

        if signal == "BUY":
            risk = entry - sl
            reward = tp - entry
        elif signal == "SELL":
            risk = sl - entry
            reward = entry - tp
        else:
            return None

        if risk <= 0:
            return None

        return round(reward / risk, 2)

    except Exception:
        return None


def rebase_trade_plan_for_momentum(signal, trade_plan, current_price):
    original_entry = trade_plan["entry_price"]
    original_sl = trade_plan["stop_loss"]
    original_tp = trade_plan["take_profit"]

    stop_distance = abs(original_entry - original_sl)
    target_distance = abs(original_entry - original_tp)

    adjusted_plan = trade_plan.copy()
    adjusted_plan["entry_price"] = round(current_price, 2)

    if signal == "BUY":
        adjusted_plan["stop_loss"] = round(current_price - stop_distance, 2)
        adjusted_plan["take_profit"] = round(current_price + target_distance, 2)

    elif signal == "SELL":
        adjusted_plan["stop_loss"] = round(current_price + stop_distance, 2)
        adjusted_plan["take_profit"] = round(current_price - target_distance, 2)

    adjusted_plan["reason"] = (
        f"{trade_plan.get('reason', '')} | MOMENTUM_CONTINUATION_AFTER_PRICE_DRIFT"
    )
    adjusted_plan["comment"] = trade_plan.get("comment", "MomentumDrift")[:31]

    adjusted_plan = apply_wavetrend_strict_sl(
        signal=signal,
        trade_plan=adjusted_plan,
        entry_price=current_price,
    )

    return adjusted_plan


def is_fvg_ce_mitigation_trade(trade_plan):
    strategy = str(trade_plan.get("strategy", "")).upper()
    entry_model = str(trade_plan.get("entry_model", "")).upper()

    return strategy == "FVG_CE_MITIGATION" or "FVG_CE" in entry_model


def is_breaker_block_trade(trade_plan):
    strategy = str(trade_plan.get("strategy", "")).upper()
    entry_model = str(trade_plan.get("entry_model", "")).upper()

    return strategy == "BREAKER_BLOCK" or "BREAKER" in entry_model

def is_wavetrend_momentum_trade(trade_plan):
    strategy = str(trade_plan.get("strategy", "")).upper()
    entry_model = str(trade_plan.get("entry_model", "")).upper()

    return strategy == "WAVETREND_MOMENTUM" or "WAVETREND" in entry_model


def apply_wavetrend_strict_sl(signal, trade_plan, entry_price=None):
    if not ENABLE_WAVETREND_STRICT_SL:
        return trade_plan

    if not is_wavetrend_momentum_trade(trade_plan):
        return trade_plan

    adjusted_plan = trade_plan.copy()

    entry = float(entry_price or adjusted_plan["entry_price"])
    current_sl = float(adjusted_plan["stop_loss"])
    max_stop = float(WAVETREND_MOMENTUM_MAX_STOP_DISTANCE)

    if signal == "BUY":
        capped_sl = round(entry - max_stop, 2)

        if current_sl < capped_sl:
            adjusted_plan["stop_loss"] = capped_sl

    elif signal == "SELL":
        capped_sl = round(entry + max_stop, 2)

        if current_sl > capped_sl:
            adjusted_plan["stop_loss"] = capped_sl

    adjusted_plan["reason"] = (
        f"{trade_plan.get('reason', '')} | WAVETREND_STRICT_SL"
    )
    adjusted_plan["comment"] = trade_plan.get("comment", "WTStrictSL")[:31]

    return adjusted_plan


def apply_breaker_block_extra_sl(signal, trade_plan):
    if not ENABLE_BREAKER_BLOCK_EXTRA_SL:
        return trade_plan

    if not is_breaker_block_trade(trade_plan):
        return trade_plan

    adjusted_plan = trade_plan.copy()
    original_sl = trade_plan["stop_loss"]

    if signal == "BUY":
        adjusted_plan["stop_loss"] = round(
            original_sl - BREAKER_BLOCK_EXTRA_SL_PRICE,
            2,
        )

    elif signal == "SELL":
        adjusted_plan["stop_loss"] = round(
            original_sl + BREAKER_BLOCK_EXTRA_SL_PRICE,
            2,
        )

    adjusted_plan["reason"] = (
        f"{trade_plan.get('reason', '')} | BREAKER_BLOCK_EXTRA_SL"
    )
    adjusted_plan["comment"] = trade_plan.get("comment", "BreakerSLBuffer")[:31]

    return adjusted_plan

def _parse_time(value):
    return datetime.strptime(value, "%H:%M").time()


def _is_now_in_window(start, end):
    now = datetime.now().time()
    start_time = _parse_time(start)
    end_time = _parse_time(end)

    if start_time <= end_time:
        return start_time <= now <= end_time

    return now >= start_time or now <= end_time


def is_rollover_trading_blocked():
    if not ENABLE_ROLLOVER_TRADING_BLOCK:
        return False, None

    for window in ROLLOVER_BLOCK_WINDOWS:
        if _is_now_in_window(window["start"], window["end"]):
            return True, window.get("name", "ROLLOVER")

    return False, None

def _execution_timing_ms(start_time):
    try:
        return round((perf_counter() - start_time) * 1000, 2)
    except Exception:
        return None


def _log_execution_timing(stage, start_time, **extra):
    elapsed_ms = _execution_timing_ms(start_time)

    details = " ".join([
        f"{key}={value}"
        for key, value in extra.items()
        if value is not None
    ])

    logger.info(
        f"[EXECUTION TIMING] stage={stage} elapsed_ms={elapsed_ms} {details}"
    )

    return elapsed_ms

def calculate_directional_slippage(signal, expected_price, execution_price):
    # Directional slippage:
    # BUY: execution above expected is adverse; below expected is favorable.
    # SELL: execution below expected is adverse; above expected is favorable.
    try:
        expected = float(expected_price)
        executed = float(execution_price)
    except Exception:
        return {
            "signed": None,
            "adverse": None,
            "favorable": None,
            "absolute": None,
            "direction": "INVALID",
        }

    signal = str(signal or '').upper().strip()

    if signal == "BUY":
        signed = executed - expected
    elif signal == "SELL":
        signed = expected - executed
    else:
        signed = abs(executed - expected)

    adverse = max(0.0, signed)
    favorable = max(0.0, -signed)
    absolute = abs(executed - expected)

    return {
        "signed": round(signed, 4),
        "adverse": round(adverse, 4),
        "favorable": round(favorable, 4),
        "absolute": round(absolute, 4),
        "direction": signal,
    }


def get_trade_plan_rr_for_execution_guard(trade_plan):
    if not isinstance(trade_plan, dict):
        return None

    for key in ("rr", "risk_reward", "rr_value", "risk_reward_ratio"):
        value = trade_plan.get(key)
        try:
            if value is not None:
                rr = float(value)
                if rr > 0:
                    return rr
        except Exception:
            pass

    try:
        entry = float(trade_plan.get("entry_price"))
        sl = float(trade_plan.get("stop_loss"))
        tp = float(trade_plan.get("take_profit"))

        risk = abs(entry - sl)
        reward = abs(tp - entry)

        if risk <= 0:
            return None

        return round(reward / risk, 4)
    except Exception:
        return None


def is_adverse_slippage_too_high(signal, expected_price, execution_price, max_slippage):
    report = calculate_directional_slippage(
        signal=signal,
        expected_price=expected_price,
        execution_price=execution_price,
    )

    adverse = report.get("adverse")

    if adverse is None:
        return True, report

    return adverse > max_slippage, report


def is_favorable_execution_drift_too_high(signal, expected_price, execution_price, max_favorable_drift):
    report = calculate_directional_slippage(
        signal=signal,
        expected_price=expected_price,
        execution_price=execution_price,
    )

    favorable = report.get("favorable")

    if favorable is None:
        return False, report

    return favorable > max_favorable_drift, report

def execute_trade(signal, trade_plan, symbol):
    execution_start_ts = perf_counter()
    _log_execution_timing(
        "execute_trade_start",
        execution_start_ts,
        symbol=symbol,
        signal=signal,
        setup_id=trade_plan.get("setup_id") if isinstance(trade_plan, dict) else None,
        strategy=trade_plan.get("strategy") if isinstance(trade_plan, dict) else None,
    )
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
    
    rollover_blocked, rollover_name = is_rollover_trading_blocked()

    if rollover_blocked:
        error_message = (
            f"⛔ Trade Blocked: Rollover Window\n"
            f"Symbol: {symbol}\n"
            f"Signal: {signal}\n"
            f"Strategy: {trade_plan.get('strategy', 'UNKNOWN')}\n"
            f"Window: {rollover_name}\n"
            f"Action: No trade executed"
        )
        print(error_message)
        logger.warning(f"[ROLLOVER BLOCK] {rollover_name}")
        send_telegram_message(error_message)
        return False

    request_price = get_current_request_price(symbol, signal)

    if request_price is None:
        error_message = f"❌ Order failed: no tick data for {symbol} | {mt5.last_error()}"
        print(error_message)
        send_telegram_message(error_message)
        return False

    expected_price = trade_plan["entry_price"]

    adverse_drift = calculate_adverse_drift(
        signal=signal,
        expected_price=expected_price,
        current_price=request_price,
    )

    if (
        ENABLE_PRICE_DRIFT_GUARD
        and adverse_drift is not None
        and adverse_drift > MAX_ENTRY_PRICE_DRIFT
    ):
        old_expected_price = expected_price

        if (
            ENABLE_MOMENTUM_CONTINUATION_ON_PRICE_DRIFT
            and adverse_drift <= MOMENTUM_CONTINUATION_MAX_DRIFT_PRICE
            and not (
                is_fvg_ce_mitigation_trade(trade_plan)
                and not FVG_CE_MITIGATION_ALLOW_MOMENTUM_DRIFT
            )
        ):
            adjusted_trade_plan = rebase_trade_plan_for_momentum(
                signal=signal,
                trade_plan=trade_plan,
                current_price=request_price,
            )

            rr = calculate_rr(
                signal=signal,
                entry=adjusted_trade_plan["entry_price"],
                sl=adjusted_trade_plan["stop_loss"],
                tp=adjusted_trade_plan["take_profit"],
            )

            if rr is None or rr < MOMENTUM_CONTINUATION_MIN_RR:
                error_message = (
                    f"🚫 Momentum Continuation Blocked\n"
                    f"Symbol: {symbol}\n"
                    f"Signal: {signal}\n"
                    f"Expected Entry: {old_expected_price}\n"
                    f"Current Price: {round(request_price, 2)}\n"
                    f"Drift: {round(adverse_drift, 2)}\n"
                    f"RR: {rr}\n"
                    f"Min RR: {MOMENTUM_CONTINUATION_MIN_RR}"
                )
                print(error_message)
                send_telegram_message(error_message)
                return False

            trade_plan = adjusted_trade_plan
            expected_price = trade_plan["entry_price"]

            send_telegram_message(
                f"⚡ Momentum Continuation Accepted\n"
                f"Symbol: {symbol}\n"
                f"Signal: {signal}\n"
                f"Old Entry: {old_expected_price}\n"
                f"New Entry: {round(request_price, 2)}\n"
                f"Drift: {round(adverse_drift, 2)}\n"
                f"New SL: {trade_plan['stop_loss']}\n"
                f"New TP: {trade_plan['take_profit']}\n"
                f"RR: {rr}"
            )

        else:
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

    pre_execution_slippage = abs(request_price - expected_price)
    
    skip_slippage_guard = bool(trade_plan.get("skip_slippage_guard"))

    if (
        not skip_slippage_guard
        and ENABLE_HIGH_SLIPPAGE_RETRACEMENT
        and pre_execution_slippage > MAX_SLIPPAGE
    ):
        adjusted_trade_plan = wait_for_high_slippage_retracement(
            signal=signal,
            trade_plan=trade_plan,
            symbol=symbol,
            current_price=request_price,
            slippage=pre_execution_slippage,
        )

        if adjusted_trade_plan is None:
            return False

        trade_plan = adjusted_trade_plan

        request_price = get_current_request_price(symbol, signal)

        if request_price is None:
            error_message = (
                f"❌ Order failed after retracement: no tick data for {symbol} | "
                f"{mt5.last_error()}"
            )
            print(error_message)
            send_telegram_message(error_message)
            return False

        expected_price = trade_plan["entry_price"]

    trade_plan = apply_breaker_block_extra_sl(signal, trade_plan)
    
    trade_plan = apply_wavetrend_strict_sl(
        signal=signal,
        trade_plan=trade_plan,
        entry_price=trade_plan["entry_price"],
    )
    
    symbol_info = mt5.symbol_info(symbol)

    if symbol_info is None or symbol_info.point <= 0:
        error_message = f"❌ Execution failed: invalid symbol info for {symbol}"
        print(error_message)
        send_telegram_message(error_message)
        return False
    
    deviation_points = max(1, int(round(MAX_SLIPPAGE / symbol_info.point)))

    base_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": trade_plan["lot"],
        "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": request_price,
        "sl": trade_plan["stop_loss"],
        "tp": trade_plan["take_profit"],
        "deviation": deviation_points,
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

        _log_execution_timing(
            "before_fresh_tick",
            execution_start_ts,
            symbol=symbol,
            signal=signal,
        )

        fresh_tick = mt5.symbol_info_tick(symbol)

        if fresh_tick is None:
            logger.error("[EXECUTION BLOCKED] No fresh tick before order_send")
            send_telegram_message(
                f"⛔ Trade Blocked\n"
                f"Symbol: {symbol}\n"
                f"Reason: No fresh tick before order_send"
            )
            return False
        
        expected_price = float(trade_plan["entry_price"])
        current_execution_price = fresh_tick.ask if signal == "BUY" else fresh_tick.bid

        _log_execution_timing(
            "fresh_tick_received",
            execution_start_ts,
            symbol=symbol,
            signal=signal,
            expected_price=expected_price,
            current_execution_price=round(current_execution_price, 2),
        )
        
        slippage_blocked, pre_send_slippage_report = is_adverse_slippage_too_high(
            signal=signal,
            expected_price=expected_price,
            execution_price=current_execution_price,
            max_slippage=MAX_SLIPPAGE,
        )

        pre_send_adverse_slippage = pre_send_slippage_report.get("adverse")
        pre_send_favorable_slippage = pre_send_slippage_report.get("favorable")
        pre_send_absolute_slippage = pre_send_slippage_report.get("absolute")
        pre_send_signed_slippage = pre_send_slippage_report.get("signed")

        if pre_send_adverse_slippage is None:
            pre_send_adverse_slippage = MAX_SLIPPAGE + 999.0
        if pre_send_favorable_slippage is None:
            pre_send_favorable_slippage = 0.0
        if pre_send_absolute_slippage is None:
            pre_send_absolute_slippage = 0.0

        execution_guard_rr = get_trade_plan_rr_for_execution_guard(trade_plan)

        if (
            ENABLE_LOW_RR_STRICT_ADVERSE_SLIPPAGE_GUARD
            and not skip_slippage_guard
            and execution_guard_rr is not None
            and execution_guard_rr <= LOW_RR_STRICT_SLIPPAGE_RR_THRESHOLD
            and pre_send_adverse_slippage is not None
            and pre_send_adverse_slippage > LOW_RR_MAX_ADVERSE_SLIPPAGE
        ):
            try:
                trade_plan["execution_block_reason"] = "LOW_RR_HIGH_ADVERSE_SLIPPAGE"
                trade_plan["execution_block_action"] = "WAIT_BETTER_ENTRY"
                trade_plan["execution_block_rr"] = round(execution_guard_rr, 4)
                trade_plan["execution_block_adverse_slippage"] = round(pre_send_adverse_slippage, 4)
                trade_plan["execution_block_max_allowed"] = LOW_RR_MAX_ADVERSE_SLIPPAGE
            except Exception:
                pass

            remember_blocked_setup(
                setup_id=trade_plan.get("setup_id"),
                symbol=symbol,
                strategy=trade_plan.get("strategy", "UNKNOWN"),
                signal=signal,
                reason="LOW_RR_HIGH_ADVERSE_SLIPPAGE",
                expected_price=expected_price,
                current_price=round(current_execution_price, 2),
                slippage=round(pre_send_adverse_slippage, 2),
                max_allowed=LOW_RR_MAX_ADVERSE_SLIPPAGE,
            )

            logger.warning(
                f"[EXECUTION BLOCKED] Low-RR adverse slippage too high | "
                f"strategy={trade_plan.get('strategy', 'UNKNOWN')} "
                f"signal={signal} rr={round(execution_guard_rr, 2)} "
                f"expected={expected_price} current={current_execution_price} "
                f"adverse={round(pre_send_adverse_slippage, 2)} "
                f"max_low_rr_adverse={LOW_RR_MAX_ADVERSE_SLIPPAGE}"
            )

            send_telegram_message(
                f"⛔ Trade Blocked: Low RR + Adverse Slippage\n"
                f"Symbol: {symbol}\n"
                f"Signal: {signal}\n"
                f"Strategy: {trade_plan.get('strategy', 'UNKNOWN')}\n"
                f"RR: {round(execution_guard_rr, 2)}\n"
                f"Low-RR Threshold: {LOW_RR_STRICT_SLIPPAGE_RR_THRESHOLD}\n"
                f"Expected: {expected_price}\n"
                f"Current: {round(current_execution_price, 2)}\n"
                f"Adverse Slippage: {round(pre_send_adverse_slippage, 2)}\n"
                f"Max Low-RR Adverse Allowed: {LOW_RR_MAX_ADVERSE_SLIPPAGE}\n"
                f"Action: No trade executed\n"
                f"Reason: low RR setup cannot tolerate this adverse execution price"
            )

            _log_execution_timing(
                "blocked_low_rr_high_adverse_slippage",
                execution_start_ts,
                symbol=symbol,
                signal=signal,
                rr=round(execution_guard_rr, 2),
                adverse=round(pre_send_adverse_slippage, 2),
            )

            return False
        
        if not skip_slippage_guard and slippage_blocked:
            remember_blocked_setup(
                setup_id=trade_plan.get("setup_id"),
                symbol=symbol,
                strategy=trade_plan.get("strategy", "UNKNOWN"),
                signal=signal,
                reason="HIGH_SLIPPAGE",
                expected_price=expected_price,
                current_price=round(current_execution_price, 2),
                slippage=round(pre_send_adverse_slippage, 2),
                max_allowed=MAX_SLIPPAGE,
            )            
            
            logger.warning(
                f"[EXECUTION BLOCKED] High adverse pre-send slippage | "
                f"strategy={trade_plan.get('strategy', 'UNKNOWN')} "
                f"signal={signal} expected={expected_price} "
                f"current={current_execution_price} "
                f"adverse={round(pre_send_adverse_slippage, 2)} "
                f"favorable={round(pre_send_favorable_slippage, 2)} "
                f"absolute={round(pre_send_absolute_slippage, 2)} "
                f"signed={pre_send_signed_slippage} "
                f"max={MAX_SLIPPAGE}"
            )
        
            send_telegram_message(
                f"⛔ Trade Blocked: High Adverse Slippage\n"
                f"Symbol: {symbol}\n"
                f"Signal: {signal}\n"
                f"Strategy: {trade_plan.get('strategy', 'UNKNOWN')}\n"
                f"Expected: {expected_price}\n"
                f"Current: {round(current_execution_price, 2)}\n"
                f"Adverse Slippage: {round(pre_send_adverse_slippage, 2)}\n"
                f"Favorable Slippage: {round(pre_send_favorable_slippage, 2)}\n"
                f"Absolute Movement: {round(pre_send_absolute_slippage, 2)}\n"
                f"Max Allowed Adverse: {MAX_SLIPPAGE}\n"
                f"Action: No trade executed\n"
                f"Action: This setup ID will not be executed again during memory window"
            )
        
            return False

        if (
            ENABLE_EXECUTION_FAVORABLE_DRIFT_GUARD
            and pre_send_favorable_slippage is not None
            and pre_send_favorable_slippage > MAX_FAVORABLE_EXECUTION_DRIFT
        ):
            remember_blocked_setup(
                setup_id=trade_plan.get("setup_id"),
                symbol=symbol,
                strategy=trade_plan.get("strategy", "UNKNOWN"),
                signal=signal,
                reason="SETUP_STALE_FAVORABLE_DRIFT",
                expected_price=expected_price,
                current_price=round(current_execution_price, 2),
                slippage=round(pre_send_favorable_slippage, 2),
                max_allowed=MAX_FAVORABLE_EXECUTION_DRIFT,
            )

            logger.warning(
                f"[EXECUTION BLOCKED] Favorable drift too large / setup stale | "
                f"strategy={trade_plan.get('strategy', 'UNKNOWN')} "
                f"signal={signal} expected={expected_price} "
                f"current={current_execution_price} "
                f"favorable={round(pre_send_favorable_slippage, 2)} "
                f"adverse={round(pre_send_adverse_slippage, 2)} "
                f"absolute={round(pre_send_absolute_slippage, 2)} "
                f"max_favorable={MAX_FAVORABLE_EXECUTION_DRIFT}"
            )

            send_telegram_message(
                f"⛔ Trade Blocked: Favorable Drift / Setup Stale\n"
                f"Symbol: {symbol}\n"
                f"Signal: {signal}\n"
                f"Strategy: {trade_plan.get('strategy', 'UNKNOWN')}\n"
                f"Expected: {expected_price}\n"
                f"Current: {round(current_execution_price, 2)}\n"
                f"Favorable Drift: {round(pre_send_favorable_slippage, 2)}\n"
                f"Adverse Slippage: {round(pre_send_adverse_slippage, 2)}\n"
                f"Absolute Movement: {round(pre_send_absolute_slippage, 2)}\n"
                f"Max Favorable Allowed: {MAX_FAVORABLE_EXECUTION_DRIFT}\n"
                f"Action: No trade executed\n"
                f"Reason: price moved too far before execution; setup may be stale/fake"
            )

            _log_execution_timing(
                "blocked_favorable_drift",
                execution_start_ts,
                symbol=symbol,
                signal=signal,
                favorable=round(pre_send_favorable_slippage, 2),
                adverse=round(pre_send_adverse_slippage, 2),
            )

            return False
        
        if skip_slippage_guard and slippage_blocked:
            logger.info(
                f"[EXECUTION] High adverse slippage guard bypassed | "
                f"strategy={trade_plan.get('strategy', 'UNKNOWN')} "
                f"signal={signal} expected={expected_price} "
                f"current={current_execution_price} "
                f"adverse={round(pre_send_adverse_slippage, 2)} "
                f"favorable={round(pre_send_favorable_slippage, 2)} "
                f"absolute={round(pre_send_absolute_slippage, 2)} "
                f"max={MAX_SLIPPAGE}"
            )
        
        request["price"] = current_execution_price

        effective_deviation_points = deviation_points
        effective_deviation_price = MAX_SLIPPAGE

        if (
            ENABLE_LOW_RR_STRICT_ADVERSE_SLIPPAGE_GUARD
            and execution_guard_rr is not None
            and execution_guard_rr <= LOW_RR_STRICT_SLIPPAGE_RR_THRESHOLD
        ):
            try:
                point_size = float(symbol_info.point or 0.01)
            except Exception:
                point_size = 0.01

            if point_size <= 0:
                point_size = 0.01

            remaining_adverse_budget = max(
                0.0,
                LOW_RR_MAX_ADVERSE_SLIPPAGE - float(pre_send_adverse_slippage or 0.0),
            )

            effective_deviation_price = min(MAX_SLIPPAGE, remaining_adverse_budget)
            effective_deviation_points = max(
                1,
                int(effective_deviation_price / point_size),
            )

            request["deviation"] = effective_deviation_points

            logger.info(
                f"[LOW RR DEVIATION] Adaptive deviation applied | "
                f"rr={round(execution_guard_rr, 2)} "
                f"pre_send_adverse={round(pre_send_adverse_slippage, 4)} "
                f"remaining_budget={round(remaining_adverse_budget, 4)} "
                f"deviation_points={effective_deviation_points} "
                f"deviation_price={round(effective_deviation_price, 4)}"
            )

        _log_execution_timing(
            "before_order_send",
            execution_start_ts,
            symbol=symbol,
            signal=signal,
            request_price=round(current_execution_price, 2),
            filling_mode=filling_mode,
            deviation_points=request.get("deviation"),
            max_deviation_price=round(effective_deviation_price, 4),
        )

        result = mt5.order_send(request)

        _log_execution_timing(
            "after_order_send",
            execution_start_ts,
            symbol=symbol,
            signal=signal,
            filling_mode=filling_mode,
            retcode=getattr(result, "retcode", None) if result is not None else None,
        )

        if result is None:
            last_error_message = (
                f"Order failed with filling={filling_mode}: {mt5.last_error()}"
            )
            continue

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            successful_filling_mode = filling_mode
            request_price = current_execution_price
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
    execution_slippage_report = calculate_directional_slippage(
        signal=signal,
        expected_price=expected_price,
        execution_price=executed_price,
    )

    slippage = execution_slippage_report.get("absolute")
    adverse_slippage = execution_slippage_report.get("adverse")
    favorable_slippage = execution_slippage_report.get("favorable")
    signed_slippage = execution_slippage_report.get("signed")

    print(f"[EXECUTION] Expected: {expected_price}")
    print(f"[EXECUTION] Request Price: {request_price}")
    print(f"[EXECUTION] Executed: {executed_price}")
    print(f"[EXECUTION] Absolute Movement: {slippage}")
    print(f"[EXECUTION] Adverse Slippage: {adverse_slippage}")
    print(f"[EXECUTION] Favorable Slippage: {favorable_slippage}")
    print(f"[EXECUTION] Signed Slippage: {signed_slippage}")
    print(f"[EXECUTION] Filling Mode: {successful_filling_mode}")
    print("Order result:", result)

    if adverse_slippage is not None and adverse_slippage > MAX_SLIPPAGE:
        print("[WARNING] High adverse slippage detected after execution!")
        send_telegram_message(
            f"⚠️ High Adverse Slippage Detected After Execution\n"
            f"Symbol: {symbol}\n"
            f"Signal: {signal}\n"
            f"Expected: {expected_price}\n"
            f"Executed: {executed_price}\n"
            f"Adverse Slippage: {round(adverse_slippage or 0.0, 2)}\n"
            f"Favorable Slippage: {round(favorable_slippage or 0.0, 2)}\n"
            f"Absolute Movement: {round(slippage or 0.0, 2)}"
        )

    _log_execution_timing(
        "execution_success_before_register_trade",
        execution_start_ts,
        symbol=symbol,
        signal=signal,
        executed_price=executed_price,
        adverse_slippage=adverse_slippage,
        favorable_slippage=favorable_slippage,
    )

    register_executed_trade(symbol, signal, trade_plan, result)

    _log_execution_timing(
        "execution_success_after_register_trade",
        execution_start_ts,
        symbol=symbol,
        signal=signal,
        executed_price=executed_price,
    )

    send_telegram_message(
        f"✅ Trade Executed\n"
        f"Symbol: {symbol}\n"
        f"Signal: {signal}\n"
        f"Expected: {expected_price}\n"
        f"Executed: {executed_price}\n"
        f"SL: {trade_plan['stop_loss']}\n"
        f"TP: {trade_plan['take_profit']}\n"
        f"Lot: {trade_plan['lot']}\n"
        f"Adverse Slippage: {round(adverse_slippage or 0.0, 2)}\n"
        f"Favorable Slippage: {round(favorable_slippage or 0.0, 2)}\n"
        f"Absolute Movement: {round(slippage or 0.0, 2)}\n"
        f"Filling Mode: {successful_filling_mode}"
    )

    return True