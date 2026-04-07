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
ATR_MIN = 5.0
ATR_MAX = 50.0
BREAKOUT_LOOKBACK = 10
BREAKOUT_BUFFER = 0.20

# =========================
# Execution / Risk Settings
# =========================
POSITION_MODE = "fixed"   # "fixed" or "risk"
FIXED_LOT = 0.01
RISK_PER_TRADE_PCT = 0.25

STOP_LOSS_ATR_MULTIPLIER = 1.5
TAKE_PROFIT_R_MULTIPLIER = 2.0

MAX_TRADES_PER_DAY = 30
MAX_ALLOWED_SPREAD = 0.50

EXECUTION_MODE = "LIVE"  # SIMULATION or LIVE

# =========================
# Bot Safety Settings
# =========================
ALLOW_LIVE_TRADING = True
ENABLE_TELEGRAM_ALERTS = False

TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "False").lower() == "true"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

FORCE_SIGNAL = "BUY"  # "BUY", "SELL", or None

COOLDOWN_MINUTES = 1

MAX_SPREAD = 0.5      # adjust later (gold typical ~0.1–0.3)
MAX_SLIPPAGE = 0.3    # max acceptable difference

# =========================
# Position Management
# =========================
ENABLE_BREAK_EVEN = True
BREAK_EVEN_TRIGGER = 5.0

ENABLE_TRAILING_STOP = True
TRAILING_STOP_DISTANCE = 3.0