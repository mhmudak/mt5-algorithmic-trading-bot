import os
import MetaTrader5 as mt5
from dotenv import load_dotenv

load_dotenv()

# =========================
# Google Sheets Logging
# =========================
ENABLE_GOOGLE_SHEETS_LOGGING = True
GOOGLE_SHEETS_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxkbNRMwx3uTquhpaKdypk2T3uPxEkR3zbwsXAJEXa6Yq_kdlAt_ETJueAxfLOUsD7nZw/exec"
GOOGLE_SHEETS_WEBHOOK_SECRET = "MyBot2k26MhMud"

# =========================
# Strategy Debugging
# =========================
ENABLE_STRATEGY_REJECTION_DEBUG = True

# =========================
# Telegram Signal Messages
# =========================
TELEGRAM_VERBOSE_SIGNALS = False

# =========================
# Market / Data Settings
# =========================
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M15
BARS_TO_FETCH = 100

# =========================
# Strategy Settings
# =========================
EMA_PERIOD = 20
ATR_PERIOD = 14
ATR_MIN = 2.0
ATR_MAX = 40.0
BREAKOUT_LOOKBACK = 10
BREAKOUT_BUFFER = 0.20

# =========================
# Fractal Sweep Strategy Settings
# =========================
FRACTAL_LOOKBACK = 40

FRACTAL_SWEEP_DISTANCE_MIN = 4.0    # $4
FRACTAL_SWEEP_DISTANCE_MAX = 5.5    # $5 with slight flexibility

FRACTAL_SL_DISTANCE = 5.0           # $5 stop loss
FRACTAL_TP_DISTANCE = 10.0          # $10 target
FRACTAL_TP_EXTENDED_DISTANCE = 15.0 # $15 optional extended target

# =========================
# News Volatility Filter
# =========================
ENABLE_NEWS_FILTER = True

NEWS_BLOCK_BEFORE_MINUTES = 15
NEWS_BLOCK_AFTER_MINUTES = 15

# Manual high-impact news blackout windows.
# Format: "YYYY-MM-DD HH:MM"
NEWS_BLACKOUT_WINDOWS = [
    # {"name": "High Impact News", "time": "2026-05-12 15:30"},
]

# =========================
# Trading Time Blackout
# =========================
ENABLE_TRADING_TIME_BLACKOUT = True

TRADING_BLACKOUT_WINDOWS = [
    {
        "name": "Low liquidity / high slippage window",
        "start": "03:00",
        "end": "04:00",
    },
]

# =========================
# Automatic Economic Calendar Filter
# =========================
ENABLE_AUTO_NEWS_FILTER = True
ECONOMIC_CALENDAR_PROVIDER = "FOREX_FACTORY"

# Forex Factory weekly XML calendar.
FOREX_FACTORY_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

# If the calendar time is not aligned with your local bot time,
# adjust this offset after testing.
# Example: if event appears 1 hour early, set +1.
FOREX_FACTORY_TIME_OFFSET_HOURS = 3

AUTO_NEWS_CURRENCIES = ["USD", "JPY"]
AUTO_NEWS_IMPACT = ["High"]

AUTO_NEWS_KEYWORDS = [
    "CPI",
    "Core CPI",
    "PPI",
    "Core PPI",
    "Non-Farm Employment Change",
    "Nonfarm Payrolls",
    "NFP",
    "Unemployment Rate",
    "Average Hourly Earnings",
    "FOMC",
    "Federal Funds Rate",
    "FOMC Statement",
    "FOMC Press Conference",
    "FOMC Meeting Minutes",
    "Powell",
    "Fed Chair",
    "Core PCE",
    "PCE Price Index",
    "GDP",
    "Advance GDP",
    "Retail Sales",
    "ISM Manufacturing PMI",
    "ISM Services PMI",
    "JOLTS",
    "ADP",
    "Unemployment Claims",
    "Jobless Claims",
]

# =========================
# Execution / Risk Settings
# =========================
POSITION_MODE = "fixed"   # "fixed" or "risk"
FIXED_LOT = 0.06
RISK_PER_TRADE_PCT = 0.25

