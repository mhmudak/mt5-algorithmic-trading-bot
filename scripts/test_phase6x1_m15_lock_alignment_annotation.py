from __future__ import annotations

from pathlib import Path

LIVE = Path("src/live_bot.py")
SETTINGS = Path("config/settings.py")


def test_settings_flag_exists():
    text = SETTINGS.read_text(encoding="utf-8")

    assert "ENABLE_INTRABAR_M15_DIRECTION_LOCK_ALIGNMENT_ANNOTATION = True" in text


def test_live_bot_alignment_markers_exist():
    text = LIVE.read_text(encoding="utf-8")

    assert "INTRABAR_M15_DIRECTION_LOCK_ALIGNED" in text
    assert "m15_direction_lock_status" in text
    assert "m15_direction_lock_setup_id" in text
    assert "m15_direction_lock_signal" in text
    assert "same_direction_as_m15_lock" in text
    assert "alignment annotation failed open" in text


if __name__ == "__main__":
    test_settings_flag_exists()
    test_live_bot_alignment_markers_exist()
    print("[PASS] Phase 6X1 M15 lock alignment annotation passed.")
