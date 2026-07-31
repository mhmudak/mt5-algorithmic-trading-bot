import os
import MetaTrader5 as mt5
from dotenv import load_dotenv

load_dotenv()

# =========================
# Google Sheets Logging
# =========================
ENABLE_GOOGLE_SHEETS_LOGGING = False
GOOGLE_SHEETS_WEBHOOK_URL = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL", "")
GOOGLE_SHEETS_WEBHOOK_SECRET = os.getenv("GOOGLE_SHEETS_WEBHOOK_SECRET", "")

# =========================
# Strategy Debugging
# =========================
ENABLE_STRATEGY_REJECTION_DEBUG = True

# =========================
# Telegram Signal Messages
# =========================
TELEGRAM_VERBOSE_SIGNALS = False
TELEGRAM_NOTIFY_TRADE_TRACKER_OPENED = False


# =========================
# Market / Data Settings
# =========================
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M15
BARS_TO_FETCH = 100


# =========================
# Broker / Session Timing
# =========================
# MT5 chart/server time is treated as Beirut local broker time.
SESSION_BASIS = "BROKER_LOCAL_TIME"
SESSION_BROKER_TIMEZONE = "Asia/Beirut"

# Times below are broker/chart time, same as Beirut local time.
SESSION_WINDOWS_BROKER_TIME = {
    "OFF_HOURS": {"start": "00:00", "end": "03:00"},
    "ASIA": {"start": "03:00", "end": "10:00"},
    "LONDON_OPEN": {"start": "10:00", "end": "12:00"},
    "LONDON": {"start": "12:00", "end": "15:00"},
    "NEWYORK_OPEN": {"start": "15:00", "end": "17:00"},
    "LONDON_NY_OVERLAP": {"start": "17:00", "end": "19:00"},
    "NEWYORK": {"start": "19:00", "end": "23:00"},
    "NEWYORK_LATE": {"start": "23:00", "end": "00:00"},
}

# Used so existing strategy boosts/blocks for LONDON and NEWYORK still work.
SESSION_FAMILY_MAP = {
    "ASIA": "ASIA",
    "LONDON_OPEN": "LONDON",
    "LONDON": "LONDON",
    "NEWYORK_OPEN": "NEWYORK",
    "LONDON_NY_OVERLAP": "NEWYORK",
    "NEWYORK": "NEWYORK",
    "NEWYORK_LATE": "NEWYORK",
    "OFF_HOURS": "OFF_HOURS",
}


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
ENABLE_TRADING_TIME_BLACKOUT = False

TRADING_BLACKOUT_WINDOWS = [
    # {
    #     "name": "Low liquidity / high slippage window",
    #     "start": "03:00",
    #     "end": "04:00",
    # },
]

# =========================
# Opening Strategy Blackout
# =========================
ENABLE_OPENING_STRATEGY_BLACKOUT = True

OPENING_STRATEGY_BLACKOUT_START = "00:00"
OPENING_STRATEGY_BLACKOUT_END = "03:00"

OPENING_STRATEGY_BLACKOUT_STRATEGIES = [
    "ORB",
    "ORB_V00",
    "WAVETREND_MOMENTUM",
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
# News context memory
# =========================
ENABLE_NEWS_CONTEXT_MEMORY = True

# Used for scenario memory after news, not only blocking.
NEWS_CONTEXT_BEFORE_MINUTES = 30
NEWS_CONTEXT_AFTER_MINUTES = 180

# =========================
# Execution / Risk Settings
# =========================
POSITION_MODE = "fixed"   # "fixed" or "risk"
FIXED_LOT = 0.03
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

ENABLE_HIGH_SLIPPAGE_RETRACEMENT = False
HIGH_SLIPPAGE_RETRACEMENT_PRICE = 10.0
HIGH_SLIPPAGE_EXTRA_SL_PRICE = 3.0
HIGH_SLIPPAGE_WAIT_TIMEOUT_SECONDS = 1800
HIGH_SLIPPAGE_WAIT_POLL_SECONDS = 5

# =========================
# Execution Favorable Drift / Freshness Guard
# =========================
ENABLE_EXECUTION_FAVORABLE_DRIFT_GUARD = True
MAX_FAVORABLE_EXECUTION_DRIFT = 1.0

# =========================
# Low-RR Strict Adverse Slippage Guard
# =========================
ENABLE_LOW_RR_STRICT_ADVERSE_SLIPPAGE_GUARD = True
LOW_RR_STRICT_SLIPPAGE_RR_THRESHOLD = 1.25
LOW_RR_MAX_ADVERSE_SLIPPAGE = 0.20

# =========================
# Execution Price Drift Guard
# =========================
ENABLE_PRICE_DRIFT_GUARD = True
MAX_ENTRY_PRICE_DRIFT = 0.66

ENABLE_MOMENTUM_CONTINUATION_ON_PRICE_DRIFT = True
MOMENTUM_CONTINUATION_MAX_DRIFT_PRICE = 5.0
MOMENTUM_CONTINUATION_MIN_RR = 1.0


FVG_CE_MITIGATION_ALLOW_MOMENTUM_DRIFT = False

# =========================
# Cooldown After SL Hit
# =========================
ENABLE_COOLDOWN_AFTER_SL = True
COOLDOWN_AFTER_SL_MINUTES = 4

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

EXTRA_ENTRY_BREAK_EVEN_TRIGGER_PRICE = 3.5
EXTRA_ENTRY_LOCK_TRIGGER_PRICE = 4.5
EXTRA_ENTRY_LOCK_PRICE = 2.0
EXTRA_ENTRY_TAKE_PROFIT_PRICE = 6.0
# =========================
# Extra Entry RR Discount
# =========================
ENABLE_EXTRA_RR_DISCOUNT = True
EXTRA_RR_MULTIPLIER = 0.75

# =========================
# Worst Extra Profit Lock (PRICE UNITS)
# =========================
ENABLE_WORST_EXTRA_LOCK = True
WORST_EXTRA_LOCK_TRIGGER_PRICE = 2.5
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

CONFLUENCE_DUPLICATE_STRATEGY_GROUPS = [
    ["ORB", "ORB_V00"],
]

# =========================
# Candidate Selection / Fallback
# =========================
ENABLE_CANDIDATE_FALLBACK = True
MAX_CANDIDATES_PER_CANDLE = 5

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

SCALP_MIN_RR = 1.0
SCALP_MIN_SCORE = 97

# Fixed scalp plan
SCALP_FIXED_STOP_DISTANCE = 5.0
SCALP_MIN_TARGET_DISTANCE = 4.0
SCALP_MAX_TARGET_DISTANCE = 8.0

# =========================
# Telegram External Signal Trading
# =========================
ENABLE_TELEGRAM_SIGNAL_TRADING = False

TELEGRAM_SIGNAL_MODE = "AUTO_EXECUTE"
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
    # {
    #     "name": "Nazeh_VIP",
    #     "chat": 2629691581,
    #     "enabled": True,
    #     "parser_profile": "NAZEH",
    # },
]

ENABLE_TELEGRAM_WAIT_BETTER_ENTRY = True
TELEGRAM_WAIT_BETTER_ENTRY_POLL_SECONDS = 10
TELEGRAM_WAIT_BETTER_ENTRY_MAX_PROFIT_MOVE = 10.0
TELEGRAM_WAIT_BETTER_ENTRY_TIMEOUT_SECONDS = 1800

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
    "WAVETREND_MOMENTUM",
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
    "WAVETREND_MOMENTUM",
]

# =========================
# Final HTF Liquidity Soft Override
# =========================
ENABLE_FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE = True

FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_STRATEGIES = [
    "BREAKER_BLOCK",
]

FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_MIN_SCORE = 100
FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_MIN_RR = 2.0

FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_SESSIONS = [
    "LONDON",
    "NEWYORK",
]

FINAL_HTF_LIQUIDITY_SOFT_OVERRIDE_ENTRY_KEYWORDS = [
    "RETEST",
]

# BREAKER_BLOCK
ENABLE_BREAKER_BLOCK_EXTRA_SL = True
BREAKER_BLOCK_EXTRA_SL_PRICE = 3.0

# =========================
# Range / Consolidation Strategies
# =========================
ENABLE_RANGE_SWEEP_RECLAIM = True
RANGE_SWEEP_RECLAIM_BASE_MIN_SCORE = 92

RANGE_SWEEP_LOOKBACK_BARS = 48
RANGE_SWEEP_BUFFER_PRICE = 0.80
RANGE_SWEEP_RECLAIM_BUFFER_PRICE = 0.30
RANGE_SWEEP_SL_BUFFER_PRICE = 1.50
RANGE_SWEEP_MIN_RANGE_ATR = 2.0
RANGE_SWEEP_MAX_RANGE_ATR = 10.0


ENABLE_VWAP_RANGE_MEAN_REVERSION = True
VWAP_RANGE_MEAN_REVERSION_BASE_MIN_SCORE = 90

VWAP_RANGE_LOOKBACK_BARS = 96
VWAP_RANGE_EDGE_ZONE_PCT = 0.25
VWAP_RANGE_MIN_DEVIATION_ATR = 0.80
VWAP_RANGE_SL_BUFFER_PRICE = 1.50

# =========================
# ORB Direct Breakout Execution
# =========================
ENABLE_ORB_DIRECT_BREAKOUT = True
ORB_DIRECT_BREAKOUT_MIN_SCORE = 98
ORB_DIRECT_BREAKOUT_REQUIRE_SMC = True
ORB_DIRECT_BREAKOUT_EXTRA_SL_PRICE = 3.0

# WAVETREND_MOMENTUM_M5
ENABLE_WAVETREND_MOMENTUM_M5 = True
WAVETREND_MOMENTUM_BASE_MIN_SCORE = 91
WAVETREND_MOMENTUM_EXTRA_SL_PRICE = 2.0
WAVETREND_MOMENTUM_MIN_RR = 0.73

# =========================
# WaveTrend Momentum Risk Control
# =========================
ENABLE_WAVETREND_STRICT_SL = True
WAVETREND_MOMENTUM_MAX_STOP_DISTANCE = 7.0


# MICRO SR SWEEP RECLAIM
ENABLE_MICRO_SR_SWEEP_RECLAIM = True
MICRO_SR_SWEEP_RECLAIM_BASE_MIN_SCORE = 91

# =========================
# M5 Execution Confirmation
# =========================
ENABLE_M5_EXECUTION_CONFIRMATION = True # may turn it off

M5_EXECUTION_CONFIRMATION_TIMEFRAME = mt5.TIMEFRAME_M5
M5_EXECUTION_CONFIRMATION_BARS = 80
M5_EXECUTION_MIN_BODY_ATR = 0.10

M5_EXECUTION_CONFIRMATION_STRATEGIES = [
    "ORB",
    "ORB_V00",
    "FVG",
    "FVG_CE_MITIGATION",
    "ORDER_BLOCK",
    "BREAKER_BLOCK",
    "FAILED_FVG_REVERSAL",
    "FAILED_BREAKOUT_REVERSAL",
    "WAVETREND_MOMENTUM",
]

# =========================
# Rollover Trading Protection
# =========================
ENABLE_ROLLOVER_TRADING_BLOCK = True

ROLLOVER_BLOCK_WINDOWS = [
    {
        "name": "ROLLOVER_NIGHT",
        "start": "23:55",
        "end": "00:15",
    },
]

# =========================
# Execution Block Memory
# =========================
ENABLE_EXECUTION_BLOCK_MEMORY = True

EXECUTION_BLOCK_MEMORY_EXPIRY_MINUTES = 90

EXECUTION_BLOCK_MEMORY_REASONS = [
    "HIGH_SLIPPAGE",
    "HIGH_ADVERSE_SLIPPAGE",
    "SETUP_STALE_FAVORABLE_DRIFT",
    "LOW_RR_HIGH_ADVERSE_SLIPPAGE",
]

# =========================
# Candidate Rejection Recovery
# =========================
ENABLE_CANDIDATE_REJECTION_RECOVERY = True

CANDIDATE_REJECTION_RECOVERY_EXPIRY_MINUTES = 30
CANDIDATE_REJECTION_RECOVERY_MIN_SCORE = 98

CANDIDATE_REJECTION_RECOVERY_REASONS = [
    "LOW_RR",
    "MTF_CONFLICT_RETRACE_FIRST",
    "SMC_FAILED",
    "HTF_LIQUIDITY_REJECTED",
]

CANDIDATE_REJECTION_RECOVERY_STRATEGIES = [
    "BREAKER_BLOCK",
    "WAVETREND_MOMENTUM",
    "HTF_TREND_PULLBACK",
    "FAILED_FVG_REVERSAL",
    "FAILED_BREAKOUT_REVERSAL",
    "SESSION_ORB_RETEST",
    "HEAD_SHOULDERS",
    "ORDER_BLOCK",
    "RELIEF_RALLY",
    "LIQUIDITY_SWEEP",
]

CANDIDATE_REJECTION_RECOVERY_REQUIRE_M5_CONFIRMATION = True
CANDIDATE_REJECTION_RECOVERY_MIN_RECOVERED_RR = 1.2

# =========================
# Generic Rejected Candidate Trade Plan Recovery
# =========================
ENABLE_GENERIC_REJECTED_CANDIDATE_TRADE_PLAN = True

GENERIC_REJECTED_CANDIDATE_RECOVERY_REASONS = [
    "mtf_conflict",
    "htf_liquidity_rejected",
    "orb_too_extended",
    "continuation_safety",
    "candidate_rejected",
]

GENERIC_REJECTED_CANDIDATE_MIN_RR_TO_TRACK = 0.20
GENERIC_REJECTED_CANDIDATE_NOTIFY_TELEGRAM = True

TELEGRAM_NOTIFY_REJECTED_CANDIDATE_TRACKED = True
REJECTED_CANDIDATE_TELEGRAM_MIN_SCORE = 95
REJECTED_CANDIDATE_TELEGRAM_MIN_RR = 1.00
REJECTED_CANDIDATE_TELEGRAM_COOLDOWN_MINUTES = 30

# Continuation Safety Guard
# =========================
ENABLE_CONTINUATION_SAFETY_GUARD = True

CONTINUATION_SAFETY_BLOCK_ORB_FAST_ON_ELLIOTT_FIB_CONFLICT = True

CONTINUATION_SAFETY_ORB_FAST_MAX_RANGE_ATR_MULTIPLIER = 6.0

CONTINUATION_SAFETY_RETRACE_FIRST_STRATEGIES = [
    "RELIEF_RALLY",
]

CONTINUATION_SAFETY_RETRACE_FIRST_ENTRY_MODELS = [
    "RELIEF_CONTINUATION",
]

CONTINUATION_SAFETY_MIN_IMMEDIATE_RR = 1.50


# =========================
# MTF Conflict Opportunity Tracker + Soft Execution
# =========================
ENABLE_MTF_CONFLICT_OPPORTUNITY_TRACKER = True
MTF_CONFLICT_OPPORTUNITY_EXPIRY_MINUTES = 60

ENABLE_MTF_CONFLICT_SOFT_EXECUTION = True

