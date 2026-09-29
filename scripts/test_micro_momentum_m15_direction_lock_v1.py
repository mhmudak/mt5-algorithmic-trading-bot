from __future__ import annotations

from pathlib import Path

from config import settings
from src.m15_setup_direction_lock import register_m15_direction_lock
from src.micro_momentum_m15_direction_lock import (
    evaluate_micro_momentum_m15_direction_lock,
)


ROOT = Path(__file__).resolve().parents[1]
LIVE_BOT = ROOT / "src" / "live_bot.py"


def main():
    print("[MICRO MOMENTUM M15 DIRECTION LOCK TEST V1]")

    lock = {}
    register_m15_direction_lock(
        lock,
        signal="BUY",
        setup_id="M15-BUY-TEST",
        strategy="WAVETREND_MOMENTUM",
        session="NEWYORK",
        ttl_seconds=900,
        now_ts=100.0,
    )

    aligned = evaluate_micro_momentum_m15_direction_lock(
        signal="BUY",
        lock_state=lock,
        enabled=True,
        now_ts=200.0,
    )
    blocked = evaluate_micro_momentum_m15_direction_lock(
        signal="SELL",
        lock_state=lock,
        enabled=True,
        now_ts=200.0,
    )
    expired = evaluate_micro_momentum_m15_direction_lock(
        signal="SELL",
        lock_state=lock,
        enabled=True,
        now_ts=1001.0,
    )
    disabled = evaluate_micro_momentum_m15_direction_lock(
        signal="SELL",
        lock_state=lock,
        enabled=False,
        now_ts=200.0,
    )

    assert aligned["allowed"] is True
    assert aligned["reason"] == "micro_momentum_aligned_with_m15_lock"
    assert aligned["active_lock"]["signal"] == "BUY"

    assert blocked["allowed"] is False
    assert blocked["reason"] == "micro_momentum_opposite_m15_direction_lock_blocked"
    assert blocked["active_lock"]["setup_id"] == "M15-BUY-TEST"

    assert expired["allowed"] is True
    assert expired["reason"] == "no_active_m15_direction_lock"

    assert disabled["allowed"] is True
    assert disabled["reason"] == "guard_disabled"

    assert settings.ENABLE_MICRO_MOMENTUM_M15_DIRECTION_LOCK_GUARD is True

    source = LIVE_BOT.read_text(encoding="utf-8")
    block_marker = 'decision="MICRO_MOMENTUM_M15_DIRECTION_LOCK_BLOCKED"'
    attempt_marker = 'event="MICRO_MOMENTUM_EXECUTION_ATTEMPT"'
    execute_marker = "execution_result = execute_trade(signal, trade_plan, SYMBOL)"

    assert block_marker in source
    assert attempt_marker in source
    assert execute_marker in source

    block_pos = source.index(block_marker)
    attempt_pos = source.index(attempt_marker)

    # live_bot.py contains other execute_trade(...) calls earlier in the file.
    # Resolve the execution marker only after the Micro Momentum attempt marker
    # so this assertion verifies the intended execution path rather than the
    # first unrelated global execute_trade occurrence.
    execute_pos = source.index(execute_marker, attempt_pos)

    assert block_pos < attempt_pos
    assert block_pos < execute_pos
    assert attempt_pos < execute_pos

    assert "evaluate_intrabar_m15_direction_lock_guard" in source

    print("aligned_allowed=", aligned["allowed"])
    print("opposite_allowed=", blocked["allowed"])
    print("expired_allowed=", expired["allowed"])
    print("")
    print(
        "PASS: INTRABAR_MICRO_MOMENTUM reuses the existing M15 direction "
        "lock authority before execution: same-direction impulses remain "
        "eligible, opposite-direction impulses are blocked, expired/no-lock "
        "behavior is unchanged, and the legacy ASLS guard remains present."
    )


if __name__ == "__main__":
    main()
