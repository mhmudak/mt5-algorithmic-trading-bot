from pathlib import Path
import datetime
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_BRANCH = "feature/rithmic-setup-verdict-supervisor"
EXPECTED_HEAD = "1c08471"

VERDICT = (
    ROOT
    / "src"
    / "rithmic_setup_verdict.py"
)

FRESHNESS_TEST = (
    ROOT
    / "scripts"
    / "test_rithmic_setup_verdict_source_freshness_v2.py"
)

TOP_FORM_TEST = (
    ROOT
    / "scripts"
    / "test_rithmic_setup_verdict_top_form_v1.py"
)

MIGRATION_HELPER = (
    ROOT
    / "scripts"
    / "patch_rithmic_setup_verdict_evidence_families_v2.py"
)

NEW_V2_TEST = (
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
    / f"rithmic_verdict_v2_fixture_migration_{stamp}"
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
        print(
            result.stderr,
            file=sys.stderr,
        )

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
    VERDICT,
    FRESHNESS_TEST,
    TOP_FORM_TEST,
    MIGRATION_HELPER,
):
    if not required.exists():
        raise SystemExit(
            f"[STOP] missing required file: "
            f"{required.relative_to(ROOT)}"
        )

if NEW_V2_TEST.exists():
    raise SystemExit(
        "[STOP] V2 verdict regression unexpectedly "
        "exists; rollback state is not what we expect"
    )


# ------------------------------------------------------------
# Ensure the failed migration really rolled back.
# ------------------------------------------------------------

verdict_before = VERDICT.read_text(
    encoding="utf-8-sig",
)

if (
    "RITHMIC_SETUP_EVIDENCE_FAMILY_MIN_COVERAGE"
    in verdict_before
):
    raise SystemExit(
        "[STOP] verdict already contains V2 migration; "
        "no changes made"
    )


# ------------------------------------------------------------
# Do not modify staged versions of these files.
# ------------------------------------------------------------

for path in (
    VERDICT,
    FRESHNESS_TEST,
    TOP_FORM_TEST,
):
    cached = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--quiet",
            "--",
            str(path.relative_to(ROOT)),
        ],
        cwd=ROOT,
    )

    if cached.returncode != 0:
        raise SystemExit(
            f"[STOP] staged changes detected: "
            f"{path.relative_to(ROOT)}"
        )


freshness_text = FRESHNESS_TEST.read_text(
    encoding="utf-8-sig",
)

top_text = TOP_FORM_TEST.read_text(
    encoding="utf-8-sig",
)


# ============================================================
# COMMON SYNTHETIC V2 PAYLOAD HELPER
# ============================================================

freshness_payload_helper = '''def evidence_families_payload() -> dict:
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


# ============================================================
# PATCH FRESHNESS REGRESSION
# ============================================================

anchor = '''def main() -> None:
'''

if freshness_text.count(anchor) != 1:
    raise SystemExit(
        "[STOP] freshness main anchor mismatch"
    )

freshness_text = freshness_text.replace(
    anchor,
    freshness_payload_helper,
    1,
)


anchor = '''    original_registration_path = verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH
    try:
'''

replacement = '''    original_registration_path = verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH
    original_evidence_loader = getattr(
        verdict_module,
        "_load_phase5g_evidence_families_v2",
        None,
    )

    try:
'''

if freshness_text.count(anchor) != 1:
    raise SystemExit(
        "[STOP] freshness registration anchor mismatch"
    )

freshness_text = freshness_text.replace(
    anchor,
    replacement,
    1,
)


anchor = '''            verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = registration_path

            context = {"rithmic": rithmic}
'''

replacement = '''            verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = registration_path

            verdict_module._load_phase5g_evidence_families_v2 = (
                lambda symbol: (
                    evidence_families_payload(),
                    "ok",
                    0.2,
                )
            )

            context = {"rithmic": rithmic}
