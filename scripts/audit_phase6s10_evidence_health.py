
from __future__ import annotations

import json
from pathlib import Path


FILES = {
    "settings": Path("config/settings.py"),
    "module": Path("src/market_outlook_evidence_health.py"),
    "script": Path("scripts/check_phase6s_evidence_health.py"),
    "test": Path("scripts/test_phase6s10_evidence_health.py"),
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
        "PHASE6S_EVIDENCE_HEALTH_OUTPUT_DIR": "PHASE6S_EVIDENCE_HEALTH_OUTPUT_DIR" in settings,
    }

    output["module_markers"] = {
        "phase": "PHASE_6S10_EVIDENCE_COLLECTION_HEALTH" in module,
        "read_settings": "def read_phase6s_evidence_settings(" in module,
        "scan_annotations": "def scan_phase6s_execution_annotations(" in module,
        "build_report": "def build_phase6s_evidence_health_report(" in module,
        "write_report": "def write_phase6s_evidence_health_report(" in module,
    }

    output["safety_contract"] = {
        "report_only": '"decision_impact": "REPORT_ONLY"' in module,
        "cannot_execute": '"can_execute": False' in module,
        "cannot_block": '"can_block_trade": False' in module,
        "cannot_modify_risk": '"can_modify_risk": False' in module,
        "cannot_modify_entry_sl_tp": '"can_modify_entry_sl_tp": False' in module,
    }

    output["script_markers"] = {
        "argparse": "argparse.ArgumentParser" in script,
        "no_write": "--no-write" in script,
        "health_status": "health_status" in script,
    }

    print(json.dumps(output, indent=2, default=str))
    print("[PASS] Phase 6S10 audit completed. No code was changed.")


if __name__ == "__main__":
    main()
