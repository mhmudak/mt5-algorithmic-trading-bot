from pathlib import Path
import datetime
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_BRANCH = "feature/rithmic-setup-verdict-supervisor"
EXPECTED_HEAD = "1c08471"

VERDICT = ROOT / "src" / "rithmic_setup_verdict.py"

NEW_TEST = (
    ROOT
    / "scripts"
    / "test_rithmic_setup_verdict_evidence_families_v2.py"
)

EXISTING_TESTS = (
    ROOT
    / "scripts"
    / "test_rithmic_setup_verdict_source_freshness_v2.py",
    ROOT
    / "scripts"
    / "test_rithmic_setup_verdict_top_form_v1.py",
)

stamp = datetime.datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

backup_dir = (
    ROOT
    / "local_backups"
    / f"rithmic_setup_verdict_evidence_families_v2_{stamp}"
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

if not VERDICT.exists():
    raise SystemExit(
        "[STOP] missing src/rithmic_setup_verdict.py"
    )

for test in EXISTING_TESTS:
    if not test.exists():
        raise SystemExit(
            f"[STOP] missing regression test: "
            f"{test.relative_to(ROOT)}"
        )

if NEW_TEST.exists():
    raise SystemExit(
        f"[STOP] target test already exists: "
        f"{NEW_TEST.relative_to(ROOT)}"
    )

cached = subprocess.run(
    [
        "git",
        "diff",
        "--cached",
        "--quiet",
        "--",
        str(VERDICT.relative_to(ROOT)),
    ],
    cwd=ROOT,
)

if cached.returncode != 0:
    raise SystemExit(
        "[STOP] staged verdict changes detected; "
        "no changes made"
    )


text = VERDICT.read_text(
    encoding="utf-8-sig",
)

if "RITHMIC_SETUP_EVIDENCE_FAMILY_MIN_COVERAGE" in text:
    raise SystemExit(
        "[STOP] Evidence Families verdict migration "
        "appears to already be present"
    )


# ------------------------------------------------------------------
# 1. Add V2 family-policy constants.
# ------------------------------------------------------------------

constant_anchor = (
    "RITHMIC_SETUP_CACHE_MAX_AGE_SECONDS = 5.0\n"
)

constant_insert = '''RITHMIC_SETUP_CACHE_MAX_AGE_SECONDS = 5.0
RITHMIC_SETUP_EVIDENCE_FAMILY_MIN_COVERAGE = 4
RITHMIC_SETUP_EVIDENCE_FAMILY_EXPECTED_COUNT = 6
RITHMIC_SETUP_EVIDENCE_FAMILY_ORDER = (
    "AGGRESSION",
    "AUCTION_PROFILE",
    "FOOTPRINT_ACCEPTANCE",
    "ABSORPTION_EXHAUSTION",
    "LIQUIDITY_DYNAMICS",
    "DIVERGENCE_TRAP",
)
'''

if text.count(constant_anchor) != 1:
    raise SystemExit(
        "[STOP] constants anchor mismatch; "
        "no changes made"
    )

text = text.replace(
    constant_anchor,
    constant_insert,
    1,
)


# ------------------------------------------------------------------
# 2. Keep the old raw scorer for compatibility, but add the V2
#    bridge loader and family scorer immediately after it.
# ------------------------------------------------------------------

helper_anchor = '''    return support, against, evidence


'''

helper_insert = r'''    return support, against, evidence


def _load_phase5g_evidence_families_v2(
    rithmic_symbol: str | None,
) -> tuple[dict[str, Any], str, float | None]:
    """
    Load the observe-only Phase 5G family payload.

    The setup verdict deliberately reads the already-built Phase 5G bridge
    rather than reconstructing evidence from raw adapter metrics.

    Fail closed on missing, stale, malformed, symbol-mismatched, or
    execution-capable payloads.
    """

    import json
    import time
    from pathlib import Path

    symbol = _safe_text(
        rithmic_symbol
    ).upper()

    if not symbol:
        return (
            {},
            "evidence_families_symbol_missing",
            None,
        )

    root = Path(__file__).resolve().parents[1]

    path = (
        root
        / "data"
        / "order_flow"
        / "rithmic"
        / (
            f"{symbol}_phase5g_"
            "rithmic_monitoring_bridge.json"
        )
    )

    if not path.exists():
        return (
            {},
            "evidence_families_bridge_missing",
            None,
        )

    try:
        bridge_age_seconds = max(
            0.0,
            time.time() - path.stat().st_mtime,
        )
    except OSError:
        return (
            {},
            "evidence_families_bridge_stat_failed",
            None,
        )

    if (
        bridge_age_seconds
        > RITHMIC_SETUP_CACHE_MAX_AGE_SECONDS
    ):
        return (
            {},
            "evidence_families_bridge_stale",
            round(
                bridge_age_seconds,
                3,
            ),
        )

    try:
        bridge = json.loads(
            path.read_text(
                encoding="utf-8-sig"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
        UnicodeError,
    ):
        return (
            {},
            "evidence_families_bridge_unreadable",
            round(
                bridge_age_seconds,
                3,
            ),
        )

    if not isinstance(bridge, dict):
        return (
            {},
            "evidence_families_bridge_invalid",
            round(
                bridge_age_seconds,
                3,
            ),
        )

    bridge_symbol = _safe_text(
        bridge.get("symbol")
    ).upper()

    if (
        bridge_symbol
        and bridge_symbol != symbol
    ):
        return (
            {},
            "evidence_families_bridge_symbol_mismatch",
            round(
                bridge_age_seconds,
                3,
            ),
        )

    payload = bridge.get(
        "evidence_families_v2"
    )

    if not isinstance(payload, dict):
        return (
            {},
            "evidence_families_v2_missing",
            round(
                bridge_age_seconds,
                3,
            ),
        )

    if (
        _safe_text(
            payload.get("engine")
        ).upper()
        != "RITHMIC_EVIDENCE_FAMILIES_V2"
    ):
        return (
            {},
            "evidence_families_v2_engine_invalid",
            round(
                bridge_age_seconds,
                3,
            ),
        )

    # Hard observe-only contract.
    if (
        payload.get("decision_impact") != "NONE"
        or bool(
            payload.get(
                "can_influence_decision"
            )
        )
        or bool(
            payload.get(
                "safe_for_execution"
            )
        )
        or bool(
            payload.get(
                "execution_allowed"
            )
        )
    ):
        return (
            {},
            "evidence_families_v2_safety_contract_failed",
            round(
                bridge_age_seconds,
                3,
            ),
        )

    return (
        payload,
        "ok",
        round(
            bridge_age_seconds,
            3,
        ),
    )


def score_rithmic_evidence_families_for_direction(
    direction: str,
    evidence_families_v2: dict[str, Any] | None,
) -> tuple[int, int, list[str], dict[str, Any]]:
    """
    Convert independent V2 family states into setup-relative counts.

    Each family contributes at most one directional vote.
    UNAVAILABLE is distinct from NEUTRAL.
    CONFLICT contributes coverage but no directional vote.
    """

    direction = _safe_text(
        direction
    ).upper()

    payload = (
        evidence_families_v2
        if isinstance(
            evidence_families_v2,
            dict,
        )
        else {}
    )

    families = (
        payload.get("families")
        if isinstance(
            payload.get("families"),
            dict,
        )
        else {}
    )

    opposite = (
        "SELL"
        if direction == "BUY"
        else "BUY"
    )

    support = 0
    against = 0
    available_count = 0
    neutral_count = 0
    conflict_count = 0
    unavailable_count = 0

    evidence: list[str] = []
    states: dict[str, str] = {}
    reasons: dict[str, str] = {}

    valid_states = {
        "BUY",
        "SELL",
        "NEUTRAL",
        "CONFLICT",
        "UNAVAILABLE",
    }

    for name in (
        RITHMIC_SETUP_EVIDENCE_FAMILY_ORDER
    ):
        family = (
            families.get(name)
            if isinstance(
                families.get(name),
                dict,
            )
            else {}
        )

        state = _safe_text(
            family.get("state"),
            "UNAVAILABLE",
        ).upper()

        if state not in valid_states:
            state = "UNAVAILABLE"

        reason = _safe_text(
            family.get("reason"),
            "family_reason_unavailable",
        )

        states[name] = state
        reasons[name] = reason

        if state == "UNAVAILABLE":
            unavailable_count += 1

        else:
            available_count += 1

            if state == direction:
                support += 1

            elif state == opposite:
                against += 1

            elif state == "NEUTRAL":
                neutral_count += 1

            elif state == "CONFLICT":
                conflict_count += 1

        evidence.append(
            f"{name}: {state} | {reason}"
        )

    summary = {
        "family_count": (
            RITHMIC_SETUP_EVIDENCE_FAMILY_EXPECTED_COUNT
        ),
        "available_count": available_count,
        "coverage": (
            f"{available_count}/"
            f"{RITHMIC_SETUP_EVIDENCE_FAMILY_EXPECTED_COUNT}"
        ),
        "support_count": support,
        "against_count": against,
        "neutral_count": neutral_count,
        "conflict_count": conflict_count,
        "unavailable_count": unavailable_count,
        "states": states,
        "reasons": reasons,
    }

    return (
        support,
        against,
        evidence,
        summary,
    )


'''

if text.count(helper_anchor) < 1:
    raise SystemExit(
        "[STOP] score helper insertion anchor "
        "not found; no changes made"
    )

text = text.replace(
    helper_anchor,
    helper_insert,
    1,
)


# ------------------------------------------------------------------
# 3. Add V2 diagnostics to the result object.
# ------------------------------------------------------------------

result_anchor = '''        "freshness": {},
        "metrics": {},
    }
'''

result_insert = '''        "freshness": {},
        "metrics": {},
        "evidence_model": None,
        "evidence_bridge_age_seconds": None,
        "evidence_family_coverage": "0/6",
        "evidence_family_available_count": 0,
        "evidence_family_unavailable_count": 6,
        "evidence_family_states": {},
        "evidence_family_reasons": {},
    }
'''

if text.count(result_anchor) != 1:
    raise SystemExit(
        "[STOP] result-object anchor mismatch; "
        "no changes made"
    )

text = text.replace(
    result_anchor,
    result_insert,
    1,
)


# ------------------------------------------------------------------
# 4. Replace ONLY the old decisive raw-score block.
#
# All registration/freshness/cache/sample/DOM gates above it remain.
# ------------------------------------------------------------------

old_decision_block = '''    support, against, evidence = (
        score_rithmic_setup_alignment_for_direction(
            direction,
            metrics,
        )
    )
    result["support_score"] = support
    result["against_score"] = against
    result["evidence"] = evidence[:12]

    if (
        support >= RITHMIC_SETUP_MIN_DECISIVE_SCORE
        and support > against
    ):
        result.update(
            {
                "verdict": "SUPPORTS_SETUP",
                "alignment": f"SUPPORTS_{direction}",
                "supports_setup": True,
                "reason": "rithmic_evidence_supports_setup",
            }
        )
    elif (
        against >= RITHMIC_SETUP_MIN_DECISIVE_SCORE
        and against > support
    ):
        result.update(
            {
                "verdict": "AGAINST_SETUP",
                "alignment": f"AGAINST_{direction}",
                "against_setup": True,
                "reason": "rithmic_evidence_against_setup",
            }
        )
    elif support == 0 and against == 0:
        result.update(
            {
                "verdict": "NEUTRAL",
                "alignment": "NEUTRAL_INSUFFICIENT_RITHMIC_EVIDENCE",
                "reason": "no_directional_rithmic_evidence",
            }
        )
    else:
        result.update(
            {
                "verdict": "NEUTRAL",
                "alignment": "NEUTRAL_OR_MIXED_RITHMIC_EVIDENCE",
                "reason": "mixed_rithmic_evidence",
            }
        )

    return result
'''

new_decision_block = '''    (
        evidence_families_v2,
        evidence_load_reason,
        evidence_bridge_age_seconds,
    ) = _load_phase5g_evidence_families_v2(
        result.get("rithmic_symbol")
    )

    result["evidence_model"] = (
        "RITHMIC_EVIDENCE_FAMILIES_V2"
    )
    result["evidence_bridge_age_seconds"] = (
        evidence_bridge_age_seconds
    )

    if not evidence_families_v2:
        result["reason"] = evidence_load_reason
        result["alignment"] = (
            "NOT_AVAILABLE_EVIDENCE_FAMILIES_V2"
        )
        return result

    feed_gate = (
        evidence_families_v2.get("feed_gate")
        if isinstance(
            evidence_families_v2.get("feed_gate"),
            dict,
        )
        else {}
    )

    if feed_gate.get("usable") is not True:
        result["reason"] = (
            "evidence_families_feed_gate_unusable"
        )
        result["alignment"] = (
            "NOT_AVAILABLE_EVIDENCE_FAMILIES_FEED_GATE"
        )
        return result

    (
        support,
        against,
        evidence,
        family_summary,
    ) = score_rithmic_evidence_families_for_direction(
        direction,
        evidence_families_v2,
    )

    result["support_score"] = support
    result["against_score"] = against
    result["evidence"] = evidence[:12]

    result["evidence_family_coverage"] = (
        family_summary.get(
            "coverage",
            "0/6",
        )
    )
    result["evidence_family_available_count"] = int(
        family_summary.get(
            "available_count",
            0,
        )
        or 0
    )
    result["evidence_family_unavailable_count"] = int(
        family_summary.get(
            "unavailable_count",
            0,
        )
        or 0
    )
    result["evidence_family_states"] = dict(
        family_summary.get(
            "states"
        )
        or {}
    )
    result["evidence_family_reasons"] = dict(
        family_summary.get(
            "reasons"
        )
        or {}
    )

    if (
        result[
            "evidence_family_available_count"
        ]
        < RITHMIC_SETUP_EVIDENCE_FAMILY_MIN_COVERAGE
    ):
        result.update(
            {
                "verdict": "NEUTRAL",
                "alignment": (
                    "NEUTRAL_INSUFFICIENT_"
                    "EVIDENCE_FAMILY_COVERAGE"
                ),
                "reason": (
                    "evidence_family_coverage_"
                    "below_minimum"
                ),
            }
        )

    elif (
        support
        >= RITHMIC_SETUP_MIN_DECISIVE_SCORE
        and support > against
    ):
        result.update(
            {
                "verdict": "SUPPORTS_SETUP",
                "alignment": f"SUPPORTS_{direction}",
                "supports_setup": True,
                "reason": (
                    "evidence_families_support_setup"
                ),
            }
        )

    elif (
        against
        >= RITHMIC_SETUP_MIN_DECISIVE_SCORE
        and against > support
    ):
        result.update(
            {
                "verdict": "AGAINST_SETUP",
                "alignment": f"AGAINST_{direction}",
                "against_setup": True,
                "reason": (
                    "evidence_families_against_setup"
                ),
            }
        )

    elif support == 0 and against == 0:
        result.update(
            {
                "verdict": "NEUTRAL",
                "alignment": (
                    "NEUTRAL_INSUFFICIENT_"
                    "DIRECTIONAL_EVIDENCE_FAMILIES"
                ),
                "reason": (
                    "no_directional_evidence_families"
                ),
            }
        )

    else:
        result.update(
            {
                "verdict": "NEUTRAL",
                "alignment": (
                    "NEUTRAL_OR_MIXED_"
                    "EVIDENCE_FAMILIES"
                ),
                "reason": (
                    "mixed_evidence_families"
                ),
            }
        )

    return result
'''

if text.count(old_decision_block) != 1:
    raise SystemExit(
        "[STOP] decisive-score block mismatch; "
        "no changes made"
    )

text = text.replace(
    old_decision_block,
    new_decision_block,
    1,
)


test_source = r'''from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.rithmic_setup_verdict as verdict_module


def registration() -> dict:
    return {
        "registered": True,
        "reason": "ok",
        "payload": {
            "symbol": "GCZ6",
            "source_market": "COMEX",
        },
    }


def context(
    *,
    delta: float = 50.0,
    cumulative_delta: float = 100.0,
    dom_depth_imbalance: float = 0.8,
    dom_bid_depth: float = 1000.0,
    dom_ask_depth: float = 100.0,
) -> dict:
    return {
        "rithmic": {
            "available": True,
            "status": "AVAILABLE",
            "rithmic_symbol": "GCZ6",
            "exchange": "COMEX",
            "cache_status": "FRESH",
            "cache_age_seconds": 0.1,
            "freshness": {
                "snapshot_fresh": True,
                "has_fresh_trade": True,
                "has_fresh_bbo": True,
                "has_fresh_order_book": True,
                "snapshot_age_seconds": 0.1,
                "last_trade_age_seconds": 0.1,
                "last_bbo_age_seconds": 0.1,
                "last_order_book_age_seconds": 0.1,
            },
            "metrics": {
                "trade_count": 40,
                "bbo_count": 40,
                "nonzero_bbo_count": 40,
                "order_book_count": 40,
                "delta": delta,
                "cumulative_delta": cumulative_delta,
                "dom_depth_imbalance": dom_depth_imbalance,
                "dom_bid_depth": dom_bid_depth,
                "dom_ask_depth": dom_ask_depth,
            },
        }
    }


def family(
    state: str,
    reason: str = "synthetic_test",
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


def payload(
    *,
    aggression: str = "NEUTRAL",
    auction: str = "NEUTRAL",
    footprint: str = "UNAVAILABLE",
    absorption: str = "NEUTRAL",
    liquidity: str = "NEUTRAL",
    divergence: str = "NEUTRAL",
    feed_usable: bool = True,
) -> dict:
    return {
        "engine": "RITHMIC_EVIDENCE_FAMILIES_V2",
        "feed_gate": {
            "usable": feed_usable,
            "reason": (
                "healthy"
                if feed_usable
                else "synthetic_bad_feed"
            ),
        },
        "families": {
            "AGGRESSION": family(
                aggression
            ),
            "AUCTION_PROFILE": family(
                auction
            ),
            "FOOTPRINT_ACCEPTANCE": family(
                footprint
            ),
            "ABSORPTION_EXHAUSTION": family(
                absorption
            ),
            "LIQUIDITY_DYNAMICS": family(
                liquidity
            ),
            "DIVERGENCE_TRAP": family(
                divergence
            ),
        },
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
    }


def run_build(
    direction: str,
    v2_payload: dict,
):
    old_registration = (
        verdict_module._load_phase5v_registration
    )
    old_loader = (
        verdict_module
        ._load_phase5g_evidence_families_v2
    )

    try:
        verdict_module._load_phase5v_registration = (
            registration
        )

        verdict_module._load_phase5g_evidence_families_v2 = (
            lambda symbol: (
                v2_payload,
                "ok",
                0.2,
            )
        )

        return (
            verdict_module
            .build_rithmic_setup_verdict(
                context(),
                direction,
            )
        )

    finally:
        verdict_module._load_phase5v_registration = (
            old_registration
        )

        verdict_module._load_phase5g_evidence_families_v2 = (
            old_loader
        )


def test_two_independent_supporting_families():
    result = run_build(
        "BUY",
        payload(
            aggression="BUY",
            auction="BUY",
        ),
    )

    assert (
        result["verdict"]
        == "SUPPORTS_SETUP"
    )
    assert result["support_score"] == 2
    assert result["against_score"] == 0
    assert (
        result["evidence_family_coverage"]
        == "5/6"
    )

    print(
        "PASS: two independent BUY families "
        "support a BUY setup"
    )


def test_two_independent_opposing_families():
    result = run_build(
        "BUY",
        payload(
            aggression="SELL",
            auction="SELL",
        ),
    )

    assert (
        result["verdict"]
        == "AGAINST_SETUP"
    )
    assert result["support_score"] == 0
    assert result["against_score"] == 2

    print(
        "PASS: two independent SELL families "
        "oppose a BUY setup"
    )


def test_one_vs_one_is_mixed():
    result = run_build(
        "BUY",
        payload(
            aggression="BUY",
            auction="SELL",
        ),
    )

    assert result["verdict"] == "NEUTRAL"
    assert result["support_score"] == 1
    assert result["against_score"] == 1
    assert result["alignment"] == (
        "NEUTRAL_OR_MIXED_EVIDENCE_FAMILIES"
    )

    print(
        "PASS: BUY-vs-SELL family disagreement "
        "remains neutral/mixed"
    )


def test_low_coverage_cannot_be_decisive():
    result = run_build(
        "BUY",
        payload(
            aggression="BUY",
            auction="BUY",
            footprint="UNAVAILABLE",
            absorption="UNAVAILABLE",
            liquidity="UNAVAILABLE",
            divergence="NEUTRAL",
        ),
    )

    assert result["support_score"] == 2
    assert (
        result["evidence_family_available_count"]
        == 3
    )
    assert result["verdict"] == "NEUTRAL"
    assert result["alignment"] == (
        "NEUTRAL_INSUFFICIENT_"
        "EVIDENCE_FAMILY_COVERAGE"
    )

    print(
        "PASS: 3/6 coverage cannot create a "
        "decisive setup verdict"
    )


def test_bad_family_feed_gate_is_unavailable():
    result = run_build(
        "SELL",
        payload(
            aggression="SELL",
            auction="SELL",
            feed_usable=False,
        ),
    )

    assert result["verdict"] == "UNAVAILABLE"
    assert result["support_score"] == 0
    assert result["against_score"] == 0
    assert result["alignment"] == (
        "NOT_AVAILABLE_"
        "EVIDENCE_FAMILIES_FEED_GATE"
    )

    print(
        "PASS: unusable V2 feed gate cannot "
        "create a setup verdict"
    )


def test_missing_v2_never_falls_back_to_raw_score():
    old_registration = (
        verdict_module._load_phase5v_registration
    )
    old_loader = (
        verdict_module
        ._load_phase5g_evidence_families_v2
    )

    try:
        verdict_module._load_phase5v_registration = (
            registration
        )

        verdict_module._load_phase5g_evidence_families_v2 = (
            lambda symbol: (
                {},
                "evidence_families_v2_missing",
                0.2,
            )
        )

        # Raw metrics are intentionally extremely bullish.
        # They must NOT become a fallback verdict.
        result = (
            verdict_module
            .build_rithmic_setup_verdict(
                context(
                    delta=999.0,
                    cumulative_delta=9999.0,
                    dom_depth_imbalance=0.99,
                    dom_bid_depth=9999.0,
                    dom_ask_depth=1.0,
                ),
                "BUY",
            )
        )

    finally:
        verdict_module._load_phase5v_registration = (
            old_registration
        )

        verdict_module._load_phase5g_evidence_families_v2 = (
            old_loader
        )

    assert result["verdict"] == "UNAVAILABLE"
    assert result["support_score"] == 0
    assert result["against_score"] == 0

    print(
        "PASS: missing Evidence Families V2 "
        "never falls back to correlated raw scoring"
    )


def test_family_scoring_one_vote_max_per_family():
    p = payload(
        aggression="BUY",
        auction="BUY",
        absorption="SELL",
        liquidity="CONFLICT",
        divergence="NEUTRAL",
    )

    (
        support,
        against,
        evidence,
        summary,
    ) = (
        verdict_module
        .score_rithmic_evidence_families_for_direction(
            "BUY",
            p,
        )
    )

    assert support == 2
    assert against == 1
    assert summary["available_count"] == 5
    assert len(evidence) == 6

    print(
        "PASS: each top-level family contributes "
        "at most one directional vote"
    )


def test_safety_contract_remains_observe_only():
    result = run_build(
        "SELL",
        payload(
            aggression="SELL",
            auction="SELL",
        ),
    )

    assert result["decision_impact"] == "NONE"
    assert (
        result["can_influence_decision"]
        is False
    )
    assert (
        result["safe_for_execution"]
        is False
    )
    assert (
        result["execution_allowed"]
        is False
    )

    print(
        "PASS: V2 setup verdict remains "
        "observe-only with zero execution authority"
    )


def test_build_no_longer_calls_legacy_raw_scorer():
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
        "\ndef _format_signed",
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


def main():
    test_two_independent_supporting_families()
    test_two_independent_opposing_families()
    test_one_vs_one_is_mixed()
    test_low_coverage_cannot_be_decisive()
    test_bad_family_feed_gate_is_unavailable()
    test_missing_v2_never_falls_back_to_raw_score()
    test_family_scoring_one_vote_max_per_family()
    test_safety_contract_remains_observe_only()
    test_build_no_longer_calls_legacy_raw_scorer()

    print("")
    print(
        "[PASS] Rithmic setup verdict Evidence "
        "Families V2 migration verified."
    )


if __name__ == "__main__":
    main()
'''


backup_dir.mkdir(
    parents=True,
    exist_ok=False,
)

shutil.copy2(
    VERDICT,
    backup_dir / VERDICT.name,
)

created = []

try:
    VERDICT.write_text(
        text,
        encoding="utf-8",
        newline="\n",
    )

    NEW_TEST.write_text(
        test_source,
        encoding="utf-8",
        newline="\n",
    )
    created.append(NEW_TEST)

    compile_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(VERDICT),
            str(NEW_TEST),
        ],
        cwd=ROOT,
    )

    if compile_result.returncode != 0:
        raise RuntimeError(
            "compile validation failed"
        )

    tests = (
        NEW_TEST,
        *EXISTING_TESTS,
    )

    for test in tests:
        print("")
        print(
            "=" * 80
        )
        print(
            test.relative_to(ROOT)
        )
        print(
            "=" * 80
        )

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
            str(VERDICT.relative_to(ROOT)),
        ],
        cwd=ROOT,
    )

    if diff_check.returncode != 0:
        raise RuntimeError(
            "git diff --check failed"
        )

except Exception:
    shutil.copy2(
        backup_dir / VERDICT.name,
        VERDICT,
    )

    for path in created:
        if path.exists():
            path.unlink()

    print("")
    print(
        "[ROLLBACK] setup-verdict V2 migration "
        "restored from backup."
    )

    raise


print("")
print(
    "[PASS] Rithmic setup verdict migrated "
    "to Evidence Families V2"
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
    "[CREATED]",
    NEW_TEST.relative_to(ROOT),
)
print(
    "[UNCHANGED] Telegram block formatting"
)
print(
    "[UNCHANGED] src/market_participation_context.py"
)
print(
    "[UNCHANGED] src/live_bot.py"
)
print(
    "[UNCHANGED] MT5 execution/risk paths"
)
print(
    "[SAFETY] missing/stale/unsafe V2 never "
    "falls back to legacy raw scoring"
)
print(
    "[SAFETY] minimum family coverage = "
    "4/6"
)
print(
    "[SAFETY] minimum decisive independent "
    "families = 2"
)
