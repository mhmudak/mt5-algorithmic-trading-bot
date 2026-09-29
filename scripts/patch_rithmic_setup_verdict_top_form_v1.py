import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = "feature/better-entry-optimizer"

LIVE_BOT = ROOT / "src" / "live_bot.py"
PARTICIPATION = ROOT / "src" / "market_participation_context.py"
PHASE5P = ROOT / "scripts" / "run_phase5p_event_driven_rithmic_watcher.py"
VERDICT_MODULE = ROOT / "src" / "rithmic_setup_verdict.py"
TEST_SCRIPT = ROOT / "scripts" / "test_rithmic_setup_verdict_top_form_v1.py"


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


def compile_text(path: Path, text: str) -> None:
    try:
        compile(text, str(path), "exec")
    except SyntaxError as exc:
        stop(f"Compile failed for {path}: {exc}")


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp_rithmic_verdict")
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

live = read_text(LIVE_BOT)
participation = read_text(PARTICIPATION)
phase5p = read_text(PHASE5P)

# -----------------------------------------------------------------------------
# 1) Expose trade-count/BBO/order-book fields already present in the Rithmic
#    provider snapshot so the live verdict can enforce the same low-sample guard
#    as Phase 5L/5P.
# -----------------------------------------------------------------------------
metrics_anchor = '''                "bid_volume": metrics.get("bid_volume"),
                "ask_volume": metrics.get("ask_volume"),
                "delta": metrics.get("delta"),
'''
metrics_replacement = '''                "bid_volume": metrics.get("bid_volume"),
                "ask_volume": metrics.get("ask_volume"),
                "trade_count": metrics.get("trade_count"),
                "bbo_count": metrics.get("bbo_count"),
                "nonzero_bbo_count": metrics.get("nonzero_bbo_count"),
                "order_book_count": metrics.get("order_book_count"),
                "last_bid": (
                    metrics.get("last_bid")
                    if metrics.get("last_bid") is not None
                    else metrics.get("latest_bid")
                ),
                "last_ask": (
                    metrics.get("last_ask")
                    if metrics.get("last_ask") is not None
                    else metrics.get("latest_ask")
                ),
                "delta": metrics.get("delta"),
'''
participation = replace_once(
    participation,
    metrics_anchor,
    metrics_replacement,
    "market participation Rithmic metrics",
)

