from __future__ import annotations

from pathlib import Path
from typing import Any
import json


MODEL = "RITHMIC_TRADE_PLAN_ADVISORY_V1"
MODE = "SHADOW_ONLY"

MIN_DECISIVE_COVERAGE = 4
TOTAL_EVIDENCE_FAMILIES = 6

_USABLE_FEED_STATES = {
    "HEALTHY",
    "OK",
    "USABLE",
    "PRODUCTION_ELIGIBLE",
}


def _safe_float(
    value: Any,
) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if result <= 0:
        return None

    return result


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _direction(
    value: Any,
) -> str | None:
    normalized = str(
        value or ""
    ).strip().upper()

    if normalized in {
        "BUY",
        "SELL",
    }:
        return normalized

    return None


def _normalize_tp_ladder(
    value: Any,
) -> list[dict[str, Any]]:
    if not isinstance(
        value,
        list,
    ):
        return []

    result: list[dict[str, Any]] = []

    for row in value:
        if not isinstance(
            row,
            dict,
        ):
            continue

        price = _safe_float(
            row.get("price")
            or row.get("take_profit")
        )

        if price is None:
            continue

        normalized = {
            "price": price,
        }

        if row.get("name") is not None:
            normalized["name"] = row.get(
                "name"
            )

        if row.get("rr") is not None:
            normalized["rr"] = row.get(
                "rr"
            )

        result.append(
            normalized
        )

    return result


def _normalize_bot_plan(
    *,
    signal: str,
    trade_plan: Any,
) -> tuple[
    dict[str, Any] | None,
    str | None,
]:
    if not isinstance(
        trade_plan,
        dict,
    ):
        return (
            None,
            "bot_trade_plan_missing",
        )

    entry = _safe_float(
        trade_plan.get(
            "entry_price"
        )
    )

    sl = _safe_float(
        trade_plan.get(
            "stop_loss"
        )
    )

    tp = _safe_float(
        trade_plan.get(
            "take_profit"
        )
    )

    if (
        entry is None
        or sl is None
        or tp is None
    ):
        return (
            None,
            "bot_trade_plan_incomplete",
        )

    if signal == "BUY":
        geometry_valid = (
            sl < entry < tp
        )

    else:
        geometry_valid = (
            tp < entry < sl
        )

    if not geometry_valid:
        return (
            None,
            "bot_trade_plan_invalid_geometry",
        )

    return (
        {
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "tp_ladder": (
                _normalize_tp_ladder(
                    trade_plan.get(
                        "tp_ladder"
                    )
                )
            ),
        },
        None,
    )


def _parse_coverage(
    value: Any,
) -> tuple[int, int]:
    if isinstance(
        value,
        str,
    ):
        text = value.strip()

        if "/" in text:
            numerator, denominator = (
                text.split(
                    "/",
                    1,
                )
            )

            return (
                _safe_int(
                    numerator.strip()
                ),
                _safe_int(
                    denominator.strip(),
                    TOTAL_EVIDENCE_FAMILIES,
                ),
            )

        return (
            _safe_int(text),
            TOTAL_EVIDENCE_FAMILIES,
        )

    if isinstance(
        value,
        (
            int,
            float,
        ),
    ):
        return (
            int(value),
            TOTAL_EVIDENCE_FAMILIES,
        )

    return (
        0,
        TOTAL_EVIDENCE_FAMILIES,
    )


def _verdict_alignment(
    verdict: dict[str, Any],
) -> str:
    raw = (
        verdict.get("alignment")
        or verdict.get("verdict")
        or verdict.get("state")
        or "UNAVAILABLE"
    )

    return str(
        raw
    ).strip().upper()


def _alignment_unavailable(
    alignment: str,
) -> bool:
    return (
        "UNAVAILABLE" in alignment
        or "NOT_AVAILABLE" in alignment
        or "STALE" in alignment
    )


