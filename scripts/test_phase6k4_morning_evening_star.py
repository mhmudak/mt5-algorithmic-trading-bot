
from datetime import datetime, timedelta
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategies.strategy_htf_rejection_candle_mtf_entry import generate_signal


def expand_htf_bars_to_m15(htf_bars):
    rows = []
    t = datetime(2026, 7, 31, 0, 0)

    for bar in htf_bars:
        open_price, high, low, close = bar

        mids = [
            open_price,
            (open_price + close) / 2,
            (open_price + close) / 2,
            close,
        ]

        for i in range(4):
            rows.append(
                {
                    "time": t,
                    "open": open_price if i == 0 else mids[i - 1],
                    "high": high if i == 3 else max(mids[max(i - 1, 0)], mids[i]) + 0.25,
                    "low": low if i == 3 else min(mids[max(i - 1, 0)], mids[i]) - 0.25,
                    "close": mids[i],
                }
            )
            t += timedelta(minutes=15)

    return pd.DataFrame(rows)


def test_evening_star_sell():
    htf = [
        (4070, 4075, 4068, 4073),
        (4073, 4079, 4072, 4078),
        (4078, 4085, 4077, 4083),
        (4083, 4090, 4082, 4088),
        (4088, 4094, 4087, 4092),
        (4092, 4100, 4091, 4098),  # first: strong bullish
        (4098, 4106, 4097, 4099),  # middle: small body at resistance
        (4100, 4104, 4088, 4092),  # third: bearish close below midpoint
    ]

    signal = generate_signal(expand_htf_bars_to_m15(htf))

    assert signal is not None
    assert signal["signal"] == "SELL"
    assert signal["entry_model"] == "EVENING_STAR"
    assert signal["score"] >= 94
    assert signal["sl_reference"] > signal["entry_reference"]
    assert signal["tp_reference"] < signal["entry_reference"]


def test_morning_star_buy():
    htf = [
        (4100, 4102, 4095, 4097),
        (4097, 4098, 4090, 4093),
        (4093, 4095, 4085, 4088),
        (4088, 4090, 4080, 4084),
        (4084, 4086, 4076, 4080),
        (4086, 4087, 4073, 4075),  # first: strong bearish
        (4074, 4077, 4067, 4073),  # middle: small body at support
        (4072, 4084, 4069, 4081),  # third: bullish close above midpoint
    ]

    signal = generate_signal(expand_htf_bars_to_m15(htf))

    assert signal is not None
    assert signal["signal"] == "BUY"
    assert signal["entry_model"] == "MORNING_STAR"
    assert signal["score"] >= 94
    assert signal["sl_reference"] < signal["entry_reference"]
    assert signal["tp_reference"] > signal["entry_reference"]


if __name__ == "__main__":
    test_evening_star_sell()
    test_morning_star_buy()
    print("[PASS] Phase 6K4 Morning/Evening Star HTF rejection tests passed.")
