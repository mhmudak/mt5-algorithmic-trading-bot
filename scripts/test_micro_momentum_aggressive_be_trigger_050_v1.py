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
    print("[MICRO MOMENTUM AGGRESSIVE BE TRIGGER 0.50 TEST V1]")

    assert _value(
        "ENABLE_MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE"
    ) is True
    assert float(
        _value(
            "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE_TRIGGER_PRICE"
        )
    ) == 0.60
    assert tuple(
        _value(
            "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE_STRENGTHS"
        )
    ) == ("NORMAL", "EXPLOSIVE")
    assert tuple(
        _value(
            "MICRO_MOMENTUM_LIVE_ALLOWED_STRENGTHS"
        )
    ) == ("NORMAL", "EXPLOSIVE")

    print("aggressive_be_enabled=True")
    print("trigger_price=0.60")
    print('strengths=("NORMAL","EXPLOSIVE")')
    print("weak_valid_live=False")
    print("PASS")


if __name__ == "__main__":
    main()
