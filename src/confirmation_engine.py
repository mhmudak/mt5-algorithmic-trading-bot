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




def confirm_session_context(
    *,
    signal_data=None,
    session=None,
    required=False,
):
    """
    MT5-native session context.

    This does not fetch data. It classifies whether the strategy type
    is being observed in a generally suitable trading session.
    """

    signal_data = signal_data or {}

    strategy = _safe_upper(signal_data.get("strategy"))
    session = _safe_upper(session or signal_data.get("session"), "UNKNOWN")

    momentum_strategies = {
        "ORB",
        "ORB_V00",
        "SESSION_ORB_RETEST",
        "FCR_M1_FVG",
        "TRIANGLE_PENNANT",
        "FLAG",
        "FLAG_REFINED",
        "SNIPER_V2",
        "STRICT",
        "FAST",
        "WAVETREND_MOMENTUM",
    }

    reversal_strategies = {
        "LIQUIDITY_SWEEP",
        "LIQUIDITY_TRAP",
        "CRT_TBS",
        "FRACTAL_SWEEP",
        "SMT",
        "SMT_PRO",
        "LIQUIDITY_CANDLE",
        "VWAP_RECLAIM",
        "STRUCTURE_LIQUIDITY",
        "AMD_FVG",
        "LIQUIDITY_POOL_OB",
        "FAILED_BREAKOUT_REVERSAL",
        "FAILED_FVG_REVERSAL",
        "EXTREME_SWEEP_RECLAIM",
        "IFVG_RETEST_CONFLUENCE",
        "RANGE_SWEEP_RECLAIM",
        "VWAP_RANGE_MEAN_REVERSION",
    }

    structural_strategies = {
        "FVG",
        "ORDER_BLOCK",
        "OB_FVG_COMBO",
        "BREAKER_BLOCK",
        "RELIEF_RALLY",
        "HTF_TREND_PULLBACK",
        "MTF_OB_ENTRY",
        "HEAD_SHOULDERS",
        "LVN_FVG_RECLAIM",
        "FVG_CE_MITIGATION",
        "HTF_FIB_CONFLUENCE",
        "SUPPLY_DEMAND_RETEST",
        "MTF_SR_FVG_RECLAIM",
    }

    london_ny_sessions = {
        "LONDON_OPEN",
        "LONDON",
        "NEWYORK_OPEN",
        "LONDON_NY_OVERLAP",
        "NEWYORK",
    }

    weak_sessions = {
        "OFF_HOURS",
        "ASIA",
        "NEWYORK_LATE",
    }

    evidence = {
        "strategy": strategy,
        "session": session,
        "strategy_family": "UNKNOWN",
    }

    if strategy in momentum_strategies:
        evidence["strategy_family"] = "MOMENTUM_BREAKOUT"

        if session in london_ny_sessions:
            return module_pass(
                "SESSION_CONTEXT",
                required=required,
                confidence=70,
                score_delta=1,
                source_type=SOURCE_MT5_NATIVE,
                reason="Momentum/breakout strategy observed during active London/New York session.",
                evidence=evidence,
            )

        if session in weak_sessions:
            return module_neutral(
                "SESSION_CONTEXT",
                required=required,
                confidence=60,
                score_delta=-1,
                source_type=SOURCE_MT5_NATIVE,
                reason="Momentum/breakout strategy observed during weaker activity session.",
                evidence=evidence,
            )

    if strategy in reversal_strategies:
        evidence["strategy_family"] = "REVERSAL_LIQUIDITY"

        if session in london_ny_sessions:
            return module_pass(
                "SESSION_CONTEXT",
                required=required,
                confidence=68,
                score_delta=1,
                source_type=SOURCE_MT5_NATIVE,
                reason="Liquidity/reversal strategy observed during active session.",
                evidence=evidence,
            )

        if session in weak_sessions:
            return module_neutral(
                "SESSION_CONTEXT",
                required=required,
                confidence=58,
                score_delta=-1,
                source_type=SOURCE_MT5_NATIVE,
                reason="Liquidity/reversal strategy observed during weaker activity session.",
                evidence=evidence,
            )

    if strategy in structural_strategies:
        evidence["strategy_family"] = "STRUCTURAL_SMC"

        if session in london_ny_sessions:
            return module_pass(
                "SESSION_CONTEXT",
                required=required,
                confidence=62,
                score_delta=1,
                source_type=SOURCE_MT5_NATIVE,
                reason="Structural strategy observed during active session.",
                evidence=evidence,
            )

        if session == "OFF_HOURS":
            return module_neutral(
                "SESSION_CONTEXT",
                required=required,
                confidence=55,
                score_delta=-1,
                source_type=SOURCE_MT5_NATIVE,
                reason="Structural strategy observed during off-hours.",
                evidence=evidence,
            )

    return module_neutral(
        "SESSION_CONTEXT",
        required=required,
        confidence=50,
        score_delta=0,
        source_type=SOURCE_MT5_NATIVE,
        reason="Session context is neutral or strategy family is unknown.",
        evidence=evidence,
    )