# =========================
# Stop / TP Settings
# =========================
STOP_BUFFER = 32
USE_STRUCTURE_STOP = True
STOP_LOSS_ATR_MULTIPLIER = 1.5
TAKE_PROFIT_R_MULTIPLIER = 1.5

# =========================
# Trading Limits
# =========================
MAX_TRADES_PER_DAY = 500
# MAX_ALLOWED_SPREAD = 0.50
MAX_SPREAD = 0.5
MAX_SLIPPAGE = 0.3
COOLDOWN_MINUTES = 1

# =========================
# Execution Price Drift Guard
# =========================
ENABLE_PRICE_DRIFT_GUARD = True
MAX_ENTRY_PRICE_DRIFT = 0.66

# =========================
# Cooldown After SL Hit
# =========================
ENABLE_COOLDOWN_AFTER_SL = True
COOLDOWN_AFTER_SL_MINUTES = 5

# =========================
# Same Direction Entries
# =========================
ALLOW_SAME_DIRECTION_ENTRIES = True
MAX_SAME_DIRECTION_TRADES = 3  # main + extras = total max open same-side trades

# =========================
# Runtime / Safety
# =========================
EXECUTION_MODE = "LIVE"  # SIMULATION or LIVE
ALLOW_LIVE_TRADING = True
ENABLE_TELEGRAM_ALERTS = False
FORCE_SIGNAL = None  # "BUY", "SELL", or "None" or BOTH

# =========================
# Telegram
# =========================
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "False").lower() == "true"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# =========================
# Main Trade Staged Management (PRICE UNITS)
# =========================
ENABLE_MAIN_STAGE_MANAGEMENT = True

MAIN_STAGE_1_TRIGGER_PRICE = 6.0
MAIN_STAGE_1_CLOSE_PCT = 0.25

MAIN_EARLY_LOCK_TRIGGER_PRICE = 12.0
MAIN_EARLY_LOCK_PRICE = 2.5

MAIN_STAGE_2_TRIGGER_PRICE = 15.0
MAIN_STAGE_2_CLOSE_PCT = 0.25
MAIN_STAGE_2_LOCK_PRICE = 12.0

MAIN_STAGE_3_TRIGGER_PRICE = 24.5
MAIN_STAGE_3_CLOSE_PCT = 0.25
MAIN_STAGE_3_LOCK_PRICE = 16.0

# =========================
# Main Runner Management
# =========================
ENABLE_MAIN_RUNNER_MODE = True
MAIN_RUNNER_REMAINING_PCT = 0.25
MAIN_RUNNER_START_STAGE = 2
MAIN_RUNNER_REMOVE_TP = True
MAIN_RUNNER_EMERGENCY_TP_PRICE = 47.0

# =========================
# Extra Entries Management (PRICE UNITS)
# =========================
ENABLE_EXTRA_ENTRY_MANAGEMENT = True

EXTRA_ENTRY_BREAK_EVEN_TRIGGER_PRICE = 3.0
EXTRA_ENTRY_LOCK_TRIGGER_PRICE = 4.0
EXTRA_ENTRY_LOCK_PRICE = 2.0
EXTRA_ENTRY_TAKE_PROFIT_PRICE = 5.5

# =========================
# Extra Entry RR Discount
# =========================
ENABLE_EXTRA_RR_DISCOUNT = True
EXTRA_RR_MULTIPLIER = 0.75

# =========================
# Worst Extra Profit Lock (PRICE UNITS)
# =========================
ENABLE_WORST_EXTRA_LOCK = True
WORST_EXTRA_LOCK_TRIGGER_PRICE = 2.0
WORST_EXTRA_LOCK_PROFIT_PRICE = 1.0

# Only allow extras if main is protected/profitable
REQUIRE_MAIN_PROTECTED_FOR_EXTRA = True
MIN_MAIN_PROFIT_FOR_EXTRA_PRICE = 2.0

# =========================
# Dynamic Main / Extra Role Management
# =========================
ENABLE_DYNAMIC_MAIN_PROMOTION = True

PROMOTE_EXTRA_TO_MAIN_IF_BETTER_ENTRY = True
MAIN_PROMOTION_MIN_ENTRY_IMPROVEMENT_PRICE = 2.0

REQUIRE_PROMOTED_MAIN_BETTER_RR = True
MIN_PROMOTED_MAIN_SCORE = 90

