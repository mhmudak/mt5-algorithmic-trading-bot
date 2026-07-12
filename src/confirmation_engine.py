from datetime import datetime
from math import isnan


# ============================================================
# Backward-compatible low-level confirmation helpers
# Existing modules import these directly.
# Keep their behavior stable.
# ============================================================

def confirm_rejection_entry(df, signal, zone_low, zone_high, atr):
    if len(df) < 3:
        return False

    candle = df.iloc[-2]

    body = abs(candle["close"] - candle["open"])
    candle_range = candle["high"] - candle["low"]

    if candle_range <= 0:
        return False

    upper_wick = candle["high"] - max(candle["open"], candle["close"])
    lower_wick = min(candle["open"], candle["close"]) - candle["low"]

    touched_zone = candle["high"] >= zone_low and candle["low"] <= zone_high

    if not touched_zone:
        return False

    if signal == "BUY":
        return (
            candle["close"] > candle["open"]
            and lower_wick > body * 1.2
            and candle["close"] >= candle["low"] + candle_range * 0.6
            and body > atr * 0.15
        )

    if signal == "SELL":
        return (
            candle["close"] < candle["open"]
            and upper_wick > body * 1.2
            and candle["close"] <= candle["high"] - candle_range * 0.6
            and body > atr * 0.15
        )

    return False


def confirm_breakout_hold(df, signal, level, atr):
    if len(df) < 3:
        return False

    candle = df.iloc[-2]

    body = abs(candle["close"] - candle["open"])
    candle_range = candle["high"] - candle["low"]

    if candle_range <= 0:
        return False

    if signal == "BUY":
        return (
            candle["close"] > level
            and candle["low"] >= level - atr * 0.10
            and candle["close"] >= candle["low"] + candle_range * 0.7
            and body > atr * 0.20
        )

    if signal == "SELL":
        return (
            candle["close"] < level
            and candle["high"] <= level + atr * 0.10
            and candle["close"] <= candle["high"] - candle_range * 0.7
            and body > atr * 0.20
        )

    return False


def confirm_entry(df, signal):
    """
    Generic confirmation for strategies that do not already have
    strategy-specific execution confirmation.

    Uses closed candles only:
    - last = last closed candle
    - prev = candle before it
    """

    try:
        if len(df) < 4:
            return False

        last = df.iloc[-2]
        prev = df.iloc[-3]

        if signal == "BUY":
            return last["close"] > prev["high"]

        if signal == "SELL":
            return last["close"] < prev["low"]

        return False

    except Exception:
        return False


# ============================================================
# Universal Confirmation Engine Foundation
# Phase 1A:
# - explainable result structure
# - MT5_NATIVE / MT5_PROXY / TRUE_ORDER_FLOW distinction
# - COMEX layer disabled by default
# - no live execution behavior change unless explicitly integrated later
# ============================================================

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_NEUTRAL = "NEUTRAL"
STATUS_DISABLED = "DISABLED"
STATUS_ERROR = "ERROR"

SOURCE_MT5_NATIVE = "MT5_NATIVE"
SOURCE_MT5_PROXY = "MT5_PROXY"
SOURCE_TRUE_ORDER_FLOW = "TRUE_ORDER_FLOW"
SOURCE_ENGINE = "ENGINE"

MODE_MT5_ONLY = "MT5_ONLY"
MODE_MT5_PLUS_COMEX = "MT5_PLUS_COMEX"


def _safe_float(value, default=None):
    try:
        if value is None:
            return default

        value = float(value)

        if isnan(value):
            return default

        return value
    except Exception:
        return default


def _safe_upper(value, default="UNKNOWN"):
    if value is None:
        return default

    value = str(value).strip()

    if not value:
        return default

    return value.upper()


def _clamp(value, low, high):
    return max(low, min(high, value))


def _get_value(obj, key, default=None):
    if obj is None:
        return default

    if isinstance(obj, dict):
        return obj.get(key, default)

    return getattr(obj, key, default)


def _latest_closed_row(df):
    if df is None:
        return None

    try:
        if len(df) < 3:
            return None

        return df.iloc[-2]
    except Exception:
        return None


def _has_column(df, column):
    try:
        return column in df.columns
    except Exception:
        return False


def _series_sum(df, column):
    try:
        return float(df[column].sum())
    except Exception:
        return 0.0


