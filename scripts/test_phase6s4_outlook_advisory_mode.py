
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.market_outlook_advisor import (
    evaluate_setup_against_outlook,
    format_outlook_advisory_telegram,
)


def sample_outlook():
    return {
        "symbol": "XAUUSD",
        "report_type": "SCENARIO_UPDATE",
        "last_price": 4043.77,
        "combined_htf_bias": "BEARISH",
        "range_zone": "DISCOUNT_SUPPORT_SIDE",
        "scenario_closer": "BUY_SCENARIO_CLOSER_NEAR_LONDON_LOW",
        "scenario_maturity": {
            "leader": "BUY",
            "BUY": {"score": 67, "state": "APPROACHING"},
            "SELL": {"score": 53, "state": "APPROACHING"},
        },
        "nearest_liquidity": {
            "buy": {"label": "LONDON_LOW", "price": 4050.31, "distance": 6.54},
            "sell": {"label": "NEWYORK_HIGH", "price": 4059.43, "distance": 15.66},
        },
    }


def test_buy_aligned_but_bias_warning():
    setup = {
        "setup_id": "TEST-BUY",
        "strategy": "MICRO_SR_SWEEP_RECLAIM",
        "signal": "BUY",
        "entry_reference": 4045,
        "sl_reference": 4035,
        "tp_reference": 4070,
        "rr": 2.5,
    }

    advisory = evaluate_setup_against_outlook(setup, sample_outlook())

    assert advisory["alignment"] == "ALIGNED_WITH_OUTLOOK_LEADER"
    assert advisory["risk_level"] in {"LOW", "MEDIUM", "HIGH"}
    assert advisory["decision_impact"] == "ADVISORY_ONLY"
    assert advisory["auto_trade_allowed"] is False
    assert advisory["can_execute"] is False
    assert advisory["can_block_trade"] is False

    message = format_outlook_advisory_telegram(advisory)

    assert "OUTLOOK ADVISORY" in message
    assert "MANUAL REVIEW" in message
    assert "Decision Impact: ADVISORY ONLY" in message
    assert "Execution: NO" in message


def test_sell_against_outlook_is_high_risk():
    setup = {
        "setup_id": "TEST-SELL",
        "strategy": "FCR_M1_FVG",
        "signal": "SELL",
        "entry_reference": 4043,
        "sl_reference": 4055,
        "tp_reference": 4010,
        "rr": 2.7,
    }

    advisory = evaluate_setup_against_outlook(setup, sample_outlook())

    assert advisory["alignment"] == "AGAINST_OUTLOOK_LEADER"
    assert advisory["risk_level"] == "HIGH"
    assert any("opposite outlook leader" in item for item in advisory["warnings"])
    assert any("SELL setup is in discount/support side" in item for item in advisory["warnings"])

    message = format_outlook_advisory_telegram(advisory)

    assert "Risk: HIGH" in message
    assert "- Alignment: AGAINST_OUTLOOK_LEADER" in message
    assert "Warnings:" in message
    assert "AVOID BLIND ENTRY" in message
    assert "Can Block Trade: False" in message
    assert "FINAL ADVISORY:" in message
    assert "MANUAL ACTION:" in message
    assert "Setup: SELL FCR_M1_FVG" in message
    assert "Outlook Match:" in message
    assert "Risk Warnings:" in message
    assert "Required Before Any Manual Entry:" in message
    assert "Clear Meaning:" in message


if __name__ == "__main__":
    test_buy_aligned_but_bias_warning()
    test_sell_against_outlook_is_high_risk()
    print("[PASS] Phase 6S4 outlook advisory mode passed.")
