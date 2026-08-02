import sys
import time
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd
import hashlib
import threading

from src.execution import check_trade_guard
from src.indicators import calculate_ema, calculate_atr
from src.logger import logger
from src.notifier import send_telegram_message
from src.order_executor import execute_trade
from src.position_manager import manage_positions
from src.risk import calculate_trade_plan
from src.setup_audit import log_setup_event
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
from src.news_filter import is_news_blackout_active, get_active_news_context
from src.time_filter import is_trading_blackout_active
from src.reversal_checker import build_blocked_setup_reversal
from src.external_macro_confirmation import apply_external_macro_confirmation
from src.position_guard import count_same_direction_positions
from src.google_sheets_logger import flush_google_sheets_retry_queue
from src.scenario_signature_confidence import get_scenario_signature_score_adjustment
from src.ai_shadow_advisor import get_ai_shadow_advice

from src.execution_block_memory import is_setup_execution_blocked
from src.execution_engine import ExecutionEngine
execution_engine = ExecutionEngine()

from src.strategy_advisory import (
    get_strategy_advisory,
    format_strategy_advisory,
    is_advisory_risky,
)

from src.market_outlook_advisory_runtime import maybe_send_runtime_outlook_advisory

from src.confirmation_engine import (
    run_universal_confirmation,
    format_confirmation_report,
)

from src.confirmation_observation_logger import log_confirmation_observation
from src.confirmation_risk_notifier import maybe_notify_confirmation_risk
from src.confirmation_summary_notifier import maybe_notify_confirmation_summary
from src.confirmation_shadow_policy import apply_confirmation_shadow_policy

from src.protected_reentry import (
    get_protected_reentry_context,
    apply_protected_reentry_confirmation,
)

from src.setup_similarity_memory import (
    notify_setup_similarity_if_relevant,
    get_setup_similarity_score_adjustment,
)

from src.scenario_cluster_memory import (
    notify_scenario_cluster_if_relevant,
    get_scenario_cluster_score_adjustment,
)

from src.memory_decision_report import (
    build_memory_decision_report,
    save_memory_decision_report,
)

from src.supply_demand_context import (
    analyze_supply_demand_context,
    apply_supply_demand_confirmation,
)

from src.elliott_fib_context import (
    analyze_elliott_fib_context,
    apply_elliott_fib_confirmation,
)

from src.setup_outcome_tracker import (
    register_setup_outcome,
    update_setup_outcomes,
)

from config.settings import (
    SYMBOL,
    TIMEFRAME,
    BARS_TO_FETCH,
    EMA_PERIOD,
    ATR_PERIOD,
    BREAKOUT_LOOKBACK,
    BREAKOUT_BUFFER,
    MAX_SPREAD,
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
    ENABLE_RANGE_SWEEP_RECLAIM,
    ENABLE_VWAP_RANGE_MEAN_REVERSION,
    ENABLE_BALANCED_AUCTION_RANGE,
    ENABLE_FCR_M1_FVG,
    ENABLE_FCR_M1_FVG_STARTUP_GUARD,
    FCR_M1_FVG_SKIP_ON_FIRST_CYCLE_AFTER_STARTUP,
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
    ENABLE_HTF_FIB_CONFLUENCE,
    ENABLE_SUPPLY_DEMAND_CONTEXT,
    ENABLE_SUPPLY_DEMAND_RETEST,
    ENABLE_EXTREME_SWEEP_RECLAIM,
    BETTER_ENTRY_FAST_EXPIRY_MINUTES,
    BETTER_ENTRY_FAST_EXPIRY_STRATEGIES,
    ALLOW_OPPOSITE_DIRECTION_TRADES,
    ENABLE_SCALP_MODE,
    SCALP_STRATEGIES,
    SCALP_MIN_SCORE,
    SCALP_MIN_RR,
    SCALP_FIXED_STOP_DISTANCE,
    SCALP_MIN_TARGET_DISTANCE,
    SCALP_MAX_TARGET_DISTANCE,
    ENABLE_DELAYED_RETRACE_ENTRY,
    DELAYED_ENTRY_OFFSET_PRICE,
    DELAYED_ENTRY_EXPIRY_MINUTES,
    DELAYED_ENTRY_STRATEGIES,
    ENABLE_SPLIT_DELAYED_ENTRY,
    SPLIT_DELAYED_ENTRY_IMMEDIATE_PCT,
    ENABLE_DELAYED_ENTRY_CONFIRMATION,
    DELAYED_ENTRY_CONFIRMATION_TIMEFRAME,
    DELAYED_ENTRY_CONFIRMATION_BARS,
    DELAYED_ENTRY_CONFIRMATION_BUFFER_PRICE,
    DELAYED_ENTRY_MIN_BODY_ATR,
    DELAYED_ENTRY_OFFSET_BY_MARKET,
    ENABLE_MTF_SR_FVG_RECLAIM,
    ENABLE_ELLIOTT_FIB_CONTEXT,
    REQUIRE_M5_CONFIRMATION_FOR_EXTRA,
    EXTRA_ENTRY_CONFIRMATION_TIMEFRAME,
    EXTRA_ENTRY_CONFIRMATION_BARS,
    EXTRA_ENTRY_MIN_BODY_ATR,
    ENABLE_PROTECTED_REENTRY,
    ENABLE_TIME_CONTEXT_ENGINE,
    ENABLE_ORB_V00,
    ENABLE_IFVG_RETEST_CONFLUENCE,
    ENABLE_SOFT_SMC_FOR_STRONG_SETUPS,
    SOFT_SMC_MIN_SCORE,
    SOFT_SMC_STRATEGIES,
    ENABLE_WAVETREND_MOMENTUM_M5,
    ENABLE_MICRO_SR_SWEEP_RECLAIM,
    WAVETREND_MOMENTUM_MIN_RR,
    ENABLE_M5_EXECUTION_CONFIRMATION,
    M5_EXECUTION_CONFIRMATION_TIMEFRAME,
    M5_EXECUTION_CONFIRMATION_BARS,
    M5_EXECUTION_MIN_BODY_ATR,
    M5_EXECUTION_CONFIRMATION_STRATEGIES,
    CONFLUENCE_DUPLICATE_STRATEGY_GROUPS,
    ENABLE_FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE,
    FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_STRATEGIES,
    FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_MIN_SCORE,
    FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_MIN_RR,
    FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_SESSIONS,
    FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_ENTRY_KEYWORDS,
    ENABLE_CANDIDATE_REJECTION_RECOVERY,
    CANDIDATE_REJECTION_RECOVERY_REQUIRE_M5_CONFIRMATION,
    CANDIDATE_REJECTION_RECOVERY_MIN_RECOVERED_RR,
    ENABLE_CONTINUATION_SAFETY_GUARD,
    CONTINUATION_SAFETY_BLOCK_ORB_FAST_ON_ELLIOTT_FIB_CONFLICT,
    CONTINUATION_SAFETY_ORB_FAST_MAX_RANGE_ATR_MULTIPLIER,
    CONTINUATION_SAFETY_RETRACE_FIRST_STRATEGIES,
    CONTINUATION_SAFETY_RETRACE_FIRST_ENTRY_MODELS,
    CONTINUATION_SAFETY_MIN_IMMEDIATE_RR,
    ENABLE_MTF_CONFLICT_OPPORTUNITY_TRACKER,
    ENABLE_MTF_CONFLICT_SOFT_EXECUTION,
    MTF_CONFLICT_SOFT_EXECUTION_STRATEGIES,
    MTF_CONFLICT_SOFT_EXECUTION_MIN_SCORE,
    MTF_CONFLICT_USE_CALCULATED_TP_WHEN_NO_MTF_POSITION,
    MTF_CONFLICT_SCALP_ONLY_WHEN_MTF_POSITION_EXISTS,
    MTF_CONFLICT_COUNTER_SCALP_TP_PRICE,
    MTF_CONFLICT_COUNTER_SCALP_SL_PRICE,
    MTF_CONFLICT_COUNTER_SCALP_LOT_MULTIPLIER,
    MTF_CONFLICT_REQUIRE_M5_CONFIRMATION,
    MTF_CONFLICT_REQUIRE_SHADOW_TRADE_PLAN,
    MTF_CONFLICT_REQUIRE_SHADOW_RR_FOR_NORMAL_EXECUTION,
    MTF_CONFLICT_REQUIRE_SHADOW_RR_FOR_SCALP,
    MTF_CONFLICT_RETRACE_FIRST_STRATEGIES,
    MTF_CONFLICT_TRACK_ONLY_STRATEGIES,
    ENABLE_OPENING_STRATEGY_BLACKOUT,
    OPENING_STRATEGY_BLACKOUT_START,
    OPENING_STRATEGY_BLACKOUT_END,
    OPENING_STRATEGY_BLACKOUT_STRATEGIES,
    ENABLE_FVG_ZONE_STAGED_ENTRY,
    FVG_ZONE_STAGED_ENTRY_STRATEGIES,
    FVG_ZONE_STAGED_ENTRY_LEVELS,
    FVG_ZONE_STAGED_ENTRY_EXPIRY_MINUTES,
    FVG_ZONE_STAGED_ENTRY_SL_BUFFER,
    STRATEGY_EXTRA_SL_BUFFER,
    LOG_STRATEGY_SESSION_BLOCKS_TO_SHEETS,
    LOG_OPENING_BLACKOUT_BLOCKS_TO_SHEETS,
    ENABLE_TICK_LEVEL_RECOVERY_RETRY,
    ENABLE_MTF_CONFLICT_HIGH_SLIPPAGE_RETRY,
    ENABLE_LOW_RR_RECOVERY_HIGH_SLIPPAGE_RETRY,
    HIGH_SLIPPAGE_RETRY_EXPIRY_MINUTES,
    HIGH_SLIPPAGE_RETRY_SOURCES,
    ENABLE_ORB_TICK_BREAKOUT_WATCHER,
    ORB_TICK_BREAKOUT_WATCH_STRATEGIES,
    ORB_TICK_BREAKOUT_EXPIRY_MINUTES,
    ORB_TICK_BREAKOUT_MIN_DISTANCE,
    ORB_TICK_BREAKOUT_MIN_RR,
    ORB_TICK_BREAKOUT_REQUIRE_M5_CONFIRMATION,
    ENABLE_CANDIDATE_REJECTION_TELEGRAM_ALERTS,
    TELEGRAM_NOTIFY_CANDIDATE_REJECTED_LOW_RR,
    TELEGRAM_NOTIFY_CANDIDATE_RECOVERY_INVALIDATED,
    TELEGRAM_NOTIFY_GENERIC_CANDIDATE_REJECTED,
    ENABLE_SMC_FAILED_LOW_RR_SL_ZONE_RECOVERY,
    SMC_FAILED_LOW_RR_SL_ZONE_RATIO,
    SMC_FAILED_LOW_RR_ALLOW_POST_SL_SWEEP_RECLAIM,
    SMC_FAILED_LOW_RR_SL_ZONE_STRATEGIES,
    SMC_FAILED_LOW_RR_SL_ZONE_EXPIRY_MINUTES,
    ENABLE_SETUP_OUTCOME_TRACKER,
    ENABLE_SETUP_OUTCOME_MEMORY_GUARD,
    MEMORY_GUARD_BLOCK_DANGEROUS_PATTERNS,
    MEMORY_GUARD_MIN_SAMPLES_FOR_WARNING,
    MEMORY_GUARD_MIN_SAMPLES_FOR_BLOCK,
    MEMORY_GUARD_NOTIFY_ON_WARNING,
    ENABLE_SCENARIO_SIGNATURE_TELEGRAM_ALERTS,
    SCENARIO_SIGNATURE_TELEGRAM_ALERT_CLASSIFICATIONS,
    ENABLE_MEMORY_DECISION_REPORT,
    AI_SHADOW_ADVISOR_NOTIFY_TELEGRAM,
    AI_SHADOW_ADVISOR_EXECUTION_CONTROL_ENABLED,
    AI_SHADOW_ADVISOR_EXECUTION_CONTROL_MODE,
    AI_SHADOW_ADVISOR_BLOCK_RECOMMENDATIONS,
    AI_SHADOW_ADVISOR_ALLOW_RECOMMENDATIONS,
    AI_SHADOW_ADVISOR_MIN_SAMPLES_FOR_CONTROL,
    ENABLE_TICK_SNIPER_EXECUTION,
    TICK_SNIPER_ALLOWED_STRATEGIES,
    TICK_SNIPER_MIN_SCORE,
    TICK_SNIPER_MIN_RR,
    TICK_SNIPER_MIN_MOVE_PRICE,
    TICK_SNIPER_EXPIRY_SECONDS,
    TICK_SNIPER_NOTIFY_TELEGRAM,
    TICK_SNIPER_REQUIRE_M5_CONFIRMATION,
    TICK_SNIPER_STRATEGY_PROFILES,
    ENABLE_INTRABAR_PRICE_EVENT_DETECTOR,
    INTRABAR_PRICE_EVENT_ALLOWED_STRATEGIES,
    INTRABAR_PRICE_EVENT_MIN_SCORE,
    INTRABAR_PRICE_EVENT_MIN_RR,
    INTRABAR_PRICE_EVENT_BREAK_DISTANCE_PRICE,
    INTRABAR_PRICE_EVENT_RECLAIM_BUFFER_PRICE,
    INTRABAR_PRICE_EVENT_STRATEGY_PROFILES,
    INTRABAR_PRICE_EVENT_REQUIRE_M5_CONFIRMATION,
    INTRABAR_PRICE_EVENT_NOTIFY_TELEGRAM,
    INTRABAR_PRICE_EVENT_MAX_BREAK_DISTANCE_PRICE,
    INTRABAR_PRICE_EVENT_EXPIRY_SECONDS,
    ENABLE_INTRABAR_PRICE_EVENT_VWAP_FILTER,
    ENABLE_INTRABAR_PRICE_EVENT_STRUCTURE_FILTER,
    ENABLE_INTRABAR_PRICE_EVENT_REVERSAL_FILTER,
    INTRABAR_PRICE_EVENT_MIN_CURRENT_BODY_ATR,
    INTRABAR_PRICE_EVENT_MIN_STRUCTURE_BREAK_PRICE,
    INTRABAR_PRICE_EVENT_VWAP_LOOKBACK_BARS,
    ENABLE_INTRABAR_PRICE_EVENT_DEDUP_GUARD,
    INTRABAR_PRICE_EVENT_DEDUP_SECONDS,
    INTRABAR_PRICE_EVENT_MAX_PER_CANDLE,
    INTRABAR_PRICE_EVENT_MAX_PER_STRATEGY_PER_CANDLE,
    INTRABAR_PRICE_EVENT_LOG_DUPLICATE_SKIPS,
    ENABLE_INTRABAR_M5_CONFIRMATION_FILTERS,
    INTRABAR_M5_CONFIRMATION_TIMEFRAME,
    INTRABAR_M5_CONFIRMATION_BARS,
    INTRABAR_M5_CONFIRMATION_STRATEGIES,
    INTRABAR_M5_USE_HEIKIN_ASHI,
    INTRABAR_M5_USE_PARABOLIC_SAR,
    INTRABAR_M5_PSAR_STEP,
    INTRABAR_M5_PSAR_MAX_STEP,
    INTRABAR_M5_REQUIRE_ALL_FILTERS,
    ENABLE_GENERIC_REJECTED_CANDIDATE_TRADE_PLAN,
    GENERIC_REJECTED_CANDIDATE_MIN_RR_TO_TRACK,
    GENERIC_REJECTED_CANDIDATE_RECOVERY_REASONS,
    GENERIC_REJECTED_CANDIDATE_NOTIFY_TELEGRAM,
    INTRABAR_PRICE_EVENT_EXTRA_SL_PRICE,
    INTRABAR_PRICE_EVENT_MIN_SL_DISTANCE_PRICE,
    INTRABAR_PRICE_EVENT_MAX_SL_DISTANCE_PRICE,
    INTRABAR_PRICE_EVENT_MIN_TP_DISTANCE_PRICE,
    INTRABAR_PRICE_EVENT_MAX_TP_DISTANCE_PRICE,
    INTRABAR_PRICE_EVENT_DEFAULT_TARGET_RR,
    ENABLE_STRATEGY_ADVISORY,
    PHASE6S_RUNTIME_OUTLOOK_ADVISORY_FORCE_SEND,
    PHASE6S_RUNTIME_OUTLOOK_ADVISORY_REPORT_TYPE,
    SEND_PHASE6S_RUNTIME_OUTLOOK_ADVISORY_TELEGRAM,
    ENABLE_PHASE6S_RUNTIME_OUTLOOK_ADVISORY,
    TELEGRAM_NOTIFY_STRATEGY_ADVISORY_CRITICAL,
    STRATEGY_ADVISORY_TELEGRAM_DECISIONS,
    STRATEGY_ADVISORY_TELEGRAM_COOLDOWN_MINUTES,
    TELEGRAM_NOTIFY_MTF_CONFLICT_CANDIDATE_TRACKED,
    MTF_CONFLICT_CANDIDATE_TELEGRAM_MIN_SCORE,
    MTF_CONFLICT_CANDIDATE_TELEGRAM_MIN_RR,
    MTF_CONFLICT_CANDIDATE_TELEGRAM_HIGH_SCORE,
    STRATEGY_ADVISORY_TELEGRAM_MIN_SAMPLES,
    STRATEGY_ADVISORY_SKIP_TRACK_ONLY_LOW_SAMPLE_ALERTS,
    TELEGRAM_NOTIFY_REJECTED_CANDIDATE_TRACKED,
    REJECTED_CANDIDATE_TELEGRAM_MIN_SCORE,
    REJECTED_CANDIDATE_TELEGRAM_MIN_RR,
    REJECTED_CANDIDATE_TELEGRAM_COOLDOWN_MINUTES,
    ENABLE_PRO_TRADER_REPLICATION,
    ENABLE_KEY_LEVEL_BREAK_HOLD,
    ENABLE_VOLATILITY_COMPRESSION_BREAKOUT,
    ENABLE_PSYCH_ROUND_NUMBER_REJECTION,
    ENABLE_SESSION_EXHAUSTION_REVERSAL,
    ENABLE_AUTO_STRUCTURAL_LEVEL_SCALP,
    ENABLE_HTF_REJECTION_CANDLE_MTF_ENTRY,
    ENABLE_HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY,
    ENABLE_HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY,
)

from src.candidate_rejection_recovery import (
    register_rejected_candidate_for_recovery,
    get_waiting_recovery_candidates,
    mark_recovery_candidate_executed,
    mark_recovery_candidate_failed,
    mark_recovery_candidate_invalidated,
)

from src.mtf_conflict_opportunity_tracker import (
    register_mtf_conflict_opportunity,
    mark_mtf_conflict_opportunity_executed,
    mark_mtf_conflict_opportunity_failed,
    update_mtf_conflict_opportunities,
)

from src.structure_liquidity_context import (
    analyze_structure_liquidity,
    apply_structure_liquidity_confirmation,
)

from src.time_context import (
    analyze_time_context,
    apply_time_context_confirmation,
)

INTRABAR_DETECTION_CACHE = {}
INTRABAR_PRICE_EVENT_DEDUP_CACHE = {}
MTF_CONFLICT_TRACKED_CACHE = {}
_REJECTED_CANDIDATE_TELEGRAM_CACHE = {}

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
    "HTF_FIB_CONFLUENCE",
    "SUPPLY_DEMAND_RETEST",
    "EXTREME_SWEEP_RECLAIM",
    "MTF_SR_FVG_RECLAIM",
    "ORB_V00",
    "IFVG_RETEST_CONFLUENCE",
    "RANGE_SWEEP_RECLAIM",
    "VWAP_RANGE_MEAN_REVERSION",
    "WAVETREND_MOMENTUM",
    "MICRO_SR_SWEEP_RECLAIM",
    "PRO_TRADER_REPLICATION",
    "KEY_LEVEL_BREAK_HOLD",
    "BALANCED_AUCTION_RANGE",
    "VOLATILITY_COMPRESSION_BREAKOUT",
    "PSYCH_ROUND_NUMBER_REJECTION",
    "SESSION_EXHAUSTION_REVERSAL",
    "AUTO_STRUCTURAL_LEVEL_SCALP",
    "HTF_REJECTION_CANDLE_MTF_ENTRY",
    "HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY",
    "HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY",
}

def send_telegram_message_async(message):
    def _worker():
        try:
            send_telegram_message(message)
        except Exception as e:
            logger.error(f"[TELEGRAM ASYNC] Failed: {e}")


    threading.Thread(target=_worker, daemon=True).start()


def _phase6s_pick(*values):
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _phase6s_runtime_advisory_notifier(message):
    send_telegram_message_async(message)
    return True


def maybe_notify_phase6s_runtime_outlook_advisory(signal_payload, trade_plan, trigger_context="pre_execution"):
    """
    Phase 6S7 live_bot hook.

    Advisory only:
    - does not block trades
    - does not change risk
    - does not approve execution
    - only sends Telegram when explicitly enabled in settings
    """
    if not ENABLE_PHASE6S_RUNTIME_OUTLOOK_ADVISORY:
        return {
            "phase": "PHASE_6S7_LIVE_BOT_RUNTIME_OUTLOOK_ADVISORY",
            "enabled": False,
            "reason": "disabled_by_config",
            "decision_impact": "NONE",
            "auto_trade_allowed": False,
            "can_execute": False,
            "can_block_trade": False,
            "can_modify_risk": False,
        }

    try:
        raw_signal = signal_payload if isinstance(signal_payload, dict) else {"signal": signal_payload}
        plan = trade_plan if isinstance(trade_plan, dict) else {}

        raw_setup = dict(raw_signal)

        raw_setup.update(
            {
                "setup_id": _phase6s_pick(
                    raw_signal.get("setup_id"),
                    raw_signal.get("id"),
                    raw_signal.get("signal_id"),
                    plan.get("setup_id"),
                    plan.get("candidate_setup_id"),
                    plan.get("source_setup_id"),
                ),
                "strategy": _phase6s_pick(
                    raw_signal.get("strategy"),
                    raw_signal.get("strategy_name"),
                    raw_signal.get("setup_source"),
                    raw_signal.get("setup_type"),
                    plan.get("strategy"),
                    plan.get("strategy_name"),
                    plan.get("setup_source"),
                    plan.get("setup_type"),
                ),
                "signal": _phase6s_pick(
                    raw_signal.get("signal"),
                    raw_signal.get("direction"),
                    raw_signal.get("side"),
                    plan.get("signal"),
                    plan.get("direction"),
                    plan.get("side"),
                ),
                "entry_reference": _phase6s_pick(
                    plan.get("entry_reference"),
                    plan.get("entry"),
                    plan.get("entry_price"),
                    raw_signal.get("entry_reference"),
                    raw_signal.get("entry"),
                    raw_signal.get("entry_price"),
                    raw_signal.get("price"),
                    raw_signal.get("close"),
                ),
                "sl_reference": _phase6s_pick(
                    plan.get("sl_reference"),
                    plan.get("sl"),
                    plan.get("stop_loss"),
                    raw_signal.get("sl_reference"),
                    raw_signal.get("sl"),
                    raw_signal.get("stop_loss"),
                ),
                "tp_reference": _phase6s_pick(
                    plan.get("tp_reference"),
                    plan.get("tp"),
                    plan.get("take_profit"),
                    plan.get("tp1"),
                    raw_signal.get("tp_reference"),
                    raw_signal.get("tp"),
                    raw_signal.get("take_profit"),
                    raw_signal.get("tp1"),
                ),
                "rr": _phase6s_pick(
                    plan.get("rr"),
                    plan.get("risk_reward"),
                    plan.get("original_rr"),
                    raw_signal.get("rr"),
                    raw_signal.get("risk_reward"),
                    raw_signal.get("original_rr"),
                ),
                "phase6s_trigger_context": trigger_context,
            }
        )

        summary = maybe_send_runtime_outlook_advisory(
            raw_setup=raw_setup,
            symbol=SYMBOL,
            report_type=PHASE6S_RUNTIME_OUTLOOKSYMBOL,
            enabled=True,
            send_telegram=SEND_PHASE6S_RUNTIME_OUTLOOK_ADVISORY_TELEGRAM,
            force_send=PHASE6S_RUNTIME_OUTLOOK_ADVISORY_FORCE_SEND,
            notifier=_phase6s_runtime_advisory_notifier,
        )

        logger.info(
            "[PHASE 6S7 OUTLOOK ADVISORY] "
            f"ready={summary.get('ready')} "
            f"risk={summary.get('risk_level')} "
            f"alignment={summary.get('alignment')} "
            f"should_notify={summary.get('should_notify')} "
            f"telegram_sent={summary.get('telegram_sent')} "
            f"decision_impact={summary.get('decision_impact')} "
            f"can_block_trade={summary.get('can_block_trade')} "
            f"can_modify_risk={summary.get('can_modify_risk')} "
            f"context={trigger_context}"
        )

        return summary

    except Exception as exc:
        logger.error(f"[PHASE 6S7 OUTLOOK ADVISORY] Failed: {exc}")

        return {
            "phase": "PHASE_6S7_LIVE_BOT_RUNTIME_OUTLOOK_ADVISORY",
            "enabled": True,
            "reason": "exception",
            "error": str(exc),
            "decision_impact": "NONE",
            "auto_trade_allowed": False,
            "can_execute": False,
            "can_block_trade": False,
            "can_modify_risk": False,
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

    if trade_plan.get("key_level_tp_ladder_applied"):
        for rr_key in ("original_rr", "rr", "risk_reward"):
            try:
                rr_value = float(trade_plan.get(rr_key))
                if rr_value > 0:
                    return rr_value >= min_rr
            except Exception:
                pass

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


def get_min_rr(strategy_name, entry_model=None, sl_model=None):
    if strategy_name == "BREAKER_BLOCK":
        if sl_model == "RETEST_CANDLE_STRUCTURE_SL":
            return 1.25

        if sl_model == "FULL_BREAKER_STRUCTURE_SL":
            return 1.10

        return 1.20

    if strategy_name == "ORB":
        if entry_model == "FAST_CONTINUATION":
            return 2.0

        return 1.2

    if strategy_name == "RANGE_SWEEP_RECLAIM":
        return 1.20

    if strategy_name == "VWAP_RANGE_MEAN_REVERSION":
        return 1.15

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

    if strategy_name in rr_140:
        return 1.40

    if strategy_name in rr_130:
        return 1.30

    if strategy_name in rr_125:
        return 1.25

    if strategy_name in rr_110:
        return 1.10

    if strategy_name == "WAVETREND_MOMENTUM":
        return WAVETREND_MOMENTUM_MIN_RR

    return 1.10

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

def m5_execution_confirmation_ok(signal, strategy_name):
    if not ENABLE_M5_EXECUTION_CONFIRMATION:
        return True, "m5_execution_confirmation_disabled"

    if strategy_name not in M5_EXECUTION_CONFIRMATION_STRATEGIES:
        return True, "strategy_not_required_for_m5_confirmation"

    rates = mt5.copy_rates_from_pos(
        SYMBOL,
        M5_EXECUTION_CONFIRMATION_TIMEFRAME,
        0,
        M5_EXECUTION_CONFIRMATION_BARS,
    )

    if rates is None or len(rates) < 10:
        return False, "no_m5_execution_confirmation_data"

    m5_df = pd.DataFrame(rates)
    m5_df["time"] = pd.to_datetime(m5_df["time"], unit="s")
    m5_df["ema_20"] = calculate_ema(m5_df, EMA_PERIOD)
    m5_df["atr_14"] = calculate_atr(m5_df, ATR_PERIOD)

    candle = m5_df.iloc[-2]
    prev = m5_df.iloc[-3]

    atr = candle["atr_14"]
    body = abs(candle["close"] - candle["open"])
    candle_range = candle["high"] - candle["low"]

    if atr <= 0 or candle_range <= 0:
        return False, "invalid_m5_confirmation_candle"

    if body < atr * M5_EXECUTION_MIN_BODY_ATR:
        return False, "m5_confirmation_body_too_small"

    if signal == "BUY":
        confirmed = (
            candle["close"] > candle["open"]
            and candle["close"] > candle["ema_20"]
            and (
                candle["close"] > prev["high"]
                or candle["close"] >= candle["low"] + candle_range * 0.60
            )
        )

        if confirmed:
            return True, "m5_buy_execution_confirmed"

        return False, "m5_buy_execution_not_confirmed"

    if signal == "SELL":
        confirmed = (
            candle["close"] < candle["open"]
            and candle["close"] < candle["ema_20"]
            and (
                candle["close"] < prev["low"]
                or candle["close"] <= candle["high"] - candle_range * 0.60
            )
        )

        if confirmed:
            return True, "m5_sell_execution_confirmed"

        return False, "m5_sell_execution_not_confirmed"

    return False, "invalid_signal"

def get_trade_setup_id(trade_plan=None, signal_data=None, setup=None):
    if trade_plan is not None:
        setup_id = trade_plan.get("setup_id")
        if setup_id:
            return setup_id

    if signal_data is not None:
        setup_id = signal_data.get("setup_id")
        if setup_id:
            return setup_id

    if setup is not None:
        setup_id = setup.get("setup_id") or setup.get("id")
        if setup_id:
            return setup_id

        setup_data = setup.get("data", {})
        setup_id = setup_data.get("setup_id")
        if setup_id:
            return setup_id

    return None

def detect_setup_source_bucket_for_advisory(signal_data, default="NORMAL_OR_TRACKED"):
    if not signal_data:
        return default

    setup_id = str(signal_data.get("setup_id") or "").upper()
    entry_model = str(signal_data.get("entry_model") or "").upper()
    market_condition = str(signal_data.get("market_condition") or "").upper()
    strategy = str(signal_data.get("strategy") or "").upper()

    source_events = signal_data.get("source_events", "")

    if isinstance(source_events, list):
        source_events_text = "|".join(str(x).upper() for x in source_events)
    else:
        source_events_text = str(source_events or "").upper()

    combined = "|".join([
        setup_id,
        entry_model,
        market_condition,
        strategy,
        source_events_text,
    ])

    if "INTRABAR" in combined:
        return "INTRABAR"

    if "TICK_SNIPER" in combined:
        return "TICK_SNIPER"

    if "ORB_TICK" in combined:
        return "ORB_TICK_WATCHER"

    if "MTF_CONFLICT" in combined:
        return "MTF_CONFLICT_TRACKED"

    if "CANDIDATE_REJECTED" in combined or "LOW_RR" in combined:
        return "REJECTED_CANDIDATE_TRACKED"

    return default

_STRATEGY_ADVISORY_TELEGRAM_CACHE = {}

def apply_strategy_advisory_note(signal_data, strategy_name=None, setup_source_bucket=None):
    if not ENABLE_STRATEGY_ADVISORY:
        return None

    strategy = strategy_name or (signal_data or {}).get("strategy")

    if not strategy:
        return None

    setup_source_bucket = setup_source_bucket or detect_setup_source_bucket_for_advisory(signal_data)

    advisory = get_strategy_advisory(
        strategy=strategy,
        setup_source_bucket=setup_source_bucket,
    )

    if not advisory:
        logger.info(
            f"[STRATEGY ADVISORY] No advisory found | "
            f"strategy={strategy} source_bucket={setup_source_bucket}"
        )
        return None

    message = format_strategy_advisory(advisory)
    logger.warning(message)

    decision = advisory.get("decision")

    if (
        TELEGRAM_NOTIFY_STRATEGY_ADVISORY_CRITICAL
        and decision in STRATEGY_ADVISORY_TELEGRAM_DECISIONS
        and is_advisory_risky(advisory)
    ):
        now_ts = time.time()
        cooldown_seconds = STRATEGY_ADVISORY_TELEGRAM_COOLDOWN_MINUTES * 60

        alert_key = (
            advisory.get("policy_key"),
            advisory.get("decision"),
        )

        last_sent_ts = _STRATEGY_ADVISORY_TELEGRAM_CACHE.get(alert_key, 0)

        if now_ts - last_sent_ts >= cooldown_seconds:
            sample_count = int(advisory.get("sample_count") or 0)
            decision_reason = str(advisory.get("decision_reason") or "")

            if (
                STRATEGY_ADVISORY_SKIP_TRACK_ONLY_LOW_SAMPLE_ALERTS
                and decision == "TRACK_ONLY"
                and sample_count < STRATEGY_ADVISORY_TELEGRAM_MIN_SAMPLES
            ):
                logger.info(
                    f"[STRATEGY ADVISORY] Telegram skipped for low-sample TRACK_ONLY | "
                    f"strategy={advisory.get('strategy')} "
                    f"bucket={advisory.get('setup_source_bucket')} "
                    f"samples={sample_count}/{STRATEGY_ADVISORY_TELEGRAM_MIN_SAMPLES} "
                    f"reason={decision_reason}"
                )
            else:
                _STRATEGY_ADVISORY_TELEGRAM_CACHE[alert_key] = now_ts

                send_telegram_message_async(
                    "⚠️ STRATEGY ADVISORY — CRITICAL\n"
                    f"Strategy: {advisory.get('strategy')}\n"
                    f"Bucket: {advisory.get('setup_source_bucket')}\n"
                    f"Decision: {decision}\n"
                    f"Samples: {advisory.get('sample_count')}\n"
                    f"W10: {advisory.get('w10_rate')}\n"
                    f"TP: {advisory.get('tp_rate')}\n"
                    f"SL: {advisory.get('sl_rate')}\n"
                    f"Expectancy: {advisory.get('synthetic_expectancy')}\n"
                    f"Reason: {advisory.get('decision_reason')}\n"
                    "Action: advisory only — trade is NOT blocked automatically."
                )
        else:
            logger.info(
                f"[STRATEGY ADVISORY] Telegram skipped by cooldown | "
                f"key={alert_key} cooldown_min={STRATEGY_ADVISORY_TELEGRAM_COOLDOWN_MINUTES}"
            )

    return advisory


def build_confirmation_engine_audit_extra(report):
    if not report:
        return {}

    return {
        "confirmation_engine_version": report.get("engine_version"),
        "confirmation_mode": report.get("mode"),
        "confirmation_approved": report.get("approved"),
        "confirmation_confidence": report.get("confidence"),
        "confirmation_score_delta": report.get("score_delta"),
        "confirmation_summary": report.get("summary"),
        "confirmation_disabled_layers": report.get("disabled_layers", []),
        "confirmation_required_failed_modules": [
            item.get("module")
            for item in report.get("required_failed", []) or []
        ],
        "confirmation_optional_failed_modules": [
            item.get("module")
            for item in report.get("optional_failed", []) or []
        ],
        "confirmation_modules": [
            {
                "module": item.get("module"),
                "status": item.get("status"),
                "confidence": item.get("confidence"),
                "score_delta": item.get("score_delta"),
                "required": item.get("required"),
                "source_type": item.get("source_type"),
                "reason": item.get("reason"),
            }
            for item in report.get("results", []) or []
        ],
    }


def observe_universal_confirmation_for_setup(
    *,
    selected_signal_data,
    trade_plan,
    df,
    tick,
    session_name,
    market_condition,
    min_rr_required=None,
    max_spread=None,
):
    """
    Phase 1B observe-only integration.

    This must not block trades, change score, change trade_plan,
    or alter execution behavior.
    """

    selected_signal_data = selected_signal_data or {}
    trade_plan = trade_plan or {}

    try:
        from config import settings as _confirmation_settings

        if not getattr(_confirmation_settings, "ENABLE_CONFIRMATION_ENGINE_OBSERVE_ONLY", True):
            logger.info("[CONFIRMATION ENGINE] Observe-only layer disabled by settings.")
            return None

    except Exception:
        pass

    try:
        report = run_universal_confirmation(
            signal_data=selected_signal_data,
            trade_plan=trade_plan,
            df=df,
            tick=tick,
            session=session_name,
            market_condition=market_condition,
            orderflow_snapshot=None,
            min_rr=min_rr_required,
            max_spread=max_spread,
            enforce_required=False,
        )

        selected_signal_data["confirmation_engine"] = report
        selected_signal_data["confirmation_engine_summary"] = report.get("summary")
        selected_signal_data["confirmation_engine_confidence"] = report.get("confidence")
        selected_signal_data["confirmation_engine_score_delta"] = report.get("score_delta")
        selected_signal_data["confirmation_engine_mode"] = report.get("mode")

        setup_source_bucket_for_confirmation = (
            selected_signal_data.get("setup_source_bucket")
            or selected_signal_data.get("execution_bucket")
            or trade_plan.get("setup_source_bucket")
            or trade_plan.get("execution_bucket")
        )

        apply_confirmation_shadow_policy(report)

        log_confirmation_observation(
            report=report,
            signal_data=selected_signal_data,
            trade_plan=trade_plan,
            setup_source_bucket=setup_source_bucket_for_confirmation,
            notes="Phase 1F structured confirmation observation",
        )

        maybe_notify_confirmation_risk(
            report=report,
            signal_data=selected_signal_data,
            trade_plan=trade_plan,
            setup_source_bucket=setup_source_bucket_for_confirmation,
        )

        maybe_notify_confirmation_summary(
            report=report,
            signal_data=selected_signal_data,
            trade_plan=trade_plan,
            setup_source_bucket=setup_source_bucket_for_confirmation,
        )

        logger.info(format_confirmation_report(report))

        log_setup_event(
            setup_id=selected_signal_data.get("setup_id") or trade_plan.get("setup_id"),
            event="CONFIRMATION_ENGINE_OBSERVATION",
            strategy=selected_signal_data.get("strategy") or trade_plan.get("strategy"),
            signal=selected_signal_data.get("signal") or trade_plan.get("signal"),
            entry_model=trade_plan.get("entry_model") or selected_signal_data.get("entry_model"),
            score=selected_signal_data.get("score"),
            session=session_name,
            market_condition=market_condition,
            entry=trade_plan.get("entry_price"),
            sl=trade_plan.get("stop_loss"),
            tp=trade_plan.get("take_profit"),
            rr=trade_plan.get("rr") or trade_plan.get("risk_reward"),
            required_rr=min_rr_required,
            reason="Universal confirmation engine observe-only report",
            extra=build_confirmation_engine_audit_extra(report),
        )

        return report

    except Exception as exc:
        logger.error(
            f"[CONFIRMATION ENGINE] Observe-only confirmation failed | "
            f"setup_id={selected_signal_data.get('setup_id') or trade_plan.get('setup_id')} "
            f"error={exc}"
        )
        selected_signal_data["confirmation_engine_error"] = str(exc)
        return None




def _confirmation_scope_get_first(scope, names):
    for name in names:
        if name in scope and scope.get(name) is not None:
            return scope.get(name)

    return None


def observe_universal_confirmation_from_scope(
    scope,
    *,
    setup_source_bucket_override=None,
):
    """
    Phase 1N helper.

    Generic observe-only bridge for execution paths where local variable names
    differ across intrabar/FVG/MTF/split/scalp/reversal/recovery flows.

    Must not block, alter trade_plan, alter execution, or change strategy behavior.
    """

    try:
        scope = scope or {}

        raw_selected_signal_data = _confirmation_scope_get_first(
            scope,
            [
                "selected_signal_data",
                "setup_data",
                "signal_data",
                "candidate",
                "recovery_setup",
                "scalp_signal_data",
                "reversal_signal_data",
                "split_signal_data",
                "event_signal_data",
                "intrabar_signal_data",
            ],
        )

        if isinstance(raw_selected_signal_data, dict):
            selected_signal_data = dict(raw_selected_signal_data)
        else:
            selected_signal_data = {}

        raw_trade_plan = _confirmation_scope_get_first(
            scope,
            [
                "trade_plan",
                "mtf_trade_plan",
                "scalp_trade_plan",
                "reversal_trade_plan",
                "split_trade_plan",
                "fvg_trade_plan",
                "candidate_trade_plan",
                "event_trade_plan",
                "intrabar_trade_plan",
                "immediate_trade_plan",
            ],
        )

        if isinstance(raw_trade_plan, dict):
            trade_plan = dict(raw_trade_plan)
        else:
            trade_plan = {}

        strategy_name = _confirmation_scope_get_first(
            scope,
            ["strategy_name", "strategy", "candidate_strategy", "selected_strategy"],
        )

        signal = _confirmation_scope_get_first(
            scope,
            ["signal", "candidate_signal", "selected_signal"],
        )

        setup_id = _confirmation_scope_get_first(
            scope,
            ["setup_id", "candidate_setup_id", "source_setup_id", "executed_setup_id"],
        )

        if strategy_name and not selected_signal_data.get("strategy"):
            selected_signal_data["strategy"] = strategy_name

        if signal and not selected_signal_data.get("signal"):
            selected_signal_data["signal"] = signal

        if setup_id and not selected_signal_data.get("setup_id"):
            selected_signal_data["setup_id"] = setup_id

        if setup_source_bucket_override:
            selected_signal_data.setdefault("setup_source_bucket", setup_source_bucket_override)
            selected_signal_data.setdefault("execution_bucket", setup_source_bucket_override)
            trade_plan.setdefault("setup_source_bucket", setup_source_bucket_override)
            trade_plan.setdefault("execution_bucket", setup_source_bucket_override)

        df = _confirmation_scope_get_first(
            scope,
            ["df", "df_m15", "m15_df", "df_signal", "latest_df"],
        )

        tick = _confirmation_scope_get_first(
            scope,
            ["tick", "current_tick", "symbol_tick"],
        )

        session_name = (
            _confirmation_scope_get_first(
                scope,
                ["session_name", "active_session", "session"],
            )
            or selected_signal_data.get("session")
            or trade_plan.get("session")
        )

        market_condition = (
            _confirmation_scope_get_first(
                scope,
                ["market_condition", "active_market_condition"],
            )
            or selected_signal_data.get("market_condition")
            or trade_plan.get("market_condition")
        )

        min_rr_required = _confirmation_scope_get_first(
            scope,
            ["min_rr_required", "required_rr", "candidate_required_rr"],
        )

        observe_universal_confirmation_for_setup(
            selected_signal_data=selected_signal_data,
            trade_plan=trade_plan,
            df=df,
            tick=tick,
            session_name=session_name,
            market_condition=market_condition,
            min_rr_required=min_rr_required,
            max_spread=MAX_SPREAD,
        )

    except Exception as exc:
        logger.error(
            f"[CONFIRMATION ENGINE] Scope-based observe failed safely | "
            f"bucket={setup_source_bucket_override} | error={exc}"
        )


def check_setup_outcome_memory_guard(signal_data, setup_id, strategy_name, signal, trade_plan=None):
    if not ENABLE_SETUP_OUTCOME_MEMORY_GUARD:
        return False, None

    if not signal_data:
        return False, None

    dangerous_reports = []

    memory_sources = [
        {
            "name": "similarity",
            "key": "similarity_memory",
            "dangerous_classification": "DANGEROUS_REPETITIVE_PATTERN",
        },
        {
            "name": "scenario_cluster",
            "key": "scenario_cluster_memory",
            "dangerous_classification": "DANGEROUS_CLUSTER_PATTERN",
        },
    ]

    for source in memory_sources:
        report = signal_data.get(source["key"])

        if not report:
            continue

        classification = report.get("classification")
        stats = report.get("stats", {}) or {}
        samples = int(stats.get("total", 0) or 0)

        if classification != source["dangerous_classification"]:
            continue

        if samples < MEMORY_GUARD_MIN_SAMPLES_FOR_WARNING:
            continue

        dangerous_reports.append(
            {
                "source": source["name"],
                "classification": classification,
                "samples": samples,
                "w10_rate": stats.get("w10_rate"),
                "tp_rate": stats.get("tp_rate"),
                "sl_rate": stats.get("sl_rate"),
                "avg_favorable": stats.get("avg_favorable"),
                "avg_adverse": stats.get("avg_adverse"),
                "avg_recovery_swing": stats.get("avg_recovery_swing"),
            }
        )

    if not dangerous_reports:
        return False, None

    strongest = max(
        dangerous_reports,
        key=lambda item: (
            float(item.get("sl_rate", 0) or 0),
            int(item.get("samples", 0) or 0),
        ),
    )

    reason = (
        f"memory_guard_dangerous_{strongest['source']} "
        f"classification={strongest['classification']} "
        f"samples={strongest['samples']} "
        f"w10_rate={strongest.get('w10_rate')} "
        f"tp_rate={strongest.get('tp_rate')} "
        f"sl_rate={strongest.get('sl_rate')} "
        f"avg_favorable={strongest.get('avg_favorable')} "
        f"avg_adverse={strongest.get('avg_adverse')} "
        f"avg_recovery_swing={strongest.get('avg_recovery_swing')}"
    )

    should_block = (
        MEMORY_GUARD_BLOCK_DANGEROUS_PATTERNS
        and strongest["samples"] >= MEMORY_GUARD_MIN_SAMPLES_FOR_BLOCK
    )

    logger.warning(
        f"[SETUP OUTCOME MEMORY GUARD] "
        f"setup_id={setup_id} strategy={strategy_name} signal={signal} "
        f"block={should_block} reason={reason}"
    )
    
    if not should_block and not signal_data.get("memory_guard_event_logged"):
        log_setup_event(
            setup_id=setup_id,
            event="SETUP_OUTCOME_MEMORY_GUARD_WARNING",
            strategy=strategy_name,
            signal=signal,
            entry_model=signal_data.get("entry_model") if signal_data else None,
            score=signal_data.get("score") if signal_data else None,
            session=signal_data.get("session") if signal_data else None,
            market_condition=trade_plan.get("market_condition") if trade_plan else None,
            entry=trade_plan.get("entry_price") if trade_plan else None,
            sl=trade_plan.get("stop_loss") if trade_plan else None,
            tp=trade_plan.get("take_profit") if trade_plan else None,
            reason=reason,
            extra={
                "guard": "setup_outcome_memory_guard",
                "mode": "warning_only",
                "source": strongest.get("source"),
                "classification": strongest.get("classification"),
                "samples": strongest.get("samples"),
                "w10_rate": strongest.get("w10_rate"),
                "tp_rate": strongest.get("tp_rate"),
                "sl_rate": strongest.get("sl_rate"),
                "avg_favorable": strongest.get("avg_favorable"),
                "avg_adverse": strongest.get("avg_adverse"),
                "avg_recovery_swing": strongest.get("avg_recovery_swing"),
            },
        )

        signal_data["memory_guard_event_logged"] = True

    if MEMORY_GUARD_NOTIFY_ON_WARNING and not signal_data.get("memory_guard_notified"):
        send_telegram_message(
            f"⚠️ Setup Outcome Memory Guard\n"
            f"Setup ID: {setup_id}\n"
            f"Strategy: {strategy_name}\n"
            f"Signal: {signal}\n"
            f"Mode: {'BLOCK' if should_block else 'WARNING ONLY'}\n\n"
            f"Source: {strongest['source']}\n"
            f"Classification: {strongest['classification']}\n"
            f"Samples: {strongest['samples']}\n"
            f"W10 Rate: {strongest.get('w10_rate')}\n"
            f"TP Rate: {strongest.get('tp_rate')}\n"
            f"SL Rate: {strongest.get('sl_rate')}\n"
            f"Avg Favorable: {strongest.get('avg_favorable')}\n"
            f"Avg Adverse: {strongest.get('avg_adverse')}\n"
            f"Avg Recovery Swing: {strongest.get('avg_recovery_swing')}"
        )

        signal_data["memory_guard_notified"] = True

    return should_block, reason

def save_trade_plan_memory_report(
    *,
    selected_signal_data,
    strategy_name,
    signal,
    score,
    session_name,
    market_condition,
    reason,
    trade_plan,
    decision,
    decision_reason,
    rr_value=None,
    required_rr=None,
):
    if not ENABLE_MEMORY_DECISION_REPORT:
        return False

    memory_report = build_memory_decision_report(
        setup_id=selected_signal_data.get("setup_id"),
        strategy=strategy_name,
        signal=signal,
        score=score,
        session=session_name,
        market_condition=market_condition,
        reason=reason,
        signal_data=selected_signal_data,
        trade_plan=trade_plan,
        decision=decision,
        decision_reason=decision_reason,
        extra={
            "rr": rr_value,
            "required_rr": required_rr,
            "stage": "post_trade_plan",
        },
    )

    return save_memory_decision_report(memory_report)

def save_execution_memory_report(
    *,
    selected_signal_data,
    strategy_name,
    signal,
    score,
    session_name,
    market_condition,
    reason,
    trade_plan,
    decision,
    decision_reason,
    rr_value=None,
    required_rr=None,
    execution_result=None,
    extra=None,
):
    if not ENABLE_MEMORY_DECISION_REPORT:
        return False

    extra = extra or {}

    if execution_result is not None:
        extra["execution_result"] = str(execution_result)

    memory_report = build_memory_decision_report(
        setup_id=selected_signal_data.get("setup_id"),
        strategy=strategy_name,
        signal=signal,
        score=score,
        session=session_name,
        market_condition=market_condition,
        reason=reason,
        signal_data=selected_signal_data,
        trade_plan=trade_plan,
        decision=decision,
        decision_reason=decision_reason,
        extra={
            "rr": rr_value,
            "required_rr": required_rr,
            "stage": "execution",
            **extra,
        },
    )

    return save_memory_decision_report(memory_report)

def is_trade_blocked_by_execution_memory(
    *,
    trade_plan,
    signal_data,
    setup,
    strategy_name,
    signal,
):
    setup_id = get_trade_setup_id(
        trade_plan=trade_plan,
        signal_data=signal_data,
        setup=setup,
    )
    
    memory_blocked, memory_reason = check_setup_outcome_memory_guard(
        signal_data=signal_data,
        setup_id=setup_id,
        strategy_name=strategy_name,
        signal=signal,
        trade_plan=trade_plan,
    )

    if memory_blocked:
        log_setup_event(
            setup_id=setup_id,
            event="SETUP_OUTCOME_MEMORY_GUARD_BLOCKED",
            strategy=strategy_name,
            signal=signal,
            entry_model=signal_data.get("entry_model") if signal_data else None,
            score=signal_data.get("score") if signal_data else None,
            session=signal_data.get("session") if signal_data else None,
            market_condition=trade_plan.get("market_condition") if trade_plan else None,
            entry=trade_plan.get("entry_price") if trade_plan else None,
            sl=trade_plan.get("stop_loss") if trade_plan else None,
            tp=trade_plan.get("take_profit") if trade_plan else None,
            reason=memory_reason,
            extra={
                "guard": "setup_outcome_memory_guard",
            },
        )

        return True

    blocked, block = is_setup_execution_blocked(setup_id)

    if not blocked:
        return False

    logger.warning(
        f"[EXECUTION MEMORY] Setup skipped | "
        f"setup_id={setup_id} strategy={strategy_name} signal={signal} "
        f"reason={block.get('reason')}"
    )

    send_telegram_message(
        f"⛔ Setup Skipped by Execution Memory\n"
        f"Symbol: {SYMBOL}\n"
        f"Strategy: {strategy_name}\n"
        f"Signal: {signal}\n"
        f"Setup ID: {setup_id}\n"
        f"Reason: previously blocked by {block.get('reason')}"
    )

    log_setup_event(
        setup_id=setup_id,
        event="EXECUTION_SKIPPED_PREVIOUS_HIGH_SLIPPAGE",
        strategy=strategy_name,
        signal=signal,
        reason=f"previously blocked by {block.get('reason')}",
        extra={
            "memory_block": block,
        },
    )

    if setup is not None and hasattr(execution_engine, "mark_execution_failed"):
        execution_engine.mark_execution_failed(
            setup,
            f"Skipped by execution memory: {block.get('reason')}",
        )

    return True

def apply_ai_shadow_advisor_execution_control(ai_shadow_advice):
    if not AI_SHADOW_ADVISOR_EXECUTION_CONTROL_ENABLED:
        return True, "ai_execution_control_disabled"

    if not ai_shadow_advice:
        return True, "no_ai_shadow_advice"

    mode = str(AI_SHADOW_ADVISOR_EXECUTION_CONTROL_MODE or "SHADOW_ONLY").upper()
    recommendation = str(ai_shadow_advice.get("recommendation") or "NO_ADVICE").upper()
    stats = ai_shadow_advice.get("stats", {}) or {}
    samples = int(stats.get("total", 0) or 0)

    if mode in ["SHADOW_ONLY", "WARN_ONLY"]:
        return True, f"ai_mode_{mode.lower()}"

    if samples < AI_SHADOW_ADVISOR_MIN_SAMPLES_FOR_CONTROL:
        return True, (
            f"ai_control_not_enough_samples "
            f"samples={samples} required={AI_SHADOW_ADVISOR_MIN_SAMPLES_FOR_CONTROL}"
        )

    if mode == "BLOCK_ONLY":
        if recommendation in AI_SHADOW_ADVISOR_BLOCK_RECOMMENDATIONS:
            return False, f"ai_recommendation_blocked recommendation={recommendation}"

        return True, f"ai_block_only_allowed recommendation={recommendation}"

    if mode == "REQUIRE_ALLOW":
        if recommendation in AI_SHADOW_ADVISOR_ALLOW_RECOMMENDATIONS:
            return True, f"ai_require_allow_passed recommendation={recommendation}"

        return False, f"ai_require_allow_blocked recommendation={recommendation}"

    return True, f"unknown_ai_control_mode_{mode}"

def get_strategy_selection_priority(strategy_name, market_condition):
    strategy_name = str(strategy_name or "").upper()
    market_condition = str(market_condition or "").upper()

    ranging_priority = {
        "RANGE_SWEEP_RECLAIM": 10,
        "VWAP_RANGE_MEAN_REVERSION": 9,
        "FAILED_BREAKOUT_REVERSAL": 8,
        "FAILED_FVG_REVERSAL": 7,
        "LIQUIDITY_TRAP": 7,
        "FRACTAL_SWEEP": 5,
        "VWAP_RECLAIM": 5,
        "SUPPLY_DEMAND_RETEST": 4,
        "IFVG_RETEST_CONFLUENCE": 4,
        "MTF_SR_FVG_RECLAIM": 3,
        "BREAKER_BLOCK": 3,
        "WAVETREND_PIVOT": 2,
        "FCR_M1_FVG": 2,
    }

    default_priority = {
        "HTF_TREND_PULLBACK": 5,
        "OB_FVG_COMBO": 5,
        "BREAKER_BLOCK": 4,
        "ORDER_BLOCK": 4,
        "FVG": 3,
        "FVG_CE_MITIGATION": 2,
        "LIQUIDITY_TRAP": 4,
        "FAILED_BREAKOUT_REVERSAL": 4,
        "FAILED_FVG_REVERSAL": 4,
    }

    if market_condition == "RANGING":
        return ranging_priority.get(strategy_name, 0)

    return default_priority.get(strategy_name, 0)


def get_session_selection_adjustment(session_name):
    session_name = str(session_name or "").upper()

    if session_name == "OFF_HOURS":
        return -6

    if session_name == "ASIA":
        return -2

    if session_name in ["LONDON_OPEN", "LONDON"]:
        return 3

    if session_name in ["NEWYORK_OPEN", "LONDON_NY_OVERLAP"]:
        return 4

    if session_name == "NEWYORK":
        return 3

    if session_name == "NEWYORK_LATE":
        return 1

    # Backward compatibility with old labels
    if session_name in ["LONDON_NEWYORK", "NY_OVERLAP"]:
        return 4

    return 0

def register_rejected_candidate_setup_outcome(
    *,
    candidate,
    rejection_reason,
    df,
    tick,
    account_info,
    market_condition,
    session_name,
    setup_id=None,
):
    signal = candidate.get("signal")
    strategy_name = candidate.get("strategy")

    if signal not in ["BUY", "SELL"]:
        return False

    # Avoid duplicate tracking because MTF conflicts already use MTF_CONFLICT_CANDIDATE_TRACKED
    if is_mtf_conflict_rejection(rejection_reason):
        return False

    trade_plan = calculate_trade_plan(
        df=df,
        signal=signal,
        tick=tick,
        account_balance=account_info.balance,
        signal_data=candidate,
    )

    if trade_plan is None:
        logger.info(
            f"[SETUP OUTCOME] Generic rejected candidate not tracked | "
            f"strategy={strategy_name} signal={signal} "
            f"reason={rejection_reason} trade_plan=None"
        )
        return False

    rr_value = calculate_rr_value(trade_plan)

    required_rr = get_min_rr(
        strategy_name,
        candidate.get("entry_model"),
        candidate.get("sl_model"),
    )

    setup_id = setup_id or candidate.get("setup_id") or build_stable_candidate_setup_id(
        candidate=candidate,
        strategy_name=strategy_name,
        signal=signal,
        tick_time=tick.time,
    )
    
    candidate["setup_id"] = setup_id
    candidate["rejected_trade_plan"] = trade_plan
    candidate["rejected_rr_value"] = rr_value
    candidate["rejected_required_rr"] = required_rr

    return register_setup_outcome(
        symbol=SYMBOL,
        setup_id=setup_id,
        event="CANDIDATE_REJECTED",
        strategy=strategy_name,
        signal=signal,
        entry_model=candidate.get("entry_model"),
        score=candidate.get("score"),
        session=session_name,
        market_condition=market_condition,
        entry=trade_plan.get("entry_price"),
        sl=trade_plan.get("stop_loss"),
        tp=trade_plan.get("take_profit"),
        reason=rejection_reason,
        extra={
            "rr": rr_value,
            "required_rr": required_rr,
            "source": "candidate_rejected_with_calculated_trade_plan",
        },
    )


def _telegram_tp123_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _telegram_tp123_round(value, digits=2):
    numeric = _telegram_tp123_float(value)
    if numeric is None:
        return value
    return round(numeric, digits)


def _format_telegram_tp123_from_levels(signal, entry, sl, tp):
    entry_value = _telegram_tp123_float(entry)
    sl_value = _telegram_tp123_float(sl)
    tp_value = _telegram_tp123_float(tp)

    if entry_value is None or sl_value is None or tp_value is None:
        return f"TP: {_telegram_tp123_round(tp)}"

    risk = abs(entry_value - sl_value)

    if risk <= 0:
        return f"TP: {_telegram_tp123_round(tp_value)}"

    # Visual TP plan only. This does not change execution.
    tp1 = entry_value + ((tp_value - entry_value) * 0.50)
    tp2 = entry_value + ((tp_value - entry_value) * 0.75)
    tp3 = tp_value

    def stage_rr(price):
        return round(abs(entry_value - price) / risk, 2)

    return "\n".join(
        [
            "TP Plan:",
            f"TP1: {_telegram_tp123_round(tp1)} | RR {stage_rr(tp1)}",
            f"TP2: {_telegram_tp123_round(tp2)} | RR {stage_rr(tp2)}",
            f"TP3: {_telegram_tp123_round(tp3)} | RR {stage_rr(tp3)}",
        ]
    )


def _format_telegram_tp123_from_trade_plan(signal, trade_plan):
    trade_plan = trade_plan or {}

    ladder = trade_plan.get("tp_ladder")

    if isinstance(ladder, list) and ladder:
        lines = ["TP Plan:"]

        for index, item in enumerate(ladder, start=1):
            price = item.get("price") or item.get("take_profit")
            stage_rr = item.get("rr") or item.get("execution_tp_stage_rr")
            name = item.get("name")
            suffix = f" | {name}" if name else ""

            lines.append(
                f"TP{index}: {_telegram_tp123_round(price)} | RR {stage_rr}{suffix}"
            )

        return "\n".join(lines)

    return _format_telegram_tp123_from_levels(
        signal=signal,
        entry=trade_plan.get("entry_price"),
        sl=trade_plan.get("stop_loss"),
        tp=trade_plan.get("take_profit"),
    )


def notify_rejected_candidate_if_relevant(
    *,
    setup_id,
    strategy,
    signal,
    entry_model,
    session_name,
    market_condition,
    score,
    rr,
    entry,
    sl,
    tp,
    reason,
):
    if not TELEGRAM_NOTIFY_REJECTED_CANDIDATE_TRACKED:
        return

    try:
        score_value = float(score or 0)
    except Exception:
        score_value = 0.0

    try:
        rr_value = float(rr or 0)
    except Exception:
        rr_value = 0.0

    strong_rejected_candidate = (
        score_value >= REJECTED_CANDIDATE_TELEGRAM_MIN_SCORE
        or rr_value >= REJECTED_CANDIDATE_TELEGRAM_MIN_RR
    )

    if not strong_rejected_candidate:
        return

    now_ts = time.time()
    cooldown_seconds = REJECTED_CANDIDATE_TELEGRAM_COOLDOWN_MINUTES * 60

    alert_key = (
        strategy,
        signal,
        entry_model,
        session_name,
        market_condition,
        reason,
    )

    last_sent_ts = _REJECTED_CANDIDATE_TELEGRAM_CACHE.get(alert_key, 0)

    if now_ts - last_sent_ts < cooldown_seconds:
        logger.info(
            f"[REJECTED CANDIDATE] Telegram skipped by cooldown | "
            f"key={alert_key}"
        )
        return

    _REJECTED_CANDIDATE_TELEGRAM_CACHE[alert_key] = now_ts

    send_telegram_message_async(
        "📌 STRONG REJECTED CANDIDATE TRACKED\n"
        f"Setup ID: {setup_id}\n"
        f"Strategy: {strategy}\n"
        f"Signal: {signal}\n"
        f"Entry Model: {entry_model}\n"
        f"Session: {session_name}\n"
        f"Market: {market_condition}\n"
        f"Score: {score_value}\n"
        f"RR: {rr_value}\n\n"
        f"Entry: {entry}\n"
        f"SL: {sl}\n"
        f"{_format_telegram_tp123_from_levels(signal, entry, sl, tp)}\n\n"
        f"Reason: {reason}\n"
        "Action: tracked only — use statistics before changing execution rules."
    )

def calculate_candidate_selection_rank(
    candidate,
    rr_value,
    min_rr_required,
    market_condition,
):
    score = candidate.get("score", 0)
    strategy_name = candidate.get("strategy")
    session_name = candidate.get("session")

    strategy_priority = get_strategy_selection_priority(
        strategy_name,
        market_condition,
    )

    session_adjustment = get_session_selection_adjustment(session_name)

    rr_extra = max(rr_value - min_rr_required, 0)
    rr_bonus = min(rr_extra * 8, 12)

    final_rank = round(
        score + rr_bonus + strategy_priority + session_adjustment,
        2,
    )

    return final_rank, {
        "score": score,
        "rr": rr_value,
        "required_rr": min_rr_required,
        "rr_bonus": round(rr_bonus, 2),
        "strategy_priority": strategy_priority,
        "session_adjustment": session_adjustment,
        "final_rank": final_rank,
    }

def try_build_rejected_candidate_trade_plan(
    *,
    df,
    tick,
    account_info,
    candidate,
    candidate_strategy,
    candidate_signal,
    session_name,
    market_condition,
    rejection_reason,
):
    if not ENABLE_GENERIC_REJECTED_CANDIDATE_TRADE_PLAN:
        return None, None

    if candidate_signal not in ["BUY", "SELL"]:
        return None, None

    candidate["strategy"] = candidate_strategy
    candidate["signal"] = candidate_signal
    candidate["session"] = candidate.get("session", session_name)
    candidate["market_condition"] = candidate.get("market_condition", market_condition)

    trade_plan = calculate_trade_plan(
        df=df,
        signal=candidate_signal,
        tick=tick,
        account_balance=account_info.balance,
        signal_data=candidate,
    )

    if trade_plan is None:
        return None, "rejected_candidate_trade_plan_failed"

    trade_plan["strategy"] = candidate_strategy
    trade_plan["signal"] = candidate_signal
    trade_plan["score"] = candidate.get("score")
    trade_plan["session"] = candidate.get("session", session_name)
    trade_plan["market_condition"] = candidate.get("market_condition", market_condition)
    trade_plan["setup_id"] = candidate.get("setup_id", "N/A")
    trade_plan["reason"] = (
        f"{candidate.get('reason', 'N/A')} | "
        f"rejected_candidate_recovery_source={rejection_reason}"
    )

    rr_value = calculate_rr_value(trade_plan)

    return trade_plan, rr_value

def handle_generic_rejected_candidate_trade_plan(
    *,
    df,
    tick,
    account_info,
    candidate,
    candidate_strategy,
    candidate_signal,
    session_name,
    market_condition,
    rejection_reason,
    news_context=None,
):
    if rejection_reason == "low_rr":
        return False
    
    if is_mtf_conflict_rejection(rejection_reason):
        return False

    if not ENABLE_GENERIC_REJECTED_CANDIDATE_TRADE_PLAN:
        return False

    candidate_trade_plan, candidate_rr = try_build_rejected_candidate_trade_plan(
        df=df,
        tick=tick,
        account_info=account_info,
        candidate=candidate,
        candidate_strategy=candidate_strategy,
        candidate_signal=candidate_signal,
        session_name=session_name,
        market_condition=market_condition,
        rejection_reason=rejection_reason,
    )

    if candidate_trade_plan is None:
        save_trade_plan_memory_report(
            selected_signal_data=candidate,
            strategy_name=candidate_strategy,
            signal=candidate_signal,
            score=candidate.get("score"),
            session_name=session_name,
            market_condition=market_condition,
            reason=rejection_reason,
            trade_plan=None,
            decision="CANDIDATE_REJECTED_TRADE_PLAN_FAILED",
            decision_reason="generic rejected candidate trade plan could not be calculated",
        )

        return False
    
    candidate_required_rr = get_min_rr(
        candidate_strategy,
        candidate.get("entry_model"),
        candidate_trade_plan.get("sl_model") or candidate.get("sl_model"),
    )

    save_trade_plan_memory_report(
        selected_signal_data=candidate,
        strategy_name=candidate_strategy,
        signal=candidate_signal,
        score=candidate.get("score"),
        session_name=session_name,
        market_condition=market_condition,
        reason=rejection_reason,
        trade_plan=candidate_trade_plan,
        decision="CANDIDATE_REJECTED_WITH_TRADE_PLAN",
        decision_reason="generic rejected candidate trade plan calculated for recovery tracking",
        rr_value=candidate_rr,
        required_rr=candidate_required_rr,
    )

    log_setup_event(
        setup_id=candidate.get("setup_id"),
        event="CANDIDATE_REJECTED_WITH_TRADE_PLAN",
        strategy=candidate_strategy,
        signal=candidate_signal,
        entry_model=candidate.get("entry_model"),
        score=candidate.get("score"),
        session=session_name,
        market_condition=market_condition,
        entry=candidate_trade_plan.get("entry_price"),
        sl=candidate_trade_plan.get("stop_loss"),
        tp=candidate_trade_plan.get("take_profit"),
        rr=candidate_rr,
        required_rr=candidate_required_rr,
        reason=rejection_reason,
        extra={
            "source": "generic_rejected_candidate_trade_plan",
            "news_context": news_context,
            "news_tag": news_context.get("news_tag") if news_context else None,
            "candidate_reason": candidate.get("reason"),
            "rejection_reason": rejection_reason,
        },
    )

    return register_generic_rejected_candidate_recovery_if_eligible(
        candidate=candidate,
        candidate_strategy=candidate_strategy,
        candidate_signal=candidate_signal,
        trade_plan=candidate_trade_plan,
        rr_value=candidate_rr,
        min_rr_required=candidate_required_rr,
        rejection_reason=rejection_reason,
        session_name=session_name,
        market_condition=market_condition,
        news_context=news_context,
    )

def register_generic_rejected_candidate_recovery_if_eligible(
    *,
    candidate,
    candidate_strategy,
    candidate_signal,
    trade_plan,
    rr_value,
    min_rr_required,
    rejection_reason,
    session_name,
    market_condition,
    news_context=None,
):
    if trade_plan is None:
        return False

    if rr_value is None:
        return False

    if rr_value < GENERIC_REJECTED_CANDIDATE_MIN_RR_TO_TRACK:
        return False

    recovery_reason = str(rejection_reason or "").lower()

    eligible_reason = any(
        allowed_reason in recovery_reason
        for allowed_reason in GENERIC_REJECTED_CANDIDATE_RECOVERY_REASONS
    )

    if not eligible_reason:
        return False

    candidate["rejected_trade_plan"] = {
        "entry_price": trade_plan.get("entry_price"),
        "stop_loss": trade_plan.get("stop_loss"),
        "take_profit": trade_plan.get("take_profit"),
        "lot": trade_plan.get("lot"),
        "rr": rr_value,
        "required_rr": min_rr_required,
        "reason": trade_plan.get("reason"),
    }

    candidate["recovery_source"] = "generic_rejected_candidate"
    candidate["recovery_reason_type"] = rejection_reason
    candidate["session"] = candidate.get("session", session_name)
    candidate["market_condition"] = candidate.get("market_condition", market_condition)

    recovery_id = register_rejected_candidate_for_recovery(
        symbol=SYMBOL,
        signal=candidate_signal,
        strategy=candidate_strategy,
        score=candidate.get("score"),
        reason_type="generic_rejected_candidate",
        rejection_reason=rejection_reason,
        signal_data=candidate,
        required_rr=min_rr_required,
        current_rr=rr_value,
    )

    logger.info(
        f"[GENERIC REJECTED RECOVERY] Registered | "
        f"recovery_id={recovery_id} "
        f"setup_id={candidate.get('setup_id')} "
        f"strategy={candidate_strategy} signal={candidate_signal} "
        f"rr={rr_value} required={min_rr_required} "
        f"reason={rejection_reason}"
    )
    
    if GENERIC_REJECTED_CANDIDATE_NOTIFY_TELEGRAM:
        send_telegram_message(
            f"⚠️ Generic Rejected Candidate Tracked\n"
            f"Symbol: {SYMBOL}\n"
            f"Strategy: {candidate_strategy}\n"
            f"Signal: {candidate_signal}\n"
            f"Setup ID: {candidate.get('setup_id', 'N/A')}\n"
            f"Entry Model: {candidate.get('entry_model')}\n"
            f"Reason: {rejection_reason}\n"
            f"Candidate Reason: {candidate.get('reason', 'N/A')}\n\n"
            f"Entry: {trade_plan.get('entry_price')}\n"
            f"SL: {trade_plan.get('stop_loss')}\n"
            f"{_format_telegram_tp123_from_trade_plan(candidate_signal, trade_plan)}\n"
            f"RR: {rr_value} / Required: {min_rr_required}\n\n"
            f"Action: moved to generic rejected candidate recovery if eligible."
        )

    return True

def extra_entry_confirmation_ok(signal):
    if not REQUIRE_M5_CONFIRMATION_FOR_EXTRA:
        return True, "extra_confirmation_disabled"

    rates = mt5.copy_rates_from_pos(
        SYMBOL,
        EXTRA_ENTRY_CONFIRMATION_TIMEFRAME,
        0,
        EXTRA_ENTRY_CONFIRMATION_BARS,
    )

    if rates is None or len(rates) < 10:
        return False, "no_m5_confirmation_data"

    confirm_df = pd.DataFrame(rates)
    confirm_df["time"] = pd.to_datetime(confirm_df["time"], unit="s")
    confirm_df["ema_20"] = calculate_ema(confirm_df, EMA_PERIOD)
    confirm_df["atr_14"] = calculate_atr(confirm_df, ATR_PERIOD)

    candle = confirm_df.iloc[-2]
    prev = confirm_df.iloc[-3]

    atr = candle["atr_14"]
    body = abs(candle["close"] - candle["open"])

    if atr <= 0:
        return False, "invalid_m5_atr"

    if body < atr * EXTRA_ENTRY_MIN_BODY_ATR:
        return False, "m5_body_too_small"

    if signal == "BUY":
        confirmed = (
            candle["close"] > candle["open"]
            and candle["close"] > candle["ema_20"]
            and (
                candle["close"] > prev["high"]
                or candle["close"] >= candle["low"] + (candle["high"] - candle["low"]) * 0.60
            )
        )

        if confirmed:
            return True, "m5_buy_confirmation"

        return False, "m5_buy_not_confirmed"

    if signal == "SELL":
        confirmed = (
            candle["close"] < candle["open"]
            and candle["close"] < candle["ema_20"]
            and (
                candle["close"] < prev["low"]
                or candle["close"] <= candle["high"] - (candle["high"] - candle["low"]) * 0.60
            )
        )

        if confirmed:
            return True, "m5_sell_confirmation"

        return False, "m5_sell_not_confirmed"

    return False, "invalid_signal"

def retry_entry_is_equal_or_better(signal, tick, expected_entry):
    if expected_entry is None:
        return True, None, None

    expected_entry = float(expected_entry)

    if signal == "BUY":
        current_price = float(tick.ask)
        improvement = expected_entry - current_price

        if current_price <= expected_entry:
            return True, current_price, round(improvement, 2)

        return False, current_price, round(improvement, 2)

    if signal == "SELL":
        current_price = float(tick.bid)
        improvement = current_price - expected_entry

        if current_price >= expected_entry:
            return True, current_price, round(improvement, 2)

        return False, current_price, round(improvement, 2)

    return False, None, None

def split_lot_for_delayed_entry(symbol, total_lot, immediate_pct):
    symbol_info = mt5.symbol_info(symbol)

    if symbol_info is None:
        return total_lot, 0.0

    min_volume = symbol_info.volume_min
    step = symbol_info.volume_step

    def round_volume(volume):
        rounded = round(round(volume / step) * step, 2)
        return max(rounded, 0.0)

    immediate_lot = round_volume(total_lot * immediate_pct)
    delayed_lot = round_volume(total_lot - immediate_lot)

    if immediate_lot < min_volume:
        return total_lot, 0.0

    if delayed_lot < min_volume:
        return total_lot, 0.0

    return immediate_lot, delayed_lot

def get_delayed_entry_offset(market_condition):
    return DELAYED_ENTRY_OFFSET_BY_MARKET.get(
        market_condition,
        DELAYED_ENTRY_OFFSET_PRICE,
    )


def fetch_delayed_confirmation_data():
    rates = mt5.copy_rates_from_pos(
        SYMBOL,
        DELAYED_ENTRY_CONFIRMATION_TIMEFRAME,
        0,
        DELAYED_ENTRY_CONFIRMATION_BARS,
    )

    if rates is None or len(rates) < 10:
        return None

    confirm_df = pd.DataFrame(rates)
    confirm_df["time"] = pd.to_datetime(confirm_df["time"], unit="s")
    confirm_df["ema_20"] = calculate_ema(confirm_df, EMA_PERIOD)
    confirm_df["atr_14"] = calculate_atr(confirm_df, ATR_PERIOD)

    return confirm_df


def delayed_entry_confirmation_ok(signal, target_entry):
    if not ENABLE_DELAYED_ENTRY_CONFIRMATION:
        return True, "confirmation_disabled"

    confirm_df = fetch_delayed_confirmation_data()

    if confirm_df is None:
        return False, "no_confirmation_data"

    candle = confirm_df.iloc[-2]
    prev = confirm_df.iloc[-3]

    atr = candle["atr_14"]
    body = abs(candle["close"] - candle["open"])

    if atr <= 0:
        return False, "invalid_confirmation_atr"

    if body < atr * DELAYED_ENTRY_MIN_BODY_ATR:
        return False, "confirmation_body_too_small"

    buffer = DELAYED_ENTRY_CONFIRMATION_BUFFER_PRICE

    if signal == "BUY":
        touched_target = candle["low"] <= target_entry + buffer
        bullish_confirmation = (
            candle["close"] > candle["open"]
            and (
                candle["close"] > target_entry
                or candle["close"] > prev["high"]
            )
        )

        if touched_target and bullish_confirmation:
            return True, "m1_bullish_reclaim"

        return False, "m1_bullish_reclaim_not_confirmed"

    if signal == "SELL":
        touched_target = candle["high"] >= target_entry - buffer
        bearish_confirmation = (
            candle["close"] < candle["open"]
            and (
                candle["close"] < target_entry
                or candle["close"] < prev["low"]
            )
        )

        if touched_target and bearish_confirmation:
            return True, "m1_bearish_rejection"

        return False, "m1_bearish_rejection_not_confirmed"

    return False, "invalid_signal"

def get_scalp_sl_reference(df, signal, entry_price, signal_data):
    signal_candle = df.iloc[-2]
    prev_candle = df.iloc[-3]
    atr = signal_candle["atr_14"]

    buffer = max(atr * 0.15, 1.0)
    strategy = signal_data.get("strategy")

    if signal == "SELL":
        raw_levels = []

        for key in [
            "fvg_top",
            "failed_fvg_top",
            "relief_high",
            "liquidity_high",
            "sweep_high",
            "zone_high",
            "ob_high",
            "recent_high",
        ]:
            value = signal_data.get(key)
            if value is not None:
                raw_levels.append(float(value))

        raw_levels.append(max(signal_candle["high"], prev_candle["high"]))

        valid_sl_candidates = [
            round(level + buffer, 2)
            for level in raw_levels
            if level + buffer > entry_price
        ]

        if not valid_sl_candidates:
            return None, None

        # Closest valid SL above entry
        sl_reference = min(valid_sl_candidates)
        return sl_reference, "SCALP_MICRO_STRUCTURE_SL"

    if signal == "BUY":
        raw_levels = []

        for key in [
            "fvg_bottom",
            "failed_fvg_bottom",
            "relief_low",
            "liquidity_low",
            "sweep_low",
            "zone_low",
            "ob_low",
            "recent_low",
        ]:
            value = signal_data.get(key)
            if value is not None:
                raw_levels.append(float(value))

        raw_levels.append(min(signal_candle["low"], prev_candle["low"]))

        valid_sl_candidates = [
            round(level - buffer, 2)
            for level in raw_levels
            if level - buffer < entry_price
        ]

        if not valid_sl_candidates:
            return None, None

        # Closest valid SL below entry
        sl_reference = max(valid_sl_candidates)
        return sl_reference, "SCALP_MICRO_STRUCTURE_SL"

    return None, None

def attach_news_context_to_signal_data(signal_data):
    news_context = get_active_news_context()

    if news_context and signal_data is not None:
        signal_data["news_context"] = news_context
        signal_data["news_tag"] = news_context.get("news_tag")

    return news_context

def try_build_scalp_trade_plan(
    df,
    tick,
    account_info,
    signal,
    strategy_name,
    selected_signal_data,
    normal_trade_plan,
):
    if not ENABLE_SCALP_MODE:
        return None

    if strategy_name not in SCALP_STRATEGIES:
        return None

    if selected_signal_data.get("score", 0) < SCALP_MIN_SCORE:
        return None

    if normal_trade_plan is None:
        return None

    entry_price = tick.ask if signal == "BUY" else tick.bid
    normal_tp = normal_trade_plan.get("take_profit")

    if normal_tp is None:
        return None

    # =========================
    # Fixed scalp SL / capped TP
    # =========================
    if signal == "BUY":
        raw_target_distance = normal_tp - entry_price

        if raw_target_distance <= 0:
            return None

        target_distance = min(raw_target_distance, SCALP_MAX_TARGET_DISTANCE)

        if target_distance < SCALP_MIN_TARGET_DISTANCE:
            return None

        stop_loss = entry_price - SCALP_FIXED_STOP_DISTANCE
        take_profit = entry_price + target_distance

    elif signal == "SELL":
        raw_target_distance = entry_price - normal_tp

        if raw_target_distance <= 0:
            return None

        target_distance = min(raw_target_distance, SCALP_MAX_TARGET_DISTANCE)

        if target_distance < SCALP_MIN_TARGET_DISTANCE:
            return None

        stop_loss = entry_price + SCALP_FIXED_STOP_DISTANCE
        take_profit = entry_price - target_distance

    else:
        return None

    scalp_trade_plan = normal_trade_plan.copy()

    scalp_trade_plan["entry_price"] = round(entry_price, 2)
    scalp_trade_plan["stop_loss"] = round(stop_loss, 2)
    scalp_trade_plan["take_profit"] = round(take_profit, 2)
    scalp_trade_plan["stop_distance"] = round(SCALP_FIXED_STOP_DISTANCE, 2)

    scalp_trade_plan["strategy"] = strategy_name
    scalp_trade_plan["score"] = selected_signal_data.get("score", 0)
    scalp_trade_plan["entry_model"] = (
        f"{selected_signal_data.get('entry_model', 'N/A')}_SCALP"
    )

    scalp_trade_plan["is_scalp"] = True
    scalp_trade_plan["scalp_sl_model"] = "FIXED_SCALP_STOP"
    scalp_trade_plan["scalp_stop_distance"] = SCALP_FIXED_STOP_DISTANCE
    scalp_trade_plan["scalp_target_distance"] = round(target_distance, 2)

    scalp_rr = calculate_rr_value(scalp_trade_plan)

    if scalp_rr is None or scalp_rr < SCALP_MIN_RR:
        return None

    scalp_trade_plan["scalp_rr"] = scalp_rr

    scalp_trade_plan["reason"] = (
        f"{normal_trade_plan.get('reason', selected_signal_data.get('reason', 'N/A'))} "
        f"| SCALP_MODE: fixed SL={SCALP_FIXED_STOP_DISTANCE}, "
        f"target={round(target_distance, 2)}"
    )

    return scalp_trade_plan

def build_setup_id(strategy_name, signal, tick_time):
    prefix = (strategy_name or "UNK")[:3].upper()
    return f"{prefix}-{signal}-{int(tick_time)}"


def _stable_setup_value(value):
    if value is None:
        return None

    try:
        return round(float(value), 2)
    except Exception:
        return str(value)

def _parse_hhmm_time(value):
    hour, minute = str(value).split(":")
    return int(hour), int(minute)


def _time_in_hhmm_window(current_time, start_hhmm, end_hhmm):
    start_hour, start_minute = _parse_hhmm_time(start_hhmm)
    end_hour, end_minute = _parse_hhmm_time(end_hhmm)

    current_minutes = current_time.hour * 60 + current_time.minute
    start_minutes = start_hour * 60 + start_minute
    end_minutes = end_hour * 60 + end_minute

    if start_minutes <= end_minutes:
        return start_minutes <= current_minutes < end_minutes

    return current_minutes >= start_minutes or current_minutes < end_minutes


def opening_strategy_blackout_blocks(strategy_name, current_time):
    if not ENABLE_OPENING_STRATEGY_BLACKOUT:
        return False, None

    strategy_key = str(strategy_name or "").upper()

    if strategy_key not in OPENING_STRATEGY_BLACKOUT_STRATEGIES:
        return False, None

    if not _time_in_hhmm_window(
        current_time,
        OPENING_STRATEGY_BLACKOUT_START,
        OPENING_STRATEGY_BLACKOUT_END,
    ):
        return False, None

    return (
        True,
        f"opening_blackout strategy={strategy_key} "
        f"window={OPENING_STRATEGY_BLACKOUT_START}-{OPENING_STRATEGY_BLACKOUT_END}",
    )

def build_stable_candidate_setup_id(candidate, strategy_name, signal, tick_time):
    strategy_key = str(strategy_name or candidate.get("strategy") or "SETUP").upper()
    signal_key = str(signal or candidate.get("signal") or "NA").upper()

    identity_keys = [
        "entry_model",
        "target_model",

        # ORB / session range
        "orb_high",
        "orb_low",
        "orb_range",
        "range_high",
        "range_low",
        "breakout_level",

        # FVG / IFVG
        "fvg_top",
        "fvg_bottom",
        "fvg_mid",
        "ifvg_top",
        "ifvg_bottom",
        "ifvg_mid",
        "failed_fvg_top",
        "failed_fvg_bottom",
        "failed_fvg_mid",

        # Structure / sweep / reversal
        "support",
        "resistance",
        "recent_high",
        "recent_low",
        "sweep_high",
        "sweep_low",
        "failed_breakout_level",
        "neckline",
        "neckline_price",

        # Final references
        "sl_reference",
        "tp_reference",
        "stop_loss",
        "take_profit",
    ]

    parts = []

    for key in identity_keys:
        value = _stable_setup_value(candidate.get(key))

        if value is not None:
            parts.append(f"{key}={value}")

    if len(parts) < 2:
        existing_setup_id = candidate.get("setup_id")

        if existing_setup_id:
            return existing_setup_id

        return build_setup_id(strategy_key, signal_key, tick_time)

    raw = f"{strategy_key}|{signal_key}|" + "|".join(parts)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    prefix = strategy_key.split("_")[0][:3]

    return f"{prefix}-{signal_key}-{digest}"

def build_structural_execution_key(signal_data, strategy_name, signal):
    strategy_key = str(strategy_name or signal_data.get("strategy") or "SETUP").upper()
    signal_key = str(signal or signal_data.get("signal") or "NA").upper()

    identity_keys = [
        "entry_model",
        "target_model",

        # ORB / ORB_V00
        "orb_high",
        "orb_low",

        # FVG / IFVG
        "fvg_top",
        "fvg_bottom",
        "fvg_mid",
        "ifvg_top",
        "ifvg_bottom",
        "ifvg_mid",

        # OB / structure
        "ob_high",
        "ob_low",
        "breaker_high",
        "breaker_low",

        # Risk references
        "sl_reference",
        "tp_reference",
    ]

    parts = [strategy_key, signal_key]

    for key in identity_keys:
        value = signal_data.get(key)
        normalized = _stable_setup_value(value)

        if normalized is not None:
            parts.append(f"{key}={normalized}")

    raw = "|".join(str(part) for part in parts)

    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:14]

    return f"{strategy_key}-{signal_key}-{digest}"


def attach_structural_execution_key(setup, signal_data, strategy_name, signal):
    structural_key = build_structural_execution_key(
        signal_data=signal_data,
        strategy_name=strategy_name,
        signal=signal,
    )

    signal_data["structural_execution_key"] = structural_key

    if setup is not None:
        setup["structural_execution_key"] = structural_key
        setup.setdefault("data", {})
        setup["data"]["structural_execution_key"] = structural_key

    return structural_key


def is_structural_execution_locked(structural_key, current_setup=None):
    if not structural_key:
        return False, None, None

    locked_states = {
        "WAITING",
        "READY",
        "WAIT_BETTER_ENTRY",
        "WAIT_DELAYED_ENTRY",
        "WAIT_FVG_STAGED_ENTRY",
        "WAIT_ORB_TICK_BREAKOUT",
        "WAIT_TICK_SNIPER",
        "EXECUTED",
    }

    for setup in execution_engine.active_setups:
        if current_setup is not None and setup is current_setup:
            continue

        if setup.get("state") not in locked_states:
            continue

        setup_data = setup.get("data", {})
        existing_key = (
            setup.get("structural_execution_key")
            or setup_data.get("structural_execution_key")
        )

        if existing_key != structural_key:
            continue

        return True, setup.get("state"), setup_data.get("setup_id")

    return False, None, None

def is_setup_id_already_active(setup_id):
    if not setup_id or setup_id == "N/A":
        return False, None

    active_states = {
        "WAITING",
        "READY",
        "WAIT_BETTER_ENTRY",
        "WAIT_DELAYED_ENTRY",
        "WAIT_FVG_STAGED_ENTRY",
        "WAIT_ORB_TICK_BREAKOUT",
        "WAIT_TICK_SNIPER",
        "EXECUTED",
    }

    for setup in execution_engine.active_setups:
        setup_data = setup.get("data", {})

        if setup_data.get("setup_id") != setup_id:
            continue

        setup_state = setup.get("state")

        if setup_state in active_states:
            return True, setup_state

    return False, None

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

        soft_smc_allowed = (
            ENABLE_SOFT_SMC_FOR_STRONG_SETUPS
            and setup_strategy in SOFT_SMC_STRATEGIES
            and setup_data.get("score", 0) >= SOFT_SMC_MIN_SCORE
        )

        if not smc_check["confirmed"] and not soft_smc_allowed:
            rejected_reasons.append(
                f"{setup_strategy}:{setup_signal}:smc_failed"
            )
            
            register_rejected_candidate_for_recovery(
                symbol=SYMBOL,
                signal=setup_signal,
                strategy=setup_strategy,
                score=setup_data.get("score", 0),
                reason_type="SMC_FAILED",
                rejection_reason="smc_failed",
                signal_data=setup_data,
            )
            
            continue

        if not smc_check["confirmed"] and soft_smc_allowed:
            setup_data.setdefault("smc", [])
            setup_data["smc"].append("soft_smc_pass")
            setup_data["reason"] = (
                f"{setup_data.get('reason', 'N/A')} | "
                f"SOFT_SMC_PASS: score={setup_data.get('score', 0)}"
            )

            smc_check = {
                "confirmed": True,
                "reasons": ["soft_smc_pass"],
            }

        return setup, smc_check, rejected_reasons

    return None, None, rejected_reasons

def calculate_simple_rr(signal, entry, sl, tp):
    try:
        entry = float(entry)
        sl = float(sl)
        tp = float(tp)

        if signal == "BUY":
            risk = entry - sl
            reward = tp - entry
        elif signal == "SELL":
            risk = sl - entry
            reward = entry - tp
        else:
            return None

        if risk <= 0 or reward <= 0:
            return None

        return round(reward / risk, 2)

    except Exception:
        return None


def get_setup_rr_value(setup_data, signal):
    rr = (
        setup_data.get("rr")
        or setup_data.get("risk_reward")
        or setup_data.get("rr_value")
    )

    if rr is not None:
        try:
            return float(rr)
        except Exception:
            pass

    entry = (
        setup_data.get("entry_price")
        or setup_data.get("entry")
    )
    sl = (
        setup_data.get("stop_loss")
        or setup_data.get("sl")
    )
    tp = (
        setup_data.get("take_profit")
        or setup_data.get("tp")
    )

    return calculate_simple_rr(signal, entry, sl, tp)


def final_htf_liquidity_soft_override_allowed(
    *,
    setup_strategy,
    setup_signal,
    setup_score,
    setup_data,
    session_name,
    liquidity_context,
):
    if not ENABLE_FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE:
        return False, "disabled"

    strategy_key = str(setup_strategy or "").upper()

    if strategy_key not in FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_STRATEGIES:
        return False, "strategy_not_allowed"

    try:
        score = float(setup_score or 0)
    except Exception:
        score = 0

    if score < FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_MIN_SCORE:
        return False, "score_too_low"

    entry_model = str(setup_data.get("entry_model", "") or "").upper()

    if FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_ENTRY_KEYWORDS:
        if not any(
            keyword.upper() in entry_model
            for keyword in FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_ENTRY_KEYWORDS
        ):
            return False, "entry_model_not_allowed"

    active_session = str(
        setup_data.get("session")
        or session_name
        or ""
    ).upper()

    if FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_SESSIONS:
        if active_session not in FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_SESSIONS:
            return False, "session_not_allowed"

    rr_value = get_setup_rr_value(setup_data, setup_signal)

    if rr_value is None:
        return False, "rr_missing"

    if rr_value < FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_MIN_RR:
        return False, f"rr_too_low {rr_value}"

    liquidity_reason = (
        liquidity_context.get("reason")
        if liquidity_context
        else "N/A"
    )

    return True, f"score={score} rr={rr_value} reason={liquidity_reason}"

def get_confluence_family_key(strategy_name):
    strategy_key = str(strategy_name or "UNKNOWN").upper()

    for index, group in enumerate(CONFLUENCE_DUPLICATE_STRATEGY_GROUPS):
        normalized_group = [str(item).upper() for item in group]

        if strategy_key in normalized_group:
            return f"DUPLICATE_GROUP_{index}"

    return strategy_key


def build_deduplicated_confluence_strategies(candidate, top_candidates):
    signal = candidate.get("signal")

    ordered_candidates = [candidate] + [
        item for item in top_candidates
        if item.get("signal") == signal
    ]

    seen_families = set()
    confluence_strategies = []

    for item in ordered_candidates:
        strategy_name = item.get("strategy", "UNKNOWN")
        family_key = get_confluence_family_key(strategy_name)

        if family_key in seen_families:
            continue

        seen_families.add(family_key)
        confluence_strategies.append(strategy_name)

    return confluence_strategies

def apply_candidate_confluence(candidate, top_candidates):
    if not ENABLE_SIGNAL_CONFLUENCE_GROUPING:
        return candidate

    signal = candidate.get("signal")

    confluence_strategies = build_deduplicated_confluence_strategies(
        candidate=candidate,
        top_candidates=top_candidates,
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

def has_elliott_fib_directional_conflict(signal, signal_data):
    reason = str(signal_data.get("reason", "") or "").lower()

    if signal == "BUY" and "elliott_fib_conflict_sell" in reason:
        return True

    if signal == "SELL" and "elliott_fib_conflict_buy" in reason:
        return True

    return False


def continuation_safety_rejects_candidate(candidate, signal, atr):
    if not ENABLE_CONTINUATION_SAFETY_GUARD:
        return False, None

    strategy = str(candidate.get("strategy", "") or "").upper()
    entry_model = str(candidate.get("entry_model", "") or "").upper()

    # =========================
    # ORB FAST_CONTINUATION safety
    # =========================
    if strategy in ["ORB", "ORB_V00"] and entry_model == "FAST_CONTINUATION":
        if (
            CONTINUATION_SAFETY_BLOCK_ORB_FAST_ON_ELLIOTT_FIB_CONFLICT
            and has_elliott_fib_directional_conflict(signal, candidate)
        ):
            return True, "continuation_safety_elliott_fib_conflict"

        orb_high = candidate.get("orb_high")
        orb_low = candidate.get("orb_low")

        if orb_high is not None and orb_low is not None and atr and atr > 0:
            orb_width = abs(float(orb_high) - float(orb_low))
            max_allowed_width = atr * CONTINUATION_SAFETY_ORB_FAST_MAX_RANGE_ATR_MULTIPLIER

            if orb_width > max_allowed_width:
                return (
                    True,
                    f"continuation_safety_orb_range_too_large width={round(orb_width, 2)} max={round(max_allowed_width, 2)}",
                )

    return False, None

def get_strategy_extra_sl_buffer(strategy_name):
    try:
        return float(STRATEGY_EXTRA_SL_BUFFER.get(strategy_name, 0.0))
    except Exception:
        return 0.0


def apply_extra_sl_buffer(signal, stop_loss, buffer_value):
    if stop_loss is None or not buffer_value:
        return stop_loss

    if signal == "BUY":
        return round(float(stop_loss) - float(buffer_value), 2)

    if signal == "SELL":
        return round(float(stop_loss) + float(buffer_value), 2)

    return stop_loss

def should_use_orb_tick_breakout_watcher(strategy_name, signal_data):
    if not ENABLE_ORB_TICK_BREAKOUT_WATCHER:
        return False

    strategy_key = str(strategy_name or "").upper()

    if strategy_key not in ORB_TICK_BREAKOUT_WATCH_STRATEGIES:
        return False

    signal = signal_data.get("signal")

    if signal not in ["BUY", "SELL"]:
        return False

    if signal_data.get("orb_high") is None or signal_data.get("orb_low") is None:
        return False

    entry_model = str(signal_data.get("entry_model", "") or "").upper()

    return entry_model in ["WAIT_RETEST", "BREAKOUT", "FAST_CONTINUATION"]


def orb_tick_breakout_ready(signal, tick, signal_data, min_distance):
    orb_high = signal_data.get("orb_high")
    orb_low = signal_data.get("orb_low")

    if orb_high is None or orb_low is None:
        return False, None, None, None

    if signal == "BUY":
        current_price = float(tick.ask)
        breakout_level = float(orb_high)
        breakout_distance = current_price - breakout_level

        if breakout_distance >= float(min_distance):
            return True, current_price, breakout_level, round(breakout_distance, 2)

        return False, current_price, breakout_level, round(breakout_distance, 2)

    if signal == "SELL":
        current_price = float(tick.bid)
        breakout_level = float(orb_low)
        breakout_distance = breakout_level - current_price

        if breakout_distance >= float(min_distance):
            return True, current_price, breakout_level, round(breakout_distance, 2)

        return False, current_price, breakout_level, round(breakout_distance, 2)

    return False, None, None, None

def should_use_tick_sniper_watcher(strategy_name, signal_data):
    if not ENABLE_TICK_SNIPER_EXECUTION:
        return False

    strategy_key = str(strategy_name or "").upper()

    if strategy_key not in TICK_SNIPER_ALLOWED_STRATEGIES:
        return False

    signal = signal_data.get("signal")

    if signal not in ["BUY", "SELL"]:
        return False

    score = signal_data.get("score", 0)

    try:
        score = float(score)
    except Exception:
        score = 0

    profile = get_tick_sniper_profile(strategy_key)

    if score < profile["min_score"]:
        return False

    return True

def get_tick_sniper_profile(strategy_name):
    strategy_key = str(strategy_name or "").upper()

    profile = TICK_SNIPER_STRATEGY_PROFILES.get(strategy_key, {})

    return {
        "trigger": profile.get("trigger", "DIRECTIONAL_RECLAIM"),
        "min_move_price": profile.get("min_move_price", TICK_SNIPER_MIN_MOVE_PRICE),
        "min_rr": profile.get("min_rr", TICK_SNIPER_MIN_RR),
        "min_score": profile.get("min_score", TICK_SNIPER_MIN_SCORE),
        "require_m5_confirmation": profile.get(
            "require_m5_confirmation",
            TICK_SNIPER_REQUIRE_M5_CONFIRMATION,
        ),
    }


def tick_sniper_ready(signal, tick, setup_data, setup):
    reference_price = setup.get("tick_sniper_reference_price")

    if reference_price is None:
        return False, None, None

    try:
        reference_price = float(reference_price)
    except Exception:
        return False, None, None

    min_move = setup.get("tick_sniper_min_move_price", TICK_SNIPER_MIN_MOVE_PRICE)

    try:
        min_move = float(min_move)
    except Exception:
        min_move = TICK_SNIPER_MIN_MOVE_PRICE

    if signal == "BUY":
        current_price = float(tick.ask)
        move = current_price - reference_price
    elif signal == "SELL":
        current_price = float(tick.bid)
        move = reference_price - current_price
    else:
        return False, None, None

    return move >= min_move, current_price, move

def get_intrabar_detector_profiles():
    allowed = {
        str(strategy or "").upper()
        for strategy in INTRABAR_PRICE_EVENT_ALLOWED_STRATEGIES
    }

    profiles = []

    for strategy in INTRABAR_PRICE_EVENT_ALLOWED_STRATEGIES:
        strategy_key = str(strategy or "").upper()

        if strategy_key not in allowed:
            continue

        profile = INTRABAR_PRICE_EVENT_STRATEGY_PROFILES.get(strategy_key)

        if not profile:
            continue

        profiles.append({
            "strategy": strategy_key,
            "trigger": profile.get("trigger", "DIRECT_BREAKOUT"),
            "level_source": profile.get("level_source", "RECENT_RANGE"),
            "lookback_bars": int(profile.get("lookback_bars", 15)),
            "min_score": profile.get("min_score", INTRABAR_PRICE_EVENT_MIN_SCORE),
            "min_rr": profile.get("min_rr", INTRABAR_PRICE_EVENT_MIN_RR),
            "min_break_distance": profile.get(
                "min_break_distance",
                INTRABAR_PRICE_EVENT_BREAK_DISTANCE_PRICE,
            ),
            "max_break_distance": profile.get(
                "max_break_distance",
                INTRABAR_PRICE_EVENT_MAX_BREAK_DISTANCE_PRICE,
            ),
            "reclaim_buffer": profile.get(
                "reclaim_buffer",
                INTRABAR_PRICE_EVENT_RECLAIM_BUFFER_PRICE,
            ),
        })

    return profiles

def evaluate_intrabar_price_event_trigger(
    *,
    trigger,
    strategy,
    signal_candidate,
    bid,
    ask,
    current,
    current_high,
    current_low,
    upper_level,
    lower_level,
    ema,
    atr,
    vwap,
    min_break,
    max_break,
    reclaim_buffer,
    require_ema_alignment,
    failed_fvg_context=None,
):
    signal = None
    current_price = None
    breakout_distance = None
    sweep_depth = None
    entry_model = None
    momentum = None
    direction_context = None

    # =========================
    # DIRECT BREAKOUT
    # =========================
    if trigger == "DIRECT_BREAKOUT":
        buy_break_distance = ask - upper_level
        sell_break_distance = lower_level - bid

        if (
            buy_break_distance >= min_break
            and buy_break_distance <= max_break
            and ema_alignment_ok("BUY", ask, ema, require_ema_alignment)
        ):
            signal = "BUY"
            current_price = ask
            breakout_distance = buy_break_distance
            entry_model = f"INTRABAR_{strategy}_BREAKOUT"
            momentum = "bullish_intrabar_breakout"
            direction_context = "tick_above_upper_level"

        elif (
            sell_break_distance >= min_break
            and sell_break_distance <= max_break
            and ema_alignment_ok("SELL", bid, ema, require_ema_alignment)
        ):
            signal = "SELL"
            current_price = bid
            breakout_distance = sell_break_distance
            entry_model = f"INTRABAR_{strategy}_BREAKOUT"
            momentum = "bearish_intrabar_breakout"
            direction_context = "tick_below_lower_level"

    # =========================
    # SWEEP / TRAP / REVERSAL RECLAIM
    # =========================
    elif trigger in ["SWEEP_RECLAIM", "TRAP_RECLAIM", "REVERSAL_RECLAIM"]:
        buy_sweep_depth = lower_level - current_low
        sell_sweep_depth = current_high - upper_level

        buy_reclaimed = ask >= lower_level + reclaim_buffer
        sell_reclaimed = bid <= upper_level - reclaim_buffer

        if trigger == "TRAP_RECLAIM":
            buy_reclaimed = buy_reclaimed and ask > float(current.get("open", ask))
            sell_reclaimed = sell_reclaimed and bid < float(current.get("open", bid))

        if trigger == "REVERSAL_RECLAIM":
            if not ENABLE_INTRABAR_PRICE_EVENT_REVERSAL_FILTER:
                return None

            if not current_body_atr_ok(current, atr):
                return None

        if (
            buy_sweep_depth >= min_break
            and buy_sweep_depth <= max_break
            and buy_reclaimed
            and ema_alignment_ok("BUY", ask, ema, require_ema_alignment)
        ):
            signal = "BUY"
            current_price = ask
            breakout_distance = ask - lower_level
            sweep_depth = buy_sweep_depth
            entry_model = f"INTRABAR_{strategy}_{trigger}"
            momentum = f"bullish_intrabar_{trigger.lower()}"
            direction_context = "sell_side_sweep_reclaimed"

        elif (
            sell_sweep_depth >= min_break
            and sell_sweep_depth <= max_break
            and sell_reclaimed
            and ema_alignment_ok("SELL", bid, ema, require_ema_alignment)
        ):
            signal = "SELL"
            current_price = bid
            breakout_distance = upper_level - bid
            sweep_depth = sell_sweep_depth
            entry_model = f"INTRABAR_{strategy}_{trigger}"
            momentum = f"bearish_intrabar_{trigger.lower()}"
            direction_context = "buy_side_sweep_reclaimed"

    # =========================
    # STRUCTURE CONTINUATION
    # =========================
    elif trigger == "STRUCTURE_CONTINUATION":
        if not ENABLE_INTRABAR_PRICE_EVENT_STRUCTURE_FILTER:
            return None
        
        structure_break = INTRABAR_PRICE_EVENT_MIN_STRUCTURE_BREAK_PRICE

        if (
            ask >= upper_level + structure_break
            and ask <= upper_level + max_break
            and ema_alignment_ok("BUY", ask, ema, require_ema_alignment)
        ):
            signal = "BUY"
            current_price = ask
            breakout_distance = ask - upper_level
            entry_model = f"INTRABAR_{strategy}_STRUCTURE_CONTINUATION"
            momentum = "bullish_intrabar_structure_continuation"
            direction_context = "structure_break_continuation_buy"

        elif (
            bid <= lower_level - structure_break
            and bid >= lower_level - max_break
            and ema_alignment_ok("SELL", bid, ema, require_ema_alignment)
        ):
            signal = "SELL"
            current_price = bid
            breakout_distance = lower_level - bid
            entry_model = f"INTRABAR_{strategy}_STRUCTURE_CONTINUATION"
            momentum = "bearish_intrabar_structure_continuation"
            direction_context = "structure_break_continuation_sell"

    # =========================
    # VWAP RECLAIM
    # =========================
    elif trigger == "VWAP_RECLAIM":
        if not ENABLE_INTRABAR_PRICE_EVENT_VWAP_FILTER:
            return None
        
        if vwap is None:
            return None

        try:
            vwap = float(vwap)
        except Exception:
            return None

        buy_sweep_depth = lower_level - current_low
        sell_sweep_depth = current_high - upper_level

        if (
            buy_sweep_depth >= min_break
            and buy_sweep_depth <= max_break
            and ask >= vwap + reclaim_buffer
        ):
            signal = "BUY"
            current_price = ask
            breakout_distance = ask - vwap
            sweep_depth = buy_sweep_depth
            entry_model = f"INTRABAR_{strategy}_VWAP_RECLAIM"
            momentum = "bullish_intrabar_vwap_reclaim"
            direction_context = "sell_side_sweep_vwap_reclaimed"

        elif (
            sell_sweep_depth >= min_break
            and sell_sweep_depth <= max_break
            and bid <= vwap - reclaim_buffer
        ):
            signal = "SELL"
            current_price = bid
            breakout_distance = vwap - bid
            sweep_depth = sell_sweep_depth
            entry_model = f"INTRABAR_{strategy}_VWAP_RECLAIM"
            momentum = "bearish_intrabar_vwap_reclaim"
            direction_context = "buy_side_sweep_vwap_reclaimed"

    # =========================
    # VWAP LIQUIDITY RECLAIM
    # =========================
    elif trigger == "VWAP_LIQUIDITY_RECLAIM":
        if not ENABLE_INTRABAR_PRICE_EVENT_VWAP_FILTER:
            return None

        if vwap is None:
            return None

        try:
            vwap = float(vwap)
            current_open = float(current.get("open", ask))
        except Exception:
            return None

        buy_sweep_depth = lower_level - current_low
        sell_sweep_depth = current_high - upper_level

        buy_level_reclaimed = ask >= lower_level + reclaim_buffer
        buy_vwap_reclaimed = ask >= vwap + reclaim_buffer

        sell_level_reclaimed = bid <= upper_level - reclaim_buffer
        sell_vwap_reclaimed = bid <= vwap - reclaim_buffer

        if (
            buy_sweep_depth >= min_break
            and buy_sweep_depth <= max_break
            and buy_level_reclaimed
            and buy_vwap_reclaimed
            and ask > current_open
        ):
            signal = "BUY"
            current_price = ask
            breakout_distance = ask - vwap
            sweep_depth = buy_sweep_depth
            entry_model = f"INTRABAR_{strategy}_VWAP_LIQUIDITY_RECLAIM"
            momentum = "bullish_intrabar_vwap_liquidity_reclaim"
            direction_context = "sell_side_sweep_level_and_vwap_reclaimed"

        elif (
            sell_sweep_depth >= min_break
            and sell_sweep_depth <= max_break
            and sell_level_reclaimed
            and sell_vwap_reclaimed
            and bid < current_open
        ):
            signal = "SELL"
            current_price = bid
            breakout_distance = vwap - bid
            sweep_depth = sell_sweep_depth
            entry_model = f"INTRABAR_{strategy}_VWAP_LIQUIDITY_RECLAIM"
            momentum = "bearish_intrabar_vwap_liquidity_reclaim"
            direction_context = "buy_side_sweep_level_and_vwap_reclaimed"

    # =========================
    # FAILED FVG REVERSAL RECLAIM
    # =========================
    elif trigger == "FAILED_FVG_REVERSAL_RECLAIM":
        failed_fvg_context = failed_fvg_context or {}

        bullish_fvg = failed_fvg_context.get("bullish_fvg")
        bearish_fvg = failed_fvg_context.get("bearish_fvg")

        try:
            current_open = float(current.get("open", ask))
        except Exception:
            return None

        # SELL: bullish FVG support failed
        if bullish_fvg:
            fvg_bottom = float(bullish_fvg["bottom"])
            fvg_top = float(bullish_fvg["top"])
            fvg_mid = float(bullish_fvg["mid"])

            sell_break_distance = fvg_bottom - bid
            touched_bullish_fvg = current_high >= fvg_bottom
            failed_below_fvg = bid <= fvg_bottom - reclaim_buffer

            if (
                touched_bullish_fvg
                and failed_below_fvg
                and sell_break_distance >= min_break
                and sell_break_distance <= max_break
                and bid < current_open
            ):
                signal = "SELL"
                current_price = bid
                breakout_distance = sell_break_distance
                sweep_depth = current_high - fvg_bottom
                entry_model = f"INTRABAR_{strategy}_FAILED_BULLISH_FVG_REVERSAL"
                momentum = "bearish_intrabar_failed_bullish_fvg"
                direction_context = (
                    f"bullish_fvg_failed bottom={round(fvg_bottom, 2)} "
                    f"top={round(fvg_top, 2)} mid={round(fvg_mid, 2)}"
                )

        # BUY: bearish FVG resistance failed
        if bearish_fvg and signal is None:
            fvg_bottom = float(bearish_fvg["bottom"])
            fvg_top = float(bearish_fvg["top"])
            fvg_mid = float(bearish_fvg["mid"])

            buy_break_distance = ask - fvg_top
            touched_bearish_fvg = current_low <= fvg_top
            reclaimed_above_fvg = ask >= fvg_top + reclaim_buffer

            if (
                touched_bearish_fvg
                and reclaimed_above_fvg
                and buy_break_distance >= min_break
                and buy_break_distance <= max_break
                and ask > current_open
            ):
                signal = "BUY"
                current_price = ask
                breakout_distance = buy_break_distance
                sweep_depth = fvg_top - current_low
                entry_model = f"INTRABAR_{strategy}_FAILED_BEARISH_FVG_REVERSAL"
                momentum = "bullish_intrabar_failed_bearish_fvg"
                direction_context = (
                    f"bearish_fvg_failed bottom={round(fvg_bottom, 2)} "
                    f"top={round(fvg_top, 2)} mid={round(fvg_mid, 2)}"
                )

    if signal is None:
        return None

    return {
        "signal": signal,
        "current_price": current_price,
        "breakout_distance": breakout_distance,
        "sweep_depth": sweep_depth,
        "entry_model": entry_model,
        "momentum": momentum,
        "direction_context": direction_context,
    }

def build_intrabar_price_event_signal_data(df, tick, session_name, market_condition, current_candle_time):
    if not ENABLE_INTRABAR_PRICE_EVENT_DETECTOR:
        return None

    if len(df) < 20:
        return None

    current = df.iloc[-1]
    signal_candle = df.iloc[-2]

    atr = signal_candle.get("atr_14")
    ema = signal_candle.get("ema_20")

    if atr is None or ema is None or atr <= 0:
        return None

    bid = float(tick.bid)
    ask = float(tick.ask)

    current_high = float(current.get("high", max(bid, ask)))
    current_low = float(current.get("low", min(bid, ask)))
    
    vwap = calculate_intrabar_vwap(
        df,
        INTRABAR_PRICE_EVENT_VWAP_LOOKBACK_BARS,
    )

    for profile in get_intrabar_detector_profiles():
        strategy = profile["strategy"]
        trigger = profile["trigger"]
        lookback_bars = profile["lookback_bars"]

        if len(df) < lookback_bars + 2:
            continue

        range_data = df.iloc[-(lookback_bars + 1):-1]

        if range_data is None or len(range_data) < 5:
            continue

        upper_level = float(range_data["high"].max())
        lower_level = float(range_data["low"].min())
        range_width = upper_level - lower_level

        if range_width <= 0:
            continue

        min_break = float(profile["min_break_distance"])
        max_break = float(profile["max_break_distance"])
        reclaim_buffer = float(profile["reclaim_buffer"])

        signal = None
        current_price = None
        breakout_distance = None
        sweep_depth = None
        entry_model = None
        direction_context = None
        momentum = None

        failed_fvg_context = None

        if trigger == "FAILED_FVG_REVERSAL_RECLAIM":
            failed_fvg_context = find_recent_intrabar_fvg_zones(
                df,
                profile.get("lookback_bars", 20),
            )

        trigger_result = evaluate_intrabar_price_event_trigger(
            trigger=trigger,
            strategy=strategy,
            signal_candidate=None,
            bid=bid,
            ask=ask,
            current=current,
            current_high=current_high,
            current_low=current_low,
            upper_level=upper_level,
            lower_level=lower_level,
            ema=ema,
            atr=atr,
            vwap=vwap,
            min_break=min_break,
            max_break=max_break,
            reclaim_buffer=reclaim_buffer,
            require_ema_alignment=profile.get("require_ema_alignment", True),
            failed_fvg_context=failed_fvg_context,
        )

        if not trigger_result:
            continue

        signal = trigger_result["signal"]
        current_price = trigger_result["current_price"]
        breakout_distance = trigger_result["breakout_distance"]
        sweep_depth = trigger_result["sweep_depth"]
        entry_model = trigger_result["entry_model"]
        momentum = trigger_result["momentum"]
        direction_context = trigger_result["direction_context"]

        min_sl_distance = float(
            profile.get("min_sl_distance", INTRABAR_PRICE_EVENT_MIN_SL_DISTANCE_PRICE)
        )
        max_sl_distance = float(
            profile.get("max_sl_distance", INTRABAR_PRICE_EVENT_MAX_SL_DISTANCE_PRICE)
        )

        min_tp_distance = float(
            profile.get("min_tp_distance", INTRABAR_PRICE_EVENT_MIN_TP_DISTANCE_PRICE)
        )
        max_tp_distance = float(
            profile.get("max_tp_distance", INTRABAR_PRICE_EVENT_MAX_TP_DISTANCE_PRICE)
        )

        target_rr = float(
            profile.get("target_rr", INTRABAR_PRICE_EVENT_DEFAULT_TARGET_RR)
        )

        sl_buffer = max(float(atr) * 0.25, 2.0)

        if signal == "BUY":
            raw_sl = lower_level - sl_buffer - INTRABAR_PRICE_EVENT_EXTRA_SL_PRICE
            raw_stop_distance = current_price - raw_sl

            stop_distance = min(max(raw_stop_distance, min_sl_distance), max_sl_distance)
            sl_reference = round(current_price - stop_distance, 2)

            tp_distance = min(
                max(stop_distance * target_rr, min_tp_distance),
                max_tp_distance,
            )
            tp_reference = round(current_price + tp_distance, 2)

            if sl_reference >= current_price or tp_reference <= current_price:
                continue
            
        else:
            raw_sl = upper_level + sl_buffer + INTRABAR_PRICE_EVENT_EXTRA_SL_PRICE
            raw_stop_distance = raw_sl - current_price

            stop_distance = min(max(raw_stop_distance, min_sl_distance), max_sl_distance)
            sl_reference = round(current_price + stop_distance, 2)

            tp_distance = min(
                max(stop_distance * target_rr, min_tp_distance),
                max_tp_distance,
            )
            tp_reference = round(current_price - tp_distance, 2)

            if sl_reference <= current_price or tp_reference >= current_price:
                continue

        setup_id = f"INTRABAR-{strategy}-{signal}-{str(current_candle_time)}"

        return {
            "signal": signal,
            "score": profile["min_score"],
            "strategy": strategy,
            "entry_model": entry_model,
            "pattern_height": range_width,
            "orb_high": upper_level,
            "orb_low": lower_level,
            "intrabar_upper_level": upper_level,
            "intrabar_lower_level": lower_level,
            "breakout_distance": round(breakout_distance, 2),
            "sweep_depth": round(sweep_depth, 2) if sweep_depth is not None else None,
            "sl_reference": sl_reference,
            "intrabar_extra_sl_price": INTRABAR_PRICE_EVENT_EXTRA_SL_PRICE,
            "tp_reference": tp_reference,
            "target_model": "INTRABAR_RANGE_EXTENSION",
            "momentum": momentum,
            "direction_context": direction_context,
            "session": session_name,
            "market_condition": market_condition,
            "setup_id": setup_id,
            "vwap": round(vwap, 2) if vwap is not None else None,
            "intrabar_trigger": trigger,
            "intrabar_profile": profile,
            "intrabar_stop_distance": round(stop_distance, 2),
            "intrabar_tp_distance": round(tp_distance, 2),
            "intrabar_target_rr": target_rr,
            "intrabar_max_sl_distance": max_sl_distance,
            "intrabar_max_tp_distance": max_tp_distance,
            "require_m5_confirmation": bool(
                profile.get("require_m5_confirmation", False)
            ),
            "required_rr": profile["min_rr"],
            "reason": (
                f"VWAP {round(vwap, 2) if vwap is not None else 'N/A'} -> "
                f"Intrabar {strategy} {signal} -> trigger {trigger} before M15 close -> "
                f"range {round(lower_level, 2)}-{round(upper_level, 2)} -> "
                f"distance {round(breakout_distance, 2)} -> "
                f"sweep {round(sweep_depth, 2) if sweep_depth is not None else 'N/A'} -> "
                f"SL {sl_reference} -> TP {tp_reference}"
            ),
        }

    return None
    
def process_intrabar_price_event_detector(df, tick, account_info, session_name, market_condition, current_candle_time):
    signal_data = build_intrabar_price_event_signal_data(
        df=df,
        tick=tick,
        session_name=session_name,
        market_condition=market_condition,
        current_candle_time=current_candle_time,
    )

    if not signal_data:
        return False

    setup_id = signal_data.get("setup_id")
    if is_intrabar_detection_recent(setup_id, INTRABAR_PRICE_EVENT_EXPIRY_SECONDS):
        return False
    
    strategy_name = signal_data.get("strategy")
    signal = signal_data.get("signal")
    
    duplicate, duplicate_key = is_intrabar_price_event_duplicate(
        signal_data,
        current_candle_time,
    )

    if duplicate:
        if INTRABAR_PRICE_EVENT_LOG_DUPLICATE_SKIPS:
            logger.info(
                f"[INTRABAR PRICE EVENT] Duplicate skipped | "
                f"setup_id={setup_id} key={duplicate_key}"
            )

        return False

    m5_ok, m5_reason = intrabar_m5_confirmation_ok(
        signal,
        strategy_name,
    )

    if not m5_ok:
        logger.info(
            f"[INTRABAR PRICE EVENT] M5 confirmation rejected | "
            f"setup_id={setup_id} strategy={strategy_name} "
            f"signal={signal} reason={m5_reason}"
        )

        return False

    already_active, active_state = is_setup_id_already_active(setup_id)

    if already_active:
        logger.info(
            f"[INTRABAR Price Event] Setup already active | "
            f"setup_id={setup_id} state={active_state}"
        )
        return False

    require_m5_confirmation = bool(
        INTRABAR_PRICE_EVENT_REQUIRE_M5_CONFIRMATION
        or signal_data.get("require_m5_confirmation", False)
    )

    m5_reason = "intrabar_m5_not_required"

    if require_m5_confirmation:
        m5_confirmed, m5_reason = intrabar_m5_confirmation_ok(
            signal,
            strategy_name,
        )

        if not m5_confirmed:
            logger.info(
                f"[INTRABAR Price Event] M5 confirmation failed | "
                f"setup_id={setup_id} strategy={strategy_name} "
                f"reason={m5_reason}"
            )
            return False

    news_blocked, news_reason = is_news_blackout_active()

    if news_blocked:
        logger.info(
            f"[INTRABAR Price Event] News blocked | "
            f"setup_id={setup_id} reason={news_reason}"
        )
        return False

    time_blocked, time_reason = is_trading_blackout_active()

    if time_blocked:
        logger.info(
            f"[INTRABAR Price Event] Time blocked | "
            f"setup_id={setup_id} reason={time_reason}"
        )
        return False

    trade_plan = calculate_trade_plan(
        df=df,
        signal=signal,
        tick=tick,
        account_balance=account_info.balance,
        signal_data=signal_data,
    )

    if trade_plan is None:
        logger.info(
            f"[INTRABAR Price Event] Trade plan failed | setup_id={setup_id}"
        )
        return False

    trade_plan["skip_slippage_guard"] = True
    trade_plan["execution_speed_mode"] = "INTRABAR"

    trade_plan["strategy"] = strategy_name
    trade_plan["signal"] = signal
    trade_plan["score"] = signal_data.get("score")
    trade_plan["session"] = session_name
    trade_plan["market_condition"] = market_condition
    trade_plan["setup_id"] = setup_id
    trade_plan["reason"] = signal_data.get("reason")

    rr_value = calculate_rr_value(trade_plan)

    required_rr = signal_data.get("required_rr", INTRABAR_PRICE_EVENT_MIN_RR)

    if rr_value is None or rr_value < required_rr:
        rejection_reason = f"low_rr {rr_value}/{required_rr}"

        logger.info(
            f"[INTRABAR PRICE EVENT] RR too low | "
            f"setup_id={setup_id} rr={rr_value} required={required_rr}"
        )

        log_setup_event(
            setup_id=setup_id,
            event="INTRABAR_PRICE_EVENT_REJECTED_LOW_RR",
            strategy=strategy_name,
            signal=signal,
            entry_model=signal_data.get("entry_model"),
            score=signal_data.get("score"),
            session=session_name,
            market_condition=market_condition,
            entry=trade_plan.get("entry_price"),
            sl=trade_plan.get("stop_loss"),
            tp=trade_plan.get("take_profit"),
            rr=rr_value,
            required_rr=required_rr,
            reason=rejection_reason,
            extra={
                "source": "intrabar_price_event_low_rr",
                "orb_high": signal_data.get("orb_high"),
                "orb_low": signal_data.get("orb_low"),
                "breakout_distance": signal_data.get("breakout_distance"),
                "trigger": signal_data.get("intrabar_trigger"),
                "vwap": signal_data.get("vwap"),
                "sweep_depth": signal_data.get("sweep_depth"),
                "intrabar_extra_sl_price": signal_data.get("intrabar_extra_sl_price"),
                "skip_slippage_guard": trade_plan.get("skip_slippage_guard"),
                "execution_speed_mode": trade_plan.get("execution_speed_mode"),
            },
        )
        
        news_context = attach_news_context_to_signal_data(signal_data)

        tracked = register_setup_outcome(
            symbol=SYMBOL,
            setup_id=setup_id,
            event="INTRABAR_PRICE_EVENT_REJECTED_LOW_RR",
            strategy=strategy_name,
            signal=signal,
            entry_model=signal_data.get("entry_model"),
            score=signal_data.get("score"),
            session=session_name,
            market_condition="INTRABAR_PENDING",
            entry=trade_plan.get("entry_price"),
            sl=trade_plan.get("stop_loss"),
            tp=trade_plan.get("take_profit"),
            reason=rejection_reason,
            extra={
                "source": "intrabar_price_event_low_rr",
                "source_events": ["INTRABAR_PRICE_EVENT_REJECTED_LOW_RR"],
                "execution_bucket": "INTRABAR",
                "rr": rr_value,
                "required_rr": required_rr,
                "orb_high": signal_data.get("orb_high"),
                "orb_low": signal_data.get("orb_low"),
                "breakout_distance": signal_data.get("breakout_distance"),
                "trigger": signal_data.get("intrabar_trigger"),
                "vwap": signal_data.get("vwap"),
                "sweep_depth": signal_data.get("sweep_depth"),
                "news_context": news_context,
                "news_tag": news_context.get("news_tag") if news_context else None,
            },
        )

        if tracked:
            notify_setup_similarity_if_relevant(setup_id)
            notify_scenario_cluster_if_relevant(setup_id)

        save_execution_memory_report(
            selected_signal_data=signal_data,
            strategy_name=strategy_name,
            signal=signal,
            score=signal_data.get("score"),
            session_name=session_name,
            market_condition=market_condition,
            reason=rejection_reason,
            trade_plan=trade_plan,
            decision="INTRABAR_PRICE_EVENT_REJECTED_LOW_RR",
            decision_reason="intrabar price event rejected before execution because RR is below required threshold",
            rr_value=rr_value,
            required_rr=required_rr,
            extra={
                "source": "intrabar_price_event_low_rr",
                "orb_high": signal_data.get("orb_high"),
                "orb_low": signal_data.get("orb_low"),
                "breakout_distance": signal_data.get("breakout_distance"),
                "trigger": signal_data.get("intrabar_trigger"),
                "vwap": signal_data.get("vwap"),
                "sweep_depth": signal_data.get("sweep_depth"),
                "intrabar_extra_sl_price": signal_data.get("intrabar_extra_sl_price"),
                "skip_slippage_guard": trade_plan.get("skip_slippage_guard"),
                "execution_speed_mode": trade_plan.get("execution_speed_mode"),
            },
        )

        recovery_id = None

        if rr_value is not None and ENABLE_CANDIDATE_REJECTION_RECOVERY:
            rejected_signal_data = signal_data.copy()

            rejected_signal_data["strategy"] = strategy_name
            rejected_signal_data["signal"] = signal
            rejected_signal_data["session"] = session_name
            rejected_signal_data["market_condition"] = market_condition
            rejected_signal_data["setup_id"] = setup_id
            rejected_signal_data["recovery_source"] = "intrabar_price_event_low_rr"
            rejected_signal_data["recovery_reason_type"] = "LOW_RR"
            rejected_signal_data["rejected_trade_plan"] = {
                "entry_price": trade_plan.get("entry_price"),
                "stop_loss": trade_plan.get("stop_loss"),
                "take_profit": trade_plan.get("take_profit"),
                "lot": trade_plan.get("lot"),
                "rr": rr_value,
                "required_rr": required_rr,
                "reason": trade_plan.get("reason"),
            }

            recovery_id = register_rejected_candidate_for_recovery(
                symbol=SYMBOL,
                signal=signal,
                strategy=strategy_name,
                score=signal_data.get("score", 0),
                reason_type="LOW_RR",
                rejection_reason=rejection_reason,
                signal_data=rejected_signal_data,
                required_rr=required_rr,
                current_rr=rr_value,
            )

        if (
            ENABLE_CANDIDATE_REJECTION_TELEGRAM_ALERTS
            and TELEGRAM_NOTIFY_CANDIDATE_REJECTED_LOW_RR
        ):
            send_telegram_message(
                f"⚠️ Intrabar Candidate Rejected — Low RR\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n"
                f"Setup ID: {setup_id}\n"
                f"Entry Model: {signal_data.get('entry_model')}\n"
                f"Trigger: {signal_data.get('intrabar_trigger')}\n"
                f"Reason: {rejection_reason}\n"
                f"Candidate Reason: {signal_data.get('reason', 'N/A')}\n\n"
                f"Entry: {trade_plan.get('entry_price')}\n"
                f"SL: {trade_plan.get('stop_loss')}\n"
                f"{_format_telegram_tp123_from_trade_plan(signal, trade_plan)}\n"
                f"RR: {rr_value} / Required: {required_rr}\n\n"
                f"Recovery ID: {recovery_id or 'not_registered'}\n"
                f"Action: moved to intrabar candidate recovery if eligible."
            )

        return False

    trade_allowed, guard_reason = check_trade_guard(signal, tick)

    if not trade_allowed:
        logger.info(
            f"[INTRABAR ORB] Guard blocked | "
            f"setup_id={setup_id} reason={guard_reason}"
        )
        return False

    if is_trade_blocked_by_execution_memory(
        trade_plan=trade_plan,
        signal_data=signal_data,
        setup=None,
        strategy_name=strategy_name,
        signal=signal,
    ):
        save_execution_memory_report(
            selected_signal_data=signal_data,
            strategy_name=strategy_name,
            signal=signal,
            score=signal_data.get("score"),
            session_name=session_name,
            market_condition=market_condition,
            reason="intrabar ORB skipped by execution memory",
            trade_plan=trade_plan,
            decision="INTRABAR_PRICE_EVENT_BLOCKED_BY_MEMORY",
            decision_reason="intrabar Price Event skipped by execution memory",
            rr_value=rr_value,
            required_rr=required_rr,
            extra={
                "orb_high": signal_data.get("orb_high"),
                "orb_low": signal_data.get("orb_low"),
                "breakout_distance": signal_data.get("breakout_distance"),
                "trigger": signal_data.get("intrabar_trigger"),
                "vwap": signal_data.get("vwap"),
                "sweep_depth": signal_data.get("sweep_depth"),
                "m5_confirmation_reason": m5_reason,
                "intrabar_extra_sl_price": signal_data.get("intrabar_extra_sl_price"),
                "skip_slippage_guard": trade_plan.get("skip_slippage_guard"),
                "execution_speed_mode": trade_plan.get("execution_speed_mode"),
            },
        )

        return True

    log_setup_event(
        setup_id=setup_id,
        event="INTRABAR_PRICE_EVENT_EXECUTION_ATTEMPT",
        strategy=strategy_name,
        signal=signal,
        entry_model=signal_data.get("entry_model"),
        score=signal_data.get("score"),
        session=session_name,
        market_condition=market_condition,
        entry=trade_plan.get("entry_price"),
        sl=trade_plan.get("stop_loss"),
        tp=trade_plan.get("take_profit"),
        rr=rr_value,
        required_rr=required_rr,
        reason="intrabar ORB execution attempt before M15 close",
        extra={
            "orb_high": signal_data.get("orb_high"),
            "orb_low": signal_data.get("orb_low"),
            "breakout_distance": signal_data.get("breakout_distance"),
        },
    )

    save_execution_memory_report(
        selected_signal_data=signal_data,
        strategy_name=strategy_name,
        signal=signal,
        score=signal_data.get("score"),
        session_name=session_name,
        market_condition=market_condition,
        reason="intrabar Price Event execution attempt before M15 close",
        trade_plan=trade_plan,
        decision="INTRABAR_PRICE_EVENT_EXECUTION_ATTEMPT",
        decision_reason="sending intrabar Price Event order to MT5",
        rr_value=rr_value,
        required_rr=required_rr,
        extra={
            "orb_high": signal_data.get("orb_high"),
            "orb_low": signal_data.get("orb_low"),
            "breakout_distance": signal_data.get("breakout_distance"),
            "m5_confirmation_reason": m5_reason,
            "intrabar_extra_sl_price": signal_data.get("intrabar_extra_sl_price"),
            "skip_slippage_guard": trade_plan.get("skip_slippage_guard"),
            "execution_speed_mode": trade_plan.get("execution_speed_mode"),
        },
    )

    if INTRABAR_PRICE_EVENT_NOTIFY_TELEGRAM:
        send_telegram_message(
            f"⚡ Intrabar Setup Executing\n"
            f"Symbol: {SYMBOL}\n"
            f"Strategy: {strategy_name}\n"
            f"Signal: {signal}\n"
            f"Setup ID: {setup_id}\n\n"
            f"ORB High: {signal_data.get('orb_high')}\n"
            f"ORB Low: {signal_data.get('orb_low')}\n"
            f"Breakout Distance: {signal_data.get('breakout_distance')}\n"
            f"Entry: {trade_plan.get('entry_price')}\n"
            f"SL: {trade_plan.get('stop_loss')}\n"
            f"TP1 / Execution TP: {trade_plan.get('take_profit')}\\n"
            f"Original TP: {trade_plan.get('original_take_profit', trade_plan.get('take_profit'))}\\n"
            f"TP Plan: {trade_plan.get('tp_plan_summary', 'standard')}\\n"
            f"Trigger: {signal_data.get('intrabar_trigger')}\n"
            f"RR: {rr_value} / Required: {required_rr}\n"
            f"Mode: before M15 candle close"
        )
        
    apply_strategy_advisory_note(
        signal_data=signal_data,
        strategy_name=strategy_name,
        setup_source_bucket="INTRABAR",
    )

    observe_universal_confirmation_from_scope(
        locals(),
        setup_source_bucket_override="INTRABAR",
    )

    _live_execute_start_ts = time.perf_counter()
    logger.info(
        f"[LIVE EXECUTION TIMING] stage=before_execute_trade "
        f"symbol={SYMBOL} signal={signal} "
        f"setup_id={trade_plan.get('setup_id') if isinstance(trade_plan, dict) else None} "
        f"strategy={trade_plan.get('strategy') if isinstance(trade_plan, dict) else None}"
    )
    maybe_notify_phase6s_runtime_outlook_advisory(
        signal,
        trade_plan,
        trigger_context="before_execute_trade",
    )

    execution_result = execute_trade(signal, trade_plan, SYMBOL)
    logger.info(
        f"[LIVE EXECUTION TIMING] stage=after_execute_trade "
        f"elapsed_ms={round((time.perf_counter() - _live_execute_start_ts) * 1000, 2)} "
        f"symbol={SYMBOL} signal={signal} result={execution_result}"
    )

    if execution_result:
        news_context = attach_news_context_to_signal_data(signal_data)

        tracked = register_setup_outcome(
            symbol=SYMBOL,
            setup_id=setup_id,
            event="INTRABAR_PRICE_EVENT_EXECUTED",
            strategy=strategy_name,
            signal=signal,
            entry_model=signal_data.get("entry_model"),
            score=signal_data.get("score"),
            session=session_name,
            market_condition="INTRABAR_PENDING",
            entry=trade_plan.get("entry_price"),
            sl=trade_plan.get("stop_loss"),
            tp=trade_plan.get("take_profit"),
            reason="intrabar Price Event executed before M15 close",
            extra={
                "source": "intrabar_price_event_executed",
                "rr": rr_value,
                "required_rr": required_rr,
                "orb_high": signal_data.get("orb_high"),
                "orb_low": signal_data.get("orb_low"),
                "breakout_distance": signal_data.get("breakout_distance"),
                "trigger": signal_data.get("intrabar_trigger"),
                "vwap": signal_data.get("vwap"),
                "sweep_depth": signal_data.get("sweep_depth"),
                "m5_confirmation_reason": m5_reason,
                "intrabar_extra_sl_price": signal_data.get("intrabar_extra_sl_price"),
                "skip_slippage_guard": trade_plan.get("skip_slippage_guard"),
                "execution_speed_mode": trade_plan.get("execution_speed_mode"),
                "news_context": news_context,
                "news_tag": news_context.get("news_tag") if news_context else None,
            },
        )

        if tracked:
            notify_setup_similarity_if_relevant(setup_id)
            notify_scenario_cluster_if_relevant(setup_id)
        
        save_execution_memory_report(
            selected_signal_data=signal_data,
            strategy_name=strategy_name,
            signal=signal,
            score=signal_data.get("score"),
            session_name=session_name,
            market_condition=market_condition,
            reason="intrabar Price Event execution success",
            trade_plan=trade_plan,
            decision="INTRABAR_PRICE_EVENT_EXECUTION_SUCCESS",
            decision_reason="intrabar Price Event MT5 order returned success",
            rr_value=rr_value,
            required_rr=required_rr,
            execution_result=execution_result,
            extra={
                "orb_high": signal_data.get("orb_high"),
                "orb_low": signal_data.get("orb_low"),
                "breakout_distance": signal_data.get("breakout_distance"),
                "m5_confirmation_reason": m5_reason,
                "intrabar_extra_sl_price": signal_data.get("intrabar_extra_sl_price"),
                "skip_slippage_guard": trade_plan.get("skip_slippage_guard"),
                "execution_speed_mode": trade_plan.get("execution_speed_mode"),
            },
        )

        log_setup_event(
            setup_id=setup_id,
            event="INTRABAR_PRICE_EVENT_EXECUTED",
            strategy=strategy_name,
            signal=signal,
            entry_model=signal_data.get("entry_model"),
            score=signal_data.get("score"),
            session=session_name,
            market_condition=market_condition,
            entry=trade_plan.get("entry_price"),
            sl=trade_plan.get("stop_loss"),
            tp=trade_plan.get("take_profit"),
            rr=rr_value,
            required_rr=required_rr,
            reason="intrabar ORB executed before M15 close",
        )
        
        news_context = attach_news_context_to_signal_data(signal_data)

        tracked = register_setup_outcome(
            symbol=SYMBOL,
            setup_id=setup_id,
            event="INTRABAR_PRICE_EVENT_EXECUTED",
            strategy=strategy_name,
            signal=signal,
            entry_model=signal_data.get("entry_model"),
            score=signal_data.get("score"),
            session=session_name,
            market_condition="INTRABAR_PENDING",
            entry=trade_plan.get("entry_price"),
            sl=trade_plan.get("stop_loss"),
            tp=trade_plan.get("take_profit"),
            reason="intrabar Price Event executed before M15 close",
            extra={
                "source": "intrabar_price_event_executed",
                "source_events": ["INTRABAR_PRICE_EVENT_EXECUTED"],
                "execution_bucket": "INTRABAR",
                "rr": rr_value,
                "required_rr": required_rr,
                "orb_high": signal_data.get("orb_high"),
                "orb_low": signal_data.get("orb_low"),
                "breakout_distance": signal_data.get("breakout_distance"),
                "trigger": signal_data.get("intrabar_trigger"),
                "vwap": signal_data.get("vwap"),
                "sweep_depth": signal_data.get("sweep_depth"),
                "news_context": news_context,
                "news_tag": news_context.get("news_tag") if news_context else None,
            },
        )

        if tracked:
            notify_setup_similarity_if_relevant(setup_id)
            notify_scenario_cluster_if_relevant(setup_id)

        return True

    save_execution_memory_report(
        selected_signal_data=signal_data,
        strategy_name=strategy_name,
        signal=signal,
        score=signal_data.get("score"),
        session_name=session_name,
        market_condition=market_condition,
        reason="intrabar Price Event execution failed",
        trade_plan=trade_plan,
        decision="INTRABAR_PRICE_EVENT_EXECUTION_FAILED",
        decision_reason="intrabar Price Event execute_trade returned False",
        rr_value=rr_value,
        required_rr=required_rr,
        execution_result=execution_result,
        extra={
            "orb_high": signal_data.get("orb_high"),
            "orb_low": signal_data.get("orb_low"),
            "breakout_distance": signal_data.get("breakout_distance"),
            "m5_confirmation_reason": m5_reason,
            "intrabar_extra_sl_price": signal_data.get("intrabar_extra_sl_price"),
            "skip_slippage_guard": trade_plan.get("skip_slippage_guard"),
            "execution_speed_mode": trade_plan.get("execution_speed_mode"),
        },
    )

    log_setup_event(
        setup_id=setup_id,
        event="INTRABAR_PRICE_EVENT_EXECUTION_FAILED",
        strategy=strategy_name,
        signal=signal,
        entry_model=signal_data.get("entry_model"),
        score=signal_data.get("score"),
        session=session_name,
        market_condition=market_condition,
        entry=trade_plan.get("entry_price"),
        sl=trade_plan.get("stop_loss"),
        tp=trade_plan.get("take_profit"),
        rr=rr_value,
        required_rr=required_rr,
        reason="intrabar execute_trade returned False",
    )

    news_context = attach_news_context_to_signal_data(signal_data)

    tracked = register_setup_outcome(
        symbol=SYMBOL,
        setup_id=setup_id,
        event="INTRABAR_PRICE_EVENT_EXECUTION_FAILED",
        strategy=strategy_name,
        signal=signal,
        entry_model=signal_data.get("entry_model"),
        score=signal_data.get("score"),
        session=session_name,
        market_condition="INTRABAR_PENDING",
        entry=trade_plan.get("entry_price"),
        sl=trade_plan.get("stop_loss"),
        tp=trade_plan.get("take_profit"),
        reason="intrabar Price Event execute_trade returned False",
        extra={
            "source": "intrabar_price_event_execution_failed",
            "source_events": ["INTRABAR_PRICE_EVENT_EXECUTION_FAILED"],
            "execution_bucket": "INTRABAR",
            "rr": rr_value,
            "required_rr": required_rr,
            "orb_high": signal_data.get("orb_high"),
            "orb_low": signal_data.get("orb_low"),
            "breakout_distance": signal_data.get("breakout_distance"),
            "trigger": signal_data.get("intrabar_trigger"),
            "vwap": signal_data.get("vwap"),
            "sweep_depth": signal_data.get("sweep_depth"),
            "news_context": news_context,
            "news_tag": news_context.get("news_tag") if news_context else None,
        },
    )
    
    if tracked:
        notify_setup_similarity_if_relevant(setup_id)
        notify_scenario_cluster_if_relevant(setup_id)

    return True

def is_intrabar_detection_recent(setup_id, expiry_seconds):
    now_ts = datetime.utcnow().timestamp()

    expired_keys = [
        key for key, seen_ts in INTRABAR_DETECTION_CACHE.items()
        if now_ts - seen_ts > expiry_seconds
    ]

    for key in expired_keys:
        INTRABAR_DETECTION_CACHE.pop(key, None)

    if setup_id in INTRABAR_DETECTION_CACHE:
        return True

    INTRABAR_DETECTION_CACHE[setup_id] = now_ts
    return False

def calculate_intrabar_vwap(df, lookback_bars=20):
    if df is None or len(df) < lookback_bars:
        return None

    recent = df.tail(lookback_bars)

    try:
        typical_price = (
            recent["high"] + recent["low"] + recent["close"]
        ) / 3

        volume = recent["tick_volume"] if "tick_volume" in recent.columns else None

        if volume is None or volume.sum() <= 0:
            return float(typical_price.mean())

        return float((typical_price * volume).sum() / volume.sum())

    except Exception:
        return None


def current_body_atr_ok(current, atr):
    try:
        body = abs(float(current.get("close")) - float(current.get("open")))
        atr = float(atr)
    except Exception:
        return False

    if atr <= 0:
        return False

    return body >= atr * INTRABAR_PRICE_EVENT_MIN_CURRENT_BODY_ATR


def ema_alignment_ok(signal, price, ema, require_ema_alignment):
    if not require_ema_alignment:
        return True

    if ema is None:
        return False

    try:
        price = float(price)
        ema = float(ema)
    except Exception:
        return False

    if signal == "BUY":
        return price > ema

    if signal == "SELL":
        return price < ema

    return False

def build_intrabar_price_event_dedup_key(signal_data, current_candle_time):
    strategy = str(signal_data.get("strategy", "UNKNOWN")).upper()
    signal = str(signal_data.get("signal", "UNKNOWN")).upper()
    trigger = str(signal_data.get("intrabar_trigger", "UNKNOWN")).upper()

    upper_level = signal_data.get("intrabar_upper_level") or signal_data.get("orb_high")
    lower_level = signal_data.get("intrabar_lower_level") or signal_data.get("orb_low")

    try:
        upper_level = round(float(upper_level), 1)
    except Exception:
        upper_level = "NA"

    try:
        lower_level = round(float(lower_level), 1)
    except Exception:
        lower_level = "NA"

    return (
        f"{current_candle_time}|"
        f"{strategy}|"
        f"{signal}|"
        f"{trigger}|"
        f"{upper_level}|"
        f"{lower_level}"
    )


def cleanup_intrabar_price_event_dedup_cache():
    now_ts = datetime.utcnow().timestamp()

    expired_keys = []

    for key, item in INTRABAR_PRICE_EVENT_DEDUP_CACHE.items():
        seen_at = item.get("seen_at", 0)

        if now_ts - seen_at > INTRABAR_PRICE_EVENT_DEDUP_SECONDS:
            expired_keys.append(key)

    for key in expired_keys:
        INTRABAR_PRICE_EVENT_DEDUP_CACHE.pop(key, None)


def is_intrabar_price_event_duplicate(signal_data, current_candle_time):
    if not ENABLE_INTRABAR_PRICE_EVENT_DEDUP_GUARD:
        return False, None

    cleanup_intrabar_price_event_dedup_cache()

    key = build_intrabar_price_event_dedup_key(
        signal_data,
        current_candle_time,
    )

    if key in INTRABAR_PRICE_EVENT_DEDUP_CACHE:
        return True, key

    strategy = str(signal_data.get("strategy", "UNKNOWN")).upper()

    candle_count = 0
    strategy_candle_count = 0

    candle_prefix = f"{current_candle_time}|"
    strategy_prefix = f"{current_candle_time}|{strategy}|"

    for existing_key in INTRABAR_PRICE_EVENT_DEDUP_CACHE:
        if existing_key.startswith(candle_prefix):
            candle_count += 1

        if existing_key.startswith(strategy_prefix):
            strategy_candle_count += 1

    if candle_count >= INTRABAR_PRICE_EVENT_MAX_PER_CANDLE:
        return True, f"max_per_candle_reached:{current_candle_time}"

    if strategy_candle_count >= INTRABAR_PRICE_EVENT_MAX_PER_STRATEGY_PER_CANDLE:
        return True, f"max_per_strategy_per_candle_reached:{strategy}"

    INTRABAR_PRICE_EVENT_DEDUP_CACHE[key] = {
        "seen_at": datetime.utcnow().timestamp(),
        "setup_id": signal_data.get("setup_id"),
        "strategy": strategy,
        "signal": signal_data.get("signal"),
        "trigger": signal_data.get("intrabar_trigger"),
    }

    return False, key

def calculate_heikin_ashi_direction(df):
    if df is None or len(df) < 3:
        return None

    try:
        ha_close = (
            df["open"] + df["high"] + df["low"] + df["close"]
        ) / 4

        ha_open_values = []

        for i in range(len(df)):
            if i == 0:
                ha_open_values.append((df.iloc[i]["open"] + df.iloc[i]["close"]) / 2)
            else:
                ha_open_values.append((ha_open_values[i - 1] + ha_close.iloc[i - 1]) / 2)

        last_ha_open = float(ha_open_values[-1])
        last_ha_close = float(ha_close.iloc[-1])

        if last_ha_close > last_ha_open:
            return "BUY"

        if last_ha_close < last_ha_open:
            return "SELL"

        return None

    except Exception as e:
        logger.error(f"[INTRABAR M5 FILTER] Heikin Ashi failed: {e}")
        return None


def calculate_parabolic_sar_direction(df, step=0.02, max_step=0.20):
    if df is None or len(df) < 10:
        return None

    try:
        high = df["high"].astype(float).tolist()
        low = df["low"].astype(float).tolist()
        close = df["close"].astype(float).tolist()

        trend = "BUY" if close[1] > close[0] else "SELL"
        af = step
        ep = high[0] if trend == "BUY" else low[0]
        sar = low[0] if trend == "BUY" else high[0]

        for i in range(1, len(df)):
            previous_sar = sar

            if trend == "BUY":
                sar = previous_sar + af * (ep - previous_sar)

                if low[i] < sar:
                    trend = "SELL"
                    sar = ep
                    ep = low[i]
                    af = step
                else:
                    if high[i] > ep:
                        ep = high[i]
                        af = min(af + step, max_step)

            else:
                sar = previous_sar + af * (ep - previous_sar)

                if high[i] > sar:
                    trend = "BUY"
                    sar = ep
                    ep = high[i]
                    af = step
                else:
                    if low[i] < ep:
                        ep = low[i]
                        af = min(af + step, max_step)

        last_close = close[-1]

        if last_close > sar:
            return "BUY"

        if last_close < sar:
            return "SELL"

        return None

    except Exception as e:
        logger.error(f"[INTRABAR M5 FILTER] PSAR failed: {e}")
        return None


def intrabar_m5_confirmation_ok(signal, strategy_name):
    if not ENABLE_INTRABAR_M5_CONFIRMATION_FILTERS:
        return True, "intrabar_m5_filters_disabled"

    strategy_key = str(strategy_name or "").upper()

    if strategy_key not in INTRABAR_M5_CONFIRMATION_STRATEGIES:
        return True, "strategy_not_using_intrabar_m5_filters"

    rates = mt5.copy_rates_from_pos(
        SYMBOL,
        INTRABAR_M5_CONFIRMATION_TIMEFRAME,
        0,
        INTRABAR_M5_CONFIRMATION_BARS,
    )

    if rates is None or len(rates) < 10:
        return False, "m5_rates_unavailable"

    m5_df = pd.DataFrame(rates)

    confirmations = []

    if INTRABAR_M5_USE_HEIKIN_ASHI:
        ha_direction = calculate_heikin_ashi_direction(m5_df)
        confirmations.append(ha_direction == signal)

    if INTRABAR_M5_USE_PARABOLIC_SAR:
        psar_direction = calculate_parabolic_sar_direction(
            m5_df,
            step=INTRABAR_M5_PSAR_STEP,
            max_step=INTRABAR_M5_PSAR_MAX_STEP,
        )
        confirmations.append(psar_direction == signal)

    if not confirmations:
        return True, "no_intrabar_m5_filters_enabled"

    strict_m5_strategy = strategy_key in [
        "FAILED_FVG_REVERSAL",
    ]

    if strict_m5_strategy:
        passed = all(confirmations)
    elif INTRABAR_M5_REQUIRE_ALL_FILTERS:
        passed = all(confirmations)
    else:
        passed = any(confirmations)

    if passed:
        return True, "intrabar_m5_filters_confirmed"

    return False, "intrabar_m5_filters_rejected"

def find_recent_intrabar_fvg_zones(df, lookback_bars=20):
    if df is None or len(df) < 5:
        return {}

    start_index = max(2, len(df) - lookback_bars)
    bullish_fvg = None
    bearish_fvg = None

    for i in range(start_index, len(df)):
        c0 = df.iloc[i - 2]
        c2 = df.iloc[i]

        # Bullish FVG: gap between old high and newer low
        if float(c2["low"]) > float(c0["high"]):
            bullish_fvg = {
                "bottom": float(c0["high"]),
                "top": float(c2["low"]),
                "mid": round((float(c0["high"]) + float(c2["low"])) / 2, 2),
            }

        # Bearish FVG: gap between newer high and old low
        if float(c2["high"]) < float(c0["low"]):
            bearish_fvg = {
                "bottom": float(c2["high"]),
                "top": float(c0["low"]),
                "mid": round((float(c2["high"]) + float(c0["low"])) / 2, 2),
            }

    return {
        "bullish_fvg": bullish_fvg,
        "bearish_fvg": bearish_fvg,
    }

def get_fvg_zone(candidate):
    fvg_top = (
        candidate.get("fvg_top")
        or candidate.get("ifvg_top")
        or candidate.get("failed_fvg_top")
    )

    fvg_bottom = (
        candidate.get("fvg_bottom")
        or candidate.get("ifvg_bottom")
        or candidate.get("failed_fvg_bottom")
    )

    if fvg_top is None or fvg_bottom is None:
        return None, None

    top = max(float(fvg_top), float(fvg_bottom))
    bottom = min(float(fvg_top), float(fvg_bottom))

    return top, bottom


def build_fvg_staged_entry_prices(signal, fvg_top, fvg_bottom):
    fvg_height = abs(float(fvg_top) - float(fvg_bottom))

    if signal == "BUY":
        return [
            round(float(fvg_top), 2),
            round(float(fvg_top) - fvg_height * 0.60, 2),
            round(float(fvg_top) - fvg_height * 0.85, 2),
        ]

    if signal == "SELL":
        return [
            round(float(fvg_bottom), 2),
            round(float(fvg_bottom) + fvg_height * 0.60, 2),
            round(float(fvg_bottom) + fvg_height * 0.85, 2),
        ]

    return []


def should_use_fvg_zone_staged_entry(strategy_name, signal_data):
    if not ENABLE_FVG_ZONE_STAGED_ENTRY:
        return False

    strategy_key = str(strategy_name or "").upper()

    if strategy_key not in FVG_ZONE_STAGED_ENTRY_STRATEGIES:
        return False

    fvg_top, fvg_bottom = get_fvg_zone(signal_data)

    return fvg_top is not None and fvg_bottom is not None

def fvg_stage_price_reached(signal, tick, target_entry):
    if signal == "BUY":
        return float(tick.ask) <= float(target_entry)

    if signal == "SELL":
        return float(tick.bid) >= float(target_entry)

    return False


def get_fvg_stage_execution_price(signal, tick):
    if signal == "BUY":
        return float(tick.ask)

    if signal == "SELL":
        return float(tick.bid)

    return None


def process_wait_fvg_staged_entry_setups(df, tick, account_info, market_condition, session_name):
    staged_setups = execution_engine.get_wait_fvg_staged_entry_setups()

    if not staged_setups:
        return False

    for setup in staged_setups:
        setup_data = setup.get("data", {})
        strategy_name = setup_data.get("strategy")
        signal = setup_data.get("signal")
        setup_id = setup_data.get("setup_id")

        stages = setup.get("fvg_staged_entries", [])

        for stage in stages:
            if stage.get("executed"):
                continue

            target_entry = stage.get("target_entry")

            if not fvg_stage_price_reached(signal, tick, target_entry):
                continue

            execution_price = get_fvg_stage_execution_price(signal, tick)

            trade_plan = dict(setup_data.get("fvg_staged_trade_plan", {}))
            trade_plan["entry_price"] = round(execution_price, 2)
            trade_plan["lot"] = stage.get("lot")
            trade_plan["setup_id"] = f"{setup_id}-{stage.get('stage_name')}"
            trade_plan["role"] = stage.get("stage_name")
            trade_plan["reason"] = (
                f"{setup_data.get('reason', 'N/A')} | "
                f"FVG_STAGED_ENTRY {stage.get('stage_name')} "
                f"target={target_entry}"
            )

            logger.info(
                f"[FVG STAGED ENTRY] Executing | "
                f"setup_id={setup_id} stage={stage.get('stage_name')} "
                f"target={target_entry} execution_price={execution_price}"
            )

            send_telegram_message(
                f"🔥 FVG Staged Entry Executing\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n"
                f"Setup ID: {setup_id}\n"
                f"Stage: {stage.get('stage_name')}\n\n"
                f"Target Entry: {target_entry}\n"
                f"Execution Entry: {trade_plan['entry_price']}\n"
                f"SL: {trade_plan['stop_loss']}\n"
                f"TP1 / Execution TP: {trade_plan['take_profit']}\\n"
                f"Original TP: {trade_plan.get('original_take_profit', trade_plan['take_profit'])}\\n"
                f"TP Plan: {trade_plan.get('tp_plan_summary', 'standard')}\\n"
                f"Lot: {trade_plan['lot']}"
            )

            log_setup_event(
                setup_id=trade_plan.get("setup_id"),
                event="FVG_STAGED_ENTRY_EXECUTION_ATTEMPT",
                strategy=strategy_name,
                signal=signal,
                entry_model=setup_data.get("entry_model"),
                score=setup_data.get("score"),
                session=session_name,
                market_condition=market_condition,
                entry=trade_plan.get("entry_price"),
                sl=trade_plan.get("stop_loss"),
                tp=trade_plan.get("take_profit"),
                reason=f"FVG staged entry {stage.get('stage_name')}",
                extra={
                    "parent_setup_id": setup_id,
                    "stage": stage,
                },
            )
            
            save_execution_memory_report(
                selected_signal_data=setup_data,
                strategy_name=strategy_name,
                signal=signal,
                score=setup_data.get("score"),
                session_name=session_name,
                market_condition=market_condition,
                reason=f"FVG staged entry {stage.get('stage_name')}",
                trade_plan=trade_plan,
                decision="FVG_STAGED_ENTRY_EXECUTION_ATTEMPT",
                decision_reason="sending FVG staged entry order to MT5",
                rr_value=None,
                required_rr=None,
                extra={
                    "parent_setup_id": setup_id,
                    "stage": stage,
                    "stage_name": stage.get("stage_name"),
                },
            )
            
            apply_strategy_advisory_note(
                signal_data=setup_data,
                strategy_name=strategy_name,
                setup_source_bucket="FVG_STAGED",
            )

            observe_universal_confirmation_from_scope(
                locals(),
                setup_source_bucket_override="FVG_STAGED",
            )

            _live_execute_start_ts = time.perf_counter()
            logger.info(
                f"[LIVE EXECUTION TIMING] stage=before_execute_trade "
                f"symbol={SYMBOL} signal={signal} "
                f"setup_id={trade_plan.get('setup_id') if isinstance(trade_plan, dict) else None} "
                f"strategy={trade_plan.get('strategy') if isinstance(trade_plan, dict) else None}"
            )
            execution_result = execute_trade(signal, trade_plan, SYMBOL)
            logger.info(
                f"[LIVE EXECUTION TIMING] stage=after_execute_trade "
                f"elapsed_ms={round((time.perf_counter() - _live_execute_start_ts) * 1000, 2)} "
                f"symbol={SYMBOL} signal={signal} result={execution_result}"
            )

            if execution_result:
                save_execution_memory_report(
                    selected_signal_data=setup_data,
                    strategy_name=strategy_name,
                    signal=signal,
                    score=setup_data.get("score"),
                    session_name=session_name,
                    market_condition=market_condition,
                    reason=f"FVG staged entry {stage.get('stage_name')}",
                    trade_plan=trade_plan,
                    decision="FVG_STAGED_ENTRY_EXECUTION_SUCCESS",
                    decision_reason="FVG staged entry MT5 order returned success",
                    rr_value=None,
                    required_rr=None,
                    execution_result=execution_result,
                    extra={
                        "parent_setup_id": setup_id,
                        "stage": stage,
                        "stage_name": stage.get("stage_name"),
                    },
                )

                stage["executed"] = True

                log_setup_event(
                    setup_id=trade_plan.get("setup_id"),
                    event="FVG_STAGED_ENTRY_EXECUTED",
                    strategy=strategy_name,
                    signal=signal,
                    entry_model=setup_data.get("entry_model"),
                    score=setup_data.get("score"),
                    session=session_name,
                    market_condition=market_condition,
                    entry=trade_plan.get("entry_price"),
                    sl=trade_plan.get("stop_loss"),
                    tp=trade_plan.get("take_profit"),
                    reason=f"FVG staged entry executed {stage.get('stage_name')}",
                    extra={
                        "parent_setup_id": setup_id,
                        "stage": stage,
                    },
                )

                if all(item.get("executed") for item in stages):
                    execution_engine.mark_executed(setup)

                return True
            
            save_execution_memory_report(
                selected_signal_data=setup_data,
                strategy_name=strategy_name,
                signal=signal,
                score=setup_data.get("score"),
                session_name=session_name,
                market_condition=market_condition,
                reason="FVG staged entry execution failed",
                trade_plan=trade_plan,
                decision="FVG_STAGED_ENTRY_EXECUTION_FAILED",
                decision_reason="FVG staged entry execute_trade returned False",
                rr_value=None,
                required_rr=None,
                execution_result=execution_result,
                extra={
                    "parent_setup_id": setup_id,
                    "stage": stage,
                    "stage_name": stage.get("stage_name"),
                },
            )

            log_setup_event(
                setup_id=trade_plan.get("setup_id"),
                event="FVG_STAGED_ENTRY_EXECUTION_FAILED",
                strategy=strategy_name,
                signal=signal,
                entry_model=setup_data.get("entry_model"),
                score=setup_data.get("score"),
                session=session_name,
                market_condition=market_condition,
                entry=trade_plan.get("entry_price"),
                sl=trade_plan.get("stop_loss"),
                tp=trade_plan.get("take_profit"),
                reason="execute_trade returned False",
                extra={
                    "parent_setup_id": setup_id,
                    "stage": stage,
                },
            )

            return True

    return False

def continuation_requires_retrace_first(strategy_name, entry_model, rr_value):
    if not ENABLE_CONTINUATION_SAFETY_GUARD:
        return False

    strategy_key = str(strategy_name or "").upper()
    entry_key = str(entry_model or "").upper()

    if strategy_key not in CONTINUATION_SAFETY_RETRACE_FIRST_STRATEGIES:
        return False

    if entry_key not in CONTINUATION_SAFETY_RETRACE_FIRST_ENTRY_MODELS:
        return False

    if rr_value is None:
        return True

    return float(rr_value) < CONTINUATION_SAFETY_MIN_IMMEDIATE_RR

def get_mtf_conflict_strategy_mode(strategy):
    strategy_key = str(strategy or "").upper()

    if strategy_key in MTF_CONFLICT_TRACK_ONLY_STRATEGIES:
        return "TRACK_ONLY"

    if strategy_key in MTF_CONFLICT_RETRACE_FIRST_STRATEGIES:
        return "RETRACE_FIRST"

    if strategy_key in MTF_CONFLICT_SOFT_EXECUTION_STRATEGIES:
        return "SOFT_EXECUTION"

    return "TRACK_ONLY"

def is_mtf_conflict_rejection(reason):
    return str(reason or "").lower().startswith("mtf_conflict")


def extract_mtf_bias_from_rejection(reason):
    reason_text = str(reason or "")

    if "bias=BUY" in reason_text:
        return "BUY"

    if "bias=SELL" in reason_text:
        return "SELL"

    return None


def get_current_mtf_conflict_price(signal, tick):
    if tick is None:
        return None

    try:
        if signal == "BUY":
            return float(tick.ask)

        if signal == "SELL":
            return float(tick.bid)
    except Exception:
        return None

    return None


def has_mtf_aligned_position(symbol, mtf_bias):
    if mtf_bias not in ["BUY", "SELL"]:
        return False

    try:
        from src.position_guard import has_same_direction_position

        return has_same_direction_position(symbol, mtf_bias)
    except Exception as e:
        logger.error(f"[MTF CONFLICT] Failed to check MTF-aligned position: {e}")
        return False


def get_mtf_conflict_execution_mode(mtf_bias):
    if has_mtf_aligned_position(SYMBOL, mtf_bias):
        return "COUNTER_MTF_SCALP"

    return "COUNTER_MTF_CALCULATED"


def mtf_conflict_soft_execution_allowed(
    *,
    candidate,
    signal,
    mtf_bias,
    shadow_trade_plan,
    shadow_rr,
    required_rr,
    execution_mode,
):
    if not ENABLE_MTF_CONFLICT_SOFT_EXECUTION:
        return False, "disabled"

    strategy = str(candidate.get("strategy", "") or "").upper()

    strategy_mode = get_mtf_conflict_strategy_mode(strategy)

    if strategy_mode == "TRACK_ONLY":
        return False, "track_only_strategy"

    if strategy_mode == "RETRACE_FIRST":
        return False, "retrace_first_required"

    if strategy_mode != "SOFT_EXECUTION":
        return False, "strategy_not_allowed"

    try:
        score = float(candidate.get("score", 0) or 0)
    except Exception:
        score = 0

    if score < MTF_CONFLICT_SOFT_EXECUTION_MIN_SCORE:
        return False, "score_too_low"

    if signal not in ["BUY", "SELL"]:
        return False, "invalid_signal"

    if mtf_bias not in ["BUY", "SELL"]:
        return False, "invalid_mtf_bias"

    if signal == mtf_bias:
        return False, "not_counter_mtf"

    if MTF_CONFLICT_REQUIRE_SHADOW_TRADE_PLAN and shadow_trade_plan is None:
        return False, "shadow_trade_plan_missing"

    if execution_mode == "COUNTER_MTF_CALCULATED":
        if not MTF_CONFLICT_USE_CALCULATED_TP_WHEN_NO_MTF_POSITION:
            return False, "calculated_mode_disabled"

        if MTF_CONFLICT_REQUIRE_SHADOW_RR_FOR_NORMAL_EXECUTION:
            if shadow_rr is None or required_rr is None:
                return False, "shadow_rr_missing"

            if float(shadow_rr) < float(required_rr):
                return False, f"shadow_rr_too_low {shadow_rr}/{required_rr}"

    if execution_mode == "COUNTER_MTF_SCALP":
        if not MTF_CONFLICT_SCALP_ONLY_WHEN_MTF_POSITION_EXISTS:
            return False, "scalp_mode_disabled"

        if MTF_CONFLICT_REQUIRE_SHADOW_RR_FOR_SCALP:
            if shadow_rr is None or required_rr is None:
                return False, "shadow_rr_missing_for_scalp"

            if float(shadow_rr) < float(required_rr):
                return False, f"shadow_rr_too_low_for_scalp {shadow_rr}/{required_rr}"

    if MTF_CONFLICT_REQUIRE_M5_CONFIRMATION:
        confirmed, confirm_reason = extra_entry_confirmation_ok(signal)

        if not confirmed:
            return False, f"m5_confirmation_failed {confirm_reason}"

    return True, "allowed"


def build_mtf_conflict_calculated_trade_plan(
    *,
    candidate,
    signal,
    shadow_trade_plan,
    setup_id,
):
    if shadow_trade_plan is None:
        return None, "shadow_trade_plan_missing"

    trade_plan = shadow_trade_plan.copy()
    trade_plan["setup_id"] = f"{setup_id}-MTFOVERRIDE"
    trade_plan["strategy"] = "MTF_CONFLICT_SOFT_EXECUTION"
    trade_plan["source_strategy"] = candidate.get("strategy")
    trade_plan["signal"] = signal
    trade_plan["entry_model"] = (
        f"MTF_CONFLICT_CALCULATED_{candidate.get('entry_model', 'UNKNOWN')}"
    )
    trade_plan["comment"] = "MtfConflictCalc"
    trade_plan["is_mtf_conflict_soft_execution"] = True
    trade_plan["reason"] = (
        f"{trade_plan.get('reason', candidate.get('reason', 'N/A'))} | "
        f"MTF_CONFLICT_SOFT_EXECUTION calculated TP/SL"
    )

    return trade_plan, "ready"


def build_mtf_conflict_scalp_trade_plan(
    *,
    candidate,
    signal,
    tick,
    shadow_trade_plan,
    setup_id,
):
    if shadow_trade_plan is None:
        return None, "shadow_trade_plan_missing"

    entry = get_current_mtf_conflict_price(signal, tick)

    if entry is None:
        return None, "invalid_entry"

    entry = round(float(entry), 2)

    if signal == "BUY":
        sl = round(entry - MTF_CONFLICT_COUNTER_SCALP_SL_PRICE, 2)
        tp = round(entry + MTF_CONFLICT_COUNTER_SCALP_TP_PRICE, 2)

    elif signal == "SELL":
        sl = round(entry + MTF_CONFLICT_COUNTER_SCALP_SL_PRICE, 2)
        tp = round(entry - MTF_CONFLICT_COUNTER_SCALP_TP_PRICE, 2)

    else:
        return None, "invalid_signal"

    original_lot = float(shadow_trade_plan.get("lot", 0.0) or 0.0)

    if original_lot <= 0:
        return None, "invalid_original_lot"

    lot = round(original_lot * MTF_CONFLICT_COUNTER_SCALP_LOT_MULTIPLIER, 2)

    if lot <= 0:
        return None, "invalid_lot"

    trade_plan = shadow_trade_plan.copy()
    trade_plan["setup_id"] = f"{setup_id}-MTFSCALP"
    trade_plan["strategy"] = "MTF_CONFLICT_COUNTER_SCALP"
    trade_plan["source_strategy"] = candidate.get("strategy")
    trade_plan["signal"] = signal
    trade_plan["entry_model"] = (
        f"MTF_CONFLICT_SCALP_{candidate.get('entry_model', 'UNKNOWN')}"
    )
    trade_plan["entry_price"] = entry
    trade_plan["stop_loss"] = sl
    trade_plan["take_profit"] = tp
    trade_plan["stop_distance"] = MTF_CONFLICT_COUNTER_SCALP_SL_PRICE
    trade_plan["lot"] = lot
    trade_plan["comment"] = "MtfConflictScalp"
    trade_plan["is_mtf_conflict_counter_scalp"] = True
    trade_plan["reason"] = (
        f"MTF conflict counter scalp | "
        f"source={candidate.get('strategy')} | "
        f"fixed_tp={MTF_CONFLICT_COUNTER_SCALP_TP_PRICE} | "
        f"fixed_sl={MTF_CONFLICT_COUNTER_SCALP_SL_PRICE}"
    )

    return trade_plan, "ready"

def get_mtf_conflict_setup_id(candidate, signal, tick):
    existing_setup_id = candidate.get("setup_id")

    if existing_setup_id:
        return existing_setup_id

    strategy = candidate.get("strategy", "MTF")
    tick_time = getattr(tick, "time", None)

    if tick_time:
        return build_setup_id(strategy, signal, tick_time)

    return f"MTF-{strategy}-{signal}-{datetime.utcnow().timestamp()}"

def is_mtf_conflict_candidate_already_tracked(setup_id, rejection_reason, execution_mode, ttl_seconds=900):
    if not setup_id:
        return False

    now_ts = datetime.utcnow().timestamp()

    expired_keys = [
        key for key, seen_ts in MTF_CONFLICT_TRACKED_CACHE.items()
        if now_ts - seen_ts > ttl_seconds
    ]

    for key in expired_keys:
        MTF_CONFLICT_TRACKED_CACHE.pop(key, None)

    key = f"{setup_id}|{rejection_reason}|{execution_mode}"

    if key in MTF_CONFLICT_TRACKED_CACHE:
        return True

    MTF_CONFLICT_TRACKED_CACHE[key] = now_ts
    return False

def process_mtf_conflict_candidate(
    *,
    candidate,
    rejection_reason,
    df,
    tick,
    account_info,
    market_condition,
    session_name,
):
    signal = candidate.get("signal")
    strategy = candidate.get("strategy")
    entry_model = candidate.get("entry_model")
    mtf_bias = extract_mtf_bias_from_rejection(rejection_reason)

    setup_id = get_mtf_conflict_setup_id(candidate, signal, tick)
    price_at_rejection = get_current_mtf_conflict_price(signal, tick)

    shadow_trade_plan = calculate_trade_plan(
        df=df,
        signal=signal,
        tick=tick,
        account_balance=account_info.balance,
        signal_data=candidate,
    )

    shadow_rr = None
    required_rr = None
    
    if shadow_trade_plan is None:
        logger.info(
            f"[MTF CONFLICT] shadow trade plan failed | "
            f"setup_id={setup_id} strategy={strategy} signal={signal} "
            f"entry_price={price_at_rejection} "
            f"sl_reference={candidate.get('sl_reference')} "
            f"tp_reference={candidate.get('tp_reference')} "
            f"entry_model={entry_model}"
        )

    if shadow_trade_plan is not None:
        shadow_trade_plan["score"] = candidate.get("score", 0)
        shadow_trade_plan["strategy"] = strategy
        shadow_trade_plan["market_condition"] = market_condition
        shadow_trade_plan["reason"] = candidate.get("reason", "N/A")
        shadow_trade_plan["session"] = candidate.get("session", session_name)
        shadow_trade_plan["setup_id"] = setup_id

        shadow_rr = calculate_rr_value(shadow_trade_plan)

        required_rr = get_min_rr(
            strategy,
            candidate.get("entry_model"),
            candidate.get("sl_model"),
        )

    execution_mode = get_mtf_conflict_execution_mode(mtf_bias)

    execution_allowed, execution_reason = mtf_conflict_soft_execution_allowed(
        candidate=candidate,
        signal=signal,
        mtf_bias=mtf_bias,
        shadow_trade_plan=shadow_trade_plan,
        shadow_rr=shadow_rr,
        required_rr=required_rr,
        execution_mode=execution_mode,
    )
    
    strategy_mode = get_mtf_conflict_strategy_mode(strategy)

    recovery_registered = False

    if strategy_mode == "RETRACE_FIRST":
        recovery_registered = register_rejected_candidate_for_recovery(
            symbol=SYMBOL,
            signal=signal,
            strategy=strategy,
            score=candidate.get("score", 0),
            reason_type="MTF_CONFLICT_RETRACE_FIRST",
            rejection_reason=rejection_reason,
            signal_data=candidate,
            required_rr=required_rr,
            current_rr=shadow_rr,
        )

    register_mtf_conflict_opportunity(
        symbol=SYMBOL,
        setup_id=setup_id,
        strategy=strategy,
        signal=signal,
        entry_model=entry_model,
        score=candidate.get("score"),
        session=session_name,
        market_condition=market_condition,
        mtf_bias=mtf_bias,
        rejection_reason=rejection_reason,
        price_at_rejection=price_at_rejection,
        shadow_trade_plan=shadow_trade_plan,
        shadow_rr=shadow_rr,
        shadow_required_rr=required_rr,
        execution_mode=execution_mode,
        execution_allowed=execution_allowed,
        execution_reason=execution_reason,
    )

    already_tracked = is_mtf_conflict_candidate_already_tracked(
        setup_id,
        rejection_reason,
        execution_mode,
    )

    if already_tracked:
        logger.info(
            f"[MTF CONFLICT] Duplicate tracked candidate skipped | "
            f"setup_id={setup_id} strategy={strategy} signal={signal} "
            f"mode={execution_mode} reason={execution_reason}"
        )

        if not execution_allowed:
            return False

    else:
        log_setup_event(
            setup_id=setup_id,
            event="MTF_CONFLICT_CANDIDATE_TRACKED",
            strategy=strategy,
            signal=signal,
            entry_model=entry_model,
            score=candidate.get("score"),
            session=session_name,
            market_condition=market_condition,
            entry=shadow_trade_plan.get("entry_price") if shadow_trade_plan else None,
            sl=shadow_trade_plan.get("stop_loss") if shadow_trade_plan else None,
            tp=shadow_trade_plan.get("take_profit") if shadow_trade_plan else None,
            rr=shadow_rr,
            required_rr=required_rr,
            reason=rejection_reason,
            extra={
                "mtf_bias": mtf_bias,
                "strategy_mode": strategy_mode,
                "recovery_registered": recovery_registered,
                "mtf_conflict_mode": execution_mode,
                "price_at_rejection": price_at_rejection,
                "shadow_entry": shadow_trade_plan.get("entry_price") if shadow_trade_plan else None,
                "shadow_sl": shadow_trade_plan.get("stop_loss") if shadow_trade_plan else None,
                "shadow_tp": shadow_trade_plan.get("take_profit") if shadow_trade_plan else None,
                "shadow_rr": shadow_rr,
                "shadow_required_rr": required_rr,
                "execution_allowed": execution_allowed,
                "execution_reason": execution_reason,
            },
        )

        news_context = attach_news_context_to_signal_data(candidate)

        tracked = register_setup_outcome(
            symbol=SYMBOL,
            setup_id=setup_id,
            event="MTF_CONFLICT_CANDIDATE_TRACKED",
            strategy=strategy,
            signal=signal,
            entry_model=entry_model,
            score=candidate.get("score"),
            session=session_name,
            market_condition=market_condition,
            entry=shadow_trade_plan.get("entry_price") if shadow_trade_plan else None,
            sl=shadow_trade_plan.get("stop_loss") if shadow_trade_plan else None,
            tp=shadow_trade_plan.get("take_profit") if shadow_trade_plan else None,
            reason=rejection_reason,
            extra={
                "mtf_bias": mtf_bias,
                "strategy_mode": strategy_mode,
                "shadow_rr": shadow_rr,
                "required_rr": required_rr,
                "execution_allowed": execution_allowed,
                "execution_reason": execution_reason,
                "source": "mtf_conflict_candidate_tracked",
                "news_context": news_context,
                "news_tag": news_context.get("news_tag") if news_context else None,
            },
        )

        try:
            observe_universal_confirmation_from_scope(
                locals(),
                setup_source_bucket_override="MTF_CONFLICT_TRACKED",
            )
            mtf_conflict_tracked_confirmation_observed = True
        except Exception as confirmation_exc:
            logger.warning(
                f"[MTF CONFLICT] Confirmation observation failed for tracked setup | "
                f"setup_id={setup_id} error={confirmation_exc}"
            )


        if tracked:
            notify_setup_similarity_if_relevant(setup_id)
            notify_scenario_cluster_if_relevant(setup_id)

            try:
                candidate_score = float(candidate.get("score", 0) or 0)
            except Exception:
                candidate_score = 0.0

            try:
                shadow_rr_value = float(shadow_rr or 0)
            except Exception:
                shadow_rr_value = 0.0

            good_rr_mtf_candidate = (
                candidate_score >= MTF_CONFLICT_CANDIDATE_TELEGRAM_MIN_SCORE
                and shadow_rr_value >= MTF_CONFLICT_CANDIDATE_TELEGRAM_MIN_RR
            )

            high_score_mtf_candidate = (
                candidate_score >= MTF_CONFLICT_CANDIDATE_TELEGRAM_HIGH_SCORE
            )

            strong_mtf_candidate = (
                TELEGRAM_NOTIFY_MTF_CONFLICT_CANDIDATE_TRACKED
                and (
                    good_rr_mtf_candidate
                    or high_score_mtf_candidate
                )
            )

            if strong_mtf_candidate:
                send_telegram_message_async(
                    "📌 STRONG MTF CONFLICT TRACKED\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Setup ID: {setup_id}\n"
                    f"Strategy: {strategy}\n"
                    f"Signal: {signal}\n"
                    f"Entry Model: {entry_model}\n"
                    f"Session: {session_name}\n"
                    f"Market: {market_condition}\n"
                    f"Score: {candidate_score}\n"
                    f"MTF Bias: {mtf_bias}\n"
                    f"Strategy Mode: {strategy_mode}\n"
                    f"Execution Mode: {execution_mode}\n"
                    f"Execution Allowed: {execution_allowed}\n"
                    f"Execution Reason: {execution_reason}\n\n"
                    f"Telegram Trigger: {'GOOD_RR' if good_rr_mtf_candidate else 'HIGH_SCORE'}\n"
                    f"Entry: {shadow_trade_plan.get('entry_price') if shadow_trade_plan else None}\n"
                    f"SL: {shadow_trade_plan.get('stop_loss') if shadow_trade_plan else None}\n"
                    f"TP: {shadow_trade_plan.get('take_profit') if shadow_trade_plan else None}\n"
                    f"RR: {shadow_rr}\n"
                    f"Required RR: {required_rr}\n\n"
                    "Action: tracked due to MTF conflict — not automatically weak."
                )

        if not execution_allowed:
            logger.info(
                f"[MTF CONFLICT] Tracked only | "
                f"setup_id={setup_id} strategy={strategy} signal={signal} "
                f"mode={execution_mode} reason={execution_reason}"
            )
            return False

    if execution_mode == "COUNTER_MTF_SCALP":
        mtf_trade_plan, plan_reason = build_mtf_conflict_scalp_trade_plan(
            candidate=candidate,
            signal=signal,
            tick=tick,
            shadow_trade_plan=shadow_trade_plan,
            setup_id=setup_id,
        )

        mtf_rr = round(
            MTF_CONFLICT_COUNTER_SCALP_TP_PRICE / MTF_CONFLICT_COUNTER_SCALP_SL_PRICE,
            2,
        )

        event_attempt = "MTF_CONFLICT_COUNTER_SCALP_EXECUTION_ATTEMPT"
        event_success = "MTF_CONFLICT_COUNTER_SCALP_EXECUTED"
        event_failed = "MTF_CONFLICT_COUNTER_SCALP_EXECUTION_FAILED"

    else:
        mtf_trade_plan, plan_reason = build_mtf_conflict_calculated_trade_plan(
            candidate=candidate,
            signal=signal,
            shadow_trade_plan=shadow_trade_plan,
            setup_id=setup_id,
        )

        mtf_rr = shadow_rr

        event_attempt = "MTF_CONFLICT_OVERRIDE_EXECUTION_ATTEMPT"
        event_success = "MTF_CONFLICT_OVERRIDE_EXECUTED"
        event_failed = "MTF_CONFLICT_OVERRIDE_EXECUTION_FAILED"

    if mtf_trade_plan is None:
        logger.info(
            f"[MTF CONFLICT] Trade plan refused | "
            f"setup_id={setup_id} strategy={strategy} signal={signal} "
            f"mode={execution_mode} reason={plan_reason}"
        )

        mark_mtf_conflict_opportunity_failed(setup_id, plan_reason)

        log_setup_event(
            setup_id=setup_id,
            event="MTF_CONFLICT_EXECUTION_PLAN_REFUSED",
            strategy=strategy,
            signal=signal,
            entry_model=entry_model,
            score=candidate.get("score"),
            session=session_name,
            market_condition=market_condition,
            rr=shadow_rr,
            required_rr=required_rr,
            reason=plan_reason,
            extra={
                "mtf_bias": mtf_bias,
                "mtf_conflict_mode": execution_mode,
            },
        )

        return False

    trade_allowed, guard_reason = check_trade_guard(signal, tick)

    if not trade_allowed:
        logger.info(
            f"[MTF CONFLICT] Guard blocked | "
            f"setup_id={setup_id} strategy={strategy} signal={signal} "
            f"reason={guard_reason}"
        )

        mark_mtf_conflict_opportunity_failed(setup_id, guard_reason)

        log_setup_event(
            setup_id=mtf_trade_plan.get("setup_id"),
            event="MTF_CONFLICT_EXECUTION_BLOCKED",
            strategy=mtf_trade_plan.get("strategy"),
            signal=signal,
            entry_model=mtf_trade_plan.get("entry_model"),
            score=candidate.get("score"),
            session=session_name,
            market_condition=market_condition,
            entry=mtf_trade_plan.get("entry_price"),
            sl=mtf_trade_plan.get("stop_loss"),
            tp=mtf_trade_plan.get("take_profit"),
            rr=mtf_rr,
            required_rr=required_rr,
            reason=guard_reason,
            extra={
                "source_setup_id": setup_id,
                "source_strategy": strategy,
                "mtf_bias": mtf_bias,
                "mtf_conflict_mode": execution_mode,
            },
        )

        return False

    news_blocked, news_reason = is_news_blackout_active()

    if news_blocked:
        logger.info(
            f"[MTF CONFLICT] News blocked | "
            f"setup_id={setup_id} reason={news_reason}"
        )
        return False

    time_blocked, time_reason = is_trading_blackout_active()

    if time_blocked:
        logger.info(
            f"[MTF CONFLICT] Time blocked | "
            f"setup_id={setup_id} reason={time_reason}"
        )
        return False

    if is_trade_blocked_by_execution_memory(
        trade_plan=mtf_trade_plan,
        signal_data=candidate,
        setup=None,
        strategy_name=mtf_trade_plan.get("strategy"),
        signal=signal,
    ):
        save_execution_memory_report(
            selected_signal_data=candidate,
            strategy_name=mtf_trade_plan.get("strategy"),
            signal=signal,
            score=candidate.get("score"),
            session_name=session_name,
            market_condition=market_condition,
            reason=rejection_reason,
            trade_plan=mtf_trade_plan,
            decision="MTF_CONFLICT_BLOCKED_BY_MEMORY",
            decision_reason="MTF conflict execution skipped by execution memory",
            rr_value=mtf_rr,
            required_rr=required_rr,
            extra={
                "source_setup_id": setup_id,
                "source_strategy": strategy,
                "mtf_bias": mtf_bias,
                "mtf_conflict_mode": execution_mode,
            },
        )

        mark_mtf_conflict_opportunity_failed(
            setup_id,
            "Skipped by execution memory",
        )
        return False

    send_telegram_message(
        f"⚡ MTF Conflict Execution\n"
        f"Symbol: {SYMBOL}\n"
        f"Mode: {execution_mode}\n"
        f"Source Strategy: {strategy}\n"
        f"Signal: {signal}\n"
        f"MTF Bias: {mtf_bias}\n"
        f"Setup ID: {setup_id}\n\n"
        f"Entry: {mtf_trade_plan['entry_price']}\n"
        f"SL: {mtf_trade_plan['stop_loss']}\n"
        f"TP: {mtf_trade_plan['take_profit']}\n"
        f"RR: {mtf_rr}\n"
        f"Lot: {mtf_trade_plan['lot']}"
    )

    log_setup_event(
        setup_id=mtf_trade_plan.get("setup_id"),
        event=event_attempt,
        strategy=mtf_trade_plan.get("strategy"),
        signal=signal,
        entry_model=mtf_trade_plan.get("entry_model"),
        score=candidate.get("score"),
        session=session_name,
        market_condition=market_condition,
        entry=mtf_trade_plan.get("entry_price"),
        sl=mtf_trade_plan.get("stop_loss"),
        tp=mtf_trade_plan.get("take_profit"),
        rr=mtf_rr,
        required_rr=required_rr,
        reason=mtf_trade_plan.get("reason"),
        extra={
            "source_setup_id": setup_id,
            "source_strategy": strategy,
            "mtf_bias": mtf_bias,
            "mtf_conflict_mode": execution_mode,
            "shadow_entry": shadow_trade_plan.get("entry_price") if shadow_trade_plan else None,
            "shadow_sl": shadow_trade_plan.get("stop_loss") if shadow_trade_plan else None,
            "shadow_tp": shadow_trade_plan.get("take_profit") if shadow_trade_plan else None,
            "shadow_rr": shadow_rr,
            "shadow_required_rr": required_rr,
        },
    )
    
    logger.warning(
        f"[MTF CONFLICT] Calling execute_trade | "
        f"source_setup_id={setup_id} "
        f"exec_setup_id={mtf_trade_plan.get('setup_id')} "
        f"source_strategy={strategy} "
        f"exec_strategy={mtf_trade_plan.get('strategy')} "
        f"signal={signal} "
        f"mode={execution_mode} "
        f"entry={mtf_trade_plan.get('entry_price')} "
        f"sl={mtf_trade_plan.get('stop_loss')} "
        f"tp={mtf_trade_plan.get('take_profit')} "
        f"lot={mtf_trade_plan.get('lot')} "
        f"rr={mtf_rr}"
    )
    
    save_execution_memory_report(
        selected_signal_data=candidate,
        strategy_name=mtf_trade_plan.get("strategy"),
        signal=signal,
        score=candidate.get("score"),
        session_name=session_name,
        market_condition=market_condition,
        reason=rejection_reason,
        trade_plan=mtf_trade_plan,
        decision="MTF_CONFLICT_EXECUTION_ATTEMPT",
        decision_reason="sending MTF conflict execution order to MT5",
        rr_value=mtf_rr,
        required_rr=required_rr,
        extra={
            "source_setup_id": setup_id,
            "source_strategy": strategy,
            "mtf_bias": mtf_bias,
            "mtf_conflict_mode": execution_mode,
        },
    )
    
    apply_strategy_advisory_note(
        signal_data=candidate,
        strategy_name=mtf_trade_plan.get("strategy") or strategy,
        setup_source_bucket="MTF_CONFLICT_TRACKED",
    )

    observe_universal_confirmation_from_scope(
        locals(),
        setup_source_bucket_override="MTF_CONFLICT_TRACKED",
    )

    _live_execute_start_ts = time.perf_counter()
    logger.info(
        f"[LIVE EXECUTION TIMING] stage=before_execute_trade "
        f"symbol={SYMBOL} signal={signal} "
        f"setup_id={mtf_trade_plan.get('setup_id') if isinstance(mtf_trade_plan, dict) else None} "
        f"strategy={mtf_trade_plan.get('strategy') if isinstance(mtf_trade_plan, dict) else None}"
    )
    execution_result = execute_trade(signal, mtf_trade_plan, SYMBOL)
    logger.info(
        f"[LIVE EXECUTION TIMING] stage=after_execute_trade "
        f"elapsed_ms={round((time.perf_counter() - _live_execute_start_ts) * 1000, 2)} "
        f"symbol={SYMBOL} signal={signal} result={execution_result}"
    )
    
    logger.warning(
        f"[MTF CONFLICT] execute_trade result | "
        f"source_setup_id={setup_id} "
        f"exec_setup_id={mtf_trade_plan.get('setup_id')} "
        f"result={execution_result}"
    )

    if execution_result:
        news_context = attach_news_context_to_signal_data(candidate)

        tracked = register_setup_outcome(
            symbol=SYMBOL,
            setup_id=setup_id,
            event="MTF_CONFLICT_EXECUTION_SUCCESS",
            strategy=mtf_trade_plan.get("strategy") or strategy,
            signal=signal,
            entry_model=candidate.get("entry_model"),
            score=candidate.get("score"),
            session=session_name,
            market_condition="MTF_CONFLICT_EXECUTED",
            entry=mtf_trade_plan.get("entry_price"),
            sl=mtf_trade_plan.get("stop_loss"),
            tp=mtf_trade_plan.get("take_profit"),
            reason="mtf_conflict_execution_success",
            extra={
                "source": "mtf_conflict_execution_success",
                "source_setup_id": setup_id,
                "executed_setup_id": mtf_trade_plan.get("setup_id"),
                "source_strategy": strategy,
                "execution_strategy": mtf_trade_plan.get("strategy"),
                "mtf_bias": mtf_bias,
                "mtf_conflict_mode": execution_mode,
                "mtf_rr": mtf_rr,
                "required_rr": required_rr,
                "news_context": news_context,
                "news_tag": news_context.get("news_tag") if news_context else None,
            },
        )

        if tracked:
            notify_setup_similarity_if_relevant(setup_id)
            notify_scenario_cluster_if_relevant(setup_id)
        
        save_execution_memory_report(
            selected_signal_data=candidate,
            strategy_name=mtf_trade_plan.get("strategy"),
            signal=signal,
            score=candidate.get("score"),
            session_name=session_name,
            market_condition=market_condition,
            reason="mtf_conflict_execution_success",
            trade_plan=mtf_trade_plan,
            decision="MTF_CONFLICT_EXECUTION_SUCCESS",
            decision_reason="MTF conflict MT5 order returned success",
            rr_value=mtf_rr,
            required_rr=required_rr,
            execution_result=execution_result,
            extra={
                "source_setup_id": setup_id,
                "source_strategy": strategy,
                "mtf_bias": mtf_bias,
                "mtf_conflict_mode": execution_mode,
            },
        )
        
        mark_mtf_conflict_opportunity_executed(
            setup_id,
            executed_setup_id=mtf_trade_plan.get("setup_id"),
            execution_mode=execution_mode,
        )

        log_setup_event(
            setup_id=mtf_trade_plan.get("setup_id"),
            event=event_success,
            strategy=mtf_trade_plan.get("strategy"),
            signal=signal,
            entry_model=mtf_trade_plan.get("entry_model"),
            score=candidate.get("score"),
            session=session_name,
            market_condition=market_condition,
            entry=mtf_trade_plan.get("entry_price"),
            sl=mtf_trade_plan.get("stop_loss"),
            tp=mtf_trade_plan.get("take_profit"),
            rr=mtf_rr,
            required_rr=required_rr,
            reason="mtf_conflict_execution_success",
            extra={
                "source_setup_id": setup_id,
                "source_strategy": strategy,
                "mtf_bias": mtf_bias,
                "mtf_conflict_mode": execution_mode,
            },
        )

        return True
    
    news_context = attach_news_context_to_signal_data(candidate)

    tracked = register_setup_outcome(
        symbol=SYMBOL,
        setup_id=setup_id,
        event="MTF_CONFLICT_EXECUTION_FAILED",
        strategy=mtf_trade_plan.get("strategy") or strategy,
        signal=signal,
        entry_model=candidate.get("entry_model"),
        score=candidate.get("score"),
        session=session_name,
        market_condition="MTF_CONFLICT_EXECUTION_FAILED",
        entry=mtf_trade_plan.get("entry_price"),
        sl=mtf_trade_plan.get("stop_loss"),
        tp=mtf_trade_plan.get("take_profit"),
        reason="mtf_conflict_execute_trade_returned_false",
        extra={
            "source": "mtf_conflict_execution_failed",
            "source_setup_id": setup_id,
            "executed_setup_id": mtf_trade_plan.get("setup_id"),
            "source_strategy": strategy,
            "execution_strategy": mtf_trade_plan.get("strategy"),
            "mtf_bias": mtf_bias,
            "mtf_conflict_mode": execution_mode,
            "mtf_rr": mtf_rr,
            "required_rr": required_rr,
            "news_context": news_context,
            "news_tag": news_context.get("news_tag") if news_context else None,
        },
    )

    if tracked:
        notify_setup_similarity_if_relevant(setup_id)
        notify_scenario_cluster_if_relevant(setup_id)
    
    save_execution_memory_report(
        selected_signal_data=candidate,
        strategy_name=mtf_trade_plan.get("strategy"),
        signal=signal,
        score=candidate.get("score"),
        session_name=session_name,
        market_condition=market_condition,
        reason="mtf_conflict_execution_failed",
        trade_plan=mtf_trade_plan,
        decision="MTF_CONFLICT_EXECUTION_FAILED",
        decision_reason="MTF conflict execute_trade returned False",
        rr_value=mtf_rr,
        required_rr=required_rr,
        execution_result=execution_result,
        extra={
            "source_setup_id": setup_id,
            "source_strategy": strategy,
            "mtf_bias": mtf_bias,
            "mtf_conflict_mode": execution_mode,
        },
    )

    if ENABLE_MTF_CONFLICT_HIGH_SLIPPAGE_RETRY:
        candidate["setup_id"] = setup_id
        candidate["strategy"] = strategy
        candidate["signal"] = signal
        candidate["entry_model"] = entry_model

        retry_setup = register_execution_failure_retry_as_better_entry(
            signal_data=candidate,
            trade_plan=mtf_trade_plan,
            source="MTF_CONFLICT",
            min_rr_required=required_rr or 1.0,
            current_rr=mtf_rr,
            reason=f"execute_trade returned False during {execution_mode}",
            expiry_minutes=HIGH_SLIPPAGE_RETRY_EXPIRY_MINUTES,
        )

        if retry_setup:
            mark_mtf_conflict_opportunity_failed(
                setup_id,
                "Moved to WAIT_BETTER_ENTRY retry after execution failure",
            )

            send_telegram_message(
                f"⏳ MTF Conflict Moved to Better Entry Retry\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy}\n"
                f"Signal: {signal}\n"
                f"Setup ID: {setup_id}\n"
                f"Mode: {execution_mode}\n"
                f"RR: {mtf_rr}"
            )

            return True

    mark_mtf_conflict_opportunity_failed(
        setup_id,
        "execute_trade returned False",
    )

    log_setup_event(
        setup_id=mtf_trade_plan.get("setup_id"),
        event=event_failed,
        strategy=mtf_trade_plan.get("strategy"),
        signal=signal,
        entry_model=mtf_trade_plan.get("entry_model"),
        score=candidate.get("score"),
        session=session_name,
        market_condition=market_condition,
        entry=mtf_trade_plan.get("entry_price"),
        sl=mtf_trade_plan.get("stop_loss"),
        tp=mtf_trade_plan.get("take_profit"),
        rr=mtf_rr,
        required_rr=required_rr,
        reason="execute_trade returned False",
        extra={
            "source_setup_id": setup_id,
            "source_strategy": strategy,
            "mtf_bias": mtf_bias,
            "mtf_conflict_mode": execution_mode,
        },
    )

    return False

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
    # CONTINUATION SAFETY GUARD
    # =========================
    continuation_rejected, continuation_reason = continuation_safety_rejects_candidate(
        candidate=candidate,
        signal=signal,
        atr=atr,
    )

    if continuation_rejected:
        return False, candidate, continuation_reason

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
            "FAILED_BREAKOUT_REVERSAL",
            "FAILED_FVG_REVERSAL",
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
        soft_override_allowed, soft_override_reason = (
            final_htf_liquidity_soft_override_allowed(
                setup_strategy=candidate.get("strategy"),
                setup_signal=signal,
                setup_score=candidate.get("score"),
                setup_data=candidate,
                session_name=candidate.get("session"),
                liquidity_context=liquidity_context,
            )
        )
    
        if not soft_override_allowed:
            logger.info(
                f"[HTF LIQUIDITY SOFT OVERRIDE] Candidate not allowed | "
                f"strategy={candidate.get('strategy')} signal={signal} "
                f"reason={soft_override_reason}"
            )
    
            return (
                False,
                candidate,
                f"htf_liquidity_rejected reason={liquidity_context.get('reason')}",
            )
    
        candidate["reason"] = (
            f"{candidate.get('reason', 'N/A')} | "
            f"HTF_LIQUIDITY_SOFT_OVERRIDE: {soft_override_reason}"
        )
    
        logger.info(
            f"[HTF LIQUIDITY SOFT OVERRIDE] Candidate allowed | "
            f"strategy={candidate.get('strategy')} signal={signal} "
            f"{soft_override_reason}"
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
        required_rr = setup.get(
            "better_entry_min_rr",
            get_min_rr(
                strategy_name,
                setup_data.get("entry_model"),
                setup_data.get("sl_model"),
            ),
        )

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
        
        retry_source = setup.get("retry_source")

        if retry_source in HIGH_SLIPPAGE_RETRY_SOURCES:
            expected_entry = setup.get("retry_expected_entry")

            price_ok, retry_current_price, improvement = retry_entry_is_equal_or_better(
                signal=signal,
                tick=tick,
                expected_entry=expected_entry,
            )

            if not price_ok:
                logger.info(
                    f"[BETTER ENTRY] Retry waiting for equal/better price | "
                    f"source={retry_source} strategy={strategy_name} "
                    f"signal={signal} current={retry_current_price} "
                    f"expected={expected_entry} improvement={improvement}"
                )
                continue

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

        same_direction_count = count_same_direction_positions(SYMBOL, signal)
        is_extra_entry = same_direction_count >= 1

        if is_extra_entry and REQUIRE_M5_CONFIRMATION_FOR_EXTRA:
            extra_confirmed, extra_confirm_reason = extra_entry_confirmation_ok(signal)

            if not extra_confirmed:
                logger.info(
                    f"[BETTER ENTRY] Extra confirmation failed | "
                    f"strategy={strategy_name} signal={signal} reason={extra_confirm_reason}"
                )
                continue

        from src.position_guard import has_same_direction_position

        opposite = "SELL" if signal == "BUY" else "BUY"

        if has_same_direction_position(SYMBOL, opposite):
            logger.info("[BETTER ENTRY] Opposite position exists → skipping")
            continue

        news_blocked, news_reason = is_news_blackout_active()
        if news_blocked:
            logger.info(f"[BETTER ENTRY] News blocked | {news_reason}")
            continue

        time_blocked, time_reason = is_trading_blackout_active()
        if time_blocked:
            logger.info(f"[BETTER ENTRY] Time blocked | {time_reason}")
            continue

        if is_trade_blocked_by_execution_memory(
            trade_plan=trade_plan,
            signal_data=setup_data,
            setup=setup,
            strategy_name=strategy_name,
            signal=signal,
        ):
            save_execution_memory_report(
                selected_signal_data=setup_data,
                strategy_name=strategy_name,
                signal=signal,
                score=setup_data.get("score"),
                session_name=session_name,
                market_condition=market_condition,
                reason="better entry skipped by execution memory",
                trade_plan=trade_plan,
                decision="BETTER_ENTRY_BLOCKED_BY_MEMORY",
                decision_reason="better entry skipped by execution memory",
                rr_value=rr_value,
                required_rr=required_rr,
                extra={
                    "setup_state": setup.get("state"),
                    "wait_reason": setup.get("wait_reason"),
                },
            )

            return True

        send_telegram_message(
            f"✅ Better Entry Ready #{setup_data.get('setup_id', 'N/A')}\n"
            f"Symbol: {SYMBOL}\n"
            f"Strategy: {strategy_name}\n"
            f"Signal: {signal}\n\n"
            f"Entry: {trade_plan['entry_price']}\n"
            f"SL: {trade_plan['stop_loss']}\n"
            f"{_format_telegram_tp123_from_trade_plan(signal, trade_plan)}\n"
            f"RR: {rr_value} / Required: {required_rr}"
        )
        
        save_execution_memory_report(
            selected_signal_data=setup_data,
            strategy_name=strategy_name,
            signal=signal,
            score=setup_data.get("score"),
            session_name=session_name,
            market_condition=market_condition,
            reason="better entry execution attempt",
            trade_plan=trade_plan,
            decision="BETTER_ENTRY_EXECUTION_ATTEMPT",
            decision_reason="sending better entry order to MT5",
            rr_value=rr_value,
            required_rr=required_rr,
            extra={
                "setup_state": setup.get("state"),
                "wait_reason": setup.get("wait_reason"),
            },
        )
        
        observe_universal_confirmation_for_setup(
            selected_signal_data=setup_data,
            trade_plan=trade_plan,
            df=df,
            tick=tick,
            session_name=session_name,
            market_condition=market_condition,
            min_rr_required=required_rr,
            max_spread=MAX_SPREAD,
        )

        apply_strategy_advisory_note(
            signal_data=setup_data,
            strategy_name=strategy_name,
            setup_source_bucket="BETTER_ENTRY",
        )

        _live_execute_start_ts = time.perf_counter()
        logger.info(
            f"[LIVE EXECUTION TIMING] stage=before_execute_trade "
            f"symbol={SYMBOL} signal={signal} "
            f"setup_id={trade_plan.get('setup_id') if isinstance(trade_plan, dict) else None} "
            f"strategy={trade_plan.get('strategy') if isinstance(trade_plan, dict) else None}"
        )
        execution_result = execute_trade(signal, trade_plan, SYMBOL)
        logger.info(
            f"[LIVE EXECUTION TIMING] stage=after_execute_trade "
            f"elapsed_ms={round((time.perf_counter() - _live_execute_start_ts) * 1000, 2)} "
            f"symbol={SYMBOL} signal={signal} result={execution_result}"
        )

        if execution_result:
            save_execution_memory_report(
                selected_signal_data=setup_data,
                strategy_name=strategy_name,
                signal=signal,
                score=setup_data.get("score"),
                session_name=session_name,
                market_condition=market_condition,
                reason="better entry execution success",
                trade_plan=trade_plan,
                decision="BETTER_ENTRY_EXECUTION_SUCCESS",
                decision_reason="better entry MT5 order returned success",
                rr_value=rr_value,
                required_rr=required_rr,
                execution_result=execution_result,
                extra={
                    "setup_state": setup.get("state"),
                    "wait_reason": setup.get("wait_reason"),
                },
            )

            execution_engine.mark_executed(setup)
            return True
        
        save_execution_memory_report(
            selected_signal_data=setup_data,
            strategy_name=strategy_name,
            signal=signal,
            score=setup_data.get("score"),
            session_name=session_name,
            market_condition=market_condition,
            reason="better entry execution failed",
            trade_plan=trade_plan,
            decision="BETTER_ENTRY_EXECUTION_FAILED",
            decision_reason="better entry execute_trade returned False",
            rr_value=rr_value,
            required_rr=required_rr,
            execution_result=execution_result,
            extra={
                "setup_state": setup.get("state"),
                "wait_reason": setup.get("wait_reason"),
            },
        )

        if hasattr(execution_engine, "mark_execution_failed"):
            execution_engine.mark_execution_failed(
                setup,
                "Better entry execution failed",
            )
        else:
            setup["state"] = "EXECUTION_FAILED"
            setup["wait_reason"] = "Better entry execution failed"

        send_telegram_message(
            f"❌ Better Entry Execution Failed\n"
            f"Symbol: {SYMBOL}\n"
            f"Strategy: {strategy_name}\n"
            f"Signal: {signal}\n\n"
            f"Setup marked as failed to prevent repeated retries."
        )

        return True

    return False

def process_wait_orb_tick_breakout_setups(df, tick, account_info, market_condition, session_name):
    orb_setups = execution_engine.get_wait_orb_tick_breakout_setups()

    if not orb_setups:
        return False

    orb_setups = sorted(
        orb_setups,
        key=lambda setup: setup["data"].get("score", 0),
        reverse=True,
    )

    for setup in orb_setups:
        setup_data = setup.get("data", {})
        signal = setup_data.get("signal")
        strategy_name = setup_data.get("strategy")
        setup_id = setup_data.get("setup_id", "N/A")

        if signal not in ["BUY", "SELL"]:
            continue

        min_distance = setup.get(
            "orb_tick_breakout_min_distance",
            ORB_TICK_BREAKOUT_MIN_DISTANCE,
        )

        breakout_ready, current_price, breakout_level, breakout_distance = orb_tick_breakout_ready(
            signal=signal,
            tick=tick,
            signal_data=setup_data,
            min_distance=min_distance,
        )

        if not breakout_ready:
            logger.info(
                f"[ORB TICK WATCHER] Not ready | "
                f"setup_id={setup_id} strategy={strategy_name} signal={signal} "
                f"current={current_price} level={breakout_level} "
                f"distance={breakout_distance} required={min_distance}"
            )
            continue

        if ORB_TICK_BREAKOUT_REQUIRE_M5_CONFIRMATION:
            m5_confirmed, m5_reason = extra_entry_confirmation_ok(signal)

            if not m5_confirmed:
                logger.info(
                    f"[ORB TICK WATCHER] M5 confirmation failed | "
                    f"setup_id={setup_id} signal={signal} reason={m5_reason}"
                )
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
                f"[ORB TICK WATCHER] Trade plan invalid | "
                f"setup_id={setup_id} strategy={strategy_name}"
            )
            continue

        trade_plan["score"] = setup_data.get("score", 0)
        trade_plan["strategy"] = strategy_name
        trade_plan["market_condition"] = market_condition
        trade_plan["reason"] = (
            f"{setup_data.get('reason', 'N/A')} | "
            f"ORB_TICK_BREAKOUT distance={breakout_distance}"
        )
        trade_plan["session"] = setup_data.get("session", session_name)
        trade_plan["setup_id"] = setup_id

        rr_value = calculate_rr_value(trade_plan)
        required_rr = setup.get("orb_tick_breakout_min_rr", ORB_TICK_BREAKOUT_MIN_RR)

        if rr_value is None or rr_value < required_rr:
            logger.info(
                f"[ORB TICK WATCHER] RR too low | "
                f"setup_id={setup_id} rr={rr_value} required={required_rr}"
            )
            continue

        trade_allowed, guard_reason = check_trade_guard(signal, tick)

        if not trade_allowed:
            logger.info(
                f"[ORB TICK WATCHER] Guard blocked | "
                f"setup_id={setup_id} reason={guard_reason}"
            )
            continue

        news_blocked, news_reason = is_news_blackout_active()

        if news_blocked:
            logger.info(
                f"[ORB TICK WATCHER] News blocked | "
                f"setup_id={setup_id} reason={news_reason}"
            )
            continue

        time_blocked, time_reason = is_trading_blackout_active()

        if time_blocked:
            logger.info(
                f"[ORB TICK WATCHER] Time blocked | "
                f"setup_id={setup_id} reason={time_reason}"
            )
            continue

        if is_trade_blocked_by_execution_memory(
            trade_plan=trade_plan,
            signal_data=setup_data,
            setup=setup,
            strategy_name=strategy_name,
            signal=signal,
        ):
            save_execution_memory_report(
                selected_signal_data=setup_data,
                strategy_name=strategy_name,
                signal=signal,
                score=setup_data.get("score"),
                session_name=session_name,
                market_condition=market_condition,
                reason="orb tick breakout skipped by execution memory",
                trade_plan=trade_plan,
                decision="ORB_TICK_BREAKOUT_BLOCKED_BY_MEMORY",
                decision_reason="ORB tick breakout skipped by execution memory",
                rr_value=rr_value,
                required_rr=required_rr,
                extra={
                    "setup_state": setup.get("state"),
                    "wait_reason": setup.get("wait_reason"),
                },
            )

            return True

        send_telegram_message(
            f"🔥 ORB Tick Breakout Executing\n"
            f"Symbol: {SYMBOL}\n"
            f"Strategy: {strategy_name}\n"
            f"Signal: {signal}\n"
            f"Setup ID: {setup_id}\n\n"
            f"Current: {current_price}\n"
            f"Breakout Level: {breakout_level}\n"
            f"Distance: {breakout_distance}\n"
            f"Entry: {trade_plan['entry_price']}\n"
            f"SL: {trade_plan['stop_loss']}\n"
            f"TP1 / Execution TP: {trade_plan['take_profit']}\\n"
            f"Original TP: {trade_plan.get('original_take_profit', trade_plan['take_profit'])}\\n"
            f"TP Plan: {trade_plan.get('tp_plan_summary', 'standard')}\\n"
            f"RR: {rr_value} / Required: {required_rr}"
        )

        log_setup_event(
            setup_id=setup_id,
            event="ORB_TICK_BREAKOUT_EXECUTION_ATTEMPT",
            strategy=strategy_name,
            signal=signal,
            entry_model=setup_data.get("entry_model"),
            score=setup_data.get("score"),
            session=session_name,
            market_condition=market_condition,
            entry=trade_plan.get("entry_price"),
            sl=trade_plan.get("stop_loss"),
            tp=trade_plan.get("take_profit"),
            rr=rr_value,
            required_rr=required_rr,
            reason="orb tick breakout watcher",
            extra={
                "current_price": current_price,
                "breakout_level": breakout_level,
                "breakout_distance": breakout_distance,
            },
        )
        
        save_execution_memory_report(
            selected_signal_data=setup_data,
            strategy_name=strategy_name,
            signal=signal,
            score=setup_data.get("score"),
            session_name=session_name,
            market_condition=market_condition,
            reason="orb tick breakout execution attempt",
            trade_plan=trade_plan,
            decision="ORB_TICK_BREAKOUT_EXECUTION_ATTEMPT",
            decision_reason="sending ORB tick breakout order to MT5",
            rr_value=rr_value,
            required_rr=required_rr,
            extra={
                "setup_state": setup.get("state"),
                "wait_reason": setup.get("wait_reason"),
            },
        )
        
        observe_universal_confirmation_for_setup(
            selected_signal_data=setup_data,
            trade_plan=trade_plan,
            df=df,
            tick=tick,
            session_name=session_name,
            market_condition=market_condition,
            min_rr_required=required_rr,
            max_spread=MAX_SPREAD,
        )

        apply_strategy_advisory_note(
            signal_data=setup_data,
            strategy_name=strategy_name,
            setup_source_bucket="ORB_TICK_WATCHER",
        )

        _live_execute_start_ts = time.perf_counter()
        logger.info(
            f"[LIVE EXECUTION TIMING] stage=before_execute_trade "
            f"symbol={SYMBOL} signal={signal} "
            f"setup_id={trade_plan.get('setup_id') if isinstance(trade_plan, dict) else None} "
            f"strategy={trade_plan.get('strategy') if isinstance(trade_plan, dict) else None}"
        )
        execution_result = execute_trade(signal, trade_plan, SYMBOL)
        logger.info(
            f"[LIVE EXECUTION TIMING] stage=after_execute_trade "
            f"elapsed_ms={round((time.perf_counter() - _live_execute_start_ts) * 1000, 2)} "
            f"symbol={SYMBOL} signal={signal} result={execution_result}"
        )

        if execution_result:
            save_execution_memory_report(
                selected_signal_data=setup_data,
                strategy_name=strategy_name,
                signal=signal,
                score=setup_data.get("score"),
                session_name=session_name,
                market_condition=market_condition,
                reason="orb tick breakout execution success",
                trade_plan=trade_plan,
                decision="ORB_TICK_BREAKOUT_EXECUTION_SUCCESS",
                decision_reason="ORB tick breakout MT5 order returned success",
                rr_value=rr_value,
                required_rr=required_rr,
                execution_result=execution_result,
                extra={
                    "setup_state": setup.get("state"),
                    "wait_reason": setup.get("wait_reason"),
                },
            )

            execution_engine.mark_executed(setup)

            log_setup_event(
                setup_id=setup_id,
                event="ORB_TICK_BREAKOUT_EXECUTED",
                strategy=strategy_name,
                signal=signal,
                entry_model=setup_data.get("entry_model"),
                score=setup_data.get("score"),
                session=session_name,
                market_condition=market_condition,
                entry=trade_plan.get("entry_price"),
                sl=trade_plan.get("stop_loss"),
                tp=trade_plan.get("take_profit"),
                rr=rr_value,
                required_rr=required_rr,
                reason="orb tick breakout executed",
            )

            return True

        save_execution_memory_report(
            selected_signal_data=setup_data,
            strategy_name=strategy_name,
            signal=signal,
            score=setup_data.get("score"),
            session_name=session_name,
            market_condition=market_condition,
            reason="orb tick breakout execution failed",
            trade_plan=trade_plan,
            decision="ORB_TICK_BREAKOUT_EXECUTION_FAILED",
            decision_reason="ORB tick breakout execute_trade returned False",
            rr_value=rr_value,
            required_rr=required_rr,
            execution_result=execution_result,
            extra={
                "setup_state": setup.get("state"),
                "wait_reason": setup.get("wait_reason"),
            },
        )
        
        if hasattr(execution_engine, "mark_execution_failed"):
            execution_engine.mark_execution_failed(
                setup,
                "ORB tick breakout execution failed",
            )
        else:
            setup["state"] = "EXECUTION_FAILED"
            setup["wait_reason"] = "ORB tick breakout execution failed"

        log_setup_event(
            setup_id=setup_id,
            event="ORB_TICK_BREAKOUT_EXECUTION_FAILED",
            strategy=strategy_name,
            signal=signal,
            entry_model=setup_data.get("entry_model"),
            score=setup_data.get("score"),
            session=session_name,
            market_condition=market_condition,
            entry=trade_plan.get("entry_price"),
            sl=trade_plan.get("stop_loss"),
            tp=trade_plan.get("take_profit"),
            rr=rr_value,
            required_rr=required_rr,
            reason="execute_trade returned False",
        )

        return True

    return False

def process_wait_tick_sniper_setups(df, tick, account_info, market_condition, session_name):
    sniper_setups = execution_engine.get_wait_tick_sniper_setups()

    if not sniper_setups:
        return False

    sniper_setups = sorted(
        sniper_setups,
        key=lambda setup: setup["data"].get("score", 0),
        reverse=True,
    )

    for setup in sniper_setups:
        setup_data = setup.get("data", {})
        setup_id = setup_data.get("setup_id")
        strategy_name = setup_data.get("strategy")
        signal = setup_data.get("signal")
        active_session = setup_data.get("session", session_name)
        active_market_condition = setup_data.get("market_condition", market_condition)

        if signal not in ["BUY", "SELL"]:
            continue

        ready, current_price, sniper_move = tick_sniper_ready(
            signal=signal,
            tick=tick,
            setup_data=setup_data,
            setup=setup,
        )

        if not ready:
            logger.info(
                f"[TICK SNIPER] Not ready | "
                f"setup_id={setup_id} strategy={strategy_name} signal={signal} "
                f"move={sniper_move}"
            )
            continue

        require_m5_confirmation = setup.get(
            "tick_sniper_require_m5_confirmation",
            TICK_SNIPER_REQUIRE_M5_CONFIRMATION,
        )
        
        if require_m5_confirmation:
            m5_confirmed, m5_reason = extra_entry_confirmation_ok(signal)

            if not m5_confirmed:
                logger.info(
                    f"[TICK SNIPER] M5 confirmation failed | "
                    f"setup_id={setup_id} signal={signal} reason={m5_reason}"
                )
                continue

        news_blocked, news_reason = is_news_blackout_active()
        if news_blocked:
            logger.info(
                f"[TICK SNIPER] News blocked | "
                f"setup_id={setup_id} reason={news_reason}"
            )
            continue

        time_blocked, time_reason = is_trading_blackout_active()
        if time_blocked:
            logger.info(
                f"[TICK SNIPER] Time blocked | "
                f"setup_id={setup_id} reason={time_reason}"
            )
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
                f"[TICK SNIPER] Trade plan invalid | "
                f"setup_id={setup_id} strategy={strategy_name}"
            )
            continue

        trade_plan["strategy"] = strategy_name
        trade_plan["signal"] = signal
        trade_plan["score"] = setup_data.get("score")
        trade_plan["market_condition"] = active_market_condition
        trade_plan["session"] = active_session
        trade_plan["setup_id"] = setup_id
        trade_plan["reason"] = (
            f"{setup_data.get('reason', 'N/A')} | "
            f"TICK_SNIPER move={sniper_move}"
        )

        rr_value = calculate_rr_value(trade_plan)
        required_rr = setup.get("tick_sniper_min_rr", TICK_SNIPER_MIN_RR)
        
        trigger_type = setup.get("tick_sniper_trigger", "DIRECTIONAL_RECLAIM")

        if rr_value is None or rr_value < required_rr:
            logger.info(
                f"[TICK SNIPER] RR too low | "
                f"setup_id={setup_id} rr={rr_value} required={required_rr}"
            )
            continue

        trade_allowed, guard_reason = check_trade_guard(signal, tick)

        if not trade_allowed:
            logger.info(
                f"[TICK SNIPER] Guard blocked | "
                f"setup_id={setup_id} reason={guard_reason}"
            )
            continue

        if is_trade_blocked_by_execution_memory(
            trade_plan=trade_plan,
            signal_data=setup_data,
            setup=setup,
            strategy_name=strategy_name,
            signal=signal,
        ):
            save_execution_memory_report(
                selected_signal_data=setup_data,
                strategy_name=strategy_name,
                signal=signal,
                score=setup_data.get("score"),
                session_name=active_session,
                market_condition=active_market_condition,
                reason="tick sniper skipped by execution memory",
                trade_plan=trade_plan,
                decision="TICK_SNIPER_BLOCKED_BY_MEMORY",
                decision_reason="tick sniper skipped by execution memory",
                rr_value=rr_value,
                required_rr=required_rr,
                extra={
                    "setup_state": setup.get("state"),
                    "wait_reason": setup.get("wait_reason"),
                    "sniper_move": sniper_move,
                    "current_price": current_price,
                    "trigger": trigger_type,
                },
            )

            return True

        if TICK_SNIPER_NOTIFY_TELEGRAM:
            send_telegram_message(
                f"🎯 Tick Sniper Executing\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n"
                f"Setup ID: {setup_id}\n\n"
                f"Entry: {trade_plan.get('entry_price')}\n"
                f"SL: {trade_plan.get('stop_loss')}\n"
                f"TP1 / Execution TP: {trade_plan.get('take_profit')}\\n"
                f"Original TP: {trade_plan.get('original_take_profit', trade_plan.get('take_profit'))}\\n"
                f"TP Plan: {trade_plan.get('tp_plan_summary', 'standard')}\\n"
                f"RR: {rr_value} / Required: {required_rr}\n"
                f"Move: {sniper_move}"
            )

        log_setup_event(
            setup_id=setup_id,
            event="TICK_SNIPER_EXECUTION_ATTEMPT",
            strategy=strategy_name,
            signal=signal,
            entry_model=setup_data.get("entry_model"),
            score=setup_data.get("score"),
            session=active_session,
            market_condition=active_market_condition,
            entry=trade_plan.get("entry_price"),
            sl=trade_plan.get("stop_loss"),
            tp=trade_plan.get("take_profit"),
            rr=rr_value,
            required_rr=required_rr,
            reason="generic tick sniper execution attempt",
            extra={
                "sniper_move": sniper_move,
                "current_price": current_price,
            },
        )

        save_execution_memory_report(
            selected_signal_data=setup_data,
            strategy_name=strategy_name,
            signal=signal,
            score=setup_data.get("score"),
            session_name=active_session,
            market_condition=active_market_condition,
            reason="generic tick sniper execution attempt",
            trade_plan=trade_plan,
            decision="TICK_SNIPER_EXECUTION_ATTEMPT",
            decision_reason="sending tick sniper order to MT5",
            rr_value=rr_value,
            required_rr=required_rr,
            extra={
                "sniper_move": sniper_move,
                "current_price": current_price,
            },
        )
        
        observe_universal_confirmation_for_setup(
            selected_signal_data=setup_data,
            trade_plan=trade_plan,
            df=df,
            tick=tick,
            session_name=active_session,
            market_condition=active_market_condition,
            min_rr_required=required_rr,
            max_spread=MAX_SPREAD,
        )

        apply_strategy_advisory_note(
            signal_data=setup_data,
            strategy_name=strategy_name,
            setup_source_bucket="TICK_SNIPER",
        )

        _live_execute_start_ts = time.perf_counter()
        logger.info(
            f"[LIVE EXECUTION TIMING] stage=before_execute_trade "
            f"symbol={SYMBOL} signal={signal} "
            f"setup_id={trade_plan.get('setup_id') if isinstance(trade_plan, dict) else None} "
            f"strategy={trade_plan.get('strategy') if isinstance(trade_plan, dict) else None}"
        )
        execution_result = execute_trade(signal, trade_plan, SYMBOL)
        logger.info(
            f"[LIVE EXECUTION TIMING] stage=after_execute_trade "
            f"elapsed_ms={round((time.perf_counter() - _live_execute_start_ts) * 1000, 2)} "
            f"symbol={SYMBOL} signal={signal} result={execution_result}"
        )

        if execution_result:
            save_execution_memory_report(
                selected_signal_data=setup_data,
                strategy_name=strategy_name,
                signal=signal,
                score=setup_data.get("score"),
                session_name=active_session,
                market_condition=active_market_condition,
                reason="generic tick sniper execution success",
                trade_plan=trade_plan,
                decision="TICK_SNIPER_EXECUTION_SUCCESS",
                decision_reason="tick sniper MT5 order returned success",
                rr_value=rr_value,
                required_rr=required_rr,
                execution_result=execution_result,
                extra={
                    "sniper_move": sniper_move,
                    "current_price": current_price,
                },
            )

            execution_engine.mark_executed(setup)

            log_setup_event(
                setup_id=setup_id,
                event="TICK_SNIPER_EXECUTED",
                strategy=strategy_name,
                signal=signal,
                entry_model=setup_data.get("entry_model"),
                score=setup_data.get("score"),
                session=active_session,
                market_condition=active_market_condition,
                entry=trade_plan.get("entry_price"),
                sl=trade_plan.get("stop_loss"),
                tp=trade_plan.get("take_profit"),
                rr=rr_value,
                required_rr=required_rr,
                reason="generic tick sniper execution success",
            )

            return True

        save_execution_memory_report(
            selected_signal_data=setup_data,
            strategy_name=strategy_name,
            signal=signal,
            score=setup_data.get("score"),
            session_name=active_session,
            market_condition=active_market_condition,
            reason="generic tick sniper execution failed",
            trade_plan=trade_plan,
            decision="TICK_SNIPER_EXECUTION_FAILED",
            decision_reason="tick sniper execute_trade returned False",
            rr_value=rr_value,
            required_rr=required_rr,
            execution_result=execution_result,
            extra={
                "sniper_move": sniper_move,
                "current_price": current_price,
            },
        )

        execution_engine.mark_execution_failed(
            setup,
            "Tick sniper execution failed",
        )

        log_setup_event(
            setup_id=setup_id,
            event="TICK_SNIPER_EXECUTION_FAILED",
            strategy=strategy_name,
            signal=signal,
            entry_model=setup_data.get("entry_model"),
            score=setup_data.get("score"),
            session=active_session,
            market_condition=active_market_condition,
            entry=trade_plan.get("entry_price"),
            sl=trade_plan.get("stop_loss"),
            tp=trade_plan.get("take_profit"),
            rr=rr_value,
            required_rr=required_rr,
            reason="tick sniper execute_trade returned False",
        )

        return True

    return False

def register_execution_failure_retry_as_better_entry(
    *,
    signal_data,
    trade_plan,
    source,
    min_rr_required,
    current_rr,
    reason,
    expiry_minutes=None,
):
    if not ENABLE_TICK_LEVEL_RECOVERY_RETRY:
        return None

    if source not in HIGH_SLIPPAGE_RETRY_SOURCES:
        return None

    if trade_plan is None:
        return None

    expiry = expiry_minutes or HIGH_SLIPPAGE_RETRY_EXPIRY_MINUTES

    signal_data["setup_id"] = signal_data.get("setup_id") or trade_plan.get("setup_id")
    signal_data["strategy"] = signal_data.get("strategy") or trade_plan.get("strategy")
    signal_data["signal"] = signal_data.get("signal") or trade_plan.get("signal")
    signal_data["retry_trade_plan"] = trade_plan
    signal_data["retry_source"] = source

    retry_setup = execution_engine.create_wait_better_entry_retry(
        signal_data=signal_data,
        trade_plan=trade_plan,
        min_rr_required=min_rr_required,
        current_rr=current_rr,
        expiry_minutes=expiry,
        source=source,
        reason=reason,
    )

    logger.info(
        f"[TICK RECOVERY RETRY] Registered WAIT_BETTER_ENTRY | "
        f"source={source} setup_id={signal_data.get('setup_id')} "
        f"rr={current_rr}/{min_rr_required} expiry={expiry}m reason={reason}"
    )

    log_setup_event(
        setup_id=signal_data.get("setup_id"),
        event="TICK_RECOVERY_RETRY_WAIT_BETTER_ENTRY",
        strategy=signal_data.get("strategy"),
        signal=signal_data.get("signal"),
        entry_model=signal_data.get("entry_model"),
        score=signal_data.get("score"),
        entry=trade_plan.get("entry_price"),
        sl=trade_plan.get("stop_loss"),
        tp=trade_plan.get("take_profit"),
        rr=current_rr,
        required_rr=min_rr_required,
        reason=f"{source}: {reason}",
        extra={
            "source": source,
            "expiry_minutes": expiry,
            "trade_plan": trade_plan,
        },
    )

    return retry_setup


def process_wait_delayed_entry_setups(df, tick, account_info, market_condition, session_name):
    delayed_setups = execution_engine.get_wait_delayed_entry_setups()

    if not delayed_setups:
        return False

    delayed_setups = sorted(
        delayed_setups,
        key=lambda setup: setup["data"].get("score", 0),
        reverse=True,
    )

    for setup in delayed_setups:
        setup_data = setup["data"]
        signal = setup_data.get("signal")
        strategy_name = setup_data.get("strategy")
        target_entry = setup.get("delayed_entry_target")

        if signal not in ["BUY", "SELL"] or target_entry is None:
            continue

        current_price = tick.ask if signal == "BUY" else tick.bid

        if signal == "BUY" and current_price > target_entry:
            logger.info(
                f"[DELAYED ENTRY] BUY not reached yet | "
                f"current={current_price} target={target_entry}"
            )
            continue

        if signal == "SELL" and current_price < target_entry:
            logger.info(
                f"[DELAYED ENTRY] SELL not reached yet | "
                f"current={current_price} target={target_entry}"
            )
            continue

        confirmed, confirmation_reason = delayed_entry_confirmation_ok(
            signal,
            target_entry,
        )

        if not confirmed:
            logger.info(
                f"[DELAYED ENTRY] Confirmation not ready | "
                f"strategy={strategy_name} signal={signal} "
                f"reason={confirmation_reason}"
            )
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
                f"[DELAYED ENTRY] Trade plan failed | "
                f"strategy={strategy_name} signal={signal}"
            )
            continue

        trade_plan["score"] = setup_data.get("score", 0)
        trade_plan["strategy"] = strategy_name
        trade_plan["market_condition"] = market_condition
        trade_plan["reason"] = setup_data.get("reason", "N/A")
        trade_plan["session"] = setup_data.get("session", session_name)
        trade_plan["setup_id"] = setup_data.get("setup_id", "N/A")

        delayed_lot = setup.get("delayed_entry_lot")

        if delayed_lot:
            trade_plan["lot"] = delayed_lot
            trade_plan["reason"] = (
                f"{trade_plan.get('reason', '')} | SPLIT_DELAYED_ENTRY remaining lot"
            )

        rr_value = calculate_rr_value(trade_plan)
        min_rr_required = get_min_rr(
            strategy_name,
            setup_data.get("entry_model"),
            setup_data.get("sl_model"),
        )

        if rr_value is None or rr_value < min_rr_required:
            logger.info(
                f"[DELAYED ENTRY] RR invalid | "
                f"strategy={strategy_name} rr={rr_value} required={min_rr_required}"
            )
            continue

        news_blocked, news_reason = is_news_blackout_active()
        if news_blocked:
            logger.info(f"[DELAYED ENTRY] News blocked | {news_reason}")
            continue

        time_blocked, time_reason = is_trading_blackout_active()
        if time_blocked:
            logger.info(f"[DELAYED ENTRY] Time blocked | {time_reason}")
            continue

        trade_allowed, guard_reason = check_trade_guard(signal, tick)

        if not trade_allowed:
            logger.info(
                f"[DELAYED ENTRY] Guard blocked | "
                f"strategy={strategy_name} reason={guard_reason}"
            )
            continue

        from src.position_guard import has_same_direction_position

        opposite = "SELL" if signal == "BUY" else "BUY"

        if has_same_direction_position(SYMBOL, opposite):
            setup["state"] = "SKIPPED"
            setup["wait_reason"] = "Skipped because opposite position exists"
            logger.info("[DELAYED ENTRY] Opposite position exists → skipped")
            continue

        send_telegram_message(
            f"✅ Delayed Entry Reached #{setup_data.get('setup_id', 'N/A')}\n"
            f"Symbol: {SYMBOL}\n"
            f"Strategy: {strategy_name}\n"
            f"Signal: {signal}\n\n"
            f"Target Entry: {target_entry}\n"
            f"Actual Entry: {trade_plan['entry_price']}\n"
            f"SL: {trade_plan['stop_loss']}\n"
            f"TP1 / Execution TP: {trade_plan['take_profit']}\\n"
            f"Original TP: {trade_plan.get('original_take_profit', trade_plan['take_profit'])}\\n"
            f"TP Plan: {trade_plan.get('tp_plan_summary', 'standard')}\\n"
            f"RR: {rr_value} / Required: {min_rr_required}"
            f"Confirmation: {confirmation_reason}\n"
        )

        log_setup_event(
            setup_id=setup_data.get("setup_id"),
            event="SPLIT_DELAYED_EXECUTION_ATTEMPT",
            strategy=strategy_name,
            signal=signal,
            entry_model=trade_plan.get("entry_model") or setup_data.get("entry_model"),
            score=setup_data.get("score", 0),
            session=setup_data.get("session", session_name),
            market_condition=market_condition,
            entry=trade_plan["entry_price"],
            sl=trade_plan["stop_loss"],
            tp=trade_plan["take_profit"],
            rr=rr_value,
            required_rr=min_rr_required,
            reason=trade_plan.get("reason", "Split delayed entry remaining execution"),
            extra={
                "is_split_delayed_entry": True,
                "split_part": "DELAYED",
                "delayed_lot": trade_plan.get("lot"),
                "delayed_target": setup.get("delayed_entry_target"),
            },
        )

        if is_trade_blocked_by_execution_memory(
            trade_plan=trade_plan,
            signal_data=setup_data,
            setup=setup,
            strategy_name=strategy_name,
            signal=signal,
        ):
            save_execution_memory_report(
                selected_signal_data=setup_data,
                strategy_name=strategy_name,
                signal=signal,
                score=setup_data.get("score"),
                session_name=setup_data.get("session", session_name),
                market_condition=market_condition,
                reason="split delayed entry skipped by execution memory",
                trade_plan=trade_plan,
                decision="SPLIT_DELAYED_BLOCKED_BY_MEMORY",
                decision_reason="split delayed entry skipped by execution memory",
                rr_value=rr_value,
                required_rr=min_rr_required,
                extra={
                    "setup_state": setup.get("state"),
                    "wait_reason": setup.get("wait_reason"),
                    "delayed_target": setup.get("delayed_entry_target"),
                },
            )

            return True
        
        save_execution_memory_report(
            selected_signal_data=setup_data,
            strategy_name=strategy_name,
            signal=signal,
            score=setup_data.get("score"),
            session_name=setup_data.get("session", session_name),
            market_condition=market_condition,
            reason="split delayed entry execution attempt",
            trade_plan=trade_plan,
            decision="SPLIT_DELAYED_EXECUTION_ATTEMPT",
            decision_reason="sending split delayed entry order to MT5",
            rr_value=rr_value,
            required_rr=min_rr_required,
            extra={
                "setup_state": setup.get("state"),
                "wait_reason": setup.get("wait_reason"),
                "delayed_target": setup.get("delayed_entry_target"),
            },
        )
        
        apply_strategy_advisory_note(
            signal_data=setup_data,
            strategy_name=strategy_name,
            setup_source_bucket="SPLIT_DELAYED",
        )

        observe_universal_confirmation_from_scope(
            locals(),
            setup_source_bucket_override="SPLIT_DELAYED",
        )

        _live_execute_start_ts = time.perf_counter()
        logger.info(
            f"[LIVE EXECUTION TIMING] stage=before_execute_trade "
            f"symbol={SYMBOL} signal={signal} "
            f"setup_id={trade_plan.get('setup_id') if isinstance(trade_plan, dict) else None} "
            f"strategy={trade_plan.get('strategy') if isinstance(trade_plan, dict) else None}"
        )
        execution_result = execute_trade(signal, trade_plan, SYMBOL)
        logger.info(
            f"[LIVE EXECUTION TIMING] stage=after_execute_trade "
            f"elapsed_ms={round((time.perf_counter() - _live_execute_start_ts) * 1000, 2)} "
            f"symbol={SYMBOL} signal={signal} result={execution_result}"
        )

        if execution_result:
            save_execution_memory_report(
                selected_signal_data=setup_data,
                strategy_name=strategy_name,
                signal=signal,
                score=setup_data.get("score"),
                session_name=setup_data.get("session", session_name),
                market_condition=market_condition,
                reason="split delayed entry execution success",
                trade_plan=trade_plan,
                decision="SPLIT_DELAYED_EXECUTION_SUCCESS",
                decision_reason="split delayed entry MT5 order returned success",
                rr_value=rr_value,
                required_rr=min_rr_required,
                execution_result=execution_result,
                extra={
                    "setup_state": setup.get("state"),
                    "wait_reason": setup.get("wait_reason"),
                    "delayed_target": setup.get("delayed_entry_target"),
                },
            )

            execution_engine.mark_executed(setup)
            return True
        
        save_execution_memory_report(
            selected_signal_data=setup_data,
            strategy_name=strategy_name,
            signal=signal,
            score=setup_data.get("score"),
            session_name=setup_data.get("session", session_name),
            market_condition=market_condition,
            reason="split delayed entry execution failed",
            trade_plan=trade_plan,
            decision="SPLIT_DELAYED_EXECUTION_FAILED",
            decision_reason="split delayed entry execute_trade returned False",
            rr_value=rr_value,
            required_rr=min_rr_required,
            execution_result=execution_result,
            extra={
                "setup_state": setup.get("state"),
                "wait_reason": setup.get("wait_reason"),
                "delayed_target": setup.get("delayed_entry_target"),
            },
        )

        if hasattr(execution_engine, "mark_execution_failed"):
            execution_engine.mark_execution_failed(
                setup,
                "Delayed entry execution failed",
            )
        else:
            setup["state"] = "EXECUTION_FAILED"
            setup["wait_reason"] = "Delayed entry execution failed"

        send_telegram_message(
            f"❌ Delayed Entry Execution Failed\n"
            f"Symbol: {SYMBOL}\n"
            f"Strategy: {strategy_name}\n"
            f"Signal: {signal}"
        )

        return False

    return False

def low_rr_smc_zone_recovery_enabled(strategy_name, reason_type):
    if not ENABLE_SMC_FAILED_LOW_RR_SL_ZONE_RECOVERY:
        return False

    if reason_type != "LOW_RR":
        return False

    strategy_key = str(strategy_name or "").upper()

    return strategy_key in SMC_FAILED_LOW_RR_SL_ZONE_STRATEGIES


def smc_still_weak_for_low_rr_recovery(df, signal):
    try:
        from src.smart_money_layer import smart_money_confirm

        smc_check = smart_money_confirm(df, signal)

        return not smc_check.get("confirmed"), smc_check.get("reasons")

    except Exception as e:
        logger.error(f"[SMC LOW RR ZONE] SMC check error: {e}")
        return False, ["smc_check_error"]


def price_inside_sl_recovery_zone(signal, tick, trade_plan, zone_ratio):
    entry = trade_plan.get("entry_price")
    stop_loss = trade_plan.get("stop_loss")

    if entry is None or stop_loss is None:
        return False, "missing_entry_or_sl", None

    entry = float(entry)
    stop_loss = float(stop_loss)

    risk_distance = abs(entry - stop_loss)

    if risk_distance <= 0:
        return False, "invalid_risk_distance", None

    zone_size = round(risk_distance * float(zone_ratio), 2)

    if signal == "SELL":
        current_price = float(tick.bid)

        pre_sl_zone_start = stop_loss - zone_size
        pre_sl_zone_end = stop_loss

        if pre_sl_zone_start <= current_price <= pre_sl_zone_end:
            return True, "pre_sl_zone", {
                "current_price": current_price,
                "stop_loss": stop_loss,
                "risk_distance": round(risk_distance, 2),
                "zone_size": zone_size,
                "zone_start": round(pre_sl_zone_start, 2),
                "zone_end": round(pre_sl_zone_end, 2),
            }

        if (
            SMC_FAILED_LOW_RR_ALLOW_POST_SL_SWEEP_RECLAIM
            and stop_loss < current_price <= stop_loss + zone_size
        ):
            return False, "post_sl_sweep_wait_reclaim", {
                "current_price": current_price,
                "stop_loss": stop_loss,
                "risk_distance": round(risk_distance, 2),
                "zone_size": zone_size,
                "zone_start": round(pre_sl_zone_start, 2),
                "zone_end": round(pre_sl_zone_end, 2),
            }

        return False, "not_near_sell_sl_zone", {
            "current_price": current_price,
            "stop_loss": stop_loss,
            "risk_distance": round(risk_distance, 2),
            "zone_size": zone_size,
            "zone_start": round(pre_sl_zone_start, 2),
            "zone_end": round(pre_sl_zone_end, 2),
        }

    if signal == "BUY":
        current_price = float(tick.ask)

        pre_sl_zone_start = stop_loss
        pre_sl_zone_end = stop_loss + zone_size

        if pre_sl_zone_start <= current_price <= pre_sl_zone_end:
            return True, "pre_sl_zone", {
                "current_price": current_price,
                "stop_loss": stop_loss,
                "risk_distance": round(risk_distance, 2),
                "zone_size": zone_size,
                "zone_start": round(pre_sl_zone_start, 2),
                "zone_end": round(pre_sl_zone_end, 2),
            }

        if (
            SMC_FAILED_LOW_RR_ALLOW_POST_SL_SWEEP_RECLAIM
            and stop_loss - zone_size <= current_price < stop_loss
        ):
            return False, "post_sl_sweep_wait_reclaim", {
                "current_price": current_price,
                "stop_loss": stop_loss,
                "risk_distance": round(risk_distance, 2),
                "zone_size": zone_size,
                "zone_start": round(pre_sl_zone_start, 2),
                "zone_end": round(pre_sl_zone_end, 2),
            }

        return False, "not_near_buy_sl_zone", {
            "current_price": current_price,
            "stop_loss": stop_loss,
            "risk_distance": round(risk_distance, 2),
            "zone_size": zone_size,
            "zone_start": round(pre_sl_zone_start, 2),
            "zone_end": round(pre_sl_zone_end, 2),
        }

    return False, "invalid_signal", None

def smc_low_rr_zone_wait_expired(item):
    try:
        created_at = datetime.fromisoformat(item.get("created_at"))
    except Exception:
        return False

    max_wait_seconds = SMC_FAILED_LOW_RR_SL_ZONE_EXPIRY_MINUTES * 60
    elapsed_seconds = (datetime.now() - created_at).total_seconds()

    return elapsed_seconds > max_wait_seconds

def get_recovery_reference_price(signal_data, keys):
    for key in keys:
        value = signal_data.get(key)

        if value is None:
            continue

        try:
            value = float(value)
        except Exception:
            continue

        if value > 0:
            return value

    return None


def get_current_recovery_price(signal, tick):
    if tick is None:
        return None

    try:
        if signal == "BUY":
            return float(tick.ask)

        if signal == "SELL":
            return float(tick.bid)
    except Exception:
        return None

    return None


def recovery_original_setup_consumed(signal, current_price, signal_data):
    original_tp = get_recovery_reference_price(
        signal_data,
        ["tp_reference", "take_profit", "target_price", "tp"],
    )

    original_sl = get_recovery_reference_price(
        signal_data,
        ["sl_reference", "stop_loss", "sl"],
    )

    if current_price is None:
        return False, None

    if signal == "BUY":
        if original_tp is not None and current_price >= original_tp:
            return (
                True,
                f"original_target_already_reached current={round(current_price, 2)} tp={round(original_tp, 2)}",
            )

        if original_sl is not None and current_price <= original_sl:
            return (
                True,
                f"original_sl_already_reached current={round(current_price, 2)} sl={round(original_sl, 2)}",
            )

    if signal == "SELL":
        if original_tp is not None and current_price <= original_tp:
            return (
                True,
                f"original_target_already_reached current={round(current_price, 2)} tp={round(original_tp, 2)}",
            )

        if original_sl is not None and current_price >= original_sl:
            return (
                True,
                f"original_sl_already_reached current={round(current_price, 2)} sl={round(original_sl, 2)}",
            )

    return False, None

def process_candidate_rejection_recovery_setups(
    df,
    tick,
    account_info,
    market_condition,
    session_name,
):
    if not ENABLE_CANDIDATE_REJECTION_RECOVERY:
        return False

    recovery_items = get_waiting_recovery_candidates(SYMBOL)

    if not recovery_items:
        return False

    for item in recovery_items:
        recovery_id = item["recovery_id"]
        setup_id = item.get("setup_id")
        signal = item.get("signal")
        strategy_name = item.get("strategy")
        reason_type = item.get("reason_type")
        signal_data = item.get("signal_data", {})

        if signal not in ["BUY", "SELL"]:
            continue
        
        current_recovery_price = get_current_recovery_price(signal, tick)

        consumed, consumed_reason = recovery_original_setup_consumed(
            signal=signal,
            current_price=current_recovery_price,
            signal_data=signal_data,
        )

        if consumed:
            mark_recovery_candidate_invalidated(
                recovery_id,
                consumed_reason,
            )

            logger.info(
                f"[CANDIDATE RECOVERY] Invalidated | "
                f"id={recovery_id} strategy={strategy_name} signal={signal} "
                f"reason={consumed_reason}"
            )

            log_setup_event(
                setup_id=setup_id,
                event="CANDIDATE_RECOVERY_INVALIDATED",
                strategy=strategy_name,
                signal=signal,
                entry_model=signal_data.get("entry_model"),
                score=signal_data.get("score"),
                session=session_name,
                market_condition=market_condition,
                reason=consumed_reason,
                extra={
                    "recovery_id": recovery_id,
                    "current_price": current_recovery_price,
                    "reason_type": reason_type,
                },
            )
            
            if (
                ENABLE_CANDIDATE_REJECTION_TELEGRAM_ALERTS
                and TELEGRAM_NOTIFY_CANDIDATE_RECOVERY_INVALIDATED
            ):
                send_telegram_message(
                    f"🛑 Candidate Recovery Invalidated\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Strategy: {strategy_name}\n"
                    f"Signal: {signal}\n"
                    f"Setup ID: {setup_id}\n"
                    f"Recovery ID: {recovery_id}\n\n"
                    f"Reason: {consumed_reason}\n"
                    f"Current Price: {current_recovery_price}\n"
                    f"Original TP: {signal_data.get('tp_reference') or signal_data.get('take_profit') or signal_data.get('tp')}\n"
                    f"Original SL: {signal_data.get('sl_reference') or signal_data.get('stop_loss') or signal_data.get('sl')}"
                )

            continue

        if reason_type == "SMC_FAILED":
            try:
                from src.smart_money_layer import smart_money_confirm

                smc_check = smart_money_confirm(df, signal)

                if not smc_check.get("confirmed"):
                    logger.info(
                        f"[CANDIDATE RECOVERY] SMC still failed | "
                        f"id={recovery_id} strategy={strategy_name} signal={signal} "
                        f"reason={smc_check.get('reasons')}"
                    )
                    continue

            except Exception as e:
                logger.error(f"[CANDIDATE RECOVERY] SMC check error: {e}")
                continue

        if reason_type == "HTF_LIQUIDITY_REJECTED":
            liquidity_context = get_liquidity_context()

            if not liquidity_allows_signal(signal, liquidity_context, allow_neutral=True):
                logger.info(
                    f"[CANDIDATE RECOVERY] HTF liquidity still rejects | "
                    f"id={recovery_id} strategy={strategy_name} signal={signal} "
                    f"reason={liquidity_context.get('reason') if liquidity_context else None}"
                )
                continue

        if (
            CANDIDATE_REJECTION_RECOVERY_REQUIRE_M5_CONFIRMATION
            and signal in ["BUY", "SELL"]
        ):
            m5_confirmed, m5_reason = extra_entry_confirmation_ok(signal)

            if not m5_confirmed:
                logger.info(
                    f"[CANDIDATE RECOVERY] M5 confirmation failed | "
                    f"id={recovery_id} strategy={strategy_name} signal={signal} "
                    f"reason={m5_reason}"
                )
                continue

        trade_plan = calculate_trade_plan(
            df=df,
            signal=signal,
            tick=tick,
            account_balance=account_info.balance,
            signal_data=signal_data,
        )

        if trade_plan is None:
            logger.info(
                f"[CANDIDATE RECOVERY] Trade plan invalid | "
                f"id={recovery_id} strategy={strategy_name} signal={signal}"
            )
            continue

        trade_plan["score"] = signal_data.get("score", item.get("score", 0))
        trade_plan["strategy"] = strategy_name
        trade_plan["market_condition"] = market_condition
        trade_plan["reason"] = (
            f"{signal_data.get('reason', 'N/A')} | "
            f"CANDIDATE_REJECTION_RECOVERY: {reason_type}"
        )
        trade_plan["session"] = signal_data.get("session", session_name)
        trade_plan["setup_id"] = setup_id

        rr_value = calculate_rr_value(trade_plan)

        min_rr = item.get("required_rr") or CANDIDATE_REJECTION_RECOVERY_MIN_RECOVERED_RR

        try:
            min_rr = float(min_rr)
        except Exception:
            min_rr = CANDIDATE_REJECTION_RECOVERY_MIN_RECOVERED_RR

        if rr_value is None or rr_value < min_rr:
            logger.info(
                f"[CANDIDATE RECOVERY] RR not recovered | "
                f"id={recovery_id} strategy={strategy_name} "
                f"rr={rr_value} required={min_rr}"
            )
            continue
        
        if low_rr_smc_zone_recovery_enabled(strategy_name, reason_type):
            if smc_low_rr_zone_wait_expired(item):
                mark_recovery_candidate_invalidated(
                    recovery_id,
                    "smc_low_rr_sl_zone_expired",
                )

                logger.info(
                    f"[SMC LOW RR ZONE] Expired | "
                    f"id={recovery_id} strategy={strategy_name} signal={signal}"
                )

                log_setup_event(
                    setup_id=setup_id,
                    event="CANDIDATE_RECOVERY_INVALIDATED",
                    strategy=strategy_name,
                    signal=signal,
                    entry_model=signal_data.get("entry_model"),
                    score=signal_data.get("score"),
                    session=session_name,
                    market_condition=market_condition,
                    reason="smc_low_rr_sl_zone_expired",
                    extra={
                        "recovery_id": recovery_id,
                        "max_wait_minutes": SMC_FAILED_LOW_RR_SL_ZONE_EXPIRY_MINUTES,
                    },
                )

                continue
            
            smc_weak, smc_reasons = smc_still_weak_for_low_rr_recovery(df, signal)

            if smc_weak:
                zone_ok, zone_reason, zone_info = price_inside_sl_recovery_zone(
                    signal=signal,
                    tick=tick,
                    trade_plan=trade_plan,
                    zone_ratio=SMC_FAILED_LOW_RR_SL_ZONE_RATIO,
                )

                if not zone_ok:
                    logger.info(
                        f"[SMC LOW RR ZONE] Waiting near SL zone | "
                        f"id={recovery_id} strategy={strategy_name} signal={signal} "
                        f"reason={zone_reason} smc_reasons={smc_reasons} "
                        f"zone={zone_info}"
                    )

                    log_setup_event(
                        setup_id=setup_id,
                        event="CANDIDATE_RECOVERY_WAITING_SMC_SL_ZONE",
                        strategy=strategy_name,
                        signal=signal,
                        entry_model=signal_data.get("entry_model"),
                        score=signal_data.get("score"),
                        session=session_name,
                        market_condition=market_condition,
                        entry=trade_plan.get("entry_price"),
                        sl=trade_plan.get("stop_loss"),
                        tp=trade_plan.get("take_profit"),
                        rr=rr_value,
                        required_rr=min_rr,
                        reason=zone_reason,
                        extra={
                            "recovery_id": recovery_id,
                            "smc_reasons": smc_reasons,
                            "zone": zone_info,
                        },
                    )

                    continue

                logger.info(
                    f"[SMC LOW RR ZONE] SL-zone recovery approved | "
                    f"id={recovery_id} strategy={strategy_name} signal={signal} "
                    f"zone={zone_info}"
                )

        trade_allowed, guard_reason = check_trade_guard(signal, tick)

        if not trade_allowed:
            logger.info(
                f"[CANDIDATE RECOVERY] Guard blocked | "
                f"id={recovery_id} strategy={strategy_name} reason={guard_reason}"
            )
            continue

        from src.position_guard import has_same_direction_position

        opposite = "SELL" if signal == "BUY" else "BUY"

        if has_same_direction_position(SYMBOL, opposite):
            logger.info(
                f"[CANDIDATE RECOVERY] Opposite position exists | "
                f"id={recovery_id} opposite={opposite}"
            )
            continue

        news_blocked, news_reason = is_news_blackout_active()

        if news_blocked:
            logger.info(
                f"[CANDIDATE RECOVERY] News blocked | "
                f"id={recovery_id} reason={news_reason}"
            )
            continue

        time_blocked, time_reason = is_trading_blackout_active()

        if time_blocked:
            logger.info(
                f"[CANDIDATE RECOVERY] Time blocked | "
                f"id={recovery_id} reason={time_reason}"
            )
            continue

        if is_trade_blocked_by_execution_memory(
            trade_plan=trade_plan,
            signal_data=signal_data,
            setup=None,
            strategy_name=strategy_name,
            signal=signal,
        ):
            save_execution_memory_report(
                selected_signal_data=signal_data,
                strategy_name=strategy_name,
                signal=signal,
                score=signal_data.get("score"),
                session_name=session_name,
                market_condition=market_condition,
                reason=f"candidate recovery from {reason_type}",
                trade_plan=trade_plan,
                decision="CANDIDATE_RECOVERY_BLOCKED_BY_MEMORY",
                decision_reason="candidate recovery skipped by execution memory",
                rr_value=rr_value,
                required_rr=None,
                extra={
                    "recovery_id": recovery_id,
                    "source_setup_id": setup_id,
                    "reason_type": reason_type,
                },
            )

            mark_recovery_candidate_failed(
                recovery_id,
                "Skipped by execution memory",
            )
            return True

        try:
            from src.key_level_tp_ladder import apply_key_level_tp_ladder

            trade_plan = apply_key_level_tp_ladder(
                df=df,
                signal=signal,
                trade_plan=trade_plan,
                signal_data=signal_data,
                strategy_name=strategy_name,
                session_name=session_name,
                market_condition=market_condition,
            )

            if isinstance(signal_data, dict):
                signal_data["tp_ladder"] = trade_plan.get("tp_ladder")
                signal_data["tp_plan_summary"] = trade_plan.get("tp_plan_summary")
                signal_data["original_take_profit"] = trade_plan.get("original_take_profit")
                signal_data["tp_reference"] = trade_plan.get("take_profit")

            try:
                rr_value = calculate_rr_value(trade_plan)
            except Exception:
                pass

        except Exception as tp_ladder_exc:
            logger.warning(
                f"[PHASE 6E TP LADDER] recovery path failed | "
                f"strategy={strategy_name} signal={signal} error={tp_ladder_exc}"
            )

        send_telegram_message(
            f"♻️ Candidate Recovery Executing\n"
            f"Symbol: {SYMBOL}\n"
            f"Strategy: {strategy_name}\n"
            f"Signal: {signal}\n"
            f"Reason: {reason_type}\n"
            f"Setup ID: {setup_id}\n\n"
            f"Entry: {trade_plan['entry_price']}\n"
            f"SL: {trade_plan['stop_loss']}\n"
            f"TP1 / Execution TP: {trade_plan['take_profit']}\\n"
            f"Original TP: {trade_plan.get('original_take_profit', trade_plan['take_profit'])}\\n"
            f"TP Plan: {trade_plan.get('tp_plan_summary', 'standard')}\\n"
            f"RR: {rr_value} / Required: {min_rr}"
        )

        log_setup_event(
            setup_id=setup_id,
            event="CANDIDATE_RECOVERY_EXECUTION_ATTEMPT",
            strategy=strategy_name,
            signal=signal,
            entry_model=signal_data.get("entry_model"),
            score=signal_data.get("score"),
            session=session_name,
            market_condition=market_condition,
            entry=trade_plan.get("entry_price"),
            sl=trade_plan.get("stop_loss"),
            tp=trade_plan.get("take_profit"),
            rr=rr_value,
            reason=f"candidate recovery from {reason_type}",
        )

        save_execution_memory_report(
            selected_signal_data=signal_data,
            strategy_name=strategy_name,
            signal=signal,
            score=signal_data.get("score"),
            session_name=session_name,
            market_condition=market_condition,
            reason=f"candidate recovery from {reason_type}",
            trade_plan=trade_plan,
            decision="CANDIDATE_RECOVERY_EXECUTION_ATTEMPT",
            decision_reason="sending candidate recovery order to MT5",
            rr_value=rr_value,
            required_rr=None,
            extra={
                "recovery_id": recovery_id,
                "source_setup_id": setup_id,
                "reason_type": reason_type,
            },
        )
        
        apply_strategy_advisory_note(
            signal_data=signal_data,
            strategy_name=strategy_name,
            setup_source_bucket="REJECTED_CANDIDATE_TRACKED",
        )
        
        observe_universal_confirmation_from_scope(
            locals(),
            setup_source_bucket_override="REJECTED_CANDIDATE_TRACKED",
        )

        _live_execute_start_ts = time.perf_counter()
        logger.info(
            f"[LIVE EXECUTION TIMING] stage=before_execute_trade "
            f"symbol={SYMBOL} signal={signal} "
            f"setup_id={trade_plan.get('setup_id') if isinstance(trade_plan, dict) else None} "
            f"strategy={trade_plan.get('strategy') if isinstance(trade_plan, dict) else None}"
        )
        execution_result = execute_trade(signal, trade_plan, SYMBOL)
        logger.info(
            f"[LIVE EXECUTION TIMING] stage=after_execute_trade "
            f"elapsed_ms={round((time.perf_counter() - _live_execute_start_ts) * 1000, 2)} "
            f"symbol={SYMBOL} signal={signal} result={execution_result}"
        )

        if execution_result:
            save_execution_memory_report(
                selected_signal_data=signal_data,
                strategy_name=strategy_name,
                signal=signal,
                score=signal_data.get("score"),
                session_name=session_name,
                market_condition=market_condition,
                reason=f"candidate recovery from {reason_type}",
                trade_plan=trade_plan,
                decision="CANDIDATE_RECOVERY_EXECUTION_SUCCESS",
                decision_reason="candidate recovery MT5 order returned success",
                rr_value=rr_value,
                required_rr=None,
                execution_result=execution_result,
                extra={
                    "recovery_id": recovery_id,
                    "source_setup_id": setup_id,
                    "reason_type": reason_type,
                },
            )

            mark_recovery_candidate_executed(recovery_id)

            log_setup_event(
                setup_id=setup_id,
                event="CANDIDATE_RECOVERY_EXECUTED",
                strategy=strategy_name,
                signal=signal,
                entry_model=signal_data.get("entry_model"),
                score=signal_data.get("score"),
                session=session_name,
                market_condition=market_condition,
                entry=trade_plan.get("entry_price"),
                sl=trade_plan.get("stop_loss"),
                tp=trade_plan.get("take_profit"),
                rr=rr_value,
                reason=f"candidate recovery executed from {reason_type}",
            )

            return True

        if (
            reason_type == "LOW_RR"
            and ENABLE_LOW_RR_RECOVERY_HIGH_SLIPPAGE_RETRY
        ):
            retry_setup = register_execution_failure_retry_as_better_entry(
                signal_data=signal_data,
                trade_plan=trade_plan,
                source="LOW_RR_RECOVERY",
                min_rr_required=min_rr,
                current_rr=rr_value,
                reason="execute_trade returned False after LOW_RR recovered",
                expiry_minutes=HIGH_SLIPPAGE_RETRY_EXPIRY_MINUTES,
            )

            if retry_setup:
                mark_recovery_candidate_failed(
                    recovery_id,
                    "Moved to WAIT_BETTER_ENTRY retry after execution failure",
                )

                send_telegram_message(
                    f"⏳ Low RR Recovery Moved to Better Entry Retry\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Strategy: {strategy_name}\n"
                    f"Signal: {signal}\n"
                    f"Setup ID: {setup_id}\n"
                    f"RR: {rr_value} / Required: {min_rr}"
                )

                return True

        mark_recovery_candidate_failed(
            recovery_id,
            "execute_trade returned False",
        )
        
        save_execution_memory_report(
            selected_signal_data=signal_data,
            strategy_name=strategy_name,
            signal=signal,
            score=signal_data.get("score"),
            session_name=session_name,
            market_condition=market_condition,
            reason=f"candidate recovery from {reason_type}",
            trade_plan=trade_plan,
            decision="CANDIDATE_RECOVERY_EXECUTION_FAILED",
            decision_reason="candidate recovery execute_trade returned False",
            rr_value=rr_value,
            required_rr=None,
            execution_result=execution_result,
            extra={
                "recovery_id": recovery_id,
                "source_setup_id": setup_id,
                "reason_type": reason_type,
            },
        )

        log_setup_event(
            setup_id=setup_id,
            event="CANDIDATE_RECOVERY_EXECUTION_FAILED",
            strategy=strategy_name,
            signal=signal,
            entry_model=signal_data.get("entry_model"),
            score=signal_data.get("score"),
            session=session_name,
            market_condition=market_condition,
            entry=trade_plan.get("entry_price"),
            sl=trade_plan.get("stop_loss"),
            tp=trade_plan.get("take_profit"),
            rr=rr_value,
            reason="execute_trade returned False",
        )

        send_telegram_message(
            f"❌ Candidate Recovery Execution Failed\n"
            f"Symbol: {SYMBOL}\n"
            f"Strategy: {strategy_name}\n"
            f"Signal: {signal}\n"
            f"Setup ID: {setup_id}"
        )

        return True

    return False

PHASE6H_INTRABAR_SCALP_MEMORY = {}

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

    try:
        flush_google_sheets_retry_queue(max_items=5)
    except Exception as e:
        logger.error(f"[GOOGLE SHEETS QUEUE] Flush error: {e}")

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
    # WAIT FOR DELAYED RETRACE ENTRY CHECK
    # Runs every loop, not only on a new M15 candle.
    # =========================
    if ENABLE_DELAYED_RETRACE_ENTRY:
        if process_wait_delayed_entry_setups(
            df=df,
            tick=tick,
            account_info=account_info,
            market_condition="PENDING",
            session_name="PENDING",
        ):
            return current_candle_time
        
    # =========================
    # FVG STAGED ENTRY CHECK
    # Runs every loop, not only on a new M15 candle.
    # =========================
    if ENABLE_FVG_ZONE_STAGED_ENTRY:
        if process_wait_fvg_staged_entry_setups(
            df=df,
            tick=tick,
            account_info=account_info,
            market_condition="PENDING",
            session_name="PENDING",
        ):
            return current_candle_time
        
    # =========================
    # ORB TICK BREAKOUT WATCHER
    # Runs every loop, not only on a new M15 candle.
    # =========================
    if ENABLE_ORB_TICK_BREAKOUT_WATCHER:
        if process_wait_orb_tick_breakout_setups(
            df=df,
            tick=tick,
            account_info=account_info,
            market_condition="PENDING",
            session_name="PENDING",
        ):
            return current_candle_time

    # =========================
    # GENERIC TICK SNIPER WATCHER
    # Runs every loop, not only on a new M15 candle.
    # =========================
    if ENABLE_TICK_SNIPER_EXECUTION:
        if process_wait_tick_sniper_setups(
            df=df,
            tick=tick,
            account_info=account_info,
            market_condition="PENDING",
            session_name="PENDING",
        ):
            return current_candle_time

    # =========================
    # CANDIDATE REJECTION RECOVERY CHECK
    # Runs every loop, not only on a new M15 candle.
    # =========================
    if ENABLE_CANDIDATE_REJECTION_RECOVERY:
        if process_candidate_rejection_recovery_setups(
            df=df,
            tick=tick,
            account_info=account_info,
            market_condition="PENDING",
            session_name="PENDING",
        ):
            return current_candle_time
        
    # =========================
    # SETUP OUTCOME TRACKER
    # Runs every loop, not only on a new M15 candle.
    # =========================
    if ENABLE_SETUP_OUTCOME_TRACKER:
        outcome_milestones = update_setup_outcomes(SYMBOL, tick)

        for milestone in outcome_milestones:
            item = milestone.get("item", {})

            log_setup_event(
                setup_id=milestone.get("setup_id"),
                event=milestone.get("event"),
                strategy=item.get("strategy"),
                signal=item.get("signal"),
                entry_model=item.get("entry_model"),
                score=item.get("score"),
                session=item.get("session"),
                market_condition=item.get("market_condition"),
                entry=item.get("entry"),
                sl=item.get("sl"),
                tp=item.get("tp"),
                reason=item.get("reason"),
                extra={
                    "current_price": milestone.get("current_price"),
                    "favorable": milestone.get("favorable"),
                    "adverse": milestone.get("adverse"),
                    "max_favorable_usd": item.get("max_favorable_usd"),
                    "max_adverse_usd": item.get("max_adverse_usd"),
                    "hit_plus_10": item.get("hit_plus_10"),
                    "hit_tp": item.get("hit_tp"),
                    "hit_sl": item.get("hit_sl"),
                    "first_hit": item.get("first_hit"),
                    "final_outcome": item.get("final_outcome"),
                    "context_key": item.get("context_key"),
                    "scenario_key": item.get("scenario_key"),
                    "nearby_strategies": item.get("nearby_strategies"),
                    "max_recovery_swing_usd": item.get("max_recovery_swing_usd"),
                    "reentry_candidate_after_adverse": item.get("reentry_candidate_after_adverse"),
                },
            )

    # =========================
    # MTF CONFLICT OPPORTUNITY TRACKER
    # Runs every loop, not only on a new M15 candle.
    # =========================
    if ENABLE_MTF_CONFLICT_OPPORTUNITY_TRACKER:
        update_mtf_conflict_opportunities(SYMBOL)
        
    # =========================
    # INTRABAR ORB DETECTOR
    # Runs before the M15 new-candle gate.
    # =========================
    if ENABLE_INTRABAR_PRICE_EVENT_DETECTOR:
        from src.session_engine import detect_session

        intrabar_session_name = detect_session(current_candle_time)
        intrabar_market_condition = "INTRABAR_PENDING"

        if process_intrabar_price_event_detector(
            df=df,
            tick=tick,
            account_info=account_info,
            session_name=intrabar_session_name,
            market_condition=intrabar_market_condition,
            current_candle_time=current_candle_time,
        ):
            return current_candle_time


    # =========================
    # PHASE 6H3 - INTRABAR STRUCTURAL LEVEL SCALP EXECUTION
    # Runs every loop before the M15 new-candle gate.
    # =========================
    if ENABLE_AUTO_STRUCTURAL_LEVEL_SCALP:
        from config.settings import (
            ASLS_INTRABAR_DUPLICATE_SECONDS,
            ASLS_INTRABAR_ENTRY_TOLERANCE,
            ASLS_MIN_RR,
        )
        from src.session_engine import detect_session
        from src.strategies.strategy_auto_structural_level_scalp import (
            generate_signal as auto_structural_level_scalp_signal,
        )

        asls_signal_data = auto_structural_level_scalp_signal(df)

        if isinstance(asls_signal_data, dict) and asls_signal_data.get("signal") in ["BUY", "SELL"]:
            asls_signal = asls_signal_data.get("signal")
            asls_strategy = asls_signal_data.get("strategy", "AUTO_STRUCTURAL_LEVEL_SCALP")
            asls_entry_model = asls_signal_data.get("entry_model", "AUTO_STRUCTURAL_LEVEL_SCALP")
            asls_entry = round(float(asls_signal_data.get("entry_reference")), 2)
            asls_sl = round(float(asls_signal_data.get("sl_reference")), 2)
            asls_tp = round(float(asls_signal_data.get("tp_reference")), 2)
            asls_level = round(float(asls_signal_data.get("structural_level", asls_entry)), 2)

            asls_setup_id = asls_signal_data.get("setup_id") or (
                f"ASLS-{asls_signal}-{asls_entry_model}-"
                f"{asls_level}-{asls_entry}-{current_candle_time}"
            )

            asls_signal_data["setup_id"] = asls_setup_id
            asls_signal_data["session"] = detect_session(current_candle_time)
            asls_signal_data["market_condition"] = "INTRABAR_STRUCTURAL_LEVEL_SCALP"
            asls_signal_data["intrabar_live_executor"] = True

            current_execution_price = tick.ask if asls_signal == "BUY" else tick.bid
            entry_distance = abs(float(current_execution_price) - asls_entry)

            if entry_distance > ASLS_INTRABAR_ENTRY_TOLERANCE:
                logger.info(
                    f"[PHASE 6H3 ASLS SKIP] price already moved | "
                    f"signal={asls_signal} setup_id={asls_setup_id} "
                    f"target_entry={asls_entry} current={round(current_execution_price, 2)} "
                    f"distance={round(entry_distance, 2)} "
                    f"max={ASLS_INTRABAR_ENTRY_TOLERANCE}"
                )
                return current_candle_time

            memory_key = f"{asls_signal}:{asls_entry_model}:{asls_level}:{asls_entry}"

            last_seen_ts = PHASE6H_INTRABAR_SCALP_MEMORY.get(memory_key)
            now_ts = time.time()

            if (
                last_seen_ts is not None
                and now_ts - last_seen_ts < ASLS_INTRABAR_DUPLICATE_SECONDS
            ):
                logger.info(
                    f"[PHASE 6H3 ASLS DUPLICATE SKIP] "
                    f"memory_key={memory_key} age={round(now_ts - last_seen_ts, 1)}s"
                )
                return current_candle_time

            PHASE6H_INTRABAR_SCALP_MEMORY[memory_key] = now_ts

            asls_trade_plan = calculate_trade_plan(
                df=df,
                signal=asls_signal,
                tick=tick,
                account_balance=account_info.balance,
                signal_data=asls_signal_data,
            )

            if asls_trade_plan is None:
                logger.info(
                    f"[PHASE 6H3 ASLS SKIP] trade plan failed | setup_id={asls_setup_id}"
                )
                return current_candle_time

            # Force exact strategy-defined scalp levels.
            # Do not let generic risk.py replace the channel-style entry.
            asls_trade_plan["entry_price"] = asls_entry
            asls_trade_plan["stop_loss"] = asls_sl
            asls_trade_plan["take_profit"] = asls_tp
            asls_trade_plan["strategy"] = asls_strategy
            asls_trade_plan["entry_model"] = asls_entry_model
            asls_trade_plan["setup_id"] = asls_setup_id
            asls_trade_plan["session"] = asls_signal_data.get("session")
            asls_trade_plan["market_condition"] = asls_signal_data.get("market_condition")
            asls_trade_plan["reason"] = asls_signal_data.get("reason", "Phase 6H3 intrabar structural scalp")
            asls_trade_plan["intrabar_live_executor"] = True
            asls_trade_plan["structural_level"] = asls_level
            asls_trade_plan["rr"] = asls_signal_data.get("rr")
            asls_trade_plan["risk_reward"] = asls_signal_data.get("rr")

            asls_rr = calculate_rr_value(asls_trade_plan)

            asls_allowed, asls_guard_reason = check_trade_guard(asls_signal, tick)

            if not is_rr_valid(asls_trade_plan, min_rr=ASLS_MIN_RR):
                asls_allowed = False
                asls_guard_reason = f"Low ASLS RR — calculated {asls_rr}, required {ASLS_MIN_RR}"

            if is_trade_blocked_by_execution_memory(
                trade_plan=asls_trade_plan,
                signal_data=asls_signal_data,
                setup=None,
                strategy_name=asls_strategy,
                signal=asls_signal,
            ):
                logger.info(
                    f"[PHASE 6H3 ASLS MEMORY BLOCK] setup_id={asls_setup_id}"
                )
                return current_candle_time

            if not asls_allowed:
                log_setup_event(
                    setup_id=asls_setup_id,
                    event="PHASE6H3_ASLS_BLOCKED",
                    strategy=asls_strategy,
                    signal=asls_signal,
                    entry_model=asls_entry_model,
                    score=asls_signal_data.get("score"),
                    session=asls_signal_data.get("session"),
                    market_condition=asls_signal_data.get("market_condition"),
                    entry=asls_entry,
                    sl=asls_sl,
                    tp=asls_tp,
                    rr=asls_rr,
                    required_rr=ASLS_MIN_RR,
                    reason=asls_guard_reason,
                    extra={
                        "current_execution_price": round(current_execution_price, 2),
                        "entry_distance": round(entry_distance, 2),
                        "intrabar_live_executor": True,
                    },
                )

                send_telegram_message(
                    f"🚫 Phase 6H3 Intrabar Scalp Blocked\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Signal: {asls_signal}\n"
                    f"Strategy: {asls_strategy}\n"
                    f"Setup ID: {asls_setup_id}\n\n"
                    f"Level: {asls_level}\n"
                    f"Entry: {asls_entry}\n"
                    f"Current: {round(current_execution_price, 2)}\n"
                    f"SL: {asls_sl}\n"
                    f"TP: {asls_tp}\n"
                    f"RR: {asls_rr}\n"
                    f"Reason: {asls_guard_reason}"
                )

                return current_candle_time

            log_setup_event(
                setup_id=asls_setup_id,
                event="PHASE6H3_ASLS_EXECUTION_ATTEMPT",
                strategy=asls_strategy,
                signal=asls_signal,
                entry_model=asls_entry_model,
                score=asls_signal_data.get("score"),
                session=asls_signal_data.get("session"),
                market_condition=asls_signal_data.get("market_condition"),
                entry=asls_entry,
                sl=asls_sl,
                tp=asls_tp,
                rr=asls_rr,
                required_rr=ASLS_MIN_RR,
                reason="Phase 6H3 intrabar structural scalp execution before M15 close",
                extra={
                    "current_execution_price": round(current_execution_price, 2),
                    "entry_distance": round(entry_distance, 2),
                    "intrabar_live_executor": True,
                },
            )

            send_telegram_message(
                f"⚡ Phase 6H3 Intrabar Structural Scalp\n"
                f"Symbol: {SYMBOL}\n"
                f"Signal: {asls_signal}\n"
                f"Strategy: {asls_strategy}\n"
                f"Setup ID: {asls_setup_id}\n\n"
                f"Entry Model: {asls_entry_model}\n"
                f"Level: {asls_level}\n"
                f"Entry: {asls_entry}\n"
                f"Current: {round(current_execution_price, 2)}\n"
                f"SL: {asls_sl}\n"
                f"TP: {asls_tp}\n"
                f"RR: {asls_rr}\n\n"
                f"Action: attempting execution before M15 close"
            )

            execution_result = execute_trade(asls_signal, asls_trade_plan, SYMBOL)

            if execution_result:
                log_setup_event(
                    setup_id=asls_setup_id,
                    event="PHASE6H3_ASLS_EXECUTED",
                    strategy=asls_strategy,
                    signal=asls_signal,
                    entry_model=asls_entry_model,
                    score=asls_signal_data.get("score"),
                    session=asls_signal_data.get("session"),
                    market_condition=asls_signal_data.get("market_condition"),
                    entry=asls_entry,
                    sl=asls_sl,
                    tp=asls_tp,
                    rr=asls_rr,
                    reason="Phase 6H3 intrabar structural scalp executed",
                )
            else:
                log_setup_event(
                    setup_id=asls_setup_id,
                    event="PHASE6H3_ASLS_EXECUTION_FAILED",
                    strategy=asls_strategy,
                    signal=asls_signal,
                    entry_model=asls_entry_model,
                    score=asls_signal_data.get("score"),
                    session=asls_signal_data.get("session"),
                    market_condition=asls_signal_data.get("market_condition"),
                    entry=asls_entry,
                    sl=asls_sl,
                    tp=asls_tp,
                    rr=asls_rr,
                    reason="Phase 6H3 intrabar structural scalp execute_trade returned False",
                )

            return current_candle_time


    # =========================
    # NEW CANDLE CHECK
    # =========================
    from src.session_engine import (
        detect_session,
        session_score_adjustment,
        session_blocks_strategy,
    )
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

    time_context = None

    if ENABLE_TIME_CONTEXT_ENGINE:
        time_context = analyze_time_context(current_candle_time)

        if time_context and time_context.get("active"):
            logger.info(
                f"[TIME CONTEXT] reasons={time_context.get('reasons')}"
            )

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
    from src.strategies.strategy_htf_fib_confluence import generate_signal as htf_fib_confluence_signal
    from src.strategies.strategy_supply_demand_retest import generate_signal as supply_demand_retest_signal
    from src.strategies.strategy_extreme_sweep_reclaim import generate_signal as extreme_sweep_reclaim_signal
    from src.strategies.strategy_mtf_sr_fvg_reclaim import generate_signal as mtf_sr_fvg_reclaim_signal
    from src.strategies.strategy_orb_v00 import generate_signal as orb_v00_signal
    from src.strategies.strategy_ifvg_retest_confluence import generate_signal as ifvg_retest_confluence_signal
    from src.strategies.strategy_range_sweep_reclaim import generate_signal as range_sweep_reclaim_signal
    from src.strategies.strategy_vwap_range_mean_reversion import generate_signal as vwap_range_mean_reversion_signal
    from src.strategies.strategy_balanced_auction_range import generate_signal as balanced_auction_range_signal
    from src.strategies.strategy_wavetrend_momentum import generate_signal as wavetrend_momentum_signal
    from src.strategies.strategy_micro_sr_sweep_reclaim import generate_signal as micro_sr_sweep_reclaim_signal
    from src.strategies.strategy_pro_trader_replication import generate_signal as pro_trader_replication_signal
    from src.strategies.strategy_key_level_break_hold import generate_signal as key_level_break_hold_signal
    from src.strategies.strategy_volatility_compression_breakout import generate_signal as volatility_compression_breakout_signal
    from src.strategies.strategy_psych_round_number_rejection import generate_signal as psych_round_number_rejection_signal
    from src.strategies.strategy_session_exhaustion_reversal import generate_signal as session_exhaustion_reversal_signal
    from src.strategies.strategy_auto_structural_level_scalp import generate_signal as auto_structural_level_scalp_signal
    from src.strategies.strategy_htf_rejection_candle_mtf_entry import generate_signal as htf_rejection_candle_mtf_entry_signal
    from src.strategies.strategy_htf_inside_bar_fakeout_mtf_entry import generate_signal as htf_inside_bar_fakeout_mtf_entry_signal
    from src.strategies.strategy_htf_double_top_bottom_mtf_entry import generate_signal as htf_double_top_bottom_mtf_entry_signal

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

    supply_demand_context = None

    if ENABLE_SUPPLY_DEMAND_CONTEXT:
        supply_demand_context = analyze_supply_demand_context(df)

        if supply_demand_context:
            logger.info(
                f"[SUPPLY DEMAND CONTEXT] "
                f"bias={supply_demand_context.get('bias')} "
                f"reasons={supply_demand_context.get('reasons')}"
            )

    elliott_fib_context = None

    if ENABLE_ELLIOTT_FIB_CONTEXT:
        elliott_fib_context = analyze_elliott_fib_context(df)

        if elliott_fib_context:
            logger.info(
                f"[ELLIOTT FIB CONTEXT] "
                f"bias={elliott_fib_context.get('bias')} "
                f"timeframe={elliott_fib_context.get('timeframe')} "
                f"zone={elliott_fib_context.get('zone_low')}-"
                f"{elliott_fib_context.get('zone_high')}"
            )

    protected_reentry_context = {}

    if ENABLE_PROTECTED_REENTRY:
        protected_reentry_context = get_protected_reentry_context()

    # =========================
    # AI STRATEGY SELECTION
    # =========================
    if market_condition == "TRENDING":
        strategy_map = [
            ("ORB", orb_signal),
            ("ORB_V00", orb_v00_signal),
            ("RANGE_SWEEP_RECLAIM", range_sweep_reclaim_signal),
            ("SESSION_ORB_RETEST", session_orb_retest_signal),
            ("VOLATILITY_COMPRESSION_BREAKOUT", volatility_compression_breakout_signal),
            ("PSYCH_ROUND_NUMBER_REJECTION", psych_round_number_rejection_signal),
            ("SESSION_EXHAUSTION_REVERSAL", session_exhaustion_reversal_signal),
            ("HTF_REJECTION_CANDLE_MTF_ENTRY", htf_rejection_candle_mtf_entry_signal),
            ("HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY", htf_inside_bar_fakeout_mtf_entry_signal),
            ("HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY", htf_double_top_bottom_mtf_entry_signal),
            ("AUTO_STRUCTURAL_LEVEL_SCALP", auto_structural_level_scalp_signal),
            ("WAVETREND_MOMENTUM", wavetrend_momentum_signal),
            ("HTF_TREND_PULLBACK", htf_trend_pullback_signal),
            ("BREAKER_BLOCK", breaker_block_signal),
            ("MICRO_SR_SWEEP_RECLAIM", micro_sr_sweep_reclaim_signal),
            ("FAILED_BREAKOUT_REVERSAL", failed_breakout_reversal_signal),
            ("RELIEF_RALLY", relief_rally_signal),
            ("ORDER_BLOCK", order_block_signal),
            ("FVG_CE_MITIGATION", fvg_ce_mitigation_signal),
            ("OB_FVG_COMBO", ob_fvg_combo_signal),
            ("HTF_FIB_CONFLUENCE", htf_fib_confluence_signal),
            ("LVN_FVG_RECLAIM", lvn_fvg_reclaim_signal),
            ("MTF_OB_ENTRY", mtf_ob_entry_signal),
            ("KEY_LEVEL_BREAK_HOLD", key_level_break_hold_signal),
            ("FCR_M1_FVG", fcr_m1_fvg_signal),
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
            ("WAVETREND_MOMENTUM", wavetrend_momentum_signal),
            ("BREAKER_BLOCK", breaker_block_signal),
            ("HTF_TREND_PULLBACK", htf_trend_pullback_signal),
            ("RELIEF_RALLY", relief_rally_signal),
            ("MICRO_SR_SWEEP_RECLAIM", micro_sr_sweep_reclaim_signal),
            ("ORDER_BLOCK", order_block_signal),
            ("FVG_CE_MITIGATION", fvg_ce_mitigation_signal),
            ("IFVG_RETEST_CONFLUENCE", ifvg_retest_confluence_signal),
            ("OB_FVG_COMBO", ob_fvg_combo_signal),
            ("HTF_FIB_CONFLUENCE", htf_fib_confluence_signal),
            ("MTF_SR_FVG_RECLAIM", mtf_sr_fvg_reclaim_signal),
            ("SUPPLY_DEMAND_RETEST", supply_demand_retest_signal),
            ("FVG", fvg_signal),
            ("WAVETREND_PIVOT", wavetrend_pivot_signal),
            ("STRUCTURE_LIQUIDITY", structure_liquidity_signal),
            ("LIQUIDITY_CANDLE", liquidity_candle_signal),
            ("SNIPER_V2", sniper_signal),
            ("STRICT", strict_signal),
        ]

    elif market_condition == "RANGING":
        strategy_map = [
            ("BREAKER_BLOCK", breaker_block_signal),
            ("FAILED_FVG_REVERSAL", failed_fvg_reversal_signal),
            ("FAILED_BREAKOUT_REVERSAL", failed_breakout_reversal_signal),
            ("MICRO_SR_SWEEP_RECLAIM", micro_sr_sweep_reclaim_signal),
            ("VWAP_RANGE_MEAN_REVERSION", vwap_range_mean_reversion_signal),
            ("SESSION_EXHAUSTION_REVERSAL", session_exhaustion_reversal_signal),
            ("HTF_REJECTION_CANDLE_MTF_ENTRY", htf_rejection_candle_mtf_entry_signal),
            ("HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY", htf_inside_bar_fakeout_mtf_entry_signal),
            ("HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY", htf_double_top_bottom_mtf_entry_signal),
            ("BALANCED_AUCTION_RANGE", balanced_auction_range_signal),
            ("PSYCH_ROUND_NUMBER_REJECTION", psych_round_number_rejection_signal),
            ("VWAP_RECLAIM", vwap_reclaim_signal),
            ("LIQUIDITY_TRAP", liquidity_trap_signal),
            ("FRACTAL_SWEEP", fractal_sweep_signal),
            ("ORDER_BLOCK", order_block_signal),
            ("HEAD_SHOULDERS", head_shoulders_signal),
            ("IFVG_RETEST_CONFLUENCE", ifvg_retest_confluence_signal),
            ("MTF_SR_FVG_RECLAIM", mtf_sr_fvg_reclaim_signal),
            ("SUPPLY_DEMAND_RETEST", supply_demand_retest_signal),
            ("EXTREME_SWEEP_RECLAIM", extreme_sweep_reclaim_signal),
            ("STRUCTURE_LIQUIDITY", structure_liquidity_signal),
            ("CRT_TBS", crt_tbs_signal),
            ("LIQUIDITY_POOL_OB", liquidity_pool_ob_signal),
            ("AMD_FVG", amd_fvg_signal),
            ("SMT_PRO", smt_pro_signal),
            ("SMT", smt_signal),
            ("LIQUIDITY_SWEEP", liquidity_sweep_signal),
            ("LIQUIDITY_CANDLE", liquidity_candle_signal),
            ("FAST", fast_signal),
            ("SNIPER_V2", sniper_signal),
        ]


    elif market_condition == "VOLATILE":
        strategy_map = [
            ("FAILED_BREAKOUT_REVERSAL", failed_breakout_reversal_signal),
            ("FAILED_FVG_REVERSAL", failed_fvg_reversal_signal),
            ("LIQUIDITY_TRAP", liquidity_trap_signal),
            ("FRACTAL_SWEEP", fractal_sweep_signal),
            ("EXTREME_SWEEP_RECLAIM", extreme_sweep_reclaim_signal),
            ("MICRO_SR_SWEEP_RECLAIM", micro_sr_sweep_reclaim_signal),
            ("VWAP_RECLAIM", vwap_reclaim_signal),
            ("BREAKER_BLOCK", breaker_block_signal),
            ("SESSION_ORB_RETEST", session_orb_retest_signal),
            ("WAVETREND_MOMENTUM", wavetrend_momentum_signal),
            ("STRUCTURE_LIQUIDITY", structure_liquidity_signal),
            ("IFVG_RETEST_CONFLUENCE", ifvg_retest_confluence_signal),
            ("MTF_SR_FVG_RECLAIM", mtf_sr_fvg_reclaim_signal),
            ("SUPPLY_DEMAND_RETEST", supply_demand_retest_signal),
            ("CRT_TBS", crt_tbs_signal),
            ("SMT_PRO", smt_pro_signal),
            ("SMT", smt_signal),
            ("LIQUIDITY_POOL_OB", liquidity_pool_ob_signal),
            ("AMD_FVG", amd_fvg_signal),
            ("LVN_FVG_RECLAIM", lvn_fvg_reclaim_signal),
            ("ORB", orb_signal),
            ("ORB_V00", orb_v00_signal),
            ("FVG_CE_MITIGATION", fvg_ce_mitigation_signal),
            ("ORDER_BLOCK", order_block_signal),
            ("FCR_M1_FVG", fcr_m1_fvg_signal),
            ("LIQUIDITY_SWEEP", liquidity_sweep_signal),
            ("LIQUIDITY_CANDLE", liquidity_candle_signal),
            ("STRICT", strict_signal),
            ("FVG", fvg_signal),
        ]

    # =========================
    # STRATEGY TOGGLES
    # =========================
    if not ENABLE_MICRO_SR_SWEEP_RECLAIM:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "MICRO_SR_SWEEP_RECLAIM"
        ]
        logger.info("[STRATEGY TOGGLE] MICRO_SR_SWEEP_RECLAIM disabled")

    if not ENABLE_WAVETREND_MOMENTUM_M5:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "WAVETREND_MOMENTUM"
        ]
        logger.info("[STRATEGY TOGGLE] WAVETREND_MOMENTUM disabled")

    if not ENABLE_RANGE_SWEEP_RECLAIM:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "RANGE_SWEEP_RECLAIM"
        ]
        logger.info("[STRATEGY TOGGLE] RANGE_SWEEP_RECLAIM disabled")

    if not ENABLE_VWAP_RANGE_MEAN_REVERSION:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "VWAP_RANGE_MEAN_REVERSION"
        ]
        logger.info("[STRATEGY TOGGLE] VWAP_RANGE_MEAN_REVERSION disabled")

    if not ENABLE_BALANCED_AUCTION_RANGE:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "BALANCED_AUCTION_RANGE"
        ]
        logger.info("[STRATEGY TOGGLE] BALANCED_AUCTION_RANGE disabled")

    if not ENABLE_VOLATILITY_COMPRESSION_BREAKOUT:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "VOLATILITY_COMPRESSION_BREAKOUT"
        ]
        logger.info("[STRATEGY TOGGLE] VOLATILITY_COMPRESSION_BREAKOUT disabled")

    if not ENABLE_PSYCH_ROUND_NUMBER_REJECTION:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "PSYCH_ROUND_NUMBER_REJECTION"
        ]
        logger.info("[STRATEGY TOGGLE] PSYCH_ROUND_NUMBER_REJECTION disabled")

    if not ENABLE_SESSION_EXHAUSTION_REVERSAL:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "SESSION_EXHAUSTION_REVERSAL"
        ]
        logger.info("[STRATEGY TOGGLE] SESSION_EXHAUSTION_REVERSAL disabled")

    if not ENABLE_AUTO_STRUCTURAL_LEVEL_SCALP:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "AUTO_STRUCTURAL_LEVEL_SCALP"
        ]
        logger.info("[STRATEGY TOGGLE] AUTO_STRUCTURAL_LEVEL_SCALP disabled")

    if not ENABLE_HTF_REJECTION_CANDLE_MTF_ENTRY:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "HTF_REJECTION_CANDLE_MTF_ENTRY"
        ]
        logger.info("[STRATEGY TOGGLE] HTF_REJECTION_CANDLE_MTF_ENTRY disabled")

    if not ENABLE_HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY"
        ]
        logger.info("[STRATEGY TOGGLE] HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY disabled")

    if not ENABLE_HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY"
        ]
        logger.info("[STRATEGY TOGGLE] HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY disabled")

    if not ENABLE_IFVG_RETEST_CONFLUENCE:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "IFVG_RETEST_CONFLUENCE"
        ]
        logger.info("[STRATEGY TOGGLE] IFVG_RETEST_CONFLUENCE disabled")

    if not ENABLE_ORB_V00:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "ORB_V00"
        ]
        logger.info("[STRATEGY TOGGLE] ORB_V00 disabled")

    if not ENABLE_MTF_SR_FVG_RECLAIM:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "MTF_SR_FVG_RECLAIM"
        ]
        logger.info("[STRATEGY TOGGLE] MTF_SR_FVG_RECLAIM disabled")

    if not ENABLE_EXTREME_SWEEP_RECLAIM:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "EXTREME_SWEEP_RECLAIM"
        ]
        logger.info("[STRATEGY TOGGLE] EXTREME_SWEEP_RECLAIM disabled")

    if not ENABLE_SUPPLY_DEMAND_RETEST:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "SUPPLY_DEMAND_RETEST"
        ]
        logger.info("[STRATEGY TOGGLE] SUPPLY_DEMAND_RETEST disabled")

    if not ENABLE_HTF_FIB_CONFLUENCE:
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "HTF_FIB_CONFLUENCE"
        ]
        logger.info("[STRATEGY TOGGLE] HTF_FIB_CONFLUENCE disabled")

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

    if (
        ENABLE_FCR_M1_FVG_STARTUP_GUARD
        and FCR_M1_FVG_SKIP_ON_FIRST_CYCLE_AFTER_STARTUP
        and last_processed_candle_time is None
    ):
        strategy_map = [
            (name, strat)
            for name, strat in strategy_map
            if name != "FCR_M1_FVG"
        ]
        logger.info(
            "[PHASE 6R FCR STARTUP GUARD] "
            "FCR_M1_FVG skipped on first full cycle after startup/restart"
        )
        
    if not ENABLE_KEY_LEVEL_BREAK_HOLD:
        strategy_map = [
            (name, fn)
            for name, fn in strategy_map
            if name != "KEY_LEVEL_BREAK_HOLD"
        ]
        logger.info("[STRATEGY TOGGLE] KEY_LEVEL_BREAK_HOLD disabled")

    if ENABLE_PRO_TRADER_REPLICATION:
        strategy_map.insert(0, ("PRO_TRADER_REPLICATION", pro_trader_replication_signal))
        logger.info("[STRATEGY TOGGLE] PRO_TRADER_REPLICATION enabled")

    logger.info(
        f"[STRATEGY MAP ACTIVE] "
        f"market_condition={market_condition} "
        f"session={session_name} "
        f"count={len(strategy_map)} "
        f"strategies={[name for name, _ in strategy_map]}"
    )

    for name, strat in strategy_map:

        # 🔒 AUTO-DISABLE
        if name in disabled_strategies:
            logger.info(f"[AUTO-DISABLE] Skipping {name} (low performance)")
            continue

        try:
            if ENABLE_SESSION_ENGINE:
                blocked_by_session, session_block_reason = session_blocks_strategy(
                    name,
                    session_name,
                )

                if blocked_by_session:
                    logger.info(
                        f"[SESSION STRATEGY BLOCKED] "
                        f"strategy={name} session={session_name} "
                        f"reason={session_block_reason}"
                    )

                    if LOG_STRATEGY_SESSION_BLOCKS_TO_SHEETS:
                        log_setup_event(
                            setup_id=f"SESSION-BLOCK-{name}-{int(tick.time)}",
                            event="STRATEGY_SESSION_BLOCKED",
                            strategy=name,
                            signal="N/A",
                            session=session_name,
                            market_condition=market_condition,
                            reason=session_block_reason,
                        )

                    continue
                
            opening_blocked, opening_block_reason = opening_strategy_blackout_blocks(
                name,
                current_candle_time,
            )

            if opening_blocked:
                logger.info(
                    f"[OPENING STRATEGY BLACKOUT] "
                    f"strategy={name} session={session_name} "
                    f"market_condition={market_condition} "
                    f"reason={opening_block_reason}"
                )

                if LOG_OPENING_BLACKOUT_BLOCKS_TO_SHEETS:
                    log_setup_event(
                        setup_id=f"OPENING-BLOCK-{name}-{int(tick.time)}",
                        event="STRATEGY_OPENING_BLACKOUT_BLOCKED",
                        strategy=name,
                        signal="N/A",
                        session=session_name,
                        market_condition=market_condition,
                        reason=opening_block_reason,
                    )

                continue

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

                if ENABLE_SUPPLY_DEMAND_CONTEXT:
                    sd_boost, sd_reasons = apply_supply_demand_confirmation(
                        result,
                        supply_demand_context,
                    )

                    result["score"] += sd_boost

                    if sd_reasons:
                        result.setdefault("supply_demand_reasons", [])
                        result["supply_demand_reasons"].extend(sd_reasons)

                        logger.info(
                            f"[SUPPLY DEMAND CONFIRMATION] "
                            f"strategy={name} signal={result.get('signal')} "
                            f"boost={sd_boost} reasons={sd_reasons}"
                        )

                if ENABLE_ELLIOTT_FIB_CONTEXT:
                    fib_boost, fib_reasons = apply_elliott_fib_confirmation(
                        result,
                        elliott_fib_context,
                    )

                    result["score"] += fib_boost

                    if fib_reasons:
                        result.setdefault("elliott_fib_reasons", [])
                        result["elliott_fib_reasons"].extend(fib_reasons)

                        logger.info(
                            f"[ELLIOTT FIB CONFIRMATION] "
                            f"strategy={name} signal={result.get('signal')} "
                            f"boost={fib_boost} reasons={fib_reasons}"
                        )

                if ENABLE_PROTECTED_REENTRY:
                    reentry_boost, reentry_reasons = apply_protected_reentry_confirmation(
                        result,
                        protected_reentry_context,
                    )

                    result["score"] += reentry_boost

                    if reentry_reasons:
                        result.setdefault("protected_reentry_reasons", [])
                        result["protected_reentry_reasons"].extend(reentry_reasons)

                        logger.info(
                            f"[PROTECTED REENTRY CONFIRMATION] "
                            f"strategy={name} signal={result.get('signal')} "
                            f"boost={reentry_boost} reasons={reentry_reasons}"
                        )

                if ENABLE_TIME_CONTEXT_ENGINE:
                    time_boost, time_reasons = apply_time_context_confirmation(
                        result,
                        time_context,
                    )

                    result["score"] += time_boost

                    if time_reasons:
                        result.setdefault("time_context_reasons", [])
                        result["time_context_reasons"].extend(time_reasons)

                        logger.info(
                            f"[TIME CONTEXT CONFIRMATION] "
                            f"strategy={name} signal={result.get('signal')} "
                            f"boost={time_boost} reasons={time_reasons}"
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
                    
                similarity_adjustment, similarity_reasons, similarity_report = (
                    get_setup_similarity_score_adjustment(
                        candidate=result,
                        session_name=session_name,
                        market_condition=market_condition,
                        current_time=current_candle_time,
                    )
                )

                if similarity_adjustment:
                    result["score"] += similarity_adjustment
                    result.setdefault("similarity_reasons", [])
                    result["similarity_reasons"].extend(similarity_reasons)
                    result["similarity_memory"] = similarity_report

                    logger.info(
                        f"[SIMILARITY SCORING] "
                        f"strategy={name} signal={result.get('signal')} "
                        f"adjustment={similarity_adjustment} "
                        f"classification={similarity_report.get('classification') if similarity_report else None}"
                    )

                result["score"] = max(0, min(result["score"], 100))

                result["setup_id"] = build_stable_candidate_setup_id(
                    candidate=result,
                    strategy_name=name,
                    signal=signal_value,
                    tick_time=tick.time,
                )

                duplicate_active, duplicate_state = is_setup_id_already_active(result["setup_id"])

                if duplicate_active:
                    logger.info(
                        f"[SETUP DUPLICATE SUPPRESSED] "
                        f"setup_id={result['setup_id']} "
                        f"strategy={name} signal={signal_value} "
                        f"state={duplicate_state}"
                    )

                    log_setup_event(
                        setup_id=result["setup_id"],
                        event="SETUP_DUPLICATE_SUPPRESSED",
                        strategy=name,
                        signal=signal_value,
                        entry_model=result.get("entry_model"),
                        score=result.get("score"),
                        session=session_name,
                        market_condition=market_condition,
                        reason=f"same structural setup already active state={duplicate_state}",
                    )

                    continue
                
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

        ranked_candidates = []

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

            if not is_valid:
                if is_mtf_conflict_rejection(rejection_reason):
                    mtf_conflict_executed = process_mtf_conflict_candidate(
                        candidate=candidate,
                        rejection_reason=rejection_reason,
                        df=df,
                        tick=tick,
                        account_info=account_info,
                        market_condition=market_condition,
                        session_name=session_name,
                    )

                    if mtf_conflict_executed:
                        return current_candle_time

                rejected_candidates.append(
                    {
                        "strategy": candidate.get("strategy"),
                        "signal": candidate.get("signal"),
                        "score": candidate.get("score"),
                        "reason": rejection_reason,
                    }
                )
                
                candidate_news_context = attach_news_context_to_signal_data(candidate)

                handle_generic_rejected_candidate_trade_plan(
                    df=df,
                    tick=tick,
                    account_info=account_info,
                    candidate=candidate,
                    candidate_strategy=candidate.get("strategy"),
                    candidate_signal=candidate.get("signal"),
                    session_name=session_name,
                    market_condition=market_condition,
                    rejection_reason=rejection_reason,
                    news_context=candidate_news_context,
                )

                logger.info(
                    f"[CANDIDATE REJECTED] "
                    f"strategy={candidate.get('strategy')} "
                    f"signal={candidate.get('signal')} "
                    f"score={candidate.get('score')} "
                    f"reason={rejection_reason}"
                )
                
                candidate_setup_id = candidate.get("setup_id") or build_stable_candidate_setup_id(
                    candidate=candidate,
                    strategy_name=candidate.get("strategy"),
                    signal=candidate.get("signal"),
                    tick_time=tick.time,
                )

                candidate["setup_id"] = candidate_setup_id

                log_setup_event(
                    setup_id=candidate_setup_id,
                    event="CANDIDATE_REJECTED",
                    strategy=candidate.get("strategy"),
                    signal=candidate.get("signal"),
                    entry_model=candidate.get("entry_model"),
                    score=candidate.get("score"),
                    session=session_name,
                    market_condition=market_condition,
                    reason=rejection_reason,
                )
                
                tracked = register_rejected_candidate_setup_outcome(
                    candidate=candidate,
                    rejection_reason=rejection_reason,
                    df=df,
                    tick=tick,
                    account_info=account_info,
                    market_condition=market_condition,
                    session_name=session_name,
                    setup_id=candidate_setup_id,
                )
                
                if tracked:
                    notify_setup_similarity_if_relevant(candidate_setup_id)
                    notify_scenario_cluster_if_relevant(candidate_setup_id)
                
                    rejected_trade_plan = candidate.get("rejected_trade_plan") or {}
                
                    notify_rejected_candidate_if_relevant(
                        setup_id=candidate_setup_id,
                        strategy=candidate.get("strategy"),
                        signal=candidate.get("signal"),
                        entry_model=candidate.get("entry_model"),
                        session_name=session_name,
                        market_condition=market_condition,
                        score=candidate.get("score"),
                        rr=candidate.get("rejected_rr_value") or 0,
                        entry=rejected_trade_plan.get("entry_price"),
                        sl=rejected_trade_plan.get("stop_loss"),
                        tp=rejected_trade_plan.get("take_profit"),
                        reason=rejection_reason,
                    )

                    try:
                        from src.setup_conflict_memory import (
                            format_conflict_telegram_message,
                            record_setup_state_event,
                        )

                        phase5ah_rejected_conflict_report = record_setup_state_event(
                            {
                                "symbol": SYMBOL,
                                "setup_id": candidate_setup_id,
                                "strategy": candidate.get("strategy"),
                                "signal": candidate.get("signal"),
                                "score": candidate.get("score"),
                                "min_required_score": (
                                    candidate.get("min_required_score")
                                    or candidate.get("required_score")
                                ),
                                "entry_model": candidate.get("entry_model"),
                                "session": session_name,
                                "market_condition": market_condition,
                                "entry": rejected_trade_plan.get("entry_price")
                                or rejected_trade_plan.get("entry"),
                                "sl": rejected_trade_plan.get("stop_loss")
                                or rejected_trade_plan.get("sl"),
                                "tp": rejected_trade_plan.get("take_profit")
                                or rejected_trade_plan.get("tp"),
                                "rr": candidate.get("rejected_rr_value")
                                or candidate.get("rr")
                                or candidate.get("risk_reward")
                                or 0,
                                "state": (
                                    "REJECTED_SCORE_TOO_LOW"
                                    if "score_too_low" in str(rejection_reason)
                                    else "TRACKED_REJECTED_CANDIDATE"
                                ),
                                "rejection_reason": rejection_reason,
                                "reason": rejection_reason,
                                "created_at_epoch": getattr(tick, "time", None),
                            }
                        )

                        if (
                            phase5ah_rejected_conflict_report
                            and phase5ah_rejected_conflict_report.get("priority_conflict_review")
                            and not phase5ah_rejected_conflict_report.get("duplicate_conflict")
                        ):
                            send_telegram_message_async(
                                format_conflict_telegram_message(
                                    phase5ah_rejected_conflict_report
                                )
                            )
                    except Exception as phase5ah_exc:
                        logger.warning(
                            f"[PHASE 5AH] rejected candidate conflict memory failed | "
                            f"setup_id={candidate_setup_id} strategy={candidate.get('strategy')} "
                            f"signal={candidate.get('signal')} error={phase5ah_exc}"
                        )
                
                if (
                    ENABLE_CANDIDATE_REJECTION_TELEGRAM_ALERTS
                    and TELEGRAM_NOTIFY_GENERIC_CANDIDATE_REJECTED
                ):
                    send_telegram_message(
                        f"🚫 Candidate Rejected\n"
                        f"Symbol: {SYMBOL}\n"
                        f"Strategy: {candidate.get('strategy')}\n"
                        f"Signal: {candidate.get('signal')}\n"
                        f"Score: {candidate.get('score')}\n\n"
                        f"Reason: {rejection_reason}"
                    )
                
                continue

            candidate_signal = validated_candidate.get("signal")
            candidate_strategy = validated_candidate.get("strategy", "UNKNOWN")

            candidate_trade_plan = calculate_trade_plan(
                df=df,
                signal=candidate_signal,
                tick=tick,
                account_balance=account_info.balance,
                signal_data=validated_candidate,
            )

            if candidate_trade_plan is None:
                rejection_reason = "trade_plan_failed"

                rejected_candidates.append(
                    {
                        "strategy": candidate_strategy,
                        "signal": candidate_signal,
                        "score": validated_candidate.get("score"),
                        "reason": rejection_reason,
                    }
                )
                
                candidate_news_context = attach_news_context_to_signal_data(validated_candidate)

                handle_generic_rejected_candidate_trade_plan(
                    df=df,
                    tick=tick,
                    account_info=account_info,
                    candidate=validated_candidate,
                    candidate_strategy=candidate_strategy,
                    candidate_signal=candidate_signal,
                    session_name=session_name,
                    market_condition=market_condition,
                    rejection_reason=rejection_reason,
                    news_context=candidate_news_context,
                )

                logger.info(
                    f"[CANDIDATE REJECTED] "
                    f"strategy={candidate_strategy} "
                    f"signal={candidate_signal} "
                    f"score={validated_candidate.get('score')} "
                    f"reason={rejection_reason}"
                )
                
                save_trade_plan_memory_report(
                    selected_signal_data=validated_candidate,
                    strategy_name=candidate_strategy,
                    signal=candidate_signal,
                    score=validated_candidate.get("score"),
                    session_name=session_name,
                    market_condition=market_condition,
                    reason=rejection_reason,
                    trade_plan=None,
                    decision="CANDIDATE_TRADE_PLAN_FAILED",
                    decision_reason="candidate calculate_trade_plan returned None",
                )

                continue

            candidate_trade_plan["signal"] = candidate_signal

            min_rr_required = get_min_rr(
                candidate_strategy,
                validated_candidate.get("entry_model"),
                validated_candidate.get("sl_model"),
            )

            same_direction_count = count_same_direction_positions(SYMBOL, candidate_signal)

            if same_direction_count >= 1 and ENABLE_EXTRA_RR_DISCOUNT:
                min_rr_required = round(min_rr_required * EXTRA_RR_MULTIPLIER, 2)

            rr_value = calculate_rr_value(candidate_trade_plan)

            if rr_value is None or rr_value < min_rr_required:
                rejection_reason = f"low_rr {rr_value}/{min_rr_required}"

                rejected_candidates.append(
                    {
                        "strategy": candidate_strategy,
                        "signal": candidate_signal,
                        "score": validated_candidate.get("score"),
                        "reason": rejection_reason,
                    }
                )
                
                candidate_news_context = attach_news_context_to_signal_data(validated_candidate)

                handle_generic_rejected_candidate_trade_plan(
                    df=df,
                    tick=tick,
                    account_info=account_info,
                    candidate=validated_candidate,
                    candidate_strategy=candidate_strategy,
                    candidate_signal=candidate_signal,
                    session_name=session_name,
                    market_condition=market_condition,
                    rejection_reason=rejection_reason,
                    news_context=candidate_news_context,
                )

                logger.info(
                    f"[CANDIDATE REJECTED BY SMART SELECTION] "
                    f"strategy={candidate_strategy} "
                    f"signal={candidate_signal} "
                    f"score={validated_candidate.get('score')} "
                    f"rr={rr_value} required={min_rr_required}"
                )
                
                save_trade_plan_memory_report(
                    selected_signal_data=validated_candidate,
                    strategy_name=candidate_strategy,
                    signal=candidate_signal,
                    score=validated_candidate.get("score"),
                    session_name=session_name,
                    market_condition=market_condition,
                    reason=rejection_reason,
                    trade_plan=candidate_trade_plan,
                    decision="CANDIDATE_REJECTED_LOW_RR",
                    decision_reason="candidate trade plan calculated but RR below required threshold",
                    rr_value=rr_value,
                    required_rr=min_rr_required,
                )

                log_setup_event(
                    setup_id=build_setup_id(
                        candidate_strategy,
                        candidate_signal,
                        tick.time,
                    ),
                    event="CANDIDATE_REJECTED_LOW_RR",
                    strategy=candidate_strategy,
                    signal=candidate_signal,
                    entry_model=validated_candidate.get("entry_model"),
                    score=validated_candidate.get("score"),
                    session=session_name,
                    market_condition=market_condition,
                    entry=candidate_trade_plan.get("entry_price"),
                    sl=candidate_trade_plan.get("stop_loss"),
                    tp=candidate_trade_plan.get("take_profit"),
                    rr=rr_value,
                    required_rr=min_rr_required,
                    reason=rejection_reason,
                )
                
                news_context = attach_news_context_to_signal_data(validated_candidate)
                
                tracked = register_setup_outcome(
                    symbol=SYMBOL,
                    setup_id=validated_candidate.get("setup_id"),
                    event="CANDIDATE_REJECTED_LOW_RR",
                    strategy=candidate_strategy,
                    signal=candidate_signal,
                    entry_model=validated_candidate.get("entry_model"),
                    score=validated_candidate.get("score"),
                    session=session_name,
                    market_condition=market_condition,
                    entry=candidate_trade_plan.get("entry_price"),
                    sl=candidate_trade_plan.get("stop_loss"),
                    tp=candidate_trade_plan.get("take_profit"),
                    reason=rejection_reason,
                    extra={
                        "rr": rr_value,
                        "required_rr": min_rr_required,
                        "source": "candidate_rejected_low_rr",
                        "news_context": news_context,
                        "news_tag": news_context.get("news_tag") if news_context else None,
                    },
                )
                
                if tracked:
                    notify_setup_similarity_if_relevant(validated_candidate.get("setup_id"))
                    notify_scenario_cluster_if_relevant(validated_candidate.get("setup_id"))
                
                if (
                    ENABLE_CANDIDATE_REJECTION_TELEGRAM_ALERTS
                    and TELEGRAM_NOTIFY_CANDIDATE_REJECTED_LOW_RR
                ):
                    send_telegram_message(
                        f"⚠️ Candidate Rejected — Low RR\n"
                        f"Symbol: {SYMBOL}\n"
                        f"Strategy: {candidate_strategy}\n"
                        f"Signal: {candidate_signal}\n"
                        f"Setup ID: {validated_candidate.get('setup_id', 'N/A')}\n"
                        f"Entry Model: {validated_candidate.get('entry_model')}\n"
                        f"Reason: {rejection_reason}\n"
                        f"Candidate Reason: {validated_candidate.get('reason', 'N/A')}\n\n"
                        f"Entry: {candidate_trade_plan.get('entry_price')}\n"
                        f"SL: {candidate_trade_plan.get('stop_loss')}\n"
                        f"{_format_telegram_tp123_from_trade_plan(candidate_signal, candidate_trade_plan)}\n"
                        f"RR: {rr_value} / Required: {min_rr_required}\n\n"
                        f"Action: moved to candidate recovery if eligible."
                    )
                
                register_rejected_candidate_for_recovery(
                    symbol=SYMBOL,
                    signal=candidate_signal,
                    strategy=candidate_strategy,
                    score=validated_candidate.get("score", 0),
                    reason_type="LOW_RR",
                    rejection_reason=rejection_reason,
                    signal_data=validated_candidate,
                    required_rr=min_rr_required,
                    current_rr=rr_value,
                )

                continue

            final_rank, rank_details = calculate_candidate_selection_rank(
                candidate=validated_candidate,
                rr_value=rr_value,
                min_rr_required=min_rr_required,
                market_condition=market_condition,
            )

            validated_candidate["selection_rr"] = rr_value
            validated_candidate["selection_required_rr"] = min_rr_required
            validated_candidate["selection_final_rank"] = final_rank
            validated_candidate["selection_rank_details"] = rank_details

            ranked_candidates.append(validated_candidate)

            logger.info(
                f"[SMART SELECTION CANDIDATE] "
                f"strategy={candidate_strategy} "
                f"signal={candidate_signal} "
                f"score={rank_details['score']} "
                f"rr={rank_details['rr']} "
                f"required_rr={rank_details['required_rr']} "
                f"rr_bonus={rank_details['rr_bonus']} "
                f"priority={rank_details['strategy_priority']} "
                f"session_adj={rank_details['session_adjustment']} "
                f"final_rank={rank_details['final_rank']}"
            )

        if ranked_candidates:
            ranked_candidates = sorted(
                ranked_candidates,
                key=lambda item: item.get("selection_final_rank", 0),
                reverse=True,
            )

            selected_candidate = ranked_candidates[0]

            if TELEGRAM_VERBOSE_SIGNALS:
                ranking_text = "\n".join(
                    [
                        f"- {item.get('strategy')} {item.get('signal')} "
                        f"score={item.get('score')} "
                        f"rr={item.get('selection_rr')} "
                        f"rank={item.get('selection_final_rank')}"
                        for item in ranked_candidates[:5]
                    ]
                )

                send_telegram_message(
                    f"🧠 Smart Candidate Selection\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Market: {market_condition}\n\n"
                    f"Selected: {selected_candidate.get('strategy')} "
                    f"{selected_candidate.get('signal')}\n"
                    f"Final Rank: {selected_candidate.get('selection_final_rank')}\n"
                    f"RR: {selected_candidate.get('selection_rr')} / "
                    f"Required: {selected_candidate.get('selection_required_rr')}\n\n"
                    f"Top candidates:\n{ranking_text}"
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

            try:
                from src.setup_conflict_memory import (
                    format_conflict_telegram_message,
                    record_setup_state_event,
                )

                setup_detected_conflict_report = record_setup_state_event(
                    {
                        "symbol": SYMBOL,
                        "setup_id": setup_id,
                        "strategy": strategy_name,
                        "signal": signal,
                        "score": score,
                        "entry_model": selected_signal_data.get("entry_model"),
                        "session": session_name,
                        "market_condition": market_condition,
                        "entry": selected_signal_data.get("entry")
                        or selected_signal_data.get("entry_price"),
                        "sl": selected_signal_data.get("sl")
                        or selected_signal_data.get("stop_loss"),
                        "tp": selected_signal_data.get("tp")
                        or selected_signal_data.get("take_profit"),
                        "rr": selected_signal_data.get("rr")
                        or selected_signal_data.get("risk_reward")
                        or selected_signal_data.get("rr_value"),
                        "state": "SETUP_DETECTED",
                        "reason": reason,
                        "created_at_epoch": getattr(tick, "time", None),
                    }
                )

                if (
                    setup_detected_conflict_report
                    and setup_detected_conflict_report.get("priority_conflict_review")
                    and not setup_detected_conflict_report.get("duplicate_conflict")
                ):
                    send_telegram_message_async(
                        format_conflict_telegram_message(setup_detected_conflict_report)
                    )
            except Exception as phase5ah_exc:
                logger.warning(
                    f"[PHASE 5AH] setup detected conflict memory failed | "
                    f"setup_id={setup_id} error={phase5ah_exc}"
                )

            if selected_signal_data.get("smc"):
                reason += f" | SMC: {','.join(selected_signal_data['smc'])}"

            if selected_signal_data.get("session_reasons"):
                reason += f" | SESSION: {','.join(selected_signal_data['session_reasons'])}"

            if selected_signal_data.get("structure_liquidity_reasons"):
                reason += (
                    f" | STRUCTURE/LIQUIDITY: "
                    f"{','.join(selected_signal_data['structure_liquidity_reasons'])}"
                )

            if selected_signal_data.get("supply_demand_reasons"):
                reason += (
                    f" | SUPPLY/DEMAND: "
                    f"{','.join(selected_signal_data['supply_demand_reasons'])}"
                )

            if selected_signal_data.get("elliott_fib_reasons"):
                reason += (
                    f" | ELLIOTT/FIB: "
                    f"{','.join(selected_signal_data['elliott_fib_reasons'])}"
                )

            if selected_signal_data.get("time_context_reasons"):
                reason += (
                    f" | TIME: "
                    f"{','.join(selected_signal_data['time_context_reasons'])}"
                )

            if selected_signal_data.get("protected_reentry_reasons"):
                reason += (
                    f" | PROTECTED REENTRY: "
                    f"{','.join(selected_signal_data['protected_reentry_reasons'])}"
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

                send_telegram_message_async(build_trade_message(detected_data))

                log_setup_event(
                    setup_id=selected_signal_data.get("setup_id"),
                    event="SETUP_DETECTED",
                    strategy=strategy_name,
                    signal=signal,
                    entry_model=selected_signal_data.get("entry_model"),
                    score=score,
                    session=session_name,
                    market_condition=market_condition,
                    entry=close_price,
                    sl=selected_signal_data.get("sl_reference"),
                    tp=(
                        selected_signal_data.get("tp_reference")
                        or selected_signal_data.get("pivot_target_level")
                    ),
                    reason=reason,
                    extra={
                        "protected_reentry": selected_signal_data.get("protected_reentry"),
                    },
                )
                
                news_context = attach_news_context_to_signal_data(selected_signal_data)
                
                tracked = register_setup_outcome(
                    symbol=SYMBOL,
                    setup_id=selected_signal_data.get("setup_id"),
                    event="SETUP_DETECTED",
                    strategy=strategy_name,
                    signal=signal,
                    entry_model=selected_signal_data.get("entry_model"),
                    score=score,
                    session=session_name,
                    market_condition=market_condition,
                    entry=close_price,
                    sl=selected_signal_data.get("sl_reference"),
                    tp=(
                        selected_signal_data.get("tp_reference")
                        or selected_signal_data.get("pivot_target_level")
                    ),
                    reason=reason,
                    extra={
                        "protected_reentry": selected_signal_data.get("protected_reentry"),
                        "source": "setup_detected_raw",
                        "news_context": news_context,
                        "news_tag": news_context.get("news_tag") if news_context else None,
                    },
                )
                
                if tracked:
                    notify_setup_similarity_if_relevant(selected_signal_data.get("setup_id"))
                    notify_scenario_cluster_if_relevant(selected_signal_data.get("setup_id"))

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
            "FAILED_BREAKOUT_REVERSAL",
            "FAILED_FVG_REVERSAL",
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

        final_liquidity_context = get_liquidity_context()

        if not liquidity_allows_signal(setup_signal, final_liquidity_context, allow_neutral=True):
            soft_override_allowed, soft_override_reason = (
                final_htf_liquidity_soft_override_allowed(
                    setup_strategy=setup_strategy,
                    setup_signal=setup_signal,
                    setup_score=setup_score,
                    setup_data=setup_data,
                    session_name=session_name,
                    liquidity_context=final_liquidity_context,
                )
            )

            if not soft_override_allowed:
                recovery_registered = register_rejected_candidate_for_recovery(
                    symbol=SYMBOL,
                    signal=setup_signal,
                    strategy=setup_strategy,
                    score=setup_score,
                    reason_type="HTF_LIQUIDITY_REJECTED",
                    rejection_reason=(
                        final_liquidity_context.get("reason")
                        if final_liquidity_context
                        else "N/A"
                    ),
                    signal_data=setup_data,
                )
                
                logger.info(
                    f"[FINAL HTF LIQUIDITY] Ready setup rejected | "
                    f"strategy={setup_strategy} signal={setup_signal} "
                    f"reason={final_liquidity_context.get('reason') if final_liquidity_context else None}"
                    f"recovery_registered={recovery_registered}"
                )

                send_telegram_message(
                    f"🚫 Ready Setup Rejected by Final HTF Liquidity\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Strategy: {setup_strategy}\n"
                    f"Signal: {setup_signal}\n"
                    f"Reason: {final_liquidity_context.get('reason') if final_liquidity_context else None}"
                    f"Recovery Registered: {recovery_registered}"
                )

                return current_candle_time

            setup_data["reason"] = (
                f"{setup_data.get('reason', 'N/A')} | "
                f"FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE: {soft_override_reason}"
            )

            logger.info(
                f"[FINAL HTF LIQUIDITY SOFT OVERRIDE] Ready setup allowed | "
                f"strategy={setup_strategy} signal={setup_signal} "
                f"{soft_override_reason}"
            )

            send_telegram_message(
                f"⚠️ Final HTF Liquidity Soft Override\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {setup_strategy}\n"
                f"Signal: {setup_signal}\n"
                f"Score: {setup_score}\n"
                f"Reason: {soft_override_reason}"
            )

        news_blocked, news_reason = is_news_blackout_active()

        if news_blocked:
            logger.info(
                f"[FINAL NEWS FILTER] Ready setup rejected | "
                f"strategy={setup_strategy} signal={setup_signal} reason={news_reason}"
            )

            send_telegram_message(
                f"🚫 Ready Setup Rejected by News Filter\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {setup_strategy}\n"
                f"Signal: {setup_signal}\n"
                f"Reason: {news_reason}"
            )

            return current_candle_time

        time_blocked, time_reason = is_trading_blackout_active()

        if time_blocked:
            logger.info(
                f"[FINAL TIME FILTER] Ready setup rejected | "
                f"strategy={setup_strategy} signal={setup_signal} reason={time_reason}"
            )

            send_telegram_message(
                f"🚫 Ready Setup Rejected by Time Filter\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {setup_strategy}\n"
                f"Signal: {setup_signal}\n"
                f"Reason: {time_reason}"
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

        cluster_adjustment, cluster_reasons, cluster_report = (
            get_scenario_cluster_score_adjustment(
                selected_signal_data.get("setup_id")
            )
        )

        if cluster_adjustment:
            score = max(0, min(score + cluster_adjustment, 100))
            selected_signal_data["score"] = score
            selected_signal_data.setdefault("scenario_cluster_reasons", [])
            selected_signal_data["scenario_cluster_reasons"].extend(cluster_reasons)
            selected_signal_data["scenario_cluster_memory"] = cluster_report

            reason += f" | SCENARIO_CLUSTER: {','.join(cluster_reasons)}"

            logger.info(
                f"[SCENARIO CLUSTER SCORING] "
                f"setup_id={selected_signal_data.get('setup_id')} "
                f"strategy={strategy_name} signal={signal} "
                f"adjustment={cluster_adjustment} "
                f"classification={cluster_report.get('classification') if cluster_report else None}"
            )
            
        signature_adjustment, signature_reasons, signature_report = (
            get_scenario_signature_score_adjustment(
                selected_signal_data.get("setup_id")
            )
        )

        if signature_adjustment:
            score = max(0, min(score + signature_adjustment, 100))
            selected_signal_data["score"] = score
            selected_signal_data.setdefault("scenario_signature_reasons", [])
            selected_signal_data["scenario_signature_reasons"].extend(signature_reasons)
            selected_signal_data["scenario_signature_memory"] = signature_report

            reason += f" | SCENARIO_SIGNATURE: {','.join(signature_reasons)}"

            log_setup_event(
                setup_id=selected_signal_data.get("setup_id"),
                event="SCENARIO_SIGNATURE_CONFIDENCE",
                strategy=strategy_name,
                signal=signal,
                entry_model=selected_signal_data.get("entry_model"),
                score=score,
                session=session_name,
                market_condition=market_condition,
                reason="scenario signature confidence applied",
                extra={
                    "adjustment": signature_adjustment,
                    "reasons": signature_reasons,
                    "classification": signature_report.get("classification") if signature_report else None,
                    "signature_key": signature_report.get("signature_key") if signature_report else None,
                    "stats": signature_report.get("stats") if signature_report else None,
                    "nearby_strategies": signature_report.get("nearby_strategies") if signature_report else None,
                },
            )
            
            signature_classification = (
                signature_report.get("classification")
                if signature_report
                else None
            )

            if (
                ENABLE_SCENARIO_SIGNATURE_TELEGRAM_ALERTS
                and signature_classification in SCENARIO_SIGNATURE_TELEGRAM_ALERT_CLASSIFICATIONS
                and not selected_signal_data.get("scenario_signature_notified")
            ):
                stats = signature_report.get("stats", {}) if signature_report else {}

                send_telegram_message(
                    f"🧠 Scenario Signature Confidence\n"
                    f"Setup ID: {selected_signal_data.get('setup_id')}\n"
                    f"Strategy: {strategy_name}\n"
                    f"Signal: {signal}\n"
                    f"Classification: {signature_classification}\n"
                    f"Adjustment: {signature_adjustment}\n\n"
                    f"Samples: {stats.get('total')}\n"
                    f"W10 Rate: {stats.get('w10_rate')}\n"
                    f"TP Rate: {stats.get('tp_rate')}\n"
                    f"SL Rate: {stats.get('sl_rate')}\n"
                    f"Avg Favorable: {stats.get('avg_favorable')}\n"
                    f"Avg Adverse: {stats.get('avg_adverse')}\n"
                    f"Avg Recovery Swing: {stats.get('avg_recovery_swing')}\n\n"
                    f"Signature: {signature_report.get('signature_key') if signature_report else None}"
                )

                selected_signal_data["scenario_signature_notified"] = True

            logger.info(
                f"[SCENARIO SIGNATURE SCORING] "
                f"setup_id={selected_signal_data.get('setup_id')} "
                f"strategy={strategy_name} signal={signal} "
                f"adjustment={signature_adjustment} "
                f"classification={signature_report.get('classification') if signature_report else None}"
            )

        ai_shadow_advice = get_ai_shadow_advice(
            selected_signal_data,
            session_name=session_name,
            market_condition=market_condition,
        )

        selected_signal_data["ai_shadow_advice"] = ai_shadow_advice

        logger.info(
            f"[AI SHADOW ADVISOR] "
            f"setup_id={selected_signal_data.get('setup_id')} "
            f"strategy={strategy_name} signal={signal} "
            f"recommendation={ai_shadow_advice.get('recommendation')} "
            f"reason={ai_shadow_advice.get('reason')}"
        )

        if (
            AI_SHADOW_ADVISOR_NOTIFY_TELEGRAM
            and ai_shadow_advice.get("recommendation") in ["ALLOW", "WARN", "BLOCK"]
        ):
            stats = ai_shadow_advice.get("stats", {})

            send_telegram_message(
                f"🤖 AI Shadow Advisor\n"
                f"Setup ID: {selected_signal_data.get('setup_id')}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n"
                f"Recommendation: {ai_shadow_advice.get('recommendation')}\n"
                f"Reason: {ai_shadow_advice.get('reason')}\n\n"
                f"Match: {ai_shadow_advice.get('match_type')}\n"
                f"Samples: {stats.get('total')}\n"
                f"W10 Rate: {stats.get('w10_rate')}\n"
                f"TP Rate: {stats.get('tp_rate')}\n"
                f"SL Rate: {stats.get('sl_rate')}\n\n"
                f"Mode: {AI_SHADOW_ADVISOR_EXECUTION_CONTROL_MODE}\n"
                f"Execution Control Enabled: {AI_SHADOW_ADVISOR_EXECUTION_CONTROL_ENABLED}"
            )
            
        ai_execution_allowed, ai_execution_reason = apply_ai_shadow_advisor_execution_control(
            ai_shadow_advice
        )

        selected_signal_data["ai_execution_allowed"] = ai_execution_allowed
        selected_signal_data["ai_execution_reason"] = ai_execution_reason

        logger.info(
            f"[AI SHADOW ADVISOR CONTROL] "
            f"setup_id={selected_signal_data.get('setup_id')} "
            f"strategy={strategy_name} signal={signal} "
            f"allowed={ai_execution_allowed} "
            f"mode={AI_SHADOW_ADVISOR_EXECUTION_CONTROL_MODE} "
            f"reason={ai_execution_reason}"
        )

        if not ai_execution_allowed:
            log_setup_event(
                setup_id=selected_signal_data.get("setup_id"),
                event="AI_ADVISOR_CONTROL_BLOCKED",
                strategy=strategy_name,
                signal=signal,
                entry_model=selected_signal_data.get("entry_model"),
                score=score,
                session=session_name,
                market_condition=market_condition,
                reason=ai_execution_reason,
                extra={
                    "ai_shadow_advice": ai_shadow_advice,
                    "control_mode": AI_SHADOW_ADVISOR_EXECUTION_CONTROL_MODE,
                },
            )
            
            if ENABLE_MEMORY_DECISION_REPORT:
                memory_report = build_memory_decision_report(
                    setup_id=selected_signal_data.get("setup_id"),
                    strategy=strategy_name,
                    signal=signal,
                    score=score,
                    session=session_name,
                    market_condition=market_condition,
                    reason=reason,
                    signal_data=selected_signal_data,
                    trade_plan=None,
                    decision="AI_ADVISOR_CONTROL_BLOCKED",
                    decision_reason=ai_execution_reason,
                    extra={
                        "ai_shadow_advice": ai_shadow_advice,
                        "control_mode": AI_SHADOW_ADVISOR_EXECUTION_CONTROL_MODE,
                    },
                )

                save_memory_decision_report(memory_report)

            send_telegram_message(
                f"🤖 AI Advisor Control Blocked\n"
                f"Setup ID: {selected_signal_data.get('setup_id')}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n"
                f"Recommendation: {ai_shadow_advice.get('recommendation')}\n"
                f"Reason: {ai_execution_reason}\n\n"
                f"Mode: {AI_SHADOW_ADVISOR_EXECUTION_CONTROL_MODE}"
            )

            return current_candle_time
        
        if ENABLE_MEMORY_DECISION_REPORT:
            memory_report = build_memory_decision_report(
                setup_id=selected_signal_data.get("setup_id"),
                strategy=strategy_name,
                signal=signal,
                score=score,
                session=session_name,
                market_condition=market_condition,
                reason=reason,
                signal_data=selected_signal_data,
                trade_plan=None,
                decision="PRE_TRADE_PLAN_REVIEW",
                decision_reason="setup selected before risk/trade plan calculation",
            )

            save_memory_decision_report(memory_report)

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
        try:
            from src.key_level_tp_ladder import apply_key_level_tp_ladder

            trade_plan = apply_key_level_tp_ladder(
                df=df,
                signal=signal,
                trade_plan=trade_plan,
                signal_data=selected_signal_data,
                strategy_name=strategy_name,
                session_name=session_name,
                market_condition=market_condition,
            )

            if isinstance(selected_signal_data, dict):
                selected_signal_data["tp_ladder"] = trade_plan.get("tp_ladder")
                selected_signal_data["tp_plan_summary"] = trade_plan.get("tp_plan_summary")
                selected_signal_data["original_take_profit"] = trade_plan.get("original_take_profit")
                selected_signal_data["tp_reference"] = trade_plan.get("take_profit")

            reason = trade_plan.get("reason", reason)

        except Exception as tp_ladder_exc:
            logger.warning(f"[PHASE 6E TP LADDER] main path failed | error={tp_ladder_exc}")

        trade_plan["setup_id"] = selected_signal_data.get("setup_id", "N/A")
        
        save_trade_plan_memory_report(
            selected_signal_data=selected_signal_data,
            strategy_name=strategy_name,
            signal=signal,
            score=score,
            session_name=session_name,
            market_condition=market_condition,
            reason=reason,
            trade_plan=trade_plan,
            decision="TRADE_PLAN_READY",
            decision_reason="trade plan calculated successfully before RR review",
        )

    if signal in ["BUY", "SELL"] and trade_plan is None:
        logger.info(
            f"[TRADE PLAN FAILED] "
            f"strategy={strategy_name} "
            f"signal={signal} "
            f"data_keys={list(selected_signal_data.keys())}"
        )
        
        save_trade_plan_memory_report(
            selected_signal_data=selected_signal_data,
            strategy_name=strategy_name,
            signal=signal,
            score=score,
            session_name=session_name,
            market_condition=market_condition,
            reason=reason,
            trade_plan=None,
            decision="TRADE_PLAN_FAILED",
            decision_reason="calculate_trade_plan returned None",
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

        min_rr_required = get_min_rr(
            strategy_name,
            selected_signal_data.get("entry_model"),
            selected_signal_data.get("sl_model"),
        )

        log_setup_event(
            setup_id=selected_signal_data.get("setup_id"),
            event="TRADE_PLAN_READY",
            strategy=strategy_name,
            signal=signal,
            entry_model=selected_signal_data.get("entry_model"),
            score=score,
            session=session_name,
            market_condition=market_condition,
            entry=trade_plan["entry_price"],
            sl=trade_plan["stop_loss"],
            tp=trade_plan["take_profit"],
            rr=rr_value,
            required_rr=min_rr_required,
            reason=reason,
        )
        
        save_trade_plan_memory_report(
            selected_signal_data=selected_signal_data,
            strategy_name=strategy_name,
            signal=signal,
            score=score,
            session_name=session_name,
            market_condition=market_condition,
            reason=reason,
            trade_plan=trade_plan,
            decision="RISK_REVIEW_READY",
            decision_reason="trade plan and RR review available",
            rr_value=rr_value,
            required_rr=min_rr_required,
        )
        
        structural_key = attach_structural_execution_key(
            setup=best_setup,
            signal_data=selected_signal_data,
            strategy_name=strategy_name,
            signal=signal,
        )

        structural_locked, locked_state, locked_setup_id = is_structural_execution_locked(
            structural_key,
            current_setup=best_setup,
        )

        if structural_locked:
            logger.info(
                f"[STRUCTURAL EXECUTION LOCK] Blocked duplicate setup | "
                f"setup_id={selected_signal_data.get('setup_id')} "
                f"strategy={strategy_name} signal={signal} "
                f"structural_key={structural_key} "
                f"locked_state={locked_state} locked_setup_id={locked_setup_id}"
            )

            if hasattr(execution_engine, "mark_execution_failed"):
                execution_engine.mark_execution_failed(
                    best_setup,
                    f"Duplicate structural setup locked by {locked_setup_id} state={locked_state}",
                )
            else:
                best_setup["state"] = "SKIPPED"
                best_setup["wait_reason"] = (
                    f"Duplicate structural setup locked by {locked_setup_id} state={locked_state}"
                )

            log_setup_event(
                setup_id=selected_signal_data.get("setup_id"),
                event="SETUP_STRUCTURAL_EXECUTION_LOCKED",
                strategy=strategy_name,
                signal=signal,
                entry_model=selected_signal_data.get("entry_model"),
                score=score,
                session=session_name,
                market_condition=market_condition,
                entry=trade_plan.get("entry_price") if trade_plan else None,
                sl=trade_plan.get("stop_loss") if trade_plan else None,
                tp=trade_plan.get("take_profit") if trade_plan else None,
                rr=rr_value,
                reason=f"duplicate structural setup locked by {locked_setup_id} state={locked_state}",
                extra={
                    "structural_execution_key": structural_key,
                    "locked_state": locked_state,
                    "locked_setup_id": locked_setup_id,
                },
            )

            return current_candle_time

        if not best_setup.get("trade_plan_notified"):
            if TELEGRAM_VERBOSE_SIGNALS and not best_setup.get("trade_plan_notified"):
                send_telegram_message(
                    f"📐 Trade Plan Ready #{selected_signal_data.get('setup_id', 'N/A')}\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Signal: {signal}\n"
                    f"Strategy: {strategy_name}\n\n"
                    f"Entry: {trade_plan['entry_price']}\n"
                    f"SL: {trade_plan['stop_loss']}\n"
                    f"TP1 / Execution TP: {trade_plan['take_profit']}\\n"
                    f"Original TP: {trade_plan.get('original_take_profit', trade_plan['take_profit'])}\\n"
                    f"TP Plan: {trade_plan.get('tp_plan_summary', 'standard')}\\n"
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

    if signal in ["BUY", "SELL"] and trade_plan is not None:
        save_trade_plan_memory_report(
            selected_signal_data=selected_signal_data,
            strategy_name=strategy_name,
            signal=signal,
            score=score,
            session_name=session_name,
            market_condition=market_condition,
            reason=reason,
            trade_plan=trade_plan,
            decision="RISK_REVIEW_RESULT",
            decision_reason=guard_reason if not trade_allowed else "trade guard passed",
            rr_value=rr_value,
            required_rr=min_rr_required,
        )

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
            # SCALP MODE FALLBACK
            # =========================
            scalp_trade_plan = None

            if low_rr_blocked and ENABLE_SCALP_MODE:
                scalp_trade_plan = try_build_scalp_trade_plan(
                    df=df,
                    tick=tick,
                    account_info=account_info,
                    signal=signal,
                    strategy_name=strategy_name,
                    selected_signal_data=selected_signal_data,
                    normal_trade_plan=trade_plan,
                )

            if scalp_trade_plan is not None:
                scalp_allowed, scalp_guard_reason = check_trade_guard(signal, tick)

                if scalp_allowed:
                    from src.position_guard import has_same_direction_position

                    opposite = "SELL" if signal == "BUY" else "BUY"

                    if has_same_direction_position(SYMBOL, opposite):
                        scalp_allowed = False
                        scalp_guard_reason = f"Opposite {opposite} position already exists."

                if not scalp_allowed:
                    logger.info(
                        f"[SCALP MODE] Blocked | "
                        f"strategy={strategy_name} reason={scalp_guard_reason}"
                    )

                else:
                    send_telegram_message(
                        f"⚡ Scalp Mode Executing\n"
                        f"Symbol: {SYMBOL}\n"
                        f"Strategy: {strategy_name}\n"
                        f"Signal: {signal}\n\n"
                        f"Entry: {scalp_trade_plan['entry_price']}\n"
                        f"SL: {scalp_trade_plan['stop_loss']}\n"
                        f"TP: {scalp_trade_plan['take_profit']}\n"
                        f"RR: {scalp_trade_plan.get('scalp_rr')}\n"
                        f"SL Model: {scalp_trade_plan['scalp_sl_model']}"
                    )

                    log_setup_event(
                        setup_id=selected_signal_data.get("setup_id"),
                        event="SCALP_EXECUTION_ATTEMPT",
                        strategy=strategy_name,
                        signal=signal,
                        entry_model=scalp_trade_plan.get("entry_model"),
                        score=score,
                        session=session_name,
                        market_condition=market_condition,
                        entry=scalp_trade_plan["entry_price"],
                        sl=scalp_trade_plan["stop_loss"],
                        tp=scalp_trade_plan["take_profit"],
                        reason=scalp_trade_plan.get("reason", "Scalp mode execution"),
                        extra={
                            "is_scalp": True,
                            "scalp_sl_model": scalp_trade_plan.get("scalp_sl_model"),
                            "scalp_stop_distance": scalp_trade_plan.get("scalp_stop_distance"),
                            "scalp_target_distance": scalp_trade_plan.get("scalp_target_distance"),
                        },
                    )

                    if is_trade_blocked_by_execution_memory(
                        trade_plan=scalp_trade_plan,
                        signal_data=selected_signal_data,
                        setup=best_setup if "best_setup" in locals() else None,
                        strategy_name=strategy_name,
                        signal=signal,
                    ):
                        save_execution_memory_report(
                            selected_signal_data=selected_signal_data,
                            strategy_name=strategy_name,
                            signal=signal,
                            score=score,
                            session_name=session_name,
                            market_condition=market_condition,
                            reason=scalp_trade_plan.get("reason", "scalp fallback skipped by execution memory"),
                            trade_plan=scalp_trade_plan,
                            decision="SCALP_BLOCKED_BY_MEMORY",
                            decision_reason="scalp fallback skipped by execution memory",
                            rr_value=None,
                            required_rr=None,
                            extra={
                                "is_scalp": True,
                                "original_setup_id": selected_signal_data.get("setup_id"),
                                "scalp_target_distance": scalp_trade_plan.get("scalp_target_distance"),
                            },
                        )

                        return current_candle_time
                    
                    save_execution_memory_report(
                        selected_signal_data=selected_signal_data,
                        strategy_name=strategy_name,
                        signal=signal,
                        score=score,
                        session_name=session_name,
                        market_condition=market_condition,
                        reason=scalp_trade_plan.get("reason", "scalp fallback execution attempt"),
                        trade_plan=scalp_trade_plan,
                        decision="SCALP_EXECUTION_ATTEMPT",
                        decision_reason="sending scalp fallback order to MT5",
                        rr_value=None,
                        required_rr=None,
                        extra={
                            "is_scalp": True,
                            "original_setup_id": selected_signal_data.get("setup_id"),
                            "scalp_target_distance": scalp_trade_plan.get("scalp_target_distance"),
                        },
                    )
                    
                    apply_strategy_advisory_note(
                        signal_data=selected_signal_data,
                        strategy_name=strategy_name,
                        setup_source_bucket="SCALP_FALLBACK",
                    )

                    observe_universal_confirmation_from_scope(
                        locals(),
                        setup_source_bucket_override="SCALP_FALLBACK",
                    )

                    execution_result = execute_trade(
                        signal,
                        scalp_trade_plan,
                        SYMBOL,
                    )

                    if execution_result:
                        if "best_setup" in locals():
                            save_execution_memory_report(
                                selected_signal_data=selected_signal_data,
                                strategy_name=strategy_name,
                                signal=signal,
                                score=score,
                                session_name=session_name,
                                market_condition=market_condition,
                                reason=scalp_trade_plan.get("reason", "scalp fallback execution success"),
                                trade_plan=scalp_trade_plan,
                                decision="SCALP_EXECUTION_SUCCESS",
                                decision_reason="scalp fallback MT5 order returned success",
                                rr_value=None,
                                required_rr=None,
                                execution_result=execution_result,
                                extra={
                                    "is_scalp": True,
                                    "original_setup_id": selected_signal_data.get("setup_id"),
                                    "scalp_target_distance": scalp_trade_plan.get("scalp_target_distance"),
                                },
                            )
                            
                            execution_engine.mark_executed(best_setup)
                        return current_candle_time
                    
                    save_execution_memory_report(
                        selected_signal_data=selected_signal_data,
                        strategy_name=strategy_name,
                        signal=signal,
                        score=score,
                        session_name=session_name,
                        market_condition=market_condition,
                        reason=scalp_trade_plan.get("reason", "scalp fallback execution failed"),
                        trade_plan=scalp_trade_plan,
                        decision="SCALP_EXECUTION_FAILED",
                        decision_reason="scalp fallback execute_trade returned False",
                        rr_value=None,
                        required_rr=None,
                        execution_result=execution_result,
                        extra={
                            "is_scalp": True,
                            "original_setup_id": selected_signal_data.get("setup_id"),
                            "scalp_target_distance": scalp_trade_plan.get("scalp_target_distance"),
                        },
                    )

                    if "best_setup" in locals() and hasattr(execution_engine, "mark_execution_failed"):
                        execution_engine.mark_execution_failed(
                            best_setup,
                            "Scalp execution failed",
                        )

                    send_telegram_message(
                        f"❌ Scalp Mode Execution Failed\n"
                        f"Symbol: {SYMBOL}\n"
                        f"Strategy: {strategy_name}\n"
                        f"Signal: {signal}"
                    )

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
                better_entry_expiry = (
                    BETTER_ENTRY_FAST_EXPIRY_MINUTES
                    if strategy_name in BETTER_ENTRY_FAST_EXPIRY_STRATEGIES
                    else BETTER_ENTRY_EXPIRY_MINUTES
                )

                execution_engine.mark_wait_better_entry(
                    setup=best_setup,
                    min_rr_required=min_rr_required,
                    current_rr=rr_value,
                    expiry_minutes=better_entry_expiry,
                )

                send_telegram_message(
                    f"⏳ Setup #{setup_id} Waiting for Better Entry\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Strategy: {strategy_name}\n"
                    f"Signal: {signal}\n\n"
                    f"Current RR: {rr_value}\n"
                    f"Required RR: {min_rr_required}\n"
                    f"Expiry: {better_entry_expiry} minutes"
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

                                if is_trade_blocked_by_execution_memory(
                                    trade_plan=reversal_trade_plan,
                                    signal_data=selected_signal_data,
                                    setup=best_setup if "best_setup" in locals() else None,
                                    strategy_name=reversal_trade_plan.get("strategy", strategy_name),
                                    signal=reversal_signal,
                                ):
                                    save_execution_memory_report(
                                        selected_signal_data=selected_signal_data,
                                        strategy_name=reversal_trade_plan.get("strategy", strategy_name),
                                        signal=reversal_signal,
                                        score=score,
                                        session_name=session_name,
                                        market_condition=market_condition,
                                        reason=reversal_data.get("reason", "reversal skipped by execution memory"),
                                        trade_plan=reversal_trade_plan,
                                        decision="REVERSAL_BLOCKED_BY_MEMORY",
                                        decision_reason="reversal execution skipped by execution memory",
                                        rr_value=reversal_rr,
                                        required_rr=None,
                                        extra={
                                            "original_setup_id": selected_signal_data.get("setup_id"),
                                            "original_signal": signal,
                                            "reversal_signal": reversal_signal,
                                            "reversal_reason": reversal_data.get("reason"),
                                        },
                                    )

                                    return current_candle_time
                                
                                save_execution_memory_report(
                                    selected_signal_data=selected_signal_data,
                                    strategy_name=reversal_trade_plan.get("strategy", strategy_name),
                                    signal=reversal_signal,
                                    score=score,
                                    session_name=session_name,
                                    market_condition=market_condition,
                                    reason=reversal_data.get("reason", "reversal execution attempt"),
                                    trade_plan=reversal_trade_plan,
                                    decision="REVERSAL_EXECUTION_ATTEMPT",
                                    decision_reason="sending reversal order to MT5",
                                    rr_value=reversal_rr,
                                    required_rr=None,
                                    extra={
                                        "original_setup_id": selected_signal_data.get("setup_id"),
                                        "original_signal": signal,
                                        "reversal_signal": reversal_signal,
                                        "reversal_reason": reversal_data.get("reason"),
                                    },
                                )
                                
                                apply_strategy_advisory_note(
                                    signal_data=selected_signal_data,
                                    strategy_name=reversal_trade_plan.get("strategy") or strategy_name,
                                    setup_source_bucket="REVERSAL",
                                )

                                observe_universal_confirmation_from_scope(
                                    locals(),
                                    setup_source_bucket_override="REVERSAL",
                                )

                                execution_result = execute_trade(
                                    reversal_signal,
                                    reversal_trade_plan,
                                    SYMBOL,
                                )

                                if not execution_result:
                                    save_execution_memory_report(
                                        selected_signal_data=selected_signal_data,
                                        strategy_name=reversal_trade_plan.get("strategy", strategy_name),
                                        signal=reversal_signal,
                                        score=score,
                                        session_name=session_name,
                                        market_condition=market_condition,
                                        reason=reversal_data.get("reason", "reversal execution failed"),
                                        trade_plan=reversal_trade_plan,
                                        decision="REVERSAL_EXECUTION_FAILED",
                                        decision_reason="reversal execute_trade returned False",
                                        rr_value=reversal_rr,
                                        required_rr=None,
                                        execution_result=execution_result,
                                        extra={
                                            "original_setup_id": selected_signal_data.get("setup_id"),
                                            "original_signal": signal,
                                            "reversal_signal": reversal_signal,
                                            "reversal_reason": reversal_data.get("reason"),
                                        },
                                    )
                                    
                                    if "best_setup" in locals() and hasattr(execution_engine, "mark_execution_failed"):
                                        execution_engine.mark_execution_failed(
                                            best_setup,
                                            "Reversal execution failed",
                                        )

                                    send_telegram_message(
                                        f"❌ Reversal Execution Failed\n"
                                        f"Symbol: {SYMBOL}\n"
                                        f"Signal: {reversal_signal}\n"
                                        f"Reason: execute_trade() returned False."
                                    )

                                    log_setup_event(
                                        setup_id=selected_signal_data.get("setup_id"),
                                        event="EXECUTION_FAILED",
                                        strategy=strategy_name,
                                        signal=signal,
                                        entry_model=selected_signal_data.get("entry_model"),
                                        score=score,
                                        session=session_name,
                                        market_condition=market_condition,
                                        entry=trade_plan["entry_price"],
                                        sl=trade_plan["stop_loss"],
                                        tp=trade_plan["take_profit"],
                                        reason="execute_trade returned False",
                                    )

                                return current_candle_time
                            
                            save_execution_memory_report(
                                    selected_signal_data=selected_signal_data,
                                    strategy_name=reversal_trade_plan.get("strategy", strategy_name),
                                    signal=reversal_signal,
                                    score=score,
                                    session_name=session_name,
                                    market_condition=market_condition,
                                    reason=reversal_data.get("reason", "reversal execution success"),
                                    trade_plan=reversal_trade_plan,
                                    decision="REVERSAL_EXECUTION_SUCCESS",
                                    decision_reason="reversal MT5 order returned success",
                                    rr_value=reversal_rr,
                                    required_rr=None,
                                    execution_result=execution_result,
                                    extra={
                                        "original_setup_id": selected_signal_data.get("setup_id"),
                                        "original_signal": signal,
                                        "reversal_signal": reversal_signal,
                                        "reversal_reason": reversal_data.get("reason"),
                                    },
                                )

            # =========================
            # FINAL BLOCKED MESSAGE
            # =========================
            log_setup_event(
                setup_id=setup_id,
                event="TRADE_BLOCKED",
                strategy=strategy_name,
                signal=signal,
                entry_model=selected_signal_data.get("entry_model"),
                score=score,
                session=session_name,
                market_condition=market_condition,
                entry=entry,
                sl=sl,
                tp=tp,
                rr=rr_value,
                required_rr=min_rr_required,
                reason=guard_reason,
                extra={
                    "reversal_summary": reversal_summary,
                },
            )

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

        # =========================
        # EXTRA ENTRY M5 CONFIRMATION
        # =========================
        same_direction_count = count_same_direction_positions(SYMBOL, signal)
        is_extra_entry = same_direction_count >= 1

        if is_extra_entry and REQUIRE_M5_CONFIRMATION_FOR_EXTRA:
            extra_confirmed, extra_confirm_reason = extra_entry_confirmation_ok(signal)

            if not extra_confirmed:
                logger.info(
                    f"[EXTRA CONFIRMATION] Extra entry skipped | "
                    f"strategy={strategy_name} signal={signal} reason={extra_confirm_reason}"
                )

                send_telegram_message(
                    f"🚫 Extra Entry Skipped\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Strategy: {strategy_name}\n"
                    f"Signal: {signal}\n\n"
                    f"Reason: {extra_confirm_reason}"
                )

                try:
                    from src.setup_conflict_memory import (
                        format_conflict_telegram_message,
                        record_setup_state_event,
                    )

                    setup_id_for_conflict = None
                    if isinstance(selected_signal_data, dict):
                        setup_id_for_conflict = selected_signal_data.get("setup_id")
                    if not setup_id_for_conflict and isinstance(trade_plan, dict):
                        setup_id_for_conflict = trade_plan.get("setup_id")

                    entry_for_conflict = None
                    sl_for_conflict = None
                    tp_for_conflict = None
                    rr_for_conflict = None

                    if isinstance(trade_plan, dict):
                        entry_for_conflict = (
                            trade_plan.get("entry_price")
                            or trade_plan.get("entry")
                            or trade_plan.get("planned_entry")
                        )
                        sl_for_conflict = (
                            trade_plan.get("stop_loss")
                            or trade_plan.get("sl")
                        )
                        tp_for_conflict = (
                            trade_plan.get("take_profit")
                            or trade_plan.get("tp")
                        )
                        rr_for_conflict = (
                            trade_plan.get("rr")
                            or trade_plan.get("risk_reward")
                            or trade_plan.get("rr_value")
                        )

                    if isinstance(selected_signal_data, dict):
                        entry_for_conflict = entry_for_conflict or selected_signal_data.get("entry") or selected_signal_data.get("entry_price")
                        sl_for_conflict = sl_for_conflict or selected_signal_data.get("sl") or selected_signal_data.get("stop_loss")
                        tp_for_conflict = tp_for_conflict or selected_signal_data.get("tp") or selected_signal_data.get("take_profit")
                        rr_for_conflict = rr_for_conflict or selected_signal_data.get("rr") or selected_signal_data.get("risk_reward") or selected_signal_data.get("rr_value")

                    extra_conflict_report = record_setup_state_event(
                        {
                            "symbol": SYMBOL,
                            "setup_id": setup_id_for_conflict,
                            "strategy": strategy_name,
                            "signal": signal,
                            "score": score if "score" in locals() else None,
                            "entry_model": selected_signal_data.get("entry_model") if isinstance(selected_signal_data, dict) else None,
                            "session": session_name if "session_name" in locals() else None,
                            "market_condition": market_condition if "market_condition" in locals() else None,
                            "entry": entry_for_conflict,
                            "sl": sl_for_conflict,
                            "tp": tp_for_conflict,
                            "rr": rr_for_conflict,
                            "state": (
                                "ENTRY_SKIPPED_WEAK_CONFIRMATION"
                                if extra_confirm_reason == "m5_body_too_small"
                                else "ENTRY_SKIPPED_EXTRA_CONFIRMATION"
                            ),
                            "entry_skip_reason": extra_confirm_reason,
                            "reason": extra_confirm_reason,
                            "created_at_epoch": getattr(tick, "time", None),
                        }
                    )

                    if (
                        extra_conflict_report
                        and extra_conflict_report.get("priority_conflict_review")
                        and not extra_conflict_report.get("duplicate_conflict")
                    ):
                        send_telegram_message_async(
                            format_conflict_telegram_message(extra_conflict_report)
                        )
                except Exception as phase5ah_exc:
                    logger.warning(
                        f"[PHASE 5AH] extra entry skip conflict memory failed | "
                        f"strategy={strategy_name} signal={signal} reason={extra_confirm_reason} "
                        f"error={phase5ah_exc}"
                    )

                if "best_setup" in locals():
                    best_setup["state"] = "SKIPPED"
                    best_setup["wait_reason"] = f"Extra skipped: {extra_confirm_reason}"

                return current_candle_time

        # =========================
        # OPPOSITE POSITION GUARD
        # =========================
        if (
            not ALLOW_OPPOSITE_DIRECTION_TRADES
            and has_same_direction_position(SYMBOL, opposite)
        ):
            logger.info("Opposite position exists → skipping execution")

            send_telegram_message(
                f"🚫 Execution Skipped\n"
                f"Symbol: {SYMBOL}\n"
                f"Signal: {signal}\n"
                f"Strategy: {strategy_name}\n\n"
                f"Reason: Opposite {opposite} position already exists."
            )

            if "best_setup" in locals():
                best_setup["state"] = "SKIPPED"
                best_setup["wait_reason"] = "Skipped because opposite position exists"
                
            save_execution_memory_report(
                selected_signal_data=selected_signal_data,
                strategy_name=strategy_name,
                signal=signal,
                score=score,
                session_name=session_name,
                market_condition=market_condition,
                reason=reason,
                trade_plan=trade_plan,
                decision="EXECUTION_SKIPPED_OPPOSITE_POSITION",
                decision_reason="opposite position exists",
                rr_value=rr_value,
                required_rr=min_rr_required,
            )

            return current_candle_time

        if (
            ENABLE_DELAYED_RETRACE_ENTRY
            and strategy_name in DELAYED_ENTRY_STRATEGIES
            and not trade_plan.get("is_scalp", False)
            and "best_setup" in locals()
        ):
            current_entry = trade_plan["entry_price"]

            delayed_offset = get_delayed_entry_offset(market_condition)

            if signal == "BUY":
                delayed_target = round(current_entry - delayed_offset, 2)
            else:
                delayed_target = round(current_entry + delayed_offset, 2)

            immediate_lot = trade_plan["lot"]
            delayed_lot = 0.0
            
            continuation_retrace_first = continuation_requires_retrace_first(
                strategy_name=strategy_name,
                entry_model=selected_signal_data.get("entry_model"),
                rr_value=rr_value,
            )
            
            if should_use_orb_tick_breakout_watcher(strategy_name, selected_signal_data):
                execution_engine.mark_wait_orb_tick_breakout(
                    setup=best_setup,
                    expiry_minutes=ORB_TICK_BREAKOUT_EXPIRY_MINUTES,
                    min_rr=ORB_TICK_BREAKOUT_MIN_RR,
                    min_distance=ORB_TICK_BREAKOUT_MIN_DISTANCE,
                )

                log_setup_event(
                    setup_id=selected_signal_data.get("setup_id"),
                    event="ORB_TICK_BREAKOUT_WATCHING",
                    strategy=strategy_name,
                    signal=signal,
                    entry_model=selected_signal_data.get("entry_model"),
                    score=score,
                    session=session_name,
                    market_condition=market_condition,
                    entry=trade_plan.get("entry_price"),
                    sl=trade_plan.get("stop_loss"),
                    tp=trade_plan.get("take_profit"),
                    rr=rr_value,
                    required_rr=ORB_TICK_BREAKOUT_MIN_RR,
                    reason="ORB tick breakout watcher registered",
                    extra={
                        "orb_high": selected_signal_data.get("orb_high"),
                        "orb_low": selected_signal_data.get("orb_low"),
                        "expiry_minutes": ORB_TICK_BREAKOUT_EXPIRY_MINUTES,
                        "min_distance": ORB_TICK_BREAKOUT_MIN_DISTANCE,
                    },
                )

                send_telegram_message(
                    f"⏳ ORB Tick Breakout Watcher Registered\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Strategy: {strategy_name}\n"
                    f"Signal: {signal}\n"
                    f"Setup ID: {selected_signal_data.get('setup_id')}\n\n"
                    f"ORB High: {selected_signal_data.get('orb_high')}\n"
                    f"ORB Low: {selected_signal_data.get('orb_low')}\n"
                    f"Min Distance: {ORB_TICK_BREAKOUT_MIN_DISTANCE}\n"
                    f"Expiry: {ORB_TICK_BREAKOUT_EXPIRY_MINUTES} minutes"
                )

                return current_candle_time
            
            if should_use_tick_sniper_watcher(strategy_name, selected_signal_data):
                reference_price = trade_plan.get("entry_price")
                
                if not selected_signal_data.get("session"):
                    selected_signal_data["session"] = session_name

                if not selected_signal_data.get("market_condition"):
                    selected_signal_data["market_condition"] = market_condition

                profile = get_tick_sniper_profile(strategy_name)
                
                execution_engine.mark_wait_tick_sniper(
                    setup=best_setup,
                    expiry_seconds=TICK_SNIPER_EXPIRY_SECONDS,
                    min_rr=profile["min_rr"],
                    min_score=profile["min_score"],
                    min_move_price=profile["min_move_price"],
                    reference_price=reference_price,
                )
                
                best_setup["tick_sniper_trigger"] = profile["trigger"]
                best_setup["tick_sniper_require_m5_confirmation"] = profile["require_m5_confirmation"]

                log_setup_event(
                    setup_id=selected_signal_data.get("setup_id"),
                    event="TICK_SNIPER_WATCHING",
                    strategy=strategy_name,
                    signal=signal,
                    entry_model=selected_signal_data.get("entry_model"),
                    score=score,
                    session=session_name,
                    market_condition=market_condition,
                    entry=trade_plan.get("entry_price"),
                    sl=trade_plan.get("stop_loss"),
                    tp=trade_plan.get("take_profit"),
                    rr=rr_value,
                    required_rr=TICK_SNIPER_MIN_RR,
                    reason="generic tick sniper watcher registered",
                    extra={
                        "reference_price": reference_price,
                        "expiry_seconds": TICK_SNIPER_EXPIRY_SECONDS,
                        "min_move_price": profile["min_move_price"],
                        "trigger": profile["trigger"],
                        "require_m5_confirmation": profile["require_m5_confirmation"],
                    },
                )

                save_execution_memory_report(
                    selected_signal_data=selected_signal_data,
                    strategy_name=strategy_name,
                    signal=signal,
                    score=score,
                    session_name=session_name,
                    market_condition=market_condition,
                    reason="generic tick sniper watcher registered",
                    trade_plan=trade_plan,
                    decision="TICK_SNIPER_WATCHING",
                    decision_reason="setup moved to generic tick sniper watcher",
                    rr_value=rr_value,
                    required_rr=TICK_SNIPER_MIN_RR,
                    extra={
                        "reference_price": reference_price,
                        "expiry_seconds": TICK_SNIPER_EXPIRY_SECONDS,
                        "min_move_price": TICK_SNIPER_MIN_MOVE_PRICE,
                    },
                )

                if TICK_SNIPER_NOTIFY_TELEGRAM:
                    send_telegram_message(
                        f"🎯 Tick Sniper Watcher Registered\n"
                        f"Symbol: {SYMBOL}\n"
                        f"Strategy: {strategy_name}\n"
                        f"Signal: {signal}\n"
                        f"Setup ID: {selected_signal_data.get('setup_id')}\n\n"
                        f"Reference: {reference_price}\n"
                        f"Min Move: {TICK_SNIPER_MIN_MOVE_PRICE}\n"
                        f"Expiry: {TICK_SNIPER_EXPIRY_SECONDS}s\n"
                        f"Required RR: {TICK_SNIPER_MIN_RR}"
                    )

                return current_candle_time

            if continuation_retrace_first:
                execution_engine.mark_wait_delayed_entry(
                    setup=best_setup,
                    target_entry_price=delayed_target,
                    expiry_minutes=DELAYED_ENTRY_EXPIRY_MINUTES,
                )

                log_setup_event(
                    setup_id=selected_signal_data.get("setup_id"),
                    event="CONTINUATION_RETRACE_FIRST",
                    strategy=strategy_name,
                    signal=signal,
                    entry_model=selected_signal_data.get("entry_model"),
                    score=score,
                    session=session_name,
                    market_condition=market_condition,
                    entry=trade_plan.get("entry_price"),
                    sl=trade_plan.get("stop_loss"),
                    tp=trade_plan.get("take_profit"),
                    rr=rr_value,
                    reason=(
                        f"Continuation safety: RR {rr_value} below "
                        f"{CONTINUATION_SAFETY_MIN_IMMEDIATE_RR}, waiting retrace first"
                    ),
                    extra={
                        "delayed_target": delayed_target,
                        "immediate_lot": 0.0,
                        "delayed_lot": trade_plan["lot"],
                    },
                )

                send_telegram_message(
                    f"⏳ Continuation Retrace-First Mode\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Strategy: {strategy_name}\n"
                    f"Signal: {signal}\n"
                    f"Setup ID: {selected_signal_data.get('setup_id')}\n\n"
                    f"RR: {rr_value} / Required Immediate: {CONTINUATION_SAFETY_MIN_IMMEDIATE_RR}\n"
                    f"Current Entry: {trade_plan['entry_price']}\n"
                    f"Waiting Target: {delayed_target}\n"
                    f"Lot Waiting: {trade_plan['lot']}"
                )

                return current_candle_time
            
            if should_use_fvg_zone_staged_entry(strategy_name, selected_signal_data):
                fvg_top, fvg_bottom = get_fvg_zone(selected_signal_data)

                staged_prices = build_fvg_staged_entry_prices(
                    signal=signal,
                    fvg_top=fvg_top,
                    fvg_bottom=fvg_bottom,
                )

                if staged_prices:
                    extra_sl_buffer = get_strategy_extra_sl_buffer(strategy_name)

                    if extra_sl_buffer <= 0:
                        extra_sl_buffer = FVG_ZONE_STAGED_ENTRY_SL_BUFFER

                    staged_trade_plan = dict(trade_plan)
                    staged_trade_plan["stop_loss"] = apply_extra_sl_buffer(
                        signal,
                        trade_plan.get("stop_loss"),
                        extra_sl_buffer,
                    )

                    stage_lot = round(float(trade_plan.get("lot", 0.0)), 2)

                    if stage_lot <= 0:
                        logger.info(
                            f"[FVG STAGED ENTRY] Skipped | invalid full stage lot "
                            f"lot={stage_lot} stages={len(staged_prices)}"
                        )
                        return current_candle_time
                    
                    total_planned_lot = round(stage_lot * len(staged_prices), 2)
                    
                    stages = []
                    
                    for index, target_entry in enumerate(staged_prices, start=1):
                        stages.append(
                            {
                                "stage_name": f"FVG_STAGE_{index}",
                                "target_entry": target_entry,
                                "lot": stage_lot,
                                "executed": False,
                            }
                        )

                    selected_signal_data["fvg_staged_trade_plan"] = staged_trade_plan

                    execution_engine.mark_wait_fvg_staged_entry(
                        setup=best_setup,
                        stages=stages,
                        expiry_minutes=FVG_ZONE_STAGED_ENTRY_EXPIRY_MINUTES,
                    )

                    log_setup_event(
                        setup_id=selected_signal_data.get("setup_id"),
                        event="FVG_STAGED_ENTRY_WAITING",
                        strategy=strategy_name,
                        signal=signal,
                        entry_model=selected_signal_data.get("entry_model"),
                        score=score,
                        session=session_name,
                        market_condition=market_condition,
                        entry=trade_plan.get("entry_price"),
                        sl=staged_trade_plan.get("stop_loss"),
                        tp=trade_plan.get("take_profit"),
                        rr=rr_value,
                        reason="FVG zone staged entry waiting",
                        extra={
                            "fvg_top": fvg_top,
                            "fvg_bottom": fvg_bottom,
                            "stages": stages,
                            "original_lot": stage_lot,
                            "stage_lot": stage_lot,
                            "total_planned_lot": total_planned_lot,
                            "lot_mode": "FULL_LOT_PER_STAGE",
                            "extra_sl_buffer": extra_sl_buffer,
                        },
                    )

                    send_telegram_message(
                        f"⏳ FVG Staged Entry Waiting\n"
                        f"Symbol: {SYMBOL}\n"
                        f"Strategy: {strategy_name}\n"
                        f"Signal: {signal}\n"
                        f"Setup ID: {selected_signal_data.get('setup_id')}\n\n"
                        f"FVG Zone: {round(fvg_bottom, 2)} - {round(fvg_top, 2)}\n"
                        f"Stages: {', '.join(str(item) for item in staged_prices)}\n"
                        f"Lot per Stage: {stage_lot}\n"
                        f"Total Planned Lot: {total_planned_lot}\n"
                        f"SL with Buffer: {staged_trade_plan.get('stop_loss')}\n"
                        f"TP: {trade_plan.get('take_profit')}"
                    )

                    return current_candle_time

            if ENABLE_SPLIT_DELAYED_ENTRY:
                immediate_lot, delayed_lot = split_lot_for_delayed_entry(
                    SYMBOL,
                    trade_plan["lot"],
                    SPLIT_DELAYED_ENTRY_IMMEDIATE_PCT,
                )

            # Execute first part now
            if ENABLE_SPLIT_DELAYED_ENTRY and delayed_lot > 0:
                immediate_trade_plan = trade_plan.copy()
                immediate_trade_plan["lot"] = immediate_lot
                immediate_trade_plan["reason"] = (
                    f"{trade_plan.get('reason', '')} | SPLIT_DELAYED_ENTRY immediate lot"
                )

                send_telegram_message(
                    f"🔥 Split Entry Executing Now\n"
                    f"Symbol: {SYMBOL}\n"
                    f"Strategy: {strategy_name}\n"
                    f"Signal: {signal}\n\n"
                    f"Immediate Lot: {immediate_lot}\n"
                    f"Delayed Lot: {delayed_lot}\n"
                    f"Current Entry: {current_entry}\n"
                    f"Delayed Target: {delayed_target}"
                )

                log_setup_event(
                    setup_id=selected_signal_data.get("setup_id"),
                    event="SPLIT_IMMEDIATE_EXECUTION_ATTEMPT",
                    strategy=strategy_name,
                    signal=signal,
                    entry_model=immediate_trade_plan.get("entry_model") or selected_signal_data.get("entry_model"),
                    score=score,
                    session=session_name,
                    market_condition=market_condition,
                    entry=immediate_trade_plan["entry_price"],
                    sl=immediate_trade_plan["stop_loss"],
                    tp=immediate_trade_plan["take_profit"],
                    reason=immediate_trade_plan.get("reason", "Split delayed entry immediate execution"),
                    extra={
                        "is_split_delayed_entry": True,
                        "split_part": "IMMEDIATE",
                        "immediate_lot": immediate_lot,
                        "delayed_lot": delayed_lot,
                        "delayed_target": delayed_target,
                    },
                )

                if is_trade_blocked_by_execution_memory(
                    trade_plan=immediate_trade_plan,
                    signal_data=selected_signal_data,
                    setup=best_setup,
                    strategy_name=strategy_name,
                    signal=signal,
                ):
                    save_execution_memory_report(
                        selected_signal_data=selected_signal_data,
                        strategy_name=strategy_name,
                        signal=signal,
                        score=score,
                        session_name=session_name,
                        market_condition=market_condition,
                        reason=immediate_trade_plan.get("reason", "split immediate skipped by execution memory"),
                        trade_plan=immediate_trade_plan,
                        decision="SPLIT_IMMEDIATE_BLOCKED_BY_MEMORY",
                        decision_reason="split immediate execution skipped by execution memory",
                        rr_value=rr_value,
                        required_rr=min_rr_required,
                        extra={
                            "is_split_delayed_entry": True,
                            "parent_setup_id": selected_signal_data.get("setup_id"),
                            "immediate_lot": immediate_lot,
                            "delayed_lot": delayed_lot,
                            "delayed_target": delayed_target,
                        },
                    )

                    return current_candle_time
                
                save_execution_memory_report(
                    selected_signal_data=selected_signal_data,
                    strategy_name=strategy_name,
                    signal=signal,
                    score=score,
                    session_name=session_name,
                    market_condition=market_condition,
                    reason=immediate_trade_plan.get("reason", "split immediate execution attempt"),
                    trade_plan=immediate_trade_plan,
                    decision="SPLIT_IMMEDIATE_EXECUTION_ATTEMPT",
                    decision_reason="sending split immediate order to MT5",
                    rr_value=rr_value,
                    required_rr=min_rr_required,
                    extra={
                        "is_split_delayed_entry": True,
                        "parent_setup_id": selected_signal_data.get("setup_id"),
                        "immediate_lot": immediate_lot,
                        "delayed_lot": delayed_lot,
                        "delayed_target": delayed_target,
                    },
                )
                
                apply_strategy_advisory_note(
                    signal_data=selected_signal_data,
                    strategy_name=strategy_name,
                    setup_source_bucket="SPLIT_IMMEDIATE",
                )

                observe_universal_confirmation_from_scope(
                    locals(),
                    setup_source_bucket_override="SPLIT_IMMEDIATE",
                )

                _live_execute_start_ts = time.perf_counter()
                logger.info(
                    f"[LIVE EXECUTION TIMING] stage=before_execute_trade "
                    f"symbol={SYMBOL} signal={signal} "
                    f"setup_id={immediate_trade_plan.get('setup_id') if isinstance(immediate_trade_plan, dict) else None} "
                    f"strategy={immediate_trade_plan.get('strategy') if isinstance(immediate_trade_plan, dict) else None}"
                )
                execution_result = execute_trade(signal, immediate_trade_plan, SYMBOL)
                logger.info(
                    f"[LIVE EXECUTION TIMING] stage=after_execute_trade "
                    f"elapsed_ms={round((time.perf_counter() - _live_execute_start_ts) * 1000, 2)} "
                    f"symbol={SYMBOL} signal={signal} result={execution_result}"
                )

                if not execution_result:
                    if immediate_trade_plan.get("execution_block_reason") == "LOW_RR_HIGH_ADVERSE_SLIPPAGE":
                        retry_signal_data = dict(selected_signal_data or {})
                        retry_signal_data["setup_id"] = selected_signal_data.get("setup_id")
                        retry_signal_data["strategy"] = strategy_name
                        retry_signal_data["signal"] = signal
                        retry_signal_data["entry_model"] = (
                            immediate_trade_plan.get("entry_model")
                            or selected_signal_data.get("entry_model")
                        )

                        retry_setup = register_execution_failure_retry_as_better_entry(
                            signal_data=retry_signal_data,
                            trade_plan=immediate_trade_plan,
                            source="LOW_RR_RECOVERY",
                            min_rr_required=min_rr_required,
                            current_rr=rr_value,
                            reason="LOW_RR_HIGH_ADVERSE_SLIPPAGE blocked immediate execution; waiting for better entry",
                            expiry_minutes=HIGH_SLIPPAGE_RETRY_EXPIRY_MINUTES,
                        )

                        save_execution_memory_report(
                            selected_signal_data=selected_signal_data,
                            strategy_name=strategy_name,
                            signal=signal,
                            score=score,
                            session_name=session_name,
                            market_condition=market_condition,
                            reason="low RR adverse slippage moved to better entry retry",
                            trade_plan=immediate_trade_plan,
                            decision="SPLIT_IMMEDIATE_LOW_RR_SLIPPAGE_WAIT_BETTER_ENTRY",
                            decision_reason="low RR adverse slippage blocked execution; setup moved to WAIT_BETTER_ENTRY retry",
                            rr_value=rr_value,
                            required_rr=min_rr_required,
                            execution_result=execution_result,
                            extra={
                                "is_split_delayed_entry": True,
                                "parent_setup_id": selected_signal_data.get("setup_id"),
                                "immediate_lot": immediate_lot,
                                "delayed_lot": delayed_lot,
                                "delayed_target": delayed_target,
                                "retry_registered": bool(retry_setup),
                                "execution_block_reason": immediate_trade_plan.get("execution_block_reason"),
                                "execution_block_adverse_slippage": immediate_trade_plan.get("execution_block_adverse_slippage"),
                                "execution_block_max_allowed": immediate_trade_plan.get("execution_block_max_allowed"),
                            },
                        )

                        if hasattr(execution_engine, "mark_execution_failed"):
                            execution_engine.mark_execution_failed(
                                best_setup,
                                "Moved to WAIT_BETTER_ENTRY after LOW_RR_HIGH_ADVERSE_SLIPPAGE",
                            )

                        log_setup_event(
                            setup_id=selected_signal_data.get("setup_id"),
                            event="SPLIT_IMMEDIATE_LOW_RR_SLIPPAGE_WAIT_BETTER_ENTRY",
                            strategy=strategy_name,
                            signal=signal,
                            entry_model=selected_signal_data.get("entry_model"),
                            score=score,
                            session=session_name,
                            market_condition=market_condition,
                            entry=immediate_trade_plan.get("entry_price"),
                            sl=immediate_trade_plan.get("stop_loss"),
                            tp=immediate_trade_plan.get("take_profit"),
                            rr=rr_value,
                            required_rr=min_rr_required,
                            reason="low RR adverse slippage blocked immediate execution; retry waiting for better entry",
                            extra={
                                "retry_registered": bool(retry_setup),
                                "execution_block_reason": immediate_trade_plan.get("execution_block_reason"),
                                "adverse_slippage": immediate_trade_plan.get("execution_block_adverse_slippage"),
                                "max_allowed": immediate_trade_plan.get("execution_block_max_allowed"),
                            },
                        )

                        send_telegram_message(
                            f"⏳ Low-RR Slippage Block → Better Entry Retry\n"
                            f"Symbol: {SYMBOL}\n"
                            f"Strategy: {strategy_name}\n"
                            f"Signal: {signal}\n"
                            f"Setup ID: {selected_signal_data.get('setup_id')}\n"
                            f"RR: {rr_value} / Required: {min_rr_required}\n"
                            f"Adverse Slippage: {immediate_trade_plan.get('execution_block_adverse_slippage')}\n"
                            f"Max Allowed: {immediate_trade_plan.get('execution_block_max_allowed')}\n"
                            f"Action: immediate entry skipped; waiting for better entry"
                        )

                        return current_candle_time

                    save_execution_memory_report(
                        selected_signal_data=selected_signal_data,
                        strategy_name=strategy_name,
                        signal=signal,
                        score=score,
                        session_name=session_name,
                        market_condition=market_condition,
                        reason=immediate_trade_plan.get("reason", "split immediate execution failed"),
                        trade_plan=immediate_trade_plan,
                        decision="SPLIT_IMMEDIATE_EXECUTION_FAILED",
                        decision_reason="split immediate execute_trade returned False",
                        rr_value=rr_value,
                        required_rr=min_rr_required,
                        execution_result=execution_result,
                        extra={
                            "is_split_delayed_entry": True,
                            "parent_setup_id": selected_signal_data.get("setup_id"),
                            "immediate_lot": immediate_lot,
                            "delayed_lot": delayed_lot,
                            "delayed_target": delayed_target,
                        },
                    )
                                        
                    if hasattr(execution_engine, "mark_execution_failed"):
                        execution_engine.mark_execution_failed(
                            best_setup,
                            "Split immediate execution failed",
                        )
                
                    log_setup_event(
                        setup_id=selected_signal_data.get("setup_id"),
                        event="EXECUTION_FAILED",
                        strategy=strategy_name,
                        signal=signal,
                        entry_model=selected_signal_data.get("entry_model"),
                        score=score,
                        session=session_name,
                        market_condition=market_condition,
                        entry=immediate_trade_plan.get("entry_price"),
                        sl=immediate_trade_plan.get("stop_loss"),
                        tp=immediate_trade_plan.get("take_profit"),
                        reason="Split immediate execution failed",
                    )
                
                    send_telegram_message(
                        f"❌ Split Entry Immediate Execution Failed\n"
                        f"Symbol: {SYMBOL}\n"
                        f"Strategy: {strategy_name}\n"
                        f"Signal: {signal}\n"
                        f"Setup ID: {selected_signal_data.get('setup_id')}\n"
                        f"Action: setup marked EXECUTION_FAILED"
                    )
                
                    return current_candle_time
                
                save_execution_memory_report(
                    selected_signal_data=selected_signal_data,
                    strategy_name=strategy_name,
                    signal=signal,
                    score=score,
                    session_name=session_name,
                    market_condition=market_condition,
                    reason=immediate_trade_plan.get("reason", "split immediate execution success"),
                    trade_plan=immediate_trade_plan,
                    decision="SPLIT_IMMEDIATE_EXECUTION_SUCCESS",
                    decision_reason="split immediate MT5 order returned success, delayed part scheduled",
                    rr_value=rr_value,
                    required_rr=min_rr_required,
                    execution_result=execution_result,
                    extra={
                        "is_split_delayed_entry": True,
                        "parent_setup_id": selected_signal_data.get("setup_id"),
                        "immediate_lot": immediate_lot,
                        "delayed_lot": delayed_lot,
                        "delayed_target": delayed_target,
                    },
                )

            execution_engine.mark_wait_delayed_entry(
                setup=best_setup,
                target_entry_price=delayed_target,
                expiry_minutes=DELAYED_ENTRY_EXPIRY_MINUTES,
            )

            best_setup["delayed_entry_lot"] = delayed_lot if delayed_lot > 0 else trade_plan["lot"]

            send_telegram_message(
                f"⏳ Setup #{selected_signal_data.get('setup_id', 'N/A')} Waiting for Delayed Entry\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n\n"
                f"Current Entry: {current_entry}\n"
                f"Target Delayed Entry: {delayed_target}\n"
                f"Immediate Lot Executed: {immediate_lot if delayed_lot > 0 else 0.0}\n"
                f"Remaining Lot Waiting: {best_setup.get('delayed_entry_lot')}\n"
                f"Offset: {delayed_offset}\n"
                f"Market Condition: {market_condition}\n"
                f"Expiry: {DELAYED_ENTRY_EXPIRY_MINUTES} minutes"
            )

            return current_candle_time

        # M5 confirmation for immediate execution only
        m5_confirmed, m5_confirm_reason = m5_execution_confirmation_ok(
            signal,
            strategy_name,
        )

        if not m5_confirmed:
            logger.info(
                f"[M5 EXECUTION CONFIRMATION] Execution skipped | "
                f"strategy={strategy_name} signal={signal} reason={m5_confirm_reason}"
            )

            send_telegram_message(
                f"🚫 Execution Skipped by M5 Confirmation\n"
                f"Symbol: {SYMBOL}\n"
                f"Strategy: {strategy_name}\n"
                f"Signal: {signal}\n\n"
                f"Reason: {m5_confirm_reason}"
            )

            if "best_setup" in locals():
                best_setup["state"] = "WAITING"
                best_setup["wait_reason"] = f"M5 execution confirmation pending: {m5_confirm_reason}"

            return current_candle_time

        confirmation_report = observe_universal_confirmation_for_setup(
            selected_signal_data=selected_signal_data,
            trade_plan=trade_plan,
            df=df,
            tick=tick,
            session_name=session_name,
            market_condition=market_condition,
            min_rr_required=min_rr_required if "min_rr_required" in locals() else None,
            max_spread=MAX_SPREAD,
        )

        logger.info("🔥 Executing trade...")

        log_setup_event(
            setup_id=selected_signal_data.get("setup_id"),
            event="EXECUTION_ATTEMPT",
            strategy=strategy_name,
            signal=signal,
            entry_model=trade_plan.get("entry_model") or selected_signal_data.get("entry_model"),
            score=score,
            session=session_name,
            market_condition=market_condition,
            entry=trade_plan["entry_price"],
            sl=trade_plan["stop_loss"],
            tp=trade_plan["take_profit"],
            reason="Sending order to MT5",
            extra={
                "is_scalp": trade_plan.get("is_scalp", False),
                "scalp_sl_model": trade_plan.get("scalp_sl_model"),
                "scalp_stop_distance": trade_plan.get("scalp_stop_distance"),
                "scalp_target_distance": trade_plan.get("scalp_target_distance"),
            },
        )

        if is_trade_blocked_by_execution_memory(
            trade_plan=trade_plan,
            signal_data=selected_signal_data,
            setup=best_setup,
            strategy_name=strategy_name,
            signal=signal,
        ):
            save_execution_memory_report(
                selected_signal_data=selected_signal_data,
                strategy_name=strategy_name,
                signal=signal,
                score=score,
                session_name=session_name,
                market_condition=market_condition,
                reason=reason,
                trade_plan=trade_plan,
                decision="EXECUTION_BLOCKED_BY_MEMORY",
                decision_reason="execution memory blocked this setup",
                rr_value=rr_value,
                required_rr=min_rr_required,
            )

            return current_candle_time
        
        save_execution_memory_report(
            selected_signal_data=selected_signal_data,
            strategy_name=strategy_name,
            signal=signal,
            score=score,
            session_name=session_name,
            market_condition=market_condition,
            reason=reason,
            trade_plan=trade_plan,
            decision="EXECUTION_ATTEMPT",
            decision_reason="sending normal order to MT5",
            rr_value=rr_value,
            required_rr=min_rr_required,
        )
        
        apply_strategy_advisory_note(
            signal_data=selected_signal_data,
            strategy_name=strategy_name,
            setup_source_bucket="NORMAL_OR_TRACKED",
        )

        _live_execute_start_ts = time.perf_counter()
        logger.info(
            f"[LIVE EXECUTION TIMING] stage=before_execute_trade "
            f"symbol={SYMBOL} signal={signal} "
            f"setup_id={trade_plan.get('setup_id') if isinstance(trade_plan, dict) else None} "
            f"strategy={trade_plan.get('strategy') if isinstance(trade_plan, dict) else None}"
        )
        execution_result = execute_trade(signal, trade_plan, SYMBOL)
        logger.info(
            f"[LIVE EXECUTION TIMING] stage=after_execute_trade "
            f"elapsed_ms={round((time.perf_counter() - _live_execute_start_ts) * 1000, 2)} "
            f"symbol={SYMBOL} signal={signal} result={execution_result}"
        )

        if execution_result:
            save_execution_memory_report(
                selected_signal_data=selected_signal_data,
                strategy_name=strategy_name,
                signal=signal,
                score=score,
                session_name=session_name,
                market_condition=market_condition,
                reason=reason,
                trade_plan=trade_plan,
                decision="EXECUTION_SUCCESS",
                decision_reason="normal MT5 order execution returned success",
                rr_value=rr_value,
                required_rr=min_rr_required,
                execution_result=execution_result,
            )

            execution_engine.mark_executed(best_setup)
        else:
            save_execution_memory_report(
                selected_signal_data=selected_signal_data,
                strategy_name=strategy_name,
                signal=signal,
                score=score,
                session_name=session_name,
                market_condition=market_condition,
                reason=reason,
                trade_plan=trade_plan,
                decision="EXECUTION_FAILED",
                decision_reason="normal execute_trade returned False",
                rr_value=rr_value,
                required_rr=min_rr_required,
                execution_result=execution_result,
            )
            if hasattr(execution_engine, "mark_execution_failed"):
                execution_engine.mark_execution_failed(
                    best_setup,
                    "Normal execution failed",
                )
            else:
                best_setup["state"] = "EXECUTION_FAILED"
                best_setup["wait_reason"] = "Normal execution failed"

            log_setup_event(
                setup_id=selected_signal_data.get("setup_id"),
                event="EXECUTION_FAILED",
                strategy=strategy_name,
                signal=signal,
                entry_model=selected_signal_data.get("entry_model"),
                score=score,
                session=session_name,
                market_condition=market_condition,
                entry=trade_plan.get("entry_price"),
                sl=trade_plan.get("stop_loss"),
                tp=trade_plan.get("take_profit"),
                reason="Normal execution failed",
            )

            logger.error(
                f"[EXECUTION FAILED] "
                f"strategy={strategy_name} signal={signal} trade_plan={trade_plan}"
            )

            send_telegram_message(
                f"❌ Execution Failed\n"
                f"Symbol: {SYMBOL}\n"
                f"Signal: {signal}\n"
                f"Strategy: {strategy_name}\n"
                f"Setup ID: {selected_signal_data.get('setup_id')}\n\n"
                f"Reason: execute_trade() returned False. Setup marked EXECUTION_FAILED."
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