def _compute_rr(signal, entry, sl, tp):
    signal = _safe_upper(signal, "")

    entry = _safe_float(entry)
    sl = _safe_float(sl)
    tp = _safe_float(tp)

    if entry is None or sl is None or tp is None:
        return None

    try:
        if signal == "BUY":
            risk = entry - sl
            reward = tp - entry
        elif signal == "SELL":
            risk = sl - entry
            reward = entry - tp
        else:
            return None

        if risk <= 0 or reward <= 0:
            return None

        return round(reward / risk, 2)
    except Exception:
        return None


def build_module_result(
    *,
    module,
    status,
    confidence=0,
    score_delta=0,
    required=False,
    source_type=SOURCE_ENGINE,
    reason=None,
    evidence=None,
    weight=1.0,
):
    return {
        "module": str(module or "UNKNOWN").upper(),
        "status": status,
        "confidence": int(_clamp(int(confidence or 0), 0, 100)),
        "score_delta": round(float(score_delta or 0), 2),
        "required": bool(required),
        "source_type": source_type,
        "reason": reason or "",
        "evidence": evidence or {},
        "weight": float(weight or 1.0),
        "created_at": datetime.now().isoformat(),
    }


def module_pass(
    module,
    *,
    confidence=70,
    score_delta=0,
    required=False,
    source_type=SOURCE_ENGINE,
    reason=None,
    evidence=None,
    weight=1.0,
):
    return build_module_result(
        module=module,
        status=STATUS_PASS,
        confidence=confidence,
        score_delta=score_delta,
        required=required,
        source_type=source_type,
        reason=reason,
        evidence=evidence,
        weight=weight,
    )


def module_fail(
    module,
    *,
    confidence=70,
    score_delta=0,
    required=False,
    source_type=SOURCE_ENGINE,
    reason=None,
    evidence=None,
    weight=1.0,
):
    return build_module_result(
        module=module,
        status=STATUS_FAIL,
        confidence=confidence,
        score_delta=score_delta,
        required=required,
        source_type=source_type,
        reason=reason,
        evidence=evidence,
        weight=weight,
    )


def module_neutral(
    module,
    *,
    confidence=50,
    score_delta=0,
    required=False,
    source_type=SOURCE_ENGINE,
    reason=None,
    evidence=None,
    weight=1.0,
):
    return build_module_result(
        module=module,
        status=STATUS_NEUTRAL,
        confidence=confidence,
        score_delta=score_delta,
        required=required,
        source_type=source_type,
        reason=reason,
        evidence=evidence,
        weight=weight,
    )


def module_disabled(
    module,
    *,
    required=False,
    source_type=SOURCE_ENGINE,
    reason=None,
    evidence=None,
):
    return build_module_result(
        module=module,
        status=STATUS_DISABLED,
        confidence=0,
        score_delta=0,
        required=required,
        source_type=source_type,
        reason=reason,
        evidence=evidence,
        weight=0.0,
    )


def module_error(
    module,
    *,
    required=False,
    source_type=SOURCE_ENGINE,
    reason=None,
    evidence=None,
):
    return build_module_result(
        module=module,
        status=STATUS_ERROR,
        confidence=0,
        score_delta=0,
        required=required,
        source_type=source_type,
        reason=reason,
        evidence=evidence,
        weight=0.0,
    )


# ============================================================
# Phase 1A confirmation modules
# These are intentionally conservative and mostly observe-only.
# ============================================================

def confirm_setup_schema(signal_data=None, trade_plan=None, required=True):
    signal_data = signal_data or {}
    trade_plan = trade_plan or {}

    strategy = signal_data.get("strategy") or trade_plan.get("strategy")
    signal = signal_data.get("signal") or trade_plan.get("signal")

    missing = []

    if not strategy:
        missing.append("strategy")

    if signal not in ["BUY", "SELL"]:
        missing.append("signal")

    if missing:
        return module_fail(
            "SETUP_SCHEMA",
            required=required,
            confidence=95,
            score_delta=-10,
            source_type=SOURCE_ENGINE,
            reason=f"Missing or invalid setup fields: {missing}",
            evidence={
                "strategy": strategy,
                "signal": signal,
                "missing": missing,
            },
        )

    return module_pass(
        "SETUP_SCHEMA",
        required=required,
        confidence=95,
        score_delta=0,
        source_type=SOURCE_ENGINE,
        reason="Setup has minimum required fields.",
        evidence={
            "strategy": strategy,
            "signal": signal,
        },
    )


