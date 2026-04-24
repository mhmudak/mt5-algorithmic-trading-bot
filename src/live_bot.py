import sys
import time
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd

from src.execution import check_trade_guard
from src.indicators import calculate_ema, calculate_atr
from src.logger import logger
from src.notifier import send_telegram_message
from src.order_executor import execute_trade
from src.position_manager import manage_positions
from src.risk import calculate_trade_plan
from src.trade_tracker import (
    update_trade_lifecycle,
    sync_open_positions,
    is_cooldown_active,
)
from src.health_monitor import send_heartbeat, send_critical_alert
from src.manual_trailing_manager import manage_manual_trailing_positions
from src.drawdown_guard import is_drawdown_exceeded
from src.emergency_close import close_all_positions
from src.dashboard import rebuild_dashboard
from src.mtf_confirmation import get_mtf_bias
from src.confirmation_engine import confirm_entry
from src.htf_filter import get_htf_context, htf_allows_signal
from src.sniper_entry import sniper_entry_allowed

from config.settings import (
    SYMBOL,
    TIMEFRAME,
    BARS_TO_FETCH,
    EMA_PERIOD,
    ATR_PERIOD,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
    FORCE_SIGNAL,
    ENABLE_MANUAL_TRAILING,
    MANUAL_TRAILING_START_PRICE,
    MANUAL_TRAILING_DISTANCE_PRICE,
    ENABLE_GLOBAL_DRAWDOWN_STOP,
    ENABLE_REVERSAL_MODE,
    REVERSAL_CONFIRMATION_CANDLES,
    ENABLE_REVERSAL_ALERTS,
    REVERSAL_MIN_SCORE,
    TRADING_MODE,
)

last_signal = None
reversal_count = 0


