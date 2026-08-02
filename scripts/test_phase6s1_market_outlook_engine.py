
from datetime import datetime
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.send_phase6s_market_outlook import ensure_likely_scenarios_heading

from src.market_outlook_engine import (
    build_market_outlook,
    format_market_outlook_telegram,
    outlook_changed,
)


def make_frame(start_price: float, rows: int, drift: float) -> pd.DataFrame:
    data = []
    price = start_price

    for i in range(rows):
        open_price = price
        close_price = price + drift
        high = max(open_price, close_price) + 1.5
        low = min(open_price, close_price) - 1.5

        data.append(
            {
                "time": pd.Timestamp("2026-01-01") + pd.Timedelta(hours=i),
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close_price, 2),
                "tick_volume": 100 + i,
            }
        )

        price = close_price

    return pd.DataFrame(data)


def make_m15_frame(start_price: float, rows: int, drift: float) -> pd.DataFrame:
    data = []
    price = start_price

    start = pd.Timestamp("2026-08-01 00:00:00")

    for i in range(rows):
        open_price = price
        close_price = price + drift
        high = max(open_price, close_price) + 0.8
        low = min(open_price, close_price) - 0.8

        data.append(
            {
                "time": start + pd.Timedelta(minutes=15 * i),
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close_price, 2),
                "tick_volume": 100 + i,
            }
        )

        price = close_price

    return pd.DataFrame(data)


def test_build_outlook():
    frames = {
        "W1": make_frame(3900, 120, 0.7),
        "D1": make_frame(3950, 180, 0.5),
        "H4": make_frame(4000, 240, 0.25),
        "H1": make_frame(4040, 240, 0.1),
        "M15": make_m15_frame(4040, 700, 0.03),
    }

    outlook = build_market_outlook(
        frames,
        report_type="daily",
        symbol="XAUUSD",
        generated_at=datetime(2026, 8, 3, 8, 0, 0),
    )

    assert outlook["phase"] == "PHASE_6S1_HTF_MARKET_OUTLOOK"
    assert outlook["report_type"] == "DAILY"
    assert outlook["symbol"] == "XAUUSD"
    assert outlook["decision_impact"] == "NONE"
    assert outlook["auto_trade_allowed"] is False
    assert outlook["can_execute"] is False
    assert outlook["can_influence_decision"] is False
    assert outlook["combined_htf_bias"] in {"BULLISH", "MIXED_BULLISH", "MIXED", "MIXED_BEARISH", "BEARISH"}
    assert outlook["levels"]["H1"]["support"] is not None
    assert outlook["levels"]["H1"]["resistance"] is not None
    assert outlook["session_liquidity"]["status"] == "AVAILABLE"
    assert outlook["session_liquidity"]["sessions"]["ASIA"]["high"] is not None
    assert outlook["session_liquidity"]["sessions"]["LONDON"]["low"] is not None
    assert outlook["session_liquidity"]["sessions"]["NEWYORK"]["high"] is not None
    assert outlook["session_liquidity"]["previous_day"]["high"] is not None
    assert outlook["nearest_liquidity"]["buy"] is not None
    assert outlook["nearest_liquidity"]["sell"] is not None
    assert outlook["scenario_maturity"]["BUY"]["score"] >= 0
    assert outlook["scenario_maturity"]["SELL"]["score"] >= 0
    assert outlook["scenario_maturity"]["leader"] in {"BUY", "SELL", "BALANCED"}
    assert len(outlook["likely_scenarios"]) == 3
    assert "maturity_score" in outlook["likely_scenarios"][0]
    assert "action_state" in outlook["likely_scenarios"][0]
    assert outlook["likely_scenarios"][0]["can_become_setup"] is True
    assert outlook["likely_scenarios"][2]["can_become_setup"] is False
    assert outlook["news_filter"]["status"] == "MANUAL_REVIEW_REQUIRED"
    assert outlook["fingerprint"]

    message = format_market_outlook_telegram(outlook)

    assert "DAILY HTF MARKET OUTLOOK" in message
    assert "Likely Scenarios:" in message
    assert "\nLikely Scenarios:\n1. " in message
    assert message.index("Likely Scenarios:") < message.index("1. ")
    assert "Session Liquidity:" in message
    assert "Asia High/Low:" in message
    assert "London High/Low:" in message
    assert "New York High/Low:" in message
    assert "Previous Day High/Low:" in message
    assert "Scenario Closer:" in message
    assert "Scenario Leader:" in message
    assert "BUY Maturity:" in message
    assert "SELL Maturity:" in message
    assert "Action State:" in message
    assert "\nLikely Scenarios:\n1. Support sweep" in message
    assert "Decision Impact: NONE" in message
    assert "Execution: NO" in message
    assert "\nLikely Scenarios:\n1. Support sweep" in message, repr(message)
    assert "Likely Scenarios:" in message
    assert message.count("Likely Scenarios:") == 1
    assert "\nLikely Scenarios:\n1. Support sweep" in message
    assert "\nLikely Scenarios:\n\n1. " not in message
    assert "\nLikely Scenarios:\n1. Support sweep" in message
    assert "\nLikely Scenarios:\n\n1. " not in message

    same = dict(outlook)
    assert outlook_changed(outlook, same) is False

    changed = dict(outlook)
    changed["fingerprint"] = "different"
    assert outlook_changed(outlook, changed) is True


def test_send_script_heading_guard():
    raw = "Header\n\n1. Support sweep and reclaim [BUY]\nFooter"
    fixed = ensure_likely_scenarios_heading(raw)

    assert "\nLikely Scenarios:\n1. Support sweep" in fixed
    assert fixed.count("Likely Scenarios:") == 1

    fixed_again = ensure_likely_scenarios_heading(fixed)
    assert fixed_again.count("Likely Scenarios:") == 1


if __name__ == "__main__":
    test_build_outlook()
    test_send_script_heading_guard()
    print("[PASS] Phase 6S1 market outlook engine passed.")