def confirm_price_action_structure(
    *,
    signal_data=None,
    df=None,
    required=False,
):
    """
    MT5-native candle/structure confirmation.

    Detects:
    - displacement
    - close beyond previous candle
    - recent liquidity sweep and reclaim

    This is not true order flow.
    """

    signal_data = signal_data or {}
    signal = _safe_upper(signal_data.get("signal"), "")

    if df is None:
        return module_disabled(
            "PRICE_ACTION_STRUCTURE",
            required=required,
            source_type=SOURCE_MT5_NATIVE,
            reason="No dataframe supplied.",
        )

    try:
        if len(df) < 15:
            return module_neutral(
                "PRICE_ACTION_STRUCTURE",
                required=required,
                confidence=45,
                source_type=SOURCE_MT5_NATIVE,
                reason="Not enough candles for price-action structure check.",
                evidence={"candles": len(df)},
            )

        last = df.iloc[-2]
        prev = df.iloc[-3]
        recent = df.iloc[-12:-2]

        close = _safe_float(last["close"])
        open_price = _safe_float(last["open"])
        high = _safe_float(last["high"])
        low = _safe_float(last["low"])
        atr = _safe_float(last.get("atr_14"), 0.0)

        body = abs(close - open_price)
        candle_range = high - low

        recent_high = _safe_float(recent["high"].max())
        recent_low = _safe_float(recent["low"].min())

        displacement = atr > 0 and body >= atr * 0.25

        bullish_bos = signal == "BUY" and close > _safe_float(prev["high"])
        bearish_bos = signal == "SELL" and close < _safe_float(prev["low"])

        swept_lows = low < recent_low and close > recent_low
        swept_highs = high > recent_high and close < recent_high

        sweep_confirms = (
            (signal == "BUY" and swept_lows)
            or (signal == "SELL" and swept_highs)
        )

        evidence = {
            "signal": signal,
            "close": close,
            "open": open_price,
            "high": high,
            "low": low,
            "atr": atr,
            "body": round(body, 3),
            "candle_range": round(candle_range, 3),
            "recent_high": recent_high,
            "recent_low": recent_low,
            "displacement": displacement,
            "bullish_bos": bullish_bos,
            "bearish_bos": bearish_bos,
            "swept_lows": swept_lows,
            "swept_highs": swept_highs,
            "sweep_confirms_signal": sweep_confirms,
        }

        score_delta = 0
        reasons = []

        if displacement:
            score_delta += 1
            reasons.append("displacement")

        if bullish_bos or bearish_bos:
            score_delta += 1
            reasons.append("bos_in_signal_direction")

        if sweep_confirms:
            score_delta += 2
            reasons.append("liquidity_sweep_reclaim_confirms_signal")

        if score_delta >= 2:
            return module_pass(
                "PRICE_ACTION_STRUCTURE",
                required=required,
                confidence=72,
                score_delta=score_delta,
                source_type=SOURCE_MT5_NATIVE,
                reason="Price-action structure supports the setup: " + ",".join(reasons),
                evidence=evidence,
            )

        if signal == "BUY" and swept_highs:
            return module_neutral(
                "PRICE_ACTION_STRUCTURE",
                required=required,
                confidence=58,
                score_delta=-1,
                source_type=SOURCE_MT5_NATIVE,
                reason="Opposing buy-side sweep detected against BUY continuation.",
                evidence=evidence,
            )

        if signal == "SELL" and swept_lows:
            return module_neutral(
                "PRICE_ACTION_STRUCTURE",
                required=required,
                confidence=58,
                score_delta=-1,
                source_type=SOURCE_MT5_NATIVE,
                reason="Opposing sell-side sweep detected against SELL continuation.",
                evidence=evidence,
            )

        return module_neutral(
            "PRICE_ACTION_STRUCTURE",
            required=required,
            confidence=55,
            score_delta=score_delta,
            source_type=SOURCE_MT5_NATIVE,
            reason="Price-action structure is not decisive.",
            evidence=evidence,
        )

    except Exception as exc:
        return module_error(
            "PRICE_ACTION_STRUCTURE",
            required=required,
            source_type=SOURCE_MT5_NATIVE,
            reason=f"Price-action structure error: {exc}",
        )


