from pathlib import Path
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

TEST_ENV = os.environ.copy()

existing_pythonpath = TEST_ENV.get(
    "PYTHONPATH",
    "",
)

TEST_ENV["PYTHONPATH"] = (
    str(ROOT)
    if not existing_pythonpath
    else (
        str(ROOT)
        + os.pathsep
        + existing_pythonpath
    )
)

EXPECTED_BRANCH = "feature/rithmic-setup-verdict-supervisor"
EXPECTED_HEAD = "1c08471"


def git(*args):
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    return result


branch = git(
    "rev-parse",
    "--abbrev-ref",
    "HEAD",
).stdout.strip()

head = git(
    "rev-parse",
    "--short",
    "HEAD",
).stdout.strip()

if branch != EXPECTED_BRANCH:
    raise SystemExit(
        f"[STOP] branch mismatch: "
        f"expected={EXPECTED_BRANCH} got={branch}"
    )

if head != EXPECTED_HEAD:
    raise SystemExit(
        f"[STOP] HEAD mismatch: "
        f"expected={EXPECTED_HEAD} got={head}"
    )


# ============================================================
# DETERMINISTIC RITHMIC REGRESSION SUITE
# ============================================================

required_tests = [
    "scripts/test_rithmic_feed_integrity_v1.py",
    "scripts/test_rithmic_anti_fakeout_bridge_v1.py",
    "scripts/test_rithmic_absorption_exhaustion_v1.py",
    "scripts/test_rithmic_liquidity_pull_replenishment_v1.py",
    "scripts/test_rithmic_delta_price_divergence_v1.py",
    "scripts/test_rithmic_volume_profile_migration_v1.py",
    "scripts/test_rithmic_evidence_families_v2.py",
    "scripts/test_rithmic_evidence_families_bridge_v2.py",
    "scripts/test_phase5g_rithmic_evidence_watcher_v1.py",
    "scripts/test_phase5c_rithmic_state_supervisor_v1.py",
    "scripts/test_rithmic_setup_verdict_evidence_families_v2.py",
    "scripts/test_rithmic_setup_verdict_source_freshness_v2.py",
    "scripts/test_rithmic_setup_verdict_top_form_v1.py",
    "scripts/test_rithmic_setup_verdict_dual_v1_v2_display.py",
    "scripts/test_rithmic_state_cache_atomic_io_v1.py",
]


# Run these as well when present in this checkout.
optional_tests = [
    "scripts/test_rithmic_anti_fakeout_v1.py",
    "scripts/test_rithmic_order_flow_regime_v1.py",
    "scripts/test_rithmic_integrity_finalization.py",
    "scripts/test_rithmic_explicit_symbol_guard.py",
]


missing = [
    path
    for path in required_tests
    if not (ROOT / path).exists()
]

if missing:
    print("[STOP] required tests missing:")

    for path in missing:
        print(" -", path)

    raise SystemExit(1)


tests = list(required_tests)

for path in optional_tests:
    if (ROOT / path).exists():
        tests.append(path)


# Pick up known deterministic recovery/boundedness tests
# without broadly running every historical/live Rithmic script.
discovery_patterns = (
    "test_*rithmic*connection*recovery*.py",
    "test_*rithmic*bounded*.py",
    "test_*rithmic*cache*bounded*.py",
)

for pattern in discovery_patterns:
    for path in sorted(
        (ROOT / "scripts").glob(pattern)
    ):
        rel = path.relative_to(ROOT).as_posix()

        if rel not in tests:
            tests.append(rel)


print("=" * 100)
print("FINAL RITHMIC REGRESSION SUITE")
print("=" * 100)

failures = []

for i, rel in enumerate(
    tests,
    1,
):
    print()
    print(
        f"[{i}/{len(tests)}] {rel}"
    )
    print("-" * 100)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / rel),
        ],
        cwd=ROOT,
        env=TEST_ENV,
    )

    if result.returncode != 0:
        failures.append(
            (
                rel,
                result.returncode,
            )
        )


if failures:
    print()
    print("=" * 100)
    print("REGRESSION FAILURES")
    print("=" * 100)

    for rel, rc in failures:
        print(
            f"[FAIL] rc={rc} {rel}"
        )

    raise SystemExit(1)


# ============================================================
# COMPILE PRODUCTION + TEST SURFACE
# ============================================================

production_files = [
    "src/order_flow_features/rithmic_state_cache.py",
    "src/order_flow_features/rithmic_evidence_families.py",
    "src/rithmic_setup_verdict.py",
    "scripts/build_phase5g_rithmic_monitoring_bridge.py",
    "scripts/run_phase5g_rithmic_evidence_watcher.py",
    "scripts/run_phase5c_rithmic_state_supervisor.py",
]

