from __future__ import annotations

import tempfile
from pathlib import Path

from src.order_flow_features.rithmic_absorption_exhaustion import (
    evaluate_rithmic_absorption_exhaustion,
)

ROOT = Path(__file__).resolve().parents[1]

def integrity_ok():
    return {"integrity_ok": True, "continuity_valid": True}

def snapshot(
    *, updated_at=1.0, trade_count=30, total_volume=100.0,
    delta=40.0, imbalance=0.40, first_price=2400.0,
    last_price=2400.5, fresh_trade=True,
):
    return {
        "symbol": "GCZ6",
        "exchange": "COMEX",
        "updated_at_epoch": updated_at,
        "freshness": {"has_fresh_trade": fresh_trade},
        "sample": {"rolling_trade_count": trade_count},
        "trade_flow": {
            "rolling_total_volume": total_volume,
            "rolling_delta": delta,
            "rolling_imbalance_ratio": imbalance,
            "first_trade_price": first_price,
            "last_trade_price": last_price,
            "high_trade_price": max(first_price, last_price),
            "low_trade_price": min(first_price, last_price),
        },
    }

def test_effective_buy_aggression():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_absorption_exhaustion(
            snapshot(), history_path=Path(tmp) / "history.json",
            feed_integrity=integrity_ok(), signal="BUY",
            session="NEW_YORK_OPEN", tick_size=0.1,
        )
        assert result["status"] == "BUY_AGGRESSION_EFFECTIVE"
        assert result["classification"]["aggression_effective"] is True
        assert result["classification"]["absorbed"] is False

def test_buy_absorption_against_buy_signal():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_absorption_exhaustion(
            snapshot(last_price=2400.05), history_path=Path(tmp) / "history.json",
            feed_integrity=integrity_ok(), signal="BUY",
            session="NEW_YORK_OPEN", tick_size=0.1,
        )
        assert result["status"] == "BUY_AGGRESSION_ABSORBED"
        assert result["classification"]["absorbed"] is True
        assert result["classification"]["absorption_against_signal"] is True

def test_buy_absorption_supports_sell_signal():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_absorption_exhaustion(
            snapshot(last_price=2399.9), history_path=Path(tmp) / "history.json",
            feed_integrity=integrity_ok(), signal="SELL",
            session="NEW_YORK_OPEN", tick_size=0.1,
        )
        assert result["status"] == "BUY_AGGRESSION_ABSORBED_ADVERSE"
        assert result["classification"]["absorption_supports_signal"] is True

def test_sell_absorption_against_sell_signal():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_absorption_exhaustion(
            snapshot(delta=-45.0, imbalance=-0.45, last_price=2399.95),
            history_path=Path(tmp) / "history.json",
            feed_integrity=integrity_ok(), signal="SELL",
            session="NEW_YORK_OPEN", tick_size=0.1,
        )
        assert result["status"] == "SELL_AGGRESSION_ABSORBED"
        assert result["classification"]["absorption_against_signal"] is True

def test_exhaustion_after_prior_strong_buy_impulse():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "history.json"
        evaluate_rithmic_absorption_exhaustion(
            snapshot(updated_at=1.0, total_volume=200.0, delta=100.0, imbalance=0.50, last_price=2400.6),
            history_path=path, feed_integrity=integrity_ok(), signal="BUY",
            session="NEW_YORK_OPEN", tick_size=0.1,
        )
        result = evaluate_rithmic_absorption_exhaustion(
            snapshot(updated_at=2.0, total_volume=90.0, delta=20.0, imbalance=0.20, last_price=2400.15),
            history_path=path, feed_integrity=integrity_ok(), signal="BUY",
            session="NEW_YORK_OPEN", tick_size=0.1,
        )
        assert result["status"] == "BUY_AGGRESSION_EXHAUSTING"
        assert result["classification"]["exhaustion"] is True
        assert result["classification"]["exhaustion_against_signal"] is True

def test_feed_integrity_blocks_classification():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_absorption_exhaustion(
            snapshot(), history_path=Path(tmp) / "history.json",
            feed_integrity={"integrity_ok": False, "continuity_valid": False},
            signal="BUY", session="NEW_YORK_OPEN",
        )
        assert result["status"] == "FEED_INTEGRITY_NOT_USABLE"
        assert result["safe_for_execution"] is False

def test_duplicate_does_not_expand_history():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "history.json"
        item = snapshot()
        first = evaluate_rithmic_absorption_exhaustion(item, history_path=path, feed_integrity=integrity_ok())
        second = evaluate_rithmic_absorption_exhaustion(item, history_path=path, feed_integrity=integrity_ok())
        assert first["history"]["snapshot_count"] == 1
        assert second["history"]["snapshot_count"] == 1
        assert second["history"]["current_snapshot_was_duplicate"] is True

def test_phase5g_wiring_is_observe_only():
    source = (ROOT / "scripts" / "build_phase5g_rithmic_monitoring_bridge.py").read_text(
        encoding="utf-8", errors="replace"
    )
    required = (
        'bridge["absorption_exhaustion"]',
        "evaluate_rithmic_absorption_exhaustion",
        "format_absorption_exhaustion_text",
        "phase5g_rithmic_absorption_exhaustion_history.json",
        "absorption_exhaustion_history.unlink()",
    )
    for marker in required:
        assert marker in source, marker
    assert "execute_trade(" not in source
    assert "order_send(" not in source

def main():
    test_effective_buy_aggression()
    test_buy_absorption_against_buy_signal()
    test_buy_absorption_supports_sell_signal()
    test_sell_absorption_against_sell_signal()
    test_exhaustion_after_prior_strong_buy_impulse()
    test_feed_integrity_blocks_classification()
    test_duplicate_does_not_expand_history()
    test_phase5g_wiring_is_observe_only()
    print("PASS: effective aggression requires executed flow + price progress")
    print("PASS: buy absorption is distinguished from effective buying")
    print("PASS: absorption can be classified against/supporting setup direction")
    print("PASS: sell-side absorption is symmetric")
    print("PASS: exhaustion requires collapse from a prior same-direction impulse")
    print("PASS: bad feed integrity blocks microstructure classification")
    print("PASS: duplicate snapshots do not inflate exhaustion history")
    print("PASS: Phase 5G absorption/exhaustion wiring has no execution authority")

if __name__ == "__main__":
    main()
