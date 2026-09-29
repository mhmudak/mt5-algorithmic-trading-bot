from pathlib import Path
import datetime
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_BRANCH = "feature/rithmic-setup-verdict-supervisor"
EXPECTED_HEAD = "1c08471"

FRESHNESS_TEST = (
    ROOT
    / "scripts"
    / "test_rithmic_setup_verdict_source_freshness_v2.py"
)

MIGRATION_HELPER = (
    ROOT
    / "scripts"
    / "patch_rithmic_setup_verdict_evidence_families_v2.py"
)

NEW_VERDICT_TEST = (
    ROOT
    / "scripts"
    / "test_rithmic_setup_verdict_evidence_families_v2.py"
)

stamp = datetime.datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

backup_dir = (
    ROOT
    / "local_backups"
    / f"rithmic_verdict_v2_retry_{stamp}"
)


def run(*args, check=True):
    result = subprocess.run(
        list(args),
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    if check and result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)

        raise RuntimeError(
            f"command failed rc={result.returncode}: "
            f"{' '.join(args)}"
        )

    return result


branch = run(
    "git",
    "rev-parse",
    "--abbrev-ref",
    "HEAD",
).stdout.strip()

head = run(
    "git",
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

for required in (
    FRESHNESS_TEST,
    MIGRATION_HELPER,
):
    if not required.exists():
        raise SystemExit(
            f"[STOP] missing required file: "
            f"{required.relative_to(ROOT)}"
        )

# The failed migration should have removed its new test.
if NEW_VERDICT_TEST.exists():
    raise SystemExit(
        "[STOP] migration test unexpectedly exists; "
        "verify rollback state before retrying"
    )

cached = subprocess.run(
    [
        "git",
        "diff",
        "--cached",
        "--quiet",
        "--",
        str(FRESHNESS_TEST.relative_to(ROOT)),
    ],
    cwd=ROOT,
)

if cached.returncode != 0:
    raise SystemExit(
        "[STOP] freshness test has staged changes"
    )


text = FRESHNESS_TEST.read_text(
    encoding="utf-8-sig",
)


# ------------------------------------------------------------
# Synthetic V2 payload for the existing freshness regression.
# This keeps that test focused on freshness/sample guards.
# ------------------------------------------------------------

main_anchor = '''def main() -> None:
'''

payload_helper = '''def evidence_families_payload() -> dict:
    def family(
        state: str,
        reason: str,
    ) -> dict:
        return {
            "state": state,
            "reason": reason,
            "available": state != "UNAVAILABLE",
            "directional": state in {
                "BUY",
                "SELL",
            },
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "safe_for_execution": False,
        }

    return {
        "engine": "RITHMIC_EVIDENCE_FAMILIES_V2",
        "feed_gate": {
            "usable": True,
            "reason": "healthy",
        },
        "families": {
            "AGGRESSION": family(
                "BUY",
                "synthetic_fresh_buy_aggression",
            ),
            "AUCTION_PROFILE": family(
                "BUY",
                "synthetic_fresh_buy_profile",
            ),
            "FOOTPRINT_ACCEPTANCE": family(
                "UNAVAILABLE",
                "independent_price_level_footprint_not_ready",
            ),
            "ABSORPTION_EXHAUSTION": family(
                "NEUTRAL",
                "no_absorption_event",
            ),
            "LIQUIDITY_DYNAMICS": family(
                "NEUTRAL",
                "stable_or_mixed_liquidity",
            ),
            "DIVERGENCE_TRAP": family(
                "NEUTRAL",
                "no_independent_trap_signal",
            ),
        },
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
    }


def main() -> None:
'''

if text.count(main_anchor) != 1:
    raise SystemExit(
        "[STOP] main-function anchor mismatch"
    )

text = text.replace(
    main_anchor,
    payload_helper,
    1,
)


# ------------------------------------------------------------
# Save the future V2 loader before monkeypatching it.
# ------------------------------------------------------------

registration_anchor = '''    original_registration_path = verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH
    try:
'''

registration_replacement = '''    original_registration_path = verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH
    original_evidence_loader = getattr(
        verdict_module,
        "_load_phase5g_evidence_families_v2",
        None,
    )

    try:
'''

if text.count(registration_anchor) != 1:
    raise SystemExit(
        "[STOP] registration backup anchor mismatch"
    )

text = text.replace(
    registration_anchor,
    registration_replacement,
    1,
)


# ------------------------------------------------------------
# Once the temporary registration is installed, also supply
# the synthetic V2 payload.
# ------------------------------------------------------------

loader_anchor = '''            verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = registration_path

            context = {"rithmic": rithmic}
'''

loader_replacement = '''            verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = registration_path

            verdict_module._load_phase5g_evidence_families_v2 = (
                lambda symbol: (
                    evidence_families_payload(),
                    "ok",
                    0.2,
                )
            )

            context = {"rithmic": rithmic}
'''

if text.count(loader_anchor) != 1:
    raise SystemExit(
        "[STOP] V2 loader insertion anchor mismatch"
    )

text = text.replace(
    loader_anchor,
    loader_replacement,
    1,
)


# ------------------------------------------------------------
# Restore both test-time monkeypatches.
# ------------------------------------------------------------

finally_anchor = '''    finally:
        verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = original_registration_path

'''

finally_replacement = '''    finally:
        verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = original_registration_path

        if original_evidence_loader is not None:
            verdict_module._load_phase5g_evidence_families_v2 = (
                original_evidence_loader
            )
        elif hasattr(
            verdict_module,
            "_load_phase5g_evidence_families_v2",
        ):
            delattr(
                verdict_module,
                "_load_phase5g_evidence_families_v2",
            )

'''

if text.count(finally_anchor) != 1:
    raise SystemExit(
        "[STOP] finally anchor mismatch"
    )

text = text.replace(
    finally_anchor,
    finally_replacement,
    1,
)


backup_dir.mkdir(
    parents=True,
    exist_ok=False,
)

shutil.copy2(
    FRESHNESS_TEST,
    backup_dir / FRESHNESS_TEST.name,
)


try:
    FRESHNESS_TEST.write_text(
        text,
        encoding="utf-8",
        newline="\n",
    )

    compile_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(FRESHNESS_TEST),
        ],
        cwd=ROOT,
    )

    if compile_result.returncode != 0:
        raise RuntimeError(
            "freshness test compile failed"
        )

    print("")
    print(
        "[STEP] freshness regression updated "
        "for Evidence Families V2"
    )

    migration_result = subprocess.run(
        [
            sys.executable,
            str(MIGRATION_HELPER),
        ],
        cwd=ROOT,
    )

    if migration_result.returncode != 0:
        raise RuntimeError(
            "verdict V2 migration helper failed"
        )

    # Final direct verification after the inner migration succeeds.
    final_tests = (
        FRESHNESS_TEST,
        NEW_VERDICT_TEST,
    )

    for test in final_tests:
        if not test.exists():
            raise RuntimeError(
                f"expected test missing: "
                f"{test.relative_to(ROOT)}"
            )

        print("")
        print("=" * 80)
        print(test.relative_to(ROOT))
        print("=" * 80)

        result = subprocess.run(
            [
                sys.executable,
                str(test),
            ],
            cwd=ROOT,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"final regression failed: "
                f"{test.relative_to(ROOT)}"
            )

    diff_check = subprocess.run(
        [
            "git",
            "diff",
            "--check",
            "--",
            str(FRESHNESS_TEST.relative_to(ROOT)),
            "src/rithmic_setup_verdict.py",
        ],
        cwd=ROOT,
    )

    if diff_check.returncode != 0:
        raise RuntimeError(
            "git diff --check failed"
        )

except Exception:
    shutil.copy2(
        backup_dir / FRESHNESS_TEST.name,
        FRESHNESS_TEST,
    )

    print("")
    print(
        "[ROLLBACK] freshness regression restored."
    )
    print(
        "[NOTE] inner verdict helper performs "
        "its own rollback on migration failure."
    )

    raise


print("")
print(
    "[PASS] Evidence Families V2 verdict retry succeeded"
)
print(
    "[BACKUP]",
    backup_dir.relative_to(ROOT),
)
print(
    "[CHANGED]",
    FRESHNESS_TEST.relative_to(ROOT),
)
print(
    "[SAFETY] freshness regression now supplies "
    "V2 evidence instead of relying on raw-score semantics"
)
print(
    "[SAFETY] stale/missing/sample/DOM gates remain "
    "tested before directional-family scoring"
)
