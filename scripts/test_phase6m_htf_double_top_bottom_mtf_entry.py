
from datetime import datetime, timedelta
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.strategies.strategy_htf_double_top_bottom_mtf_entry import generate_signal


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


def test_double_top_neckline_retest_sell():
    htf = [
        (4070, 4076, 4068, 4074),
        (4074, 4085, 4072, 4082),
        (4082, 4100, 4080, 4096),  # first top
        (4096, 4098, 4078, 4082),  # neckline trough 4078
        (4082, 4092, 4080, 4088),
        (4088, 4101, 4086, 4095),  # second top near first top
        (4095, 4097, 4072, 4074),  # break below neckline
        (4075, 4080, 4068, 4073),  # retest neckline from below + bearish close
    ]

    signal = generate_signal(expand_htf_bars_to_m15(htf))

    assert signal is not None
    assert signal["strategy"] == "HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY"
    assert signal["signal"] == "SELL"
    assert signal["entry_model"] == "DOUBLE_TOP_NECKLINE_RETEST_SELL"
    assert signal["score"] >= 94
    assert signal["sl_reference"] > signal["entry_reference"]
    assert signal["tp_reference"] < signal["entry_reference"]


def test_double_bottom_neckline_retest_buy():
    htf = [
        (4100, 4102, 4092, 4095),
        (4095, 4098, 4085, 4088),
        (4088, 4090, 4070, 4075),  # first bottom
        (4075, 4096, 4074, 4092),  # neckline high 4096
        (4092, 4094, 4080, 4086),
        (4086, 4090, 4069, 4076),  # second bottom near first bottom
        (4076, 4102, 4075, 4099),  # break above neckline
        (4098, 4105, 4094, 4101),  # retest neckline from above + bullish close
    ]

    signal = generate_signal(expand_htf_bars_to_m15(htf))

    assert signal is not None
    assert signal["strategy"] == "HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY"
    assert signal["signal"] == "BUY"
    assert signal["entry_model"] == "DOUBLE_BOTTOM_NECKLINE_RETEST_BUY"
    assert signal["score"] >= 94
    assert signal["sl_reference"] < signal["entry_reference"]
    assert signal["tp_reference"] > signal["entry_reference"]


def test_no_break_retest_rejected():
    htf = [
        (4070, 4076, 4068, 4074),
        (4074, 4085, 4072, 4082),
        (4082, 4100, 4080, 4096),
        (4096, 4098, 4078, 4082),
        (4082, 4092, 4080, 4088),
        (4088, 4101, 4086, 4095),
        (4095, 4097, 4080, 4084),  # no real break below neckline
        (4085, 4089, 4081, 4087),
    ]

    signal = generate_signal(expand_htf_bars_to_m15(htf))

    assert signal is None


if __name__ == "__main__":
    test_double_top_neckline_retest_sell()
    test_double_bottom_neckline_retest_buy()
    test_no_break_retest_rejected()
    print("[PASS] Phase 6M HTF double top/bottom neckline break-retest tests passed.")
