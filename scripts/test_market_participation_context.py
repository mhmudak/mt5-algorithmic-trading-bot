from __future__ import annotations

import json
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.market_participation_context import (
    _reset_market_participation_state_for_tests,
    build_market_participation_context,
    build_market_participation_observation,
    claim_market_participation_high_impact_alert,
    classify_market_participation_alert,
    format_market_participation_high_impact_alert,
    format_market_participation_telegram_block,
    get_cached_rithmic_participation_context,
    log_market_participation_observation,
    record_mt5_tick,
    refresh_rithmic_participation_context,
)


class Tick:
    def __init__(self, epoch, bid, ask):
        self.time = int(epoch)
        self.time_msc = int(epoch * 1000)
        self.bid = bid
        self.ask = ask


class FakeRithmicProvider:
    def __init__(self, *, available=True, delta=20, imbalance=0.20, dom=0.10):
        self.available = available
        self.delta = delta
        self.imbalance = imbalance
        self.dom = dom

    def get_latest_snapshot(self, symbol):
        return {
            "provider": "RITHMIC_SNAPSHOT_PROVIDER",
            "symbol": "GC_TEST",
            "requested_symbol": symbol,
            "exchange": "COMEX",
            "available": self.available,
            "status": "OBSERVE_ONLY_READY" if self.available else "UNAVAILABLE",
            "data_quality": "REALTIME" if self.available else "UNAVAILABLE",
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "safe_for_execution": False,
            "metrics": {
                "bid_volume": 40,
                "ask_volume": 60,
                "delta": self.delta,
                "cumulative_delta": 125,
                "footprint_imbalance": self.imbalance,
                "dom_bid_depth": 120,
                "dom_ask_depth": 100,
                "dom_depth_imbalance": self.dom,
                "volume_profile_poc": 4000.0,
            },
            "rithmic_status": {
                "freshness": {
                    "snapshot_fresh": self.available,
                    "has_fresh_trade": self.available,
                }
            },
            "warning": "observe only",
        }


def _seed_buy_ticks():
    base = 1_800_000_000.0
    for i in range(8):
        bid = 4000.0 + i * 0.05
        ask = bid + 0.20
        assert record_mt5_tick(
            Tick(base + i * 0.5, bid, ask),
            observed_at_epoch=base + i * 0.5,
        )
    return base + 3.5


def test_cross_market_buy_alignment_is_research_only():
    _reset_market_participation_state_for_tests()
    now = _seed_buy_ticks()

    context = build_market_participation_context(
        symbol="XAUUSD",
        signal="BUY",
        provider=FakeRithmicProvider(),
        now_epoch=now,
    )

    assert context["combined_state"] == "CROSS_MARKET_BUY_ALIGNED"
    assert context["signal_relation"] == "WITH_SIGNAL"
    assert context["source_coverage"] == "MT5_PLUS_RITHMIC"
    assert context["identity_inference"] == "PARTICIPANT_IDENTITY_NOT_OBSERVABLE"
    assert context["decision_impact"] == "NONE"
    assert context["can_influence_decision"] is False
    assert context["safe_for_execution"] is False
    assert context["mt5"]["source"] == "MT5_BOT_LOOP_SAMPLED_QUOTES"
    assert context["rithmic"]["aggression_state"] == "BUY_AGGRESSION"


def test_rithmic_cache_can_be_refreshed_outside_execution_path():
    _reset_market_participation_state_for_tests()
    now = 1_800_000_100.0

    refreshed = refresh_rithmic_participation_context(
        symbol="XAUUSD",
        provider=FakeRithmicProvider(delta=-25, imbalance=-0.25, dom=-0.15),
        now_epoch=now,
    )

    assert refreshed["aggression_state"] == "SELL_AGGRESSION"

    cached = get_cached_rithmic_participation_context(
        symbol="XAUUSD",
        now_epoch=now + 1.0,
    )

    assert cached["available"] is True
    assert cached["cache_status"] == "FRESH_CACHE"
    assert cached["aggression_state"] == "SELL_AGGRESSION"

    stale = get_cached_rithmic_participation_context(
        symbol="XAUUSD",
        now_epoch=now + 10.0,
    )
    assert stale["available"] is False
    assert stale["status"] == "RITHMIC_CONTEXT_CACHE_MISSING_OR_STALE"


