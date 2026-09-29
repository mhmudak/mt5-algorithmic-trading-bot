from pathlib import Path
import datetime
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_BRANCH = "feature/rithmic-setup-verdict-supervisor"
EXPECTED_HEAD = "1c08471"

MODULE = (
    ROOT
    / "src"
    / "order_flow_features"
    / "rithmic_evidence_families.py"
)

TEST = (
    ROOT
    / "scripts"
    / "test_rithmic_evidence_families_v2.py"
)

stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

backup_dir = (
    ROOT
    / "local_backups"
    / f"rithmic_evidence_families_v2_phase1_1_{stamp}"
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

if not MODULE.exists():
    raise SystemExit(
        f"[STOP] missing Phase 1 module: {MODULE}"
    )

if not TEST.exists():
    raise SystemExit(
        f"[STOP] missing Phase 1 test: {TEST}"
    )

# Do not mutate a staged file.
for path in (MODULE, TEST):
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


module_text = MODULE.read_text(
    encoding="utf-8-sig",
)

test_text = TEST.read_text(
    encoding="utf-8-sig",
)


old_feed_gate = '''    if not bool(feed.get("continuity_valid")):
        return False, "feed_continuity_invalid"

    return True, "healthy"
'''

new_feed_gate = '''    if not bool(feed.get("continuity_valid")):
        return False, "feed_continuity_invalid"

    production_data_eligible = (
        feed.get("production_data_eligible")
    )

    if production_data_eligible is False:
        return False, "feed_not_production_data_eligible"

    return True, "healthy"
'''

if module_text.count(old_feed_gate) != 1:
    raise SystemExit(
        "[STOP] feed-gate anchor mismatch; "
        "no changes made"
    )


old_aggression = '''    flow = _dict(
        anti.get("executed_flow")
    )

    if not flow:
        return _family(
            "AGGRESSION",
            UNAVAILABLE,
            reason="executed_flow_missing",
            source_engine=anti.get("engine"),
            source_status=_status(anti),
        )

    if not bool(flow.get("sufficient")):
'''

new_aggression = '''    flow = _dict(
        anti.get("executed_flow")
    )
    freshness = _dict(
        anti.get("freshness_gate")
    )

    if not flow:
        return _family(
            "AGGRESSION",
            UNAVAILABLE,
            reason="executed_flow_missing",
            source_engine=anti.get("engine"),
            source_status=_status(anti),
        )

    if freshness.get("has_fresh_trade") is not True:
        return _family(
            "AGGRESSION",
            UNAVAILABLE,
            reason="executed_trade_flow_not_fresh",
            source_engine=anti.get("engine"),
            source_status=_status(anti),
            raw=flow,
        )

    if not bool(flow.get("sufficient")):
'''

if module_text.count(old_aggression) != 1:
    raise SystemExit(
        "[STOP] aggression anchor mismatch; "
        "no changes made"
    )


# Phase 1 synthetic bridge must explicitly model fresh executed trades.
old_test_anti = '''        "anti_fakeout": {
            "engine": "RITHMIC_ANTI_FAKEOUT_V1",
            "status": "NEUTRAL",
            "executed_flow": {
'''

new_test_anti = '''        "anti_fakeout": {
            "engine": "RITHMIC_ANTI_FAKEOUT_V1",
            "status": "NEUTRAL",
            "freshness_gate": {
                "has_fresh_trade": True,
                "has_fresh_bbo": True,
                "has_fresh_order_book": True,
                "all_fresh": True,
            },
            "executed_flow": {
'''

if test_text.count(old_test_anti) != 1:
    raise SystemExit(
        "[STOP] test anti-fakeout anchor mismatch; "
        "no changes made"
    )


insert_before = '''def test_bad_feed_makes_every_family_unavailable():
'''

new_tests = '''def test_stale_trade_flow_cannot_vote_aggression():
    bridge = base_bridge()

    bridge[
        "anti_fakeout"
    ][
        "freshness_gate"
    ][
        "has_fresh_trade"
    ] = False

    bridge[
        "anti_fakeout"
    ][
        "freshness_gate"
    ][
        "all_fresh"
    ] = False

    bridge[
        "anti_fakeout"
    ]["status"] = "STALE"

    result = build_rithmic_evidence_families(
        bridge,
        signal="SELL",
    )

    assert_state(
        result,
        "AGGRESSION",
        UNAVAILABLE,
    )

    assert (
        result["summary"]["support_count"]
        == 0
    )

    print(
        "PASS: stale executed trades cannot create "
        "an Aggression family vote even when the "
        "overall BBO/DOM feed remains usable"
    )


def test_nonproduction_feed_gates_all_families():
    bridge = base_bridge()

    bridge[
        "feed_integrity"
    ][
        "production_data_eligible"
    ] = False

    result = build_rithmic_evidence_families(
        bridge,
        signal="BUY",
    )

    assert (
        result["feed_gate"]["usable"]
        is False
    )

    assert (
        result["feed_gate"]["reason"]
        == "feed_not_production_data_eligible"
    )

    assert (
        result["summary"]["available_count"]
        == 0
    )

    assert (
        result["summary"]["unavailable_count"]
        == 6
    )

    print(
        "PASS: explicitly non-production Rithmic "
        "feed cannot create Evidence Families votes"
    )


'''

if test_text.count(insert_before) != 1:
    raise SystemExit(
        "[STOP] test insertion anchor mismatch; "
        "no changes made"
    )


main_anchor = '''    test_live_like_case_avoids_double_counting()
    test_bad_feed_makes_every_family_unavailable()
'''

main_replacement = '''    test_live_like_case_avoids_double_counting()
    test_stale_trade_flow_cannot_vote_aggression()
    test_nonproduction_feed_gates_all_families()
    test_bad_feed_makes_every_family_unavailable()
'''

if test_text.count(main_anchor) != 1:
    raise SystemExit(
        "[STOP] test main anchor mismatch; "
        "no changes made"
    )


backup_dir.mkdir(
    parents=True,
    exist_ok=False,
)

shutil.copy2(
    MODULE,
    backup_dir / MODULE.name,
)

shutil.copy2(
    TEST,
    backup_dir / TEST.name,
)


try:
    module_text = module_text.replace(
        old_feed_gate,
        new_feed_gate,
        1,
    )

    module_text = module_text.replace(
        old_aggression,
        new_aggression,
        1,
    )

    test_text = test_text.replace(
        old_test_anti,
        new_test_anti,
        1,
    )

    test_text = test_text.replace(
        insert_before,
        new_tests + insert_before,
        1,
    )

    test_text = test_text.replace(
        main_anchor,
        main_replacement,
        1,
    )

    MODULE.write_text(
        module_text,
        encoding="utf-8",
        newline="\n",
    )

    TEST.write_text(
        test_text,
        encoding="utf-8",
        newline="\n",
    )

    compile_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(MODULE),
            str(TEST),
        ],
        cwd=ROOT,
    )

    if compile_result.returncode != 0:
        raise RuntimeError(
            "compile validation failed"
        )

    test_result = subprocess.run(
        [
            sys.executable,
            str(TEST),
        ],
        cwd=ROOT,
    )

    if test_result.returncode != 0:
        raise RuntimeError(
            "Evidence Families V2 regression failed"
        )

except Exception:
    shutil.copy2(
        backup_dir / MODULE.name,
        MODULE,
    )

    shutil.copy2(
        backup_dir / TEST.name,
        TEST,
    )

    print(
        "[ROLLBACK] Phase 1.1 changes restored "
        "from backup."
    )

    raise


print("")
print(
    "[PASS] Evidence Families V2 Phase 1.1 "
    "freshness hardening applied"
)
print(
    "[BACKUP]",
    backup_dir.relative_to(ROOT),
)
print(
    "[CHANGED]",
    MODULE.relative_to(ROOT),
)
print(
    "[CHANGED]",
    TEST.relative_to(ROOT),
)
print(
    "[SAFETY] stale executed flow cannot vote"
)
print(
    "[SAFETY] explicitly non-production feed "
    "cannot vote"
)
print(
    "[SAFETY] decision/execution authority remains NONE"
)
