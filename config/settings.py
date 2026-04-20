import os
import MetaTrader5 as mt5
from dotenv import load_dotenv

load_dotenv()

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
# Execution / Risk Settings
# =========================
POSITION_MODE = "fixed"   # "fixed" or "risk"
FIXED_LOT = 0.04
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
# Cooldown After SL Hit
# =========================
ENABLE_COOLDOWN_AFTER_SL = True
COOLDOWN_AFTER_SL_MINUTES = 5

# =========================
# Same Direction Entries
# =========================
ALLOW_SAME_DIRECTION_ENTRIES = True
MAX_SAME_DIRECTION_TRADES = 25  # main + extras = total max open same-side trades

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
MAIN_STAGE_2_LOCK_PRICE = 12.5

MAIN_STAGE_3_TRIGGER_PRICE = 24.5
MAIN_STAGE_3_CLOSE_PCT = 0.25
MAIN_STAGE_3_LOCK_PRICE = 16.0

# =========================
# Extra Entries Management (PRICE UNITS)
# =========================
ENABLE_EXTRA_ENTRY_MANAGEMENT = True

EXTRA_ENTRY_BREAK_EVEN_TRIGGER_PRICE = 3.0
EXTRA_ENTRY_LOCK_TRIGGER_PRICE = 4.0
EXTRA_ENTRY_LOCK_PRICE = 2.0
EXTRA_ENTRY_TAKE_PROFIT_PRICE = 5.5

# =========================
# Worst Extra Profit Lock (PRICE UNITS)
# =========================
ENABLE_WORST_EXTRA_LOCK = True
WORST_EXTRA_LOCK_TRIGGER_PRICE = 2.0
WORST_EXTRA_LOCK_PROFIT_PRICE = 1.0

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
# Per-Strategy Minimum Scores
# =========================
FAST_MIN_SCORE = 55
SNIPER_V2_MIN_SCORE = 70
FLAG_MIN_SCORE = 78
FLAG_REFINED_MIN_SCORE = 84
STRICT_MIN_SCORE = 85
LIQUIDITY_SWEEP_MIN_SCORE = 86


# =========================
# Adaptive Strategy Thresholds
# =========================
ENABLE_ADAPTIVE_THRESHOLDS = True

ADAPTIVE_MIN_TRADES = 10
ADAPTIVE_WINRATE_HIGH = 60.0
ADAPTIVE_WINRATE_LOW = 40.0

ADAPTIVE_SCORE_STEP = 3

FAST_BASE_MIN_SCORE = 55
SNIPER_V2_BASE_MIN_SCORE = 75
FLAG_BASE_MIN_SCORE = 78
FLAG_REFINED_BASE_MIN_SCORE = 84
LIQUIDITY_SWEEP_BASE_MIN_SCORE = 86
TRIANGLE_PENNANT_BASE_MIN_SCORE = 88
STRICT_BASE_MIN_SCORE = 90
HEAD_SHOULDERS_BASE_MIN_SCORE = 90

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
    "RANGING": +4,
    "VOLATILE": +6,
}