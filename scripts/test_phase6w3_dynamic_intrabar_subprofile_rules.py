from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import json

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_phase6w3_intrabar_subprofile_rules import (
    generate_rules_from_rows,
    parse_intrabar_policy_key,
)
from src.intrabar_subprofile_risk_guard import (
    evaluate_intrabar_subprofile_risk_guard,
    get_effective_intrabar_subprofile_block_rules,
)


SETTINGS = Path("config/settings.py")
SCRIPT = Path("scripts/generate_phase6w3_intrabar_subprofile_rules.py")


def test_parse_intrabar_policy_key_with_entry_model():
    parsed = parse_intrabar_policy_key(
        "AUTO_STRUCTURAL_LEVEL_SCALP|SELL|SUPPORT_BREAK_HOLD_SCALP|LONDON|INTRABAR_STRUCTURAL_LEVEL_SCALP|INTRABAR"
    )

    assert parsed["strategy"] == "AUTO_STRUCTURAL_LEVEL_SCALP"
    assert parsed["signal"] == "SELL"
    assert parsed["session"] == "LONDON"
    assert parsed["market_condition"] == "INTRABAR_STRUCTURAL_LEVEL_SCALP"


def test_generate_block_rule_from_block_temporarily_row():
    rows = [
        {
            "policy_key": "AUTO_STRUCTURAL_LEVEL_SCALP|SELL|SUPPORT_BREAK_HOLD_SCALP|LONDON|INTRABAR_STRUCTURAL_LEVEL_SCALP|INTRABAR",
            "sample_count": "5",
            "decision": "BLOCK_TEMPORARILY",
            "actual_expectancy": "-2.45",
            "loss_rate": "0.8",
        }
    ]

    rules = generate_rules_from_rows(
        rows,
        min_samples=5,
        block_decisions=("BLOCK_TEMPORARILY",),
        max_loss_rate=0.60,
        min_expectancy=0.0,
    )

    assert len(rules) == 1
    assert rules[0]["strategy"] == "AUTO_STRUCTURAL_LEVEL_SCALP"
    assert rules[0]["signal"] == "SELL"
    assert rules[0]["session"] == "LONDON"


def test_low_sample_row_does_not_generate_rule():
    rows = [
        {
            "policy_key": "AUTO_STRUCTURAL_LEVEL_SCALP|SELL|SUPPORT_BREAK_HOLD_SCALP|LONDON|INTRABAR_STRUCTURAL_LEVEL_SCALP|INTRABAR",
            "sample_count": "3",
            "decision": "BLOCK_TEMPORARILY",
            "actual_expectancy": "-9.0",
            "loss_rate": "1.0",
        }
    ]

    rules = generate_rules_from_rows(
        rows,
        min_samples=5,
        block_decisions=("BLOCK_TEMPORARILY",),
        max_loss_rate=0.60,
        min_expectancy=0.0,
    )

    assert rules == []


def test_dynamic_rules_can_be_enabled_temporarily():
    with tempfile.TemporaryDirectory() as tmpdir:
        dynamic_path = Path(tmpdir) / "rules.json"
        dynamic_path.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
                            "signal": "SELL",
                            "session": "ASIA",
                            "market_condition": "*",
                            "rule_reason": "dynamic test rule",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        import config.settings as settings

        original_enabled = getattr(settings, "ENABLE_DYNAMIC_INTRABAR_SUBPROFILE_RISK_RULES", False)
        original_path = getattr(settings, "DYNAMIC_INTRABAR_SUBPROFILE_RULES_FILE", None)
        original_fallback = getattr(settings, "DYNAMIC_INTRABAR_SUBPROFILE_STATIC_FALLBACK", False)

        settings.ENABLE_DYNAMIC_INTRABAR_SUBPROFILE_RISK_RULES = True
        settings.DYNAMIC_INTRABAR_SUBPROFILE_RULES_FILE = str(dynamic_path)
        settings.DYNAMIC_INTRABAR_SUBPROFILE_STATIC_FALLBACK = False

        try:
            effective = get_effective_intrabar_subprofile_block_rules(
                static_rules=[
                    (
                        "AUTO_STRUCTURAL_LEVEL_SCALP",
                        "SELL",
                        "LONDON",
                        "*",
                        "static rule",
                    )
                ]
            )

            assert len(effective) == 1
            assert effective[0][2] == "ASIA"

            blocked = evaluate_intrabar_subprofile_risk_guard(
                signal="SELL",
                trade_plan={
                    "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
                    "session": "ASIA",
                    "market_condition": "INTRABAR_STRUCTURAL_LEVEL_SCALP",
                    "setup_source_bucket": "INTRABAR",
                },
                enabled=True,
                block_rules=[
                    (
                        "AUTO_STRUCTURAL_LEVEL_SCALP",
                        "SELL",
                        "LONDON",
                        "*",
                        "static rule",
                    )
                ],
            )

            allowed = evaluate_intrabar_subprofile_risk_guard(
                signal="SELL",
                trade_plan={
                    "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
                    "session": "LONDON",
                    "market_condition": "INTRABAR_STRUCTURAL_LEVEL_SCALP",
                    "setup_source_bucket": "INTRABAR",
                },
                enabled=True,
                block_rules=[
                    (
                        "AUTO_STRUCTURAL_LEVEL_SCALP",
                        "SELL",
                        "LONDON",
                        "*",
                        "static rule",
                    )
                ],
            )

            assert blocked["allowed"] is False
            assert allowed["allowed"] is True

        finally:
            settings.ENABLE_DYNAMIC_INTRABAR_SUBPROFILE_RISK_RULES = original_enabled
            settings.DYNAMIC_INTRABAR_SUBPROFILE_STATIC_FALLBACK = original_fallback
            if original_path is not None:
                settings.DYNAMIC_INTRABAR_SUBPROFILE_RULES_FILE = original_path


def test_settings_default_disabled_and_script_markers_exist():
    settings_text = SETTINGS.read_text(encoding="utf-8")
    script_text = SCRIPT.read_text(encoding="utf-8")

    assert "ENABLE_DYNAMIC_INTRABAR_SUBPROFILE_RISK_RULES = False" in settings_text
    assert "DYNAMIC_INTRABAR_SUBPROFILE_STATIC_FALLBACK = False" in settings_text
    assert "DYNAMIC_INTRABAR_SUBPROFILE_RULES_FILE" in settings_text
    assert "intrabar_subprofile_block_rules.json" in script_text
    assert "trade_tracker_health_by_bucket.csv" in script_text


if __name__ == "__main__":
    test_parse_intrabar_policy_key_with_entry_model()
    test_generate_block_rule_from_block_temporarily_row()
    test_low_sample_row_does_not_generate_rule()
    test_dynamic_rules_can_be_enabled_temporarily()
    test_settings_default_disabled_and_script_markers_exist()
    print("[PASS] Phase 6W3 dynamic intrabar sub-profile toggle rules passed.")
