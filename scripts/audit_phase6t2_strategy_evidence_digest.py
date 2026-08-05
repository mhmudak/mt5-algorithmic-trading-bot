
from __future__ import annotations

import json
from pathlib import Path


FILES = {
    "settings": Path("config/settings.py"),
    "module": Path("src/strategy_evidence_digest.py"),
    "script": Path("scripts/send_phase6t_strategy_evidence_digest.py"),
    "test": Path("scripts/test_phase6t2_strategy_evidence_digest.py"),
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
    module = FILES["module"].read_text(encoding="utf-8")
    script = FILES["script"].read_text(encoding="utf-8")

    output["settings_flags"] = {
        "PHASE6T_STRATEGY_EVIDENCE_DIGEST_OUTPUT_DIR": "PHASE6T_STRATEGY_EVIDENCE_DIGEST_OUTPUT_DIR" in settings,
        "PHASE6T_STRATEGY_EVIDENCE_DIGEST_SEND_TELEGRAM": "PHASE6T_STRATEGY_EVIDENCE_DIGEST_SEND_TELEGRAM = False" in settings,
    }

    output["module_markers"] = {
        "phase": "PHASE_6T2_STRATEGY_EVIDENCE_DIGEST" in module,
        "load_dashboard": "def load_phase6t_strategy_evidence_dashboard(" in module,
        "build_digest": "def build_phase6t_strategy_evidence_digest(" in module,
        "write_digest": "def write_phase6t_strategy_evidence_digest(" in module,
        "send_digest": "def maybe_send_phase6t_strategy_evidence_digest(" in module,
    }

    output["safety_contract"] = {
        "digest_only": '"decision_impact": "DIGEST_ONLY"' in module,
        "cannot_execute": '"can_execute": False' in module,
        "cannot_block": '"can_block_trade": False' in module,
        "cannot_modify_risk": '"can_modify_risk": False' in module,
        "cannot_modify_entry_sl_tp": '"can_modify_entry_sl_tp": False' in module,
        "cannot_modify_strategy_policy": '"can_modify_strategy_policy": False' in module,
    }

    output["script_markers"] = {
        "argparse": "argparse.ArgumentParser" in script,
        "send_telegram_flag": "--send-telegram" in script,
        "no_write": "--no-write" in script,
        "notifier_import": "from src.notifier import send_telegram_message" in script,
    }

    print(json.dumps(output, indent=2, default=str))
    print("[PASS] Phase 6T2 audit completed. No code was changed.")


if __name__ == "__main__":
    main()
