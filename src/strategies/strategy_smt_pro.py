import MetaTrader5 as mt5
import pandas as pd

from src.indicators import calculate_ema, calculate_atr
from src.logger import logger
from config.settings import (
    SYMBOL,
    EMA_PERIOD,
    ATR_PERIOD,
    ATR_MIN,
    ATR_MAX,
    ENABLE_EXTERNAL_SMT,
    SMT_CONFIRMATION_SYMBOL,
    SMT_LOOKBACK_BARS,
    TIMEFRAME,
)


def _fetch_symbol_df(symbol: str, bars: int):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, bars)
    if rates is None:
        logger.error(f"[SMT PRO] Failed to fetch rates for {symbol}: {mt5.last_error()}")
        return None

    df = pd.DataFrame(rates)
    if df.empty:
        return None

    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ema_20"] = calculate_ema(df, EMA_PERIOD)
    df["atr_14"] = calculate_atr(df, ATR_PERIOD)
    return df


def generate_signal(df):
    if not ENABLE_EXTERNAL_SMT:
        return None

    if len(df) < SMT_LOOKBACK_BARS + 5:
        return None

    confirm_df = _fetch_symbol_df(SMT_CONFIRMATION_SYMBOL, len(df))
    if confirm_df is None or len(confirm_df) < SMT_LOOKBACK_BARS + 5:
        return None

    # align lengths conservatively
    min_len = min(len(df), len(confirm_df))
    df = df.iloc[-min_len:].reset_index(drop=True)
    confirm_df = confirm_df.iloc[-min_len:].reset_index(drop=True)

    entry = df.iloc[-2]
    confirm_entry = confirm_df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    main_high_1 = df.iloc[-(SMT_LOOKBACK_BARS + 5):-5]["high"].max()
    main_high_2 = df.iloc[-5:]["high"].max()

    main_low_1 = df.iloc[-(SMT_LOOKBACK_BARS + 5):-5]["low"].min()
    main_low_2 = df.iloc[-5:]["low"].min()

    conf_high_1 = confirm_df.iloc[-(SMT_LOOKBACK_BARS + 5):-5]["high"].max()
    conf_high_2 = confirm_df.iloc[-5:]["high"].max()

    conf_low_1 = confirm_df.iloc[-(SMT_LOOKBACK_BARS + 5):-5]["low"].min()
    conf_low_2 = confirm_df.iloc[-5:]["low"].min()

    body = abs(entry["close"] - entry["open"])

    # =========================================================
    # Bearish SMT PRO
    # XAU makes higher high, XAG does NOT confirm
    # =========================================================
    main_higher_high = main_high_2 > main_high_1
    confirm_no_higher_high = conf_high_2 <= conf_high_1

    bearish_rejection = (
        entry["high"] >= main_high_2
        and entry["close"] < entry["open"]
        and entry["close"] < entry["high"] - atr * 0.2
    )

    bearish_context = price < ema
    bearish_momentum = body > atr * 0.2

    if (
        main_higher_high
        and confirm_no_higher_high
        and bearish_rejection
        and bearish_context
        and bearish_momentum
    ):
        pattern_height = abs(main_high_2 - main_low_2)

        return {
            "signal": "SELL",
            "score": 95,
            "strategy": "SMT_PRO",
            "pattern_height": pattern_height,
            "main_high_1": main_high_1,
            "main_high_2": main_high_2,
            "confirm_high_1": conf_high_1,
            "confirm_high_2": conf_high_2,
            "reason": (
                f"SMT PRO bearish -> {SYMBOL} made higher high {round(main_high_2,2)} "
                f"while {SMT_CONFIRMATION_SYMBOL} failed to confirm ({round(conf_high_1,2)} vs {round(conf_high_2,2)}) "
                f"-> bearish rejection -> price below EMA"
            ),
        }

    # =========================================================
    # Bullish SMT PRO
    # XAU makes lower low, XAG does NOT confirm
    # =========================================================
    main_lower_low = main_low_2 < main_low_1
    confirm_no_lower_low = conf_low_2 >= conf_low_1

    bullish_rejection = (
        entry["low"] <= main_low_2
        and entry["close"] > entry["open"]
        and entry["close"] > entry["low"] + atr * 0.2
    )

    bullish_context = price > ema
    bullish_momentum = body > atr * 0.2

    if (
        main_lower_low
        and confirm_no_lower_low
        and bullish_rejection
        and bullish_context
        and bullish_momentum
    ):
        pattern_height = abs(main_high_2 - main_low_2)

        return {
            "signal": "BUY",
            "score": 95,
            "strategy": "SMT_PRO",
            "pattern_height": pattern_height,
            "main_low_1": main_low_1,
            "main_low_2": main_low_2,
            "confirm_low_1": conf_low_1,
            "confirm_low_2": conf_low_2,
            "reason": (
                f"SMT PRO bullish -> {SYMBOL} made lower low {round(main_low_2,2)} "
                f"while {SMT_CONFIRMATION_SYMBOL} failed to confirm ({round(conf_low_1,2)} vs {round(conf_low_2,2)}) "
                f"-> bullish rejection -> price above EMA"
            ),
        }

    return None