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
from src.time_filter import is_trading_blackout_active
from src.reversal_checker import build_blocked_setup_reversal
from src.external_macro_confirmation import apply_external_macro_confirmation
from src.position_guard import count_same_direction_positions

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
    ENABLE_EXTRA_RR_DISCOUNT,
    EXTRA_RR_MULTIPLIER,
    MAX_CANDIDATES_PER_CANDLE,
    ENABLE_CANDIDATE_FALLBACK,
    ENABLE_SIGNAL_CONFLUENCE_GROUPING,
    CONFLUENCE_SCORE_BOOST_PER_STRATEGY,
    MAX_CONFLUENCE_SCORE_BOOST,
    TELEGRAM_VERBOSE_SIGNALS,
    ENABLE_FAILED_BREAKOUT_REVERSAL,
    ENABLE_WAIT_FOR_BETTER_ENTRY,
    BETTER_ENTRY_EXPIRY_MINUTES,
    BETTER_ENTRY_STRATEGIES,
    ENABLE_FAILED_FVG_REVERSAL,
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
    "FAILED_BREAKOUT_REVERSAL",
    "FAILED_FVG_REVERSAL",
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
    rr_150 = {
        "ORB",
    }

    rr_140 = {
        "FVG",
        "ORDER_BLOCK",
        "OB_FVG_COMBO",
        "SNIPER_V2",
        "STRICT",
        "HEAD_SHOULDERS",
        "TRIANGLE_PENNANT",
    }

    rr_130 = {
        "BLOCKED_SETUP_REVERSAL",
        "WAVETREND_PIVOT",
    }

    rr_125 = {
        "SMT",
        "SMT_PRO",
        "LIQUIDITY_TRAP",
        "CRT_TBS",
        "FRACTAL_SWEEP",
        "FLAG",
        "FLAG_REFINED",
        "LIQUIDITY_SWEEP",
        "LIQUIDITY_CANDLE",
        "RELIEF_RALLY",
    }

    rr_110 = {
        "FVG_CE_MITIGATION",
    }

    if strategy_name in rr_150:
        return 1.2

    if strategy_name in rr_140:
        return 1.1

    if strategy_name in rr_130:
        return 1.0

    if strategy_name in rr_125:
        return 0.95

    if strategy_name in rr_110:
        return 0.80

    return 0.90

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

def build_setup_id(strategy_name, signal, tick_time):
    prefix = (strategy_name or "UNK")[:3].upper()
    return f"{prefix}-{signal}-{int(tick_time)}"

def select_confirmed_ready_setup(ready_setups, df, selected_signal_data):
    from src.confirmation_engine import confirm_entry
    from src.smart_money_layer import smart_money_confirm

    current_ready = []
    other_ready = []

    for setup in ready_setups:
        setup_data = setup["data"]

        is_current = (
            setup_data.get("strategy") == selected_signal_data.get("strategy")
            and setup_data.get("signal") == selected_signal_data.get("signal")
            and setup_data.get("entry_model", "MARKET")
            == selected_signal_data.get("entry_model", "MARKET")
        )

        if is_current:
            current_ready.append(setup)
        else:
            other_ready.append(setup)

    other_ready = sorted(
        other_ready,
        key=lambda setup: setup["data"].get("score", 0),
        reverse=True,
    )

    ordered_setups = current_ready + other_ready
    rejected_reasons = []

    for setup in ordered_setups:
        setup_data = setup["data"]
        setup_strategy = setup_data.get("strategy")
        setup_signal = setup_data.get("signal")

        if setup_strategy in STRATEGY_SPECIFIC_CONFIRMED:
            confirmed = True
        else:
            try:
                confirmed = confirm_entry(df, setup_signal)
            except Exception as e:
                logger.error(f"[CONFIRMATION ERROR] {e}")
                confirmed = False

        if not confirmed:
            rejected_reasons.append(
                f"{setup_strategy}:{setup_signal}:confirmation_failed"
            )
            continue

        smc_check = smart_money_confirm(df, setup_signal)

        if not smc_check["confirmed"]:
            rejected_reasons.append(
                f"{setup_strategy}:{setup_signal}:smc_failed"
            )
            continue

        return setup, smc_check, rejected_reasons

    return None, None, rejected_reasons

