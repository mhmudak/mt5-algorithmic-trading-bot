
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intrabar_strategy_allowlist import (
    explain_intrabar_strategy_allowlist_decision,
    filter_intrabar_strategy_profiles,
    normalize_intrabar_allowlist,
)


SETTINGS = Path("config/settings.py")
LIVE_BOT = Path("src/live_bot.py")


def test_phase6u1_allowlist_decision_allows_only_target_strategies():
    allowlist = ("AUTO_STRUCTURAL_LEVEL_SCALP", "FAILED_FVG_REVERSAL")

    allowed = explain_intrabar_strategy_allowlist_decision(
        trade_plan={"strategy": "FAILED_FVG_REVERSAL", "source_bucket": "INTRABAR"},
        enabled=True,
        allowlist=allowlist,
    )

    blocked = explain_intrabar_strategy_allowlist_decision(
        trade_plan={"strategy": "MICRO_SR_SWEEP_RECLAIM", "source_bucket": "INTRABAR"},
        enabled=True,
        allowlist=allowlist,
    )

    assert allowed["allowed"] is True
    assert allowed["reason"] == "allowed_strategy"

    assert blocked["allowed"] is False
    assert blocked["reason"] == "blocked_intrabar_strategy_not_in_allowlist"
    assert blocked["can_block_trade"] is True
    assert blocked["can_modify_risk"] is False
    assert blocked["can_modify_entry_sl_tp"] is False


def test_phase6u1_profile_filter_removes_non_allowed_intrabar_profiles():
    profiles = [
        {"strategy": "AUTO_STRUCTURAL_LEVEL_SCALP"},
        {"strategy": "FAILED_FVG_REVERSAL"},
        {"strategy": "MICRO_SR_SWEEP_RECLAIM"},
        {"strategy": "RANGE_SWEEP_RECLAIM"},
        {"strategy": "VWAP_RECLAIM"},
    ]

    filtered = filter_intrabar_strategy_profiles(
        profiles,
        enabled=True,
        allowlist=("AUTO_STRUCTURAL_LEVEL_SCALP", "FAILED_FVG_REVERSAL"),
    )

    assert [row["strategy"] for row in filtered] == [
        "AUTO_STRUCTURAL_LEVEL_SCALP",
        "FAILED_FVG_REVERSAL",
    ]


def test_phase6u1_normalizes_allowlist():
    assert normalize_intrabar_allowlist([" failed_fvg_reversal ", "FAILED_FVG_REVERSAL"]) == (
        "FAILED_FVG_REVERSAL",
    )



def test_phase6u1_non_intrabar_trade_is_not_blocked():
    decision = explain_intrabar_strategy_allowlist_decision(
        trade_plan={"strategy": "ORB_V00", "source_bucket": "NORMAL_OR_TRACKED"},
        enabled=True,
        allowlist=("AUTO_STRUCTURAL_LEVEL_SCALP", "FAILED_FVG_REVERSAL"),
    )

    assert decision["allowed"] is True
    assert decision["reason"] == "non_intrabar_scope"
    assert decision["scope"] == "NON_INTRABAR_SKIPPED"
    assert decision["can_block_trade"] is False

def test_phase6u1_settings_flags_exist_and_are_enabled():
    text = SETTINGS.read_text(encoding="utf-8")

    assert "ENABLE_INTRABAR_STRATEGY_ALLOWLIST = True" in text
    assert "ENABLE_INTRABAR_STRATEGY_DETECTION_ALLOWLIST = True" in text
    assert '"AUTO_STRUCTURAL_LEVEL_SCALP"' in text
    assert '"FAILED_FVG_REVERSAL"' in text
    assert '"MICRO_SR_SWEEP_RECLAIM"' in text


def test_phase6u1_live_bot_has_final_execution_guard():
    text = LIVE_BOT.read_text(encoding="utf-8")

    assert "from src.intrabar_strategy_allowlist import (" in text
    assert "ENABLE_INTRABAR_STRATEGY_ALLOWLIST" in text
    assert "INTRABAR_STRATEGY_ALLOWLIST" in text
    assert "phase6u_intrabar_allowlist_decision = explain_intrabar_strategy_allowlist_decision(" in text
    module_text = Path("src/intrabar_strategy_allowlist.py").read_text(encoding="utf-8")
    assert "blocked_intrabar_strategy_not_in_allowlist" in module_text
    assert "execution_result = execute_trade(signal, trade_plan, SYMBOL)" in text

    guard_index = text.find("phase6u_intrabar_allowlist_decision = explain_intrabar_strategy_allowlist_decision(")
    execute_index = text.find("execution_result = execute_trade(signal, trade_plan, SYMBOL)")

    assert guard_index != -1
    assert execute_index != -1
    assert guard_index < execute_index


if __name__ == "__main__":
    test_phase6u1_allowlist_decision_allows_only_target_strategies()
    test_phase6u1_profile_filter_removes_non_allowed_intrabar_profiles()
    test_phase6u1_normalizes_allowlist()
    test_phase6u1_non_intrabar_trade_is_not_blocked()
    test_phase6u1_settings_flags_exist_and_are_enabled()
    test_phase6u1_live_bot_has_final_execution_guard()
    print("[PASS] Phase 6U1 intrabar strategy allowlist passed.")
