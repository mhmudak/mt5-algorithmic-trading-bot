from pathlib import Path
import ast
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
    / "test_rithmic_setup_verdict_dual_v1_v2_display.py"
)

REGRESSION_TESTS = (
    ROOT
    / "scripts"
    / "test_rithmic_setup_verdict_evidence_families_v2.py",
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
    / f"rithmic_dual_v1_v2_display_{stamp}"
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
        f"{branch}"
    )

if head != EXPECTED_HEAD:
    raise SystemExit(
        f"[STOP] HEAD mismatch: "
        f"{head}"
    )

if not VERDICT.exists():
    raise SystemExit(
        "[STOP] verdict module missing"
    )

for test in REGRESSION_TESTS:
    if not test.exists():
        raise SystemExit(
            f"[STOP] missing regression: "
            f"{test.relative_to(ROOT)}"
        )

if NEW_TEST.exists():
    raise SystemExit(
        "[STOP] dual-display test already exists"
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
        "[STOP] verdict file has staged changes"
    )


text = VERDICT.read_text(
    encoding="utf-8-sig",
)


# ============================================================
# 1. Extend result contract with V1 shadow fields
#    and V2 presentation metadata.
# ============================================================

old_defaults = '''        "evidence_family_states": {},
        "evidence_family_reasons": {},
    }
'''

new_defaults = '''        "evidence_family_states": {},
        "evidence_family_reasons": {},

        # Legacy V1 scoring remains available only as a
        # research/shadow benchmark. It must never determine
        # the production V2 verdict.
        "legacy_v1_evaluated": False,
        "legacy_v1_support_score": 0,
        "legacy_v1_against_score": 0,
        "legacy_v1_alignment": "NOT_EVALUATED",
        "legacy_v1_evidence": [],
        "legacy_v1_mode": "SHADOW_ONLY",
        "legacy_v1_can_influence_decision": False,

        # Non-voting V2 presentation metadata.
        "evidence_feed_status": None,
        "evidence_order_flow_regime": None,
    }
'''

if text.count(old_defaults) != 1:
    raise SystemExit(
        "[STOP] result-default anchor mismatch"
    )

text = text.replace(
    old_defaults,
    new_defaults,
    1,
)


# ============================================================
# 2. Compute old V1 score as SHADOW ONLY immediately before
#    loading V2. All source/sample/DOM guards have already run.
# ============================================================

v2_loader_anchor = '''    (
        evidence_families_v2,
        evidence_load_reason,
        evidence_bridge_age_seconds,
    ) = _load_phase5g_evidence_families_v2(
        result.get("rithmic_symbol")
    )
'''

v1_shadow_insert = '''    # --------------------------------------------------------
    # V1 LEGACY SHADOW BENCHMARK
    #
    # Preserve the original raw delta/CVD/DOM scoring only for
    # display/research comparison. These fields are NEVER used
    # to set verdict/supports_setup/against_setup or execution.
    # --------------------------------------------------------

    (
        legacy_v1_support,
        legacy_v1_against,
        legacy_v1_evidence,
    ) = score_rithmic_setup_alignment_for_direction(
        direction,
        metrics,
    )

    result["legacy_v1_evaluated"] = True
    result["legacy_v1_support_score"] = (
        legacy_v1_support
    )
    result["legacy_v1_against_score"] = (
        legacy_v1_against
    )
    result["legacy_v1_evidence"] = (
        legacy_v1_evidence[:12]
    )

    if (
        legacy_v1_support
        >= RITHMIC_SETUP_MIN_DECISIVE_SCORE
        and legacy_v1_support
        > legacy_v1_against
    ):
        result["legacy_v1_alignment"] = (
            f"SUPPORTS_{direction}"
        )

    elif (
        legacy_v1_against
        >= RITHMIC_SETUP_MIN_DECISIVE_SCORE
        and legacy_v1_against
        > legacy_v1_support
    ):
        result["legacy_v1_alignment"] = (
            f"AGAINST_{direction}"
        )

    elif (
        legacy_v1_support == 0
        and legacy_v1_against == 0
    ):
        result["legacy_v1_alignment"] = (
            "NEUTRAL_INSUFFICIENT_RITHMIC_EVIDENCE"
        )

    else:
        result["legacy_v1_alignment"] = (
            "NEUTRAL_OR_MIXED_RITHMIC_EVIDENCE"
        )

    (
        evidence_families_v2,
        evidence_load_reason,
        evidence_bridge_age_seconds,
    ) = _load_phase5g_evidence_families_v2(
        result.get("rithmic_symbol")
    )
'''