# -----------------------------------------------------------------------------
# 2) Add the dedicated Rithmic-only setup verdict module.
#    Important safety properties:
#      - Phase 5V registration is mandatory.
#      - Registered symbol must equal the live Rithmic symbol.
#      - Cache older than 5s is unavailable.
#      - Fewer than 5 trades is neutral/low-sample, not directional.
#      - Verdict has decision_impact NONE and zero execution authority.
#      - Scoring mirrors the established Phase 5P semantics.
# -----------------------------------------------------------------------------
verdict_module = r'''from __future__ import annotations

import json
from pathlib import Path
from typing import Any


RITHMIC_SETUP_MIN_TRADES = 5
RITHMIC_SETUP_DOM_IMBALANCE_THRESHOLD = 0.15
RITHMIC_SETUP_MIN_DECISIVE_SCORE = 2
RITHMIC_SETUP_CACHE_MAX_AGE_SECONDS = 5.0
RITHMIC_PROVIDER_REGISTRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "order_flow"
    / "rithmic"
    / "phase5v_rithmic_observe_only_provider_registration.json"
)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        value = float(value)
        return value if value == value else None
    except Exception:
        return None


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def score_rithmic_setup_alignment_for_direction(
    direction: str,
    metrics: dict[str, Any] | None,
) -> tuple[int, int, list[str]]:
    """Score Rithmic-only evidence using the established Phase 5P semantics."""

    direction = _safe_text(direction).upper()
    metrics = metrics if isinstance(metrics, dict) else {}
    support = 0
    against = 0
    evidence: list[str] = []

    delta = _safe_float(metrics.get("delta")) or 0.0
    cumulative_delta = _safe_float(metrics.get("cumulative_delta")) or 0.0
    dom_imbalance = _safe_float(metrics.get("dom_depth_imbalance"))
    bid_depth = _safe_float(metrics.get("dom_bid_depth")) or 0.0
    ask_depth = _safe_float(metrics.get("dom_ask_depth")) or 0.0

    if direction == "BUY":
        if delta > 0:
            support += 1
            evidence.append(f"delta positive supports BUY: {delta}")
        elif delta < 0:
            against += 1
            evidence.append(f"delta negative is against BUY: {delta}")

        if cumulative_delta > 0:
            support += 1
            evidence.append(
                f"cumulative_delta positive supports BUY: {cumulative_delta}"
            )
        elif cumulative_delta < 0:
            against += 1
            evidence.append(
                f"cumulative_delta negative is against BUY: {cumulative_delta}"
            )

        if dom_imbalance is not None:
            if dom_imbalance > RITHMIC_SETUP_DOM_IMBALANCE_THRESHOLD:
                support += 1
                evidence.append(f"DOM bid-heavy supports BUY: {dom_imbalance}")
            elif dom_imbalance < -RITHMIC_SETUP_DOM_IMBALANCE_THRESHOLD:
                against += 1
                evidence.append(f"DOM ask-heavy is against BUY: {dom_imbalance}")

        if bid_depth > 0 or ask_depth > 0:
            if bid_depth > ask_depth:
                support += 1
                evidence.append(
                    f"bid_depth > ask_depth supports BUY: {bid_depth} > {ask_depth}"
                )
            elif ask_depth > bid_depth:
                against += 1
                evidence.append(
                    f"ask_depth > bid_depth is against BUY: {ask_depth} > {bid_depth}"
                )

    elif direction == "SELL":
        if delta < 0:
            support += 1
            evidence.append(f"delta negative supports SELL: {delta}")
        elif delta > 0:
            against += 1
            evidence.append(f"delta positive is against SELL: {delta}")

        if cumulative_delta < 0:
            support += 1
            evidence.append(
                f"cumulative_delta negative supports SELL: {cumulative_delta}"
            )
        elif cumulative_delta > 0:
            against += 1
            evidence.append(
                f"cumulative_delta positive is against SELL: {cumulative_delta}"
            )

        if dom_imbalance is not None:
            if dom_imbalance < -RITHMIC_SETUP_DOM_IMBALANCE_THRESHOLD:
                support += 1
                evidence.append(f"DOM ask-heavy supports SELL: {dom_imbalance}")
            elif dom_imbalance > RITHMIC_SETUP_DOM_IMBALANCE_THRESHOLD:
                against += 1
                evidence.append(f"DOM bid-heavy is against SELL: {dom_imbalance}")

        if bid_depth > 0 or ask_depth > 0:
            if ask_depth > bid_depth:
                support += 1
                evidence.append(
                    f"ask_depth > bid_depth supports SELL: {ask_depth} > {bid_depth}"
                )
            elif bid_depth > ask_depth:
                against += 1
                evidence.append(
                    f"bid_depth > ask_depth is against SELL: {bid_depth} > {ask_depth}"
                )

    return support, against, evidence


def _load_phase5v_registration() -> dict[str, Any]:
    try:
        if not RITHMIC_PROVIDER_REGISTRATION_PATH.exists():
            return {
                "registered": False,
                "reason": "phase5v_registration_missing",
                "payload": {},
            }

        payload = json.loads(
            RITHMIC_PROVIDER_REGISTRATION_PATH.read_text(encoding="utf-8")
        )
        payload = payload if isinstance(payload, dict) else {}
        gates = payload.get("gates") if isinstance(payload.get("gates"), dict) else {}

        registered = bool(
            payload.get("registration_status") == "REGISTERED_OBSERVE_ONLY"
            and payload.get("provider_quality") == "ACCEPTED_OBSERVE_ONLY"
            and payload.get("decision_impact") == "NONE"
            and not bool(payload.get("can_influence_decision"))
            and not bool(payload.get("safe_for_execution"))
            and bool(gates.get("can_register_observe_only"))
            and bool(gates.get("trade_flow_decision_grade"))
            and not bool(gates.get("decision_influence_allowed"))
            and not bool(gates.get("execution_allowed"))
        )

        return {
            "registered": registered,
            "reason": (
                "phase5v_registered_observe_only"
                if registered
                else "phase5v_registration_not_accepted"
            ),
            "payload": payload,
        }
    except Exception as exc:
        return {
            "registered": False,
            "reason": "phase5v_registration_read_error",
            "error": str(exc),
            "payload": {},
        }


def build_rithmic_setup_verdict(
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
        "trade_count": None,
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
    result["trade_count"] = (
        int(trade_count)
        if trade_count is not None
        else None
    )

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
        trade_count is not None
        and trade_count < RITHMIC_SETUP_MIN_TRADES
    ):
        result.update(
            {
                "verdict": "NEUTRAL",
                "alignment": "NEUTRAL_LOW_RITHMIC_TRADE_SAMPLE",
                "reason": "rithmic_trade_sample_below_minimum",
            }
        )
        return result

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


def _format_signed(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "N/A"
    return (
        f"+{round(numeric, 3)}"
        if numeric > 0
        else str(round(numeric, 3))
    )


def format_rithmic_setup_verdict_telegram_block(
    verdict: dict | None,
) -> str:
    """Format the compact block shown above the normal setup form."""

    verdict = verdict if isinstance(verdict, dict) else {}
    state = _safe_text(
        verdict.get("verdict"),
        "UNAVAILABLE",
    ).upper()
    direction = _safe_text(
        verdict.get("setup_direction"),
        "UNKNOWN",
    ).upper()

    if state == "SUPPORTS_SETUP":
        headline = f"🟢 RITHMIC: SUPPORTS {direction}"
    elif state == "AGAINST_SETUP":
        headline = f"🔴 RITHMIC: AGAINST {direction}"
    elif state == "NEUTRAL":
        headline = "⚪ RITHMIC: NEUTRAL / MIXED"
    else:
        headline = "⚪ RITHMIC: UNAVAILABLE / STALE"

    symbol = _safe_text(
        verdict.get("rithmic_symbol"),
        "RITHMIC",
    )
    exchange = _safe_text(
        verdict.get("exchange"),
        "COMEX",
    )
    cache_age = _safe_float(
        verdict.get("cache_age_seconds")
    )
    freshness = (
        f"Fresh {round(cache_age, 1)}s"
        if cache_age is not None
        and cache_age <= RITHMIC_SETUP_CACHE_MAX_AGE_SECONDS
        else "Freshness unavailable"
    )
    metrics = (
        verdict.get("metrics")
        if isinstance(verdict.get("metrics"), dict)
        else {}
    )
    trades = verdict.get("trade_count")
    trades_label = (
        str(trades)
        if trades is not None
        else "N/A"
    )

    lines = [headline]
    if state == "UNAVAILABLE":
        lines.append(
            "Reason: "
            + _safe_text(
                verdict.get("reason"),
                "rithmic_context_unavailable",
            )
        )

    lines.extend(
        [
            (
                f"{symbol} | {exchange} | {freshness} | "
                f"Trades {trades_label}"
            ),
            (
                f"Δ {_format_signed(metrics.get('delta'))} | "
                f"CumΔ {_format_signed(metrics.get('cumulative_delta'))} | "
                f"DOM {_format_signed(metrics.get('dom_depth_imbalance'))} | "
                f"S/A {verdict.get('support_score', 0)}/"
                f"{verdict.get('against_score', 0)}"
            ),
            "Mode: OBSERVE ONLY — NO EXECUTION AUTHORITY",
        ]
    )

    return "\n".join(lines)
'''

