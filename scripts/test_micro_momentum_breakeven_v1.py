from __future__ import annotations

from src.micro_momentum_breakeven import evaluate_micro_momentum_breakeven


def main():
    print("[MICRO MOMENTUM BREAKEVEN TEST V1]")

    # WEAK_VALID geometry: 0.60 target -> BE after +0.30.
    buy_pre = evaluate_micro_momentum_breakeven(
        signal="BUY",
        entry_price=4250.00,
        original_take_profit=4250.60,
        current_price=4250.29,
        current_stop=4249.70,
    )
    assert buy_pre["should_modify"] is False
    assert buy_pre["trigger_distance"] == 0.30

    buy_hit = evaluate_micro_momentum_breakeven(
        signal="BUY",
        entry_price=4250.00,
        original_take_profit=4250.60,
        current_price=4250.30,
        current_stop=4249.70,
    )
    assert buy_hit["should_modify"] is True
    assert buy_hit["desired_stop"] == 4250.00

    # NORMAL geometry: 1.20 target -> BE after +0.60.
    normal = evaluate_micro_momentum_breakeven(
        signal="BUY",
        entry_price=4250.00,
        original_take_profit=4251.20,
        current_price=4250.60,
        current_stop=4249.60,
    )
    assert normal["should_modify"] is True
    assert normal["trigger_distance"] == 0.60

    # EXPLOSIVE geometry: 2.00 target -> BE after +1.00.
    explosive = evaluate_micro_momentum_breakeven(
        signal="SELL",
        entry_price=4250.00,
        original_take_profit=4248.00,
        current_price=4249.00,
        current_stop=4250.50,
    )
    assert explosive["should_modify"] is True
    assert explosive["trigger_distance"] == 1.00
    assert explosive["desired_stop"] == 4250.00

    sell_pre = evaluate_micro_momentum_breakeven(
        signal="SELL",
        entry_price=4250.00,
        original_take_profit=4249.40,
        current_price=4249.71,
        current_stop=4250.30,
    )
    assert sell_pre["should_modify"] is False

    tighter_buy = evaluate_micro_momentum_breakeven(
        signal="BUY",
        entry_price=4250.00,
        original_take_profit=4250.60,
        current_price=4250.50,
        current_stop=4250.10,
    )
    assert tighter_buy["should_modify"] is False
    assert tighter_buy["reason"] == "stop_already_at_or_better_than_be"

    tighter_sell = evaluate_micro_momentum_breakeven(
        signal="SELL",
        entry_price=4250.00,
        original_take_profit=4249.40,
        current_price=4249.50,
        current_stop=4249.90,
    )
    assert tighter_sell["should_modify"] is False

    print("weak_be_trigger=50%_tp_distance=0.30")
    print("normal_be_trigger=50%_tp_distance=0.60")
    print("explosive_be_trigger=50%_tp_distance=1.00")
    print("desired_be_lock=entry_price_fallback_only")
    print("never_loosen_tighter_stop=True")
    print(
        "PASS: Micro Momentum BE protection moves SL to entry after 50% "
        "of original TP distance and never loosens an already tighter stop."
    )


if __name__ == "__main__":
    main()
