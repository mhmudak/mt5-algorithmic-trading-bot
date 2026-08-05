from __future__ import annotations

from pathlib import Path

LIVE = Path("src/live_bot.py")


def test_old_misleading_tracked_wording_removed():
    text = LIVE.read_text(encoding="utf-8")

    assert "Action: tracked only — use statistics before changing execution rules." not in text
    assert "Action: tracked due to MTF conflict — not automatically weak." not in text
    assert "Action: moved to generic rejected candidate recovery if eligible." not in text


def test_new_promotion_wording_exists():
    text = LIVE.read_text(encoding="utf-8")

    assert "tracked for promotion" in text
    assert "confirmation gate pass" in text
    assert "waits for better entry" in text
    assert "moved to recovery queue" in text


if __name__ == "__main__":
    test_old_misleading_tracked_wording_removed()
    test_new_promotion_wording_exists()
    print("[PASS] Phase 6V3 Telegram wording cleanup passed.")
