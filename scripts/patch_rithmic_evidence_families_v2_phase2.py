from pathlib import Path
import datetime
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_BRANCH = "feature/rithmic-setup-verdict-supervisor"
EXPECTED_HEAD = "1c08471"

BUILDER = (
    ROOT
    / "scripts"
    / "build_phase5g_rithmic_monitoring_bridge.py"
)

FAMILY_MODULE = (
    ROOT
    / "src"
    / "order_flow_features"
    / "rithmic_evidence_families.py"
)

FAMILY_TEST = (
    ROOT
    / "scripts"
    / "test_rithmic_evidence_families_v2.py"
)

BRIDGE_TEST = (
    ROOT
    / "scripts"
    / "test_rithmic_evidence_families_bridge_v2.py"
)

WATCHER_TEST = (
    ROOT
    / "scripts"
    / "test_phase5g_rithmic_evidence_watcher_v1.py"
)

stamp = datetime.datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

backup_dir = (
    ROOT
    / "local_backups"
    / f"rithmic_evidence_families_v2_phase2_{stamp}"
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
    BUILDER,
    FAMILY_MODULE,
    FAMILY_TEST,
    WATCHER_TEST,
):
    if not required.exists():
        raise SystemExit(
            f"[STOP] missing required file: "
            f"{required.relative_to(ROOT)}"
        )

if BRIDGE_TEST.exists():
    raise SystemExit(
        f"[STOP] target test already exists: "
        f"{BRIDGE_TEST.relative_to(ROOT)}"
    )

# The builder already contains intentional working-tree
# changes from the watcher work, but it must not be staged.
cached = subprocess.run(
    [
        "git",
        "diff",
        "--cached",
        "--quiet",
        "--",
        str(BUILDER.relative_to(ROOT)),
    ],
    cwd=ROOT,
)

if cached.returncode != 0:
    raise SystemExit(
        "[STOP] staged builder changes detected; "
        "no changes made"
    )


builder_text = BUILDER.read_text(
    encoding="utf-8-sig",
)

old_anchor = '''    bridge["order_flow_regime"] = order_flow_regime

    output_json = output_dir / f"{safe_symbol}_phase5g_rithmic_monitoring_bridge.json"
'''

new_anchor = '''    bridge["order_flow_regime"] = order_flow_regime

    # Evidence Families V2 is a research/observe-only synthesis layer.
    # It receives the already-built Phase 5G evidence and cannot execute,
    # block, resize, approve, or otherwise influence MT5 decisions.
    from src.order_flow_features.rithmic_evidence_families import (
        build_rithmic_evidence_families,
    )

    evidence_families_v2 = build_rithmic_evidence_families(
        bridge,
        signal=args.signal,
    )
    bridge["evidence_families_v2"] = evidence_families_v2

    output_json = output_dir / f"{safe_symbol}_phase5g_rithmic_monitoring_bridge.json"
'''

if builder_text.count(old_anchor) != 1:
    raise SystemExit(
        "[STOP] Phase 5G insertion anchor mismatch; "
        "no changes made"
    )