# -----------------------------------------------------------------------------
# 3) Wire the dedicated verdict module into live_bot and prepend it to the
#    normal SETUP_DETECTED Telegram form. The old detailed participation block
#    remains at the bottom for now; this patch only adds the compact top verdict.
# -----------------------------------------------------------------------------
live_import_anchor = '''from src.market_participation_context import (
    build_market_participation_context,
    build_market_participation_observation,
    claim_market_participation_high_impact_alert,
    format_market_participation_high_impact_alert,
    format_market_participation_telegram_block,
    log_market_participation_observation,
    record_mt5_tick,
    refresh_rithmic_participation_context,
)
'''
live_import_replacement = live_import_anchor + '''from src.rithmic_setup_verdict import (
    build_rithmic_setup_verdict,
    format_rithmic_setup_verdict_telegram_block,
)
'''
live = replace_once(
    live,
    live_import_anchor,
    live_import_replacement,
    "live_bot Rithmic verdict import",
)

helper_anchor = '''        return ""


def _notify_market_participation_high_impact_fail_open(
'''
helper_replacement = r'''        return ""


def _rithmic_setup_verdict_telegram_fail_open(
    *,
    signal,
    context,
):
    """Build display-only Rithmic setup context with zero trading authority."""

    try:
        verdict = build_rithmic_setup_verdict(
            context,
            signal,
        )
        block = format_rithmic_setup_verdict_telegram_block(
            verdict
        )
        return verdict, block
    except Exception as exc:
        logger.warning(
            "[RITHMIC SETUP VERDICT] failed open: "
            f"{exc}"
        )
        verdict = {
            "verdict": "UNAVAILABLE",
            "alignment": "NOT_AVAILABLE_FORMATTER_ERROR",
            "setup_direction": str(signal or "UNKNOWN").upper(),
            "supports_setup": False,
            "against_setup": False,
            "support_score": 0,
            "against_score": 0,
            "evidence": [],
            "reason": "rithmic_setup_verdict_error",
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "safe_for_execution": False,
            "execution_allowed": False,
        }
        return (
            verdict,
            "⚪ RITHMIC: UNAVAILABLE / ERROR\n"
            "Mode: OBSERVE ONLY — NO EXECUTION AUTHORITY",
        )


def _notify_market_participation_high_impact_fail_open(
'''
live = replace_once(
    live,
    helper_anchor,
    helper_replacement,
    "live_bot Rithmic verdict fail-open helper",
)

