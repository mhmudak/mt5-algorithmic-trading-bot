
from __future__ import annotations

import json
from pathlib import Path


FILES = {
    "settings": Path("config/settings.py"),
    "module": Path("src/market_outlook_outcome_attribution.py"),
    "script": Path("scripts/run_phase6s_outcome_attribution_report.py"),
    "test": Path("scripts/test_phase6s9_outcome_attribution_report.py"),
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
        "PHASE6S_OUTCOME_ATTRIBUTION_OUTPUT_DIR": "PHASE6S_OUTCOME_ATTRIBUTION_OUTPUT_DIR" in settings,
        "PHASE6S_OUTCOME_ATTRIBUTION_MIN_SAMPLES": "PHASE6S_OUTCOME_ATTRIBUTION_MIN_SAMPLES" in settings,
    }

    output["module_markers"] = {
        "phase": "PHASE_6S9_OUTLOOK_OUTCOME_ATTRIBUTION_REPORT" in module,
        "load_annotations": "def load_phase6s_execution_annotations(" in module,
        "load_trade_outcomes": "def load_trade_outcomes(" in module,
        "build_report": "def build_phase6s_outcome_attribution_report(" in module,
        "write_report": "def write_phase6s_outcome_attribution_report(" in module,
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
        "default_annotation_dir": "data/reports/market_outlook/execution_annotations" in script,
        "writes_report": "write_phase6s_outcome_attribution_report" in script,
    }

    print(json.dumps(output, indent=2, default=str))
    print("[PASS] Phase 6S9 audit completed. No code was changed.")


if __name__ == "__main__":
    main()
