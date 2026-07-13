from config import settings


SHADOW_STRONG_SUPPORT = "STRONG_SUPPORT"
SHADOW_SUPPORT = "SUPPORT"
SHADOW_WEAK_SUPPORT = "WEAK_SUPPORT"
SHADOW_NEUTRAL = "NEUTRAL"
SHADOW_CAUTION = "CAUTION"
SHADOW_HIGH_RISK = "HIGH_RISK"
SHADOW_BLOCK_CANDIDATE = "BLOCK_CANDIDATE_OBSERVE_ONLY"
SHADOW_DISABLED = "DISABLED"


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _get_modules(report):
    if not isinstance(report, dict):
        return []

    for key in ["results", "modules"]:
        value = report.get(key)
        if isinstance(value, list):
            return value

    return []


def _count_negative_modules(modules):
    count = 0
    names = []

    for module in modules:
        if not isinstance(module, dict):
            continue

        status = module.get("status")
        delta = _safe_float(module.get("score_delta"), 0.0)

        if status in {"FAIL", "ERROR"} or delta < 0:
            count += 1
            names.append(module.get("module") or "UNKNOWN_MODULE")

    return count, names


def classify_confirmation_shadow_decision(report):
    """
    Phase 2A shadow-only policy.

    This does not block trades. It only labels the setup quality for
    Telegram/logging/analyzer review.
    """

    if not getattr(settings, "ENABLE_CONFIRMATION_SHADOW_POLICY", True):
        return {
            "shadow_decision": SHADOW_DISABLED,
            "shadow_action": "OBSERVE_ONLY",
            "shadow_blocking_allowed": False,
            "shadow_reason": "Shadow policy disabled by settings.",
            "shadow_score": 0,
            "shadow_policy_version": "phase_2a_shadow_policy_v1",
        }

    report = report or {}

    confidence = _safe_float(report.get("confidence"), 0.0)
    score_delta = _safe_float(report.get("score_delta"), 0.0)
    approved = bool(report.get("approved"))

    required_failed = report.get("required_failed") or report.get("required_failed_modules") or []
    optional_failed = report.get("optional_failed") or report.get("optional_failed_modules") or []

    fail_count = _safe_int(report.get("fail_count"), 0)
    error_count = _safe_int(report.get("error_count"), 0)

    modules = _get_modules(report)
    negative_count, negative_module_names = _count_negative_modules(modules)

    strong_conf = _safe_float(getattr(settings, "CONFIRMATION_SHADOW_STRONG_CONFIDENCE", 80), 80)
    support_conf = _safe_float(getattr(settings, "CONFIRMATION_SHADOW_SUPPORT_CONFIDENCE", 70), 70)
    weak_conf = _safe_float(getattr(settings, "CONFIRMATION_SHADOW_WEAK_CONFIDENCE", 60), 60)

    strong_delta = _safe_float(getattr(settings, "CONFIRMATION_SHADOW_STRONG_POSITIVE_DELTA", 3.0), 3.0)
    support_delta = _safe_float(getattr(settings, "CONFIRMATION_SHADOW_SUPPORT_POSITIVE_DELTA", 0.0), 0.0)
    caution_delta = _safe_float(getattr(settings, "CONFIRMATION_SHADOW_CAUTION_DELTA", -3.0), -3.0)
    high_risk_delta = _safe_float(getattr(settings, "CONFIRMATION_SHADOW_HIGH_RISK_DELTA", -5.0), -5.0)

    blocking_allowed = False

    reasons = []

    if required_failed:
        decision = SHADOW_BLOCK_CANDIDATE
        reasons.append("one_or_more_required_modules_failed")

    elif not approved:
        decision = SHADOW_HIGH_RISK
        reasons.append("confirmation_engine_not_approved")

    elif error_count > 0:
        decision = SHADOW_HIGH_RISK
        reasons.append("confirmation_engine_module_error")

    elif fail_count > 0:
        decision = SHADOW_HIGH_RISK
        reasons.append("one_or_more_modules_failed")

    elif score_delta <= high_risk_delta:
        decision = SHADOW_HIGH_RISK
        reasons.append(f"score_delta <= {high_risk_delta}")

    elif score_delta <= caution_delta:
        decision = SHADOW_CAUTION
        reasons.append(f"score_delta <= {caution_delta}")

    elif confidence >= strong_conf and score_delta >= strong_delta:
        decision = SHADOW_STRONG_SUPPORT
        reasons.append(f"confidence >= {strong_conf} and score_delta >= {strong_delta}")

    elif confidence >= support_conf and score_delta >= support_delta:
        decision = SHADOW_SUPPORT
        reasons.append(f"confidence >= {support_conf} and score_delta >= {support_delta}")

    elif confidence >= weak_conf:
        decision = SHADOW_WEAK_SUPPORT
        reasons.append(f"confidence >= {weak_conf}")

    else:
        decision = SHADOW_NEUTRAL
        reasons.append("confidence/score_delta not decisive")

    if optional_failed:
        reasons.append(f"optional_failed_count={len(optional_failed)}")

    if negative_count:
        reasons.append(f"negative_module_count={negative_count}")

    shadow_score = round(confidence + (score_delta * 5), 2)

    return {
        "shadow_decision": decision,
        "shadow_action": "OBSERVE_ONLY",
        "shadow_blocking_allowed": blocking_allowed,
        "shadow_reason": "; ".join(reasons),
        "shadow_score": shadow_score,
        "shadow_confidence": confidence,
        "shadow_score_delta": score_delta,
        "shadow_negative_module_count": negative_count,
        "shadow_negative_modules": negative_module_names,
        "shadow_required_failed_count": len(required_failed),
        "shadow_optional_failed_count": len(optional_failed),
        "shadow_policy_version": "phase_2a_shadow_policy_v1",
    }


def apply_confirmation_shadow_policy(report):
    """
    Mutates only the confirmation report dictionary by adding shadow fields.
    Does not mutate trade_plan, does not mutate execution behavior.
    """

    if not isinstance(report, dict):
        return report

    shadow = classify_confirmation_shadow_decision(report)

    report.update(shadow)

    return report
