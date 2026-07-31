
from pathlib import Path
import ast

targets = [
    ("src/strategies/strategy_triangle_pennant.py", "TRIANGLE_PENNANT", "PHASE_6O2_EXISTING_TRIANGLE_PENNANT_STANDARDIZED"),
    ("src/strategies/strategy_flag.py", "FLAG", "PHASE_6O2_EXISTING_FLAG_STANDARDIZED"),
    ("src/strategies/strategy_flag_refined.py", "FLAG_REFINED", "PHASE_6O2_EXISTING_FLAG_REFINED_STANDARDIZED"),
]

required_text = [
    "import hashlib",
    "PHASE6O2_OUTPUT_STANDARDIZED = True",
    "def _generate_signal_raw(df):",
    "def _phase6o2_risk_reward",
    "def _phase6o2_setup_id",
    "def _phase6o2_standardize_signal",
    "def generate_signal(df):",
    "setup_id",
    "entry_reference",
    "min_required_score",
    "rr",
    "risk_reward",
    "auto_trade_allowed",
    "decision_impact",
    "duplicate_policy",
    "orderflow_status",
]

for file_path, strategy, phase in targets:
    source = Path(file_path).read_text(encoding="utf-8")
    ast.parse(source)

    assert f'PHASE6O2_STRATEGY_NAME = "{strategy}"' in source, f"{strategy} strategy constant missing"
    assert f'PHASE6O2_PHASE_NAME = "{phase}"' in source, f"{strategy} phase constant missing"

    for text in required_text:
        assert text in source, f"{file_path} missing {text}"

    assert source.count("def generate_signal(df):") == 1, f"{file_path} must expose one generate_signal wrapper"

print("[PASS] Phase 6O2 existing triangle/flag chart-pattern outputs are standardized.")