MTF_CONFLICT_SOFT_EXECUTION_STRATEGIES = [
    "BREAKER_BLOCK",
    "ORB",
    "ORB_V00",
    "STRUCTURE_LIQUIDITY",
    "LIQUIDITY_SWEEP",
    "CRT_TBS",
    "LIQUIDITY_TRAP",
]

MTF_CONFLICT_RETRACE_FIRST_STRATEGIES = [
    "WAVETREND_MOMENTUM",
    "FAILED_FVG_REVERSAL",
    "SESSION_ORB_RETEST",
    "HTF_TREND_PULLBACK",
    "HEAD_SHOULDERS",
    "ORDER_BLOCK",
    "RELIEF_RALLY",
    "MICRO_SR_SWEEP_RECLAIM",
    "FVG_CE_MITIGATION",
    "FVG",
]

MTF_CONFLICT_TRACK_ONLY_STRATEGIES = [
    "RANGE_SWEEP_RECLAIM",
]

MTF_CONFLICT_SOFT_EXECUTION_MIN_SCORE = 100

# When no MTF-aligned trade is open:
# counter-MTF setup may execute using its calculated TP/SL.
MTF_CONFLICT_USE_CALCULATED_TP_WHEN_NO_MTF_POSITION = True

# When an MTF-aligned trade is already open:
# counter-MTF setup becomes only a quick scalp.
MTF_CONFLICT_SCALP_ONLY_WHEN_MTF_POSITION_EXISTS = True
MTF_CONFLICT_COUNTER_SCALP_TP_PRICE = 4.0
MTF_CONFLICT_COUNTER_SCALP_SL_PRICE = 8.0
MTF_CONFLICT_COUNTER_SCALP_LOT_MULTIPLIER = 0.50

MTF_CONFLICT_REQUIRE_M5_CONFIRMATION = True
MTF_CONFLICT_REQUIRE_SHADOW_TRADE_PLAN = True
MTF_CONFLICT_REQUIRE_SHADOW_RR_FOR_NORMAL_EXECUTION = True
MTF_CONFLICT_REQUIRE_SHADOW_RR_FOR_SCALP = False

TELEGRAM_NOTIFY_MTF_CONFLICT_CANDIDATE_TRACKED = True
MTF_CONFLICT_CANDIDATE_TELEGRAM_MIN_SCORE = 95
MTF_CONFLICT_CANDIDATE_TELEGRAM_MIN_RR = 0.90
MTF_CONFLICT_CANDIDATE_TELEGRAM_HIGH_SCORE = 97

# =========================
# Session Strategy Hard Blocks / Boosts
# =========================
ENABLE_SESSION_STRATEGY_BLOCKS = True
ENABLE_SESSION_STRATEGY_BOOSTS = True

SESSION_STRATEGY_BLOCKS = {
    "LONDON": [
        "RANGE_SWEEP_RECLAIM",
        "HEAD_SHOULDERS",
    ],
    "ASIA": [
        "FVG_CE_MITIGATION",
    ],
    "OFF_HOURS": [
        "FVG_CE_MITIGATION",
        "FVG",
        "MICRO_SR_SWEEP_RECLAIM",
    ],
}

SESSION_STRATEGY_BOOSTS = {
    "NEWYORK": [
        "ORB",
        "ORB_V00",
        "SESSION_ORB_RETEST",
        "WAVETREND_MOMENTUM",
        "BREAKER_BLOCK",
        "FVG_CE_MITIGATION",
        "MICRO_SR_SWEEP_RECLAIM",
    ],
    "LONDON": [
        "WAVETREND_MOMENTUM",
        "SESSION_ORB_RETEST",
        "FAILED_FVG_REVERSAL",
    ],
    "ASIA": [
        "BREAKER_BLOCK",
        "HEAD_SHOULDERS",
    ],
    "OFF_HOURS": [
        "BREAKER_BLOCK",
        "FAILED_FVG_REVERSAL",
        "WAVETREND_MOMENTUM",
        "ORB",
        "ORB_V00",
    ],
}

SESSION_STRATEGY_BOOST_VALUE = 2

# =========================
# FVG Zone Staged Entry
# =========================
ENABLE_FVG_ZONE_STAGED_ENTRY = True

FVG_ZONE_STAGED_ENTRY_STRATEGIES = [
    "FVG",
    "FVG_CE_MITIGATION",
]

FVG_ZONE_STAGED_ENTRY_LEVELS = [
    0.0,
    0.60,
    0.85,
]

FVG_ZONE_STAGED_ENTRY_EXPIRY_MINUTES = 30

FVG_ZONE_STAGED_ENTRY_SL_BUFFER = 3.0

STRATEGY_EXTRA_SL_BUFFER = {
    "FVG_CE_MITIGATION": 2.0,
    "HTF_TREND_PULLBACK": 3.0,
}

# =========================
# Monitoring Noise Control
# =========================
LOG_STRATEGY_SESSION_BLOCKS_TO_SHEETS = False
LOG_OPENING_BLACKOUT_BLOCKS_TO_SHEETS = False

# =========================
# Tick-Level Recovery Retry
# =========================
ENABLE_TICK_LEVEL_RECOVERY_RETRY = True

ENABLE_MTF_CONFLICT_HIGH_SLIPPAGE_RETRY = True
ENABLE_LOW_RR_RECOVERY_HIGH_SLIPPAGE_RETRY = True

HIGH_SLIPPAGE_RETRY_EXPIRY_MINUTES = 5
HIGH_SLIPPAGE_RETRY_MAX_ENTRY_DISTANCE = 0.30

HIGH_SLIPPAGE_RETRY_SOURCES = [
    "MTF_CONFLICT",
    "LOW_RR_RECOVERY",
]

# =========================
# ORB Tick Breakout Watcher
# =========================
ENABLE_ORB_TICK_BREAKOUT_WATCHER = True

ORB_TICK_BREAKOUT_WATCH_STRATEGIES = [
    "ORB",
    "ORB_V00",
]

ORB_TICK_BREAKOUT_EXPIRY_MINUTES = 75

ORB_TICK_BREAKOUT_MIN_DISTANCE = 0.30
ORB_TICK_BREAKOUT_MIN_RR = 2.0

ORB_TICK_BREAKOUT_REQUIRE_M5_CONFIRMATION = False

# =========================
# Intrabar ORB / Liquidity Detector
# =========================
ENABLE_INTRABAR_PRICE_EVENT_DETECTOR = True

INTRABAR_PRICE_EVENT_ALLOWED_STRATEGIES = [
    "ORB_V00",
    "ORB",
    "LIQUIDITY_SWEEP",
    "LIQUIDITY_TRAP",
    "RELIEF_RALLY",
    "STRUCTURE_LIQUIDITY",
    "MICRO_SR_SWEEP_RECLAIM",
    "ORDER_BLOCK",
    "EXTREME_SWEEP_RECLAIM",
    "RANGE_SWEEP_RECLAIM",
    "VWAP_RECLAIM",
    "INTRABAR_VWAP_LIQUIDITY_RECLAIM",
    "FAILED_FVG_REVERSAL",
]

INTRABAR_PRICE_EVENT_MIN_SCORE = 95
INTRABAR_PRICE_EVENT_MIN_RR = 1.5
INTRABAR_PRICE_EVENT_BREAK_DISTANCE_PRICE = 0.30
INTRABAR_PRICE_EVENT_MAX_BREAK_DISTANCE_PRICE = 4.00
INTRABAR_PRICE_EVENT_RECLAIM_BUFFER_PRICE = 0.20
INTRABAR_PRICE_EVENT_EXPIRY_SECONDS = 180
INTRABAR_PRICE_EVENT_EXTRA_SL_PRICE = 2.0