bridge_test_source = r'''from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.order_flow_features.rithmic_evidence_families import (
    SELL,
    UNAVAILABLE,
    build_rithmic_evidence_families,
)


BUILDER = (
    ROOT
    / "scripts"
    / "build_phase5g_rithmic_monitoring_bridge.py"
)

FAMILY_MODULE = (
    ROOT
    / "src"
    / "order_flow_features"
    / "rithmic_evidence_families.py"
)


def synthetic_bridge() -> dict:
    return {
        "feed_integrity": {
            "engine": "RITHMIC_FEED_INTEGRITY_GUARD_V1",
            "status": "HEALTHY",
            "integrity_ok": True,
            "continuity_valid": True,
            "production_data_eligible": True,
        },
        "anti_fakeout": {
            "engine": "RITHMIC_ANTI_FAKEOUT_V1",
            "status": "NEUTRAL",
            "freshness_gate": {
                "has_fresh_trade": True,
                "has_fresh_bbo": True,
                "has_fresh_order_book": True,
                "all_fresh": True,
            },
            "executed_flow": {
                "trade_count": 80,
                "total_volume": 100.0,
                "delta": -20.0,
                "cumulative_delta": -35.0,
                "flow_imbalance": -0.20,
                "direction": -1,
                "sufficient": True,
            },
            "footprint": {
                "footprint_imbalance": -0.20,
                "direction": -1,
                "recent_candle_delta": -10.0,
                "recent_candle_volume": 40.0,
                "strength_ok": True,
            },
            "spoof_risk": False,
            "dom_only_untrusted": False,
        },
        "absorption_exhaustion": {
            "engine": "RITHMIC_ABSORPTION_EXHAUSTION_V1",
            "status": "SELL_AGGRESSION_EFFECTIVE",
            "flow": {
                "direction": -1,
            },
            "classification": {
                "aggression_effective": True,
                "absorbed": False,
                "exhaustion": False,
            },
        },
        "liquidity_pull_replenishment": {
            "engine": (
                "RITHMIC_LIQUIDITY_PULL_REPLENISHMENT_V1"
            ),
            "status": "STABLE_OR_MIXED",
            "bid": {
                "replenishment": False,
                "pull_risk": False,
            },
            "ask": {
                "replenishment": False,
                "pull_risk": False,
            },
            "policy": {
                "aggregate_depth_only": True,
            },
        },
        "delta_price_divergence": {
            "engine": "RITHMIC_DELTA_PRICE_DIVERGENCE_V1",
            "status": "DELTA_CHANGE_TOO_SMALL",
            "classification": {
                "potential_trapped_buyers": False,
                "potential_trapped_sellers": False,
                "buyer_flow_effective": False,
                "seller_flow_effective": False,
                "bullish_price_without_delta": False,
                "bearish_price_without_delta": False,
            },
        },
        "volume_profile_migration": {
            "engine": "RITHMIC_VOLUME_PROFILE_MIGRATION_V1",
            "status": "PRICE_ACCEPTING_NEAR_STABLE_POC",
            "poc": {
                "change_ticks": 0.0,
                "migrating_up": False,
                "migrating_down": False,
                "stable": True,
            },
            "price_context": {
                "price_vs_poc_ticks": -1.0,
                "accepting_near_poc": True,
                "rejection_above_poc": False,
                "rejection_below_poc": False,
                "price_following_up_migration": False,
                "price_following_down_migration": False,
                "migration_price_conflict": False,
            },
        },
        "order_flow_regime": {
            "engine": "RITHMIC_ORDER_FLOW_REGIME_V1",
            "regime": "SELL_FLOW_EFFECTIVE",
            "direction": "SELL",
            "confidence": "MODERATE",
        },
    }


def test_builder_wiring_position() -> None:
    source = BUILDER.read_text(
        encoding="utf-8-sig",
    )

    old_engine = (
        'bridge["order_flow_regime"] = order_flow_regime'
    )

    import_marker = (
        "from src.order_flow_features."
        "rithmic_evidence_families import"
    )

    call_marker = (
        "build_rithmic_evidence_families("
    )

    family_marker = (
        'bridge["evidence_families_v2"] = '
        "evidence_families_v2"
    )

    output_marker = (
        "output_json = output_dir / "
    )

    for marker in (
        old_engine,
        import_marker,
        call_marker,
        family_marker,
        output_marker,
    ):
        assert marker in source, marker

    positions = [
        source.index(old_engine),
        source.index(import_marker),
        source.index(call_marker),
        source.index(family_marker),
        source.index(output_marker),
    ]

    assert positions == sorted(positions)

    assert "signal=args.signal" in source

    print(
        "PASS: Evidence Families V2 is built after "
        "existing Phase 5G engines and before bridge write"
    )


def test_existing_phase5g_sections_preserved() -> None:
    source = BUILDER.read_text(
        encoding="utf-8-sig",
    )

    required = (
        'bridge["feed_integrity"]',
        'bridge["absorption_exhaustion"]',
        'bridge["liquidity_pull_replenishment"]',
        'bridge["delta_price_divergence"]',
        'bridge["volume_profile_migration"]',
        'bridge["anti_fakeout"]',
        'bridge["order_flow_regime"]',
        'bridge["evidence_families_v2"]',
    )

    for marker in required:
        assert marker in source, marker

    print(
        "PASS: all pre-existing Phase 5G evidence "
        "sections remain present"
    )


def test_family_payload_contract() -> None:
    result = build_rithmic_evidence_families(
        synthetic_bridge(),
        signal="BUY",
    )

    assert result["engine"] == (
        "RITHMIC_EVIDENCE_FAMILIES_V2"
    )

    assert result["feed_gate"]["usable"] is True

    assert (
        result["families"]["AGGRESSION"]["state"]
        == SELL
    )

    assert (
        result["families"][
            "FOOTPRINT_ACCEPTANCE"
        ]["state"]
        == UNAVAILABLE
    )

    assert result["summary"]["coverage"] == "5/6"

    assert result["summary"]["support_count"] == 0
    assert result["summary"]["against_count"] == 1

    assert result["decision_impact"] == "NONE"
    assert result["can_influence_decision"] is False
    assert result["safe_for_execution"] is False
    assert result["execution_allowed"] is False

    print(
        "PASS: bridge family payload preserves "
        "independent-family and safety contracts"
    )


def test_family_module_has_zero_mt5_execution_coupling() -> None:
    source = FAMILY_MODULE.read_text(
        encoding="utf-8-sig",
    ).lower()

    forbidden = (
        "import metatrader5",
        "mt5.order_send",
        "order_send(",
        "place_order(",
        "execute_trade(",
        "open_position(",
    )

    found = [
        token
        for token in forbidden
        if token in source
    ]

    assert not found, found

    print(
        "PASS: Evidence Families V2 has zero "
        "MetaTrader execution coupling"
    )


def main() -> None:
    test_builder_wiring_position()
    test_existing_phase5g_sections_preserved()
    test_family_payload_contract()
    test_family_module_has_zero_mt5_execution_coupling()

    print("")
    print(
        "[PASS] Evidence Families V2 Phase 5G "
        "bridge wiring contract verified."
    )


if __name__ == "__main__":
    main()
'''


