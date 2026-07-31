
from datetime import datetime, timedelta
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategies.strategy_htf_inside_bar_fakeout_mtf_entry import generate_signal


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


def test_upside_fakeout_sell():
    htf = [
        (4070, 4075, 4068, 4073),
        (4073, 4079, 4072, 4078),
        (4078, 4085, 4077, 4083),
        (4083, 4090, 4082, 4088),
        (4088, 4098, 4087, 4096),
        (4092, 4100, 4087, 4098),  # mother bar at resistance
        (4098, 4097, 4090, 4094),  # inside bar
        (4096, 4104, 4088, 4091),  # upside fakeout close back inside
    ]

    signal = generate_signal(expand_htf_bars_to_m15(htf))

    assert signal is not None
    assert signal["strategy"] == "HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY"
    assert signal["signal"] == "SELL"
    assert signal["entry_model"] == "MOTHER_BAR_UPSIDE_FAKEOUT_SELL"
    assert signal["score"] >= 94
    assert signal["sl_reference"] > signal["entry_reference"]
    assert signal["tp_reference"] < signal["entry_reference"]


def test_downside_fakeout_buy():
    htf = [
        (4100, 4102, 4095, 4097),
        (4097, 4098, 4090, 4093),
        (4093, 4095, 4085, 4088),
        (4088, 4090, 4080, 4084),
        (4084, 4086, 4072, 4077),
        (4078, 4085, 4070, 4073),  # mother bar at support
        (4073, 4080, 4072, 4076),  # inside bar
        (4074, 4086, 4065, 4081),  # downside fakeout close back inside
    ]

    signal = generate_signal(expand_htf_bars_to_m15(htf))

    assert signal is not None
    assert signal["strategy"] == "HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY"
    assert signal["signal"] == "BUY"
    assert signal["entry_model"] == "MOTHER_BAR_DOWNSIDE_FAKEOUT_BUY"
    assert signal["score"] >= 94
    assert signal["sl_reference"] < signal["entry_reference"]
    assert signal["tp_reference"] > signal["entry_reference"]


def test_no_inside_bar_rejected():
    htf = [
        (4070, 4075, 4068, 4073),
        (4073, 4079, 4072, 4078),
        (4078, 4085, 4077, 4083),
        (4083, 4090, 4082, 4088),
        (4088, 4098, 4087, 4096),
        (4092, 4100, 4087, 4098),  # mother
        (4098, 4102, 4085, 4094),  # not inside
        (4096, 4104, 4088, 4091),
    ]

    signal = generate_signal(expand_htf_bars_to_m15(htf))

    assert signal is None


if __name__ == "__main__":
    test_upside_fakeout_sell()
    test_downside_fakeout_buy()
    test_no_inside_bar_rejected()
    print("[PASS] Phase 6L HTF inside bar fakeout MTF entry tests passed.")
