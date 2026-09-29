import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = "feature/better-entry-optimizer"

PARTICIPATION = ROOT / "src" / "market_participation_context.py"
VERDICT_MODULE = ROOT / "src" / "rithmic_setup_verdict.py"
TEST_V1 = ROOT / "scripts" / "test_rithmic_setup_verdict_top_form_v1.py"
TEST_V2 = ROOT / "scripts" / "test_rithmic_setup_verdict_source_freshness_v2.py"


def stop(message: str) -> None:
    raise SystemExit(f"[STOP] {message}")


def git_output(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        stop(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def read_text(path: Path) -> str:
    if not path.exists():
        stop(f"Missing required file: {path}")
    return path.read_text(encoding="utf-8")


def require_count(text: str, anchor: str, expected: int, label: str) -> None:
    count = text.count(anchor)
    if count != expected:
        stop(f"Anchor mismatch for {label}: expected {expected}, found {count}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    require_count(text, old, 1, label)
    return text.replace(old, new, 1)


def replace_between(
    text: str,
    start_marker: str,
    end_marker: str,
    replacement: str,
    label: str,
) -> str:
    require_count(text, start_marker, 1, f"{label} start")
    require_count(text, end_marker, 1, f"{label} end")
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[:start] + replacement + text[end:]


def compile_text(path: Path, text: str) -> None:
    try:
        compile(text, str(path), "exec")
    except SyntaxError as exc:
        stop(f"Compile failed for {path}: {exc}")


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp_rithmic_source_freshness_v2")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def backup_file(path: Path, backup_root: Path) -> None:
    if not path.exists():
        return
    relative = path.relative_to(ROOT)
    target = backup_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


branch = git_output("rev-parse", "--abbrev-ref", "HEAD")
if branch != EXPECTED_BRANCH:
    stop(f"Expected branch {EXPECTED_BRANCH}, found {branch}")
print(f"[OK] Branch={branch}")

participation = read_text(PARTICIPATION)
verdict = read_text(VERDICT_MODULE)
test_v1 = read_text(TEST_V1)

# Ensure this helper is being applied after V1, not to an unrelated tree.
for required, label, source in [
    ('"trade_count": metrics.get("trade_count")', "V1 participation metrics", participation),
    ('RITHMIC_SETUP_CACHE_MAX_AGE_SECONDS = 5.0', "V1 verdict module", verdict),
    ('detected_rithmic_verdict_block', "V1 focused test", test_v1),
]:
    if required not in source:
        stop(f"Expected V1 anchor missing: {label}")

# -----------------------------------------------------------------------------
# 1) Preserve authoritative Phase 5C sample/freshness information while the
#    snapshot is flattened into market-participation context.
# -----------------------------------------------------------------------------
snapshot_anchor = '''        snapshot = provider.get_latest_snapshot(symbol)\n        snapshot = snapshot if isinstance(snapshot, dict) else {}\n        metrics = snapshot.get("metrics") or {}\n        available = bool(snapshot.get("available"))\n\n        return {\n'''
snapshot_replacement = '''        snapshot = provider.get_latest_snapshot(symbol)\n        snapshot = snapshot if isinstance(snapshot, dict) else {}\n        metrics = snapshot.get("metrics") or {}\n        rithmic_status = (\n            snapshot.get("rithmic_status")\n            if isinstance(snapshot.get("rithmic_status"), dict)\n            else {}\n        )\n        sample = (\n            rithmic_status.get("sample")\n            if isinstance(rithmic_status.get("sample"), dict)\n            else {}\n        )\n        order_book = (\n            rithmic_status.get("order_book")\n            if isinstance(rithmic_status.get("order_book"), dict)\n            else {}\n        )\n        freshness = (\n            rithmic_status.get("freshness")\n            if isinstance(rithmic_status.get("freshness"), dict)\n            else {}\n        )\n        available = bool(snapshot.get("available"))\n\n        return {\n'''
participation = replace_once(
    participation,
    snapshot_anchor,
    snapshot_replacement,
    "Rithmic snapshot/sample/freshness extraction",
)

metrics_old = '''                "trade_count": metrics.get("trade_count"),\n                "bbo_count": metrics.get("bbo_count"),\n                "nonzero_bbo_count": metrics.get("nonzero_bbo_count"),\n                "order_book_count": metrics.get("order_book_count"),\n                "last_bid": (\n                    metrics.get("last_bid")\n                    if metrics.get("last_bid") is not None\n                    else metrics.get("latest_bid")\n                ),\n                "last_ask": (\n                    metrics.get("last_ask")\n                    if metrics.get("last_ask") is not None\n                    else metrics.get("latest_ask")\n                ),\n'''
metrics_new = '''                "trade_count": (\n                    metrics.get("trade_count")\n                    if metrics.get("trade_count") is not None\n                    else sample.get("rolling_trade_count")\n                ),\n                "bbo_count": (\n                    metrics.get("bbo_count")\n                    if metrics.get("bbo_count") is not None\n                    else sample.get("bbo_count")\n                ),\n                "nonzero_bbo_count": (\n                    metrics.get("nonzero_bbo_count")\n                    if metrics.get("nonzero_bbo_count") is not None\n                    else sample.get("nonzero_bbo_count")\n                ),\n                "order_book_count": (\n                    metrics.get("order_book_count")\n                    if metrics.get("order_book_count") is not None\n                    else sample.get("order_book_count")\n                ),\n                "last_bid": (\n                    metrics.get("last_bid")\n                    if metrics.get("last_bid") is not None\n                    else (\n                        metrics.get("latest_bid")\n                        if metrics.get("latest_bid") is not None\n                        else order_book.get("top_bid_price")\n                    )\n                ),\n                "last_ask": (\n                    metrics.get("last_ask")\n                    if metrics.get("last_ask") is not None\n                    else (\n                        metrics.get("latest_ask")\n                        if metrics.get("latest_ask") is not None\n                        else order_book.get("top_ask_price")\n                    )\n                ),\n'''
participation = replace_once(
    participation,
    metrics_old,
    metrics_new,
    "Rithmic sample-count fallback",
)
participation = replace_once(
    participation,
    '            "freshness": (snapshot.get("rithmic_status") or {}).get("freshness"),\n',
    '            "freshness": freshness,\n',
    "Rithmic authoritative freshness passthrough",
)

# -----------------------------------------------------------------------------
# 2) Harden the operator-only verdict. A directional verdict now requires:
#      - Phase 5V observe-only registration
#      - available snapshot
#      - authoritative source freshness flags + ages <= 5s
#      - fresh in-process cache when cache metadata is present
#      - known trade/BBO/order-book sample counts
#      - >= 5 rolling trades
#      - two-sided DOM and complete delta/DOM metrics
#    Missing/invalid quality evidence returns UNAVAILABLE, never directional.
# -----------------------------------------------------------------------------
new_build_function = r'''def build_rithmic_setup_verdict(
    context: dict | None,
    signal: str | None,
) -> dict[str, Any]:
    """Build an operator-only Rithmic verdict. It has zero trading authority."""

    direction = _safe_text(signal).upper()
    result: dict[str, Any] = {
        "verdict": "UNAVAILABLE",
        "alignment": "NOT_AVAILABLE",
        "setup_direction": direction or "UNKNOWN",
        "supports_setup": False,
        "against_setup": False,
        "support_score": 0,
        "against_score": 0,
        "evidence": [],
        "reason": "rithmic_context_unavailable",
        "source": "RITHMIC_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
        "registered_observe_only": False,
        "rithmic_symbol": None,
        "exchange": None,
        "cache_age_seconds": None,
        "source_age_seconds": None,
        "trade_count": None,
        "bbo_count": None,
        "nonzero_bbo_count": None,
        "order_book_count": None,
        "freshness": {},
        "metrics": {},
    }

    if direction not in {"BUY", "SELL"}:
        result["reason"] = "invalid_or_missing_setup_direction"
        return result

    registration = _load_phase5v_registration()
    result["registered_observe_only"] = bool(registration.get("registered"))
    if not result["registered_observe_only"]:
        result["reason"] = _safe_text(
            registration.get("reason"),
            "phase5v_registration_not_accepted",
        )
        return result

    registration_payload = (
        registration.get("payload")
        if isinstance(registration.get("payload"), dict)
        else {}
    )
    rithmic = (
        context.get("rithmic")
        if isinstance(context, dict)
        and isinstance(context.get("rithmic"), dict)
        else {}
    )
    metrics = (
        rithmic.get("metrics")
        if isinstance(rithmic.get("metrics"), dict)
        else {}
    )
    freshness = (
        rithmic.get("freshness")
        if isinstance(rithmic.get("freshness"), dict)
        else {}
    )

    result["rithmic_symbol"] = (
        rithmic.get("rithmic_symbol")
        or registration_payload.get("symbol")
    )
    result["exchange"] = (
        rithmic.get("exchange")
        or registration_payload.get("source_market")
    )
    result["cache_age_seconds"] = _safe_float(
        rithmic.get("cache_age_seconds")
    )
    result["metrics"] = dict(metrics)
    result["freshness"] = dict(freshness)

    registered_symbol = _safe_text(
        registration_payload.get("symbol")
    ).upper()
    current_symbol = _safe_text(
        result.get("rithmic_symbol")
    ).upper()
    if (
        registered_symbol
        and current_symbol
        and registered_symbol != current_symbol
    ):
        result["reason"] = "phase5v_symbol_mismatch"
        result["alignment"] = "NOT_AVAILABLE_SYMBOL_MISMATCH"
        return result

    if not bool(rithmic.get("available")):
        result["reason"] = _safe_text(
            rithmic.get("status"),
            "rithmic_snapshot_unavailable",
        )
        result["alignment"] = "NOT_AVAILABLE_RITHMIC_SNAPSHOT"
        return result

    # Source freshness is authoritative. The participation-cache timestamp only
    # tells us when the bot re-read the snapshot, not when COMEX last updated it.
    source_ages = {
        "snapshot_age_seconds": _safe_float(
            freshness.get("snapshot_age_seconds")
        ),
        "last_trade_age_seconds": _safe_float(
            freshness.get("last_trade_age_seconds")
        ),
        "last_bbo_age_seconds": _safe_float(
            freshness.get("last_bbo_age_seconds")
        ),
        "last_order_book_age_seconds": _safe_float(
            freshness.get("last_order_book_age_seconds")
        ),
    }
    known_source_ages = [
        value for value in source_ages.values() if value is not None
    ]
    result["source_age_seconds"] = (
        round(max(known_source_ages), 3)
        if known_source_ages
        else None
    )

    required_fresh_flags = {
        "snapshot_fresh": freshness.get("snapshot_fresh"),
        "has_fresh_trade": freshness.get("has_fresh_trade"),
        "has_fresh_bbo": freshness.get("has_fresh_bbo"),
        "has_fresh_order_book": freshness.get("has_fresh_order_book"),
    }
    if not freshness or any(
        value is not True for value in required_fresh_flags.values()
    ):
        result["reason"] = "rithmic_source_not_fully_fresh"
        result["alignment"] = "NOT_AVAILABLE_SOURCE_NOT_FULLY_FRESH"
        return result

    if any(value is None for value in source_ages.values()):
        result["reason"] = "rithmic_source_age_missing"
        result["alignment"] = "NOT_AVAILABLE_SOURCE_AGE_MISSING"
        return result

    if any(
        value > RITHMIC_SETUP_CACHE_MAX_AGE_SECONDS
        for value in source_ages.values()
        if value is not None
    ):
        result["reason"] = "rithmic_source_stale"
        result["alignment"] = "NOT_AVAILABLE_STALE_RITHMIC_SOURCE"
        return result

    cache_status = _safe_text(rithmic.get("cache_status")).upper()
    cache_age = result.get("cache_age_seconds")
    if (
        "STALE" in cache_status
        or "MISSING" in cache_status
        or (
            cache_age is not None
            and cache_age > RITHMIC_SETUP_CACHE_MAX_AGE_SECONDS
        )
    ):
        result["reason"] = "rithmic_cache_stale"
        result["alignment"] = "NOT_AVAILABLE_STALE_RITHMIC_CACHE"
        return result

    trade_count = _safe_float(metrics.get("trade_count"))
    bbo_count = _safe_float(metrics.get("bbo_count"))
    nonzero_bbo_count = _safe_float(metrics.get("nonzero_bbo_count"))
    order_book_count = _safe_float(metrics.get("order_book_count"))

    result["trade_count"] = int(trade_count) if trade_count is not None else None
    result["bbo_count"] = int(bbo_count) if bbo_count is not None else None
    result["nonzero_bbo_count"] = (
        int(nonzero_bbo_count) if nonzero_bbo_count is not None else None
    )
    result["order_book_count"] = (
        int(order_book_count) if order_book_count is not None else None
    )

    if trade_count is None:
        result["reason"] = "rithmic_trade_count_missing"
        result["alignment"] = "NOT_AVAILABLE_TRADE_SAMPLE_UNKNOWN"
        return result

    if trade_count < RITHMIC_SETUP_MIN_TRADES:
        result.update(
            {
                "verdict": "NEUTRAL",
                "alignment": "NEUTRAL_LOW_RITHMIC_TRADE_SAMPLE",
                "reason": "rithmic_trade_sample_below_minimum",
            }
        )
        return result

    if (
        bbo_count is None
        or nonzero_bbo_count is None
        or order_book_count is None
        or bbo_count <= 0
        or nonzero_bbo_count <= 0
        or order_book_count <= 0
    ):
        result["reason"] = "rithmic_market_structure_sample_missing"
        result["alignment"] = "NOT_AVAILABLE_MARKET_STRUCTURE_SAMPLE"
        return result

    required_numeric_metrics = {
        "delta": _safe_float(metrics.get("delta")),
        "cumulative_delta": _safe_float(metrics.get("cumulative_delta")),
        "dom_depth_imbalance": _safe_float(
            metrics.get("dom_depth_imbalance")
        ),
        "dom_bid_depth": _safe_float(metrics.get("dom_bid_depth")),
        "dom_ask_depth": _safe_float(metrics.get("dom_ask_depth")),
    }
    if any(value is None for value in required_numeric_metrics.values()):
        result["reason"] = "rithmic_required_metrics_missing"
        result["alignment"] = "NOT_AVAILABLE_REQUIRED_METRICS_MISSING"
        return result

    if (
        required_numeric_metrics["dom_bid_depth"] <= 0
        or required_numeric_metrics["dom_ask_depth"] <= 0
    ):
        result["reason"] = "rithmic_two_sided_dom_missing"
        result["alignment"] = "NOT_AVAILABLE_TWO_SIDED_DOM_MISSING"
        return result

    support, against, evidence = (
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
verdict = replace_between(
    verdict,
    "def build_rithmic_setup_verdict(\n",
    "\n\ndef _format_signed(",
    new_build_function,
    "Rithmic setup verdict builder",
)

formatter_old = '''    cache_age = _safe_float(\n        verdict.get("cache_age_seconds")\n    )\n    freshness = (\n        f"Fresh {round(cache_age, 1)}s"\n        if cache_age is not None\n        and cache_age <= RITHMIC_SETUP_CACHE_MAX_AGE_SECONDS\n        else "Freshness unavailable"\n    )\n'''
formatter_new = '''    source_age = _safe_float(\n        verdict.get("source_age_seconds")\n    )\n    cache_age = _safe_float(\n        verdict.get("cache_age_seconds")\n    )\n    display_age = (\n        source_age\n        if source_age is not None\n        else cache_age\n    )\n    freshness = (\n        f"Fresh {round(display_age, 1)}s"\n        if display_age is not None\n        and display_age <= RITHMIC_SETUP_CACHE_MAX_AGE_SECONDS\n        else "Freshness unavailable"\n    )\n'''
verdict = replace_once(
    verdict,
    formatter_old,
    formatter_new,
    "Telegram source freshness display",
)

# -----------------------------------------------------------------------------
# 3) Keep the V1 focused regression valid under the stricter V2 data contract.
# -----------------------------------------------------------------------------
test_context_start = "def _context(\n"
test_context_end = "\n\ndef main() -> None:\n"
new_test_context = r'''def _context(
    *,
    delta: float,
    cumulative_delta: float,
    dom_imbalance: float,
    bid_depth: float,
    ask_depth: float,
    trades: int = 21,
    cache_age_seconds: float = 0.2,
    symbol: str = "GCZ6",
    available: bool = True,
) -> dict:
    return {
        "source_coverage": "MT5_PLUS_RITHMIC",
        "rithmic": {
            "available": available,
            "status": "OBSERVE_ONLY_READY",
            "rithmic_symbol": symbol,
            "exchange": "COMEX",
            "cache_status": "FRESH_CACHE",
            "cache_age_seconds": cache_age_seconds,
            "freshness": {
                "snapshot_age_seconds": 0.2,
                "snapshot_fresh": True,
                "last_trade_age_seconds": 0.3,
                "last_bbo_age_seconds": 0.1,
                "last_order_book_age_seconds": 0.2,
                "has_fresh_trade": True,
                "has_fresh_bbo": True,
                "has_fresh_order_book": True,
            },
            "metrics": {
                "trade_count": trades,
                "bbo_count": 120,
                "nonzero_bbo_count": 120,
                "order_book_count": 1333,
                "delta": delta,
                "cumulative_delta": cumulative_delta,
                "dom_depth_imbalance": dom_imbalance,
                "dom_bid_depth": bid_depth,
                "dom_ask_depth": ask_depth,
            },
        },
    }
'''
test_v1 = replace_between(
    test_v1,
    test_context_start,
    test_context_end,
    new_test_context,
    "V1 regression context fixture",
)

# -----------------------------------------------------------------------------
# 4) Add a dedicated regression for the real provider payload shape observed on
#    2026-09-29: counts under rithmic_status.sample, freshness under
#    rithmic_status.freshness, and adapter metrics without sample counts.
# -----------------------------------------------------------------------------
test_v2 = r'''from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import rithmic_setup_verdict as verdict_module

try:
    from src.market_participation_context import (
        refresh_rithmic_participation_context,
    )
except ModuleNotFoundError as exc:
    # Allows this focused test to run in the patch helper's minimal dry-run
    # repository. In the real bot repo src.logger exists and this branch is not
    # used.
    if exc.name != "src.logger":
        raise
    import types

    logger_module = types.ModuleType("src.logger")

    class _NullLogger:
        def __getattr__(self, _name):
            return lambda *args, **kwargs: None

    logger_module.logger = _NullLogger()
    sys.modules["src.logger"] = logger_module
    from src.market_participation_context import (
        refresh_rithmic_participation_context,
    )


class FakeRealShapeProvider:
    def get_latest_snapshot(self, requested_symbol: str) -> dict:
        return {
            "available": True,
            "status": "OBSERVE_ONLY_READY",
            "provider": "RITHMIC_SNAPSHOT_PROVIDER",
            "symbol": "GCZ6",
            "requested_symbol": requested_symbol,
            "exchange": "COMEX",
            "data_quality": "OBSERVE_ONLY_READY",
            # Intentionally mirrors the real adapter: no sample counts here.
            "metrics": {
                "bid_volume": 9,
                "ask_volume": 12,
                "delta": 3,
                "cumulative_delta": 3,
                "footprint_imbalance": 0.142857,
                "dom_bid_depth": 2495,
                "dom_ask_depth": 3178,
                "dom_depth_imbalance": -0.120395,
                "volume_profile_poc": 4171.1,
            },
            "rithmic_status": {
                "provider_status": "OBSERVE_ONLY_READY",
                "freshness": {
                    "snapshot_age_seconds": 0.2,
                    "snapshot_fresh": True,
                    "last_trade_age_seconds": 0.4,
                    "last_bbo_age_seconds": 0.1,
                    "last_order_book_age_seconds": 0.2,
                    "has_fresh_trade": True,
                    "has_fresh_bbo": True,
                    "has_fresh_order_book": True,
                },
                "sample": {
                    "last_trade_count_total_session": 21,
                    "rolling_trade_count": 21,
                    "bbo_count": 120,
                    "nonzero_bbo_count": 120,
                    "order_book_count": 1333,
                },
                "order_book": {
                    "available": True,
                    "bid_depth": 2495,
                    "ask_depth": 3178,
                    "depth_imbalance": -0.120395,
                    "top_bid_price": 4171.5,
                    "top_ask_price": 4171.8,
                },
            },
        }


def registration_payload() -> dict:
    return {
        "provider": "RITHMIC_R_PROTOCOL",
        "provider_role": "REAL_ORDER_FLOW_SOURCE",
        "source_market": "COMEX",
        "symbol": "GCZ6",
        "registration_status": "REGISTERED_OBSERVE_ONLY",
        "provider_quality": "ACCEPTED_OBSERVE_ONLY",
        "mode": "OBSERVE_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
        "gates": {
            "can_register_observe_only": True,
            "trade_flow_decision_grade": True,
            "decision_influence_allowed": False,
            "execution_allowed": False,
        },
    }


def main() -> None:
    rithmic = refresh_rithmic_participation_context(
        symbol="XAUUSD",
        provider=FakeRealShapeProvider(),
        min_refresh_interval_seconds=0,
    )

    metrics = rithmic["metrics"]
    assert metrics["trade_count"] == 21
    assert metrics["bbo_count"] == 120
    assert metrics["nonzero_bbo_count"] == 120
    assert metrics["order_book_count"] == 1333
    assert metrics["last_bid"] == 4171.5
    assert metrics["last_ask"] == 4171.8
    assert rithmic["freshness"]["has_fresh_trade"] is True
    assert rithmic["freshness"]["has_fresh_bbo"] is True
    assert rithmic["freshness"]["has_fresh_order_book"] is True

    original_registration_path = verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            registration_path = Path(tmp_dir) / "phase5v.json"
            registration_path.write_text(
                json.dumps(registration_payload(), indent=2),
                encoding="utf-8",
            )
            verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = registration_path

            context = {"rithmic": rithmic}
            fresh = verdict_module.build_rithmic_setup_verdict(context, "BUY")
            assert fresh["verdict"] == "SUPPORTS_SETUP"
            assert fresh["alignment"] == "SUPPORTS_BUY"
            assert fresh["trade_count"] == 21
            assert fresh["bbo_count"] == 120
            assert fresh["order_book_count"] == 1333
            assert fresh["source_age_seconds"] == 0.4
            assert fresh["decision_impact"] == "NONE"
            assert fresh["can_influence_decision"] is False
            assert fresh["safe_for_execution"] is False
            assert fresh["execution_allowed"] is False

            block = verdict_module.format_rithmic_setup_verdict_telegram_block(fresh)
            assert block.startswith("🟢 RITHMIC: SUPPORTS BUY")
            assert "Fresh 0.4s" in block
            assert "Trades 21" in block
            assert "OBSERVE ONLY" in block

            missing_trade = copy.deepcopy(context)
            missing_trade["rithmic"]["metrics"].pop("trade_count", None)
            result = verdict_module.build_rithmic_setup_verdict(
                missing_trade,
                "BUY",
            )
            assert result["verdict"] == "UNAVAILABLE"
            assert result["reason"] == "rithmic_trade_count_missing"

            low_sample = copy.deepcopy(context)
            low_sample["rithmic"]["metrics"]["trade_count"] = 2
            result = verdict_module.build_rithmic_setup_verdict(
                low_sample,
                "BUY",
            )
            assert result["verdict"] == "NEUTRAL"
            assert result["alignment"] == "NEUTRAL_LOW_RITHMIC_TRADE_SAMPLE"

            missing_freshness = copy.deepcopy(context)
            missing_freshness["rithmic"].pop("freshness", None)
            result = verdict_module.build_rithmic_setup_verdict(
                missing_freshness,
                "BUY",
            )
            assert result["verdict"] == "UNAVAILABLE"
            assert result["reason"] == "rithmic_source_not_fully_fresh"

            stale_trade = copy.deepcopy(context)
            stale_trade["rithmic"]["freshness"]["last_trade_age_seconds"] = 7.0
            result = verdict_module.build_rithmic_setup_verdict(
                stale_trade,
                "BUY",
            )
            assert result["verdict"] == "UNAVAILABLE"
            assert result["reason"] == "rithmic_source_stale"

            stale_flag = copy.deepcopy(context)
            stale_flag["rithmic"]["freshness"]["has_fresh_order_book"] = False
            result = verdict_module.build_rithmic_setup_verdict(
                stale_flag,
                "BUY",
            )
            assert result["verdict"] == "UNAVAILABLE"
            assert result["reason"] == "rithmic_source_not_fully_fresh"

            missing_bbo_count = copy.deepcopy(context)
            missing_bbo_count["rithmic"]["metrics"].pop("bbo_count", None)
            result = verdict_module.build_rithmic_setup_verdict(
                missing_bbo_count,
                "BUY",
            )
            assert result["verdict"] == "UNAVAILABLE"
            assert result["reason"] == "rithmic_market_structure_sample_missing"

            one_sided_dom = copy.deepcopy(context)
            one_sided_dom["rithmic"]["metrics"]["dom_ask_depth"] = 0
            result = verdict_module.build_rithmic_setup_verdict(
                one_sided_dom,
                "BUY",
            )
            assert result["verdict"] == "UNAVAILABLE"
            assert result["reason"] == "rithmic_two_sided_dom_missing"
    finally:
        verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = original_registration_path

    for path in [
        ROOT / "src" / "market_participation_context.py",
        ROOT / "src" / "rithmic_setup_verdict.py",
    ]:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")

    print(
        "[PASS] Rithmic source-freshness hardening: real provider sample counts "
        "are flattened correctly; source freshness, missing counts, low sample, "
        "and two-sided DOM guards fail safe with decision_impact NONE."
    )


if __name__ == "__main__":
    main()
'''

# Compile every future source before touching disk.
for path, text in [
    (PARTICIPATION, participation),
    (VERDICT_MODULE, verdict),
    (TEST_V1, test_v1),
    (TEST_V2, test_v2),
]:
    compile_text(path, text)
print("[OK] All patched/new Python sources compile in-memory")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_root = ROOT / "local_backups" / f"rithmic_source_freshness_v2_{stamp}"
for path in [PARTICIPATION, VERDICT_MODULE, TEST_V1, TEST_V2]:
    backup_file(path, backup_root)
print(f"[BACKUP] {backup_root}")

atomic_write(PARTICIPATION, participation)
print(f"[UPDATED] {PARTICIPATION.relative_to(ROOT)}")
atomic_write(VERDICT_MODULE, verdict)
print(f"[UPDATED] {VERDICT_MODULE.relative_to(ROOT)}")
atomic_write(TEST_V1, test_v1)
print(f"[UPDATED] {TEST_V1.relative_to(ROOT)}")
atomic_write(TEST_V2, test_v2)
print(f"[CREATED] {TEST_V2.relative_to(ROOT)}")

for path in [PARTICIPATION, VERDICT_MODULE, TEST_V1, TEST_V2]:
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        stop(f"Post-write py_compile failed for {path}: {proc.stderr.strip()}")

print("[OK] Post-write py_compile passed")
print("[DONE] Rithmic source-freshness/sample-count hardening V2 applied.")
print("[SAFETY] Missing/stale source data cannot produce SUPPORTS/AGAINST.")
print("[SAFETY] decision_impact remains NONE; Rithmic has no execution authority.")
print("[NO BOT RESTART] Run focused regressions first.")
print("[NO COMMIT] Review/test before staging or committing.")