'''

if freshness_text.count(anchor) != 1:
    raise SystemExit(
        "[STOP] freshness V2 loader anchor mismatch"
    )

freshness_text = freshness_text.replace(
    anchor,
    replacement,
    1,
)


anchor = '''    finally:
        verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = original_registration_path

'''

replacement = '''    finally:
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

if freshness_text.count(anchor) != 1:
    raise SystemExit(
        "[STOP] freshness finally anchor mismatch"
    )

freshness_text = freshness_text.replace(
    anchor,
    replacement,
    1,
)


# ============================================================
# PATCH TOP-FORM REGRESSION
# ============================================================

top_payload_helper = '''def _evidence_families_payload(
    *,
    aggression: str = "NEUTRAL",
    auction_profile: str = "NEUTRAL",
    footprint: str = "UNAVAILABLE",
    absorption: str = "NEUTRAL",
    liquidity: str = "NEUTRAL",
    divergence: str = "NEUTRAL",
) -> dict:
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
                aggression,
                "synthetic_aggression",
            ),
            "AUCTION_PROFILE": family(
                auction_profile,
                "synthetic_auction_profile",
            ),
            "FOOTPRINT_ACCEPTANCE": family(
                footprint,
                "synthetic_footprint",
            ),
            "ABSORPTION_EXHAUSTION": family(
                absorption,
                "synthetic_absorption",
            ),
            "LIQUIDITY_DYNAMICS": family(
                liquidity,
                "synthetic_liquidity",
            ),
            "DIVERGENCE_TRAP": family(
                divergence,
                "synthetic_divergence",
            ),
        },
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
    }


def main() -> None:
'''

anchor = '''def main() -> None:
'''

if top_text.count(anchor) != 1:
    raise SystemExit(
        "[STOP] top-form main anchor mismatch"
    )

top_text = top_text.replace(
    anchor,
    top_payload_helper,
    1,
)


anchor = '''    original_registration_path = (
        verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH
    )

    try:
'''

replacement = '''    original_registration_path = (
        verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH
    )
    original_evidence_loader = getattr(
        verdict_module,
        "_load_phase5g_evidence_families_v2",
        None,
    )

    active_evidence_payload = {
        "value": _evidence_families_payload()
    }

    try:
'''

if top_text.count(anchor) != 1:
    raise SystemExit(
        "[STOP] top-form registration anchor mismatch"
    )

top_text = top_text.replace(
    anchor,
    replacement,
    1,
)


anchor = '''            verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = (
                registration_path
            )

            current_like = _context(
'''

replacement = '''            verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = (
                registration_path
            )

            verdict_module._load_phase5g_evidence_families_v2 = (
                lambda symbol: (
                    active_evidence_payload["value"],
                    "ok",
                    0.2,
                )
            )

            current_like = _context(
'''

if top_text.count(anchor) != 1:
    raise SystemExit(
        "[STOP] top-form loader anchor mismatch"
    )

top_text = top_text.replace(
    anchor,
    replacement,
    1,
)


# ------------------------------------------------------------
# SUPPORT BUY:
# preserve the old test's expected 2 SUPPORT / 1 AGAINST,
# but make them independent top-level families.
# ------------------------------------------------------------

anchor = '''            support_buy = verdict_module.build_rithmic_setup_verdict(
'''

replacement = '''            active_evidence_payload["value"] = (
                _evidence_families_payload(
                    aggression="BUY",
                    auction_profile="BUY",
                    liquidity="SELL",
                )
            )

            support_buy = verdict_module.build_rithmic_setup_verdict(
'''

if top_text.count(anchor) != 1:
    raise SystemExit(
        "[STOP] support BUY anchor mismatch"
    )

top_text = top_text.replace(
    anchor,
    replacement,
    1,
)


# ------------------------------------------------------------
# AGAINST BUY:
# two independent SELL families.
# ------------------------------------------------------------