def confirm_entry_quality(
    *,
    signal_data=None,
    trade_plan=None,
    tick=None,
    min_rr=None,
    max_spread=None,
    required=False,
):
    signal_data = signal_data or {}
    trade_plan = trade_plan or {}

    if not trade_plan:
        return module_neutral(
            "ENTRY_QUALITY",
            required=required,
            source_type=SOURCE_MT5_NATIVE,
            reason="No trade_plan supplied; entry quality not evaluated.",
        )

    signal = trade_plan.get("signal") or signal_data.get("signal")
    entry = trade_plan.get("entry_price") or trade_plan.get("entry")
    sl = trade_plan.get("stop_loss") or trade_plan.get("sl")
    tp = trade_plan.get("take_profit") or trade_plan.get("tp")

    rr = (
        _safe_float(trade_plan.get("rr"))
        or _safe_float(trade_plan.get("risk_reward"))
        or _compute_rr(signal, entry, sl, tp)
    )

    ask = _safe_float(_get_value(tick, "ask"))
    bid = _safe_float(_get_value(tick, "bid"))
    spread = None

    if ask is not None and bid is not None:
        spread = round(ask - bid, 5)

    if spread is None:
        spread = _safe_float(trade_plan.get("spread"))

    failures = []
    evidence = {
        "signal": signal,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rr": rr,
        "min_rr": min_rr,
        "spread": spread,
        "max_spread": max_spread,
    }

    if rr is None:
        failures.append("rr_unavailable_or_invalid")
    elif min_rr is not None and rr < float(min_rr):
        failures.append("rr_below_minimum")

    if max_spread is not None and spread is not None and spread > float(max_spread):
        failures.append("spread_above_maximum")

    if failures:
        return module_fail(
            "ENTRY_QUALITY",
            required=required,
            confidence=80,
            score_delta=-4,
            source_type=SOURCE_MT5_NATIVE,
            reason=f"Entry quality failed: {failures}",
            evidence={
                **evidence,
                "failures": failures,
            },
        )

    score_delta = 0

    if rr is not None and rr >= 1.20:
        score_delta += 1

    if max_spread is not None and spread is not None and spread <= float(max_spread):
        score_delta += 1

    return module_pass(
        "ENTRY_QUALITY",
        required=required,
        confidence=75,
        score_delta=score_delta,
        source_type=SOURCE_MT5_NATIVE,
        reason="Entry quality is acceptable.",
        evidence=evidence,
    )


def confirm_market_regime_context(
    *,
    signal_data=None,
    market_condition=None,
    required=False,
):
    signal_data = signal_data or {}

    strategy = _safe_upper(signal_data.get("strategy"))
    entry_model = _safe_upper(signal_data.get("entry_model"), "")
    market_condition = _safe_upper(
        market_condition or signal_data.get("market_condition"),
        "UNKNOWN",
    )

    consolidation_regimes = {
        "RANGING",
        "RANGE",
        "SIDEWAYS",
        "CONSOLIDATION",
        "LOW_VOLATILITY",
        "COMPRESSION",
    }

    trend_regimes = {
        "TRENDING",
        "STRONG_TREND",
        "PULLBACK_TREND",
        "EXPANSION",
        "VOLATILE",
    }

    evidence = {
        "strategy": strategy,
        "entry_model": entry_model,
        "market_condition": market_condition,
        "regime_family": "UNKNOWN",
    }

    if market_condition in consolidation_regimes:
        evidence["regime_family"] = "CONSOLIDATION"
        return module_neutral(
            "MARKET_REGIME",
            required=required,
            confidence=65,
            score_delta=0,
            source_type=SOURCE_MT5_NATIVE,
            reason="Consolidation/range regime detected. Later phases should enforce stricter range-edge and breakout-quality rules.",
            evidence=evidence,
        )

    if market_condition in trend_regimes:
        evidence["regime_family"] = "TREND_OR_EXPANSION"
        return module_pass(
            "MARKET_REGIME",
            required=required,
            confidence=65,
            score_delta=1,
            source_type=SOURCE_MT5_NATIVE,
            reason="Trend/expansion regime detected.",
            evidence=evidence,
        )

    return module_neutral(
        "MARKET_REGIME",
        required=required,
        confidence=45,
        score_delta=0,
        source_type=SOURCE_MT5_NATIVE,
        reason="Market regime is unknown or not classified.",
        evidence=evidence,
    )