INTRABAR_PRICE_EVENT_STRATEGY_PROFILES = {
    # ---------------------------------------------------------
    # OPENING RANGE BREAKOUT
    # Fast continuation strategy.
    # Needs EMA alignment but should not wait for M5 confirmation.
    # ---------------------------------------------------------
    "ORB_V00": {
        "trigger": "DIRECT_BREAKOUT",
        "level_source": "ORB_RANGE",
        "lookback_bars": 15,

        "min_score": 96,
        "min_rr": 1.50,
        "target_rr": 1.80,

        "min_break_distance": 0.30,
        "max_break_distance": 3.50,
        "reclaim_buffer": 0.20,

        "require_ema_alignment": True,
        "require_m5_confirmation": False,

        "min_sl_distance": 3.50,
        "max_sl_distance": 10.00,
        "min_tp_distance": 6.00,
        "max_tp_distance": 20.00,
    },

    "ORB": {
        "trigger": "DIRECT_BREAKOUT",
        "level_source": "ORB_RANGE",
        "lookback_bars": 15,

        "min_score": 95,
        "min_rr": 1.50,
        "target_rr": 1.75,

        "min_break_distance": 0.30,
        "max_break_distance": 4.00,
        "reclaim_buffer": 0.20,

        "require_ema_alignment": True,
        "require_m5_confirmation": False,

        "min_sl_distance": 4.00,
        "max_sl_distance": 12.00,
        "min_tp_distance": 7.00,
        "max_tp_distance": 24.00,
    },

    # ---------------------------------------------------------
    # LIQUIDITY REVERSAL STRATEGIES
    # EMA alignment is intentionally disabled because a valid
    # sweep can initially occur against the current EMA direction.
    # M5 confirmation helps avoid entering during the sweep itself.
    # ---------------------------------------------------------
    "LIQUIDITY_SWEEP": {
        "trigger": "SWEEP_RECLAIM",
        "level_source": "RECENT_RANGE",
        "lookback_bars": 12,

        "min_score": 95,
        "min_rr": 1.30,
        "target_rr": 1.55,

        "min_break_distance": 0.25,
        "max_break_distance": 3.50,
        "reclaim_buffer": 0.20,

        "require_ema_alignment": False,
        "require_m5_confirmation": True,

        "min_sl_distance": 3.50,
        "max_sl_distance": 10.00,
        "min_tp_distance": 5.00,
        "max_tp_distance": 18.00,
    },

    "LIQUIDITY_TRAP": {
        "trigger": "TRAP_RECLAIM",
        "level_source": "RECENT_RANGE",
        "lookback_bars": 12,

        "min_score": 96,
        "min_rr": 1.30,
        "target_rr": 1.60,

        "min_break_distance": 0.30,
        "max_break_distance": 4.00,
        "reclaim_buffer": 0.25,

        "require_ema_alignment": False,
        "require_m5_confirmation": True,

        "min_sl_distance": 4.00,
        "max_sl_distance": 11.00,
        "min_tp_distance": 6.00,
        "max_tp_distance": 20.00,
    },

    # ---------------------------------------------------------
    # COUNTERTREND / RELIEF REVERSAL
    # Wider stops and stronger M5 confirmation are appropriate.
    # ---------------------------------------------------------
    "RELIEF_RALLY": {
        "trigger": "REVERSAL_RECLAIM",
        "level_source": "RECENT_RANGE",
        "lookback_bars": 16,

        "min_score": 96,
        "min_rr": 1.35,
        "target_rr": 1.60,

        "min_break_distance": 0.35,
        "max_break_distance": 4.50,
        "reclaim_buffer": 0.30,

        "require_ema_alignment": False,
        "require_m5_confirmation": True,

        "min_sl_distance": 4.50,
        "max_sl_distance": 14.00,
        "min_tp_distance": 7.00,
        "max_tp_distance": 24.00,
    },

    # ---------------------------------------------------------
    # STRUCTURE CONTINUATION
    # Requires both EMA alignment and M5 confirmation because it
    # must prove that the structure break is continuing.
    # ---------------------------------------------------------
    "STRUCTURE_LIQUIDITY": {
        "trigger": "STRUCTURE_CONTINUATION",
        "level_source": "RECENT_STRUCTURE",
        "lookback_bars": 18,

        "min_score": 96,
        "min_rr": 1.40,
        "target_rr": 1.70,

        "min_break_distance": 0.35,
        "max_break_distance": 4.00,
        "reclaim_buffer": 0.25,

        "require_ema_alignment": True,
        "require_m5_confirmation": True,

        "min_sl_distance": 4.00,
        "max_sl_distance": 12.00,
        "min_tp_distance": 7.00,
        "max_tp_distance": 22.00,
    },

    # ---------------------------------------------------------
    # MICRO SUPPORT / RESISTANCE
    # Smaller structure means tighter break, stop and target ranges.
    # M5 confirmation would often arrive too late.
    # ---------------------------------------------------------
    "MICRO_SR_SWEEP_RECLAIM": {
        "trigger": "SWEEP_RECLAIM",
        "level_source": "MICRO_RANGE",
        "lookback_bars": 8,

        "min_score": 96,
        "min_rr": 1.20,
        "target_rr": 1.35,

        "min_break_distance": 0.20,
        "max_break_distance": 2.50,
        "reclaim_buffer": 0.15,

        "require_ema_alignment": False,
        "require_m5_confirmation": False,

        "min_sl_distance": 2.50,
        "max_sl_distance": 8.00,
        "min_tp_distance": 4.00,
        "max_tp_distance": 12.00,
    },

    # ---------------------------------------------------------
    # ORDER BLOCK
    # The entry requires a reaction/reclaim from a recent structural
    # zone. M5 confirmation is used to avoid entering while price is
    # still cutting through the block.
    #
    # Existing trigger/source names are used for compatibility.
    # ---------------------------------------------------------
    "ORDER_BLOCK": {
        "trigger": "REVERSAL_RECLAIM",
        "level_source": "RECENT_STRUCTURE",
        "lookback_bars": 20,

        "min_score": 96,
        "min_rr": 1.30,
        "target_rr": 1.55,

        "min_break_distance": 0.25,
        "max_break_distance": 5.00,
        "reclaim_buffer": 0.30,

        "require_ema_alignment": False,
        "require_m5_confirmation": True,

        "min_sl_distance": 4.00,
        "max_sl_distance": 14.00,
        "min_tp_distance": 6.00,
        "max_tp_distance": 24.00,
    },

    # ---------------------------------------------------------
    # EXTREME RANGE SWEEP
    # Wider structural move, therefore larger permissible stop,
    # target and sweep distances.
    # ---------------------------------------------------------
    "EXTREME_SWEEP_RECLAIM": {
        "trigger": "SWEEP_RECLAIM",
        "level_source": "EXTREME_RANGE",
        "lookback_bars": 20,

        "min_score": 96,
        "min_rr": 1.40,
        "target_rr": 1.65,

        "min_break_distance": 0.40,
        "max_break_distance": 5.00,
        "reclaim_buffer": 0.30,

        "require_ema_alignment": False,
        "require_m5_confirmation": True,

        "min_sl_distance": 5.00,
        "max_sl_distance": 16.00,
        "min_tp_distance": 8.00,
        "max_tp_distance": 28.00,
    },

    # ---------------------------------------------------------
    # STANDARD RANGE SWEEP
    # Faster than an extreme sweep and therefore no mandatory M5
    # confirmation, but its permissible distances remain controlled.
    # ---------------------------------------------------------
    "RANGE_SWEEP_RECLAIM": {
        "trigger": "SWEEP_RECLAIM",
        "level_source": "RECENT_RANGE",
        "lookback_bars": 14,

        "min_score": 95,
        "min_rr": 1.25,
        "target_rr": 1.45,

        "min_break_distance": 0.25,
        "max_break_distance": 3.50,
        "reclaim_buffer": 0.20,

        "require_ema_alignment": False,
        "require_m5_confirmation": False,

        "min_sl_distance": 3.00,
        "max_sl_distance": 10.00,
        "min_tp_distance": 5.00,
        "max_tp_distance": 18.00,
    },

    # ---------------------------------------------------------
    # VWAP RECLAIM
    # VWAP itself supplies the directional context, so strict EMA
    # alignment is unnecessary. M5 confirmation prevents a weak touch.
    # ---------------------------------------------------------
    "VWAP_RECLAIM": {
        "trigger": "VWAP_RECLAIM",
        "level_source": "VWAP_CONTEXT",
        "lookback_bars": 10,

        "min_score": 96,
        "min_rr": 1.25,
        "target_rr": 1.45,

        "min_break_distance": 0.20,
        "max_break_distance": 3.00,
        "reclaim_buffer": 0.20,

        "require_ema_alignment": False,
        "require_m5_confirmation": True,

        "min_sl_distance": 3.00,
        "max_sl_distance": 9.00,
        "min_tp_distance": 5.00,
        "max_tp_distance": 16.00,
    },

    # ---------------------------------------------------------
    # VWAP + LIQUIDITY RECLAIM
    # Stronger setup than basic VWAP reclaim, but it requires a
    # higher score and allows slightly larger structural distances.
    # ---------------------------------------------------------
    "INTRABAR_VWAP_LIQUIDITY_RECLAIM": {
        "trigger": "VWAP_LIQUIDITY_RECLAIM",
        "level_source": "RECENT_RANGE",
        "lookback_bars": 14,

        "min_score": 97,
        "min_rr": 1.35,
        "target_rr": 1.60,

        "min_break_distance": 0.30,
        "max_break_distance": 4.00,
        "reclaim_buffer": 0.25,

        "require_ema_alignment": False,
        "require_m5_confirmation": True,

        "min_sl_distance": 4.00,
        "max_sl_distance": 12.00,
        "min_tp_distance": 6.00,
        "max_tp_distance": 22.00,
    },

    # ---------------------------------------------------------
    # FAILED FVG REVERSAL
    # Kept as the reference profile because its settings already
    # reflect the strategy's actual reversal geometry accurately.
    # ---------------------------------------------------------
    "FAILED_FVG_REVERSAL": {
        "trigger": "FAILED_FVG_REVERSAL_RECLAIM",
        "level_source": "RECENT_RANGE",
        "lookback_bars": 20,

        "min_score": 96,
        "min_rr": 1.10,
        "target_rr": 1.25,

        "min_break_distance": 0.20,
        "max_break_distance": 8.00,
        "reclaim_buffer": 0.25,

        "require_ema_alignment": False,
        "require_m5_confirmation": True,

        "min_sl_distance": 4.00,
        "max_sl_distance": 12.00,
        "min_tp_distance": 6.00,
        "max_tp_distance": 20.00,
    },
}

