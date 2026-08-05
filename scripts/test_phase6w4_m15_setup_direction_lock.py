from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.m15_setup_direction_lock import (
    evaluate_intrabar_m15_direction_lock_guard,
    get_active_m15_direction_lock,
    register_m15_direction_lock,
)


LIVE = Path("src/live_bot.py")
SETTINGS = Path("config/settings.py")


def test_register_and_expire_m15_lock():
    lock = {}

    register_m15_direction_lock(
        lock,
        signal="BUY",
        setup_id="ORB-BUY-1",
        strategy="ORB",
        session="NEWYORK_LATE",
        ttl_seconds=10,
        now_ts=100.0,
    )

    assert lock["active"] is True
    assert lock["signal"] == "BUY"
    assert get_active_m15_direction_lock(lock, now_ts=105.0) is not None
    assert get_active_m15_direction_lock(lock, now_ts=111.0) is None
    assert lock == {}


def test_intrabar_opposite_direction_blocks_against_m15_lock():
    lock = {}

    register_m15_direction_lock(
        lock,
        signal="BUY",
        setup_id="M15-BUY-1",
        strategy="ORB",
        session="NEWYORK_LATE",
        ttl_seconds=900,
        now_ts=100.0,
    )

    decision = evaluate_intrabar_m15_direction_lock_guard(
        signal="SELL",
        trade_plan={
            "setup_id": "ASLS-SELL-1",
            "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
            "setup_source_bucket": "INTRABAR",
        },
        lock_state=lock,
        now_ts=120.0,
    )

    assert decision["allowed"] is False
    assert decision["reason"] == "intrabar_opposite_m15_direction_lock_blocked"
    assert decision["active_lock"]["signal"] == "BUY"


def test_intrabar_same_direction_allowed_against_m15_lock():
    lock = {}

    register_m15_direction_lock(
        lock,
        signal="BUY",
        setup_id="M15-BUY-1",
        strategy="ORB",
        ttl_seconds=900,
        now_ts=100.0,
    )

    decision = evaluate_intrabar_m15_direction_lock_guard(
        signal="BUY",
        trade_plan={
            "setup_id": "ASLS-BUY-1",
            "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
            "setup_source_bucket": "INTRABAR",
        },
        lock_state=lock,
        now_ts=120.0,
    )

    assert decision["allowed"] is True
    assert decision["reason"] == "same_direction_as_m15_lock"


def test_non_intrabar_ignores_m15_lock():
    lock = {}

    register_m15_direction_lock(
        lock,
        signal="BUY",
        setup_id="M15-BUY-1",
        strategy="ORB",
        ttl_seconds=900,
        now_ts=100.0,
    )

    decision = evaluate_intrabar_m15_direction_lock_guard(
        signal="SELL",
        trade_plan={
            "setup_id": "ORB-SELL-1",
            "strategy": "ORB",
            "setup_source_bucket": "NORMAL_OR_TRACKED",
            "market_condition": "TRENDING",
        },
        lock_state=lock,
        now_ts=120.0,
    )

    assert decision["allowed"] is True
    assert decision["reason"] == "not_intrabar_trade_plan"


def test_live_bot_markers_exist():
    text = LIVE.read_text(encoding="utf-8")

    assert "PHASE6W_M15_DIRECTION_LOCK = {}" in text
    assert "register_m15_direction_lock" in text
    assert "evaluate_intrabar_m15_direction_lock_guard" in text
    assert "M15_SETUP_DIRECTION_LOCK_REGISTERED" in text
    assert "INTRABAR_M15_DIRECTION_LOCK_BLOCKED" in text
    assert "Intrabar Blocked by M15 Direction Lock" in text


def test_settings_flags_exist():
    text = SETTINGS.read_text(encoding="utf-8")

    assert "ENABLE_M15_SETUP_DIRECTION_LOCK = True" in text
    assert "M15_SETUP_DIRECTION_LOCK_TTL_SECONDS = 900" in text
    assert "ENABLE_INTRABAR_M15_DIRECTION_LOCK_GUARD = True" in text


if __name__ == "__main__":
    test_register_and_expire_m15_lock()
    test_intrabar_opposite_direction_blocks_against_m15_lock()
    test_intrabar_same_direction_allowed_against_m15_lock()
    test_non_intrabar_ignores_m15_lock()
    test_live_bot_markers_exist()
    test_settings_flags_exist()
    print("[PASS] Phase 6W4 M15 setup direction lock passed.")