def confirm_mt5_volume_proxy(
    *,
    df=None,
    required=False,
    expansion_ratio=1.15,
    low_activity_ratio=0.75,
):
    """
    MT5 tick/real volume proxy.

    Important:
    This is NOT true order flow.
    This does not calculate delta, footprint, bid/ask imbalance,
    absorption, iceberg orders, or aggressive buyers/sellers.
    """

    if df is None:
        return module_disabled(
            "MT5_VOLUME_PROXY",
            required=required,
            source_type=SOURCE_MT5_PROXY,
            reason="No dataframe supplied.",
            evidence={
                "proxy_warning": "This layer is not true order flow.",
            },
        )

    try:
        if len(df) < 25:
            return module_neutral(
                "MT5_VOLUME_PROXY",
                required=required,
                source_type=SOURCE_MT5_PROXY,
                reason="Not enough candles for volume proxy.",
                evidence={
                    "candles": len(df),
                    "proxy_warning": "This layer is not true order flow.",
                },
            )

        volume_col = None

        if _has_column(df, "real_volume") and _series_sum(df, "real_volume") > 0:
            volume_col = "real_volume"
        elif _has_column(df, "tick_volume") and _series_sum(df, "tick_volume") > 0:
            volume_col = "tick_volume"

        if volume_col is None:
            return module_disabled(
                "MT5_VOLUME_PROXY",
                required=required,
                source_type=SOURCE_MT5_PROXY,
                reason="No usable real_volume or tick_volume column.",
                evidence={
                    "proxy_warning": "This layer is not true order flow.",
                },
            )

        closed = df.iloc[:-1]
        sample = closed.iloc[-21:-1]
        current = closed.iloc[-1]

        avg_volume = _safe_float(sample[volume_col].mean(), 0.0)
        current_volume = _safe_float(current[volume_col], 0.0)

        if avg_volume <= 0:
            return module_neutral(
                "MT5_VOLUME_PROXY",
                required=required,
                source_type=SOURCE_MT5_PROXY,
                reason="Average proxy volume is zero.",
                evidence={
                    "volume_col": volume_col,
                    "current_volume": current_volume,
                    "avg_volume": avg_volume,
                    "proxy_warning": "This layer is not true order flow.",
                },
            )

        ratio = round(current_volume / avg_volume, 3)

        evidence = {
            "volume_col": volume_col,
            "current_volume": current_volume,
            "avg_volume_20": round(avg_volume, 2),
            "relative_volume_ratio": ratio,
            "expansion_ratio": expansion_ratio,
            "low_activity_ratio": low_activity_ratio,
            "proxy_warning": "MT5 volume is activity/participation proxy only, not true order flow.",
        }

        if ratio >= expansion_ratio:
            return module_pass(
                "MT5_VOLUME_PROXY",
                required=required,
                confidence=65,
                score_delta=1,
                source_type=SOURCE_MT5_PROXY,
                reason="MT5 proxy volume expansion detected.",
                evidence=evidence,
            )

        if ratio <= low_activity_ratio:
            return module_neutral(
                "MT5_VOLUME_PROXY",
                required=required,
                confidence=55,
                score_delta=-1,
                source_type=SOURCE_MT5_PROXY,
                reason="Low MT5 proxy activity detected. This is useful for caution, but not a true order-flow signal.",
                evidence=evidence,
            )

        return module_neutral(
            "MT5_VOLUME_PROXY",
            required=required,
            confidence=55,
            score_delta=0,
            source_type=SOURCE_MT5_PROXY,
            reason="MT5 proxy volume is normal.",
            evidence=evidence,
        )

    except Exception as exc:
        return module_error(
            "MT5_VOLUME_PROXY",
            required=required,
            source_type=SOURCE_MT5_PROXY,
            reason=f"MT5 volume proxy error: {exc}",
            evidence={
                "proxy_warning": "This layer is not true order flow.",
            },
        )


