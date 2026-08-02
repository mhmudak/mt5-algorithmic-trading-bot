
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.market_outlook_advisory_runtime import (
    build_runtime_outlook_advisory,
    maybe_send_runtime_outlook_advisory,
    normalize_signal_setup_for_outlook_advisory,
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


def raw_live_like_setup():
    return {
        "id": "LIVE-LIKE-SELL-1",
        "strategy_name": "FCR_M1_FVG",
        "direction": "sell",
        "entry_price": 4043,
        "stop_loss": 4055,
        "take_profit": 4010,
        "risk_reward": 2.7,
    }


def test_normalize_live_like_setup():
    setup = normalize_signal_setup_for_outlook_advisory(raw_live_like_setup())

    assert setup["setup_id"] == "LIVE-LIKE-SELL-1"
    assert setup["strategy"] == "FCR_M1_FVG"
    assert setup["signal"] == "SELL"
    assert setup["entry_reference"] == 4043
    assert setup["sl_reference"] == 4055
    assert setup["tp_reference"] == 4010
    assert setup["rr"] == 2.7


def test_runtime_build_is_advisory_only():
    result = build_runtime_outlook_advisory(
        raw_setup=raw_live_like_setup(),
        symbol="XAUUSD",
        report_type="scenario_update",
        outlook=sample_outlook(),
    )

    assert result["ready"] is True
    assert result["runtime_phase"] == "PHASE_6S6_OUTLOOK_ADVISORY_RUNTIME_HOOK"
    assert result["risk_level"] == "HIGH"
    assert result["alignment"] == "AGAINST_OUTLOOK_LEADER"
    assert result["decision_impact"] == "ADVISORY_ONLY"
    assert result["auto_trade_allowed"] is False
    assert result["can_execute"] is False
    assert result["can_block_trade"] is False
    assert result["can_modify_risk"] is False
    assert "- Alignment: AGAINST_OUTLOOK_LEADER" in result["message"]
    assert "Execution: NO" in result["message"]


def test_disabled_runtime_does_not_send():
    calls = []

    def fake_notifier(message: str) -> bool:
        calls.append(message)
        return True

    summary = maybe_send_runtime_outlook_advisory(
        raw_setup=raw_live_like_setup(),
        symbol="XAUUSD",
        report_type="scenario_update",
        enabled=False,
        send_telegram=True,
        force_send=True,
        notifier=fake_notifier,
        outlook=sample_outlook(),
        state={"sent_fingerprints": {}},
        persist_state=False,
    )

    assert summary["ready"] is True
    assert summary["enabled"] is False
    assert summary["telegram_sent"] is False
    assert summary["reason"] == "runtime_advisory_disabled"
    assert calls == []


def test_enabled_runtime_sends_once_then_dedupes():
    calls = []
    state = {"sent_fingerprints": {}}

    def fake_notifier(message: str) -> bool:
        calls.append(message)
        return True

    first = maybe_send_runtime_outlook_advisory(
        raw_setup=raw_live_like_setup(),
        symbol="XAUUSD",
        report_type="scenario_update",
        enabled=True,
        send_telegram=True,
        force_send=False,
        notifier=fake_notifier,
        outlook=sample_outlook(),
        state=state,
        persist_state=False,
    )

    assert first["should_notify"] is True
    assert first["telegram_sent"] is True
    assert len(calls) == 1

    second = maybe_send_runtime_outlook_advisory(
        raw_setup=raw_live_like_setup(),
        symbol="XAUUSD",
        report_type="scenario_update",
        enabled=True,
        send_telegram=True,
        force_send=False,
        notifier=fake_notifier,
        outlook=sample_outlook(),
        state=state,
        persist_state=False,
    )

    assert second["should_notify"] is False
    assert second["telegram_sent"] is False
    assert second["reason"] == "duplicate_advisory_fingerprint"
    assert len(calls) == 1


if __name__ == "__main__":
    test_normalize_live_like_setup()
    test_runtime_build_is_advisory_only()
    test_disabled_runtime_does_not_send()
    test_enabled_runtime_sends_once_then_dedupes()
    print("[PASS] Phase 6S6 outlook advisory runtime hook passed.")
