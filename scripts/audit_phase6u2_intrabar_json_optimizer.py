
from __future__ import annotations

import json
from pathlib import Path


FILES = {
    "settings": Path("config/settings.py"),
    "module": Path("src/intrabar_json_optimization_report.py"),
    "script": Path("scripts/run_phase6u_intrabar_json_optimization_report.py"),
    "test": Path("scripts/test_phase6u2_intrabar_json_optimizer.py"),
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
        "OUTPUT_DIR": "PHASE6U_INTRABAR_JSON_OPTIMIZATION_OUTPUT_DIR" in settings,
        "ALLOWED_STRATEGIES": "PHASE6U_INTRABAR_JSON_OPTIMIZATION_ALLOWED_STRATEGIES" in settings,
        "BLOCK_OTHERS_TRUE": "PHASE6U_INTRABAR_JSON_OPTIMIZATION_BLOCK_OTHERS = True" in settings,
    }

    output["module_markers"] = {
        "phase": "PHASE_6U2_INTRABAR_JSON_OPTIMIZATION_REPORT" in module,
        "parse_policy_key": "def parse_policy_key(" in module,
        "extract_rows": "def extract_intrabar_performance_rows(" in module,
        "build_report": "def build_phase6u_intrabar_json_optimization_report(" in module,
        "write_report": "def write_phase6u_intrabar_json_optimization_report(" in module,
        "format_report": "def format_phase6u_intrabar_json_optimization_report(" in module,
    }

    output["safety_contract"] = {
        "report_only": '"decision_impact": "REPORT_ONLY"' in module,
        "cannot_execute": '"can_execute": False' in module,
        "cannot_block_trade": '"can_block_trade": False' in module,
        "cannot_modify_risk": '"can_modify_risk": False' in module,
        "cannot_modify_entry_sl_tp": '"can_modify_entry_sl_tp": False' in module,
        "cannot_modify_detection": '"can_modify_detection": False' in module,
    }

    output["script_markers"] = {
        "argparse": "argparse.ArgumentParser" in script,
        "no_write": "--no-write" in script,
        "allowed_strategy": "--allowed-strategy" in script,
        "do_not_block_others": "--do-not-block-others" in script,
    }

    print(json.dumps(output, indent=2, default=str))
    print("[PASS] Phase 6U2 audit completed. No code was changed.")


if __name__ == "__main__":
    main()
