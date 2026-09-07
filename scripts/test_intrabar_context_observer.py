from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.intrabar_context_observer import (
    SCHEMA_VERSION,
    build_intrabar_context_snapshot,
    log_intrabar_context_observation,
)


def synthetic_bearish_df():
    closes = [120.0 - (i * 0.5) for i in range(30)]

    return pd.DataFrame(
        {
            "open": [value + 0.20 for value in closes],
            "high": [value + 0.60 for value in closes],
            "low": [value - 0.60 for value in closes],
            "close": closes,
        }
    )


def test_snapshot_v2_direction_liquidity_and_risk():
    snapshot = build_intrabar_context_snapshot(
        df=synthetic_bearish_df(),
        source="PHASE6H3_ASLS",
        event="PHASE6H3_ASLS_EXECUTED",
        strategy="AUTO_STRUCTURAL_LEVEL_SCALP",
        setup_id="TEST-ASLS-1",
        signal="SELL",
        entry_model="SUPPORT_BREAK_HOLD_SCALP",
        session="LONDON",
        execution_market_condition="INTRABAR_STRUCTURAL_LEVEL_SCALP",
        observed_market_condition="TRENDING",
        signal_data={
            "momentum": "bearish_structure_momentum",
            "direction_context": "bearish_break_hold",
            "liquidity_interaction": "SUPPORT_BREAK_RETEST_HOLD",
            "break_hold_distance": 0.75,
            "structural_level": 100.5,
        },
        trade_plan={
            "entry_price": 100.0,
            "stop_loss": 105.0,
            "take_profit": 90.0,
            "lot": 0.25,
            "reason": "synthetic test",
        },
        m15_direction="SELL",
        mtf_bias="BUY",
        htf_context={"bias": "BEARISH"},
    )

    assert snapshot is not None
    assert SCHEMA_VERSION == 2
    assert snapshot["schema_version"] == 2
    assert snapshot["record_type"] == "INTRABAR_EXECUTION_CONTEXT_T0"
    assert snapshot["capture_phase"] == "T0_PRE_EXECUTION"

    assert snapshot["m15_direction"] == "SELL"
    assert snapshot["m15_bias"] == "SELL"
    assert snapshot["m15_relation"] == "WITH_M15"
    assert snapshot["mtf_bias"] == "BUY"
    assert snapshot["mtf_relation"] == "COUNTER_MTF"
    assert snapshot["htf_bias"] == "SELL"
    assert snapshot["htf_relation"] == "WITH_HTF"

    assert snapshot["regime_family"] == "TREND_OR_EXPANSION"
    assert snapshot["initial_price_risk"] == 5.0
    assert snapshot["risk_distance"] == 5.0
    assert snapshot["planned_rr"] == 2.0
    assert snapshot["lot"] == 0.25

    assert snapshot["momentum"]["strategy_label"] == "bearish_structure_momentum"
    assert snapshot["momentum"]["relation"] == "WITH_PRICE_MOMENTUM"
    assert snapshot["liquidity_context"]["interaction"] == "SUPPORT_BREAK_RETEST_HOLD"
    assert snapshot["liquidity_context"]["break_hold_distance"] == 0.75
    assert snapshot["liquidity_context"]["structural_level"] == 100.5


def test_all_target_intrabar_strategies_are_observed():
    for strategy in (
        "AUTO_STRUCTURAL_LEVEL_SCALP",
        "FAILED_FVG_REVERSAL",
        "BREAKER_BLOCK",
        "ORDER_BLOCK",
    ):
        snapshot = build_intrabar_context_snapshot(
            df=synthetic_bearish_df(),
            source="TEST",
            event="EXECUTED",
            strategy=strategy,
            setup_id=f"TEST-{strategy}",
            signal="SELL",
        )
        assert snapshot is not None

    assert build_intrabar_context_snapshot(
        df=synthetic_bearish_df(),
        source="TEST",
        event="EXECUTED",
        strategy="ORB",
        setup_id="TEST-ORB",
        signal="SELL",
    ) is None


def test_jsonl_persistence():
    snapshot = build_intrabar_context_snapshot(
        df=synthetic_bearish_df(),
        source="INTRABAR_PRICE_EVENT",
        event="INTRABAR_PRICE_EVENT_EXECUTED",
        strategy="FAILED_FVG_REVERSAL",
        setup_id="TEST-FVG-1",
        signal="SELL",
        entry_model="FAILED_FVG",
        session="ASIA",
        execution_market_condition="INTRABAR_PENDING",
        observed_market_condition="RANGING",
        trade_plan={
            "entry_price": 100.0,
            "stop_loss": 104.0,
            "take_profit": 92.0,
            "lot": 0.06,
        },
        m15_direction="SELL",
        mtf_bias="SELL",
        htf_context={"bias": "BEARISH"},
    )

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "observations.jsonl"
        assert log_intrabar_context_observation(snapshot, file_path=path) is True
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["setup_id"] == "TEST-FVG-1"
        assert row["regime_family"] == "RANGE_OR_COMPRESSION"
        assert row["capture_phase"] == "T0_PRE_EXECUTION"


def test_live_hook_is_causal_t0_then_success_persist():
    source = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8-sig")

    assert "def _freeze_intrabar_context_observation(" in source
    assert "def _persist_intrabar_context_observation(" in source
    assert "def _capture_intrabar_context_observation(" not in source

    generic_start = source.index("def process_intrabar_price_event_detector(")
    generic_end = source.index("def intrabar_m5_confirmation_ok(", generic_start)
    generic = source[generic_start:generic_end]

    generic_freeze = generic.index("intrabar_t0_snapshot = _freeze_intrabar_context_observation(")
    generic_execute = generic.index("execution_result = execute_trade(signal, trade_plan, SYMBOL)")
    generic_success = generic.index("if execution_result:", generic_execute)
    generic_persist = generic.index("_persist_intrabar_context_observation(intrabar_t0_snapshot)")

    assert generic_freeze < generic_execute < generic_success < generic_persist

    phase_start = source.index("PHASE 6H3 - INTRABAR STRUCTURAL LEVEL SCALP EXECUTION")
    phase_end = source.index("# NEW CANDLE CHECK", phase_start)
    phase = source[phase_start:phase_end]

    phase_freeze = phase.index("asls_t0_snapshot = _freeze_intrabar_context_observation(")
    phase_execute = phase.index("execution_result = execute_trade(asls_signal, asls_trade_plan, SYMBOL)")
    phase_success = phase.index("if execution_result:", phase_execute)
    phase_persist = phase.index("_persist_intrabar_context_observation(asls_t0_snapshot)")

    assert phase_freeze < phase_execute < phase_success < phase_persist


def main():
    test_snapshot_v2_direction_liquidity_and_risk()
    test_all_target_intrabar_strategies_are_observed()
    test_jsonl_persistence()
    test_live_hook_is_causal_t0_then_success_persist()

    print(
        "[PASS] Intrabar observer V2 freezes causal T0 context before execution "
        "and persists only successful executions."
    )


if __name__ == "__main__":
    main()
