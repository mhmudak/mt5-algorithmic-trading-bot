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
MAX_SAME_DIRECTION_TRADES = 5  # main + extras = total max open same-side trades

# =========================
# Runtime / Safety
# =========================
EXECUTION_MODE = "LIVE"  # SIMULATION or LIVE
ALLOW_LIVE_TRADING = True
ENABLE_TELEGRAM_ALERTS = False
FORCE_SIGNAL = None  # "BUY", "SELL", or None or BOTH

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

MAIN_STAGE_1_TRIGGER_PRICE = 6.5
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
EXTRA_ENTRY_LOCK_TRIGGER_PRICE = 5.0
EXTRA_ENTRY_LOCK_PRICE = 2.0
EXTRA_ENTRY_TAKE_PROFIT_PRICE = 8.0

# =========================
# Worst Extra Profit Lock (PRICE UNITS)
# =========================
ENABLE_WORST_EXTRA_LOCK = True
WORST_EXTRA_LOCK_TRIGGER_PRICE = 5.0
WORST_EXTRA_LOCK_PROFIT_PRICE = 3.0

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
MAX_DRAWDOWN_USD = 75.0




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
ENABLE_REVERSAL_MODE = True
REVERSAL_CONFIRMATION_CANDLES = 2
ENABLE_REVERSAL_ALERTS = True
REVERSAL_MIN_SCORE = 60


# =========================
# Smart Structure TP/SL
# =========================
USE_STRUCTURE_TAKE_PROFIT = True

STOP_EXTRA_BUFFER_PRICE = 5.0   # move SL farther behind structure
TP_EARLY_BUFFER_PRICE = 3.0     # take profit earlier before structure target