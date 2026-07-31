
from pathlib import Path
import ast

path = Path("src/strategies/strategy_head_shoulders.py")
source = path.read_text(encoding="utf-8")
tree = ast.parse(source)

assert "import hashlib" in source, "hashlib import missing"
assert 'STRATEGY_NAME = "HEAD_SHOULDERS"' in source, "STRATEGY_NAME missing"
assert 'PHASE_NAME = "PHASE_6N_EXISTING_HEAD_SHOULDERS_STANDARDIZED"' in source, "PHASE_NAME missing"
assert "def _risk_reward" in source, "_risk_reward helper missing"
assert "def _setup_id" in source, "_setup_id helper missing"
assert "def _standardize_signal" in source, "_standardize_signal helper missing"
assert source.count("return _standardize_signal({") == 4, "Expected four standardized return payloads"

required_fields = [
    "phase",
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

for field in required_fields:
    assert field in source, f"Missing standardized field: {field}"

print("[PASS] Phase 6N2 existing HEAD_SHOULDERS output is standardized.")