if text.count(v2_loader_anchor) != 1:
    raise SystemExit(
        "[STOP] V2 loader anchor mismatch"
    )

text = text.replace(
    v2_loader_anchor,
    v1_shadow_insert,
    1,
)


# ============================================================
# 3. Store V2 feed/regime metadata.
#    These remain non-voting context.
# ============================================================

old_feed = '''    feed_gate = (
        evidence_families_v2.get("feed_gate")
        if isinstance(
            evidence_families_v2.get("feed_gate"),
            dict,
        )
        else {}
    )

    if feed_gate.get("usable") is not True:
'''

new_feed = '''    feed_gate = (
        evidence_families_v2.get("feed_gate")
        if isinstance(
            evidence_families_v2.get("feed_gate"),
            dict,
        )
        else {}
    )

    result["evidence_feed_status"] = _safe_text(
        feed_gate.get("feed_status"),
        "UNKNOWN",
    ).upper()

    modifiers = (
        evidence_families_v2.get("modifiers")
        if isinstance(
            evidence_families_v2.get("modifiers"),
            dict,
        )
        else {}
    )

    regime_context = (
        modifiers.get("order_flow_regime")
        if isinstance(
            modifiers.get("order_flow_regime"),
            dict,
        )
        else {}
    )

    result["evidence_order_flow_regime"] = (
        _safe_text(
            regime_context.get("regime"),
            "UNAVAILABLE",
        ).upper()
    )

    if feed_gate.get("usable") is not True:
'''

if text.count(old_feed) != 1:
    raise SystemExit(
        "[STOP] feed-gate anchor mismatch"
    )

text = text.replace(
    old_feed,
    new_feed,
    1,
)


# ============================================================
# 4. Replace Telegram formatter.
# ============================================================

