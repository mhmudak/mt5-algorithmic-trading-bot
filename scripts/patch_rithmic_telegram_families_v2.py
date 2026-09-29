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
    / "test_rithmic_setup_verdict_telegram_families_v2.py"
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
    / f"rithmic_telegram_families_v2_{stamp}"
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

if not VERDICT.exists():
    raise SystemExit(
        "[STOP] missing src/rithmic_setup_verdict.py"
    )

for test in REGRESSION_TESTS:
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
        "[STOP] staged verdict changes detected"
    )


text = VERDICT.read_text(
    encoding="utf-8-sig",
)


# ============================================================
# 1. Add V2 presentation metadata to the result contract.
# ============================================================

old_defaults = '''        "evidence_family_states": {},
        "evidence_family_reasons": {},
    }
'''

new_defaults = '''        "evidence_family_states": {},
        "evidence_family_reasons": {},
        "evidence_feed_status": None,
        "evidence_order_flow_regime": None,
    }
'''

if text.count(old_defaults) != 1:
    raise SystemExit(
        "[STOP] verdict result-default anchor mismatch"
    )

text = text.replace(
    old_defaults,
    new_defaults,
    1,
)


# ============================================================
# 2. Persist feed integrity + order-flow regime from V2.
#
# They remain context/synthesis metadata, never votes.
# ============================================================

old_feed_block = '''    feed_gate = (
        evidence_families_v2.get("feed_gate")
        if isinstance(
            evidence_families_v2.get("feed_gate"),
            dict,
        )
        else {}
    )

    if feed_gate.get("usable") is not True:
'''

new_feed_block = '''    feed_gate = (
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

    order_flow_regime = (
        modifiers.get("order_flow_regime")
        if isinstance(
            modifiers.get("order_flow_regime"),
            dict,
        )
        else {}
    )

    result["evidence_order_flow_regime"] = _safe_text(
        order_flow_regime.get("regime"),
        "UNAVAILABLE",
    ).upper()

    if feed_gate.get("usable") is not True:
'''

if text.count(old_feed_block) != 1:
    raise SystemExit(
        "[STOP] V2 feed-gate anchor mismatch"
    )

text = text.replace(
    old_feed_block,
    new_feed_block,
    1,
)


# ============================================================
# 3. Replace formatter function using AST boundaries.
# ============================================================

formatter_source = r'''def format_rithmic_setup_verdict_telegram_block(
    verdict: dict | None,
) -> str:
    """Format compact display-only Rithmic context for directional alerts."""

    verdict = verdict if isinstance(verdict, dict) else {}

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
        headline = f"🟢 RITHMIC: SUPPORTS {direction}"

    elif state == "AGAINST_SETUP":
        headline = f"🔴 RITHMIC: AGAINST {direction}"

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

    evidence_model = _safe_text(
        verdict.get("evidence_model"),
        "",
    ).upper()

    family_states = (
        verdict.get("evidence_family_states")
        if isinstance(
            verdict.get("evidence_family_states"),
            dict,
        )
        else {}
    )

    is_v2 = bool(
        evidence_model
        == "RITHMIC_EVIDENCE_FAMILIES_V2"
        or family_states
    )

    if is_v2:
        lines.append("")

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

            elif family_state == "UNAVAILABLE":
                marker = "⚫"
                relative = "N/A"

            else:
                marker = "⚫"
                relative = "N/A"

            lines.append(
                f"{label}: {marker} {relative}"
            )

        support = int(
            verdict.get(
                "support_score",
                0,
            )
            or 0
        )

        against = int(
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

        coverage_display = (
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

        feed_status = _safe_text(
            verdict.get(
                "evidence_feed_status"
            ),
            "UNKNOWN",
        ).upper()

        lines.extend(
            [
                "",
                (
                    f"Families: {support} SUPPORT / "
                    f"{against} AGAINST"
                ),
                f"Coverage: {coverage_display}",
                f"Regime: {regime}",
                (
                    "Feed Integrity: "
                    f"{feed_status}"
                ),
            ]
        )

    else:
        if state in {
            "UNAVAILABLE",
            "NEUTRAL",
        }:
            lines.append(
                "Reason: " + reason
            )

    lines.append(
        "Mode: OBSERVE ONLY — "
        "NO EXECUTION AUTHORITY"
    )

    return "\n".join(lines)
'''


