from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _assignment_value(path: Path, name: str):
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
    print("[MICRO MOMENTUM DISABLE WEAK LIVE TEST V1]")

    settings_path = ROOT / "config" / "settings.py"
    live = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")

    allowed = _assignment_value(
        settings_path,
        "MICRO_MOMENTUM_LIVE_ALLOWED_STRENGTHS",
    )
    assert tuple(allowed) == ("NORMAL", "EXPLOSIVE")

    assert _assignment_value(
        settings_path,
        "ENABLE_INTRABAR_MICRO_MOMENTUM_LIVE",
    ) is True

    assert _assignment_value(
        settings_path,
        "MICRO_MOMENTUM_TELEGRAM_ENABLED",
    ) is False

    assert float(
        _assignment_value(
            settings_path,
            "MICRO_MOMENTUM_PROFIT_CAPTURE_PRICE",
        )
    ) == 1.50

    assert "MICRO_MOMENTUM_LIVE_ALLOWED_STRENGTHS" in live

    print("weak_valid_live=False")
    print("normal_live=True")
    print("explosive_live=True")
    print("micro_strategy_live=True")
    print("profit_capture_retained=1.50")
    print("telegram_silence_retained=True")
    print("PASS")


if __name__ == "__main__":
    main()
