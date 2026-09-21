from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "config" / "settings.py"
LIVE = ROOT / "src" / "live_bot.py"
OBSERVER = ROOT / "src" / "fcr_m1_fvg_regime_shadow.py"
EVALUATOR = ROOT / "scripts" / "evaluate_fcr_m1_fvg_regime_shadow_v1.py"
WRAPPER = ROOT / "scripts" / "run_live_bot_research_shadow_fcr_regime.py"


def main():
    settings = SETTINGS.read_text(
        encoding="utf-8",
        errors="replace",
    )
    live = LIVE.read_text(
        encoding="utf-8",
        errors="replace",
    )
    observer = OBSERVER.read_text(
        encoding="utf-8",
        errors="replace",
    )
    evaluator = EVALUATOR.read_text(
        encoding="utf-8",
        errors="replace",
    )
    wrapper = WRAPPER.read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "ENABLE_FCR_M1_FVG_REGIME_SHADOW = False" in settings

    fixed = re.search(
        r"(?m)^FIXED_LOT\s*=\s*([0-9.]+)\s*$",
        settings,
    )
    assert fixed
    assert float(fixed.group(1)) == 0.25

    assert "FCR_REGIME_SHADOW_OBSERVER_V1" in live
    assert "persist_fcr_regime_shadow_observation" in live
    assert "regime shadow detected" in live

    assert '"decision_impact": "OBSERVE_ONLY"' in observer
    assert '"execution_authority": False' in observer
    assert "execute_trade(" not in observer
    assert "order_send(" not in observer

    assert "SETUP_WIN_USD = 10.0" in evaluator
    assert 'if int(bar["time"]) > observed' in evaluator

    assert (
        "settings.ENABLE_FCR_M1_FVG_REGIME_SHADOW = True"
        in wrapper
    )
    assert (
        '"scripts.run_live_bot_research_shadow"'
        in wrapper
    )

    print("PASS: FCR regime shadow committed disabled by default")
    print("PASS: research wrapper enables observer for that process only")
    print("PASS: observer has execution_authority=False")
    print("PASS: observer contains no direct trade/order call")
    print("PASS: evaluator uses future M1 bars only")
    print("PASS: Setup Win remains favorable +$10")
    print("PASS: FIXED_LOT remains exactly 0.25")


if __name__ == "__main__":
    main()