def apply_candidate_confluence(candidate, top_candidates):
    if not ENABLE_SIGNAL_CONFLUENCE_GROUPING:
        return candidate

    signal = candidate.get("signal")

    same_direction_candidates = [
        item for item in top_candidates
        if item.get("signal") == signal
    ]

    confluence_strategies = list(
        dict.fromkeys(
            item.get("strategy", "UNKNOWN")
            for item in same_direction_candidates
        )
    )

    if len(confluence_strategies) <= 1:
        return candidate

    confluence_boost = min(
        (len(confluence_strategies) - 1) * CONFLUENCE_SCORE_BOOST_PER_STRATEGY,
        MAX_CONFLUENCE_SCORE_BOOST,
    )

    candidate["score"] = min(candidate.get("score", 0) + confluence_boost, 100)
    candidate["confluence_strategies"] = confluence_strategies

    reason = candidate.get("reason", "N/A")
    if "CONFLUENCE:" not in reason:
        candidate["reason"] = (
            f"{reason} | CONFLUENCE: {','.join(confluence_strategies)}"
        )

    logger.info(
        f"[CONFLUENCE] signal={signal} "
        f"strategies={confluence_strategies} "
        f"boost={confluence_boost} "
        f"final_score={candidate['score']}"
    )

    return candidate


def validate_candidate_pre_execution(
    candidate,
    df,
    tick,
    market_condition,
    close_price,
    atr,
):
    from src.adaptive_thresholds import get_adaptive_min_score

    candidate = candidate.copy()

    signal = candidate.get("signal")
    strategy_name = candidate.get("strategy", "UNKNOWN")
    score = candidate.get("score", 0)

    if signal not in ["BUY", "SELL"]:
        return False, candidate, "invalid_signal"

    # =========================
    # TRADING MODE FILTER
    # =========================
    if TRADING_MODE == "BUY_ONLY" and signal != "BUY":
        return False, candidate, "trading_mode_buy_only"

    if TRADING_MODE == "SELL_ONLY" and signal != "SELL":
        return False, candidate, "trading_mode_sell_only"

    # =========================
    # ORB ANTI-CHASE FILTER
    # =========================
    if strategy_name == "ORB":
        orb_low = candidate.get("orb_low")
        orb_high = candidate.get("orb_high")

        current_price = tick.ask if signal == "BUY" else tick.bid

        if signal == "SELL" and orb_low is not None:
            if abs(current_price - orb_low) > atr * 0.6:
                return False, candidate, "orb_too_extended_below_breakout"

        if signal == "BUY" and orb_high is not None:
            if abs(current_price - orb_high) > atr * 0.6:
                return False, candidate, "orb_too_extended_above_breakout"

    # =========================
    # SCORE FILTER
    # =========================
    min_required_score = get_adaptive_min_score(strategy_name, market_condition)

    if score < min_required_score:
        return (
            False,
            candidate,
            f"score_too_low {score}/{min_required_score}",
        )

    # =========================
    # MTF CONFIRMATION
    # =========================
    from config.settings import ENABLE_MTF_CONFIRMATION

    if ENABLE_MTF_CONFIRMATION:
        mtf_bias = get_mtf_bias()
        logger.info(f"[MTF] candidate={strategy_name} bias={mtf_bias} signal={signal}")

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
            return False, candidate, f"mtf_conflict bias={mtf_bias}"

        if mtf_conflict and allow_mtf_override:
            reason = candidate.get("reason", "N/A")
            candidate["reason"] = f"{reason} | MTF override: counter-bias {mtf_bias}"
            candidate.setdefault("mtf_reasons", [])
            candidate["mtf_reasons"].append(f"mtf_override_{mtf_bias}")

    # =========================
    # HTF FILTER
    # =========================
    htf_context = get_htf_context()

    if not htf_allows_signal(signal, htf_context, allow_neutral=True):
        return (
            False,
            candidate,
            f"htf_rejected bias={htf_context.get('bias') if htf_context else None}",
        )

    # =========================
    # HTF LIQUIDITY CONTEXT FILTER
    # =========================
    liquidity_context = get_liquidity_context()

    if not liquidity_allows_signal(signal, liquidity_context, allow_neutral=True):
        return (
            False,
            candidate,
            f"htf_liquidity_rejected reason={liquidity_context.get('reason')}",
        )

    # =========================
    # NEWS FILTER
    # =========================
    news_blocked, news_reason = is_news_blackout_active()

    if news_blocked:
        return False, candidate, f"news_blocked {news_reason}"

    return True, candidate, "passed"