formatter = r'''def format_rithmic_setup_verdict_telegram_block(
    verdict: dict | None,
) -> str:
    """Format V1 shadow + V2 production Rithmic context."""

    verdict = (
        verdict
        if isinstance(verdict, dict)
        else {}
    )

    state = _safe_text(
        verdict.get("verdict"),
        "UNAVAILABLE",
    ).upper()

    direction = _safe_text(
        verdict.get("setup_direction"),
        "UNKNOWN",
    ).upper()

    reason = _safe_text(
        verdict.get("reason"),
        "rithmic_context_unavailable",
    )
    reason_lower = reason.lower()

    if state == "SUPPORTS_SETUP":
        headline = (
            f"🟢 RITHMIC: SUPPORTS {direction}"
        )

    elif state == "AGAINST_SETUP":
        headline = (
            f"🔴 RITHMIC: AGAINST {direction}"
        )

    elif state == "NEUTRAL":
        if (
            "coverage_below_minimum"
            in reason_lower
        ):
            headline = (
                "⚪ RITHMIC: NEUTRAL / "
                "INSUFFICIENT COVERAGE"
            )
        else:
            headline = (
                "⚪ RITHMIC: NEUTRAL / MIXED"
            )

    else:
        if any(
            token in reason_lower
            for token in (
                "stale",
                "not_fully_fresh",
                "source_age",
                "age_missing",
            )
        ):
            headline = (
                "⚪ RITHMIC: UNAVAILABLE / STALE"
            )

        elif any(
            token in reason_lower
            for token in (
                "disconnect",
                "not_connected",
                "connection",
            )
        ):
            headline = (
                "⚪ RITHMIC: UNAVAILABLE / "
                "DISCONNECTED"
            )

        else:
            headline = (
                "⚪ RITHMIC: UNAVAILABLE"
            )

    symbol = _safe_text(
        verdict.get("rithmic_symbol"),
        "RITHMIC",
    )

    exchange = _safe_text(
        verdict.get("exchange"),
        "COMEX",
    )

    source_age = _safe_float(
        verdict.get("source_age_seconds")
    )

    cache_age = _safe_float(
        verdict.get("cache_age_seconds")
    )

    display_age = (
        source_age
        if source_age is not None
        else cache_age
    )

    if display_age is None:
        freshness = "Freshness unavailable"

    elif (
        display_age
        <= RITHMIC_SETUP_CACHE_MAX_AGE_SECONDS
    ):
        freshness = (
            f"Fresh {round(display_age, 1)}s"
        )

    else:
        freshness = (
            f"Stale {round(display_age, 1)}s"
        )

    lines = [
        headline,
        f"{symbol} | {exchange} | {freshness}",
    ]

    # ========================================================
    # V1 LEGACY — SHADOW ONLY
    # ========================================================

    if bool(
        verdict.get("legacy_v1_evaluated")
    ):
        metrics = (
            verdict.get("metrics")
            if isinstance(
                verdict.get("metrics"),
                dict,
            )
            else {}
        )

        trades = verdict.get("trade_count")

        trades_label = (
            str(trades)
            if trades is not None
            else "N/A"
        )

        v1_support = int(
            verdict.get(
                "legacy_v1_support_score",
                0,
            )
            or 0
        )

        v1_against = int(
            verdict.get(
                "legacy_v1_against_score",
                0,
            )
            or 0
        )

        lines.extend(
            [
                "",
                "V1 LEGACY — SHADOW ONLY",
                (
                    f"Trades {trades_label} | "
                    f"Δ {_format_signed(metrics.get('delta'))} | "
                    f"CumΔ {_format_signed(metrics.get('cumulative_delta'))} | "
                    f"DOM {_format_signed(metrics.get('dom_depth_imbalance'))}"
                ),
                (
                    f"Evidence: {v1_support} SUPPORT / "
                    f"{v1_against} AGAINST"
                ),
            ]
        )

    # ========================================================
    # V2 — production Rithmic verdict model
    # ========================================================

    family_states = (
        verdict.get("evidence_family_states")
        if isinstance(
            verdict.get(
                "evidence_family_states"
            ),
            dict,
        )
        else {}
    )

    if family_states:
        lines.extend(
            [
                "",
                "V2 EVIDENCE FAMILIES — VERDICT MODEL",
            ]
        )

        family_labels = (
            (
                "AGGRESSION",
                "Aggression",
            ),
            (
                "AUCTION_PROFILE",
                "Auction / Profile",
            ),
            (
                "FOOTPRINT_ACCEPTANCE",
                "Footprint",
            ),
            (
                "ABSORPTION_EXHAUSTION",
                "Absorp / Exhaust",
            ),
            (
                "LIQUIDITY_DYNAMICS",
                "Liquidity",
            ),
            (
                "DIVERGENCE_TRAP",
                "Divergence / Trap",
            ),
        )

        opposite = (
            "SELL"
            if direction == "BUY"
            else "BUY"
        )

        for key, label in family_labels:
            family_state = _safe_text(
                family_states.get(key),
                "UNAVAILABLE",
            ).upper()

            if (
                direction in {"BUY", "SELL"}
                and family_state == direction
            ):
                marker = "🟢"
                relative = "SUPPORT"

            elif (
                direction in {"BUY", "SELL"}
                and family_state == opposite
            ):
                marker = "🔴"
                relative = "AGAINST"

            elif family_state == "NEUTRAL":
                marker = "⚪"
                relative = "NEUTRAL"

            elif family_state == "CONFLICT":
                marker = "🟡"
                relative = "CONFLICT"

            else:
                marker = "⚫"
                relative = "N/A"

            lines.append(
                f"{label}: {marker} {relative}"
            )

        v2_support = int(
            verdict.get(
                "support_score",
                0,
            )
            or 0
        )

        v2_against = int(
            verdict.get(
                "against_score",
                0,
            )
            or 0
        )

        coverage = _safe_text(
            verdict.get(
                "evidence_family_coverage"
            ),
            "0/6",
        )

        coverage = (
            coverage.replace(
                "/",
                " / ",
                1,
            )
            if "/" in coverage
            else coverage
        )

        regime = _safe_text(
            verdict.get(
                "evidence_order_flow_regime"
            ),
            "UNAVAILABLE",
        ).upper()

        feed = _safe_text(
            verdict.get(
                "evidence_feed_status"
            ),
            "UNKNOWN",
        ).upper()

        lines.extend(
            [
                "",
                (
                    f"Families: {v2_support} SUPPORT / "
                    f"{v2_against} AGAINST"
                ),
                f"Coverage: {coverage}",
                f"Regime: {regime}",
                f"Feed Integrity: {feed}",
            ]
        )

    elif state == "UNAVAILABLE":
        lines.extend(
            [
                "",
                "V2 VERDICT MODEL",
                "Reason: " + reason,
            ]
        )

    lines.extend(
        [
            "",
            (
                "Mode: OBSERVE ONLY — "
                "NO EXECUTION AUTHORITY"
            ),
        ]
    )

    return "\n".join(lines)
'''


tree = ast.parse(text)

