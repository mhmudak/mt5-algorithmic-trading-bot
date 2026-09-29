from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "config" / "settings.py"
LIVE_BOT = ROOT / "src" / "live_bot.py"


def main():
    print("[FCR NATIVE DIRECTIONAL AUTHORITY TEST V2]")

    settings = SETTINGS.read_text(encoding="utf-8")
    live = LIVE_BOT.read_text(encoding="utf-8")

    ast.parse(settings)
    ast.parse(live)

    required_settings = [
        "FCR_M1_FVG_NATIVE_DIRECTIONAL_AUTHORITY = True",
    ]
    required_live = [
        "FCR_M1_FVG_NATIVE_DIRECTIONAL_AUTHORITY,",
        "fcr_native_directional_authority = (",
        'strategy_name == "FCR_M1_FVG"',
        "fcr_native_directional_authority",
        "FCR native directional authority: counter-bias",
        "not fcr_native_directional_authority",
        "run_tracked_setup_confirmation_gate(",
        "build_mtf_conflict_scalp_trade_plan(",
    ]

    for snippet in required_settings:
        if snippet not in settings:
            raise AssertionError(f"missing setting wiring: {snippet}")

    for snippet in required_live:
        if snippet not in live:
            raise AssertionError(f"missing live wiring: {snippet}")

    if '"FCR_M1_FVG",' in _extract_m5_confirmation_block(settings):
        raise AssertionError(
            "FCR_M1_FVG must remain outside generic M5 execution confirmation"
        )

    print(
        "\nPASS: FCR_M1_FVG owns generic MTF/HTF directional confirmation, "
        "stays on its native execution path, and remains outside generic M5 "
        "execution confirmation. Shared MTF machinery remains present for "
        "other strategies."
    )


def _extract_m5_confirmation_block(settings):
    marker = "M5_EXECUTION_CONFIRMATION_STRATEGIES"
    start = settings.find(marker)
    if start < 0:
        raise AssertionError("M5 execution confirmation list missing")
    end = settings.find("]", start)
    if end < 0:
        raise AssertionError("M5 execution confirmation list malformed")
    return settings[start:end + 1]


if __name__ == "__main__":
    main()
