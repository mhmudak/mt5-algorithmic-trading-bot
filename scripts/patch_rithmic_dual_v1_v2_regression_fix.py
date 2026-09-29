from pathlib import Path
import datetime
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_BRANCH = "feature/rithmic-setup-verdict-supervisor"
EXPECTED_HEAD = "1c08471"

VERDICT = ROOT / "src" / "rithmic_setup_verdict.py"

EVIDENCE_TEST = (
    ROOT
    / "scripts"
    / "test_rithmic_setup_verdict_evidence_families_v2.py"
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

DUAL_HELPER = (
    ROOT
    / "scripts"
    / "patch_rithmic_dual_v1_v2_setup_form.py"
)

DUAL_TEST = (
    ROOT
    / "scripts"
    / "test_rithmic_setup_verdict_dual_v1_v2_display.py"
)

stamp = datetime.datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

backup_dir = (
    ROOT
    / "local_backups"
    / f"rithmic_dual_v1_v2_regression_fix_{stamp}"
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
    EVIDENCE_TEST,
    FRESHNESS_TEST,
    TOP_FORM_TEST,
    DUAL_HELPER,
):
    if not required.exists():
        raise SystemExit(
            f"[STOP] missing required file: "
            f"{required.relative_to(ROOT)}"
        )


# The failed dual-display helper should have rolled this back.
if DUAL_TEST.exists():
    raise SystemExit(
        "[STOP] dual-display test still exists. "
        "Rollback state is not what we expect."
    )


for path in (
    VERDICT,
    EVIDENCE_TEST,
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


evidence_text = EVIDENCE_TEST.read_text(
    encoding="utf-8-sig",
)


old_function = '''def test_build_no_longer_calls_legacy_raw_scorer():
    source = (
        Path(
            verdict_module.__file__
        )
        .read_text(
            encoding="utf-8-sig"
        )
    )

    build_start = source.index(
        "def build_rithmic_setup_verdict("
    )

    build_end = source.index(
        "\\ndef _format_signed",
        build_start,
    )

    build_source = source[
        build_start:build_end
    ]

    assert (
        "score_rithmic_setup_alignment_for_direction("
        not in build_source
    )

    assert (
        "score_rithmic_evidence_families_for_direction("
        in build_source
    )

    print(
        "PASS: production verdict no longer "
        "uses the legacy raw delta/CVD/DOM scorer"
    )
'''


new_function = '''def test_legacy_raw_scorer_is_shadow_only():
    source = (
        Path(
            verdict_module.__file__
        )
        .read_text(
            encoding="utf-8-sig"
        )
    )

    build_start = source.index(
        "def build_rithmic_setup_verdict("
    )

    build_end = source.index(
        "\\ndef _format_signed",
        build_start,
    )

    build_source = source[
        build_start:build_end
    ]

    # V1 is deliberately retained as a research/shadow
    # benchmark for the setup form.
    assert (
        "score_rithmic_setup_alignment_for_direction("
        in build_source
    )

    # V2 remains the production verdict scorer.
    assert (
        "score_rithmic_evidence_families_for_direction("
        in build_source
    )

    assert (
        '"legacy_v1_mode": "SHADOW_ONLY"'
        in source
    )

    assert (
        '"legacy_v1_can_influence_decision": False'
        in source
    )

    # The V1 shadow calculation must happen before V2 scoring
    # and must not act as a fallback if V2 is unavailable.
    v1_pos = build_source.index(
        "score_rithmic_setup_alignment_for_direction("
    )

    v2_loader_pos = build_source.index(
        "_load_phase5g_evidence_families_v2("
    )

    v2_score_pos = build_source.index(
        "score_rithmic_evidence_families_for_direction("
    )

    assert (
        v1_pos
        < v2_loader_pos
        < v2_score_pos
    )

    print(
        "PASS: legacy V1 raw scorer is retained "
        "only as shadow diagnostics while V2 "
        "remains the production verdict scorer"
    )
'''


if evidence_text.count(old_function) != 1:
    raise SystemExit(
        "[STOP] old production-scorer regression "
        "anchor not found"
    )

evidence_text = evidence_text.replace(
    old_function,
    new_function,
    1,
)


old_main_call = (
    "    test_build_no_longer_calls_legacy_raw_scorer()\n"
)

new_main_call = (
    "    test_legacy_raw_scorer_is_shadow_only()\n"
)

if evidence_text.count(old_main_call) != 1:
    raise SystemExit(
        "[STOP] old regression main-call anchor "
        "not found"
    )

evidence_text = evidence_text.replace(
    old_main_call,
    new_main_call,
    1,
)


# ============================================================
# BACKUP
# ============================================================

backup_dir.mkdir(
    parents=True,
    exist_ok=False,
)

shutil.copy2(
    VERDICT,
    backup_dir / VERDICT.name,
)

shutil.copy2(
    EVIDENCE_TEST,
    backup_dir / EVIDENCE_TEST.name,
)


try:
    # --------------------------------------------------------
    # Update the regression contract first.
    # --------------------------------------------------------

    EVIDENCE_TEST.write_text(
        evidence_text,
        encoding="utf-8",
        newline="\n",
    )

    compile_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(EVIDENCE_TEST),
        ],
        cwd=ROOT,
    )

    if compile_result.returncode != 0:
        raise RuntimeError(
            "updated Evidence Families verdict "
            "regression failed to compile"
        )

    print()
    print(
        "[STEP] Evidence Families regression "
        "updated for V1 shadow-only policy"
    )

    # --------------------------------------------------------
    # Reapply the dual-display patch.
    # Its own rollback protection remains active.
    # --------------------------------------------------------

    dual_result = subprocess.run(
        [
            sys.executable,
            str(DUAL_HELPER),
        ],
        cwd=ROOT,
    )

    if dual_result.returncode != 0:
        raise RuntimeError(
            "dual V1/V2 setup-form helper failed"
        )

    if not DUAL_TEST.exists():
        raise RuntimeError(
            "dual-display regression was not created"
        )

    # --------------------------------------------------------
    # Final verdict regression sweep.
    # --------------------------------------------------------

    tests = (
        DUAL_TEST,
        EVIDENCE_TEST,
        FRESHNESS_TEST,
        TOP_FORM_TEST,
    )

    for test in tests:
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
    # Production structural sanity checks.
    # --------------------------------------------------------

    source = VERDICT.read_text(
        encoding="utf-8-sig",
    )

    start = source.index(
        "def build_rithmic_setup_verdict("
    )

    end = source.index(
        "\ndef _format_signed",
        start,
    )

    build_source = source[start:end]

    if (
        "score_rithmic_setup_alignment_for_direction("
        not in build_source
    ):
        raise RuntimeError(
            "V1 shadow scorer missing"
        )

    if (
        "score_rithmic_evidence_families_for_direction("
        not in build_source
    ):
        raise RuntimeError(
            "V2 production scorer missing"
        )

    if (
        '"legacy_v1_mode": "SHADOW_ONLY"'
        not in source
    ):
        raise RuntimeError(
            "V1 shadow-mode marker missing"
        )

    if (
        '"legacy_v1_can_influence_decision": False'
        not in source
    ):
        raise RuntimeError(
            "V1 non-authority marker missing"
        )

    # --------------------------------------------------------
    # Verify the critical behavioral regression exists.
    # --------------------------------------------------------

    dual_source = DUAL_TEST.read_text(
        encoding="utf-8-sig",
    )

    if (
        "test_v1_disagreement_cannot_change_v2_verdict"
        not in dual_source
    ):
        raise RuntimeError(
            "V1-vs-V2 disagreement safety test missing"
        )

    diff_check = subprocess.run(
        [
            "git",
            "diff",
            "--check",
            "--",
            str(VERDICT.relative_to(ROOT)),
            str(EVIDENCE_TEST.relative_to(ROOT)),
        ],
        cwd=ROOT,
    )

    if diff_check.returncode != 0:
        raise RuntimeError(
            "git diff --check failed"
        )


except Exception:
    # Full wrapper rollback.
    shutil.copy2(
        backup_dir / VERDICT.name,
        VERDICT,
    )

    shutil.copy2(
        backup_dir / EVIDENCE_TEST.name,
        EVIDENCE_TEST,
    )

    if DUAL_TEST.exists():
        DUAL_TEST.unlink()

    print()
    print(
        "[ROLLBACK] verdict + Evidence Families "
        "regression restored."
    )

    raise


print()
print(
    "[PASS] dual V1-shadow + V2-verdict "
    "architecture verified"
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
    EVIDENCE_TEST.relative_to(ROOT),
)

print(
    "[CREATED]",
    DUAL_TEST.relative_to(ROOT),
)

print(
    "[V1] visible on setup form = YES"
)

print(
    "[V1] raw delta/CVD/DOM evidence = SHADOW ONLY"
)

print(
    "[V1] can influence production verdict = NO"
)

print(
    "[V2] Evidence Families = production verdict model"
)

print(
    "[V2] minimum coverage = 4/6"
)

print(
    "[V2] minimum decisive families = 2"
)

print(
    "[SAFETY] missing V2 never falls back to V1"
)

print(
    "[SAFETY] MT5 decision/execution authority remains NONE"
)
