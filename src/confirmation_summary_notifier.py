from datetime import datetime, timedelta

from config import settings

try:
    from src.logger import logger
except Exception:
    logger = None


_CONFIRMATION_SUMMARY_TELEGRAM_CACHE = {}


def _log_warning(message):
    try:
        if logger:
            logger.warning(message)
            return
    except Exception:
        pass

    print(message)


def _resolve_telegram_sender():
    candidates = [
        ("src.notifier", "send_telegram_message"),
        ("src.telegram_notifier", "send_telegram_message"),
        ("src.telegram_notifier", "send_message"),
        ("src.notifier", "notify"),
    ]

    for module_name, function_name in candidates:
        try:
            module = __import__(module_name, fromlist=[function_name])
            fn = getattr(module, function_name, None)

            if callable(fn):
                return fn
        except Exception:
            continue

    return None


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


def _get_report_modules(report):
    if not isinstance(report, dict):
        return []

    modules = report.get("results")

    if isinstance(modules, list):
        return modules

    modules = report.get("modules")

    if isinstance(modules, list):
        return modules

    return []


def _build_cache_key(report, signal_data, trade_plan, setup_source_bucket):
    setup_id = (
        signal_data.get("setup_id")
        or trade_plan.get("setup_id")
        or report.get("setup_id")
        or "UNKNOWN_SETUP"
    )

    strategy = (
        signal_data.get("strategy")
        or trade_plan.get("strategy")
        or report.get("strategy")
        or "UNKNOWN_STRATEGY"
    )

    signal = (
        signal_data.get("signal")
        or trade_plan.get("signal")
        or report.get("signal")
        or "UNKNOWN_SIGNAL"
    )

    bucket = setup_source_bucket or signal_data.get("setup_source_bucket") or trade_plan.get("setup_source_bucket") or "UNKNOWN_BUCKET"

    return f"{setup_id}|{strategy}|{signal}|{bucket}"


def _cooldown_active(key):
    minutes = _safe_int(
        getattr(settings, "CONFIRMATION_SUMMARY_TELEGRAM_COOLDOWN_MINUTES", 10),
        10,
    )

    if minutes <= 0:
        return False

    now = datetime.utcnow()
    last_sent = _CONFIRMATION_SUMMARY_TELEGRAM_CACHE.get(key)

    if not last_sent:
        return False

    return now - last_sent < timedelta(minutes=minutes)


def _mark_sent(key):
    _CONFIRMATION_SUMMARY_TELEGRAM_CACHE[key] = datetime.utcnow()