def test_observation_persistence_is_generic_not_intrabar_only():
    _reset_market_participation_state_for_tests()
    now = _seed_buy_ticks()
    context = build_market_participation_context(
        symbol="XAUUSD",
        signal="BUY",
        provider=FakeRithmicProvider(),
        now_epoch=now,
    )

    observation = build_market_participation_observation(
        context=context,
        capture_phase="SETUP_DETECTED_CLOSED_M15",
        event="SETUP_DETECTED",
        strategy="HTF_TREND_PULLBACK",
        setup_id="GENERIC-1",
        signal="BUY",
        entry_model="PULLBACK",
        session="NEWYORK",
        market_condition="TRENDING",
        trade_plan=None,
    )

    assert observation["strategy"] == "HTF_TREND_PULLBACK"
    assert observation["capture_phase"] == "SETUP_DETECTED_CLOSED_M15"
    assert observation["can_influence_decision"] is False

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "participation.jsonl"
        assert log_market_participation_observation(observation, file_path=path)
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 1
    assert rows[0]["setup_id"] == "GENERIC-1"
    assert rows[0]["participation_context"]["combined_state"] == "CROSS_MARKET_BUY_ALIGNED"



def _high_impact_mt5_context():
    return {
        "schema_version": 1,
        "symbol": "XAUUSD",
        "signal": "SELL",
        "identity_inference": (
            "PARTICIPANT_IDENTITY_NOT_OBSERVABLE"
        ),
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "source_coverage": "MT5_ONLY",
        "combined_state": (
            "MT5_ONLY_SELL_PRESSURE_PROXY"
        ),
        "signal_relation": "WITH_SIGNAL",
        "mt5": {
            "available": True,
            "source": (
                "MT5_BOT_LOOP_SAMPLED_QUOTES"
            ),
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "activity_state": (
                "ACCELERATING_QUOTE_ACTIVITY"
            ),
            "pressure_state": (
                "SELL_PRESSURE_PROXY"
            ),
            "quote_activity_acceleration_ratio": (
                1.85
            ),
            "current_spread": 0.20,
            "windows": {
                "5s": {
                    "sample_count": 9,
                    "observed_span_seconds": 4.0,
                    "mid_move": -1.25,
                    "directional_imbalance": -0.78,
                },
                "15s": {},
                "60s": {},
            },
        },
        "rithmic": {
            "available": False,
            "source": "RITHMIC",
            "status": (
                "RITHMIC_CONTEXT_CACHE_"
                "MISSING_OR_STALE"
            ),
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "safe_for_execution": False,
            "aggression_state": "UNAVAILABLE",
            "dom_state": "UNAVAILABLE",
        },
    }


def test_mt5_proxy_telegram_block_is_honest():
    context = _high_impact_mt5_context()

    block = (
        format_market_participation_telegram_block(
            context
        )
    )

    assert (
        "Market Participation — MT5 Proxy"
        in block
    )

    assert "Activity: ACCELERATING" in block
    assert "Pressure: SELL" in block
    assert "5s Imbalance: -0.78" in block
    assert "Signal Relation: WITH_SIGNAL" in block
    assert "Rithmic: UNAVAILABLE" in block
    assert "Mode: OBSERVE ONLY" in block

    # Never overclaim participant identity.
    assert "Institutional Confirmed" not in block
    assert "Bank Flow" not in block