INTRABAR_PRICE_EVENT_MIN_SL_DISTANCE_PRICE = 3.0
INTRABAR_PRICE_EVENT_MAX_SL_DISTANCE_PRICE = 14.0

INTRABAR_PRICE_EVENT_MIN_TP_DISTANCE_PRICE = 5.0
INTRABAR_PRICE_EVENT_MAX_TP_DISTANCE_PRICE = 28.0
INTRABAR_PRICE_EVENT_DEFAULT_TARGET_RR = 1.35

# Safety first: false means no M5 close confirmation required.
INTRABAR_PRICE_EVENT_REQUIRE_M5_CONFIRMATION = True

INTRABAR_PRICE_EVENT_NOTIFY_TELEGRAM = True

# =========================
# Intrabar Price Event De-duplication Guard
# =========================
ENABLE_INTRABAR_PRICE_EVENT_DEDUP_GUARD = True

INTRABAR_PRICE_EVENT_DEDUP_SECONDS = 180
INTRABAR_PRICE_EVENT_MAX_PER_CANDLE = 2
INTRABAR_PRICE_EVENT_MAX_PER_STRATEGY_PER_CANDLE = 1

INTRABAR_PRICE_EVENT_LOG_DUPLICATE_SKIPS = False

# =========================
# Intrabar M5 Confirmation Filters
# =========================
ENABLE_INTRABAR_M5_CONFIRMATION_FILTERS = True

INTRABAR_M5_CONFIRMATION_TIMEFRAME = mt5.TIMEFRAME_M5
INTRABAR_M5_CONFIRMATION_BARS = 80

INTRABAR_M5_CONFIRMATION_STRATEGIES = [
    "FAILED_FVG_REVERSAL",
    "RELIEF_RALLY",
    "STRUCTURE_LIQUIDITY",
    "VWAP_RECLAIM",
    "INTRABAR_VWAP_LIQUIDITY_RECLAIM",
    "EXTREME_SWEEP_RECLAIM",
]

INTRABAR_M5_USE_HEIKIN_ASHI = True
INTRABAR_M5_USE_PARABOLIC_SAR = True

INTRABAR_M5_PSAR_STEP = 0.02
INTRABAR_M5_PSAR_MAX_STEP = 0.20

# If True, both HA and PSAR must agree.
# If False, one confirmation is enough.
INTRABAR_M5_REQUIRE_ALL_FILTERS = False

# =========================
# Intrabar Price Event Trigger Filters
# =========================
ENABLE_INTRABAR_PRICE_EVENT_VWAP_FILTER = True
ENABLE_INTRABAR_PRICE_EVENT_STRUCTURE_FILTER = True
ENABLE_INTRABAR_PRICE_EVENT_REVERSAL_FILTER = True

INTRABAR_PRICE_EVENT_MIN_CURRENT_BODY_ATR = 0.05
INTRABAR_PRICE_EVENT_MIN_STRUCTURE_BREAK_PRICE = 0.25
INTRABAR_PRICE_EVENT_VWAP_LOOKBACK_BARS = 20

# =========================
# Generic Tick Sniper Execution Engine
# =========================
ENABLE_TICK_SNIPER_EXECUTION = True

TICK_SNIPER_ALLOWED_STRATEGIES = [
    "LIQUIDITY_SWEEP",
    "LIQUIDITY_TRAP",
    "STRUCTURE_LIQUIDITY"
]

TICK_SNIPER_MIN_SCORE = 95
TICK_SNIPER_MIN_RR = 1.2

# Price must move in the trade direction from the reference entry before execution.
TICK_SNIPER_MIN_MOVE_PRICE = 0.30

TICK_SNIPER_EXPIRY_SECONDS = 180
TICK_SNIPER_NOTIFY_TELEGRAM = True

# Keep this false first. Later we can add M5 confirmation strategy-by-strategy.
TICK_SNIPER_REQUIRE_M5_CONFIRMATION = False

TICK_SNIPER_STRATEGY_PROFILES = {
    "LIQUIDITY_SWEEP": {
        "trigger": "DIRECTIONAL_RECLAIM",
        "min_move_price": 0.30,
        "min_rr": 1.2,
        "min_score": 95,
        "require_m5_confirmation": False,
    },
    "LIQUIDITY_TRAP": {
        "trigger": "DIRECTIONAL_RECLAIM",
        "min_move_price": 0.35,
        "min_rr": 1.2,
        "min_score": 95,
        "require_m5_confirmation": False,
    },
    "STRUCTURE_LIQUIDITY": {
        "trigger": "STRUCTURE_CONTINUATION",
        "min_move_price": 0.40,
        "min_rr": 1.3,
        "min_score": 95,
        "require_m5_confirmation": False,
    },
}