EXTRA_FIXED_TP_PRICE = 5.5

REQUIRE_MAIN_PROTECTED_FOR_EXTRA = False

# =========================
# Extra Entry Confirmation
# =========================
REQUIRE_M5_CONFIRMATION_FOR_EXTRA = True
EXTRA_ENTRY_CONFIRMATION_TIMEFRAME = mt5.TIMEFRAME_M5
EXTRA_ENTRY_CONFIRMATION_BARS = 80
EXTRA_ENTRY_MIN_BODY_ATR = 0.10

# =========================
# Manual Trades Aggressive Trailing
# =========================
ENABLE_MANUAL_TRAILING = False
MANUAL_TRAILING_START_PRICE = 0.35
MANUAL_TRAILING_DISTANCE_PRICE = 0.2

# =========================
# Global Risk Kill Switch
# =========================
ENABLE_GLOBAL_DRAWDOWN_STOP = False
MAX_DRAWDOWN_USD = 100.0



# =========================
# Strategy Mode
# =========================
TRADING_MODE = "DUAL"  
# "NORMAL" = use strategy
# "BUY_ONLY"
# "SELL_ONLY"
# "DUAL" = both directions allowed (safe)


# =========================
# Reversal Mode
# =========================
ENABLE_REVERSAL_MODE = False
REVERSAL_CONFIRMATION_CANDLES = 2
ENABLE_REVERSAL_ALERTS = True
REVERSAL_MIN_SCORE = 50


# =========================
# Smart Structure TP/SL
# =========================
USE_STRUCTURE_TAKE_PROFIT = True

STOP_EXTRA_BUFFER_PRICE = 5.0   # move SL farther behind structure
TP_EARLY_BUFFER_PRICE = 5.0     # take profit earlier before structure target

# =========================
# Sniper v2 Filters
# =========================
ENABLE_SNIPER_V2 = True

# Liquidity sweep / fake-breakout filters
MIN_BREAKOUT_BODY_ATR = 0.35
MAX_BREAKOUT_WICK_BODY_RATIO = 2.0

# Volatility spike filter
ENABLE_VOLATILITY_SPIKE_FILTER = True
MAX_ATR_SPIKE_MULTIPLIER = 1.8

# Session filter
ENABLE_SESSION_FILTER = False
SESSION_START_HOUR = 9
SESSION_END_HOUR = 18


# =========================
# Strategy Auto Control
# =========================
ENABLE_STRATEGY_AUTO_DISABLE = False

MIN_TRADES_TO_EVALUATE = 5
MIN_WINRATE_PERCENT = 45.0

DISABLE_FAST = False
DISABLE_SNIPER_V2 = False
DISABLE_STRICT = False

# =========================
# ATR Adaptive TP Buffer
# =========================
ENABLE_ATR_ADAPTIVE_TP = True
TP_ATR_BUFFER_MULTIPLIER = 0.40
MIN_TP_BUFFER_PRICE = 3.0
MAX_TP_BUFFER_PRICE = 8.0


# =========================
# Adaptive Strategy Thresholds
# =========================
ENABLE_ADAPTIVE_THRESHOLDS = True

ADAPTIVE_MIN_TRADES = 10
ADAPTIVE_WINRATE_HIGH = 60.0
ADAPTIVE_WINRATE_LOW = 40.0
ADAPTIVE_SCORE_STEP = 3

FAST_BASE_MIN_SCORE = 85
SNIPER_V2_BASE_MIN_SCORE = 88
FLAG_BASE_MIN_SCORE = 88
FLAG_REFINED_BASE_MIN_SCORE = 90
LIQUIDITY_SWEEP_BASE_MIN_SCORE = 90
FVG_BASE_MIN_SCORE = 90
LIQUIDITY_CANDLE_BASE_MIN_SCORE = 90
TRIANGLE_PENNANT_BASE_MIN_SCORE = 90
ORDER_BLOCK_BASE_MIN_SCORE = 90
STRICT_BASE_MIN_SCORE = 90
HEAD_SHOULDERS_BASE_MIN_SCORE = 90
ORB_BASE_MIN_SCORE = 90
FRACTAL_SWEEP_BASE_MIN_SCORE = 90
VWAP_RECLAIM_BASE_MIN_SCORE = 90

