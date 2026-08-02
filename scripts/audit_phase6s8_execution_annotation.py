
from pathlib import Path
import json


FILES = {
    "settings": Path("config/settings.py"),
    "live_bot": Path("src/live_bot.py"),
    "module": Path("src/market_outlook_execution_annotation.py"),
    "test": Path("scripts/test_phase6s8_execution_annotation.py"),
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
        "ENABLE_PHASE6S_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION": "ENABLE_PHASE6S_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION = False" in settings,
        "PHASE6S_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION_DIR": "PHASE6S_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION_DIR" in settings,
    }

    output["live_bot_markers"] = {
        "annotation_import": "from src.market_outlook_execution_annotation import (" in live_bot,
        "annotation_helper": "def maybe_record_phase6s_runtime_outlook_execution_annotation(" in live_bot,
        "summary_capture": "phase6s_runtime_outlook_advisory_summary = maybe_notify_phase6s_runtime_outlook_advisory(" in live_bot,
        "record_call": "maybe_record_phase6s_runtime_outlook_execution_annotation(" in live_bot,
        "execute_trade": "execution_result = execute_trade(signal, trade_plan, SYMBOL)" in live_bot,
    }

    output["safety_contract"] = {
        "annotation_only": '"decision_impact": "ANNOTATION_ONLY"' in module,
        "cannot_execute": '"can_execute": False' in module,
        "cannot_block": '"can_block_trade": False' in module,
        "cannot_modify_risk": '"can_modify_risk": False' in module,
        "cannot_modify_entry_sl_tp": '"can_modify_entry_sl_tp": False' in module,
    }

    print(json.dumps(output, indent=2, default=str))
    print("[PASS] Phase 6S8 audit completed. No code was changed.")


if __name__ == "__main__":
    main()
