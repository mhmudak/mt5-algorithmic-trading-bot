from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.strategies.strategy_auto_structural_level_scalp import generate_signal


fixtures = runpy.run_path(
    str(ROOT / "scripts" / "test_phase6g_auto_structural_level_scalp.py"),
    run_name="phase6g_asls_fixture_module",
)


def test_bounce_requires_liquidity_reclaim_momentum_and_context():
    signal = generate_signal(fixtures["build_bounce_buy_df"]())

    assert signal is not None
    assert signal["entry_model"] == "SUPPORT_BOUNCE_SCALP"
    assert signal["asls_context_qualified"] is True
    assert signal["liquidity_confirmed"] is True
    assert signal["momentum_confirmed"] is True
    assert signal["liquidity_interaction"] == "SELL_SIDE_SUPPORT_REJECTION_RECLAIM"
    assert signal["liquidity_reclaim_distance"] > 0
    assert signal["m15_context_relation"] in {
        "WITH_M15",
        "M15_TRANSITION",
        "COUNTER_M15",
    }


def test_break_hold_requires_post_break_hold_distance():
    signal = generate_signal(fixtures["build_break_sell_df"]())

    assert signal is not None
    assert signal["entry_model"] == "SUPPORT_BREAK_HOLD_SCALP"
    assert signal["asls_context_qualified"] is True
    assert signal["liquidity_confirmed"] is True
    assert signal["momentum_confirmed"] is True
    assert signal["liquidity_interaction"] == "SUPPORT_BREAK_HOLD"
    assert signal["break_hold_distance"] >= 0.30


def test_quality_logic_has_no_permanent_side_or_session_block():
    source = (
        ROOT / "src" / "strategies" / "strategy_auto_structural_level_scalp.py"
    ).read_text(encoding="utf-8-sig")

    start = source.index("def _asls_quality_context(")
    end = source.index("def _build_signal(", start)
    section = source[start:end]

    assert "COUNTER_M15" in section
    assert "counter_m15_override" in section
    assert "ASLS_CONTEXT_COUNTER_MIN_BODY_ATR" in section
    assert "session" not in section.lower()


if __name__ == "__main__":
    test_bounce_requires_liquidity_reclaim_momentum_and_context()
    test_break_hold_requires_post_break_hold_distance()
    test_quality_logic_has_no_permanent_side_or_session_block()
    print("[PASS] ASLS liquidity/momentum/M15 contextual qualification regression passed.")