SMT_BASE_MIN_SCORE = 91
RELIEF_RALLY_BASE_MIN_SCORE = 92
HTF_TREND_PULLBACK_BASE_MIN_SCORE = 92
SESSION_ORB_RETEST_BASE_MIN_SCORE = 92
STRUCTURE_LIQUIDITY_BASE_MIN_SCORE = 92
LVN_FVG_RECLAIM_BASE_MIN_SCORE = 92
AMD_FVG_BASE_MIN_SCORE = 92
FVG_CE_MITIGATION_BASE_MIN_SCORE = 92

CRT_TBS_BASE_MIN_SCORE = 93
BREAKER_BLOCK_BASE_MIN_SCORE = 93
FCR_M1_FVG_BASE_MIN_SCORE = 93
LIQUIDITY_POOL_OB_BASE_MIN_SCORE = 93

LIQUIDITY_TRAP_BASE_MIN_SCORE = 94
MTF_OB_ENTRY_BASE_MIN_SCORE = 94
SMT_PRO_BASE_MIN_SCORE = 95
OB_FVG_COMBO_BASE_MIN_SCORE = 96


LIQUIDITY_CANDLE_R_MULTIPLIER = 2.0

# =========================
# Multi-Timeframe Confirmation
# =========================
ENABLE_MTF_CONFIRMATION = True
MTF_TIMEFRAME = mt5.TIMEFRAME_H1
MTF_BARS_TO_FETCH = 120


# =========================
# Market Condition Modifiers
# =========================
ENABLE_MARKET_ADAPTATION = True

MARKET_THRESHOLD_MODIFIERS = {
    "TRENDING": -2,
    "PULLBACK_TREND": 0,
    "RANGING": +2,
    "VOLATILE": +3,
}

# =========================
# External SMT Confirmation
# =========================
ENABLE_EXTERNAL_SMT = True
SMT_CONFIRMATION_SYMBOL = "XAGUSD"
SMT_LOOKBACK_BARS = 20

# =========================
# External Macro Confirmation
# =========================
ENABLE_EXTERNAL_MACRO_CONFIRMATION = True

# Use your broker's exact symbols.
# If a symbol does not exist on your broker, the engine will skip it safely.
EXTERNAL_MACRO_CONFIRMATIONS = [
    {
        "symbol": "DXY",
        "mode": "INVERSE",
        "weight": 2,
    },
    {
        "symbol": "USDJPY",
        "mode": "INVERSE",
        "weight": 1,
    },
]

# =========================
# SMC Engine
# =========================
ENABLE_SMC_ENGINE = True
SMC_MIN_FINAL_SCORE = 88

# =========================
# Strategy Toggles
# =========================
ENABLE_FCR_M1_FVG = True # may turn it off

# =========================
# Session Engine
# =========================
ENABLE_SESSION_ENGINE = True

SESSION_ASIA_START = 0
SESSION_ASIA_END = 7

SESSION_LONDON_START = 7
SESSION_LONDON_END = 13

SESSION_NEWYORK_START = 13
SESSION_NEWYORK_END = 21


# =========================
# WaveTrend Pivot M5 Strategy
# =========================
ENABLE_WAVETREND_PIVOT_M5 = True # may turn it off
WAVETREND_PIVOT_TIMEFRAME = mt5.TIMEFRAME_M5
WAVETREND_PIVOT_BARS = 600

WT_CHANNEL_LENGTH = 10
WT_AVERAGE_LENGTH = 21

PIVOT_PROXIMITY_BUFFER = 1.5
PIVOT_BREAK_BUFFER = 0.8

WAVETREND_OVERBOUGHT = 53
WAVETREND_OVERSOLD = -53

WAVETREND_PIVOT_BASE_MIN_SCORE = 90

# =========================
# Structure / Liquidity Confirmation Layer
# =========================
ENABLE_STRUCTURE_LIQUIDITY = True
STRUCTURE_LIQUIDITY_BASE_MIN_SCORE = 92

ENABLE_STRUCTURE_LIQUIDITY_CONFIRMATION = True
STRUCTURE_LIQUIDITY_CONFIRMATION_BOOST = 3
STRUCTURE_LIQUIDITY_CONFLICT_PENALTY = 2