# =========================
# Candidate Rejection Notifications
# =========================
ENABLE_CANDIDATE_REJECTION_TELEGRAM_ALERTS = True

TELEGRAM_NOTIFY_CANDIDATE_REJECTED_LOW_RR = True
TELEGRAM_NOTIFY_CANDIDATE_RECOVERY_INVALIDATED = True

# Keep this False unless you want a lot of noise.
TELEGRAM_NOTIFY_GENERIC_CANDIDATE_REJECTED = False

# =========================
# SMC Failed Low RR SL-Zone Recovery
# =========================
ENABLE_SMC_FAILED_LOW_RR_SL_ZONE_RECOVERY = True
SMC_FAILED_LOW_RR_SL_ZONE_EXPIRY_MINUTES = 65

SMC_FAILED_LOW_RR_SL_ZONE_RATIO = 0.25
SMC_FAILED_LOW_RR_ALLOW_POST_SL_SWEEP_RECLAIM = True

SMC_FAILED_LOW_RR_SL_ZONE_STRATEGIES = [
    "SESSION_ORB_RETEST",
    "WAVETREND_MOMENTUM",
    "RELIEF_RALLY",
    "FAILED_FVG_REVERSAL",
    "BREAKER_BLOCK",
    "ORDER_BLOCK",
    "STRUCTURE_LIQUIDITY",
]

# =========================
# Setup Outcome Tracker
# =========================
ENABLE_SETUP_OUTCOME_TRACKER = True

SETUP_OUTCOME_EXPIRY_MINUTES = 180

SETUP_OUTCOME_WIN_PRICE_MOVE = 10.0

SETUP_OUTCOME_TRACK_EVENTS = [
    "SETUP_DETECTED",
    "CANDIDATE_REJECTED_LOW_RR",
    "CANDIDATE_REJECTED",
    "MTF_CONFLICT_CANDIDATE_TRACKED",
    "FVG_STAGED_ENTRY_WAITING",
    "ORB_TICK_BREAKOUT_WATCHING",
]

SETUP_OUTCOME_SCENARIO_WINDOW_MINUTES = 15

# For your idea: price first goes against setup, then returns into profit.
SETUP_OUTCOME_MIN_ADVERSE_FOR_REENTRY = 3.0
SETUP_OUTCOME_REENTRY_PROFIT_TRIGGER = 5.0

# =========================
# Setup Similarity Memory
# =========================
ENABLE_SETUP_SIMILARITY_MEMORY = True

SETUP_SIMILARITY_MIN_SAMPLES = 3
SETUP_SIMILARITY_MIN_W10_RATE = 0.65
SETUP_SIMILARITY_MAX_SL_RATE = 0.35

SETUP_SIMILARITY_ALERT_ON_EVENTS = [
    "SETUP_DETECTED",
    "CANDIDATE_REJECTED_LOW_RR",
    "CANDIDATE_REJECTED",
    "MTF_CONFLICT_CANDIDATE_TRACKED",
]

# =========================
# Similarity Memory Scoring
# =========================
ENABLE_SETUP_SIMILARITY_SCORING = True

SETUP_SIMILARITY_FAVORABLE_SCORE_BOOST = 3
SETUP_SIMILARITY_DANGEROUS_SCORE_PENALTY = 5
SETUP_SIMILARITY_NEUTRAL_SCORE_BOOST = 0

# =========================
# Scenario Cluster Memory
# =========================
ENABLE_SCENARIO_CLUSTER_MEMORY = True

SCENARIO_CLUSTER_MIN_STRATEGIES = 2
SCENARIO_CLUSTER_MIN_SAMPLES = 3

SCENARIO_CLUSTER_MIN_W10_RATE = 0.65
SCENARIO_CLUSTER_MAX_SL_RATE = 0.35

# =========================
# Scenario Cluster Scoring
# =========================
ENABLE_SCENARIO_CLUSTER_SCORING = True

SCENARIO_CLUSTER_FAVORABLE_SCORE_BOOST = 2
SCENARIO_CLUSTER_DANGEROUS_SCORE_PENALTY = 4
SCENARIO_CLUSTER_NEUTRAL_SCORE_BOOST = 0

# =========================
# SETUP OUTCOME MEMORY GUARD
# =========================
ENABLE_SETUP_OUTCOME_MEMORY_GUARD = True

# Start safely: warning only, no hard block.
MEMORY_GUARD_BLOCK_DANGEROUS_PATTERNS = False

MEMORY_GUARD_MIN_SAMPLES_FOR_WARNING = 3
MEMORY_GUARD_MIN_SAMPLES_FOR_BLOCK = 8

MEMORY_GUARD_NOTIFY_ON_WARNING = True

# =========================
# SCENARIO SIGNATURE CONFIDENCE
# =========================
ENABLE_SCENARIO_SIGNATURE_CONFIDENCE = True

SCENARIO_SIGNATURE_MIN_SAMPLES = 3
SCENARIO_SIGNATURE_FAVORABLE_SCORE_BOOST = 4
SCENARIO_SIGNATURE_DANGEROUS_SCORE_PENALTY = 6
SCENARIO_SIGNATURE_NEUTRAL_SCORE_BOOST = 1

SCENARIO_SIGNATURE_MIN_W10_RATE = 0.60
SCENARIO_SIGNATURE_MAX_SL_RATE = 0.35

SCENARIO_SIGNATURE_REQUIRE_MULTI_STRATEGY = True
SCENARIO_SIGNATURE_MIN_STRATEGIES = 2

ENABLE_SCENARIO_SIGNATURE_TELEGRAM_ALERTS = True

SCENARIO_SIGNATURE_TELEGRAM_ALERT_CLASSIFICATIONS = [
    "FAVORABLE_SCENARIO_SIGNATURE",
    "DANGEROUS_SCENARIO_SIGNATURE",
]

# =========================
# MEMORY DECISION REPORT
# =========================
ENABLE_MEMORY_DECISION_REPORT = True
MEMORY_DECISION_REPORT_MAX_ITEMS = 5000

# =========================
# AI SHADOW ADVISOR
# =========================
ENABLE_AI_SHADOW_ADVISOR = True

AI_SHADOW_ADVISOR_MIN_SAMPLES = 5
AI_SHADOW_ADVISOR_BLOCK_SL_RATE = 0.6
AI_SHADOW_ADVISOR_ALLOW_W10_RATE = 0.6

AI_SHADOW_ADVISOR_NOTIFY_TELEGRAM = True

# IMPORTANT:
# False = AI can advise only, it cannot control execution.
# Later, when mature, set this to True.
AI_SHADOW_ADVISOR_EXECUTION_CONTROL_ENABLED = False

# Modes:
# SHADOW_ONLY      = never blocks, only logs and notifies
# WARN_ONLY        = warns but never blocks
# BLOCK_ONLY       = blocks only when AI recommendation is BLOCK
# REQUIRE_ALLOW    = blocks unless AI recommendation is ALLOW
AI_SHADOW_ADVISOR_EXECUTION_CONTROL_MODE = "SHADOW_ONLY"

AI_SHADOW_ADVISOR_BLOCK_RECOMMENDATIONS = ["BLOCK"]
AI_SHADOW_ADVISOR_ALLOW_RECOMMENDATIONS = ["ALLOW"]
AI_SHADOW_ADVISOR_MIN_SAMPLES_FOR_CONTROL = 20

