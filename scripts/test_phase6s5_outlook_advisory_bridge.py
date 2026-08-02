
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.market_outlook_advisory_bridge import (
    advisory_fingerprint,
    build_outlook_advisory_bridge_result,
    mark_advisory_sent,
    setup_identity,
    should_send_advisory,
)


def sample_outlook():
    return {
        "symbol": "XAUUSD",
        "report_type": "SCENARIO_UPDATE",
        "fingerprint": "sample-outlook-fingerprint",
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


def sample_setup():
    return {
        "setup_id": "TEST-SELL-FCR",
        "strategy": "FCR_M1_FVG",
        "signal": "SELL",
        "entry_reference": 4043,
        "sl_reference": 4055,
        "tp_reference": 4010,
        "rr": 2.7,
    }


def test_setup_identity():
    identity = setup_identity(sample_setup())

    assert identity["setup_id"] == "TEST-SELL-FCR"
    assert identity["strategy"] == "FCR_M1_FVG"
    assert identity["direction"] == "SELL"
    assert identity["entry"] == 4043
    assert identity["sl"] == 4055
    assert identity["tp"] == 4010
    assert identity["rr"] == 2.7


def test_bridge_result_is_advisory_only():
    result = build_outlook_advisory_bridge_result(
        setup=sample_setup(),
        symbol="XAUUSD",
        report_type="scenario_update",
        outlook=sample_outlook(),
    )

    assert result["ready"] is True
    assert result["phase"] == "PHASE_6S5_OUTLOOK_ADVISORY_BRIDGE_CORE"
    assert result["risk_level"] == "HIGH"
    assert result["alignment"] == "AGAINST_OUTLOOK_LEADER"
    assert result["decision_impact"] == "ADVISORY_ONLY"
    assert result["auto_trade_allowed"] is False
    assert result["can_execute"] is False
    assert result["can_block_trade"] is False
    assert result["can_modify_risk"] is False
    assert "FINAL ADVISORY: HIGH RISK" in result["message"]
    assert "Execution: NO" in result["message"]


def test_fingerprint_is_stable_and_changes_with_setup():
    setup = sample_setup()
    outlook = sample_outlook()

    result = build_outlook_advisory_bridge_result(
        setup=setup,
        symbol="XAUUSD",
        report_type="scenario_update",
        outlook=outlook,
    )

    fp1 = advisory_fingerprint(setup=setup, outlook=outlook, advisory=result["advisory"])
    fp2 = advisory_fingerprint(setup=setup, outlook=outlook, advisory=result["advisory"])

    changed_setup = dict(setup)
    changed_setup["entry_reference"] = 4044

    fp3 = advisory_fingerprint(setup=changed_setup, outlook=outlook, advisory=result["advisory"])

    assert fp1 == fp2
    assert fp1 != fp3


def test_should_send_and_mark_sent():
    result = build_outlook_advisory_bridge_result(
        setup=sample_setup(),
        symbol="XAUUSD",
        report_type="scenario_update",
        outlook=sample_outlook(),
    )

    state = {"sent_fingerprints": {}}
    fingerprint = result["advisory_fingerprint"]

    assert should_send_advisory(state=state, fingerprint=fingerprint) is True

    state = mark_advisory_sent(
        state=state,
        fingerprint=fingerprint,
        result=result,
        sent_at="2026-08-03T00:00:00+03:00",
    )

    assert should_send_advisory(state=state, fingerprint=fingerprint) is False
    assert should_send_advisory(state=state, fingerprint=fingerprint, force_send=True) is True


if __name__ == "__main__":
    test_setup_identity()
    test_bridge_result_is_advisory_only()
    test_fingerprint_is_stable_and_changes_with_setup()
    test_should_send_and_mark_sent()
    print("[PASS] Phase 6S5 outlook advisory bridge passed.")
