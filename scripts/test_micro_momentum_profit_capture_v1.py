from __future__ import annotations

from src.micro_momentum_breakeven import evaluate_micro_momentum_profit_capture


def main():
    print("[MICRO MOMENTUM PROFIT CAPTURE TEST V1]")

    weak = evaluate_micro_momentum_profit_capture(
        signal="BUY",
        entry_price=4250.00,
        original_take_profit=4250.60,
        current_price=4250.55,
        capture_price=1.50,
    )
    assert weak["should_close"] is False
    assert weak["reason"] == "original_tp_not_beyond_capture"

    normal = evaluate_micro_momentum_profit_capture(
        signal="SELL",
        entry_price=4250.00,
        original_take_profit=4248.80,
        current_price=4248.90,
        capture_price=1.50,
    )
    assert normal["should_close"] is False
    assert normal["reason"] == "original_tp_not_beyond_capture"

    explosive_buy_pre = evaluate_micro_momentum_profit_capture(
        signal="BUY",
        entry_price=4250.00,
        original_take_profit=4252.00,
        current_price=4251.49,
        capture_price=1.50,
    )
    assert explosive_buy_pre["should_close"] is False

    explosive_buy = evaluate_micro_momentum_profit_capture(
        signal="BUY",
        entry_price=4250.00,
        original_take_profit=4252.00,
        current_price=4251.50,
        capture_price=1.50,
    )
    assert explosive_buy["should_close"] is True
    assert explosive_buy["target_distance"] == 2.00
    assert explosive_buy["favorable_distance"] == 1.50

    explosive_sell = evaluate_micro_momentum_profit_capture(
        signal="SELL",
        entry_price=4250.00,
        original_take_profit=4248.00,
        current_price=4248.50,
        capture_price=1.50,
    )
    assert explosive_sell["should_close"] is True

    print("weak_original_tp_unchanged=True")
    print("normal_original_tp_unchanged=True")
    print("explosive_buy_close_at_plus_1_50=True")
    print("explosive_sell_close_at_plus_1_50=True")
    print(
        "PASS: smaller WEAK/NORMAL TPs remain authoritative, while Micro "
        "trades whose original TP is beyond $1.50 are fully closed at "
        "+$1.50 favorable price movement."
    )


if __name__ == "__main__":
    main()
