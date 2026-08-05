from __future__ import annotations

from config import settings
from src.confirmation_engine import run_universal_confirmation
from src.confirmation_observation_logger import log_confirmation_observation
from src.confirmation_risk_notifier import maybe_notify_confirmation_risk
from src.confirmation_summary_notifier import maybe_notify_confirmation_summary
from src.logger import logger


def _get_first(scope, names, default=None):
    for name in names:
        if name in scope and scope.get(name) is not None:
            return scope.get(name)
    return default


def _as_dict(value):
    if isinstance(value, dict):
        return dict(value)
    return {}


def _safe_float(value, default=0.0):
    try:
        return float(value or 0.0)
    except Exception:
        return default


def evaluate_tracked_confirmation_report(
    report,
    *,
    enabled=True,
    min_confidence=50.0,
    min_score_delta=-4.0,
    block_optional_failed=True,
    bucket=None,
):
    if not enabled:
        return {
            "allowed": True,
            "reason": "tracked_confirmation_gate_disabled",
            "bucket": bucket,
            "report": report,
        }

    if not report:
        return {
            "allowed": False,
            "reason": "confirmation_report_unavailable",
            "bucket": bucket,
            "report": report,
        }

    required_failed = report.get("required_failed") or []
    optional_failed = report.get("optional_failed") or []

    confidence = _safe_float(report.get("confidence"))
    score_delta = _safe_float(report.get("score_delta"))

    blocked_reasons = []

    if not report.get("approved", True):
        blocked_reasons.append("confirmation_not_approved")

    if required_failed:
        blocked_reasons.append("required_confirmation_failed")

    if block_optional_failed and optional_failed:
        blocked_reasons.append("optional_confirmation_failed")

    if confidence < float(min_confidence):
        blocked_reasons.append("confirmation_confidence_below_minimum")

    if score_delta < float(min_score_delta):
        blocked_reasons.append("confirmation_score_delta_below_minimum")

    failed_modules = []
    failed_items = list(required_failed)
    if block_optional_failed:
        failed_items.extend(optional_failed)

    for item in failed_items:
        module = item.get("module")
        if module:
            failed_modules.append(module)

    allowed = not blocked_reasons

    return {
        "allowed": allowed,
        "reason": "confirmation_gate_passed" if allowed else ",".join(blocked_reasons),
        "bucket": bucket,
        "confidence": confidence,
        "score_delta": score_delta,
        "required_failed_count": len(required_failed),
        "optional_failed_count": len(optional_failed),
        "failed_modules": failed_modules,
        "min_confidence": float(min_confidence),
        "min_score_delta": float(min_score_delta),
        "block_optional_failed": bool(block_optional_failed),
        "report": report,
    }


def run_tracked_setup_confirmation_gate(
    scope,
    *,
    setup_source_bucket_override,
    max_spread=None,
):
    enabled = bool(getattr(settings, "ENABLE_TRACKED_SETUP_CONFIRMATION_GATE", True))
    min_confidence = float(getattr(settings, "TRACKED_SETUP_CONFIRMATION_GATE_MIN_CONFIDENCE", 50))
    min_score_delta = float(getattr(settings, "TRACKED_SETUP_CONFIRMATION_GATE_MIN_SCORE_DELTA", -4))
    block_optional_failed = bool(getattr(settings, "TRACKED_SETUP_CONFIRMATION_GATE_BLOCK_OPTIONAL_FAILED", True))

    selected_signal_data = _as_dict(
        _get_first(
            scope,
            ["selected_signal_data", "signal_data", "candidate", "validated_candidate"],
            {},
        )
    )

    trade_plan = _as_dict(
        _get_first(
            scope,
            ["trade_plan", "mtf_trade_plan", "scalp_trade_plan", "reversal_trade_plan"],
            {},
        )
    )

    signal = _get_first(scope, ["signal", "candidate_signal"], None)
    strategy = _get_first(scope, ["strategy_name", "strategy"], None)
    setup_id = _get_first(scope, ["setup_id", "recovery_id"], None)

    if signal and not selected_signal_data.get("signal"):
        selected_signal_data["signal"] = signal

    if strategy and not selected_signal_data.get("strategy"):
        selected_signal_data["strategy"] = strategy

    if setup_id and not selected_signal_data.get("setup_id"):
        selected_signal_data["setup_id"] = setup_id

    selected_signal_data.setdefault("setup_source_bucket", setup_source_bucket_override)
    selected_signal_data.setdefault("execution_bucket", setup_source_bucket_override)
    trade_plan.setdefault("setup_source_bucket", setup_source_bucket_override)
    trade_plan.setdefault("execution_bucket", setup_source_bucket_override)

    df = _get_first(scope, ["df", "df_m15", "m15_df", "df_signal", "latest_df"], None)
    tick = _get_first(scope, ["tick", "current_tick", "symbol_tick"], None)

    session_name = (
        _get_first(scope, ["session_name", "active_session", "session"], None)
        or selected_signal_data.get("session")
        or trade_plan.get("session")
    )

    market_condition = (
        _get_first(scope, ["market_condition", "active_market_condition"], None)
        or selected_signal_data.get("market_condition")
        or trade_plan.get("market_condition")
    )

    min_rr_required = _get_first(
        scope,
        ["min_rr_required", "required_rr", "candidate_required_rr", "min_rr"],
        None,
    )

    report = run_universal_confirmation(
        signal_data=selected_signal_data,
        trade_plan=trade_plan,
        df=df,
        tick=tick,
        session=session_name,
        market_condition=market_condition,
        min_rr=min_rr_required,
        max_spread=max_spread,
        enforce_required=True,
    )

    try:
        log_confirmation_observation(
            report=report,
            signal_data=selected_signal_data,
            trade_plan=trade_plan,
        )
    except Exception as exc:
        logger.warning(f"[TRACKED CONFIRMATION GATE] observation log failed safely: {exc}")

    try:
        maybe_notify_confirmation_risk(
            report=report,
            signal_data=selected_signal_data,
            trade_plan=trade_plan,
        )
    except Exception as exc:
        logger.warning(f"[TRACKED CONFIRMATION GATE] risk notify failed safely: {exc}")

    try:
        maybe_notify_confirmation_summary(
            report=report,
            signal_data=selected_signal_data,
            trade_plan=trade_plan,
        )
    except Exception as exc:
        logger.warning(f"[TRACKED CONFIRMATION GATE] summary notify failed safely: {exc}")

    return evaluate_tracked_confirmation_report(
        report,
        enabled=enabled,
        min_confidence=min_confidence,
        min_score_delta=min_score_delta,
        block_optional_failed=block_optional_failed,
        bucket=setup_source_bucket_override,
    )