def confirm_consolidation_location(
    *,
    signal_data=None,
    df=None,
    market_condition=None,
    required=False,
):
    """
    MT5-native consolidation quality check.

    Purpose:
    reduce fake setups in range/consolidation by identifying whether
    the setup is near a range edge or stuck in the middle.

    Observe-only for now.
    """

    signal_data = signal_data or {}
    signal = _safe_upper(signal_data.get("signal"), "")
    strategy = _safe_upper(signal_data.get("strategy"))
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

    if market_condition not in consolidation_regimes:
        return module_disabled(
            "CONSOLIDATION_LOCATION",
            required=required,
            source_type=SOURCE_MT5_NATIVE,
            reason="Market condition is not classified as consolidation/range.",
            evidence={
                "market_condition": market_condition,
            },
        )

    if df is None:
        return module_neutral(
            "CONSOLIDATION_LOCATION",
            required=required,
            confidence=45,
            source_type=SOURCE_MT5_NATIVE,
            reason="No dataframe supplied for consolidation location check.",
            evidence={
                "market_condition": market_condition,
            },
        )

    try:
        if len(df) < 35:
            return module_neutral(
                "CONSOLIDATION_LOCATION",
                required=required,
                confidence=45,
                source_type=SOURCE_MT5_NATIVE,
                reason="Not enough candles for consolidation range location check.",
                evidence={
                    "candles": len(df),
                    "market_condition": market_condition,
                },
            )

        closed = df.iloc[:-1]
        window = closed.iloc[-30:]

        range_high = _safe_float(window["high"].max())
        range_low = _safe_float(window["low"].min())
        last = closed.iloc[-1]
        close = _safe_float(last["close"])

        range_size = range_high - range_low

        if range_size <= 0:
            return module_neutral(
                "CONSOLIDATION_LOCATION",
                required=required,
                confidence=40,
                source_type=SOURCE_MT5_NATIVE,
                reason="Invalid consolidation range size.",
                evidence={
                    "range_high": range_high,
                    "range_low": range_low,
                    "market_condition": market_condition,
                },
            )

        position_ratio = (close - range_low) / range_size

        near_low = position_ratio <= 0.25
        near_high = position_ratio >= 0.75
        mid_range = 0.35 <= position_ratio <= 0.65

        buy_good_location = signal == "BUY" and near_low
        sell_good_location = signal == "SELL" and near_high

        evidence = {
            "strategy": strategy,
            "signal": signal,
            "market_condition": market_condition,
            "range_high": round(range_high, 2),
            "range_low": round(range_low, 2),
            "range_size": round(range_size, 2),
            "close": round(close, 2),
            "position_ratio": round(position_ratio, 3),
            "near_low": near_low,
            "near_high": near_high,
            "mid_range": mid_range,
            "buy_good_location": buy_good_location,
            "sell_good_location": sell_good_location,
        }

        range_reversal_strategies = {
            "RANGE_SWEEP_RECLAIM",
            "VWAP_RANGE_MEAN_REVERSION",
            "LIQUIDITY_SWEEP",
            "LIQUIDITY_TRAP",
            "FAILED_BREAKOUT_REVERSAL",
            "FAILED_FVG_REVERSAL",
            "FRACTAL_SWEEP",
            "VWAP_RECLAIM",
        }

        breakout_strategies = {
            "ORB",
            "ORB_V00",
            "FAST",
            "STRICT",
            "SNIPER_V2",
            "WAVETREND_MOMENTUM",
            "TRIANGLE_PENNANT",
            "FLAG",
            "FLAG_REFINED",
        }

        if strategy in range_reversal_strategies and (buy_good_location or sell_good_location):
            return module_pass(
                "CONSOLIDATION_LOCATION",
                required=required,
                confidence=76,
                score_delta=2,
                source_type=SOURCE_MT5_NATIVE,
                reason="Range/reversal setup is located near the correct range edge.",
                evidence=evidence,
            )

        if strategy in range_reversal_strategies and mid_range:
            return module_neutral(
                "CONSOLIDATION_LOCATION",
                required=required,
                confidence=70,
                score_delta=-3,
                source_type=SOURCE_MT5_NATIVE,
                reason="Range/reversal setup is located near the middle of consolidation; higher fake-setup risk.",
                evidence=evidence,
            )

        if strategy in breakout_strategies and mid_range:
            return module_neutral(
                "CONSOLIDATION_LOCATION",
                required=required,
                confidence=60,
                score_delta=-1,
                source_type=SOURCE_MT5_NATIVE,
                reason="Breakout/momentum setup is still inside the middle of consolidation.",
                evidence=evidence,
            )

        return module_neutral(
            "CONSOLIDATION_LOCATION",
            required=required,
            confidence=55,
            score_delta=0,
            source_type=SOURCE_MT5_NATIVE,
            reason="Consolidation location is not decisive.",
            evidence=evidence,
        )

    except Exception as exc:
        return module_error(
            "CONSOLIDATION_LOCATION",
            required=required,
            source_type=SOURCE_MT5_NATIVE,
            reason=f"Consolidation location error: {exc}",
        )


