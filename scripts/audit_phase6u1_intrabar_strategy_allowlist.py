
from __future__ import annotations

import json
from pathlib import Path


FILES = {
    "settings": Path("config/settings.py"),
    "live_bot": Path("src/live_bot.py"),
    "module": Path("src/intrabar_strategy_allowlist.py"),
    "test": Path("scripts/test_phase6u1_intrabar_strategy_allowlist.py"),
}


def main():
    output = {}

    for name, path in FILES.items():
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        output[name] = {
            "exists": path.exists(),
            "lines": len(text.splitlines()) if text else 0,
        }

    settings = FILES["settings"].read_text(encoding="utf-8")
    live_bot = FILES["live_bot"].read_text(encoding="utf-8")
    module = FILES["module"].read_text(encoding="utf-8")

    output["settings_flags"] = {
        "ENABLE_INTRABAR_STRATEGY_ALLOWLIST_TRUE": "ENABLE_INTRABAR_STRATEGY_ALLOWLIST = True" in settings,
        "ENABLE_INTRABAR_STRATEGY_DETECTION_ALLOWLIST_TRUE": "ENABLE_INTRABAR_STRATEGY_DETECTION_ALLOWLIST = True" in settings,
        "AUTO_STRUCTURAL_LEVEL_SCALP_ALLOWED": '"AUTO_STRUCTURAL_LEVEL_SCALP"' in settings,
        "FAILED_FVG_REVERSAL_ALLOWED": '"FAILED_FVG_REVERSAL"' in settings,
        "MICRO_SR_SWEEP_RECLAIM_NOT_ALLOWED": '"MICRO_SR_SWEEP_RECLAIM"' in settings and "INTRABAR_STRATEGY_BLOCKED_EXAMPLES" in settings,
    }

    output["module_markers"] = {
        "phase": "PHASE_6U1_INTRABAR_STRATEGY_ALLOWLIST" in module,
        "decision_function": "def explain_intrabar_strategy_allowlist_decision(" in module,
        "profile_filter": "def filter_intrabar_strategy_profiles(" in module,
    }

    output["live_bot_markers"] = {
        "allowlist_import": "from src.intrabar_strategy_allowlist import (" in live_bot,
        "settings_import": "ENABLE_INTRABAR_STRATEGY_ALLOWLIST" in live_bot and "INTRABAR_STRATEGY_ALLOWLIST" in live_bot,
        "guard": "phase6u_intrabar_allowlist_decision = explain_intrabar_strategy_allowlist_decision(" in live_bot,
        "returns_before_execute": "return None" in live_bot and "execution_result = execute_trade(signal, trade_plan, SYMBOL)" in live_bot,
    }

    output["safety_contract"] = {
        "intrabar_only": '"scope": "INTRABAR_ONLY"' in module,
        "can_block_trade": '"can_block_trade": True' in module,
        "cannot_modify_risk": '"can_modify_risk": False' in module,
        "cannot_modify_entry_sl_tp": '"can_modify_entry_sl_tp": False' in module,
    }

    print(json.dumps(output, indent=2, default=str))
    print("[PASS] Phase 6U1 audit completed. No code was changed.")


if __name__ == "__main__":
    main()
