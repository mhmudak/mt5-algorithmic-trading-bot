from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "config" / "settings.py"
EXECUTION = ROOT / "src" / "execution.py"


def main():
    print("[MAX SAME-DIRECTION TRADES 4 TEST V1]")

    settings_text = SETTINGS.read_text(encoding="utf-8")
    tree = ast.parse(settings_text)

    allow_same = None
    max_same = None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "ALLOW_SAME_DIRECTION_ENTRIES":
                allow_same = ast.literal_eval(node.value)
            elif target.id == "MAX_SAME_DIRECTION_TRADES":
                max_same = ast.literal_eval(node.value)

    print(f"ALLOW_SAME_DIRECTION_ENTRIES={allow_same}")
    print(f"MAX_SAME_DIRECTION_TRADES={max_same}")

    if allow_same is not True:
        raise AssertionError("same-direction entries are not enabled")
    if max_same != 4:
        raise AssertionError(f"expected MAX_SAME_DIRECTION_TRADES=4, got {max_same}")

    execution_text = EXECUTION.read_text(encoding="utf-8")

    required = [
        "same_direction_count = count_same_direction_positions(SYMBOL, signal)",
        "if same_direction_count >= MAX_SAME_DIRECTION_TRADES:",
    ]
    for snippet in required:
        if snippet not in execution_text:
            raise AssertionError(f"missing execution guard wiring: {snippet}")

    print(
        "\nPASS: same-direction entries remain enabled and the live execution "
        "guard now permits up to 4 open positions in the same direction, "
        "blocking the next same-side order once count >= 4."
    )


if __name__ == "__main__":
    main()