def fetch_market_data():
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, BARS_TO_FETCH)
    if rates is None:
        logger.error(f"Failed to fetch rates: {mt5.last_error()}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)
    return df

def is_rr_valid(trade_plan, min_rr=1.5):
    if not trade_plan:
        return False

    entry = trade_plan.get("entry_price")
    sl = trade_plan.get("stop_loss")
    tp = trade_plan.get("take_profit")
    side = trade_plan.get("signal")

    try:
        if side == "BUY":
            rr = (tp - entry) / (entry - sl)
        else:
            rr = (entry - tp) / (sl - entry)

        return rr >= min_rr
    except Exception:
        return False
    
def get_min_rr(strategy_name, entry_model=None):
    if strategy_name == "WAVETREND_PIVOT":
        if entry_model == "PIVOT_REJECTION_PRECISION":
            return 1.0
        if entry_model == "PIVOT_BREAKOUT_PRECISION":
            return 1.2
        return 1.3

    if strategy_name == "LIQUIDITY_TRAP":
        return 1.3

    return 1.5

def process_cycle(last_processed_candle_time):
    global last_signal, reversal_count
    

    df = fetch_market_data()
    if df is None:
        return last_processed_candle_time

    last = df.iloc[-1]
    current_candle_time = last["time"]

    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        logger.error(f"Failed to fetch current tick: {mt5.last_error()}")
        return last_processed_candle_time

    print("MT5 time:", tick.time)
    
    account_info = mt5.account_info()
    if account_info is None:
        logger.error(f"Failed to fetch account info: {mt5.last_error()}")
        return last_processed_candle_time

    # =========================
    # POSITION MANAGEMENT
    # =========================
    sync_open_positions(SYMBOL)

    if ENABLE_MANUAL_TRAILING:
        manage_manual_trailing_positions(
            symbol=SYMBOL,
            start_price=MANUAL_TRAILING_START_PRICE,
            trail_distance=MANUAL_TRAILING_DISTANCE_PRICE,
        )

    manage_positions(SYMBOL)
    update_trade_lifecycle(SYMBOL)
    rebuild_dashboard()

    # =========================
    # NEW CANDLE CHECK
    # =========================
    from src.session_engine import detect_session, session_score_adjustment
    from config.settings import ENABLE_SESSION_ENGINE
    
    if (
        last_processed_candle_time is not None
        and current_candle_time == last_processed_candle_time
    ):
        logger.info(f"No new candle yet. Current candle: {current_candle_time}")
        return last_processed_candle_time

    logger.info(f"New candle detected: {current_candle_time}")
    
    from src.strategy_performance import rebuild_strategy_performance
    rebuild_strategy_performance()
    
    session_name = detect_session(current_candle_time)
    logger.info(f"[SESSION] {session_name}")

    # =========================
    # SIGNAL GENERATION
    # =========================
    from src.strategies.strategy_fast import generate_signal as fast_signal
    from src.strategies.strategy_sniper_v2 import generate_signal as sniper_signal
    from src.strategies.strategy_strict import generate_signal as strict_signal
    from src.strategies.strategy_flag import generate_signal as flag_signal
    from src.strategies.strategy_flag_refined import generate_signal as flag_refined_signal
    from src.strategies.strategy_liquidity_sweep import generate_signal as liquidity_sweep_signal
    from src.strategies.strategy_head_shoulders import generate_signal as head_shoulders_signal
    from src.strategies.strategy_triangle_pennant import generate_signal as triangle_pennant_signal
    from src.strategies.strategy_fvg import generate_signal as fvg_signal
    from src.strategies.strategy_order_block import generate_signal as order_block_signal
    from src.strategies.strategy_liquidity_candle import generate_signal as liquidity_candle_signal
    from src.strategies.strategy_orb import generate_signal as orb_signal
    from src.strategies.strategy_smt import generate_signal as smt_signal
    from src.smc_engine import smc_validate
    from src.strategies.strategy_smt_pro import generate_signal as smt_pro_signal
    from src.strategies.strategy_crt_tbs import generate_signal as crt_tbs_signal
    from src.strategies.strategy_ob_fvg_combo import generate_signal as ob_fvg_combo_signal
    from src.strategies.strategy_liquidity_trap import generate_signal as liquidity_trap_signal
    from src.strategies.strategy_relief_rally import generate_signal as relief_rally_signal


    from src.strategy_performance import get_disabled_strategies

    disabled_strategies = get_disabled_strategies()

    signals = []

    from src.market_condition import detect_market_condition

    market_condition = detect_market_condition(df)

    strategy_map = []


    from src.mtf_confirmation import get_mtf_bias

    # =========================
    # AI STRATEGY SELECTION (M5 SCALPING MODE)
    # =========================
    from src.strategies.strategy_wavetrend_pivot import generate_signal as wavetrend_pivot_signal
    
    if market_condition == "TRENDING":
        strategy_map = [
            ("WAVETREND_PIVOT", wavetrend_pivot_signal),
            ("OB_FVG_COMBO", ob_fvg_combo_signal),
        ]
    
    elif market_condition == "RANGING":
        strategy_map = [
            ("WAVETREND_PIVOT", wavetrend_pivot_signal),
            ("LIQUIDITY_TRAP", liquidity_trap_signal),
        ]
    
    elif market_condition == "VOLATILE":
        strategy_map = [
            ("WAVETREND_PIVOT", wavetrend_pivot_signal),
            ("LIQUIDITY_TRAP", liquidity_trap_signal),
        ]

    for name, strat in strategy_map:

        # 🔒 AUTO-DISABLE
        if name in disabled_strategies:
            logger.info(f"[AUTO-DISABLE] Skipping {name} (low performance)")
            continue

        try:
            result = strat(df)
            logger.info(f"[STRATEGY RESULT] {name}: {result}")
        
            if not result:
                continue
            
            signal_value = result.get("signal")
        
            if signal_value in ["BUY", "SELL"]:
            
                # 🔥 enforce metadata
                result["strategy"] = name
                result.setdefault("score", 0)
                result.setdefault("reason", "N/A")
                result["session"] = session_name
        
                # =========================
                # 🔥 APPLY SMC ENGINE HERE
                # =========================
                from config.settings import ENABLE_SMC_ENGINE, SMC_MIN_FINAL_SCORE
                
                score_boost, smc_reasons = smc_validate(df, result)
        
                result["score"] += score_boost
                result["smc"] = smc_reasons
        
                if ENABLE_SMC_ENGINE and result["score"] < SMC_MIN_FINAL_SCORE:
                    logger.info(
                        f"[SMC FILTER] Rejected {name} "
                        f"(score={result['score']} required={SMC_MIN_FINAL_SCORE})"
                    )
                    continue
                
                if ENABLE_SESSION_ENGINE:
                    session_boost, session_reasons = session_score_adjustment(name, session_name)
                    result["score"] += session_boost
                    result.setdefault("session_reasons", [])
                    result["session_reasons"].extend(session_reasons)
                
                signals.append(result)
        
        except Exception as e:
            logger.error(f"[STRATEGY ERROR] {name}: {e}")

    # =========================
    # SIGNAL SELECTION (SMART)
    # =========================
    original_signal = "NO_TRADE"
    original_strategy_name = None
    original_reason = None
    original_score = 0
    selected_signal_data = {}
    
    if not signals:
        signal = "NO_TRADE"
        score = 0
        strategy_name = None
        reason = None
        selected_signal_data = {}
    else:
        best = max(signals, key=lambda x: x.get("score", 0))

        signal = best["signal"]
        score = best.get("score", 0)
        strategy_name = best.get("strategy", "UNKNOWN")
        reason = best.get("reason", "N/A")
        selected_signal_data = best.copy()

        # =========================
        # ANTI-CHASING FILTER (M5)
        # =========================
        if signal in ["BUY", "SELL"]:
            pivot_level = selected_signal_data.get("pivot_support_level") if signal == "BUY" else selected_signal_data.get("pivot_resistance_level")

            if pivot_level is not None:
                current_price = tick.ask if signal == "BUY" else tick.bid
                distance = abs(current_price - pivot_level)

                if distance > df.iloc[-1]["atr_14"] * 0.5:
                    logger.info("❌ Skipped: price too far from pivot (anti-chase)")
                    signal = "NO_TRADE"

        if selected_signal_data.get("smc"):
            reason += f" | SMC: {','.join(selected_signal_data['smc'])}"
            
        if selected_signal_data.get("session_reasons"):
            reason += f" | SESSION: {','.join(selected_signal_data['session_reasons'])}"

        original_signal = signal
        original_strategy_name = strategy_name
        original_reason = reason
        original_score = score

    # =========================
    # BASIC SCORE FILTER (ANTI-FAKE)
    # =========================
    # if signal in ["BUY", "SELL"] and score < REVERSAL_MIN_SCORE:
    #     logger.info("Signal rejected (low score filter)")
    #     signal = "NO_TRADE"


    from src.adaptive_thresholds import get_adaptive_min_score
    
    if signal in ["BUY", "SELL"]:
        min_required_score = get_adaptive_min_score(strategy_name, market_condition)
        
    
        if score < min_required_score:
            logger.info(
                f"Signal rejected (score too low) | "
                f"strategy={strategy_name} score={score} required={min_required_score}"
            )
            signal = "NO_TRADE"

    # =========================
    # MTF CONFIRMATION
    # =========================
    from config.settings import ENABLE_MTF_CONFIRMATION

    if ENABLE_MTF_CONFIRMATION and signal in ["BUY", "SELL"]:
        mtf_bias = get_mtf_bias()
        logger.info(f"[MTF] bias={mtf_bias} signal={signal}")

        if mtf_bias is not None and mtf_bias != signal:
            logger.info(
                f"[MTF] Signal rejected by higher timeframe | signal={signal} mtf_bias={mtf_bias}"
            )
            signal = "NO_TRADE"
            reason = f"Rejected by MTF confirmation -> higher timeframe bias is {mtf_bias}"

    # =========================
    # HTF FILTER (M15 bias filter)
    # =========================
    if signal in ["BUY", "SELL"]:
        htf_context = get_htf_context()

        if not htf_allows_signal(signal, htf_context, allow_neutral=True):
            logger.info(
                f"[HTF] Rejected | signal={signal} "
                f"htf_bias={htf_context.get('bias')}"
            )
            signal = "NO_TRADE"
            reason = f"Rejected by HTF filter → bias={htf_context.get('bias')}"

    # =========================
    # REVERSAL DETECTION (FIXED)
    # =========================
    if ENABLE_REVERSAL_MODE:
        if signal not in ["BUY", "SELL"]:
            reversal_count = 0
        else:
            if last_signal is None:
                last_signal = signal
                reversal_count = 0

            elif signal != last_signal:
                reversal_count += 1

                if reversal_count == 1 and ENABLE_REVERSAL_ALERTS:
                    send_telegram_message(
                        f"⚠️ Reversal candidate detected\n"
                        f"From: {last_signal} -> {signal}"
                    )

                if reversal_count >= REVERSAL_CONFIRMATION_CANDLES:
                    if score < REVERSAL_MIN_SCORE:
                        logger.info("Reversal rejected (low score)")
                        signal = "NO_TRADE"
                        reversal_count = 0
                    else:
                        if ENABLE_REVERSAL_ALERTS:
                            send_telegram_message(
                                f"🔥 Reversal confirmed\n"
                                f"From: {last_signal} -> {signal}\n"
                                f"Score: {score}"
                            )

                        last_signal = signal
                        reversal_count = 0

            else:
                reversal_count = 0
                last_signal = signal

    # =========================
    # MODE CONTROL
    # =========================
    if TRADING_MODE == "BUY_ONLY":
        if signal != "BUY":
            signal = "NO_TRADE"

    elif TRADING_MODE == "SELL_ONLY":
        if signal != "SELL":
            signal = "NO_TRADE"

    elif TRADING_MODE == "DUAL":
        pass

    # =========================
    # FORCE SIGNAL (SAFE MODE)
    # =========================
    if FORCE_SIGNAL in ["BUY", "SELL"]:
        logger.warning(f"⚠ FORCE SIGNAL REQUESTED: {FORCE_SIGNAL}")

        if original_signal in ["BUY", "SELL"]:
            if FORCE_SIGNAL == original_signal:
                signal = FORCE_SIGNAL
                strategy_name = original_strategy_name
                score = original_score
                reason = f"{original_reason} -> force confirmed same direction"
                logger.info(f"[SAFE FORCE] Confirmed strategy direction: {FORCE_SIGNAL}")
            else:
                logger.warning(
                    f"[SAFE FORCE] Blocked conflicting force | "
                    f"strategy={original_signal} forced={FORCE_SIGNAL}"
                )
                signal = "NO_TRADE"
                score = 0
                strategy_name = "FORCE_BLOCKED"
                reason = (
                    f"Force blocked -> strategy wanted {original_signal} via "
                    f"{original_strategy_name}, forced {FORCE_SIGNAL} rejected"
                )
                selected_signal_data = {}
        else:
            # no strategy signal exists
            signal = FORCE_SIGNAL
            score = 0
            strategy_name = "FORCED"
            reason = f"Manual forced direction override without strategy signal -> forced {FORCE_SIGNAL}"
            selected_signal_data = {}
            logger.info(f"[SAFE FORCE] No strategy signal, forced {FORCE_SIGNAL} allowed")
            
    # =========================
    # FINAL SIGNAL NOTIFICATION
    # =========================
    if signal in ["BUY", "SELL"]:
        from src.notifier import build_trade_message
    
        preview_data = {
            "signal": signal,
            "strategy": strategy_name,
            "entry_model": selected_signal_data.get("entry_model", "N/A"),
            "entry": tick.ask if signal == "BUY" else tick.bid,
            "sl": selected_signal_data.get("sl_reference") or "N/A",
            "tp": selected_signal_data.get("pivot_target_level") or "N/A",
            "score": score,
            "session": selected_signal_data.get("session", session_name),
            "pivot_support_level": selected_signal_data.get("pivot_support_level"),
            "pivot_resistance_level": selected_signal_data.get("pivot_resistance_level"),
            "pivot_target_level": selected_signal_data.get("pivot_target_level"),
            "reason": reason,
        }
    
        send_telegram_message(build_trade_message(preview_data))

    # =========================
    # CONTEXT LOG
    # =========================
    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 1):-1]
    recent_resistance = recent_data["high"].max()
    recent_support = recent_data["low"].min()

    logger.info("Signal context:")
    logger.info(f"Close: {last['close']}")
    logger.info(f"EMA: {last['ema_20']}")
    logger.info(f"ATR: {last['atr_14']}")
    logger.info(f"Resistance: {recent_resistance}")
    logger.info(f"Support: {recent_support}")
    logger.info(f"Signal: {signal}")
    logger.info(f"Score: {score}")


    # =========================
    # FAST CONFIRMATION (M5)
    # =========================
    if signal in ["BUY", "SELL"]:
        confirmed = confirm_entry(df, signal, mode="FAST")
    
        if not confirmed:
            logger.info("❌ FAST confirmation failed (M5 entry)")
            return current_candle_time
    
    # =========================
    # SNIPER ENTRY FILTER (M5)
    # =========================
    if signal in ["BUY", "SELL"] and strategy_name == "WAVETREND_PIVOT":
        sniper_ok, sniper_reason = sniper_entry_allowed(
            df=df,
            signal=signal,
            signal_data=selected_signal_data,
            atr=df.iloc[-1]["atr_14"],
        )
    
        if not sniper_ok:
            logger.info(f"❌ Sniper entry rejected: {sniper_reason}")
            return current_candle_time
    
        reason += f" | SNIPER: {sniper_reason}"


    # =========================
    # TRADE PLAN
    # =========================         
    trade_plan = calculate_trade_plan(
        df=df,
        signal=signal,
        tick=tick,
        account_balance=account_info.balance,
        signal_data=selected_signal_data,
    )

    if trade_plan is not None:
        trade_plan["score"] = score
        trade_plan["strategy"] = strategy_name
        trade_plan["market_condition"] = market_condition
        trade_plan["reason"] = reason
        trade_plan["session"] = selected_signal_data.get("session", session_name)

    trade_allowed, guard_reason = check_trade_guard(signal, tick)
    
    if signal in ["BUY", "SELL"] and trade_plan is not None:
        min_rr_required = get_min_rr(
            strategy_name,
            selected_signal_data.get("entry_model")
        )
        
        if not is_rr_valid(trade_plan, min_rr=min_rr_required):
            trade_allowed = False
            guard_reason = "Trade blocked - Due to the low risk-reward ratio RR"

    if is_cooldown_active() and signal in ["BUY", "SELL"]:
        trade_allowed = False
        guard_reason = "Cooldown after stop loss is active"

    # =========================
    # DEBUG
    # =========================
    spread = tick.ask - tick.bid
    logger.info(f"Spread: {spread}")

    if not trade_allowed:
        if signal in ["BUY", "SELL"] and trade_plan is not None:
            entry = trade_plan.get("entry_price")
            sl = trade_plan.get("stop_loss")
            tp = trade_plan.get("take_profit")
    
            rr_value = None
            try:
                if signal == "BUY":
                    rr_value = round((tp - entry) / (entry - sl), 2)
                else:
                    rr_value = round((entry - tp) / (sl - entry), 2)
            except Exception:
                pass
            
            send_telegram_message(
            f"""🚫 M5 Trade Blocked
            Symbol: {SYMBOL}
            Strategy: {strategy_name}
            Signal: {signal}
            Type: {selected_signal_data.get("entry_model")}
            
            Entry: {entry}
            SL: {sl}
            TP: {tp}
            RR: {rr_value}
            Required RR: {min_rr_required}
            
            Reason: {guard_reason}
            """
            )
    
        return current_candle_time

    # =========================
    # SAFE EXECUTION (ANTI-FLIP)
    # =========================
    from src.position_guard import has_same_direction_position

    if signal in ["BUY", "SELL"] and trade_plan is not None:
        opposite = "SELL" if signal == "BUY" else "BUY"

        if has_same_direction_position(SYMBOL, opposite):
            logger.info("Opposite position exists → skipping execution")
            return current_candle_time

        logger.info("🔥 Executing trade...")
        execute_trade(signal, trade_plan, SYMBOL)

    return current_candle_time


def main():
    logger.info("🚀 Starting live bot loop...")
    send_telegram_message(f"Live bot started on {SYMBOL}")

    if not mt5.initialize():
        logger.error(f"initialize() failed: {mt5.last_error()}")
        return

    last_processed_candle_time = None

    try:
        while True:
            if ENABLE_GLOBAL_DRAWDOWN_STOP:
                exceeded, pnl = is_drawdown_exceeded(SYMBOL)

                if exceeded:
                    logger.info(f"🚨 MAX DRAWDOWN HIT: {pnl} USD")
                    close_all_positions(SYMBOL)
                    mt5.shutdown()
                    sys.exit()

            try:
                last_processed_candle_time = process_cycle(last_processed_candle_time)
                send_heartbeat(SYMBOL)
            except Exception as e:
                logger.exception(f"Loop failed: {e}")
                send_critical_alert(str(e))

            time.sleep(10)

    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped manually")

    finally:
        mt5.shutdown()
        logger.info("MT5 shutdown completed")


if __name__ == "__main__":
    main()