compile_files = []

for rel in production_files + tests:
    path = ROOT / rel

    if path.exists():
        compile_files.append(
            str(path)
        )


print()
print("=" * 100)
print("PY_COMPILE")
print("=" * 100)

compile_result = subprocess.run(
    [
        sys.executable,
        "-m",
        "py_compile",
        *compile_files,
    ],
    cwd=ROOT,
)

if compile_result.returncode != 0:
    raise SystemExit(
        "[FAIL] py_compile"
    )

print(
    "[PASS] relevant production/tests compile"
)


# ============================================================
# EXECUTION-COUPLING SAFETY SCAN
# ============================================================

print()
print("=" * 100)
print("EXECUTION-COUPLING SAFETY SCAN")
print("=" * 100)

forbidden = (
    "MetaTrader5",
    "mt5.order_send",
    "order_send(",
    "place_order(",
    "execute_trade(",
    "modify_position(",
    "position_modify(",
)

safety_failures = []

for rel in production_files:
    path = ROOT / rel

    if not path.exists():
        continue

    source = path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    )

    for token in forbidden:
        if token in source:
            safety_failures.append(
                (
                    rel,
                    token,
                )
            )


if safety_failures:
    for rel, token in safety_failures:
        print(
            f"[FAIL] {rel}: "
            f"execution coupling token={token!r}"
        )

    raise SystemExit(1)

print(
    "[PASS] no MT5 order/position mutation "
    "coupling in the Rithmic production layer"
)


# ============================================================
# CRITICAL SAFETY CONTRACT
# ============================================================

print()
print("=" * 100)
print("OBSERVE-ONLY CONTRACT")
print("=" * 100)

evidence_source = (
    ROOT
    / "src"
    / "order_flow_features"
    / "rithmic_evidence_families.py"
).read_text(
    encoding="utf-8-sig",
)

verdict_source = (
    ROOT
    / "src"
    / "rithmic_setup_verdict.py"
).read_text(
    encoding="utf-8-sig",
)

required_markers = [
    (
        evidence_source,
        "decision_impact",
        "Evidence Families decision marker",
    ),
    (
        evidence_source,
        "can_influence_decision",
        "Evidence Families influence marker",
    ),
    (
        verdict_source,
        '"legacy_v1_mode": "SHADOW_ONLY"',
        "V1 shadow marker",
    ),
    (
        verdict_source,
        '"legacy_v1_can_influence_decision": False',
        "V1 non-authority marker",
    ),
    (
        verdict_source,
        "RITHMIC_EVIDENCE_FAMILIES_V2",
        "V2 verdict model marker",
    ),
]

for source, token, label in required_markers:
    if token not in source:
        raise SystemExit(
            f"[FAIL] missing: {label}"
        )

    print(
        f"[PASS] {label}"
    )


# ============================================================
# DIFF CHECK
# ============================================================

print()
print("=" * 100)
print("GIT DIFF CHECK")
print("=" * 100)

tracked_rithmic_files = [
    rel
    for rel in production_files
    if git(
        "ls-files",
        "--error-unmatch",
        rel,
    ).returncode == 0
]

tracked_test_files = [
    rel
    for rel in tests
    if git(
        "ls-files",
        "--error-unmatch",
        rel,
    ).returncode == 0
]

diff_check_files = (
    tracked_rithmic_files
    + tracked_test_files
)

diff_check = subprocess.run(
    [
        "git",
        "diff",
        "--check",
        "--",
        *diff_check_files,
    ],
    cwd=ROOT,
)

if diff_check.returncode != 0:
    raise SystemExit(
        "[FAIL] git diff --check"
    )

print(
    "[PASS] git diff --check"
)


# ============================================================
# FINAL STATUS
# ============================================================

print()
print("=" * 100)
print("FINAL RESULT")
print("=" * 100)

print(
    f"tests_run = {len(tests)}"
)

print(
    "[PASS] all deterministic Rithmic regressions"
)

print(
    "[PASS] compile validation"
)

print(
    "[PASS] execution-coupling safety scan"
)

print(
    "[PASS] observe-only authority contract"
)

print(
    "[PASS] atomic Phase 5C state writes"
)

print(
    "[PASS] V1 legacy remains shadow-only"
)

print(
    "[PASS] V2 Evidence Families remains "
    "production Rithmic verdict model"
)

print(
    "[PASS] READY FOR NEW-BRANCH / "
    "EXACT-STAGING AUDIT"
)
