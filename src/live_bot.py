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
from src.htf_filter import get_htf_context, htf_allows_signal
from src.liquidity_context import get_liquidity_context, liquidity_allows_signal
from src.news_filter import is_news_blackout_active
from src.reversal_checker import build_blocked_setup_reversal
from src.external_macro_confirmation import apply_external_macro_confirmation

from src.execution_engine import ExecutionEngine
execution_engine = ExecutionEngine()

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
    ENABLE_FCR_M1_FVG,
    ENABLE_WAVETREND_PIVOT_M5,
    ENABLE_STRUCTURE_LIQUIDITY,
    ENABLE_STRUCTURE_LIQUIDITY_CONFIRMATION,
    ENABLE_BLOCKED_SETUP_REVERSAL,
    BLOCKED_REVERSAL_MIN_SCORE,
    BLOCKED_REVERSAL_MIN_RR,
    ENABLE_LVN_FVG_RECLAIM,
    ENABLE_AMD_FVG,
    ENABLE_FVG_CE_MITIGATION,
    ENABLE_LIQUIDITY_POOL_OB,
)

from src.structure_liquidity_context import (
    analyze_structure_liquidity,
    apply_structure_liquidity_confirmation,
)

last_signal = None
reversal_count = 0

STRATEGY_SPECIFIC_CONFIRMED = {
    "HTF_TREND_PULLBACK",
    "SESSION_ORB_RETEST",
    "VWAP_RECLAIM",
    "BREAKER_BLOCK",
    "ORB",
    "FVG",
    "ORDER_BLOCK",
    "CRT_TBS",
    "LIQUIDITY_TRAP",
    "LIQUIDITY_SWEEP",
    "LIQUIDITY_CANDLE",
    "FRACTAL_SWEEP",
    "OB_FVG_COMBO",
    "RELIEF_RALLY",
    "HEAD_SHOULDERS",
    "TRIANGLE_PENNANT",
    "SMT",
    "SMT_PRO",
    "FLAG",
    "FLAG_REFINED",
    "SNIPER_V2",
    "STRICT",
    "FAST",
    "MTF_OB_ENTRY",
    "FCR_M1_FVG",
    "WAVETREND_PIVOT",
    "STRUCTURE_LIQUIDITY",
    "BLOCKED_SETUP_REVERSAL",
    "LVN_FVG_RECLAIM",
    "AMD_FVG",
    "FVG_CE_MITIGATION",
    "LIQUIDITY_POOL_OB",
}

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

def is_rr_valid(trade_plan, min_rr=1.2):
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


def get_min_rr(strategy_name):
    if strategy_name == "BLOCKED_SETUP_REVERSAL":
        return 1.3
    elif strategy_name == "ORB":
        return 1.5

    elif strategy_name in ["FVG", "ORDER_BLOCK", "OB_FVG_COMBO"]:
        return 1.4

    elif strategy_name in ["SMT", "SMT_PRO", "LIQUIDITY_TRAP", "CRT_TBS", "FRACTAL_SWEEP"]:
        return 1.25

    elif strategy_name in ["SNIPER_V2", "STRICT", "HEAD_SHOULDERS", "TRIANGLE_PENNANT"]:
        return 1.4

    elif strategy_name in ["FLAG", "FLAG_REFINED", "LIQUIDITY_SWEEP", "LIQUIDITY_CANDLE", "RELIEF_RALLY"]:
        return 1.25

    elif strategy_name == "WAVETREND_PIVOT":
        return 1.3

    else:
        return 1.2

def calculate_rr_value(trade_plan):
    if not trade_plan:
        return None

    entry = trade_plan.get("entry_price")
    sl = trade_plan.get("stop_loss")
    tp = trade_plan.get("take_profit")
    side = trade_plan.get("signal")

    try:
        if side == "BUY":
            return round((tp - entry) / (entry - sl), 2)

        if side == "SELL":
            return round((entry - tp) / (sl - entry), 2)

    except Exception:
        return None

    return None

