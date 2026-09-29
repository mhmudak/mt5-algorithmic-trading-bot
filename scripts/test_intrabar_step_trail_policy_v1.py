from __future__ import annotations

from src.intrabar_step_trail_policy import (
    DEFAULT_POLICY,
    build_initial_stop,
    evaluate_early_failure,
    evaluate_profit_lock,
)


def main():
    print("[INTRABAR STEP TRAIL POLICY TEST V1]")

    assert build_initial_stop(
        signal="BUY",
        entry_price=4250.00,
    ) == 4243.00

    assert build_initial_stop(
        signal="SELL",
        entry_price=4250.00,
    ) == 4257.00

    pre = evaluate_profit_lock(
        signal="BUY",
        entry_price=4250.00,
        best_price=4250.59,
        current_stop=4243.00,
    )
    assert pre["should_modify"] is False
    assert pre["stage"] == "PRE_ACTIVATION"

    first = evaluate_profit_lock(
        signal="BUY",
        entry_price=4250.00,
        best_price=4250.60,
        current_stop=4243.00,
    )
    assert first["desired_stop"] == 4250.10
    assert first["lock_profit"] == 0.10
    assert first["should_modify"] is True

    step2 = evaluate_profit_lock(
        signal="BUY",
        entry_price=4250.00,
        best_price=4251.10,
        current_stop=4250.10,
    )
    assert step2["desired_stop"] == 4250.60
    assert step2["lock_profit"] == 0.60

    step3 = evaluate_profit_lock(
        signal="BUY",
        entry_price=4250.00,
        best_price=4251.60,
        current_stop=4250.60,
    )
    assert step3["desired_stop"] == 4251.10
    assert step3["lock_profit"] == 1.10

    # Never loosen a tighter existing BUY stop.
    tighter_buy = evaluate_profit_lock(
        signal="BUY",
        entry_price=4250.00,
        best_price=4251.60,
        current_stop=4251.25,
    )
    assert tighter_buy["desired_stop"] == 4251.25
    assert tighter_buy["should_modify"] is False

    sell_first = evaluate_profit_lock(
        signal="SELL",
        entry_price=4250.00,
        best_price=4249.40,
        current_stop=4257.00,
    )
    assert sell_first["desired_stop"] == 4249.90
    assert sell_first["lock_profit"] == 0.10

    sell_step = evaluate_profit_lock(
        signal="SELL",
        entry_price=4250.00,
        best_price=4248.90,
        current_stop=4249.90,
    )
    assert sell_step["desired_stop"] == 4249.40
    assert sell_step["lock_profit"] == 0.60

    # No early exit inside the grace period.
    grace = evaluate_early_failure(
        signal="BUY",
        entry_price=4250.00,
        current_price=4249.00,
        best_price=4250.20,
        age_seconds=1.0,
        opposite_impulse=True,
    )
    assert grace["should_exit"] is False
    assert grace["reason"] == "early_failure_grace_active"

    # Opposite impulse + meaningful adverse move after grace => early exit.
    failed = evaluate_early_failure(
        signal="BUY",
        entry_price=4250.00,
        current_price=4249.20,
        best_price=4250.20,
        age_seconds=2.5,
        opposite_impulse=True,
    )
    assert failed["should_exit"] is True
    assert failed["reason"] == "opposite_impulse_early_failure"

    # Once activation happened, trail owns the exit.
    trail_authority = evaluate_early_failure(
        signal="BUY",
        entry_price=4250.00,
        current_price=4250.30,
        best_price=4250.70,
        age_seconds=3.0,
        opposite_impulse=True,
    )
    assert trail_authority["should_exit"] is False
    assert trail_authority["reason"] == "profit_lock_authority_active"

    print(f"hard_stop_distance={DEFAULT_POLICY.hard_stop_distance}")
    print(f"activation_profit={DEFAULT_POLICY.activation_profit}")
    print(f"first_lock_profit={DEFAULT_POLICY.first_lock_profit}")
    print(f"trail_step={DEFAULT_POLICY.trail_step}")
    print(f"trail_gap={DEFAULT_POLICY.trail_gap}")
    print("buy_initial_stop=4243.0")
    print("buy_first_lock=4250.1")
    print("buy_second_lock=4250.6")
    print("sell_initial_stop=4257.0")
    print("sell_first_lock=4249.9")
    print("never_loosen_stop=True")
    print("early_failure_before_activation=True")
    print("trail_authority_after_activation=True")
    print(
        "PASS: INTRABAR_STEP_TRAIL V1 policy is deterministic: $7 hard stop, "
        "+$0.60 activation, +$0.10 first profit lock, +$0.50 discrete MFE "
        "steps, monotonic SL protection, and separate pre-activation early "
        "failure authority."
    )


if __name__ == "__main__":
    main()
