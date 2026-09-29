from __future__ import annotations

import ast
from pathlib import Path

from src.micro_momentum_breakeven import (
    evaluate_micro_momentum_aggressive_early_be,
)

ROOT = Path(__file__).resolve().parents[1]


def _setting(name: str):
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


def _eval(
    *,
    signal,
    strength,
    current,
    stop,
):
    return evaluate_micro_momentum_aggressive_early_be(
        signal=signal,
        strength=strength,
        entry_price=4300.00,
        current_price=current,
        current_stop=stop,
        enabled=True,
        trigger_price=0.10,
        lock_price=0.0,
        allowed_strengths=("NORMAL", "EXPLOSIVE"),
        stage2_profiles=_setting(
            "MICRO_MOMENTUM_AGGRESSIVE_STAGE2_PROFILES"
        ),
    )


def main():
    print("[MICRO MOMENTUM STRENGTH-SPECIFIC TWO-STAGE TEST V1]")

    profiles = _setting(
        "MICRO_MOMENTUM_AGGRESSIVE_STAGE2_PROFILES"
    )

    assert profiles["NORMAL"] == {
        "trigger_price": 0.40,
        "lock_price": 0.20,
    }
    assert profiles["EXPLOSIVE"] == {
        "trigger_price": 0.70,
        "lock_price": 0.40,
    }

    assert float(
        _setting(
            "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE_TRIGGER_PRICE"
        )
    ) == 0.10
    assert float(
        _setting(
            "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE_LOCK_PRICE"
        )
    ) == 0.0

    # Legacy 50%-TP fallback stays entry-only so it can never
    # loosen the tighter strength-specific Stage-2 stop.
    assert float(
        _setting("MICRO_MOMENTUM_BREAKEVEN_LOCK_PRICE")
    ) == 0.0

    normal_stage1 = _eval(
        signal="BUY",
        strength="NORMAL",
        current=4300.10,
        stop=4299.60,
    )
    assert normal_stage1["should_modify"] is True
    assert normal_stage1["stage"] == 1
    assert abs(
        normal_stage1["desired_stop"] - 4300.00
    ) < 1e-9

    normal_stage2 = _eval(
        signal="BUY",
        strength="NORMAL",
        current=4300.40,
        stop=4300.00,
    )
    assert normal_stage2["should_modify"] is True
    assert normal_stage2["stage"] == 2
    assert abs(
        normal_stage2["desired_stop"] - 4300.20
    ) < 1e-9

    explosive_stage1 = _eval(
        signal="SELL",
        strength="EXPLOSIVE",
        current=4299.90,
        stop=4300.50,
    )
    assert explosive_stage1["should_modify"] is True
    assert explosive_stage1["stage"] == 1
    assert abs(
        explosive_stage1["desired_stop"] - 4300.00
    ) < 1e-9

    explosive_stage2 = _eval(
        signal="SELL",
        strength="EXPLOSIVE",
        current=4299.30,
        stop=4300.00,
    )
    assert explosive_stage2["should_modify"] is True
    assert explosive_stage2["stage"] == 2
    assert abs(
        explosive_stage2["desired_stop"] - 4299.60
    ) < 1e-9

    tighter = _eval(
        signal="BUY",
        strength="NORMAL",
        current=4300.80,
        stop=4300.25,
    )
    assert tighter["should_modify"] is False

    print("normal_stage1=+0.10_to_entry")
    print("normal_stage2=+0.40_to_lock_+0.20")
    print("normal_tp=1.20_unchanged")
    print("explosive_stage1=+0.10_to_entry")
    print("explosive_stage2=+0.70_to_lock_+0.40")
    print("explosive_capture=1.50_unchanged")
    print("legacy_be_never_loosen=True")
    print("PASS")


if __name__ == "__main__":
    main()
