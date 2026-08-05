from __future__ import annotations

from pathlib import Path

LIVE = Path("src/live_bot.py")
SETTINGS = Path("config/settings.py")


def test_settings_flags_exist():
    text = SETTINGS.read_text(encoding="utf-8")

    assert "ENABLE_MTF_CONFLICT_TRACK_ONLY_PROMOTION = True" in text
    assert "MTF_CONFLICT_TRACK_ONLY_PROMOTION_MIN_SCORE = 95" in text
    assert "ENABLE_MTF_CONFLICT_LOW_RR_WAIT_BETTER_ENTRY = True" in text
    assert "MTF_CONFLICT_LOW_RR_WAIT_BETTER_ENTRY_EXPIRY_MINUTES = 15" in text
    assert "ENABLE_REJECTED_CANDIDATE_LOW_RR_WAIT_BETTER_ENTRY = True" in text
    assert "REJECTED_CANDIDATE_LOW_RR_WAIT_BETTER_ENTRY_EXPIRY_MINUTES = 15" in text


def test_mtf_track_only_promotion_markers_exist():
    text = LIVE.read_text(encoding="utf-8")

    assert "promote_track_only" in text
    assert "promote_min_score" in text
    assert "promoted_track_only = True" in text
    assert "track_only_promotion_score_too_low" in text


def test_low_rr_wait_markers_exist():
    text = LIVE.read_text(encoding="utf-8")

    assert "MTF_CONFLICT_LOW_RR_WAIT_BETTER_ENTRY" in text
    assert 'source="MTF_CONFLICT_LOW_RR"' in text
    assert "MTF Conflict Waiting for Better Entry" in text

    assert "CANDIDATE_RECOVERY_LOW_RR_WAIT_BETTER_ENTRY" in text
    assert 'source="REJECTED_CANDIDATE_LOW_RR"' in text
    assert "Candidate Recovery Waiting for Better Entry" in text
    assert 'and reason_type == "LOW_RR"' in text
    assert "and float(rr_value) < float(min_rr)" in text


def test_wait_blocks_are_before_execution():
    text = LIVE.read_text(encoding="utf-8")

    mtf_wait = text.find("MTF_CONFLICT_LOW_RR_WAIT_BETTER_ENTRY")
    mtf_exec = text.find("execution_result = execute_trade(signal, mtf_trade_plan, SYMBOL)", mtf_wait)
    assert mtf_wait != -1
    assert mtf_exec != -1
    assert mtf_wait < mtf_exec

    rec_wait = text.find("CANDIDATE_RECOVERY_LOW_RR_WAIT_BETTER_ENTRY")
    rec_exec = text.find("execution_result = execute_trade(signal, trade_plan, SYMBOL)", rec_wait)
    assert rec_wait != -1
    assert rec_exec != -1
    assert rec_wait < rec_exec


if __name__ == "__main__":
    test_settings_flags_exist()
    test_mtf_track_only_promotion_markers_exist()
    test_low_rr_wait_markers_exist()
    test_wait_blocks_are_before_execution()
    print("[PASS] Phase 6V2 tracked promotion + low-RR wait passed.")