# =========================
# Strategy Advisory
# =========================
ENABLE_STRATEGY_ADVISORY = True
TELEGRAM_NOTIFY_STRATEGY_ADVISORY_CRITICAL = True

# Only these decisions trigger Telegram.
STRATEGY_ADVISORY_TELEGRAM_DECISIONS = [
    "BLOCK_TEMPORARILY",
    "DISABLE_STRATEGY",
    "TRACK_ONLY",
]

STRATEGY_ADVISORY_TELEGRAM_COOLDOWN_MINUTES = 60

STRATEGY_ADVISORY_TELEGRAM_MIN_SAMPLES = 5
STRATEGY_ADVISORY_SKIP_TRACK_ONLY_LOW_SAMPLE_ALERTS = True

# ============================================================
# Confirmation Engine Telegram Risk Alerts
# Phase 1G observe-only warnings
# ============================================================

TELEGRAM_NOTIFY_CONFIRMATION_ENGINE_RISK = True

CONFIRMATION_RISK_TELEGRAM_COOLDOWN_MINUTES = 30
CONFIRMATION_RISK_TELEGRAM_MIN_CONFIDENCE = 75
CONFIRMATION_RISK_TELEGRAM_MIN_NEGATIVE_SCORE_DELTA = -5

CONFIRMATION_RISK_TELEGRAM_MODULES = [
    "CONSOLIDATION_POLICY_AUDIT",
]

CONFIRMATION_RISK_TELEGRAM_INCLUDE_OBSERVE_ONLY_NOTE = True

# ============================================================
# Confirmation Engine Analyzer / Report Integration
# Phase 1K / 1L
# ============================================================

ENABLE_CONFIRMATION_OBSERVATION_ANALYZER_IN_MAIN_ANALYZER = True
ENABLE_CONFIRMATION_SUMMARY_IN_STRATEGY_REPORT = True

# ============================================================
# Confirmation Engine Runtime Safety
# Phase 1O
# ============================================================

ENABLE_CONFIRMATION_ENGINE_OBSERVE_ONLY = True

# The confirmation engine remains observe-only.
# It must not block trades or modify execution behavior.
CONFIRMATION_ENGINE_OBSERVE_ONLY_MODE = True

# ============================================================
# Confirmation Engine Telegram Summary
# Phase 1T
# ============================================================

TELEGRAM_NOTIFY_CONFIRMATION_ENGINE_SUMMARY = True

# Avoid repeated Telegram summaries for same setup/bucket.
CONFIRMATION_SUMMARY_TELEGRAM_COOLDOWN_MINUTES = 10

# Keep summary messages concise.
CONFIRMATION_SUMMARY_TELEGRAM_INCLUDE_MODULE_DETAILS = True
CONFIRMATION_SUMMARY_TELEGRAM_MAX_MODULES = 6

# ============================================================
# Confirmation Engine Shadow Policy
# Phase 2A
# ============================================================

ENABLE_CONFIRMATION_SHADOW_POLICY = True

# Shadow policy never blocks trades in Phase 2A.
CONFIRMATION_SHADOW_POLICY_OBSERVE_ONLY = True

CONFIRMATION_SHADOW_STRONG_CONFIDENCE = 80
CONFIRMATION_SHADOW_SUPPORT_CONFIDENCE = 70
CONFIRMATION_SHADOW_WEAK_CONFIDENCE = 60

CONFIRMATION_SHADOW_STRONG_POSITIVE_DELTA = 3.0
CONFIRMATION_SHADOW_SUPPORT_POSITIVE_DELTA = 0.0
CONFIRMATION_SHADOW_CAUTION_DELTA = -3.0
CONFIRMATION_SHADOW_HIGH_RISK_DELTA = -5.0

# =========================
# Pro Trader Replication Demo Strategy
# =========================
# Demo execution only. No full-margin sizing. No real order-flow dependency.
ENABLE_PRO_TRADER_REPLICATION = True
PRO_TRADER_REPLICATION_MIN_SCORE = 86
PRO_TRADER_REPLICATION_DEFAULT_RR = 1.80
PRO_TRADER_REPLICATION_MIN_STOP_DISTANCE_PRICE = 1.5
PRO_TRADER_REPLICATION_MAX_STOP_DISTANCE_PRICE = 14.0
PRO_TRADER_REPLICATION_MIN_TARGET_DISTANCE_PRICE = 5.0

# =========================
# Key Level Break & Hold Strategy
# =========================
ENABLE_KEY_LEVEL_BREAK_HOLD = True
KEY_LEVEL_BREAK_HOLD_LOOKBACK_BARS = 80
KEY_LEVEL_BREAK_HOLD_MIN_SCORE = 88
KEY_LEVEL_BREAK_HOLD_MIN_LEVEL_TOUCHES = 2
KEY_LEVEL_BREAK_HOLD_TOUCH_TOLERANCE_ATR = 0.20
KEY_LEVEL_BREAK_HOLD_BREAK_BUFFER_ATR = 0.10
KEY_LEVEL_BREAK_HOLD_HOLD_BUFFER_ATR = 0.05
KEY_LEVEL_BREAK_HOLD_MAX_EXTENSION_ATR = 0.75
KEY_LEVEL_BREAK_HOLD_MIN_BODY_ATR = 0.18
KEY_LEVEL_BREAK_HOLD_SL_BUFFER_ATR = 0.25
KEY_LEVEL_BREAK_HOLD_MIN_SL_BUFFER_PRICE = 1.5
KEY_LEVEL_BREAK_HOLD_MAX_SL_DISTANCE_PRICE = 14.0
KEY_LEVEL_BREAK_HOLD_TARGET_RR = 1.80
KEY_LEVEL_BREAK_HOLD_MIN_TP_DISTANCE_PRICE = 5.0


# =========================
# Balanced Auction Range Strategy
# =========================
# Consolidation/range strategy. Demo-only guard enabled by default.
ENABLE_BALANCED_AUCTION_RANGE = True
BALANCED_AUCTION_RANGE_DEMO_ONLY = True
BALANCED_AUCTION_RANGE_FIXED_LOT = 0.1
BALANCED_AUCTION_RANGE_LOOKBACK_BARS = 48
BALANCED_AUCTION_RANGE_MIN_WIDTH_ATR = 1.20
BALANCED_AUCTION_RANGE_MAX_WIDTH_ATR = 5.50
BALANCED_AUCTION_RANGE_EDGE_ZONE_PCT = 0.22
BALANCED_AUCTION_RANGE_NO_TRADE_MIDDLE_PCT = 0.40
BALANCED_AUCTION_RANGE_MIN_SCORE = 88
BALANCED_AUCTION_RANGE_DEFAULT_RR = 1.20
BALANCED_AUCTION_RANGE_MIN_STOP_DISTANCE_PRICE = 1.5
BALANCED_AUCTION_RANGE_MAX_STOP_DISTANCE_PRICE = 12.0
BALANCED_AUCTION_RANGE_MIN_TARGET_DISTANCE_PRICE = 4.0


# =========================
# PHASE 6B - VOLATILITY COMPRESSION BREAKOUT
# =========================
ENABLE_VOLATILITY_COMPRESSION_BREAKOUT = True

VCB_COMPRESSION_CANDLES = 8
VCB_ATR_CANDLES = 30
VCB_MAX_COMPRESSION_ATR_RATIO = 0.55
VCB_MAX_AVG_BODY_ATR_RATIO = 0.28
VCB_MIN_BREAKOUT_BODY_ATR_RATIO = 0.45
VCB_MIN_CLOSE_BEYOND_RANGE = 0.20
VCB_MAX_BREAKOUT_CHASE_ATR_RATIO = 1.80
VCB_MIN_RR = 2.0
VCB_TARGET_RR = 2.2
VCB_SL_BUFFER = 0.35
VCB_MAX_SL_DISTANCE = 7.0
VCB_MIN_SCORE = 94