normal_anchor = '''                detected_participation_block = (
                    _market_participation_telegram_block_fail_open(
                        signal=signal,
                        context=(
                            setup_participation_context
                        ),
                    )
                )

                if detected_entry_tp_block:
'''
normal_replacement = '''                detected_participation_block = (
                    _market_participation_telegram_block_fail_open(
                        signal=signal,
                        context=(
                            setup_participation_context
                        ),
                    )
                )

                (
                    detected_rithmic_verdict,
                    detected_rithmic_verdict_block,
                ) = (
                    _rithmic_setup_verdict_telegram_fail_open(
                        signal=signal,
                        context=(
                            setup_participation_context
                        ),
                    )
                )

                selected_signal_data[
                    "rithmic_setup_verdict"
                ] = detected_rithmic_verdict

                if detected_rithmic_verdict_block:
                    detected_message = (
                        detected_rithmic_verdict_block
                        + "\\n--------------------------------\\n\\n"
                        + detected_message
                    )

                if detected_entry_tp_block:
'''
live = replace_once(
    live,
    normal_anchor,
    normal_replacement,
    "normal SETUP_DETECTED top verdict placement",
)

log_extra_anchor = '''                    extra={
                        "protected_reentry": selected_signal_data.get("protected_reentry"),
                    },
'''
require_count(live, log_extra_anchor, 1, "SETUP_DETECTED log extra")
log_extra_replacement = '''                    extra={
                        "protected_reentry": selected_signal_data.get("protected_reentry"),
                        "rithmic_setup_verdict": (
                            selected_signal_data.get(
                                "rithmic_setup_verdict"
                            )
                        ),
                    },
'''
live = live.replace(
    log_extra_anchor,
    log_extra_replacement,
    1,
)

