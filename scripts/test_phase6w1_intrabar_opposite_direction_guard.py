from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intrabar_opposite_direction_guard import (
    evaluate_intrabar_opposite_direction_guard,
    is_intrabar_trade_plan,
)


LIVE = Path("src/live_bot.py")
SETTINGS = Path("config/settings.py")


def test_intrabar_plan_detection():
    assert is_intrabar_trade_plan(
        {
            "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
            "setup_source_bucket": "INTRABAR",
        }
    )

    assert is_intrabar_trade_plan(
        {
            "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
            "market_condition": "INTRABAR_STRUCTURAL_LEVEL_SCALP",
        }
    )

    assert not is_intrabar_trade_plan(
        {
            "strategy": "ORB",
            "setup_source_bucket": "NORMAL_OR_TRACKED",
            "market_condition": "TRENDING",
        }
    )


def test_intrabar_opposite_direction_blocks():
    decision = evaluate_intrabar_opposite_direction_guard(
        signal="BUY",
        trade_plan={
            "setup_id": "ASLS-BUY-1",
            "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
            "setup_source_bucket": "INTRABAR",
        },
        active_setups=[
            {
                "setup_id": "ORB-SELL-1",
                "strategy": "ORB",
                "signal": "SELL",
                "setup_source_bucket": "NORMAL_OR_TRACKED",
            }
        ],
    )

    assert decision["allowed"] is False
    assert decision["reason"] == "intrabar_opposite_active_setup_blocked"
    assert decision["opposing_setup"]["signal"] == "SELL"


def test_intrabar_same_direction_allows():
    decision = evaluate_intrabar_opposite_direction_guard(
        signal="BUY",
        trade_plan={
            "setup_id": "ASLS-BUY-1",
            "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
            "setup_source_bucket": "INTRABAR",
        },
        active_setups=[
            {
                "setup_id": "ORB-BUY-1",
                "strategy": "ORB",
                "signal": "BUY",
                "setup_source_bucket": "NORMAL_OR_TRACKED",
            }
        ],
    )

    assert decision["allowed"] is True


def test_non_intrabar_does_not_block():
    decision = evaluate_intrabar_opposite_direction_guard(
        signal="BUY",
        trade_plan={
            "setup_id": "ORB-BUY-1",
            "strategy": "ORB",
            "setup_source_bucket": "NORMAL_OR_TRACKED",
            "market_condition": "TRENDING",
        },
        active_setups=[
            {
                "setup_id": "SELL-1",
                "strategy": "ANY",
                "signal": "SELL",
                "setup_source_bucket": "NORMAL_OR_TRACKED",
            }
        ],
    )

    assert decision["allowed"] is True
    assert decision["reason"] == "not_intrabar_trade_plan"


def test_live_bot_execute_trade_wrapper_markers_exist():
    text = LIVE.read_text(encoding="utf-8")

    assert "execute_trade as _raw_execute_trade" in text
    assert "def execute_trade(signal, trade_plan, symbol):" in text
    assert "evaluate_intrabar_opposite_direction_guard" in text
    assert "INTRABAR_OPPOSITE_ACTIVE_SETUP_BLOCKED" in text
    assert "Intrabar Opposite Direction Blocked" in text
    assert "return _raw_execute_trade(signal, trade_plan, symbol)" in text


def test_settings_flags_exist():
    text = SETTINGS.read_text(encoding="utf-8")

    assert "ENABLE_INTRABAR_OPPOSITE_ACTIVE_SETUP_GUARD = True" in text
    assert "INTRABAR_OPPOSITE_ACTIVE_SETUP_BLOCK_SOURCES" in text


if __name__ == "__main__":
    test_intrabar_plan_detection()
    test_intrabar_opposite_direction_blocks()
    test_intrabar_same_direction_allows()
    test_non_intrabar_does_not_block()
    test_live_bot_execute_trade_wrapper_markers_exist()
    test_settings_flags_exist()
    print("[PASS] Phase 6W1 intrabar opposite direction guard passed.")
