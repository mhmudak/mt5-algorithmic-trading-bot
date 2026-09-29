from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    print("[MICRO MOMENTUM ALL STRENGTHS LIVE TEST V1]")

    settings_path = ROOT / "config" / "settings.py"
    settings_text = settings_path.read_text(encoding="utf-8")
    tree = ast.parse(settings_text)

    allowed = None
    live_enabled = None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "MICRO_MOMENTUM_LIVE_ALLOWED_STRENGTHS":
                allowed = ast.literal_eval(node.value)
            elif target.id == "ENABLE_INTRABAR_MICRO_MOMENTUM_LIVE":
                live_enabled = ast.literal_eval(node.value)

    print(f"live_enabled={live_enabled}")
    print(f"live_allowed_strengths={allowed}")

    expected = ("WEAK_VALID", "NORMAL", "EXPLOSIVE")

    assert_true(live_enabled is True, "Micro Momentum live unexpectedly disabled")
    assert_true(
        allowed == expected,
        f"unexpected live strength tuple: {allowed}",
    )

    live_text = (ROOT / "src" / "live_bot.py").read_text(
        encoding="utf-8"
    )

    assert_true(
        "MICRO_MOMENTUM_LIVE_ALLOWED_STRENGTHS" in live_text,
        "live strength gate missing",
    )
    assert_true(
        "process_intrabar_micro_momentum_live(" in live_text,
        "live execution path missing",
    )
    assert_true(
        "[MICRO MOMENTUM FINAL GEOMETRY]" in (
            ROOT / "src" / "order_executor.py"
        ).read_text(encoding="utf-8"),
        "final geometry authority missing",
    )

    print(
        "\nPASS: WEAK_VALID, NORMAL, and EXPLOSIVE all retain live execution "
        "authority while the final Micro Momentum execution-geometry fix "
        "remains in place."
    )


if __name__ == "__main__":
    main()