tree = ast.parse(text)

formatter_node = None

for node in tree.body:
    if (
        isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and node.name
        == "format_rithmic_setup_verdict_telegram_block"
    ):
        formatter_node = node
        break

if formatter_node is None:
    raise SystemExit(
        "[STOP] formatter function not found"
    )

lines = text.splitlines()

start = formatter_node.lineno - 1
end = formatter_node.end_lineno

replacement_lines = (
    formatter_source.rstrip("\n").splitlines()
)

new_lines = (
    lines[:start]
    + replacement_lines
    + lines[end:]
)

text = "\n".join(new_lines) + "\n"


# ============================================================
# 4. Focused formatter regression.
# ============================================================

test_source = r'''from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.rithmic_setup_verdict as rv


def base_verdict(
    direction: str,
) -> dict:
    return {
        "verdict": "NEUTRAL",
        "alignment": (
            "NEUTRAL_INSUFFICIENT_"
            "EVIDENCE_FAMILY_COVERAGE"
        ),
        "reason": (
            "evidence_family_coverage_"
            "below_minimum"
        ),
        "setup_direction": direction,
        "rithmic_symbol": "GCZ6",
        "exchange": "COMEX",
        "source_age_seconds": 4.9,
        "cache_age_seconds": 0.2,
        "trade_count": 491,

        # Deliberately populate raw metrics.
        # V2 Telegram output must not display them.
        "metrics": {
            "delta": -143.0,
            "cumulative_delta": -143.0,
            "dom_depth_imbalance": -0.038,
        },

        "evidence_model": (
            "RITHMIC_EVIDENCE_FAMILIES_V2"
        ),
        "evidence_family_coverage": "3/6",
        "evidence_family_available_count": 3,
        "evidence_family_unavailable_count": 3,
        "evidence_family_states": {
            "AGGRESSION": "SELL",
            "AUCTION_PROFILE": "NEUTRAL",
            "FOOTPRINT_ACCEPTANCE": (
                "UNAVAILABLE"
            ),
            "ABSORPTION_EXHAUSTION": (
                "NEUTRAL"
            ),
            "LIQUIDITY_DYNAMICS": (
                "UNAVAILABLE"
            ),
            "DIVERGENCE_TRAP": (
                "UNAVAILABLE"
            ),
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


def test_buy_relative_display() -> None:
    verdict = base_verdict("BUY")
    verdict["support_score"] = 0
    verdict["against_score"] = 1

    block = (
        rv
        .format_rithmic_setup_verdict_telegram_block(
            verdict
        )
    )

    assert block.startswith(
        "⚪ RITHMIC: NEUTRAL / "
        "INSUFFICIENT COVERAGE"
    )

    assert (
        "GCZ6 | COMEX | Fresh 4.9s"
        in block
    )

    assert (
        "Aggression: 🔴 AGAINST"
        in block
    )

    assert (
        "Auction / Profile: ⚪ NEUTRAL"
        in block
    )

    assert (
        "Footprint: ⚫ N/A"
        in block
    )

    assert (
        "Absorp / Exhaust: ⚪ NEUTRAL"
        in block
    )

    assert (
        "Liquidity: ⚫ N/A"
        in block
    )

    assert (
        "Divergence / Trap: ⚫ N/A"
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

    assert (
        "Mode: OBSERVE ONLY — "
        "NO EXECUTION AUTHORITY"
        in block
    )

    print(
        "PASS: BUY Telegram block maps SELL "
        "aggression to AGAINST setup"
    )


def test_sell_relative_display() -> None:
    verdict = base_verdict("SELL")
    verdict["support_score"] = 1
    verdict["against_score"] = 0

    block = (
        rv
        .format_rithmic_setup_verdict_telegram_block(
            verdict
        )
    )

    assert (
        "Aggression: 🟢 SUPPORT"
        in block
    )

    assert (
        "Families: 1 SUPPORT / 0 AGAINST"
        in block
    )

    print(
        "PASS: SELL Telegram block maps the "
        "same SELL aggression to SUPPORT setup"
    )


def test_raw_correlated_metrics_are_hidden() -> None:
    verdict = base_verdict("SELL")
    verdict["support_score"] = 1
    verdict["against_score"] = 0

    block = (
        rv
        .format_rithmic_setup_verdict_telegram_block(
            verdict
        )
    )

    assert "Trades " not in block
    assert "CumΔ" not in block
    assert "DOM " not in block

    # Do not reintroduce raw delta as a display vote.
    assert "| Δ " not in block

    print(
        "PASS: V2 Telegram block does not "
        "re-display raw delta/CVD/DOM scoring"
    )


def test_unavailable_fallback_remains_safe() -> None:
    block = (
        rv
        .format_rithmic_setup_verdict_telegram_block(
            {
                "verdict": "UNAVAILABLE",
                "setup_direction": "BUY",
                "reason": (
                    "rithmic_source_stale"
                ),
                "rithmic_symbol": "GCZ6",
                "exchange": "COMEX",
                "source_age_seconds": 9.0,
                "decision_impact": "NONE",
                "can_influence_decision": False,
                "safe_for_execution": False,
                "execution_allowed": False,
            }
        )
    )

    assert block.startswith(
        "⚪ RITHMIC: UNAVAILABLE / STALE"
    )

    assert (
        "Reason: rithmic_source_stale"
        in block
    )

    assert (
        "Mode: OBSERVE ONLY — "
        "NO EXECUTION AUTHORITY"
        in block
    )

    print(
        "PASS: pre-V2 unavailable states remain "
        "compact and fail-safe"
    )


def test_production_metadata_is_persisted() -> None:
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
                            "state": "BUY",
                            "reason": "test",
                        },
                        "AUCTION_PROFILE": {
                            "state": "BUY",
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
                            "regime": (
                                "BUY_FLOW_EFFECTIVE"
                            ),
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
                    "delta": 10.0,
                    "cumulative_delta": 20.0,
                    "dom_depth_imbalance": 0.1,
                    "dom_bid_depth": 1000.0,
                    "dom_ask_depth": 900.0,
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

    assert (
        result["evidence_feed_status"]
        == "HEALTHY"
    )

    assert (
        result["evidence_order_flow_regime"]
        == "BUY_FLOW_EFFECTIVE"
    )

    assert (
        result["decision_impact"]
        == "NONE"
    )

    assert (
        result["can_influence_decision"]
        is False
    )

    assert (
        result["execution_allowed"]
        is False
    )

    print(
        "PASS: production verdict persists "
        "feed/regime metadata without authority"
    )


def main() -> None:
    test_buy_relative_display()
    test_sell_relative_display()
    test_raw_correlated_metrics_are_hidden()
    test_unavailable_fallback_remains_safe()
    test_production_metadata_is_persisted()

    print("")
    print(
        "[PASS] Rithmic Evidence Families V2 "
        "Telegram presentation verified."
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

    source_after = VERDICT.read_text(
        encoding="utf-8-sig",
    )

    formatter_start = source_after.index(
        "def format_rithmic_setup_verdict_telegram_block("
    )

    formatter_source_after = source_after[
        formatter_start:
    ]

    forbidden_display = (
        "Trades {trades_label}",
        "CumΔ",
        "dom_depth_imbalance'))}",
    )

    for token in forbidden_display:
        if token in formatter_source_after:
            raise RuntimeError(
                "legacy raw-metric Telegram display "
                f"still present: {token}"
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
        "[ROLLBACK] V2 Telegram presentation "
        "restored from backup."
    )

    raise


print("")
print(
    "[PASS] Evidence Families V2 Telegram "
    "presentation applied"
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
    "[SAFETY] raw Δ/CumΔ/DOM removed from "
    "main V2 Telegram presentation"
)

print(
    "[SAFETY] family rows are setup-relative "
    "display only"
)

print(
    "[SAFETY] Regime and Feed Integrity remain "
    "non-voting context"
)

print(
    "[SAFETY] MT5 execution authority remains NONE"
)