outcome_extra_anchor = '''                        "source": "setup_detected_raw",
                        "news_context": news_context,
'''
outcome_extra_replacement = '''                        "source": "setup_detected_raw",
                        "rithmic_setup_verdict": (
                            selected_signal_data.get(
                                "rithmic_setup_verdict"
                            )
                        ),
                        "news_context": news_context,
'''
live = replace_once(
    live,
    outcome_extra_anchor,
    outcome_extra_replacement,
    "setup outcome Rithmic verdict persistence",
)

# -----------------------------------------------------------------------------
# 4) Make Phase 5P use the exact same scorer so manual watcher and live setup
#    form cannot disagree because of duplicated scoring logic.
# -----------------------------------------------------------------------------
phase5p_import_anchor = '''from src.order_flow_providers.rithmic_contract_identity import (
    require_rithmic_symbol as _require_rithmic_symbol,
    require_rithmic_symbols as _require_rithmic_symbols,
    resolve_rithmic_symbol as _resolve_rithmic_symbol,
    safe_symbol_for_file as _rithmic_safe_symbol_for_file,
)
'''
phase5p_import_replacement = phase5p_import_anchor + '''from src.rithmic_setup_verdict import (
    score_rithmic_setup_alignment_for_direction,
)
'''
phase5p = replace_once(
    phase5p,
    phase5p_import_anchor,
    phase5p_import_replacement,
    "Phase5P shared verdict scorer import",
)

score_start_anchor = "def score_alignment_for_direction("
score_end_anchor = "\n\ndef compute_rithmic_directional_alignment("
require_count(phase5p, score_start_anchor, 1, "Phase5P score function start")
require_count(phase5p, score_end_anchor, 1, "Phase5P score function end")
score_start = phase5p.index(score_start_anchor)
score_end = phase5p.index(score_end_anchor, score_start)
phase5p = (
    phase5p[:score_start]
    + '''def score_alignment_for_direction(
    direction: str,
    metrics: dict[str, Any],
) -> tuple[int, int, list[str]]:
    return score_rithmic_setup_alignment_for_direction(
        direction,
        metrics,
    )
'''
    + phase5p[score_end:]
)

