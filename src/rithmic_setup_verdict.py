from __future__ import annotations

import json
from pathlib import Path
from typing import Any


RITHMIC_SETUP_MIN_TRADES = 5
RITHMIC_SETUP_DOM_IMBALANCE_THRESHOLD = 0.15
RITHMIC_SETUP_MIN_DECISIVE_SCORE = 2
RITHMIC_SETUP_CACHE_MAX_AGE_SECONDS = 5.0
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
        "evidence_model": None,
        "evidence_bridge_age_seconds": None,
        "evidence_family_coverage": "0/6",
        "evidence_family_available_count": 0,
        "evidence_family_unavailable_count": 6,
        "evidence_family_states": {},
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

    # --------------------------------------------------------
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