def confirm_comex_order_flow(
    *,
    signal_data=None,
    orderflow_snapshot=None,
    required=False,
):
    """
    Future TRUE_ORDER_FLOW adapter boundary.

    This must remain disabled unless a real COMEX futures data source
    is connected. Never replace this with MT5 tick-volume logic.
    """

    signal_data = signal_data or {}
    signal = _safe_upper(signal_data.get("signal"), "")

    if not orderflow_snapshot:
        return module_disabled(
            "COMEX_ORDER_FLOW",
            required=required,
            source_type=SOURCE_TRUE_ORDER_FLOW,
            reason="No real COMEX futures order-flow provider connected.",
            evidence={
                "required_data": [
                    "COMEX GC/MGC trades",
                    "bid_ask_volume",
                    "delta",
                    "cumulative_delta",
                    "market_depth",
                    "footprint_or_imbalance_data",
                ],
                "mt5_tick_volume_allowed_as_replacement": False,
            },
        )

    if not orderflow_snapshot.get("available", False):
        return module_disabled(
            "COMEX_ORDER_FLOW",
            required=required,
            source_type=SOURCE_TRUE_ORDER_FLOW,
            reason=orderflow_snapshot.get("reason") or "COMEX order flow unavailable.",
            evidence={
                "provider": orderflow_snapshot.get("provider"),
                "mt5_tick_volume_allowed_as_replacement": False,
            },
        )

    bias = _safe_upper(orderflow_snapshot.get("bias"), "NEUTRAL")
    delta = _safe_float(orderflow_snapshot.get("delta"))
    cumulative_delta = _safe_float(orderflow_snapshot.get("cumulative_delta"))
    absorption_against_signal = bool(orderflow_snapshot.get("absorption_against_signal", False))
    imbalance_confirms = bool(orderflow_snapshot.get("imbalance_confirms", False))

    evidence = {
        "provider": orderflow_snapshot.get("provider"),
        "symbol": orderflow_snapshot.get("symbol"),
        "bias": bias,
        "signal": signal,
        "delta": delta,
        "cumulative_delta": cumulative_delta,
        "absorption_against_signal": absorption_against_signal,
        "imbalance_confirms": imbalance_confirms,
        "source_is_true_order_flow": True,
    }

    if absorption_against_signal:
        return module_fail(
            "COMEX_ORDER_FLOW",
            required=required,
            confidence=85,
            score_delta=-6,
            source_type=SOURCE_TRUE_ORDER_FLOW,
            reason="COMEX order flow shows absorption against the setup.",
            evidence=evidence,
        )

    if signal in ["BUY", "SELL"] and bias == signal and imbalance_confirms:
        return module_pass(
            "COMEX_ORDER_FLOW",
            required=required,
            confidence=85,
            score_delta=5,
            source_type=SOURCE_TRUE_ORDER_FLOW,
            reason="COMEX order flow confirms setup direction.",
            evidence=evidence,
        )

    if bias in ["BUY", "SELL"] and signal in ["BUY", "SELL"] and bias != signal:
        return module_fail(
            "COMEX_ORDER_FLOW",
            required=required,
            confidence=80,
            score_delta=-5,
            source_type=SOURCE_TRUE_ORDER_FLOW,
            reason="COMEX order flow conflicts with setup direction.",
            evidence=evidence,
        )

    return module_neutral(
        "COMEX_ORDER_FLOW",
        required=required,
        confidence=60,
        score_delta=0,
        source_type=SOURCE_TRUE_ORDER_FLOW,
        reason="COMEX order flow is available but not decisive.",
        evidence=evidence,
    )


# ============================================================
# Universal report builder
# ============================================================

def build_confirmation_report(
    *,
    signal_data=None,
    trade_plan=None,
    results=None,
    enforce_required=False,
):
    signal_data = signal_data or {}
    trade_plan = trade_plan or {}
    results = results or []

    required_failed = [
        item
        for item in results
        if item.get("required") and item.get("status") in [STATUS_FAIL, STATUS_ERROR]
    ]

    optional_failed = [
        item
        for item in results
        if not item.get("required") and item.get("status") in [STATUS_FAIL, STATUS_ERROR]
    ]

    disabled_layers = [
        item.get("module")
        for item in results
        if item.get("status") == STATUS_DISABLED
    ]

    true_order_flow_active = any(
        item.get("source_type") == SOURCE_TRUE_ORDER_FLOW
        and item.get("status") != STATUS_DISABLED
        for item in results
    )

    mode = MODE_MT5_PLUS_COMEX if true_order_flow_active else MODE_MT5_ONLY

    raw_score_delta = sum(
        float(item.get("score_delta") or 0.0) * float(item.get("weight") or 1.0)
        for item in results
        if item.get("status") not in [STATUS_DISABLED, STATUS_ERROR]
    )

    score_delta = round(_clamp(raw_score_delta, -12, 12), 2)

    pass_count = sum(1 for item in results if item.get("status") == STATUS_PASS)
    fail_count = sum(1 for item in results if item.get("status") == STATUS_FAIL)
    neutral_count = sum(1 for item in results if item.get("status") == STATUS_NEUTRAL)

    confidence = 50
    confidence += min(pass_count * 7, 30)
    confidence -= min(fail_count * 10, 35)
    confidence += int(max(score_delta, 0))
    confidence -= int(abs(min(score_delta, 0)))
    confidence = int(_clamp(confidence, 0, 100))

    approved = True

    if enforce_required and required_failed:
        approved = False

    summary = (
        f"mode={mode} approved={approved} confidence={confidence} "
        f"score_delta={score_delta} pass={pass_count} "
        f"fail={fail_count} neutral={neutral_count} "
        f"required_failed={len(required_failed)}"
    )

    return {
        "created_at": datetime.now().isoformat(),
        "engine_version": "confirmation_engine_phase_1a",
        "mode": mode,
        "approved": approved,
        "confidence": confidence,
        "score_delta": score_delta,
        "enforce_required": bool(enforce_required),
        "required_failed": required_failed,
        "optional_failed": optional_failed,
        "disabled_layers": disabled_layers,
        "summary": summary,
        "strategy": signal_data.get("strategy") or trade_plan.get("strategy"),
        "signal": signal_data.get("signal") or trade_plan.get("signal"),
        "entry_model": signal_data.get("entry_model") or trade_plan.get("entry_model"),
        "setup_id": signal_data.get("setup_id") or trade_plan.get("setup_id"),
        "results": results,
    }