def build_confirmation_summary_message(
    *,
    report,
    signal_data=None,
    trade_plan=None,
    setup_source_bucket=None,
):
    signal_data = signal_data or {}
    trade_plan = trade_plan or {}
    report = report or {}

    setup_id = (
        signal_data.get("setup_id")
        or trade_plan.get("setup_id")
        or report.get("setup_id")
        or "UNKNOWN"
    )

    strategy = (
        signal_data.get("strategy")
        or trade_plan.get("strategy")
        or report.get("strategy")
        or "UNKNOWN"
    )

    signal = (
        signal_data.get("signal")
        or trade_plan.get("signal")
        or report.get("signal")
        or "UNKNOWN"
    )

    bucket = (
        setup_source_bucket
        or signal_data.get("setup_source_bucket")
        or trade_plan.get("setup_source_bucket")
        or "UNKNOWN"
    )

    confidence = report.get("confidence")
    score_delta = report.get("score_delta")
    approved = report.get("approved")
    mode = report.get("mode")
    summary = report.get("summary")

    modules = _get_report_modules(report)
    module_count = len(modules)

    pass_count = sum(1 for m in modules if isinstance(m, dict) and m.get("status") == "PASS")
    fail_count = sum(1 for m in modules if isinstance(m, dict) and m.get("status") == "FAIL")
    neutral_count = sum(1 for m in modules if isinstance(m, dict) and m.get("status") == "NEUTRAL")
    disabled_count = sum(1 for m in modules if isinstance(m, dict) and m.get("status") == "DISABLED")

    negative_modules = []

    for module in modules:
        if not isinstance(module, dict):
            continue

        delta = _safe_float(module.get("score_delta"), 0.0)

        if delta < 0 or module.get("status") in {"FAIL", "ERROR"}:
            negative_modules.append(module)

    shadow_decision = report.get("shadow_decision")
    shadow_reason = report.get("shadow_reason")
    shadow_score = report.get("shadow_score")
    shadow_action = report.get("shadow_action")

    lines = [
        "🧠 CONFIRMATION ENGINE",
        "",
        f"Shadow Decision: {shadow_decision}",
        f"Shadow Score: {shadow_score}",
        f"Shadow Action: {shadow_action}",
        "",
        f"Confidence: {confidence}",
        f"Score Delta: {score_delta}",
        f"Approved: {approved}",
        f"Mode: {mode}",
        "",
        f"Strategy: {strategy}",
        f"Signal: {signal}",
        f"Bucket: {bucket}",
        f"Setup ID: {setup_id}",
        "",
        f"Modules: {module_count} | PASS {pass_count} | FAIL {fail_count} | NEUTRAL {neutral_count} | DISABLED {disabled_count}",
    ]

    if negative_modules:
        lines.append("")
        lines.append("Risk / Negative Modules:")

        max_modules = _safe_int(
            getattr(settings, "CONFIRMATION_SUMMARY_TELEGRAM_MAX_MODULES", 6),
            6,
        )

        for module in negative_modules[:max_modules]:
            lines.append(
                f"- {module.get('module')} | "
                f"{module.get('status')} | "
                f"Δ {module.get('score_delta')} | "
                f"{module.get('reason')}"
            )

    include_details = getattr(
        settings,
        "CONFIRMATION_SUMMARY_TELEGRAM_INCLUDE_MODULE_DETAILS",
        True,
    )

    if include_details and modules:
        lines.append("")
        lines.append("Top Modules:")

        max_modules = _safe_int(
            getattr(settings, "CONFIRMATION_SUMMARY_TELEGRAM_MAX_MODULES", 6),
            6,
        )

        for module in modules[:max_modules]:
            if not isinstance(module, dict):
                continue

            lines.append(
                f"- {module.get('module')}: "
                f"{module.get('status')} | "
                f"conf {module.get('confidence')} | "
                f"Δ {module.get('score_delta')}"
            )

    if shadow_reason:
        lines.append("")
        lines.append(f"Shadow Reason: {shadow_reason}")

    if summary:
        lines.append("")
        lines.append(f"Summary: {summary}")

    lines.append("")
    lines.append("Action: observe-only, trade not blocked.")

    return "\n".join(str(x) for x in lines)


def maybe_notify_confirmation_summary(
    *,
    report,
    signal_data=None,
    trade_plan=None,
    setup_source_bucket=None,
):
    try:
        if not getattr(settings, "TELEGRAM_NOTIFY_CONFIRMATION_ENGINE_SUMMARY", False):
            return False

        sender = _resolve_telegram_sender()

        if not sender:
            _log_warning("[CONFIRMATION SUMMARY] Telegram sender not found.")
            return False

        signal_data = signal_data or {}
        trade_plan = trade_plan or {}
        report = report or {}

        key = _build_cache_key(report, signal_data, trade_plan, setup_source_bucket)

        if _cooldown_active(key):
            return False

        message = build_confirmation_summary_message(
            report=report,
            signal_data=signal_data,
            trade_plan=trade_plan,
            setup_source_bucket=setup_source_bucket,
        )

        result = sender(message)

        _mark_sent(key)

        return result

    except Exception as exc:
        _log_warning(f"[CONFIRMATION SUMMARY] Telegram summary failed safely: {exc}")
        return False