# =========================
# Blocked Setup Reversal
# =========================
ENABLE_BLOCKED_SETUP_REVERSAL = True
BLOCKED_REVERSAL_MIN_SCORE = 94
BLOCKED_REVERSAL_MIN_RR = 1.3

# LVN + FVG
ENABLE_LVN_FVG_RECLAIM = True
LVN_FVG_RECLAIM_BASE_MIN_SCORE = 92

# AMD + FVG
ENABLE_AMD_FVG = True
AMD_FVG_BASE_MIN_SCORE = 92

# FVG CE MITIGATION
ENABLE_FVG_CE_MITIGATION = True
FVG_CE_MITIGATION_BASE_MIN_SCORE = 92

# LIQUIDITY POOL OB
ENABLE_LIQUIDITY_POOL_OB = True
LIQUIDITY_POOL_OB_BASE_MIN_SCORE = 93

# =========================
# Candidate / Confluence Selection
# =========================
ENABLE_SIGNAL_CONFLUENCE_GROUPING = True
CONFLUENCE_SCORE_BOOST_PER_STRATEGY = 2
MAX_CONFLUENCE_SCORE_BOOST = 6

# =========================
# Candidate Selection / Fallback
# =========================
ENABLE_CANDIDATE_FALLBACK = True
MAX_CANDIDATES_PER_CANDLE = 3

# =========================
# Multi-Strategy Extra Entries
# =========================
ENABLE_MULTI_STRATEGY_EXTRAS = True
MAX_NEW_TRADES_PER_CANDLE = 2
MIN_EXTRA_CANDIDATE_SCORE = 94
ALLOW_ONLY_SAME_DIRECTION_EXTRAS = True

# FAILED_BREAKOUT_REVERSAL
ENABLE_FAILED_BREAKOUT_REVERSAL = True
FAILED_BREAKOUT_REVERSAL_BASE_MIN_SCORE = 92

# =========================
# Wait For Better Entry
# =========================
ENABLE_WAIT_FOR_BETTER_ENTRY = True
BETTER_ENTRY_EXPIRY_MINUTES = 15

BETTER_ENTRY_STRATEGIES = [
    "FVG_CE_MITIGATION",
    "ORDER_BLOCK",
    "BREAKER_BLOCK",
    "FVG",
    "OB_FVG_COMBO",
    "HTF_TREND_PULLBACK",
    "RELIEF_RALLY",
    "FAILED_FVG_REVERSAL",
]

# Fast reversal setups should not wait too long
BETTER_ENTRY_FAST_EXPIRY_MINUTES = 3

BETTER_ENTRY_FAST_EXPIRY_STRATEGIES = [
    "FAILED_FVG_REVERSAL",
    "FAILED_BREAKOUT_REVERSAL",
]

ENABLE_FAILED_FVG_REVERSAL = True
FAILED_FVG_REVERSAL_BASE_MIN_SCORE = 92

ENABLE_HTF_FIB_CONFLUENCE = True
HTF_FIB_CONFLUENCE_BASE_MIN_SCORE = 92

ENABLE_SUPPLY_DEMAND_CONTEXT = True
ENABLE_SUPPLY_DEMAND_RETEST = True
SUPPLY_DEMAND_RETEST_BASE_MIN_SCORE = 92

# EXTREME SWEEP RECLAIM
ENABLE_EXTREME_SWEEP_RECLAIM = True
EXTREME_SWEEP_RECLAIM_BASE_MIN_SCORE = 92

# =========================
# Opposite Direction / Hedging
# =========================
ALLOW_OPPOSITE_DIRECTION_TRADES = True

# =========================
# Scalp Mode
# =========================
ENABLE_SCALP_MODE = True

SCALP_STRATEGIES = [
    "FVG_CE_MITIGATION",
    "FAILED_FVG_REVERSAL",
    "RELIEF_RALLY",
]

SCALP_MIN_SCORE = 98

# Fixed scalp plan
SCALP_FIXED_STOP_DISTANCE = 10.0
SCALP_MIN_TARGET_DISTANCE = 3.5
SCALP_MAX_TARGET_DISTANCE = 9.0