def process_cycle(last_processed_candle_time):
    global last_signal, reversal_count

    df = fetch_market_data()
    if df is None:
        return last_processed_candle_time

    current = df.iloc[-1]          # currently forming candle, used only for new-candle detection
    signal_candle = df.iloc[-2]    # last closed candle, used for strategy context

    current_candle_time = current["time"]
    close_price = signal_candle["close"]
    atr = signal_candle["atr_14"]

    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        logger.error(f"Failed to fetch current tick: {mt5.last_error()}")
        return last_processed_candle_time

    logger.info(f"MT5 time: {tick.time}")

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

    from src.strategy_performance import rebuild_strategy_performance
    rebuild_strategy_performance()

    logger.info(f"New candle detected: {current_candle_time}")
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
    from src.strategies.strategy_fractal_sweep import generate_signal as fractal_sweep_signal
    from src.strategy_performance import get_disabled_strategies
    from src.strategies.strategy_htf_trend_pullback import generate_signal as htf_trend_pullback_signal
    from src.strategies.strategy_session_orb_retest import generate_signal as session_orb_retest_signal
    from src.strategies.strategy_vwap_reclaim import generate_signal as vwap_reclaim_signal
    from src.strategies.strategy_breaker_block import generate_signal as breaker_block_signal
    from src.strategies.strategy_mtf_order_block_entry import generate_signal as mtf_ob_entry_signal
    from src.strategies.strategy_fcr_m1_fvg import generate_signal as fcr_m1_fvg_signal
    from src.strategies.strategy_wavetrend_pivot import generate_signal as wavetrend_pivot_signal
    from src.strategies.strategy_structure_liquidity import generate_signal as structure_liquidity_signal
    from src.strategies.strategy_lvn_fvg_reclaim import generate_signal as lvn_fvg_reclaim_signal
    from src.strategies.strategy_amd_fvg import generate_signal as amd_fvg_signal
    from src.strategies.strategy_fvg_ce_mitigation import generate_signal as fvg_ce_mitigation_signal
    from src.strategies.strategy_liquidity_pool_ob import generate_signal as liquidity_pool_ob_signal

    disabled_strategies = get_disabled_strategies()

    signals = []

    from src.market_condition import detect_market_condition

    market_condition = detect_market_condition(df)

    strategy_map = []

    structure_liquidity_context = None

    if ENABLE_STRUCTURE_LIQUIDITY_CONFIRMATION:
        structure_liquidity_context = analyze_structure_liquidity(df)

        if structure_liquidity_context:
            logger.info(
                f"[STRUCTURE LIQUIDITY CONTEXT] "
                f"bias={structure_liquidity_context.get('bias')} "
                f"score={structure_liquidity_context.get('score')} "
                f"reasons={structure_liquidity_context.get('reasons')}"
            )


    from src.mtf_confirmation import get_mtf_bias

    # =========================
    # AI STRATEGY SELECTION
    # =========================
    if market_condition == "TRENDING":
        strategy_map = [
            ("HTF_TREND_PULLBACK", htf_trend_pullback_signal),
            ("OB_FVG_COMBO", ob_fvg_combo_signal),
            ("RELIEF_RALLY", relief_rally_signal),
            ("SESSION_ORB_RETEST", session_orb_retest_signal),
            ("LVN_FVG_RECLAIM", lvn_fvg_reclaim_signal),
            ("FVG_CE_MITIGATION", fvg_ce_mitigation_signal),
            ("ORB", orb_signal),
            ("FCR_M1_FVG", fcr_m1_fvg_signal),
            ("BREAKER_BLOCK", breaker_block_signal),
            ("MTF_OB_ENTRY", mtf_ob_entry_signal),
            ("ORDER_BLOCK", order_block_signal),
            ("FVG", fvg_signal),
            ("TRIANGLE_PENNANT", triangle_pennant_signal),
            ("FLAG_REFINED", flag_refined_signal),
            ("FLAG", flag_signal),
            ("LIQUIDITY_CANDLE", liquidity_candle_signal),
            ("SMT_PRO", smt_pro_signal),
            ("SMT", smt_signal),
            ("SNIPER_V2", sniper_signal),
            ("STRICT", strict_signal),
            ("HEAD_SHOULDERS", head_shoulders_signal),
        ]

    elif market_condition == "RANGING":
        strategy_map = [
            ("VWAP_RECLAIM", vwap_reclaim_signal),
            ("WAVETREND_PIVOT", wavetrend_pivot_signal),
            ("FRACTAL_SWEEP", fractal_sweep_signal),
            ("LIQUIDITY_TRAP", liquidity_trap_signal),
            ("STRUCTURE_LIQUIDITY", structure_liquidity_signal),
            ("CRT_TBS", crt_tbs_signal),
            ("LIQUIDITY_POOL_OB", liquidity_pool_ob_signal),
            ("AMD_FVG", amd_fvg_signal),
            ("SMT_PRO", smt_pro_signal),
            ("SMT", smt_signal),
            ("LIQUIDITY_SWEEP", liquidity_sweep_signal),
            ("LIQUIDITY_CANDLE", liquidity_candle_signal),
            ("BREAKER_BLOCK", breaker_block_signal),
            ("ORDER_BLOCK", order_block_signal),
            ("HEAD_SHOULDERS", head_shoulders_signal),
            ("FAST", fast_signal),
            ("SNIPER_V2", sniper_signal),
        ]

    elif market_condition == "VOLATILE":
        strategy_map = [
            ("VWAP_RECLAIM", vwap_reclaim_signal),
            ("WAVETREND_PIVOT", wavetrend_pivot_signal),
            ("LIQUIDITY_TRAP", liquidity_trap_signal),
            ("FRACTAL_SWEEP", fractal_sweep_signal),
            ("STRUCTURE_LIQUIDITY", structure_liquidity_signal),
            ("CRT_TBS", crt_tbs_signal),
            ("SMT_PRO", smt_pro_signal),
            ("SMT", smt_signal),
            ("LIQUIDITY_POOL_OB", liquidity_pool_ob_signal),
            ("SESSION_ORB_RETEST", session_orb_retest_signal),
            ("LVN_FVG_RECLAIM", lvn_fvg_reclaim_signal),
            ("AMD_FVG", amd_fvg_signal),
            ("FVG_CE_MITIGATION", fvg_ce_mitigation_signal),
            ("ORB", orb_signal),
            ("FCR_M1_FVG", fcr_m1_fvg_signal),
            ("LIQUIDITY_SWEEP", liquidity_sweep_signal),
            ("LIQUIDITY_CANDLE", liquidity_candle_signal),
            ("ORDER_BLOCK", order_block_signal),
            ("STRICT", strict_signal),
            ("FVG", fvg_signal),
        ]

    # =========================
    # STRATEGY TOGGLES
    # =========================

    if not ENABLE_LIQUIDITY_POOL_OB:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "LIQUIDITY_POOL_OB"
        ]
        logger.info("[STRATEGY TOGGLE] LIQUIDITY_POOL_OB disabled")

    if not ENABLE_FVG_CE_MITIGATION:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "FVG_CE_MITIGATION"
        ]
        logger.info("[STRATEGY TOGGLE] FVG_CE_MITIGATION disabled")

    if not ENABLE_AMD_FVG:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "AMD_FVG"
        ]
        logger.info("[STRATEGY TOGGLE] AMD_FVG disabled")

    if not ENABLE_LVN_FVG_RECLAIM:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "LVN_FVG_RECLAIM"
        ]
        logger.info("[STRATEGY TOGGLE] LVN_FVG_RECLAIM disabled")

    if not ENABLE_STRUCTURE_LIQUIDITY:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "STRUCTURE_LIQUIDITY"
        ]
        logger.info("[STRATEGY TOGGLE] STRUCTURE_LIQUIDITY disabled")

    if not ENABLE_WAVETREND_PIVOT_M5:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "WAVETREND_PIVOT"
        ]
        logger.info("[STRATEGY TOGGLE] WAVETREND_PIVOT disabled")

    if not ENABLE_FCR_M1_FVG:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "FCR_M1_FVG"
        ]
        logger.info("[STRATEGY TOGGLE] FCR_M1_FVG disabled")

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

                macro_boost, macro_reasons = apply_external_macro_confirmation(result)

                result["score"] += macro_boost

                if macro_reasons:
                    result.setdefault("macro_reasons", [])
                    result["macro_reasons"].extend(macro_reasons)

                    logger.info(
                        f"[MACRO CONFIRMATION] "
                        f"strategy={name} signal={result.get('signal')} "
                        f"boost={macro_boost} reasons={macro_reasons}"
                    )

                if ENABLE_STRUCTURE_LIQUIDITY_CONFIRMATION:
                    sl_boost, sl_reasons = apply_structure_liquidity_confirmation(
                        result,
                        structure_liquidity_context,
                    )

                    result["score"] += sl_boost

                    if sl_reasons:
                        result.setdefault("structure_liquidity_reasons", [])
                        result["structure_liquidity_reasons"].extend(sl_reasons)

                        logger.info(
                            f"[STRUCTURE LIQUIDITY CONFIRMATION] "
                            f"strategy={name} signal={result.get('signal')} "
                            f"boost={sl_boost} reasons={sl_reasons}"
                        )

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
        # 📡 DETECTED SIGNAL (RAW)
        # =========================
        if signal in ["BUY", "SELL"]:
            from src.notifier import build_trade_message

            detected_data = {
                "stage": "SETUP DETECTED",
                "signal": signal,
                "strategy": strategy_name,
                "entry_model": selected_signal_data.get("entry_model", "RAW"),
                "entry": close_price,
                "sl": selected_signal_data.get("sl_reference") or "N/A",
                "tp": (
                    selected_signal_data.get("tp_reference")
                    or selected_signal_data.get("pivot_target_level")
                    or "N/A"
                ),
                "score": score,
                "session": session_name,
                "reason": f"[DETECTED] {reason}",
            }

            send_telegram_message(build_trade_message(detected_data))

        # =========================
        # ORB ANTI-CHASE FIX
        # =========================
        if strategy_name == "ORB" and signal in ["BUY", "SELL"]:
            orb_low = selected_signal_data.get("orb_low")
            orb_high = selected_signal_data.get("orb_high")

            current_price = tick.ask if signal == "BUY" else tick.bid

            if signal == "SELL" and orb_low is not None:
                if abs(current_price - orb_low) > atr * 0.6:
                    logger.info("❌ ORB skipped (too extended below breakout)")
                    signal = "NO_TRADE"

            elif signal == "BUY" and orb_high is not None:
                if abs(current_price - orb_high) > atr * 0.6:
                    logger.info("❌ ORB skipped (too extended above breakout)")
                    signal = "NO_TRADE"

        if selected_signal_data.get("smc"):
            reason += f" | SMC: {','.join(selected_signal_data['smc'])}"

        if selected_signal_data.get("session_reasons"):
            reason += f" | SESSION: {','.join(selected_signal_data['session_reasons'])}"

        if selected_signal_data.get("structure_liquidity_reasons"):
            reason += (
                f" | STRUCTURE/LIQUIDITY: "
                f"{','.join(selected_signal_data['structure_liquidity_reasons'])}"
            )

        if selected_signal_data.get("macro_reasons"):
            reason += (
                f" | MACRO: "
                f"{','.join(selected_signal_data['macro_reasons'])}"
            )

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

            send_telegram_message(
                f"🚫 Signal Rejected by Score\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n"
                f"Score: {score}\n"
                f"Required: {min_required_score}"
            )

            signal = "NO_TRADE"

    # =========================
    # MTF CONFIRMATION
    # =========================
    from config.settings import ENABLE_MTF_CONFIRMATION

    if ENABLE_MTF_CONFIRMATION and signal in ["BUY", "SELL"]:
        mtf_bias = get_mtf_bias()
        logger.info(f"[MTF] bias={mtf_bias} signal={signal}")

        mtf_conflict = mtf_bias is not None and mtf_bias != signal

        mtf_override_strategies = [
            "CRT_TBS",
            "LIQUIDITY_TRAP",
            "FRACTAL_SWEEP",
        ]

        allow_mtf_override = (
            strategy_name in mtf_override_strategies
            and score >= 98
        )

        if mtf_conflict and not allow_mtf_override:
            logger.info(
                f"[MTF] Signal rejected by higher timeframe | "
                f"strategy={strategy_name} signal={signal} mtf_bias={mtf_bias}"
            )

            send_telegram_message(
                f"🚫 Signal Rejected by MTF\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n"
                f"Score: {score}\n"
                f"MTF Bias: {mtf_bias}"
            )

            signal = "NO_TRADE"
            reason = f"Rejected by MTF confirmation -> higher timeframe bias is {mtf_bias}"

        elif mtf_conflict and allow_mtf_override:
            logger.info(
                f"[MTF OVERRIDE] Allowed counter-bias setup | "
                f"strategy={strategy_name} score={score} "
                f"signal={signal} mtf_bias={mtf_bias}"
            )

            send_telegram_message(
                f"⚠️ MTF Override Allowed\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n"
                f"Score: {score}\n"
                f"MTF Bias: {mtf_bias}\n\n"
                f"Reason: High-score trap/reversal setup allowed against MTF."
            )

            reason += f" | MTF override: counter-bias {mtf_bias}"

    # =========================
    # HTF FILTER
    # =========================
    if signal in ["BUY", "SELL"]:
        htf_context = get_htf_context()

        if not htf_allows_signal(signal, htf_context, allow_neutral=True):
            logger.info(
                f"[HTF] Signal rejected | signal={signal} "
                f"htf_bias={htf_context.get('bias')} "
                f"price={htf_context.get('price')} "
                f"ema={htf_context.get('ema')}"
            )
            send_telegram_message(
                f"🚫 Signal Rejected by HTF\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n"
                f"HTF Bias: {htf_context.get('bias')}\n"
                f"HTF Price: {htf_context.get('price')}\n"
                f"HTF EMA: {htf_context.get('ema')}"
            )
            signal = "NO_TRADE"
            reason = (
                f"Rejected by HTF filter -> "
                f"HTF bias={htf_context.get('bias')}, "
                f"HTF price={htf_context.get('price')}, "
                f"HTF EMA={htf_context.get('ema')}"
            )

    # =========================
    # HTF LIQUIDITY CONTEXT FILTER
    # =========================
    if signal in ["BUY", "SELL"]:
        liquidity_context = get_liquidity_context()

        if not liquidity_allows_signal(signal, liquidity_context, allow_neutral=True):
            logger.info(
                f"[HTF LIQUIDITY] Rejected | signal={signal} "
                f"bias={liquidity_context.get('bias')} "
                f"reason={liquidity_context.get('reason')}"
            )
            send_telegram_message(
                f"🚫 Signal Rejected by HTF Liquidity\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n"
                f"Bias: {liquidity_context.get('bias')}\n"
                f"Reason: {liquidity_context.get('reason')}"
            )
            signal = "NO_TRADE"
            reason = (
                f"Rejected by HTF liquidity context -> "
                f"{liquidity_context.get('reason')}"
            )

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
    # NEWS VOLATILITY FILTER
    # =========================
    if signal in ["BUY", "SELL"]:
        news_blocked, news_reason = is_news_blackout_active()

        if news_blocked:
            logger.info(
                f"[NEWS FILTER] Signal blocked | "
                f"strategy={strategy_name} signal={signal} reason={news_reason}"
            )

            send_telegram_message(
                f"🚫 Signal Blocked by News Filter\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n\n"
                f"Reason: {news_reason}"
            )

            signal = "NO_TRADE"
            reason = news_reason

    # =========================
    # FINAL SIGNAL LOG
    # =========================
    if signal in ["BUY", "SELL"]:
        logger.info(
            f"[FILTERED SIGNAL] "
            f"strategy={strategy_name} "
            f"signal={signal} "
            f"score={score} "
            f"reason={reason}"
        )

    # =========================
    # CONTEXT LOG
    # =========================
    recent_data = df.iloc[-(BREAKOUT_LOOKBACK + 1):-1]
    recent_resistance = recent_data["high"].max()
    recent_support = recent_data["low"].min()

    logger.info("Signal context:")
    logger.info(f"Close: {signal_candle['close']}")
    logger.info(f"EMA: {signal_candle['ema_20']}")
    logger.info(f"ATR: {signal_candle['atr_14']}")
    logger.info(f"Resistance: {recent_resistance}")
    logger.info(f"Support: {recent_support}")
    logger.info(f"Signal: {signal}")
    logger.info(f"Score: {score}")



    # =========================
    # REGISTER SETUP AFTER FINAL FILTERS
    # =========================
    if (
        signal in ["BUY", "SELL"]
        and selected_signal_data.get("signal") in ["BUY", "SELL"]
        and selected_signal_data.get("strategy")
    ):
        execution_engine.register_setup(
            selected_signal_data,
            close_price,
            atr
        )

    # =========================
    # EXECUTION ENGINE (NEW)
    # =========================

    ready_setups = execution_engine.process_setups(df, close_price, atr)

    if not ready_setups:
        waiting_reasons = [
            setup.get("wait_reason")
            for setup in execution_engine.active_setups
            if setup.get("state") == "WAITING"
            and setup.get("strategy") == strategy_name
            and setup.get("signal") == signal
            and setup.get("entry_model") == selected_signal_data.get("entry_model", "MARKET")
        ]

        waiting_reason = next((reason for reason in waiting_reasons if reason), None)

        if signal in ["BUY", "SELL"]:
            logger.info(
                f"[EXECUTION WAITING] "
                f"strategy={strategy_name} "
                f"signal={signal} "
                f"entry_model={selected_signal_data.get('entry_model', 'N/A')}"
            )

            send_telegram_message(
                f"⏳ Setup Waiting for Execution\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n"
                f"Type: {selected_signal_data.get('entry_model', 'N/A')}\n\n"
                f"Reason: {waiting_reason or 'Execution engine did not confirm entry yet.'}"
            )

        return current_candle_time

    else:
        current_ready_setups = []

        if selected_signal_data.get("signal") in ["BUY", "SELL"]:
            current_ready_setups = [
                setup for setup in ready_setups
                if setup["data"].get("strategy") == selected_signal_data.get("strategy")
                and setup["data"].get("signal") == selected_signal_data.get("signal")
                and setup["data"].get("entry_model", "MARKET")
                == selected_signal_data.get("entry_model", "MARKET")
            ]

        if current_ready_setups:
            best_setup = current_ready_setups[0]
            logger.info(
                f"[EXECUTION] Using current filtered setup | "
                f"strategy={best_setup['data'].get('strategy')} "
                f"signal={best_setup['data'].get('signal')}"
            )
        else:
            best_setup = ready_setups[0]
            logger.info(
                f"[EXECUTION] Using previously registered ready setup | "
                f"strategy={best_setup['data'].get('strategy')} "
                f"signal={best_setup['data'].get('signal')}"
            )

        setup_data = best_setup["data"]
        setup_strategy = setup_data.get("strategy")
        setup_signal = setup_data.get("signal")
        setup_score = setup_data.get("score", score)

        # =========================
        # FINAL CONTEXT REVALIDATION
        # =========================
        final_mtf_bias = get_mtf_bias()
        final_mtf_conflict = final_mtf_bias is not None and final_mtf_bias != setup_signal

        final_mtf_override_strategies = [
            "CRT_TBS",
            "LIQUIDITY_TRAP",
            "FRACTAL_SWEEP",
        ]

        final_allow_mtf_override = (
            setup_strategy in final_mtf_override_strategies
            and setup_score >= 98
        )

        if final_mtf_conflict and not final_allow_mtf_override:
            logger.info(
                f"[FINAL MTF] Ready setup rejected | "
                f"strategy={setup_strategy} signal={setup_signal} mtf_bias={final_mtf_bias}"
            )

            send_telegram_message(
                f"🚫 Ready Setup Rejected by Final MTF\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {setup_strategy}\n"
                f"Signal: {setup_signal}\n"
                f"Score: {setup_score}\n"
                f"MTF Bias: {final_mtf_bias}"
            )

            return current_candle_time

        final_htf_context = get_htf_context()

        if not htf_allows_signal(setup_signal, final_htf_context, allow_neutral=True):
            logger.info(
                f"[FINAL HTF] Ready setup rejected | "
                f"strategy={setup_strategy} signal={setup_signal} "
                f"htf_bias={final_htf_context.get('bias') if final_htf_context else None}"
            )

            send_telegram_message(
                f"🚫 Ready Setup Rejected by Final HTF\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {setup_strategy}\n"
                f"Signal: {setup_signal}\n"
                f"HTF Bias: {final_htf_context.get('bias') if final_htf_context else None}"
            )

            return current_candle_time

        # =========================
        # 🔥 FINAL CONFIRMATION FILTER
        # =========================
        from src.confirmation_engine import confirm_entry
        from src.smart_money_layer import smart_money_confirm

        strategy_specific_confirmed = setup_strategy in STRATEGY_SPECIFIC_CONFIRMED

        if strategy_specific_confirmed:
            confirmed = True
            logger.info(
                f"[CONFIRMATION] Generic confirmation skipped | "
                f"strategy={setup_strategy} already confirmed by execution engine"
            )
        else:
            try:
                confirmed = confirm_entry(df, setup_data["signal"])
            except Exception as e:
                logger.error(f"[CONFIRMATION ERROR] {e}")
                confirmed = False

        if not confirmed:
            logger.info(
                f"❌ Confirmation failed → waiting better candle | "
                f"strategy={strategy_name} "
                f"signal={setup_data.get('signal')} "
                f"entry_model={setup_data.get('entry_model')}"
            )
            return current_candle_time

        smc_check = smart_money_confirm(df, setup_data["signal"])

        if not smc_check["confirmed"]:
            logger.info(
                f"❌ Smart money confirmation failed → reasons={smc_check['reasons']}"
            )

            smc_reasons = smc_check.get("reasons", [])
            smc_reason_text = ", ".join(smc_reasons) if smc_reasons else "No sweep, displacement, or inducement break detected"

            send_telegram_message(
                f"🚫 Smart Money Confirmation Failed\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {setup_strategy}\n"
                f"Signal: {setup_signal}\n\n"
                f"Reason: {smc_reason_text}"
            )

            return current_candle_time

        # =========================
        # ✅ CONFIRMED TRADE
        # =========================
        if not best_setup.get("notified"):
            send_telegram_message(
            f"""✅ Setup Confirmed
            Symbol: {SYMBOL}
            Signal: {setup_data['signal']}
            Strategy: {setup_data['strategy']}

            Confirmation candle detected
            Smart Money: {", ".join(smc_check['reasons'])}
            Waiting for risk approval 🚦
            """
            )
            best_setup["notified"] = True

        selected_signal_data = setup_data
        signal = setup_signal
        strategy_name = setup_strategy
        reason = setup_data.get("reason", reason)
        score = setup_score

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

    if signal in ["BUY", "SELL"] and trade_plan is None:
        logger.info(
            f"[TRADE PLAN FAILED] "
            f"strategy={strategy_name} "
            f"signal={signal} "
            f"data_keys={list(selected_signal_data.keys())}"
        )

        send_telegram_message(
            f"🚫 Trade Plan Failed\n"
            f"Symbol: {SYMBOL}\n"
            f"Signal: {signal}\n"
            f"Strategy: {strategy_name}\n\n"
            f"Reason: Could not calculate SL/TP from signal data.\n"
            f"Available data keys: {', '.join(selected_signal_data.keys())}"
        )

        return current_candle_time

    if signal in ["BUY", "SELL"] and trade_plan is not None:
        try:
            if signal == "BUY":
                rr_value = round(
                    (trade_plan["take_profit"] - trade_plan["entry_price"])
                    / (trade_plan["entry_price"] - trade_plan["stop_loss"]),
                    2,
                )
            else:
                rr_value = round(
                    (trade_plan["entry_price"] - trade_plan["take_profit"])
                    / (trade_plan["stop_loss"] - trade_plan["entry_price"]),
                    2,
                )
        except Exception:
            rr_value = "N/A"

        min_rr_required = get_min_rr(strategy_name)

        if not best_setup.get("trade_plan_notified"):
            send_telegram_message(
                f"📐 Trade Plan Ready\n"
                f"Symbol: {SYMBOL}\n"
                f"Signal: {signal}\n"
                f"Strategy: {strategy_name}\n\n"
                f"Entry: {trade_plan['entry_price']}\n"
                f"SL: {trade_plan['stop_loss']}\n"
                f"TP: {trade_plan['take_profit']}\n"
                f"RR: {rr_value}\n"
                f"Required RR: {min_rr_required}\n"
                f"Lot: {trade_plan['lot']}"
            )

            best_setup["trade_plan_notified"] = True

    trade_allowed, guard_reason = check_trade_guard(signal, tick)

    low_rr_blocked = False

    if signal in ["BUY", "SELL"] and trade_plan is not None and trade_allowed:
        if not is_rr_valid(trade_plan, min_rr=min_rr_required):
            trade_allowed = False
            low_rr_blocked = True
            guard_reason = f"Low RR — calculated {rr_value}, required {min_rr_required}"

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

            rr_value = None
            entry = trade_plan.get("entry_price")
            sl = trade_plan.get("stop_loss")
            tp = trade_plan.get("take_profit")

            try:
                if signal == "BUY":
                    rr_value = round((tp - entry) / (entry - sl), 2)
                else:
                    rr_value = round((entry - tp) / (sl - entry), 2)
            except Exception:
                pass

            send_telegram_message(
            f"""🚫 Trade Blocked
            Symbol: {SYMBOL}
            Signal: {signal}
            Strategy: {strategy_name}

            Entry: {entry}
            SL: {sl}
            TP: {tp}

            RR: {rr_value}
            Reason: {guard_reason}
            """
            )

        if (
            low_rr_blocked
            and ENABLE_BLOCKED_SETUP_REVERSAL
            and signal in ["BUY", "SELL"]
            and trade_plan is not None
        ):
            reversal_data = build_blocked_setup_reversal(
                df=df,
                blocked_signal=signal,
                blocked_strategy=strategy_name,
                blocked_trade_plan=trade_plan,
                blocked_signal_data=selected_signal_data,
            )

            if reversal_data is None:
                send_telegram_message(
                    f"🔎 Reversal Check\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Original Strategy: {strategy_name}\n"
                    f"Original Signal: {signal}\n\n"
                    f"Result: No valid reversal confirmation."
                )

            elif reversal_data.get("score", 0) < BLOCKED_REVERSAL_MIN_SCORE:
                send_telegram_message(
                    f"🚫 Reversal Rejected\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Original Strategy: {strategy_name}\n"
                    f"Original Signal: {signal}\n"
                    f"Reversal Signal: {reversal_data.get('signal')}\n"
                    f"Score: {reversal_data.get('score')}\n"
                    f"Required: {BLOCKED_REVERSAL_MIN_SCORE}"
                )

            else:
                reversal_signal = reversal_data["signal"]

                reversal_trade_plan = calculate_trade_plan(
                    df=df,
                    signal=reversal_signal,
                    tick=tick,
                    account_balance=account_info.balance,
                    signal_data=reversal_data,
                )

                if reversal_trade_plan is None:
                    send_telegram_message(
                        f"🚫 Reversal Trade Plan Failed\n"
                        f"Symbol: {SYMBOL}\n"
                        f"Original Strategy: {strategy_name}\n"
                        f"Reversal Signal: {reversal_signal}\n\n"
                        f"Reason: Could not calculate reversal SL/TP."
                    )

                else:
                    reversal_trade_plan["score"] = reversal_data.get("score", 0)
                    reversal_trade_plan["strategy"] = reversal_data.get("strategy")
                    reversal_trade_plan["market_condition"] = market_condition
                    reversal_trade_plan["reason"] = reversal_data.get("reason", "N/A")
                    reversal_trade_plan["session"] = selected_signal_data.get("session", session_name)

                    reversal_rr = calculate_rr_value(reversal_trade_plan)
                    reversal_allowed, reversal_guard_reason = check_trade_guard(reversal_signal, tick)

                    if not is_rr_valid(reversal_trade_plan, min_rr=BLOCKED_REVERSAL_MIN_RR):
                        reversal_allowed = False
                        reversal_guard_reason = (
                            f"Low reversal RR — calculated {reversal_rr}, "
                            f"required {BLOCKED_REVERSAL_MIN_RR}"
                        )

                    if is_cooldown_active():
                        reversal_allowed = False
                        reversal_guard_reason = "Cooldown after stop loss is active"

                    if not reversal_allowed:
                        send_telegram_message(
                            f"🚫 Reversal Trade Blocked\n"
                            f"Symbol: {SYMBOL}\n"
                            f"Original Strategy: {strategy_name}\n"
                            f"Reversal Signal: {reversal_signal}\n\n"
                            f"Entry: {reversal_trade_plan['entry_price']}\n"
                            f"SL: {reversal_trade_plan['stop_loss']}\n"
                            f"TP: {reversal_trade_plan['take_profit']}\n"
                            f"RR: {reversal_rr}\n\n"
                            f"Reason: {reversal_guard_reason}"
                        )

                    else:
                        from src.position_guard import has_same_direction_position

                        reversal_opposite = "SELL" if reversal_signal == "BUY" else "BUY"

                        if has_same_direction_position(SYMBOL, reversal_opposite):
                            send_telegram_message(
                                f"🚫 Reversal Execution Blocked\n"
                                f"Symbol: {SYMBOL}\n"
                                f"Reversal Signal: {reversal_signal}\n\n"
                                f"Reason: Opposite position already exists."
                            )
                            return current_candle_time

                        send_telegram_message(
                            f"🔁 Reversal Setup Confirmed\n"
                            f"Symbol: {SYMBOL}\n"
                            f"Original Strategy: {strategy_name}\n"
                            f"Original Signal: {signal}\n"
                            f"Reversal Signal: {reversal_signal}\n"
                            f"Reversal Strategy: {reversal_data.get('strategy')}\n\n"
                            f"Entry: {reversal_trade_plan['entry_price']}\n"
                            f"SL: {reversal_trade_plan['stop_loss']}\n"
                            f"TP: {reversal_trade_plan['take_profit']}\n"
                            f"RR: {reversal_rr}\n"
                            f"Reason: {reversal_data.get('reason')}"
                        )

                        execution_result = execute_trade(
                            reversal_signal,
                            reversal_trade_plan,
                            SYMBOL,
                        )

                        if not execution_result:
                            send_telegram_message(
                                f"❌ Reversal Execution Failed\n"
                                f"Symbol: {SYMBOL}\n"
                                f"Signal: {reversal_signal}\n"
                                f"Reason: execute_trade() returned False."
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

        send_telegram_message(
            f"🔥 Executing Trade\n"
            f"Symbol: {SYMBOL}\n"
            f"Signal: {signal}\n"
            f"Strategy: {strategy_name}\n\n"
            f"Entry: {trade_plan['entry_price']}\n"
            f"SL: {trade_plan['stop_loss']}\n"
            f"TP: {trade_plan['take_profit']}\n"
            f"Lot: {trade_plan['lot']}"
        )

        execution_result = execute_trade(signal, trade_plan, SYMBOL)

        if execution_result:
            execution_engine.mark_executed(best_setup)
        else:
            logger.error(
                f"[EXECUTION FAILED] "
                f"strategy={strategy_name} signal={signal} trade_plan={trade_plan}"
            )

            send_telegram_message(
                f"❌ Execution Failed\n"
                f"Symbol: {SYMBOL}\n"
                f"Signal: {signal}\n"
                f"Strategy: {strategy_name}\n\n"
                f"Reason: execute_trade() returned False. Check MT5/order_executor logs."
            )

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
                time.sleep(5)  # prevent CPU/log spam

            time.sleep(10)

    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped manually")

    finally:
        mt5.shutdown()
        logger.info("MT5 shutdown completed")


if __name__ == "__main__":
    main()