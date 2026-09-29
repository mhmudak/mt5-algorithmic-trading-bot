from __future__ import annotations

import ast
from pathlib import Path

from src.micro_momentum_breakeven import (
    evaluate_micro_momentum_aggressive_early_be,
)

ROOT = Path(__file__).resolve().parents[1]


def _value(name: str):
    tree = ast.parse(
        (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    )
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(name)


def main():
    print("[MICRO MOMENTUM AGGRESSIVE PROFIT LOCK 0.50 TEST V1]")

    assert _value(
        "ENABLE_MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE"
    ) is True
    assert float(
        _value(
            "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE_TRIGGER_PRICE"
        )
    ) == 0.60
    assert float(
        _value(
            "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE_LOCK_PRICE"
        )
    ) == 0.50

    buy = evaluate_micro_momentum_aggressive_early_be(
        signal="BUY",
        strength="NORMAL",
        entry_price=4250.00,
        current_price=4250.60,
        current_stop=4249.60,
        enabled=True,
        trigger_price=0.60,
        lock_price=0.50,
        allowed_strengths=("NORMAL", "EXPLOSIVE"),
    )
    assert buy["should_modify"] is True
    assert abs(buy["desired_stop"] - 4250.50) < 1e-9

    sell = evaluate_micro_momentum_aggressive_early_be(
        signal="SELL",
        strength="EXPLOSIVE",
        entry_price=4250.00,
        current_price=4249.40,
        current_stop=4250.50,
        enabled=True,
        trigger_price=0.60,
        lock_price=0.50,
        allowed_strengths=("NORMAL", "EXPLOSIVE"),
    )
    assert sell["should_modify"] is True
    assert abs(sell["desired_stop"] - 4249.50) < 1e-9

    invalid = evaluate_micro_momentum_aggressive_early_be(
        signal="BUY",
        strength="NORMAL",
        entry_price=4250.00,
        current_price=4251.00,
        current_stop=4249.60,
        enabled=True,
        trigger_price=0.40,
        lock_price=0.50,
        allowed_strengths=("NORMAL", "EXPLOSIVE"),
    )
    assert invalid["should_modify"] is False
    assert invalid["reason"] == "invalid_trigger_lock_geometry"

    print("trigger_price=0.60")
    print("lock_price=0.50")
    print("buy_stop=entry_plus_0.50")
    print("sell_stop=entry_minus_0.50")
    print("lot_independent=True")
    print("PASS")


if __name__ == "__main__":
    main()