def test_rithmic_formatter_auto_enriches_when_available():
    _reset_market_participation_state_for_tests()

    now = _seed_buy_ticks()

    context = build_market_participation_context(
        symbol="XAUUSD",
        signal="BUY",
        provider=FakeRithmicProvider(),
        now_epoch=now,
    )

    block = (
        format_market_participation_telegram_block(
            context
        )
    )

    assert (
        "Market Participation — MT5 + Rithmic"
        in block
    )

    assert (
        "Rithmic Aggression: BUY_AGGRESSION"
        in block
    )

    assert (
        "DOM: BID_DEPTH_DOMINANT"
        in block
    )


def test_high_impact_alert_is_notification_only():
    context = _high_impact_mt5_context()

    alert = (
        classify_market_participation_alert(
            context
        )
    )

    assert (
        alert["severity"]
        == "HIGH_IMPACT"
    )

    assert (
        alert[
            "should_notify_candidate"
        ]
        is True
    )

    assert (
        alert["direction"]
        == "SELL"
    )

    assert (
        alert["decision_impact"]
        == "NONE"
    )

    assert (
        alert[
            "can_influence_decision"
        ]
        is False
    )

    assert (
        alert[
            "safe_for_execution"
        ]
        is False
    )

    assert (
        alert[
            "execution_allowed"
        ]
        is False
    )

    message = (
        format_market_participation_high_impact_alert(
            context,
            alert,
        )
    )

    assert (
        "HIGH-IMPACT MARKET PARTICIPATION"
        in message
    )

    assert (
        "does NOT guarantee future price direction"
        in message
    )


def test_high_impact_same_direction_cooldown():
    _reset_market_participation_state_for_tests()

    context = _high_impact_mt5_context()

    first = (
        claim_market_participation_high_impact_alert(
            context,
            now_epoch=1000.0,
            cooldown_seconds=300.0,
        )
    )

    second = (
        claim_market_participation_high_impact_alert(
            context,
            now_epoch=1001.0,
            cooldown_seconds=300.0,
        )
    )

    later = (
        claim_market_participation_high_impact_alert(
            context,
            now_epoch=1301.0,
            cooldown_seconds=300.0,
        )
    )

    assert (
        first["should_notify"]
        is True
    )

    assert (
        second["should_notify"]
        is False
    )

    assert (
        second[
            "notification_reason"
        ]
        == "same_direction_cooldown_active"
    )

    assert (
        later["should_notify"]
        is True
    )


def test_live_notifications_surface_context_without_authority():
    live_source = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    risk_source = (
        ROOT
        / "src"
        / "risk.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    execution_source = (
        ROOT
        / "src"
        / "execution_engine.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    recovery_source = (
        ROOT
        / "src"
        / "candidate_rejection_recovery.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    # Definition + five lifecycle notification uses.
    assert (
        live_source.count(
            "_market_participation_telegram_"
            "block_fail_open("
        )
        == 6
    )

    # Definition + cycle-level invocation.
    assert (
        live_source.count(
            "_notify_market_participation_"
            "high_impact_fail_open("
        )
        == 2
    )

    assert (
        "cycle_participation_context"
        in live_source
    )

    assert (
        "SETUP DETECTED"
        in live_source
    )

    assert (
        "STRONG MTF CONFLICT TRACKED"
        in live_source
    )

    assert (
        "Candidate Rejected"
        in live_source
    )

    for source in (
        risk_source,
        execution_source,
        recovery_source,
    ):
        assert (
            "format_market_participation_"
            "telegram_block"
            not in source
        )

        assert (
            "claim_market_participation_"
            "high_impact_alert"
            not in source
        )


if __name__ == "__main__":
    test_cross_market_buy_alignment_is_research_only()
    test_rithmic_cache_can_be_refreshed_outside_execution_path()
    test_observation_persistence_is_generic_not_intrabar_only()
    test_mt5_proxy_telegram_block_is_honest()
    test_rithmic_formatter_auto_enriches_when_available()
    test_high_impact_alert_is_notification_only()
    test_high_impact_same_direction_cooldown()
    test_live_notifications_surface_context_without_authority()

    print(
        "[PASS] Universal MT5/Rithmic market-participation "
        "context + Telegram notification regression passed."
    )
