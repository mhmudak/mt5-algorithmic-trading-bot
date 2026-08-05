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
    assert "if not promoted_track_only and score < MTF_CONFLICT_SOFT_EXECUTION_MIN_SCORE" in text


def test_mtf_low_rr_wait_markers_exist():
    text = LIVE.read_text(encoding="utf-8")

    assert "ENABLE_MTF_CONFLICT_LOW_RR_WAIT_BETTER_ENTRY" in text
    assert "MTF_CONFLICT_LOW_RR_WAIT_BETTER_ENTRY_EXPIRY_MINUTES" in text
    assert 'low_rr_reason = "shadow_rr_too_low" in str(execution_reason or "")' in text
    assert 'source="MTF_CONFLICT_LOW_RR"' in text
    assert "MTF_CONFLICT_LOW_RR_WAIT_BETTER_ENTRY" in text
    assert "MTF Conflict Waiting for Better Entry" in text


def test_mtf_wait_is_before_mtf_execution():
    text = LIVE.read_text(encoding="utf-8")

    wait_index = text.find("MTF_CONFLICT_LOW_RR_WAIT_BETTER_ENTRY")
    execute_index = text.find("execution_result = execute_trade(signal, mtf_trade_plan, SYMBOL)", wait_index)

    assert wait_index != -1
    assert execute_index != -1
    assert wait_index < execute_index


if __name__ == "__main__":
    test_settings_flags_exist()
    test_mtf_track_only_promotion_markers_exist()
    test_mtf_low_rr_wait_markers_exist()
    test_mtf_wait_is_before_mtf_execution()
    print("[PASS] Phase 6V2A MTF tracked promotion low-RR wait passed.")