# =========================
# Telegram External Signal Trading
# =========================
ENABLE_TELEGRAM_SIGNAL_TRADING = False

TELEGRAM_SIGNAL_MODE = "ALERT_ONLY"
# ALERT_ONLY
# CONFIRMATION
# AUTO_EXECUTE

TELEGRAM_SIGNAL_SYMBOL = "XAUUSD"

ALLOW_TELEGRAM_PRE_SIGNAL_ENTRY = False
TELEGRAM_PRE_SIGNAL_EMERGENCY_SL_PRICE = 12.0
TELEGRAM_PRE_SIGNAL_EMERGENCY_TP_PRICE = 8.0
TELEGRAM_PRE_SIGNAL_LOT = 0.01

TELEGRAM_SIGNAL_DEFAULT_LOT = 0.04
TELEGRAM_SIGNAL_LOW_RISK_LOT = 0.01

TELEGRAM_SIGNAL_MIN_RR = 0.0
TELEGRAM_SIGNAL_MAX_ENTRY_DISTANCE = 3.0

# =========================
# Telegram Source Listener
# =========================
ENABLE_TELEGRAM_SIGNAL_LISTENER = True

TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_USER_SESSION = "telegram_signal_session"

TELEGRAM_SIGNAL_MODE = "AUTO_EXECUTE"
# ALERT_ONLY / CONFIRMATION / AUTO_EXECUTE

TELEGRAM_SIGNAL_SYMBOL = "XAUUSD"

ALLOW_TELEGRAM_SIGNAL_WITHOUT_TP = True
TELEGRAM_NO_TP_LOT = 0.05

TELEGRAM_SIGNAL_SOURCES = [
    {
        "name": "Steve",
        "chat": 3480309161,
        "enabled": True,
        "parser_profile": "STEVE",
    },
    {
        "name": "Nazeh_VIP",
        "chat": 2629691581,
        "enabled": True,
        "parser_profile": "NAZEH",
    },
]

# =========================
# Delayed Retrace Entry
# =========================
ENABLE_DELAYED_RETRACE_ENTRY = True
DELAYED_ENTRY_OFFSET_PRICE = 5.5
DELAYED_ENTRY_EXPIRY_MINUTES = 15

DELAYED_ENTRY_SKIP_IF_RR_ABOVE = 1.5
DELAYED_ENTRY_CANCEL_IF_PROFIT_MISSED = 5.0

# Split Delayed Entry
ENABLE_SPLIT_DELAYED_ENTRY = True
SPLIT_DELAYED_ENTRY_IMMEDIATE_PCT = 0.50

DELAYED_ENTRY_STRATEGIES = [
    "FVG_CE_MITIGATION",
    "ORDER_BLOCK",
    "BREAKER_BLOCK",
    "HTF_TREND_PULLBACK",
    "RELIEF_RALLY",
    "FAILED_FVG_REVERSAL",
    "FVG",
    "OB_FVG_COMBO",
    "MTF_SR_FVG_RECLAIM",
]

# Hybrid Delayed Entry Confirmation
ENABLE_DELAYED_ENTRY_CONFIRMATION = True

# Use M1 first. If noisy, change to mt5.TIMEFRAME_M5.
DELAYED_ENTRY_CONFIRMATION_TIMEFRAME = mt5.TIMEFRAME_M5
DELAYED_ENTRY_CONFIRMATION_BARS = 80

DELAYED_ENTRY_CONFIRMATION_BUFFER_PRICE = 0.50
DELAYED_ENTRY_MIN_BODY_ATR = 0.10

# Market-condition based delayed-entry offset
DELAYED_ENTRY_OFFSET_BY_MARKET = {
    "TRENDING": 4.5,
    "PULLBACK_TREND": 2.5,
    "RANGING": 3.5,
    "VOLATILE": 5.5,
    "PENDING": 4.5,
}

# =========================
# MTF_SR_FVG_RECLAIM
# =========================
ENABLE_MTF_SR_FVG_RECLAIM = True
MTF_SR_FVG_RECLAIM_BASE_MIN_SCORE = 93

# =========================
# Elliott / Fibonacci Context
# =========================
ENABLE_ELLIOTT_FIB_CONTEXT = True # may turn it off
ELLIOTT_FIB_CONTEXT_BOOST = 3
ELLIOTT_FIB_CONFLICT_PENALTY = 2

