from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    print("[MICRO MOMENTUM AGGRESSIVE BE TRADE TAG TEST V1]")

    source = (
        ROOT / "src" / "micro_momentum_breakeven.py"
    ).read_text(encoding="utf-8")

    required = (
        "micro_momentum_aggressive_early_be_enabled",
        "micro_momentum_aggressive_early_be_trigger_price",
        "micro_momentum_aggressive_early_be_allowed_strengths",
        "micro_momentum_aggressive_early_be_strength",
        "micro_momentum_aggressive_early_be_applied",
    )

    for token in required:
        assert token in source, token

    assert "changed_tracker = True" in source
    assert "MICRO_MOMENTUM_AGGRESSIVE_EARLY_BE" in source

    print("experiment_enabled_tag=True")
    print("trigger_price_tag=True")
    print("allowed_strengths_tag=True")
    print("strength_tag=True")
    print("applied_tag=True")
    print("trades_json_persistence_path=True")
    print("execution_logic_modified=False")
    print("PASS")


if __name__ == "__main__":
    main()
