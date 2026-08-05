from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.tracked_setup_confirmation_gate import evaluate_tracked_confirmation_report

LIVE = Path("src/live_bot.py")
SETTINGS = Path("config/settings.py")


def test_report_gate_blocks_optional_failure():
    result = evaluate_tracked_confirmation_report(
        {
            "approved": True,
            "confidence": 70,
            "score_delta": 1,
            "required_failed": [],
            "optional_failed": [{"module": "ENTRY_QUALITY"}],
        },
        enabled=True,
        block_optional_failed=True,
        bucket="REJECTED_CANDIDATE_TRACKED",
    )

    assert result["allowed"] is False
    assert "optional_confirmation_failed" in result["reason"]
    assert result["failed_modules"] == ["ENTRY_QUALITY"]


def test_report_gate_allows_clean_confirmation():
    result = evaluate_tracked_confirmation_report(
        {
            "approved": True,
            "confidence": 70,
            "score_delta": 1,
            "required_failed": [],
            "optional_failed": [],
        },
        enabled=True,
        block_optional_failed=True,
        bucket="MTF_CONFLICT_TRACKED",
    )

    assert result["allowed"] is True
    assert result["reason"] == "confirmation_gate_passed"


def test_live_bot_has_tracked_gates_before_execution():
    text = LIVE.read_text(encoding="utf-8")

    assert "from src.tracked_setup_confirmation_gate import run_tracked_setup_confirmation_gate" in text
    assert 'setup_source_bucket_override="MTF_CONFLICT_TRACKED"' in text
    assert 'setup_source_bucket_override="REJECTED_CANDIDATE_TRACKED"' in text
    assert "MTF_CONFLICT_CONFIRMATION_GATE_BLOCKED" in text
    assert "CANDIDATE_RECOVERY_CONFIRMATION_GATE_BLOCKED" in text

    mtf_gate = text.find('setup_source_bucket_override="MTF_CONFLICT_TRACKED"')
    mtf_exec = text.find("execution_result = execute_trade(signal, mtf_trade_plan, SYMBOL)", mtf_gate)
    assert mtf_gate != -1
    assert mtf_exec != -1
    assert mtf_gate < mtf_exec

    rec_gate = text.find('setup_source_bucket_override="REJECTED_CANDIDATE_TRACKED"')
    rec_exec = text.find("execution_result = execute_trade(signal, trade_plan, SYMBOL)", rec_gate)
    assert rec_gate != -1
    assert rec_exec != -1
    assert rec_gate < rec_exec


def test_settings_flags_exist():
    text = SETTINGS.read_text(encoding="utf-8")

    assert "ENABLE_TRACKED_SETUP_CONFIRMATION_GATE = True" in text
    assert "TRACKED_SETUP_CONFIRMATION_GATE_MIN_CONFIDENCE = 50" in text
    assert "TRACKED_SETUP_CONFIRMATION_GATE_MIN_SCORE_DELTA = -4" in text
    assert "TRACKED_SETUP_CONFIRMATION_GATE_BLOCK_OPTIONAL_FAILED = True" in text


if __name__ == "__main__":
    test_report_gate_blocks_optional_failure()
    test_report_gate_allows_clean_confirmation()
    test_live_bot_has_tracked_gates_before_execution()
    test_settings_flags_exist()
    print("[PASS] Phase 6V1 tracked confirmation gate passed.")