anchor = '''            against_buy = verdict_module.build_rithmic_setup_verdict(
'''

replacement = '''            active_evidence_payload["value"] = (
                _evidence_families_payload(
                    aggression="SELL",
                    auction_profile="SELL",
                )
            )

            against_buy = verdict_module.build_rithmic_setup_verdict(
'''

if top_text.count(anchor) != 1:
    raise SystemExit(
        "[STOP] against BUY anchor mismatch"
    )

top_text = top_text.replace(
    anchor,
    replacement,
    1,
)


# ------------------------------------------------------------
# SUPPORT SELL:
# same independent SELL agreement, setup-relative.
# ------------------------------------------------------------

anchor = '''            support_sell = verdict_module.build_rithmic_setup_verdict(
'''

replacement = '''            active_evidence_payload["value"] = (
                _evidence_families_payload(
                    aggression="SELL",
                    auction_profile="SELL",
                )
            )

            support_sell = verdict_module.build_rithmic_setup_verdict(
'''

if top_text.count(anchor) != 1:
    raise SystemExit(
        "[STOP] support SELL anchor mismatch"
    )

top_text = top_text.replace(
    anchor,
    replacement,
    1,
)


# ------------------------------------------------------------
# NEUTRAL:
# adequate coverage, zero directional family votes.
# ------------------------------------------------------------

anchor = '''            neutral = verdict_module.build_rithmic_setup_verdict(
'''

replacement = '''            active_evidence_payload["value"] = (
                _evidence_families_payload()
            )

            neutral = verdict_module.build_rithmic_setup_verdict(
'''

if top_text.count(anchor) != 1:
    raise SystemExit(
        "[STOP] neutral anchor mismatch"
    )

top_text = top_text.replace(
    anchor,
    replacement,
    1,
)


# ------------------------------------------------------------
# For guard tests below, make V2 strongly supportive so that
# the pre-V2 guards must be what prevents a decisive verdict.
# ------------------------------------------------------------

anchor = '''            low_sample = verdict_module.build_rithmic_setup_verdict(
'''

replacement = '''            active_evidence_payload["value"] = (
                _evidence_families_payload(
                    aggression="BUY",
                    auction_profile="BUY",
                )
            )

            low_sample = verdict_module.build_rithmic_setup_verdict(
'''

if top_text.count(anchor) != 1:
    raise SystemExit(
        "[STOP] low-sample anchor mismatch"
    )

top_text = top_text.replace(
    anchor,
    replacement,
    1,
)


# stale and mismatch can keep that same bullish V2 payload.
# Their gates must fire before V2 directional scoring.


# ------------------------------------------------------------
# Restore the V2 loader after the test.
# ------------------------------------------------------------

anchor = '''    finally:
        verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = (
            original_registration_path
        )

'''