def confirm_news_context_awareness(
    *,
    signal_data=None,
    required=False,
):
    """
    News context awareness.

    This does not fetch news. It only reads news context already attached
    to the setup by existing news modules.
    """

    signal_data = signal_data or {}
    news_context = signal_data.get("news_context")
    news_tag = signal_data.get("news_tag") or signal_data.get("setup_news_tag")

    if not news_context and not news_tag:
        return module_neutral(
            "NEWS_CONTEXT",
            required=required,
            confidence=50,
            score_delta=0,
            source_type=SOURCE_MT5_NATIVE,
            reason="No news context attached to setup.",
        )

    evidence = {
        "news_tag": news_tag,
        "news_context": news_context,
    }

    text = str(news_context or news_tag or "").upper()

    high_risk_keywords = [
        "FOMC",
        "CPI",
        "PPI",
        "NFP",
        "NONFARM",
        "GDP",
        "PMI",
        "POWELL",
        "FED",
        "INTEREST",
        "RATE",
        "HIGH",
        "BLACKOUT",
    ]

    high_risk = any(keyword in text for keyword in high_risk_keywords)

    if high_risk:
        return module_neutral(
            "NEWS_CONTEXT",
            required=required,
            confidence=75,
            score_delta=-2,
            source_type=SOURCE_MT5_NATIVE,
            reason="High-impact news context detected; execution should remain more selective.",
            evidence=evidence,
        )

    return module_neutral(
        "NEWS_CONTEXT",
        required=required,
        confidence=55,
        score_delta=0,
        source_type=SOURCE_MT5_NATIVE,
        reason="News context attached but not classified as high-risk by confirmation engine.",
        evidence=evidence,
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
        confirm_session_context(
            signal_data=signal_data,
            session=session,
            required=False,
        )
    )

    results.append(
        confirm_price_action_structure(
            signal_data=signal_data,
            df=df,
            required=False,
        )
    )

    results.append(
        confirm_consolidation_location(
            signal_data=signal_data,
            df=df,
            market_condition=market_condition,
            required=False,
        )
    )

    results.append(
        confirm_news_context_awareness(
            signal_data=signal_data,
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
    "confirm_session_context",
    "confirm_price_action_structure",
    "confirm_consolidation_location",
    "confirm_news_context_awareness",
]