# -----------------------------------------------------------------------------
# 5) Focused regression test.
# -----------------------------------------------------------------------------
test_script = r'''from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import rithmic_setup_verdict as verdict_module
from scripts.run_phase5p_event_driven_rithmic_watcher import (
    score_alignment_for_direction as phase5p_score_alignment,
)


def _registration_payload(symbol: str = "GCZ6") -> dict:
    return {
        "provider": "RITHMIC_R_PROTOCOL",
        "provider_role": "REAL_ORDER_FLOW_SOURCE",
        "source_market": "COMEX",
        "symbol": symbol,
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


def _context(
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
            "metrics": {
                "trade_count": trades,
                "delta": delta,
                "cumulative_delta": cumulative_delta,
                "dom_depth_imbalance": dom_imbalance,
                "dom_bid_depth": bid_depth,
                "dom_ask_depth": ask_depth,
            },
        },
    }


def main() -> None:
    original_registration_path = (
        verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH
    )

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            registration_path = Path(tmp_dir) / "phase5v.json"
            registration_path.write_text(
                json.dumps(
                    _registration_payload(),
                    indent=2,
                ),
                encoding="utf-8",
            )
            verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = (
                registration_path
            )

            current_like = _context(
                delta=3,
                cumulative_delta=3,
                dom_imbalance=-0.120395,
                bid_depth=2495,
                ask_depth=3178,
            )
            support_buy = verdict_module.build_rithmic_setup_verdict(
                current_like,
                "BUY",
            )
            assert support_buy["verdict"] == "SUPPORTS_SETUP"
            assert support_buy["alignment"] == "SUPPORTS_BUY"
            assert support_buy["support_score"] == 2
            assert support_buy["against_score"] == 1
            assert support_buy["decision_impact"] == "NONE"
            assert support_buy["can_influence_decision"] is False
            assert support_buy["safe_for_execution"] is False
            assert support_buy["execution_allowed"] is False

            support_block = (
                verdict_module.format_rithmic_setup_verdict_telegram_block(
                    support_buy
                )
            )
            assert support_block.startswith(
                "🟢 RITHMIC: SUPPORTS BUY"
            )
            assert "GCZ6 | COMEX" in support_block
            assert "Mode: OBSERVE ONLY" in support_block

            against_buy = verdict_module.build_rithmic_setup_verdict(
                _context(
                    delta=-7,
                    cumulative_delta=-9,
                    dom_imbalance=-0.22,
                    bid_depth=2000,
                    ask_depth=3300,
                ),
                "BUY",
            )
            assert against_buy["verdict"] == "AGAINST_SETUP"
            assert against_buy["alignment"] == "AGAINST_BUY"

            support_sell = verdict_module.build_rithmic_setup_verdict(
                _context(
                    delta=-7,
                    cumulative_delta=-9,
                    dom_imbalance=-0.22,
                    bid_depth=2000,
                    ask_depth=3300,
                ),
                "SELL",
            )
            assert support_sell["verdict"] == "SUPPORTS_SETUP"
            assert support_sell["alignment"] == "SUPPORTS_SELL"

            neutral = verdict_module.build_rithmic_setup_verdict(
                _context(
                    delta=0,
                    cumulative_delta=0,
                    dom_imbalance=0,
                    bid_depth=2500,
                    ask_depth=2500,
                ),
                "BUY",
            )
            assert neutral["verdict"] == "NEUTRAL"

            low_sample = verdict_module.build_rithmic_setup_verdict(
                _context(
                    delta=20,
                    cumulative_delta=30,
                    dom_imbalance=0.3,
                    bid_depth=3500,
                    ask_depth=1500,
                    trades=2,
                ),
                "BUY",
            )
            assert low_sample["verdict"] == "NEUTRAL"
            assert (
                low_sample["alignment"]
                == "NEUTRAL_LOW_RITHMIC_TRADE_SAMPLE"
            )

            stale = verdict_module.build_rithmic_setup_verdict(
                _context(
                    delta=20,
                    cumulative_delta=30,
                    dom_imbalance=0.3,
                    bid_depth=3500,
                    ask_depth=1500,
                    cache_age_seconds=9.0,
                ),
                "BUY",
            )
            assert stale["verdict"] == "UNAVAILABLE"
            assert stale["reason"] == "rithmic_cache_stale"

            mismatch = verdict_module.build_rithmic_setup_verdict(
                _context(
                    delta=20,
                    cumulative_delta=30,
                    dom_imbalance=0.3,
                    bid_depth=3500,
                    ask_depth=1500,
                    symbol="GCG7",
                ),
                "BUY",
            )
            assert mismatch["verdict"] == "UNAVAILABLE"
            assert mismatch["reason"] == "phase5v_symbol_mismatch"

            metrics = current_like["rithmic"]["metrics"]
            assert phase5p_score_alignment(
                "BUY",
                metrics,
            ) == verdict_module.score_rithmic_setup_alignment_for_direction(
                "BUY",
                metrics,
            )

            registration_path.unlink()
            missing_registration = (
                verdict_module.build_rithmic_setup_verdict(
                    current_like,
                    "BUY",
                )
            )
            assert missing_registration["verdict"] == "UNAVAILABLE"
            assert (
                missing_registration["reason"]
                == "phase5v_registration_missing"
            )
    finally:
        verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = (
            original_registration_path
        )

    live_text = (ROOT / "src" / "live_bot.py").read_text(
        encoding="utf-8"
    )
    setup_anchor = (
        "detected_message = (\n"
        "                    build_trade_message("
    )
    setup_start = live_text.index(setup_anchor)
    setup_end = live_text.index(
        "                send_telegram_message_async(\n"
        "                    detected_message",
        setup_start,
    )
    setup_region = live_text[setup_start:setup_end]

    assert "detected_rithmic_verdict_block" in setup_region
    assert "_rithmic_setup_verdict_telegram_fail_open(" in setup_region
    assert (
        'selected_signal_data[\n'
        '                    "rithmic_setup_verdict"\n'
        '                ] = detected_rithmic_verdict'
        in setup_region
    )
    assert (
        'detected_rithmic_verdict_block\n'
        '                        + "\\n--------------------------------\\n\\n"\n'
        '                        + detected_message'
        in setup_region
    )

    for path in [
        ROOT / "src" / "live_bot.py",
        ROOT / "src" / "market_participation_context.py",
        ROOT / "src" / "rithmic_setup_verdict.py",
        ROOT / "scripts" / "run_phase5p_event_driven_rithmic_watcher.py",
    ]:
        compile(
            path.read_text(encoding="utf-8"),
            str(path),
            "exec",
        )

    print(
        "[PASS] Rithmic setup verdict top-of-form integration: "
        "support/against/neutral/stale/low-sample/rollover guards, "
        "Phase5P scoring parity, top placement, and compile checks passed."
    )


if __name__ == "__main__":
    main()
'''

