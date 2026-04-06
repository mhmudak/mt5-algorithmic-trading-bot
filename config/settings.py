import MetaTrader5 as mt5

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

MAX_TRADES_PER_DAY = 3
MAX_ALLOWED_SPREAD = 0.50

EXECUTION_MODE = "SIMULATION"  # SIMULATION or LIVE

# =========================
# Bot Safety Settings
# =========================
ALLOW_LIVE_TRADING = False
ENABLE_TELEGRAM_ALERTS = False