# =========================
# Protected Re-Entry
# =========================
ENABLE_PROTECTED_REENTRY = True

PROTECTED_REENTRY_MIN_PROFIT_PRICE = 6.0
PROTECTED_REENTRY_LOOKBACK_MINUTES = 90
PROTECTED_REENTRY_SCORE_BOOST = 3

PROTECTED_REENTRY_CLOSE_REASONS = [
    "SL",
    "SL_LIKELY",
    "PROFIT_CLOSE",
]

PROTECTED_REENTRY_STRATEGIES = [
    "FVG_CE_MITIGATION",
    "ORDER_BLOCK",
    "BREAKER_BLOCK",
    "HTF_TREND_PULLBACK",
    "RELIEF_RALLY",
    "FAILED_FVG_REVERSAL",
    "FAILED_BREAKOUT_REVERSAL",
    "ORB",
]

# =========================
# Time Context Engine
# =========================
ENABLE_TIME_CONTEXT_ENGINE = True # may turn it off

TIME_CONTEXT_WINDOWS = [
    {
        "name": "LONDON_OPEN_MOMENTUM",
        "start": "07:00",
        "end": "09:30",
        "boost": 2,
        "penalty": 1,
        "boost_strategies": [
            "ORB",
            "SESSION_ORB_RETEST",
            "FVG_CE_MITIGATION",
            "ORDER_BLOCK",
            "BREAKER_BLOCK",
            "HTF_TREND_PULLBACK",
            "MTF_SR_FVG_RECLAIM",
        ],
        "penalty_strategies": [
            "FAST",
        ],
    },
    {
        "name": "NEWYORK_OPEN_LIQUIDITY",
        "start": "13:00",
        "end": "15:30",
        "boost": 2,
        "penalty": 1,
        "boost_strategies": [
            "ORB",
            "SESSION_ORB_RETEST",
            "LIQUIDITY_SWEEP",
            "LIQUIDITY_TRAP",
            "FAILED_BREAKOUT_REVERSAL",
            "FAILED_FVG_REVERSAL",
            "VWAP_RECLAIM",
            "EXTREME_SWEEP_RECLAIM",
        ],
        "penalty_strategies": [
            "FAST",
        ],
    },
    {
        "name": "ASIA_RANGE_TRAP",
        "start": "00:00",
        "end": "07:00",
        "boost": 1,
        "penalty": 2,
        "boost_strategies": [
            "LIQUIDITY_TRAP",
            "CRT_TBS",
            "FRACTAL_SWEEP",
            "VWAP_RECLAIM",
            "STRUCTURE_LIQUIDITY",
        ],
        "penalty_strategies": [
            "ORB",
            "FAST",
            "STRICT",
        ],
    },
    {
        "name": "OFF_HOURS_LOW_QUALITY",
        "start": "21:00",
        "end": "23:59",
        "boost": 0,
        "penalty": 2,
        "boost_strategies": [],
        "penalty_strategies": [
            "ORB",
            "FAST",
            "STRICT",
            "FCR_M1_FVG",
        ],
    },
]

# =========================
# ORB_V00
# =========================
ENABLE_ORB_V00 = True
ORB_V00_BASE_MIN_SCORE = 92

# =========================
# IFVG_RETEST_CONFLUENCE
# =========================
ENABLE_IFVG_RETEST_CONFLUENCE = True # may turn it off
IFVG_RETEST_CONFLUENCE_BASE_MIN_SCORE = 93

# =========================
# Soft SMC Pass
# =========================
ENABLE_SOFT_SMC_FOR_STRONG_SETUPS = True # may turn it off
SOFT_SMC_MIN_SCORE = 98

SOFT_SMC_STRATEGIES = [
    "FVG_CE_MITIGATION",
    "BREAKER_BLOCK",
    "ORDER_BLOCK",
    "OB_FVG_COMBO",
    "HTF_TREND_PULLBACK",
    "LVN_FVG_RECLAIM",
    "AMD_FVG",
    "LIQUIDITY_POOL_OB",
    "IFVG_RETEST_CONFLUENCE",
    "MTF_SR_FVG_RECLAIM",
]