def _normalize_basis_summary(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(
        value,
        dict,
    ):
        return {
            "present": False,
            "basis_ready_observe_only": False,
            "statistically_ready": False,
            "numeric_translation_allowed": False,
            "reason": "basis_summary_missing",
        }

    nested = value.get(
        "summary"
    )

    if isinstance(
        nested,
        dict,
    ):
        source = nested

    else:
        source = value

    ready = bool(
        source.get(
            "basis_ready_observe_only"
        )
    )

    valid_pair_count = _safe_int(
        source.get(
            "valid_pair_count"
        )
    )

    valid_pair_rate_raw = (
        source.get(
            "valid_pair_rate"
        )
    )

    try:
        valid_pair_rate = float(
            valid_pair_rate_raw
        )
    except (TypeError, ValueError):
        valid_pair_rate = None

    basis_std_raw = source.get(
        "basis_std"
    )

    try:
        basis_std = float(
            basis_std_raw
        )
    except (TypeError, ValueError):
        basis_std = None

    avg_basis_raw = source.get(
        "avg_basis"
    )

    try:
        avg_basis = float(
            avg_basis_raw
        )
    except (TypeError, ValueError):
        avg_basis = None

    jump_raw = source.get(
        "max_abs_basis_jump"
    )

    try:
        max_abs_basis_jump = float(
            jump_raw
        )
    except (TypeError, ValueError):
        max_abs_basis_jump = None

    statistically_ready = bool(
        ready
        and valid_pair_count >= 30
        and (
            valid_pair_rate is None
            or valid_pair_rate >= 0.90
        )
        and (
            basis_std is not None
            and basis_std <= 2.0
        )
    )

    # Phase 1 deliberately refuses numeric translation.
    #
    # basis_ready_observe_only proves statistical quality, but this
    # advisory layer does not yet have a setup-time freshness contract
    # plus independently verified translated Rithmic price anchors.
    numeric_translation_allowed = False

    if statistically_ready:
        reason = (
            "statistically_ready_but_numeric_translation_"
            "withheld_pending_freshness_and_price_anchor_contract"
        )
    else:
        reason = (
            str(
                source.get("reason")
                or "basis_not_ready"
            )
        )

    return {
        "present": True,
        "sample_count": _safe_int(
            source.get(
                "sample_count"
            )
        ),
        "valid_pair_count": (
            valid_pair_count
        ),
        "valid_pair_rate": (
            valid_pair_rate
        ),
        "avg_basis": avg_basis,
        "basis_std": basis_std,
        "max_abs_basis_jump": (
            max_abs_basis_jump
        ),
        "basis_ready_observe_only": (
            ready
        ),
        "statistically_ready": (
            statistically_ready
        ),
        "numeric_translation_allowed": (
            numeric_translation_allowed
        ),
        "reason": reason,
    }


def _qualitative_plan(
    *,
    alignment: str,
    coverage_count: int,
) -> dict[str, str]:
    if (
        coverage_count
        < MIN_DECISIVE_COVERAGE
    ):
        return {
            "posture": (
                "INSUFFICIENT_COVERAGE"
            ),
            "entry_context": (
                "KEEP_ORIGINAL_NO_DIRECTIONAL_ADVISORY"
            ),
            "sl_context": (
                "KEEP_ORIGINAL_NO_DIRECTIONAL_ADVISORY"
            ),
            "tp_context": (
                "KEEP_ORIGINAL_NO_DIRECTIONAL_ADVISORY"
            ),
        }

    if alignment == "SUPPORTS_SETUP":
        return {
            "posture": "SETUP_SUPPORTED",
            "entry_context": (
                "KEEP_ORIGINAL_OR_BETTER_ENTRY_ONLY"
            ),
            "sl_context": (
                "ORIGINAL_SL_CONTEXT_SUPPORTED"
            ),
            "tp_context": (
                "EXTENSION_PRESSURE_SUPPORTED_"
                "BUT_KEEP_ORIGINAL_TP"
            ),
        }

    if alignment == "AGAINST_SETUP":
        return {
            "posture": "SETUP_OPPOSED",
            "entry_context": (
                "AVOID_CHASING_OR_WAIT_FOR_BETTER_ENTRY"
            ),
            "sl_context": (
                "ELEVATED_STOP_RISK_CONTEXT"
            ),
            "tp_context": (
                "CLOSER_TARGET_PRESSURE_CONTEXT"
            ),
        }

    return {
        "posture": "MIXED_OR_NEUTRAL",
        "entry_context": (
            "KEEP_ORIGINAL"
        ),
        "sl_context": (
            "KEEP_ORIGINAL"
        ),
        "tp_context": (
            "KEEP_ORIGINAL"
        ),
    }


def _base_result(
    signal: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": "V1",
        "model": MODEL,
        "mode": MODE,
        "status": "UNAVAILABLE",
        "signal": signal,
        "reason": None,
        "bot_plan": None,
        "rithmic_plan": {
            "numeric_plan_available": False,
            "suggested_entry": None,
            "suggested_sl": None,
            "suggested_tp": None,
            "suggested_tp_ladder": [],
            "posture": "UNAVAILABLE",
            "entry_context": (
                "NO_GUIDANCE"
            ),
            "sl_context": (
                "NO_GUIDANCE"
            ),
            "tp_context": (
                "NO_GUIDANCE"
            ),
        },
        "evidence": {
            "alignment": "UNAVAILABLE",
            "support_count": 0,
            "against_count": 0,
            "coverage_count": 0,
            "coverage_total": (
                TOTAL_EVIDENCE_FAMILIES
            ),
            "coverage": (
                f"0/{TOTAL_EVIDENCE_FAMILIES}"
            ),
            "regime": "UNAVAILABLE",
            "feed_integrity": "UNKNOWN",
        },
        "basis": (
            _normalize_basis_summary(
                None
            )
        ),
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
        "trade_action": "NO_AUTO_TRADE",
        "can_modify_entry": False,
        "can_modify_sl": False,
        "can_modify_tp": False,
        "can_modify_size": False,
    }



def _normalize_numeric_shadow_plan(
    *,
    signal: str,
    numeric_shadow_plan: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Accept only an already-validated Phase-3B SHADOW plan.

    This function does not calculate or invent prices.
    """

    if not isinstance(
        numeric_shadow_plan,
        dict,
    ):
        return None, "numeric_shadow_plan_missing"

    if (
        str(
            numeric_shadow_plan.get("mode")
            or ""
        ).strip().upper()
        != "SHADOW_ONLY"
    ):
        return (
            None,
            "numeric_shadow_plan_mode_invalid",
        )

    if (
        str(
            numeric_shadow_plan.get("status")
            or ""
        ).strip().upper()
        != "NUMERIC_SHADOW_PLAN"
    ):
        return (
            None,
            "numeric_shadow_plan_status_invalid",
        )

    if not bool(
        numeric_shadow_plan.get(
            "numeric_plan_available"
        )
    ):
        return (
            None,
            "numeric_shadow_plan_not_available",
        )

    authority = {
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
        "trade_action": "NO_AUTO_TRADE",
        "can_modify_entry": False,
        "can_modify_sl": False,
        "can_modify_tp": False,
        "can_modify_size": False,
    }

    for key, expected in authority.items():
        if (
            numeric_shadow_plan.get(key)
            != expected
        ):
            return (
                None,
                "numeric_shadow_plan_authority_invalid",
            )

    plan_signal = _direction(
        numeric_shadow_plan.get("signal")
    )

    if plan_signal != signal:
        return (
            None,
            "numeric_shadow_plan_signal_mismatch",
        )

    entry = _safe_float(
        numeric_shadow_plan.get(
            "suggested_entry"
        )
    )

    sl = _safe_float(
        numeric_shadow_plan.get(
            "suggested_sl"
        )
    )

    if (
        entry is None
        or sl is None
    ):
        return (
            None,
            "numeric_shadow_plan_core_price_missing",
        )

    raw_ladder = numeric_shadow_plan.get(
        "suggested_tp_ladder"
    )

    if not isinstance(
        raw_ladder,
        list,
    ):
        return (
            None,
            "numeric_shadow_plan_tp_ladder_missing",
        )

    ladder = []

    for row in raw_ladder:
        if not isinstance(
            row,
            dict,
        ):
            continue

        price = _safe_float(
            row.get("price")
        )

        if price is None:
            continue

        ladder.append(
            {
                "label": (
                    str(
                        row.get("label")
                        or ""
                    ).strip()
                    or None
                ),
                "price": price,
                "rr": row.get("rr"),
                "anchor_id": (
                    str(
                        row.get(
                            "anchor_id"
                        )
                        or ""
                    ).strip()
                    or None
                ),
            }
        )

    if len(ladder) < 2:
        return (
            None,
            "numeric_shadow_plan_two_targets_required",
        )

    tp1 = ladder[0]["price"]
    tp2 = ladder[1]["price"]

    if signal == "BUY":
        geometry_ok = (
            sl
            < entry
            < tp1
            < tp2
        )
    else:
        geometry_ok = (
            tp2
            < tp1
            < entry
            < sl
        )

    if not geometry_ok:
        return (
            None,
            "numeric_shadow_plan_geometry_invalid",
        )

    suggested_tp = _safe_float(
        numeric_shadow_plan.get(
            "suggested_tp"
        )
    )

    if (
        suggested_tp is not None
        and suggested_tp != tp1
    ):
        return (
            None,
            "numeric_shadow_plan_tp1_mismatch",
        )

    entry_anchor = (
        numeric_shadow_plan.get(
            "entry_anchor"
        )
    )

    sl_anchor = (
        numeric_shadow_plan.get(
            "sl_anchor"
        )
    )

    tp_anchors = (
        numeric_shadow_plan.get(
            "tp_anchors"
        )
    )

    if not isinstance(
        entry_anchor,
        dict,
    ):
        entry_anchor = {}

    if not isinstance(
        sl_anchor,
        dict,
    ):
        sl_anchor = {}

    if not isinstance(
        tp_anchors,
        list,
    ):
        tp_anchors = []

    return (
        {
            "numeric_translation_allowed": True,
            "numeric_plan_available": True,
            "suggested_entry": entry,
            "suggested_sl": sl,
            "suggested_tp": tp1,
            "suggested_tp_ladder": ladder[:2],
            "entry_anchor": {
                "anchor_id": (
                    entry_anchor.get(
                        "anchor_id"
                    )
                ),
                "family": (
                    entry_anchor.get(
                        "family"
                    )
                ),
                "price": entry,
            },
            "sl_anchor": {
                "anchor_id": (
                    sl_anchor.get(
                        "anchor_id"
                    )
                ),
                "family": (
                    sl_anchor.get(
                        "family"
                    )
                ),
                "price": sl,
            },
            "tp_anchors": tp_anchors[:2],
            "rr_tp1": (
                numeric_shadow_plan.get(
                    "rr_tp1"
                )
            ),
            "rr_tp2": (
                numeric_shadow_plan.get(
                    "rr_tp2"
                )
            ),
        },
        None,
    )


def build_rithmic_trade_plan_advisory(
    *,
    signal: Any,
    bot_trade_plan: Any,
    rithmic_verdict: Any,
    basis_summary: Any = None,
    numeric_shadow_enabled: bool = False,
    numeric_shadow_plan: Any = None,
) -> dict[str, Any]:
    """
    Build the Phase-1 Rithmic trade-plan advisory.

    This function is intentionally pure and shadow-only.

    It never mutates the authoritative bot trade plan and never
    produces executable or decision-grade instructions.

    Numeric XAUUSD alternatives are deliberately withheld in V1
    until the project has a separate, freshness-aware GC->XAUUSD
    translation contract with verified Rithmic price anchors.
    """

    normalized_signal = _direction(
        signal
    )

    result = _base_result(
        normalized_signal
    )

    result["numeric_shadow"] = {
        "enabled": bool(
            numeric_shadow_enabled
        ),
        "attached": False,
        "reason": (
            "disabled_by_default"
            if not numeric_shadow_enabled
            else "not_evaluated"
        ),
    }

    result["basis"] = (
        _normalize_basis_summary(
            basis_summary
        )
    )

    if normalized_signal is None:
        result["reason"] = (
            "invalid_signal"
        )
        return result

    bot_plan, plan_error = (
        _normalize_bot_plan(
            signal=normalized_signal,
            trade_plan=bot_trade_plan,
        )
    )

    if bot_plan is None:
        result["reason"] = (
            plan_error
            or "bot_trade_plan_unavailable"
        )
        return result

    result["bot_plan"] = bot_plan

    if not isinstance(
        rithmic_verdict,
        dict,
    ):
        result["reason"] = (
            "rithmic_verdict_missing"
        )
        return result

    alignment = (
        _verdict_alignment(
            rithmic_verdict
        )
    )

    feed = str(
        rithmic_verdict.get(
            "evidence_feed_status"
        )
        or "UNKNOWN"
    ).strip().upper()

    coverage_count, coverage_total = (
        _parse_coverage(
            rithmic_verdict.get(
                "evidence_family_coverage"
            )
        )
    )

    support_count = _safe_int(
        rithmic_verdict.get(
            "support_score"
        )
    )

    against_count = _safe_int(
        rithmic_verdict.get(
            "against_score"
        )
    )

    regime = str(
        rithmic_verdict.get(
            "evidence_order_flow_regime"
        )
        or "UNAVAILABLE"
    ).strip().upper()

    result["evidence"] = {
        "alignment": alignment,
        "support_count": (
            support_count
        ),
        "against_count": (
            against_count
        ),
        "coverage_count": (
            coverage_count
        ),
        "coverage_total": (
            coverage_total
        ),
        "coverage": (
            f"{coverage_count}/{coverage_total}"
        ),
        "regime": regime,
        "feed_integrity": feed,
    }

    if _alignment_unavailable(
        alignment
    ):
        result["reason"] = (
            "rithmic_verdict_unavailable"
        )
        return result

    if feed not in _USABLE_FEED_STATES:
        result["reason"] = (
            "rithmic_feed_not_usable"
        )
        return result

    qualitative = _qualitative_plan(
        alignment=alignment,
        coverage_count=coverage_count,
    )

    result["rithmic_plan"].update(
        qualitative
    )

    result["status"] = (
        "QUALITATIVE_ONLY"
    )

    if (
        coverage_count
        < MIN_DECISIVE_COVERAGE
    ):
        result["reason"] = (
            "insufficient_independent_family_coverage"
        )

    elif alignment == "SUPPORTS_SETUP":
        result["reason"] = (
            "v2_independent_families_support_setup"
        )

    elif alignment == "AGAINST_SETUP":
        result["reason"] = (
            "v2_independent_families_oppose_setup"
        )

    else:
        result["reason"] = (
            "v2_independent_families_mixed_or_neutral"
        )

    # Default remains qualitative-only.
    #
    # Phase 3C may attach an already-validated Phase-3B
    # numeric SHADOW plan only when explicitly enabled.
    result["rithmic_plan"][
        "numeric_plan_available"
    ] = False

    result["rithmic_plan"][
        "suggested_entry"
    ] = None

    result["rithmic_plan"][
        "suggested_sl"
    ] = None

    result["rithmic_plan"][
        "suggested_tp"
    ] = None

    result["rithmic_plan"][
        "suggested_tp_ladder"
    ] = []

    if not bool(
        numeric_shadow_enabled
    ):
        return result

    if (
        alignment
        != "SUPPORTS_SETUP"
    ):
        result["numeric_shadow"][
            "reason"
        ] = (
            "rithmic_alignment_not_supportive"
        )
        return result

    if (
        coverage_count
        < MIN_DECISIVE_COVERAGE
    ):
        result["numeric_shadow"][
            "reason"
        ] = (
            "insufficient_independent_family_coverage"
        )
        return result

    normalized_numeric, numeric_error = (
        _normalize_numeric_shadow_plan(
            signal=normalized_signal,
            numeric_shadow_plan=(
                numeric_shadow_plan
            ),
        )
    )

    if normalized_numeric is None:
        result["numeric_shadow"][
            "reason"
        ] = (
            numeric_error
            or "numeric_shadow_plan_invalid"
        )
        return result

    result["rithmic_plan"].update(
        normalized_numeric
    )

    result["numeric_shadow"] = {
        "enabled": True,
        "attached": True,
        "reason": (
            "validated_numeric_shadow_plan_attached"
        ),
    }

    result["status"] = (
        "NUMERIC_SHADOW_PLAN"
    )

    result["reason"] = (
        "v2_supportive_numeric_shadow_plan_attached"
    )

    return result

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_RITHMIC_BASIS_SUMMARY_PATH = (
    _PROJECT_ROOT
    / "data"
    / "order_flow"
    / "rithmic"
    / "phase5ac_xauusd_rithmic_basis_calibration.json"
)


def load_rithmic_basis_summary(
    path: str | Path | None = None,
) -> dict[str, Any] | None:
    """
    Load Phase 5AC basis statistics fail-open.

    Research context only.
    """

    source_path = (
        Path(path)
        if path is not None
        else DEFAULT_RITHMIC_BASIS_SUMMARY_PATH
    )

    try:
        payload = json.loads(
            source_path.read_text(
                encoding="utf-8-sig",
            )
        )

    except Exception:
        return None

    if not isinstance(
        payload,
        dict,
    ):
        return None

    return payload


def _display_token(
    value: Any,
    default: str = "N/A",
) -> str:
    text = str(
        value
        if value is not None
        else default
    ).strip()

    if not text:
        text = default

    return text.replace(
        "_",
        " ",
    )


def format_rithmic_trade_plan_advisory_telegram_block(
    advisory: dict[str, Any] | None,
) -> str:
    """
    Format shadow-only Rithmic trade-plan context.
    """

    if not isinstance(
        advisory,
        dict,
    ):
        return ""

    status = str(
        advisory.get("status")
        or "UNAVAILABLE"
    ).strip().upper()

    reason = str(
        advisory.get("reason")
        or "rithmic_trade_plan_advisory_unavailable"
    ).strip()

    plan = advisory.get(
        "rithmic_plan"
    )

    if not isinstance(
        plan,
        dict,
    ):
        plan = {}

    basis = advisory.get(
        "basis"
    )

    if not isinstance(
        basis,
        dict,
    ):
        basis = {}

    numeric_shadow = advisory.get(
        "numeric_shadow"
    )

    if not isinstance(
        numeric_shadow,
        dict,
    ):
        numeric_shadow = {}

    # IMPORTANT:
    # Keep legacy Phase-2 display text exactly unchanged.
    lines = [
        "RITHMIC PLAN ? SHADOW ADVISORY",
        (
            "Status: "
            + _display_token(
                status
            )
        ),
    ]

    if status in {
        "QUALITATIVE_ONLY",
        "NUMERIC_SHADOW_PLAN",
    }:
        lines.extend(
            [
                (
                    "Posture: "
                    + _display_token(
                        plan.get(
                            "posture"
                        )
                    )
                ),
                (
                    "Entry Context: "
                    + _display_token(
                        plan.get(
                            "entry_context"
                        )
                    )
                ),
                (
                    "SL Context: "
                    + _display_token(
                        plan.get(
                            "sl_context"
                        )
                    )
                ),
                (
                    "TP Context: "
                    + _display_token(
                        plan.get(
                            "tp_context"
                        )
                    )
                ),
            ]
        )

    else:
        lines.append(
            "Reason: "
            + _display_token(
                reason
            )
        )

    numeric_ready = bool(
        status
        == "NUMERIC_SHADOW_PLAN"
        and numeric_shadow.get(
            "attached"
        )
        is True
        and plan.get(
            "numeric_plan_available"
        )
        is True
    )

    entry = None
    sl = None
    ladder = None

    if numeric_ready:
        entry = _safe_float(
            plan.get(
                "suggested_entry"
            )
        )

        sl = _safe_float(
            plan.get(
                "suggested_sl"
            )
        )

        ladder = plan.get(
            "suggested_tp_ladder"
        )

        if (
            entry is None
            or sl is None
            or not isinstance(
                ladder,
                list,
            )
            or len(ladder) < 2
        ):
            numeric_ready = False

    if numeric_ready:
        tp1 = _safe_float(
            ladder[0].get("price")
            if isinstance(
                ladder[0],
                dict,
            )
            else None
        )

        tp2 = _safe_float(
            ladder[1].get("price")
            if isinstance(
                ladder[1],
                dict,
            )
            else None
        )

        if (
            tp1 is None
            or tp2 is None
        ):
            numeric_ready = False

    if numeric_ready:
        lines.append(
            "Basis: VALIDATED UPSTREAM "
            "FOR NUMERIC SHADOW"
        )

        lines.append(
            f"Suggested Entry: {entry:.2f}"
        )

        lines.append(
            f"Suggested SL: {sl:.2f}"
        )

        for index, row in enumerate(
            ladder[:2],
            1,
        ):
            price = _safe_float(
                row.get("price")
                if isinstance(
                    row,
                    dict,
                )
                else None
            )

            if price is None:
                continue

            rr = (
                row.get("rr")
                if isinstance(
                    row,
                    dict,
                )
                else None
            )

            rr_text = ""

            try:
                if rr is not None:
                    rr_text = (
                        f" | RR {float(rr):.2f}"
                    )
            except (
                TypeError,
                ValueError,
            ):
                rr_text = ""

            lines.append(
                f"Suggested TP{index}: "
                f"{price:.2f}"
                f"{rr_text}"
            )

        entry_anchor = plan.get(
            "entry_anchor"
        )

        sl_anchor = plan.get(
            "sl_anchor"
        )

        tp_anchors = plan.get(
            "tp_anchors"
        )

        if not isinstance(
            entry_anchor,
            dict,
        ):
            entry_anchor = {}

        if not isinstance(
            sl_anchor,
            dict,
        ):
            sl_anchor = {}

        if not isinstance(
            tp_anchors,
            list,
        ):
            tp_anchors = []

        lines.append(
            "Entry Anchor: "
            + _display_token(
                entry_anchor.get(
                    "anchor_id"
                )
            )
        )

        lines.append(
            "SL Anchor: "
            + _display_token(
                sl_anchor.get(
                    "anchor_id"
                )
            )
        )

        tp_anchor_ids = [
            str(
                row.get(
                    "anchor_id"
                )
                or ""
            ).strip()
            for row in tp_anchors[:2]
            if isinstance(
                row,
                dict,
            )
        ]

        tp_anchor_ids = [
            value
            for value in tp_anchor_ids
            if value
        ]

        lines.append(
            "TP Anchors: "
            + (
                " / ".join(
                    tp_anchor_ids
                )
                if tp_anchor_ids
                else "N/A"
            )
        )

    else:
        # Legacy Phase-2 text preserved exactly.
        if bool(
            basis.get(
                "statistically_ready"
            )
        ):
            lines.append(
                "Basis: STATISTICALLY READY ? "
                "LIVE NUMERIC TRANSLATION WITHHELD"
            )

        elif bool(
            basis.get(
                "present"
            )
        ):
            lines.append(
                "Basis: NOT READY FOR "
                "NUMERIC TRANSLATION"
            )

        else:
            lines.append(
                "Basis: UNAVAILABLE"
            )

        lines.append(
            "Numeric XAUUSD Entry / SL / TP: "
            "WITHHELD"
        )

    # Legacy Phase-2 authority text preserved exactly.
    lines.append(
        "Authority: SHADOW ONLY ? "
        "NO EXECUTION AUTHORITY"
    )

    return "\n".join(
        lines
    )
