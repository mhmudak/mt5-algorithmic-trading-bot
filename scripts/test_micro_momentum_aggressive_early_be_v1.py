from __future__ import annotations

from src.micro_momentum_breakeven import (
    evaluate_micro_momentum_aggressive_early_be,
)


def main():
    print("[MICRO MOMENTUM AGGRESSIVE EARLY BE TEST V1]")

    below = evaluate_micro_momentum_aggressive_early_be(
        signal="BUY",
        strength="NORMAL",
        entry_price=4250.00,
        current_price=4250.09,
        current_stop=4249.60,
        enabled=True,
        trigger_price=0.10,
        allowed_strengths=("NORMAL", "EXPLOSIVE"),
    )
    assert below["should_modify"] is False

    normal_buy = evaluate_micro_momentum_aggressive_early_be(
        signal="BUY",
        strength="NORMAL",
        entry_price=4250.00,
        current_price=4250.10,
        current_stop=4249.60,
        enabled=True,
        trigger_price=0.10,
        allowed_strengths=("NORMAL", "EXPLOSIVE"),
    )
    assert normal_buy["should_modify"] is True
    assert normal_buy["desired_stop"] == 4250.00

    explosive_sell = evaluate_micro_momentum_aggressive_early_be(
        signal="SELL",
        strength="EXPLOSIVE",
        entry_price=4250.00,
        current_price=4249.90,
        current_stop=4250.50,
        enabled=True,
        trigger_price=0.10,
        allowed_strengths=("NORMAL", "EXPLOSIVE"),
    )
    assert explosive_sell["should_modify"] is True
    assert explosive_sell["desired_stop"] == 4250.00

    tighter = evaluate_micro_momentum_aggressive_early_be(
        signal="BUY",
        strength="NORMAL",
        entry_price=4250.00,
        current_price=4250.20,
        current_stop=4250.05,
        enabled=True,
        trigger_price=0.10,
        allowed_strengths=("NORMAL", "EXPLOSIVE"),
    )
    assert tighter["should_modify"] is False

    weak = evaluate_micro_momentum_aggressive_early_be(
        signal="BUY",
        strength="WEAK_VALID",
        entry_price=4250.00,
        current_price=4250.50,
        current_stop=4249.70,
        enabled=True,
        trigger_price=0.10,
        allowed_strengths=("NORMAL", "EXPLOSIVE"),
    )
    assert weak["should_modify"] is False
    assert weak["reason"] == "strength_not_enabled"

    disabled = evaluate_micro_momentum_aggressive_early_be(
        signal="BUY",
        strength="NORMAL",
        entry_price=4250.00,
        current_price=4251.00,
        current_stop=4249.60,
        enabled=False,
        trigger_price=0.10,
        allowed_strengths=("NORMAL", "EXPLOSIVE"),
    )
    assert disabled["should_modify"] is False
    assert disabled["reason"] == "disabled"

    print("normal_plus_0_10_to_be=True")
    print("explosive_plus_0_10_to_be=True")
    print("weak_excluded=True")
    print("never_loosen_tighter_stop=True")
    print("boolean_off_restores_old_behavior=True")
    print("PASS")


if __name__ == "__main__":
    main()
