from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intrabar_subprofile_risk_guard import evaluate_intrabar_subprofile_risk_guard


LIVE = Path("src/live_bot.py")
SETTINGS = Path("config/settings.py")


RULES = (
    (
        "AUTO_STRUCTURAL_LEVEL_SCALP",
        "SELL",
        "LONDON",
        "*",
        "blocked for test",
    ),
)


def test_blocks_configured_intrabar_subprofile():
    decision = evaluate_intrabar_subprofile_risk_guard(
        signal="SELL",
        trade_plan={
            "setup_id": "ASLS-SELL-1",
            "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
            "session": "LONDON",
            "market_condition": "INTRABAR_STRUCTURAL_LEVEL_SCALP",
            "setup_source_bucket": "INTRABAR",
        },
        block_rules=RULES,
    )

    assert decision["allowed"] is False
    assert decision["reason"] == "intrabar_subprofile_risk_blocked"
    assert decision["matched_rule"]["session"] == "LONDON"


def test_allows_unconfigured_intrabar_subprofile():
    decision = evaluate_intrabar_subprofile_risk_guard(
        signal="BUY",
        trade_plan={
            "setup_id": "ASLS-BUY-1",
            "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
            "session": "LONDON",
            "market_condition": "INTRABAR_STRUCTURAL_LEVEL_SCALP",
            "setup_source_bucket": "INTRABAR",
        },
        block_rules=RULES,
    )

    assert decision["allowed"] is True
    assert decision["reason"] == "intrabar_subprofile_allowed"


def test_non_intrabar_is_not_blocked():
    decision = evaluate_intrabar_subprofile_risk_guard(
        signal="SELL",
        trade_plan={
            "setup_id": "ORB-SELL-1",
            "strategy": "ORB",
            "session": "LONDON",
            "market_condition": "TRENDING",
            "setup_source_bucket": "NORMAL_OR_TRACKED",
        },
        block_rules=RULES,
    )

    assert decision["allowed"] is True
    assert decision["reason"] == "not_intrabar_trade_plan"


def test_live_bot_markers_exist():
    text = LIVE.read_text(encoding="utf-8")

    assert "evaluate_intrabar_subprofile_risk_guard" in text
    assert "INTRABAR_SUBPROFILE_RISK_BLOCKED" in text
    assert "Intrabar Sub-Profile Blocked" in text
    assert "[INTRABAR SUBPROFILE GUARD] failed open" in text
    assert "return _raw_execute_trade(signal, trade_plan, symbol)" in text


def test_settings_flags_exist():
    text = SETTINGS.read_text(encoding="utf-8")

    assert "ENABLE_INTRABAR_SUBPROFILE_RISK_GUARD = True" in text
    assert "INTRABAR_SUBPROFILE_BLOCK_RULES" in text
    assert '"AUTO_STRUCTURAL_LEVEL_SCALP"' in text
    assert '"SELL"' in text
    assert '"LONDON"' in text


if __name__ == "__main__":
    test_blocks_configured_intrabar_subprofile()
    test_allows_unconfigured_intrabar_subprofile()
    test_non_intrabar_is_not_blocked()
    test_live_bot_markers_exist()
    test_settings_flags_exist()
    print("[PASS] Phase 6W2 intrabar sub-profile risk guard passed.")
