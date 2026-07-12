import importlib
import logging
import time


logger = logging.getLogger(__name__)


_CONFIRMATION_RISK_TELEGRAM_CACHE = {}


def _setting(name, default=None):
    try:
        from config import settings
        return getattr(settings, name, default)
    except Exception:
        return default


def _safe_upper(value, default="UNKNOWN"):
    if value is None:
        return default

    value = str(value).strip()

    if not value:
        return default

    return value.upper()


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _find_result(report, module_name):
    module_name = _safe_upper(module_name)

    for item in report.get("results", []) or []:
        if _safe_upper(item.get("module")) == module_name:
            return item

    return None


def _telegram_sender_candidates():
    """
    Try known project notifier modules/functions without hard-coupling this
    confirmation engine layer to one Telegram implementation.
    """

    return [
        ("src.notifier", "send_telegram_message"),
        ("src.notifier", "send_message"),
        ("src.notifier", "notify"),
        ("src.telegram_notifier", "send_telegram_message"),
        ("src.telegram_notifier", "send_message"),
        ("src.telegram_alerts", "send_telegram_message"),
        ("src.telegram_alerts", "send_message"),
        ("src.telegram_utils", "send_telegram_message"),
        ("src.telegram_utils", "send_message"),
    ]


def _send_telegram_message(message):
    """
    Best-effort Telegram send.

    Must never raise to live_bot. If no compatible notifier exists,
    the warning is logged only.
    """

    for module_name, function_name in _telegram_sender_candidates():
        try:
            module = importlib.import_module(module_name)
            fn = getattr(module, function_name, None)

            if fn is None:
                continue

            try:
                fn(message)
                return True
            except TypeError:
                try:
                    fn(text=message)
                    return True
                except TypeError:
                    try:
                        fn(body=message)
                        return True
                    except TypeError:
                        continue

        except Exception:
            continue

    logger.warning(
        "[CONFIRMATION RISK] No compatible Telegram notifier found. Message was not sent."
    )
    logger.warning("[CONFIRMATION RISK MESSAGE]\n%s", message)
    return False


def _cooldown_key(*, module, strategy, signal, session, market_condition, evidence):
    policy_family = None

    try:
        policy_family = evidence.get("policy_family")
    except Exception:
        policy_family = None

    return "|".join([
        _safe_upper(module),
        _safe_upper(strategy),
        _safe_upper(signal),
        _safe_upper(session),
        _safe_upper(market_condition),
        _safe_upper(policy_family, "NO_POLICY_FAMILY"),
    ])


def _cooldown_allows(key):
    cooldown_minutes = _safe_int(
        _setting("CONFIRMATION_RISK_TELEGRAM_COOLDOWN_MINUTES", 30),
        30,
    )

    now = time.time()
    previous = _CONFIRMATION_RISK_TELEGRAM_CACHE.get(key)

    if previous is None:
        return True

    elapsed_minutes = (now - previous) / 60.0

    return elapsed_minutes >= cooldown_minutes


def _mark_cooldown(key):
    _CONFIRMATION_RISK_TELEGRAM_CACHE[key] = time.time()


