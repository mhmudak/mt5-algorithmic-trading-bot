from __future__ import annotations

from pathlib import Path

from src.order_flow_features.rithmic_anti_fakeout import (
    FuturesSpotBasisTracker,
    RithmicAntiFakeoutEngine,
    thresholds_for_session,
)


ROOT = Path(__file__).resolve().parents[1]


def snapshot(
    *,
    trade_count=30,
    total_volume=100,
    delta=40,
    cumulative_delta=200,
    flow_imbalance=0.40,
    footprint_imbalance=0.35,
    first_price=2400.0,
    last_price=2400.5,
    dom_imbalance=0.25,
    bid_depth=600,
    ask_depth=360,
    top_bid=2400.4,
    top_ask=2400.5,
    fresh=True,
):
    return {
        "freshness": {
            "has_fresh_trade": fresh,
            "has_fresh_bbo": fresh,
            "has_fresh_order_book": fresh,
        },
        "sample": {
            "rolling_trade_count": trade_count,
        },
        "trade_flow": {
            "rolling_total_volume": total_volume,
            "rolling_delta": delta,
            "session_cumulative_delta": cumulative_delta,
            "rolling_imbalance_ratio": flow_imbalance,
            "first_trade_price": first_price,
            "last_trade_price": last_price,
        },
        "adapter_compatible_metrics": {
            "footprint_imbalance": footprint_imbalance,
        },
        "footprint": {
            "candles": [
                {
                    "delta": delta,
                    "total_volume": total_volume,
                }
            ],
        },
        "order_book": {
            "available": True,
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "depth_imbalance": dom_imbalance,
            "top_bid_price": top_bid,
            "top_ask_price": top_ask,
        },
        "volume_profile": {
            "rolling_poc_price": 2400.3,
        },
    }


def test_confirmed_requires_flow_footprint_and_response():
    engine = RithmicAntiFakeoutEngine(tick_size=0.1)

    for _ in range(3):
        result = engine.update(
            snapshot(),
            signal="BUY",
            session="NEW_YORK_OPEN",
        )

    assert result["status"] == "CONFIRMED"
    assert result["flow_confirms_signal"] is True
    assert result["footprint_confirms_signal"] is True
    assert result["price_confirms_signal"] is True
    assert result["policy"]["dom_can_pass_alone"] is False


def test_dom_alone_never_confirms():
    engine = RithmicAntiFakeoutEngine(tick_size=0.1)

    for _ in range(4):
        result = engine.update(
            snapshot(
                trade_count=0,
                total_volume=0,
                delta=0,
                cumulative_delta=0,
                flow_imbalance=0.0,
                footprint_imbalance=0.0,
                first_price=2400.0,
                last_price=2400.0,
                dom_imbalance=0.80,
                bid_depth=900,
                ask_depth=100,
            ),
            signal="BUY",
            session="NEW_YORK_OPEN",
        )

    assert result["status"] == "DOM_ONLY_UNTRUSTED"
    assert result["dom_only_untrusted"] is True
    assert result["safe_for_execution"] is False


def test_absorption_against_buy():
    engine = RithmicAntiFakeoutEngine(tick_size=0.1)

    result = engine.update(
        snapshot(
            delta=60,
            flow_imbalance=0.60,
            footprint_imbalance=0.50,
            first_price=2400.0,
            last_price=2400.0,
        ),
        signal="BUY",
        session="NEW_YORK_OPEN",
    )

    assert result["status"] == "ABSORPTION_AGAINST"
    assert result["absorption_against_signal"] is True


def test_stale_blocks():
    engine = RithmicAntiFakeoutEngine(tick_size=0.1)

    result = engine.update(
        snapshot(fresh=False),
        signal="BUY",
        session="NEW_YORK_OPEN",
    )

    assert result["status"] == "STALE"
    assert result["freshness_gate"]["all_fresh"] is False


def test_spoof_risk_from_churn_and_flip():
    engine = RithmicAntiFakeoutEngine(tick_size=0.1)

    sequence = [
        snapshot(
            dom_imbalance=0.85,
            bid_depth=900,
            ask_depth=100,
            top_bid=2400.0,
            top_ask=2400.1,
            flow_imbalance=0.30,
        ),
        snapshot(
            dom_imbalance=-0.80,
            bid_depth=100,
            ask_depth=900,
            top_bid=2400.5,
            top_ask=2400.6,
            flow_imbalance=0.30,
        ),
        snapshot(
            dom_imbalance=0.90,
            bid_depth=1000,
            ask_depth=50,
            top_bid=2399.8,
            top_ask=2399.9,
            flow_imbalance=0.30,
        ),
    ]

    for item in sequence:
        result = engine.update(
            item,
            signal="BUY",
            session="NEW_YORK_OPEN",
        )

    assert result["spoof_risk"] is True
    assert result["status"] == "SPOOF_RISK"
    assert result["dom"]["depth_churn_ratio_proxy"] > 0


def test_basis_tracker_and_adjusted_poc():
    tracker = FuturesSpotBasisTracker(
        max_samples=10,
        min_samples=4,
        max_stdev=0.05,
    )

    for basis in (10.00, 10.02, 9.99, 10.01, 10.00):
        state = tracker.update(
            futures_mid=2400.0 + basis,
            xauusd_mid=2400.0,
        )

    assert state["stable"] is True

    engine = RithmicAntiFakeoutEngine(tick_size=0.1)
    result = engine.update(
        snapshot(),
        signal="BUY",
        session="NEW_YORK_OPEN",
        basis_state=state,
    )

    assert result["volume_profile"]["basis_adjusted_poc_xauusd"] is not None


def test_session_thresholds_are_distinct():
    ny = thresholds_for_session("NEW_YORK_OPEN")
    london = thresholds_for_session("LONDON_OPEN")
    asia = thresholds_for_session("ASIA")

    assert ny.min_trade_count > london.min_trade_count
    assert london.min_trade_count > asia.min_trade_count


def test_no_execution_authority_in_module():
    text = (
        ROOT
        / "src"
        / "order_flow_features"
        / "rithmic_anti_fakeout.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "CAN_INFLUENCE_DECISION = False" in text
    assert "SAFE_FOR_EXECUTION = False" in text
    assert "execute_trade(" not in text
    assert "order_send(" not in text


def main():
    test_confirmed_requires_flow_footprint_and_response()
    test_dom_alone_never_confirms()
    test_absorption_against_buy()
    test_stale_blocks()
    test_spoof_risk_from_churn_and_flip()
    test_basis_tracker_and_adjusted_poc()
    test_session_thresholds_are_distinct()
    test_no_execution_authority_in_module()

    print("PASS: CONFIRMED requires executed flow + footprint + price response")
    print("PASS: DOM alone can never confirm")
    print("PASS: absorption against setup is detected")
    print("PASS: stale data blocks confirmation")
    print("PASS: depth churn / flicker proxy can raise spoof risk")
    print("PASS: GC/MGC-to-XAU basis tracker gates price-level translation")
    print("PASS: session research thresholds are distinct")
    print("PASS: decision influence and execution remain disabled")


if __name__ == "__main__":
    main()
