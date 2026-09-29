from __future__ import annotations

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
    freshness = (
        f"Fresh {round(display_age, 1)}s"
        if display_age is not None
        and display_age <= RITHMIC_SETUP_CACHE_MAX_AGE_SECONDS
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