def build_confirmation_risk_alert(
    *,
    report,
    signal_data=None,
    trade_plan=None,
    setup_source_bucket=None,
):
    """
    Build alert payload if confirmation engine detects a serious risk.

    Phase 1G focuses on observe-only Telegram warnings.
    """

    report = report or {}
    signal_data = signal_data or {}
    trade_plan = trade_plan or {}

    enabled = bool(_setting("TELEGRAM_NOTIFY_CONFIRMATION_ENGINE_RISK", True))

    if not enabled:
        return {
            "should_notify": False,
            "reason": "TELEGRAM_NOTIFY_CONFIRMATION_ENGINE_RISK is disabled.",
        }

    allowed_modules = _setting(
        "CONFIRMATION_RISK_TELEGRAM_MODULES",
        ["CONSOLIDATION_POLICY_AUDIT"],
    )

    allowed_modules = {
        _safe_upper(item)
        for item in allowed_modules or []
    }

    min_confidence = _safe_int(
        _setting("CONFIRMATION_RISK_TELEGRAM_MIN_CONFIDENCE", 75),
        75,
    )

    min_negative_score_delta = _safe_float(
        _setting("CONFIRMATION_RISK_TELEGRAM_MIN_NEGATIVE_SCORE_DELTA", -5),
        -5,
    )

    strategy = (
        report.get("strategy")
        or signal_data.get("strategy")
        or trade_plan.get("strategy")
    )

    signal = (
        report.get("signal")
        or signal_data.get("signal")
        or trade_plan.get("signal")
    )

    setup_id = (
        report.get("setup_id")
        or signal_data.get("setup_id")
        or trade_plan.get("setup_id")
    )

    session = (
        signal_data.get("session")
        or trade_plan.get("session")
        or "UNKNOWN"
    )

    market_condition = (
        signal_data.get("market_condition")
        or trade_plan.get("market_condition")
        or "UNKNOWN"
    )

    entry_model = (
        report.get("entry_model")
        or signal_data.get("entry_model")
        or trade_plan.get("entry_model")
    )

    mode = report.get("mode")
    report_confidence = _safe_int(report.get("confidence"), 0)
    report_score_delta = _safe_float(report.get("score_delta"), 0.0)

    candidates = []

    for item in report.get("results", []) or []:
        module = _safe_upper(item.get("module"))

        if module not in allowed_modules:
            continue

        status = _safe_upper(item.get("status"), "")
        confidence = _safe_int(item.get("confidence"), 0)
        score_delta = _safe_float(item.get("score_delta"), 0.0)
        evidence = item.get("evidence") or {}

        risk_flags = evidence.get("risk_flags") or []

        serious_negative_score = score_delta <= min_negative_score_delta
        high_confidence = confidence >= min_confidence
        many_risk_flags = len(risk_flags) >= 3

        if module == "CONSOLIDATION_POLICY_AUDIT":
            should_flag = (
                status in ["NEUTRAL", "FAIL", "ERROR"]
                and high_confidence
                and (serious_negative_score or many_risk_flags)
            )
        else:
            should_flag = (
                status in ["FAIL", "ERROR"]
                and high_confidence
            )

        if should_flag:
            candidates.append({
                "module": module,
                "status": status,
                "confidence": confidence,
                "score_delta": score_delta,
                "reason": item.get("reason"),
                "evidence": evidence,
                "risk_flags": risk_flags,
            })

    if not candidates:
        return {
            "should_notify": False,
            "reason": "No confirmation module crossed Telegram risk threshold.",
            "report_confidence": report_confidence,
            "report_score_delta": report_score_delta,
        }

    selected = sorted(
        candidates,
        key=lambda item: (
            item.get("score_delta", 0),
            -item.get("confidence", 0),
        ),
    )[0]

    evidence = selected.get("evidence") or {}
    risk_flags = selected.get("risk_flags") or []
    support_flags = evidence.get("support_flags") or []

    cooldown_key = _cooldown_key(
        module=selected.get("module"),
        strategy=strategy,
        signal=signal,
        session=session,
        market_condition=market_condition,
        evidence=evidence,
    )

    message_lines = [
        "⚠️ CONFIRMATION ENGINE RISK",
        "",
        f"Module: {selected.get('module')}",
        f"Status: {selected.get('status')}",
        f"Confidence: {selected.get('confidence')}",
        f"Score Delta: {selected.get('score_delta')}",
        "",
        f"Strategy: {strategy}",
        f"Signal: {signal}",
        f"Entry Model: {entry_model}",
        f"Setup ID: {setup_id}",
        f"Source Bucket: {setup_source_bucket or signal_data.get('setup_source_bucket') or signal_data.get('execution_bucket') or trade_plan.get('setup_source_bucket') or trade_plan.get('execution_bucket') or 'UNKNOWN'}",
        "",
        f"Session: {session}",
        f"Market: {market_condition}",
        f"Mode: {mode}",
        "",
        f"Reason: {selected.get('reason')}",
    ]

    if risk_flags:
        message_lines.append("")
        message_lines.append("Risk Flags:")
        for flag in risk_flags[:6]:
            message_lines.append(f"- {flag}")

    if support_flags:
        message_lines.append("")
        message_lines.append("Support Flags:")
        for flag in support_flags[:4]:
            message_lines.append(f"- {flag}")

    message_lines.append("")

    if bool(_setting("CONFIRMATION_RISK_TELEGRAM_INCLUDE_OBSERVE_ONLY_NOTE", True)):
        message_lines.append("Action: observe-only, trade not blocked yet.")
    else:
        message_lines.append("Action: confirmation warning.")

    return {
        "should_notify": True,
        "module": selected.get("module"),
        "cooldown_key": cooldown_key,
        "message": "\n".join(message_lines),
        "selected": selected,
    }


def maybe_notify_confirmation_risk(
    *,
    report,
    signal_data=None,
    trade_plan=None,
    setup_source_bucket=None,
    dry_run=False,
):
    """
    Send Telegram warning when confirmation risk is serious.

    Must never block live execution.
    """

    try:
        alert = build_confirmation_risk_alert(
            report=report,
            signal_data=signal_data,
            trade_plan=trade_plan,
            setup_source_bucket=setup_source_bucket,
        )

        if not alert.get("should_notify"):
            logger.info(
                "[CONFIRMATION RISK] No Telegram alert | reason=%s",
                alert.get("reason"),
            )
            return False

        cooldown_key = alert.get("cooldown_key")

        if not dry_run and not _cooldown_allows(cooldown_key):
            logger.info(
                "[CONFIRMATION RISK] Telegram alert skipped by cooldown | key=%s",
                cooldown_key,
            )
            return False

        if dry_run:
            logger.info(
                "[CONFIRMATION RISK] dry_run=True | message:\n%s",
                alert.get("message"),
            )
            return True

        sent = _send_telegram_message(alert.get("message"))

        if sent:
            _mark_cooldown(cooldown_key)
            logger.info(
                "[CONFIRMATION RISK] Telegram alert sent | module=%s | key=%s",
                alert.get("module"),
                cooldown_key,
            )
            return True

        return False

    except Exception as exc:
        logger.error("[CONFIRMATION RISK] Telegram alert failed safely: %s", exc)
        return False


__all__ = [
    "build_confirmation_risk_alert",
    "maybe_notify_confirmation_risk",
]
