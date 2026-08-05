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


def _with_static_fallback_enabled(fn):
    import config.settings as settings

    original_dynamic = getattr(settings, "ENABLE_DYNAMIC_INTRABAR_SUBPROFILE_RISK_RULES", False)
    original_fallback = getattr(settings, "DYNAMIC_INTRABAR_SUBPROFILE_STATIC_FALLBACK", False)

    settings.ENABLE_DYNAMIC_INTRABAR_SUBPROFILE_RISK_RULES = False
    settings.DYNAMIC_INTRABAR_SUBPROFILE_STATIC_FALLBACK = True

    try:
        fn()
    finally:
        settings.ENABLE_DYNAMIC_INTRABAR_SUBPROFILE_RISK_RULES = original_dynamic
        settings.DYNAMIC_INTRABAR_SUBPROFILE_STATIC_FALLBACK = original_fallback


def test_default_guard_disabled_allows_intrabar_subprofile():
    decision = evaluate_intrabar_subprofile_risk_guard(
        signal="SELL",
        trade_plan={
            "setup_id": "ASLS-SELL-1",
            "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
            "session": "LONDON",
            "market_condition": "INTRABAR_STRUCTURAL_LEVEL_SCALP",
            "setup_source_bucket": "INTRABAR",
        },
        enabled=False,
        block_rules=RULES,
    )

    assert decision["allowed"] is True
    assert decision["reason"] == "guard_disabled"


def test_toggle_on_blocks_configured_intrabar_subprofile():
    def run():
        decision = evaluate_intrabar_subprofile_risk_guard(
            signal="SELL",
            trade_plan={
                "setup_id": "ASLS-SELL-1",
                "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
                "session": "LONDON",
                "market_condition": "INTRABAR_STRUCTURAL_LEVEL_SCALP",
                "setup_source_bucket": "INTRABAR",
            },
            enabled=True,
            block_rules=RULES,
        )

        assert decision["allowed"] is False
        assert decision["reason"] == "intrabar_subprofile_risk_blocked"
        assert decision["matched_rule"]["session"] == "LONDON"

    _with_static_fallback_enabled(run)


def test_toggle_on_allows_unconfigured_intrabar_subprofile():
    def run():
        decision = evaluate_intrabar_subprofile_risk_guard(
            signal="BUY",
            trade_plan={
                "setup_id": "ASLS-BUY-1",
                "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
                "session": "LONDON",
                "market_condition": "INTRABAR_STRUCTURAL_LEVEL_SCALP",
                "setup_source_bucket": "INTRABAR",
            },
            enabled=True,
            block_rules=RULES,
        )

        assert decision["allowed"] is True
        assert decision["reason"] == "intrabar_subprofile_allowed"

    _with_static_fallback_enabled(run)


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
        enabled=True,
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


def test_settings_default_disabled_and_rules_exist():
    text = SETTINGS.read_text(encoding="utf-8")

    assert "ENABLE_INTRABAR_SUBPROFILE_RISK_GUARD = False" in text
    assert "ENABLE_DYNAMIC_INTRABAR_SUBPROFILE_RISK_RULES = False" in text
    assert "DYNAMIC_INTRABAR_SUBPROFILE_STATIC_FALLBACK = False" in text
    assert "INTRABAR_SUBPROFILE_BLOCK_RULES" in text
    assert '"AUTO_STRUCTURAL_LEVEL_SCALP"' in text
    assert '"FAILED_FVG_REVERSAL"' in text


if __name__ == "__main__":
    test_default_guard_disabled_allows_intrabar_subprofile()
    test_toggle_on_blocks_configured_intrabar_subprofile()
    test_toggle_on_allows_unconfigured_intrabar_subprofile()
    test_non_intrabar_is_not_blocked()
    test_live_bot_markers_exist()
    test_settings_default_disabled_and_rules_exist()
    print("[PASS] Phase 6W2 intrabar sub-profile toggle guard passed.")