def process_wait_better_entry_setups(df, tick, account_info, market_condition, session_name):
    wait_setups = execution_engine.get_wait_better_entry_setups()

    if not wait_setups:
        return False

    wait_setups = sorted(
        wait_setups,
        key=lambda setup: setup["data"].get("score", 0),
        reverse=True,
    )

    for setup in wait_setups:
        setup_data = setup["data"]
        signal = setup_data.get("signal")
        strategy_name = setup_data.get("strategy")
        required_rr = setup.get("better_entry_min_rr", get_min_rr(strategy_name))

        if signal not in ["BUY", "SELL"]:
            continue

        trade_plan = calculate_trade_plan(
            df=df,
            signal=signal,
            tick=tick,
            account_balance=account_info.balance,
            signal_data=setup_data,
        )

        if trade_plan is None:
            logger.info(
                f"[BETTER ENTRY] Trade plan still invalid | "
                f"strategy={strategy_name} signal={signal}"
            )
            continue

        trade_plan["score"] = setup_data.get("score", 0)
        trade_plan["strategy"] = strategy_name
        trade_plan["market_condition"] = market_condition
        trade_plan["reason"] = setup_data.get("reason", "N/A")
        trade_plan["session"] = setup_data.get("session", session_name)
        trade_plan["setup_id"] = setup_data.get("setup_id", "N/A")

        rr_value = calculate_rr_value(trade_plan)

        if rr_value is None or rr_value < required_rr:
            logger.info(
                f"[BETTER ENTRY] RR still too low | "
                f"strategy={strategy_name} rr={rr_value} required={required_rr}"
            )
            continue

        trade_allowed, guard_reason = check_trade_guard(signal, tick)

        if not trade_allowed:
            logger.info(
                f"[BETTER ENTRY] Guard blocked | "
                f"strategy={strategy_name} reason={guard_reason}"
            )
            continue

        from src.position_guard import has_same_direction_position

        opposite = "SELL" if signal == "BUY" else "BUY"

        if has_same_direction_position(SYMBOL, opposite):
            logger.info("[BETTER ENTRY] Opposite position exists → skipping")
            continue

        send_telegram_message(
            f"✅ Better Entry Ready #{setup_data.get('setup_id', 'N/A')}\n"
            f"Symbol: {SYMBOL}\n"
            f"Strategy: {strategy_name}\n"
            f"Signal: {signal}\n\n"
            f"Entry: {trade_plan['entry_price']}\n"
            f"SL: {trade_plan['stop_loss']}\n"
            f"TP: {trade_plan['take_profit']}\n"
            f"RR: {rr_value} / Required: {required_rr}"
        )

        execution_result = execute_trade(signal, trade_plan, SYMBOL)

        if execution_result:
            execution_engine.mark_executed(setup)
            return True

        setup["state"] = "EXECUTION_FAILED"
        setup["wait_reason"] = "Better entry execution failed"

        send_telegram_message(
            f"❌ Better Entry Execution Failed\n"
            f"Symbol: {SYMBOL}\n"
            f"Strategy: {strategy_name}\n"
            f"Signal: {signal}\n\n"
            f"Setup marked as failed to prevent repeated retries."
        )

        return False

    return False

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
    # WAIT FOR BETTER ENTRY CHECK
    # Runs every loop, not only on a new M15 candle.
    # =========================
    if ENABLE_WAIT_FOR_BETTER_ENTRY:
        if process_wait_better_entry_setups(
            df=df,
            tick=tick,
            account_info=account_info,
            market_condition="PENDING",
            session_name="PENDING",
        ):
            return current_candle_time

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
    from src.strategies.strategy_failed_breakout_reversal import generate_signal as failed_breakout_reversal_signal
    from src.strategies.strategy_failed_fvg_reversal import generate_signal as failed_fvg_reversal_signal

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
            ("FAILED_BREAKOUT_REVERSAL", failed_breakout_reversal_signal),
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

    elif market_condition == "PULLBACK_TREND":
        strategy_map = [
            ("HTF_TREND_PULLBACK", htf_trend_pullback_signal),
            ("ORDER_BLOCK", order_block_signal),
            ("BREAKER_BLOCK", breaker_block_signal),
            ("FVG_CE_MITIGATION", fvg_ce_mitigation_signal),
            ("FVG", fvg_signal),
            ("OB_FVG_COMBO", ob_fvg_combo_signal),
            ("RELIEF_RALLY", relief_rally_signal),
            ("WAVETREND_PIVOT", wavetrend_pivot_signal),
            ("STRUCTURE_LIQUIDITY", structure_liquidity_signal),
            ("LIQUIDITY_CANDLE", liquidity_candle_signal),
            ("SNIPER_V2", sniper_signal),
            ("STRICT", strict_signal),
        ]

    elif market_condition == "RANGING":
        strategy_map = [
            ("VWAP_RECLAIM", vwap_reclaim_signal),
            ("WAVETREND_PIVOT", wavetrend_pivot_signal),
            ("FRACTAL_SWEEP", fractal_sweep_signal),
            ("LIQUIDITY_TRAP", liquidity_trap_signal),
            ("FAILED_FVG_REVERSAL", failed_fvg_reversal_signal),
            ("FAILED_BREAKOUT_REVERSAL", failed_breakout_reversal_signal),
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
            ("FAILED_FVG_REVERSAL", failed_fvg_reversal_signal),
            ("FAILED_BREAKOUT_REVERSAL", failed_breakout_reversal_signal),
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

    if not ENABLE_FAILED_FVG_REVERSAL:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "FAILED_FVG_REVERSAL"
        ]
        logger.info("[STRATEGY TOGGLE] FAILED_FVG_REVERSAL disabled")

    if not ENABLE_FAILED_BREAKOUT_REVERSAL:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "FAILED_BREAKOUT_REVERSAL"
        ]
        logger.info("[STRATEGY TOGGLE] FAILED_BREAKOUT_REVERSAL disabled")

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

                result["score"] = max(0, min(result["score"], 100))

                signals.append(result)

        except Exception as e:
            logger.error(f"[STRATEGY ERROR] {name}: {e}")

    # =========================
    # SIGNAL SELECTION WITH CANDIDATE FALLBACK
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
        sorted_signals = sorted(
            signals,
            key=lambda item: item.get("score", 0),
            reverse=True,
        )

        top_candidates = sorted_signals[:MAX_CANDIDATES_PER_CANDLE]

        for index, candidate in enumerate(top_candidates, start=1):
            candidate["candidate_rank"] = index

        selected_candidate = None
        rejected_candidates = []

        candidates_to_check = top_candidates if ENABLE_CANDIDATE_FALLBACK else [top_candidates[0]]

        for candidate in candidates_to_check:
            candidate = apply_candidate_confluence(candidate.copy(), top_candidates)

            is_valid, validated_candidate, rejection_reason = validate_candidate_pre_execution(
                candidate=candidate,
                df=df,
                tick=tick,
                market_condition=market_condition,
                close_price=close_price,
                atr=atr,
            )

            if is_valid:
                selected_candidate = validated_candidate
                break

            rejected_candidates.append(
                {
                    "strategy": candidate.get("strategy"),
                    "signal": candidate.get("signal"),
                    "score": candidate.get("score"),
                    "reason": rejection_reason,
                }
            )

            logger.info(
                f"[CANDIDATE REJECTED] "
                f"strategy={candidate.get('strategy')} "
                f"signal={candidate.get('signal')} "
                f"score={candidate.get('score')} "
                f"reason={rejection_reason}"
            )

        if selected_candidate is None:
            signal = "NO_TRADE"
            score = 0
            strategy_name = None
            reason = "All top candidates rejected"
            selected_signal_data = {}

            if TELEGRAM_VERBOSE_SIGNALS and rejected_candidates:
                rejected_text = "\n".join(
                    [
                        f"- {item['strategy']} {item['signal']} "
                        f"score={item['score']} reason={item['reason']}"
                        for item in rejected_candidates
                    ]
                )

                send_telegram_message(
                    f"🚫 Top Candidates Rejected\n"
                    f"Symbol: {SYMBOL}\n\n"
                    f"{rejected_text}"
                )

        else:
            signal = selected_candidate["signal"]
            score = selected_candidate.get("score", 0)
            strategy_name = selected_candidate.get("strategy", "UNKNOWN")
            reason = selected_candidate.get("reason", "N/A")
            selected_signal_data = selected_candidate.copy()

            selected_signal_data["top_candidates"] = [
                {
                    "strategy": candidate.get("strategy"),
                    "signal": candidate.get("signal"),
                    "score": candidate.get("score"),
                    "entry_model": candidate.get("entry_model"),
                }
                for candidate in top_candidates
            ]

            selected_signal_data["confluence_strategies"] = selected_candidate.get(
                "confluence_strategies",
                [],
            )

            setup_id = build_setup_id(strategy_name, signal, tick.time)
            selected_signal_data["setup_id"] = setup_id

            # =========================
            # 📡 DETECTED SIGNAL
            # =========================
            if signal in ["BUY", "SELL"]:
                from src.notifier import build_trade_message

                detected_data = {
                    "stage": f"SETUP DETECTED #{selected_signal_data.get('setup_id')}",
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
                    "reason": reason,
                }

                send_telegram_message(build_trade_message(detected_data))

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

            if selected_signal_data.get("confluence_strategies"):
                if "CONFLUENCE:" not in reason:
                    reason += (
                        f" | CONFLUENCE: "
                        f"{','.join(selected_signal_data['confluence_strategies'])}"
                    )

            original_signal = signal
            original_strategy_name = strategy_name
            original_reason = reason
            original_score = score

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
    # TRADING TIME BLACKOUT FILTER
    # =========================
    if signal in ["BUY", "SELL"]:
        time_blocked, time_reason = is_trading_blackout_active()

        if time_blocked:
            logger.info(
                f"[TIME FILTER] Signal blocked | "
                f"strategy={strategy_name} signal={signal} reason={time_reason}"
            )

            send_telegram_message(
                f"🚫 Signal Blocked by Time Filter\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n\n"
                f"Reason: {time_reason}"
            )

            signal = "NO_TRADE"
            reason = time_reason

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
        best_setup, smc_check, rejected_ready_reasons = select_confirmed_ready_setup(
            ready_setups=ready_setups,
            df=df,
            selected_signal_data=selected_signal_data,
        )

        if best_setup is None:
            logger.info(
                f"[READY SETUP FALLBACK] No ready setup passed final confirmation | "
                f"rejected={rejected_ready_reasons}"
            )

            send_telegram_message(
                f"🚫 Ready Setups Rejected\n"
                f"Symbol: {SYMBOL}\n"
                f"Rejected: {', '.join(rejected_ready_reasons) or 'N/A'}"
            )

            return current_candle_time

        setup_data = best_setup["data"]
        setup_strategy = setup_data.get("strategy")
        setup_signal = setup_data.get("signal")
        setup_score = setup_data.get("score", score)

        logger.info(
            f"[EXECUTION] Using confirmed ready setup | "
            f"strategy={setup_strategy} "
            f"signal={setup_signal} "
            f"score={setup_score}"
        )

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
        # ✅ CONFIRMED TRADE
        # =========================


        if not best_setup.get("notified"):
            if TELEGRAM_VERBOSE_SIGNALS and not best_setup.get("notified"):
                send_telegram_message(
                    f"✅ Setup Confirmed #{selected_signal_data.get('setup_id', 'N/A')}\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Signal: {setup_data['signal']}\n"
                    f"Strategy: {setup_data['strategy']}\n\n"
                    f"Confirmation: passed\n"
                    f"Smart Money: {', '.join(smc_check['reasons'])}\n"
                    f"Waiting for risk approval 🚦"
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
        trade_plan["setup_id"] = selected_signal_data.get("setup_id", "N/A")

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
            if TELEGRAM_VERBOSE_SIGNALS and not best_setup.get("trade_plan_notified"):
                send_telegram_message(
                    f"📐 Trade Plan Ready #{selected_signal_data.get('setup_id', 'N/A')}\n"
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
        same_direction_count = count_same_direction_positions(SYMBOL, signal)
        is_extra_entry = same_direction_count >= 1

        if is_extra_entry and ENABLE_EXTRA_RR_DISCOUNT:
            min_rr_required = round(min_rr_required * EXTRA_RR_MULTIPLIER, 2)
            logger.info(
                f"[RR DISCOUNT] Extra entry RR adjusted | "
                f"strategy={strategy_name} required_rr={min_rr_required}"
            )

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
        reversal_summary = "Not checked"
        setup_id = selected_signal_data.get("setup_id", "N/A")

        if signal in ["BUY", "SELL"] and trade_plan is not None:
            entry = trade_plan.get("entry_price")
            sl = trade_plan.get("stop_loss")
            tp = trade_plan.get("take_profit")
            rr_value = calculate_rr_value(trade_plan)

            # =========================
            # WAIT FOR BETTER ENTRY
            # =========================
            if (
                low_rr_blocked
                and rr_value is not None
                and ENABLE_WAIT_FOR_BETTER_ENTRY
                and strategy_name in BETTER_ENTRY_STRATEGIES
                and "best_setup" in locals()
            ):
                execution_engine.mark_wait_better_entry(
                    setup=best_setup,
                    min_rr_required=min_rr_required,
                    current_rr=rr_value,
                    expiry_minutes=BETTER_ENTRY_EXPIRY_MINUTES,
                )

                send_telegram_message(
                    f"⏳ Setup #{setup_id} Waiting for Better Entry\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Strategy: {strategy_name}\n"
                    f"Signal: {signal}\n\n"
                    f"Current RR: {rr_value}\n"
                    f"Required RR: {min_rr_required}\n"
                    f"Expiry: {BETTER_ENTRY_EXPIRY_MINUTES} minutes"
                )

                return current_candle_time

            # =========================
            # BLOCKED SETUP REVERSAL CHECK
            # =========================
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
                    reversal_summary = "No valid reversal confirmation"

                elif reversal_data.get("score", 0) < BLOCKED_REVERSAL_MIN_SCORE:
                    reversal_summary = (
                        f"Rejected | score {reversal_data.get('score')} "
                        f"/ required {BLOCKED_REVERSAL_MIN_SCORE}"
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
                        reversal_summary = "Confirmed, but reversal trade plan failed"

                    else:
                        reversal_trade_plan["score"] = reversal_data.get("score", 0)
                        reversal_trade_plan["strategy"] = reversal_data.get("strategy")
                        reversal_trade_plan["market_condition"] = market_condition
                        reversal_trade_plan["reason"] = reversal_data.get("reason", "N/A")
                        reversal_trade_plan["session"] = selected_signal_data.get("session", session_name)
                        reversal_trade_plan["setup_id"] = setup_id

                        reversal_rr = calculate_rr_value(reversal_trade_plan)
                        reversal_allowed, reversal_guard_reason = check_trade_guard(
                            reversal_signal,
                            tick,
                        )

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
                            reversal_summary = (
                                f"Confirmed {reversal_signal}, but blocked | "
                                f"RR {reversal_rr} | {reversal_guard_reason}"
                            )

                        else:
                            from src.position_guard import has_same_direction_position

                            reversal_opposite = "SELL" if reversal_signal == "BUY" else "BUY"

                            if has_same_direction_position(SYMBOL, reversal_opposite):
                                reversal_summary = (
                                    f"Confirmed {reversal_signal}, but blocked | "
                                    f"opposite position already exists"
                                )

                            else:
                                send_telegram_message(
                                    f"🔁 Setup #{setup_id} Reversal Confirmed\n"
                                    f"Original: {strategy_name} {signal}\n"
                                    f"Reversal: {reversal_signal}\n"
                                    f"Strategy: {reversal_data.get('strategy')}\n\n"
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
            # FINAL BLOCKED MESSAGE
            # =========================
            send_telegram_message(
                f"🚫 Setup #{setup_id} Blocked\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n\n"
                f"Entry: {entry}\n"
                f"SL: {sl}\n"
                f"TP: {tp}\n"
                f"RR: {rr_value} / Required: {min_rr_required}\n\n"
                f"Reason: {guard_reason}\n"
                f"Reversal Check: {reversal_summary}"
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