def run_universal_confirmation(
    *,
    signal_data=None,
    trade_plan=None,
    df=None,
    tick=None,
    session=None,
    market_condition=None,
    orderflow_snapshot=None,
    min_rr=None,
    max_spread=None,
    enforce_required=False,
):
    """
    Universal strategy-independent confirmation engine.

    Phase 1A behavior:
    - observe/score/explain only
    - approved remains True unless enforce_required=True and a required module fails
    - COMEX order flow remains disabled unless a real provider snapshot is supplied
    """

    signal_data = signal_data or {}
    trade_plan = trade_plan or {}

    if session is not None:
        signal_data.setdefault("session", session)

    if market_condition is not None:
        signal_data.setdefault("market_condition", market_condition)

    results = []

    results.append(
        confirm_setup_schema(
            signal_data=signal_data,
            trade_plan=trade_plan,
            required=True,
        )
    )

    results.append(
        confirm_market_regime_context(
            signal_data=signal_data,
            market_condition=market_condition,
            required=False,
        )
    )

    results.append(
        confirm_entry_quality(
            signal_data=signal_data,
            trade_plan=trade_plan,
            tick=tick,
            min_rr=min_rr,
            max_spread=max_spread,
            required=False,
        )
    )

    results.append(
        confirm_mt5_volume_proxy(
            df=df,
            required=False,
        )
    )

    results.append(
        confirm_comex_order_flow(
            signal_data=signal_data,
            orderflow_snapshot=orderflow_snapshot,
            required=False,
        )
    )

    return build_confirmation_report(
        signal_data=signal_data,
        trade_plan=trade_plan,
        results=results,
        enforce_required=enforce_required,
    )


def format_confirmation_report(report):
    if not report:
        return "[CONFIRMATION ENGINE] No report."

    lines = [
        "[CONFIRMATION ENGINE]",
        f"Mode: {report.get('mode')}",
        f"Approved: {report.get('approved')}",
        f"Confidence: {report.get('confidence')}",
        f"Score Delta: {report.get('score_delta')}",
        f"Strategy: {report.get('strategy')}",
        f"Signal: {report.get('signal')}",
        f"Setup ID: {report.get('setup_id')}",
        f"Summary: {report.get('summary')}",
    ]

    failed = report.get("required_failed") or []

    if failed:
        lines.append("Required failed:")
        for item in failed:
            lines.append(f"- {item.get('module')}: {item.get('reason')}")

    disabled = report.get("disabled_layers") or []

    if disabled:
        lines.append(f"Disabled layers: {', '.join(disabled)}")

    return "\n".join(lines)


__all__ = [
    "confirm_rejection_entry",
    "confirm_breakout_hold",
    "confirm_entry",
    "run_universal_confirmation",
    "format_confirmation_report",
    "build_confirmation_report",
    "build_module_result",
    "module_pass",
    "module_fail",
    "module_neutral",
    "module_disabled",
    "module_error",
    "confirm_comex_order_flow",
    "confirm_mt5_volume_proxy",
]