# Compile all future contents before touching the working tree.
compile_text(PARTICIPATION, participation)
compile_text(LIVE_BOT, live)
compile_text(PHASE5P, phase5p)
compile_text(VERDICT_MODULE, verdict_module)
compile_text(TEST_SCRIPT, test_script)
print("[OK] All patched/new Python sources compile in-memory")

# Back up only files that already exist.
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_root = ROOT / "local_backups" / f"rithmic_setup_verdict_top_form_v1_{stamp}"
for path in [
    LIVE_BOT,
    PARTICIPATION,
    PHASE5P,
    VERDICT_MODULE,
    TEST_SCRIPT,
]:
    backup_file(path, backup_root)
print(f"[BACKUP] {backup_root}")

# Atomic writes.
atomic_write(PARTICIPATION, participation)
print(f"[UPDATED] {PARTICIPATION.relative_to(ROOT)}")
atomic_write(LIVE_BOT, live)
print(f"[UPDATED] {LIVE_BOT.relative_to(ROOT)}")
atomic_write(PHASE5P, phase5p)
print(f"[UPDATED] {PHASE5P.relative_to(ROOT)}")
atomic_write(VERDICT_MODULE, verdict_module)
print(f"[CREATED] {VERDICT_MODULE.relative_to(ROOT)}")
atomic_write(TEST_SCRIPT, test_script)
print(f"[CREATED] {TEST_SCRIPT.relative_to(ROOT)}")

# Final compile from disk.
for path in [
    PARTICIPATION,
    LIVE_BOT,
    PHASE5P,
    VERDICT_MODULE,
    TEST_SCRIPT,
]:
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        stop(
            f"Post-write compile failed for {path}: "
            f"{proc.stderr.strip()}"
        )
print("[OK] Post-write py_compile passed")

print("[DONE] Rithmic setup verdict top-of-form patch applied.")
print("[SAFETY] decision_impact remains NONE; Rithmic cannot block/approve/execute trades.")
print("[NO COMMIT] Review and run the focused regression before any commit.")
print("[NO BOT RESTART] Do not restart the live bot yet.")