backup_dir.mkdir(
    parents=True,
    exist_ok=False,
)

shutil.copy2(
    BUILDER,
    backup_dir / BUILDER.name,
)

created = []

try:
    builder_text = builder_text.replace(
        old_anchor,
        new_anchor,
        1,
    )

    BUILDER.write_text(
        builder_text,
        encoding="utf-8",
        newline="\n",
    )

    BRIDGE_TEST.write_text(
        bridge_test_source,
        encoding="utf-8",
        newline="\n",
    )
    created.append(BRIDGE_TEST)

    compile_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(BUILDER),
            str(FAMILY_MODULE),
            str(FAMILY_TEST),
            str(BRIDGE_TEST),
            str(WATCHER_TEST),
        ],
        cwd=ROOT,
    )

    if compile_result.returncode != 0:
        raise RuntimeError(
            "compile validation failed"
        )

    for test in (
        FAMILY_TEST,
        BRIDGE_TEST,
        WATCHER_TEST,
    ):
        result = subprocess.run(
            [
                sys.executable,
                str(test),
            ],
            cwd=ROOT,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"regression failed: "
                f"{test.relative_to(ROOT)}"
            )

    diff_check = subprocess.run(
        [
            "git",
            "diff",
            "--check",
            "--",
            str(BUILDER.relative_to(ROOT)),
        ],
        cwd=ROOT,
    )

    if diff_check.returncode != 0:
        raise RuntimeError(
            "git diff --check failed"
        )

except Exception:
    shutil.copy2(
        backup_dir / BUILDER.name,
        BUILDER,
    )

    for path in created:
        if path.exists():
            path.unlink()

    print(
        "[ROLLBACK] Evidence Families V2 Phase 2 "
        "bridge changes reverted."
    )

    raise


print("")
print(
    "[PASS] Evidence Families V2 Phase 2 applied"
)
print(
    "[BACKUP]",
    backup_dir.relative_to(ROOT),
)
print(
    "[CHANGED]",
    BUILDER.relative_to(ROOT),
)
print(
    "[CREATED]",
    BRIDGE_TEST.relative_to(ROOT),
)
print(
    "[UNCHANGED] src/rithmic_setup_verdict.py"
)
print(
    "[UNCHANGED] src/live_bot.py"
)
print(
    "[UNCHANGED] MT5 execution/risk paths"
)
print(
    "[SAFETY] old Phase 5G sections preserved"
)
print(
    "[SAFETY] Evidence Families remains "
    "research/observe-only"
)