replacement = '''    finally:
        verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = (
            original_registration_path
        )

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

if top_text.count(anchor) != 1:
    raise SystemExit(
        "[STOP] top-form finally anchor mismatch"
    )

top_text = top_text.replace(
    anchor,
    replacement,
    1,
)


# ============================================================
# BACKUP
# ============================================================

backup_dir.mkdir(
    parents=True,
    exist_ok=False,
)

for path in (
    VERDICT,
    FRESHNESS_TEST,
    TOP_FORM_TEST,
):
    shutil.copy2(
        path,
        backup_dir / path.name,
    )


new_test_existed_before = (
    NEW_V2_TEST.exists()
)


try:
    # --------------------------------------------------------
    # Write only the two test-fixture migrations first.
    # --------------------------------------------------------

    FRESHNESS_TEST.write_text(
        freshness_text,
        encoding="utf-8",
        newline="\n",
    )

    TOP_FORM_TEST.write_text(
        top_text,
        encoding="utf-8",
        newline="\n",
    )

    compile_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(FRESHNESS_TEST),
            str(TOP_FORM_TEST),
        ],
        cwd=ROOT,
    )

    if compile_result.returncode != 0:
        raise RuntimeError(
            "fixture compile validation failed"
        )

    print()
    print(
        "[STEP] legacy verdict regressions migrated "
        "to Evidence Families V2 fixtures"
    )

    # --------------------------------------------------------
    # Apply the already-created production verdict migration.
    # Its own rollback remains active too.
    # --------------------------------------------------------

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

    if not NEW_V2_TEST.exists():
        raise RuntimeError(
            "V2 verdict regression was not created"
        )

    # --------------------------------------------------------
    # Final direct test suite after migration.
    # --------------------------------------------------------

    final_tests = (
        NEW_V2_TEST,
        FRESHNESS_TEST,
        TOP_FORM_TEST,
    )

    for test in final_tests:
        print()
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

    # --------------------------------------------------------
    # Structural production check:
    # build_rithmic_setup_verdict must use V2 and must not call
    # the legacy raw scorer.
    # --------------------------------------------------------

    verdict_after = VERDICT.read_text(
        encoding="utf-8-sig",
    )

    start = verdict_after.index(
        "def build_rithmic_setup_verdict("
    )

    end = verdict_after.index(
        "\ndef _format_signed",
        start,
    )

    build_source = verdict_after[start:end]

    if (
        "score_rithmic_setup_alignment_for_direction("
        in build_source
    ):
        raise RuntimeError(
            "production build still calls legacy raw scorer"
        )

    if (
        "score_rithmic_evidence_families_for_direction("
        not in build_source
    ):
        raise RuntimeError(
            "production build does not call V2 family scorer"
        )

    # --------------------------------------------------------
    # Diff hygiene.
    # --------------------------------------------------------

    diff_check = subprocess.run(
        [
            "git",
            "diff",
            "--check",
            "--",
            str(VERDICT.relative_to(ROOT)),
            str(FRESHNESS_TEST.relative_to(ROOT)),
            str(TOP_FORM_TEST.relative_to(ROOT)),
        ],
        cwd=ROOT,
    )

    if diff_check.returncode != 0:
        raise RuntimeError(
            "git diff --check failed"
        )

except Exception:
    # Full wrapper rollback, including a migration that may
    # already have succeeded before a later verification failed.
    shutil.copy2(
        backup_dir / VERDICT.name,
        VERDICT,
    )

    shutil.copy2(
        backup_dir / FRESHNESS_TEST.name,
        FRESHNESS_TEST,
    )

    shutil.copy2(
        backup_dir / TOP_FORM_TEST.name,
        TOP_FORM_TEST,
    )

    if (
        not new_test_existed_before
        and NEW_V2_TEST.exists()
    ):
        NEW_V2_TEST.unlink()

    print()
    print(
        "[ROLLBACK] verdict + both legacy test "
        "fixtures restored from backup."
    )

    raise


print()
print(
    "[PASS] Evidence Families V2 verdict migration "
    "and legacy fixture migration succeeded"
)

print(
    "[BACKUP]",
    backup_dir.relative_to(ROOT),
)

print(
    "[CHANGED]",
    VERDICT.relative_to(ROOT),
)

print(
    "[CHANGED]",
    FRESHNESS_TEST.relative_to(ROOT),
)

print(
    "[CHANGED]",
    TOP_FORM_TEST.relative_to(ROOT),
)

print(
    "[CREATED]",
    NEW_V2_TEST.relative_to(ROOT),
)

print(
    "[SAFETY] production verdict uses independent "
    "Evidence Families V2"
)

print(
    "[SAFETY] production verdict no longer calls "
    "legacy raw delta/CVD/DOM scorer"
)

print(
    "[SAFETY] source freshness / low sample / stale "
    "cache / rollover / registration guards preserved"
)

print(
    "[SAFETY] decision_impact=NONE and execution "
    "authority remains disabled"
)
