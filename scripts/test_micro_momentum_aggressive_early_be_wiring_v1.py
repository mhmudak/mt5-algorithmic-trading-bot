from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _value(name: str):
    path = ROOT / "config" / "settings.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
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
    print("[MICRO MOMENTUM AGGRESSIVE EARLY BE WIRING TEST V1]")

    source = (
        ROOT / "src" / "micro_momentum_breakeven.py"
    ).read_text(encoding="utf-8")

    assert _value(
        "ENABLE_MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE"
    ) is True
    assert float(
        _value(
            "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE_TRIGGER_PRICE"
        )
    ) == 0.10
    assert tuple(
        _value(
            "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE_STRENGTHS"
        )
    ) == ("NORMAL", "EXPLOSIVE")

    assert (
        "evaluate_micro_momentum_aggressive_early_be("
        in source
    )
    assert "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE" in source
    assert "micro_momentum_aggressive_early_be_applied" in source
    assert "MICRO_MOMENTUM_BREAKEVEN_TP_PROGRESS" in source
    assert "MICRO_MOMENTUM_PROFIT_CAPTURE_PRICE" in source

    print("boolean_toggle=True")
    print("trigger_price=0.10")
    print('strengths=("NORMAL","EXPLOSIVE")')
    print("existing_50pct_be_retained=True")
    print("profit_capture_retained=True")
    print("PASS")


if __name__ == "__main__":
    main()