# =========================
# PHASE 6C - PSYCHOLOGICAL ROUND NUMBER REJECTION
# =========================
ENABLE_PSYCH_ROUND_NUMBER_REJECTION = True

PSYCH_RNR_MAJOR_STEP = 50.0
PSYCH_RNR_MINOR_STEP = 25.0
PSYCH_RNR_USE_MINOR_LEVELS = True
PSYCH_RNR_LOOKBACK_BARS = 80
PSYCH_RNR_ATR_PERIOD = 14
PSYCH_RNR_MIN_WICK_ATR_RATIO = 0.35
PSYCH_RNR_MIN_BODY_ATR_RATIO = 0.18
PSYCH_RNR_MAX_CLOSE_DISTANCE_FROM_LEVEL = 1.20
PSYCH_RNR_MIN_REJECTION_DISTANCE = 0.40
PSYCH_RNR_SL_BUFFER = 0.35
PSYCH_RNR_MIN_RR = 2.0
PSYCH_RNR_TARGET_RR = 2.2
PSYCH_RNR_MAX_SL_DISTANCE = 7.0
PSYCH_RNR_MIN_SCORE = 94


# =========================
# PHASE 6D - SESSION EXHAUSTION REVERSAL
# =========================
ENABLE_SESSION_EXHAUSTION_REVERSAL = True

SER_LOOKBACK_BARS = 36
SER_ATR_PERIOD = 14
SER_MIN_MOVE_ATR_RATIO = 2.2
SER_MIN_EXTENSION_ATR_RATIO = 1.15
SER_MIN_WICK_ATR_RATIO = 0.35
SER_MIN_BODY_ATR_RATIO = 0.16
SER_CLOSE_REVERSAL_RATIO = 0.55
SER_SL_BUFFER = 0.35
SER_MIN_RR = 2.0
SER_TARGET_RR = 2.2
SER_MAX_SL_DISTANCE = 8.0
SER_MIN_SCORE = 94


# =========================
# PHASE 6E - AUTO KEY LEVEL TP LADDER
# =========================
ENABLE_KEY_LEVEL_TP_LADDER = True

KEY_LEVEL_TP_LADDER_STRATEGIES = {
    "SESSION_ORB_RETEST",
    "ORB",
    "KEY_LEVEL_BREAK_HOLD",
    "VOLATILITY_COMPRESSION_BREAKOUT",
    "PSYCH_ROUND_NUMBER_REJECTION",
    "SESSION_EXHAUSTION_REVERSAL",
    "MICRO_SR_SWEEP_RECLAIM",
    "HTF_REJECTION_CANDLE_MTF_ENTRY",
}

KLT_LOOKBACK_BARS = 120
KLT_SWING_WINDOW = 2
KLT_MIN_BARRIER_STRENGTH = 3
KLT_LEVEL_BUFFER_PRICE = 0.55
KLT_MIN_TP1_RR = 0.50
KLT_SET_EXECUTION_TP_TO_TP1 = True
KLT_ROUND_LEVEL_STEPS = [25.0, 50.0, 100.0]
KLT_MINOR_ROUND_LEVEL_STEPS = [5.0, 10.0]
KLT_MAX_BARRIER_DISTANCE_PRICE = 25.0


# =========================
# PHASE 6F - SPLIT TP LADDER EXECUTION
# =========================
ENABLE_TP_LADDER_SPLIT_EXECUTION = True
TP_LADDER_SPLIT_MAX_PARTS = 3
TP_LADDER_SPLIT_MIN_PARTS = 2
TP_LADDER_SPLIT_COMMENT_PREFIX = "TPLadder"


# =========================
# PHASE 6G - AUTO STRUCTURAL LEVEL SCALP
# =========================
ENABLE_AUTO_STRUCTURAL_LEVEL_SCALP = True
ASLS_USE_INTRABAR_CANDLE = True
ASLS_INTRABAR_ENTRY_TOLERANCE = 0.30
ASLS_INTRABAR_DUPLICATE_SECONDS = 180

ASLS_LOOKBACK_BARS = 160
ASLS_ATR_PERIOD = 14
ASLS_SWING_WINDOW = 2
ASLS_LEVEL_MERGE_DISTANCE = 1.25
ASLS_TOUCH_DISTANCE = 1.20
ASLS_ENTRY_PROXIMITY = 1.60
ASLS_MAX_ENTRY_DISTANCE_FROM_LEVEL = 0.50
ASLS_BOUNCE_ENTRY_OFFSET = 0.00
ASLS_BREAK_ENTRY_OFFSET = 0.50
ASLS_MAX_BREAK_ENTRY_LATE_DISTANCE = 0.25
ASLS_MIN_LEVEL_STRENGTH = 3
ASLS_MIN_RECLAIM_DISTANCE = 0.20
ASLS_MIN_WICK_ATR_RATIO = 0.22
ASLS_MIN_WICK_PRICE = 0.50
ASLS_MIN_BODY_ATR_RATIO = 0.10
ASLS_MIN_BODY_PRICE = 0.50
ASLS_BREAK_CONFIRM_DISTANCE = 0.50
ASLS_BREAK_CONFIRM_TOLERANCE = 0.20
ASLS_BREAK_BODY_ATR_RATIO = 0.18
ASLS_SL_BUFFER = 2.50
ASLS_TARGET_PRICE = 8.0
ASLS_MIN_TARGET_PRICE = 5.0
ASLS_MAX_TARGET_PRICE = 14.0
ASLS_MIN_RR = 1.0
ASLS_MIN_SCORE = 94
ASLS_ROUND_CONFLUENCE_STEPS = [5.0, 25.0, 50.0, 100.0]
ASLS_NY_SESSION_BOOST_ENABLED = True
ASLS_NY_START_HOUR = 15
ASLS_NY_END_HOUR = 22


# =========================
# PHASE 6K - HTF REJECTION CANDLE MTF ENTRY
# =========================
ENABLE_HTF_REJECTION_CANDLE_MTF_ENTRY = True

HRCM_HTF_AGGREGATION_BARS = 4          # 4 x M15 = H1 proxy
HRCM_LOOKBACK_HTF_BARS = 24
HRCM_EXTENSION_HTF_BARS = 3

HRCM_REQUIRE_LOCATION = True
HRCM_REQUIRE_EXTENSION = True
HRCM_REQUIRE_MTF_CONFIRMATION = True
HRCM_MTF_CONFIRMATION_BARS = 3

HRCM_LEVEL_PROXIMITY_PRICE = 2.0
HRCM_SWEEP_BUFFER_PRICE = 0.20
HRCM_MIN_EXTENSION_PRICE = 3.0

HRCM_MIN_WICK_RATIO = 0.55
HRCM_MAX_BODY_RATIO = 0.35
HRCM_CLOSE_LOCATION_RATIO = 0.60
HRCM_ENGULFING_MIN_BODY_RATIO = 0.40

HRCM_SL_BUFFER_PRICE = 0.60
HRCM_TARGET_RR = 2.20
HRCM_MIN_RR = 1.80
HRCM_MIN_SCORE = 94

HRCM_ENABLE_SHOOTING_STAR = True
HRCM_ENABLE_HAMMER = True
HRCM_ENABLE_BEARISH_ENGULFING = True
HRCM_ENABLE_BULLISH_ENGULFING = True

