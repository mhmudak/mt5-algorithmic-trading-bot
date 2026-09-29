from __future__ import annotations

import ast
from pathlib import Path

from src.micro_momentum_breakeven import (
    evaluate_micro_momentum_aggressive_early_be,
)

ROOT = Path(__file__).resolve().parents[1]


def _value(name: str):
    tree = ast.parse(
        (ROOT / "config" / "settings.py").read_text(
            encoding="utf-8"
        )
    )
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"Missing setting: {name}")


def main():
    print("[MICRO MOMENTUM TWO-STAGE PROFIT PROTECTION TEST V1]")

    assert _value(
        "ENABLE_MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE"
    ) is True
    assert float(
        _value(
            "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE_TRIGGER_PRICE"
        )
    ) == 0.10
    assert float(
        _value(
            "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE_LOCK_PRICE"
        )
    ) == 0.0
    assert float(
        _value(
            "MICRO_MOMENTUM_BREAKEVEN_LOCK_PRICE"
        )
    ) == 0.50

    # Stage 1: +0.10 only protects entry, not +0.50.
    buy_early = evaluate_micro_momentum_aggressive_early_be(
        signal="BUY",
        strength="NORMAL",
        entry_price=4250.00,
        current_price=4250.10,
        current_stop=4249.60,
        enabled=True,
        trigger_price=0.10,
        lock_price=0.0,
        allowed_strengths=("NORMAL", "EXPLOSIVE"),
    )
    assert buy_early["should_modify"] is True
    assert abs(buy_early["desired_stop"] - 4250.00) < 1e-9

    sell_early = evaluate_micro_momentum_aggressive_early_be(
        signal="SELL",
        strength="EXPLOSIVE",
        entry_price=4250.00,
        current_price=4249.90,
        current_stop=4250.50,
        enabled=True,
        trigger_price=0.10,
        lock_price=0.0,
        allowed_strengths=("NORMAL", "EXPLOSIVE"),
    )
    assert sell_early["should_modify"] is True
    assert abs(sell_early["desired_stop"] - 4250.00) < 1e-9

    # An impossible trigger/lock pair must fail closed at policy level.
    impossible = evaluate_micro_momentum_aggressive_early_be(
        signal="BUY",
        strength="NORMAL",
        entry_price=4250.00,
        current_price=4250.10,
        current_stop=4249.60,
        enabled=True,
        trigger_price=0.10,
        lock_price=0.50,
        allowed_strengths=("NORMAL", "EXPLOSIVE"),
    )
    assert impossible["should_modify"] is False
    assert impossible["reason"] == "invalid_trigger_lock_geometry"

    print("stage1_trigger_price=0.10")
    print("stage1_lock_price=0.00")
    print("stage2_standard_be_lock_price=0.50")
    print("normal_stage2_trigger=0.60")
    print("explosive_stage2_trigger=1.00")
    print("impossible_0.10_trigger_0.50_lock_blocked=True")
    print("PASS")


if __name__ == "__main__":
    main()
