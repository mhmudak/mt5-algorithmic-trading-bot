from pathlib import Path
import ast

STRATEGY_DIR = Path("src/strategies")

REQUIRED_MARKERS = [
    "setup_id",
    "phase",
    "entry_reference",
    "rr",
    "risk_reward",
    "auto_trade_allowed",
    "decision_impact",
    "duplicate_policy",
]

files = sorted(STRATEGY_DIR.glob("strategy_*.py"))

assert len(files) == 53, f"Expected 53 strategy files, found {len(files)}"

failures = []

for path in files:
    source = path.read_text(encoding="utf-8")

    if "\ufeff" in source:
        failures.append(f"{path}: contains BOM U+FEFF")

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        failures.append(f"{path}: syntax error: {exc}")
        continue

    has_public_generate_signal = any(
        isinstance(node, ast.FunctionDef) and node.name == "generate_signal"
        for node in tree.body
    )

    if not has_public_generate_signal:
        failures.append(f"{path}: missing public generate_signal function")

    missing = [marker for marker in REQUIRED_MARKERS if marker not in source]
    if missing:
        failures.append(f"{path}: missing standardized markers: {', '.join(missing)}")

if failures:
    raise AssertionError("\n".join(failures))

print("[PASS] Phase 6P final audit: all 53 strategy outputs are standardized.")