
from __future__ import annotations

import json
from pathlib import Path


FILES = {
    "settings": Path("config/settings.py"),
    "module": Path("src/strategy_evidence_dashboard.py"),
    "script": Path("scripts/run_phase6t_strategy_evidence_dashboard.py"),
    "test": Path("scripts/test_phase6t1_strategy_evidence_dashboard.py"),
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
        "PHASE6T_STRATEGY_EVIDENCE_DASHBOARD_OUTPUT_DIR": "PHASE6T_STRATEGY_EVIDENCE_DASHBOARD_OUTPUT_DIR" in settings,
        "PHASE6T_STRATEGY_EVIDENCE_MIN_MATCHED_SAMPLES": "PHASE6T_STRATEGY_EVIDENCE_MIN_MATCHED_SAMPLES" in settings,
    }

    output["module_markers"] = {
        "phase": "PHASE_6T1_STRATEGY_EVIDENCE_DASHBOARD" in module,
        "load_attribution": "def load_phase6s_attribution_report(" in module,
        "classify": "def classify_strategy_evidence(" in module,
        "build_dashboard": "def build_phase6t_strategy_evidence_dashboard(" in module,
        "write_dashboard": "def write_phase6t_strategy_evidence_dashboard(" in module,
    }

    output["safety_contract"] = {
        "dashboard_only": '"decision_impact": "DASHBOARD_ONLY"' in module,
        "cannot_execute": '"can_execute": False' in module,
        "cannot_block": '"can_block_trade": False' in module,
        "cannot_modify_risk": '"can_modify_risk": False' in module,
        "cannot_modify_entry_sl_tp": '"can_modify_entry_sl_tp": False' in module,
        "cannot_modify_strategy_policy": '"can_modify_strategy_policy": False' in module,
    }

    output["script_markers"] = {
        "argparse": "argparse.ArgumentParser" in script,
        "no_write": "--no-write" in script,
        "strategy_rows": "strategy_rows" in script,
    }

    print(json.dumps(output, indent=2, default=str))
    print("[PASS] Phase 6T1 audit completed. No code was changed.")


if __name__ == "__main__":
    main()
