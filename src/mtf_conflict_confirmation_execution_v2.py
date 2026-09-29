from __future__ import annotations

from typing import Any


def _setting(name: str, default: Any) -> Any:
    try:
        from config import settings
        return getattr(settings, name, default)
    except Exception:
        return default


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _status_counts(report: dict[str, Any]) -> dict[str, int]:
    counts = {
        "PASS": 0,
        "FAIL": 0,
        "NEUTRAL": 0,
        "DISABLED": 0,
        "ERROR": 0,
    }
    for item in report.get("results") or []:
        status = str(item.get("status") or "").upper()
        if status in counts:
            counts[status] += 1
    return counts


def evaluate_mtf_confirmation_execution_authority_v2(
    *,
    report: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    shadow_trade_plan: dict[str, Any] | None,
    shadow_rr: float | None,
    required_rr: float | None,
    execution_mode: str | None,
    original_allowed: bool,
    original_reason: str | None,
) -> dict[str, Any]:
    candidate = candidate or {}
    strategy = str(candidate.get("strategy") or "").upper()
    original_reason = str(original_reason or "")

    result = {
        "allowed": bool(original_allowed),
        "promoted": False,
        "reason": (
            "already_allowed_by_mtf_soft_execution"
            if original_allowed
            else original_reason or "unknown"
        ),
        "strategy": strategy,
        "execution_mode": execution_mode,
        "confidence": None,
        "score_delta": None,
        "status_counts": {},
        "original_allowed": bool(original_allowed),
        "original_reason": original_reason,
        "authority_scope": "MTF_CONFLICT_TRACKED_ONLY",
        "authority_version": "V2",
    }

    if original_allowed:
        return result

    if not bool(
        _setting(
            "ENABLE_MTF_CONFLICT_CONFIRMATION_EXECUTION_AUTHORITY_V2",
            False,
        )
    ):
        result["reason"] = "confirmation_execution_authority_v2_disabled"
        return result

    profiles = _setting(
        "MTF_CONFLICT_CONFIRMATION_EXECUTION_PROFILES_V2",
        {},
    )
    profile = profiles.get(strategy) if isinstance(profiles, dict) else None
    if not isinstance(profile, dict):
        result["reason"] = "strategy_not_authorized_for_confirmation_promotion"
        return result

    allowed_reason_prefixes = tuple(
        str(value)
        for value in _setting(
            "MTF_CONFLICT_CONFIRMATION_OVERRIDE_REASON_PREFIXES_V2",
            ("m5_confirmation_failed",),
        )
    )
    if not any(
        original_reason.startswith(prefix)
        for prefix in allowed_reason_prefixes
    ):
        result["reason"] = "original_rejection_not_overridable"
        return result

    if execution_mode not in {
        "COUNTER_MTF_CALCULATED",
        "COUNTER_MTF_SCALP",
    }:
        result["reason"] = "unsupported_execution_mode"
        return result

    if not isinstance(shadow_trade_plan, dict):
        result["reason"] = "shadow_trade_plan_missing"
        return result

    rr = _safe_float(shadow_rr)
    min_rr = _safe_float(required_rr)
    if rr is None or min_rr is None:
        result["reason"] = "rr_missing"
        return result
    if rr < min_rr:
        result["reason"] = f"rr_below_required {rr}/{min_rr}"
        return result

    if not isinstance(report, dict):
        result["reason"] = "confirmation_report_missing"
        return result

    confidence = _safe_float(report.get("confidence"))
    score_delta = _safe_float(report.get("score_delta"))
    counts = _status_counts(report)

    result["confidence"] = confidence
    result["score_delta"] = score_delta
    result["status_counts"] = counts

    if report.get("approved") is not True:
        result["reason"] = "confirmation_not_approved"
        return result

    if report.get("required_failed"):
        result["reason"] = "confirmation_required_module_failed"
        return result

    min_confidence = float(profile.get("min_confidence", 80.0))
    min_score_delta = float(profile.get("min_score_delta", 3.0))

    if confidence is None or confidence < min_confidence:
        result["reason"] = (
            f"confirmation_confidence_too_low "
            f"{confidence}/{min_confidence}"
        )
        return result

    if score_delta is None or score_delta < min_score_delta:
        result["reason"] = (
            f"confirmation_score_delta_too_low "
            f"{score_delta}/{min_score_delta}"
        )
        return result

    require_zero_fails = bool(
        _setting(
            "MTF_CONFLICT_CONFIRMATION_REQUIRE_ZERO_FAILS_V2",
            True,
        )
    )
    if require_zero_fails and (
        counts.get("FAIL", 0) > 0
        or counts.get("ERROR", 0) > 0
    ):
        result["reason"] = (
            "confirmation_contains_fail_or_error "
            f"fail={counts.get('FAIL', 0)} "
            f"error={counts.get('ERROR', 0)}"
        )
        return result

    result["allowed"] = True
    result["promoted"] = True
    result["reason"] = (
        "confirmation_authority_v2_promoted "
        f"strategy={strategy} "
        f"confidence={confidence} "
        f"score_delta={score_delta} "
        f"original_reason={original_reason}"
    )
    return result


def maybe_apply_mtf_confirmation_execution_authority_v2(
    *,
    candidate: dict[str, Any],
    shadow_trade_plan: dict[str, Any] | None,
    df: Any,
    tick: Any,
    session_name: str | None,
    market_condition: str | None,
    shadow_rr: float | None,
    required_rr: float | None,
    execution_mode: str | None,
    original_allowed: bool,
    original_reason: str | None,
    max_spread: float | None,
) -> dict[str, Any]:
    preflight = evaluate_mtf_confirmation_execution_authority_v2(
        report=None,
        candidate=candidate,
        shadow_trade_plan=shadow_trade_plan,
        shadow_rr=shadow_rr,
        required_rr=required_rr,
        execution_mode=execution_mode,
        original_allowed=original_allowed,
        original_reason=original_reason,
    )

    if original_allowed:
        return preflight

    if preflight.get("reason") != "confirmation_report_missing":
        return preflight

    from src.confirmation_engine import run_universal_confirmation

    report = run_universal_confirmation(
        signal_data=dict(candidate or {}),
        trade_plan=dict(shadow_trade_plan or {}),
        df=df,
        tick=tick,
        session=session_name,
        market_condition=market_condition,
        min_rr=required_rr,
        max_spread=max_spread,
        enforce_required=True,
    )

    decision = evaluate_mtf_confirmation_execution_authority_v2(
        report=report,
        candidate=candidate,
        shadow_trade_plan=shadow_trade_plan,
        shadow_rr=shadow_rr,
        required_rr=required_rr,
        execution_mode=execution_mode,
        original_allowed=original_allowed,
        original_reason=original_reason,
    )
    decision["report"] = report
    return decision
