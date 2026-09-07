from __future__ import annotations
import ast

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


SETTINGS = ROOT / "config" / "settings.py"
LIVE_BOT = ROOT / "src" / "live_bot.py"
TARGET_ALLOWLIST = (
    "AUTO_STRUCTURAL_LEVEL_SCALP",
    "FAILED_FVG_REVERSAL",
    "BREAKER_BLOCK",
    "ORDER_BLOCK",
)


def test_phase6u1_allowlist_decision_allows_target_strategies_only():
    for strategy in TARGET_ALLOWLIST:
        allowed = explain_intrabar_strategy_allowlist_decision(
            trade_plan={"strategy": strategy, "source_bucket": "INTRABAR"},
            enabled=True,
            allowlist=TARGET_ALLOWLIST,
        )
        assert allowed["allowed"] is True
        assert allowed["reason"] == "allowed_strategy"

    blocked = explain_intrabar_strategy_allowlist_decision(
        trade_plan={"strategy": "MICRO_SR_SWEEP_RECLAIM", "source_bucket": "INTRABAR"},
        enabled=True,
        allowlist=TARGET_ALLOWLIST,
    )

    assert blocked["allowed"] is False
    assert blocked["reason"] == "blocked_intrabar_strategy_not_in_allowlist"
    assert blocked["can_block_trade"] is True
    assert blocked["can_modify_risk"] is False
    assert blocked["can_modify_entry_sl_tp"] is False


def test_phase6u1_profile_filter_removes_non_allowed_intrabar_profiles():
    profiles = [
        {"strategy": "AUTO_STRUCTURAL_LEVEL_SCALP"},
        {"strategy": "FAILED_FVG_REVERSAL"},
        {"strategy": "BREAKER_BLOCK"},
        {"strategy": "ORDER_BLOCK"},
        {"strategy": "MICRO_SR_SWEEP_RECLAIM"},
        {"strategy": "RANGE_SWEEP_RECLAIM"},
    ]

    filtered = filter_intrabar_strategy_profiles(
        profiles,
        enabled=True,
        allowlist=TARGET_ALLOWLIST,
    )

    assert [row["strategy"] for row in filtered] == list(TARGET_ALLOWLIST)


def test_phase6u1_normalizes_allowlist():
    assert normalize_intrabar_allowlist(
        [" failed_fvg_reversal ", "FAILED_FVG_REVERSAL"]
    ) == ("FAILED_FVG_REVERSAL",)


def test_phase6u1_non_intrabar_trade_is_not_blocked():
    decision = explain_intrabar_strategy_allowlist_decision(
        trade_plan={"strategy": "ORB_V00", "source_bucket": "NORMAL_OR_TRACKED"},
        enabled=True,
        allowlist=TARGET_ALLOWLIST,
    )

    assert decision["allowed"] is True
    assert decision["reason"] == "non_intrabar_scope"
    assert decision["scope"] == "NON_INTRABAR_SKIPPED"
    assert decision["can_block_trade"] is False


def test_settings_master_switch_and_single_canonical_list():
    text = SETTINGS.read_text(encoding="utf-8-sig")

    assert "ENABLE_INTRABAR_ENGINE = True" in text

    tree = ast.parse(
        text,
        filename=str(SETTINGS),
    )

    canonical_values = []

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue

        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and target.id == "INTRABAR_STRATEGY_ALLOWLIST"
            ):
                canonical_values.append(
                    tuple(ast.literal_eval(node.value))
                )

    assert len(canonical_values) == 1
    assert canonical_values[0] == TARGET_ALLOWLIST

    assert "INTRABAR_PRICE_EVENT_ALLOWED_STRATEGIES = tuple(" in text
    assert "for strategy in INTRABAR_STRATEGY_ALLOWLIST" in text


def test_live_bot_has_generic_and_asls_canonical_guards():
    text = LIVE_BOT.read_text(encoding="utf-8-sig")

    assert "ENABLE_INTRABAR_ENGINE and ENABLE_INTRABAR_PRICE_EVENT_DETECTOR" in text
    assert "ENABLE_INTRABAR_ENGINE and ENABLE_AUTO_STRUCTURAL_LEVEL_SCALP" in text
    assert "phase6u_intrabar_allowlist_decision = explain_intrabar_strategy_allowlist_decision(" in text
    assert "asls_allowlist_decision = explain_intrabar_strategy_allowlist_decision(" in text

    generic_guard = text.index("phase6u_intrabar_allowlist_decision = explain_intrabar_strategy_allowlist_decision(")
    generic_execute = text.index("execution_result = execute_trade(signal, trade_plan, SYMBOL)")
    assert generic_guard < generic_execute

    phase_start = text.index("PHASE 6H3 - INTRABAR STRUCTURAL LEVEL SCALP EXECUTION")
    phase = text[phase_start:text.index("# NEW CANDLE CHECK", phase_start)]
    assert phase.index("asls_allowlist_decision = explain_intrabar_strategy_allowlist_decision(") < phase.index(
        "execution_result = execute_trade(asls_signal, asls_trade_plan, SYMBOL)"
    )


if __name__ == "__main__":
    test_phase6u1_allowlist_decision_allows_target_strategies_only()
    test_phase6u1_profile_filter_removes_non_allowed_intrabar_profiles()
    test_phase6u1_normalizes_allowlist()
    test_phase6u1_non_intrabar_trade_is_not_blocked()
    test_settings_master_switch_and_single_canonical_list()
    test_live_bot_has_generic_and_asls_canonical_guards()
    print("[PASS] Canonical intrabar strategy allowlist regression passed.")