node = None

for candidate in tree.body:
    if (
        isinstance(candidate, ast.FunctionDef)
        and candidate.name
        == "format_rithmic_setup_verdict_telegram_block"
    ):
        node = candidate
        break

if node is None:
    raise SystemExit(
        "[STOP] formatter not found"
    )

source_lines = text.splitlines()

text = "\n".join(
    source_lines[: node.lineno - 1]
    + formatter.rstrip("\n").splitlines()
    + source_lines[node.end_lineno :]
) + "\n"


# ============================================================
# 5. Dual-model regression test.
# ============================================================

test_source = r'''from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.rithmic_setup_verdict as rv


def test_v1_shadow_and_v2_both_display() -> None:
    verdict = {
        "verdict": "NEUTRAL",
        "setup_direction": "BUY",
        "reason": (
            "evidence_family_coverage_below_minimum"
        ),
        "rithmic_symbol": "GCZ6",
        "exchange": "COMEX",
        "source_age_seconds": 0.4,
        "trade_count": 491,
        "metrics": {
            "delta": -143.0,
            "cumulative_delta": -143.0,
            "dom_depth_imbalance": -0.038,
        },

        "legacy_v1_evaluated": True,
        "legacy_v1_support_score": 2,
        "legacy_v1_against_score": 1,
        "legacy_v1_alignment": "SUPPORTS_BUY",
        "legacy_v1_mode": "SHADOW_ONLY",
        "legacy_v1_can_influence_decision": False,

        "support_score": 0,
        "against_score": 1,
        "evidence_family_coverage": "3/6",
        "evidence_family_states": {
            "AGGRESSION": "SELL",
            "AUCTION_PROFILE": "NEUTRAL",
            "FOOTPRINT_ACCEPTANCE": "UNAVAILABLE",
            "ABSORPTION_EXHAUSTION": "NEUTRAL",
            "LIQUIDITY_DYNAMICS": "UNAVAILABLE",
            "DIVERGENCE_TRAP": "UNAVAILABLE",
        },
        "evidence_feed_status": "HEALTHY",
        "evidence_order_flow_regime": (
            "SELL_FLOW_EFFECTIVE"
        ),

        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
    }

    block = (
        rv
        .format_rithmic_setup_verdict_telegram_block(
            verdict
        )
    )

    assert "V1 LEGACY — SHADOW ONLY" in block
    assert "Trades 491" in block
    assert (
        "Evidence: 2 SUPPORT / 1 AGAINST"
        in block
    )

    assert (
        "V2 EVIDENCE FAMILIES — VERDICT MODEL"
        in block
    )

    assert (
        "Aggression: 🔴 AGAINST"
        in block
    )

    assert (
        "Families: 0 SUPPORT / 1 AGAINST"
        in block
    )

    assert "Coverage: 3 / 6" in block
    assert (
        "Regime: SELL_FLOW_EFFECTIVE"
        in block
    )
    assert (
        "Feed Integrity: HEALTHY"
        in block
    )

    print(
        "PASS: setup form displays V1 shadow "
        "and V2 family verdict together"
    )


def test_v1_disagreement_cannot_change_v2_verdict() -> None:
    """
    Prove the architecture:
    raw V1 can be strongly BUY while V2 is strongly SELL.
    Production verdict must follow V2.
    """

    old_registration = (
        rv._load_phase5v_registration
    )

    old_loader = (
        rv._load_phase5g_evidence_families_v2
    )

    try:
        rv._load_phase5v_registration = (
            lambda: {
                "registered": True,
                "reason": "ok",
                "payload": {
                    "symbol": "GCZ6",
                    "source_market": "COMEX",
                },
            }
        )

        rv._load_phase5g_evidence_families_v2 = (
            lambda symbol: (
                {
                    "engine": (
                        "RITHMIC_EVIDENCE_FAMILIES_V2"
                    ),
                    "feed_gate": {
                        "usable": True,
                        "reason": "healthy",
                        "feed_status": "HEALTHY",
                    },
                    "families": {
                        "AGGRESSION": {
                            "state": "SELL",
                            "reason": "test",
                        },
                        "AUCTION_PROFILE": {
                            "state": "SELL",
                            "reason": "test",
                        },
                        "FOOTPRINT_ACCEPTANCE": {
                            "state": "UNAVAILABLE",
                            "reason": "test",
                        },
                        "ABSORPTION_EXHAUSTION": {
                            "state": "NEUTRAL",
                            "reason": "test",
                        },
                        "LIQUIDITY_DYNAMICS": {
                            "state": "NEUTRAL",
                            "reason": "test",
                        },
                        "DIVERGENCE_TRAP": {
                            "state": "NEUTRAL",
                            "reason": "test",
                        },
                    },
                    "modifiers": {
                        "order_flow_regime": {
                            "regime": "SELL_FLOW_EFFECTIVE",
                        },
                    },
                    "decision_impact": "NONE",
                    "can_influence_decision": False,
                    "safe_for_execution": False,
                    "execution_allowed": False,
                },
                "ok",
                0.2,
            )
        )

        # Strongly bullish legacy raw metrics.
        context = {
            "rithmic": {
                "available": True,
                "status": "OBSERVE_ONLY_READY",
                "rithmic_symbol": "GCZ6",
                "exchange": "COMEX",
                "cache_status": "FRESH_CACHE",
                "cache_age_seconds": 0.2,
                "freshness": {
                    "snapshot_age_seconds": 0.2,
                    "snapshot_fresh": True,
                    "last_trade_age_seconds": 0.2,
                    "last_bbo_age_seconds": 0.2,
                    "last_order_book_age_seconds": 0.2,
                    "has_fresh_trade": True,
                    "has_fresh_bbo": True,
                    "has_fresh_order_book": True,
                },
                "metrics": {
                    "trade_count": 50,
                    "bbo_count": 50,
                    "nonzero_bbo_count": 50,
                    "order_book_count": 50,
                    "delta": 50.0,
                    "cumulative_delta": 100.0,
                    "dom_depth_imbalance": 0.8,
                    "dom_bid_depth": 5000.0,
                    "dom_ask_depth": 1000.0,
                },
            }
        }

        result = (
            rv.build_rithmic_setup_verdict(
                context,
                "BUY",
            )
        )

    finally:
        rv._load_phase5v_registration = (
            old_registration
        )

        rv._load_phase5g_evidence_families_v2 = (
            old_loader
        )

    assert result["legacy_v1_evaluated"] is True
    assert (
        result["legacy_v1_support_score"]
        >= 2
    )

    # V2 is two independent SELL families.
    assert result["against_score"] == 2
    assert result["support_score"] == 0

    assert result["verdict"] == "AGAINST_SETUP"
    assert result["alignment"] == "AGAINST_BUY"

    assert result["decision_impact"] == "NONE"
    assert (
        result["can_influence_decision"]
        is False
    )
    assert result["execution_allowed"] is False

    print(
        "PASS: V1 shadow disagreement cannot "
        "override production V2 verdict"
    )


def test_source_contains_explicit_shadow_policy() -> None:
    source = Path(
        rv.__file__
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        '"legacy_v1_mode": "SHADOW_ONLY"'
        in source
    )

    assert (
        '"legacy_v1_can_influence_decision": False'
        in source
    )

    print(
        "PASS: V1 legacy scorer is explicitly "
        "marked shadow-only/non-authoritative"
    )


def main() -> None:
    test_v1_shadow_and_v2_both_display()
    test_v1_disagreement_cannot_change_v2_verdict()
    test_source_contains_explicit_shadow_policy()

    print("")
    print(
        "[PASS] Rithmic dual V1-shadow / "
        "V2-verdict setup-form contract verified."
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

    created.append(
        NEW_TEST
    )

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
        *REGRESSION_TESTS,
    )

    for test in tests:
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
                f"regression failed: "
                f"{test.relative_to(ROOT)}"
            )

    # Production V2 must still use the family scorer.
    source = VERDICT.read_text(
        encoding="utf-8-sig"
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
        "score_rithmic_evidence_families_for_direction("
        not in build_source
    ):
        raise RuntimeError(
            "V2 family scorer missing from production build"
        )

    if (
        "legacy_v1_can_influence_decision"
        not in source
    ):
        raise RuntimeError(
            "V1 shadow safety marker missing"
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
        "[ROLLBACK] dual V1/V2 presentation "
        "restored from backup."
    )

    raise


print("")
print(
    "[PASS] dual V1-shadow + V2-verdict "
    "setup-form presentation applied"
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
    "[SAFETY] V1 legacy scoring is SHADOW ONLY"
)

print(
    "[SAFETY] V2 Evidence Families remains "
    "the production Rithmic verdict model"
)

print(
    "[SAFETY] V1/V2 disagreement is preserved "
    "for research rather than merged"
)

print(
    "[SAFETY] MT5 decision/execution authority remains NONE"
)
