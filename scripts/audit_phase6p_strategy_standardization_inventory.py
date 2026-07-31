from pathlib import Path

STRATEGY_DIR = Path("src/strategies")

REQUIRED_FIELDS = [
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

print("\n[PHASE 6P] Strategy Standardization Inventory")
print("=" * 70)

legacy = []
standardized = []

for path in files:
    source = path.read_text(encoding="utf-8", errors="ignore")

    if "def generate_signal" not in source:
        continue

    present = [field for field in REQUIRED_FIELDS if field in source]
    missing = [field for field in REQUIRED_FIELDS if field not in source]

    strategy_names = []

    for line in source.splitlines():
        line = line.strip()

        if '"strategy":' in line or "'strategy':" in line or "STRATEGY_NAME =" in line:
            strategy_names.append(line)

    if missing:
        legacy.append((path.name, present, missing, strategy_names[:4]))
    else:
        standardized.append((path.name, strategy_names[:4]))

print(f"\nStandardized strategy files: {len(standardized)}")
for name, strategy_lines in standardized:
    print(f"  ✅ {name}")
    for s in strategy_lines:
        print(f"     {s}")

print(f"\nLegacy / partially standardized strategy files: {len(legacy)}")
for name, present, missing, strategy_lines in legacy:
    print(f"\n  ⚠️ {name}")
    print(f"     present: {', '.join(present) if present else 'none'}")
    print(f"     missing: {', '.join(missing)}")

    for s in strategy_lines:
        print(f"     {s}")

print("\n[SUMMARY]")
print(f"standardized={len(standardized)} legacy_or_partial={len(legacy)} total_checked={len(standardized) + len(legacy)}")