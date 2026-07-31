from __future__ import annotations

from dataclasses import dataclass
from typing import Any


STRATEGY_NAME = "VOLATILITY_COMPRESSION_BREAKOUT"
PHASE = "PHASE_6A_VOLATILITY_COMPRESSION_BREAKOUT"


@dataclass(frozen=True)
class VolatilityCompressionBreakoutConfig:
    compression_candles: int = 8
    atr_candles: int = 30
    max_compression_atr_ratio: float = 0.55
    max_avg_body_atr_ratio: float = 0.28
    min_breakout_body_atr_ratio: float = 0.45
    min_close_beyond_range: float = 0.20
    max_breakout_chase_atr_ratio: float = 1.80
    min_rr: float = 2.0
    target_rr: float = 2.2
    sl_buffer: float = 0.35
    max_sl_distance: float = 7.0


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def candle_value(candle: dict[str, Any], key: str) -> float:
    return safe_float(candle.get(key))


def candle_time(candle: dict[str, Any]) -> str:
    return str(candle.get("time") or candle.get("timestamp") or candle.get("created_at") or "")


def true_range(candle: dict[str, Any], previous_close: float | None = None) -> float:
    high = candle_value(candle, "high")
    low = candle_value(candle, "low")

    if previous_close is None or previous_close <= 0:
        return max(0.0, high - low)

    return max(
        high - low,
        abs(high - previous_close),
        abs(low - previous_close),
    )


def average_true_range(candles: list[dict[str, Any]]) -> float:
    if not candles:
        return 0.0

    trs: list[float] = []
    prev_close: float | None = None

    for candle in candles:
        trs.append(true_range(candle, prev_close))
        close = candle_value(candle, "close")
        if close > 0:
            prev_close = close

    return sum(trs) / len(trs) if trs else 0.0


def build_no_signal(reason: str, *, symbol: str = "XAUUSD") -> dict[str, Any]:
    return {
        "phase": PHASE,
        "strategy": STRATEGY_NAME,
        "family": "VOLATILITY_COMPRESSION_BREAKOUT",
        "symbol": symbol,
        "signal": None,
        "valid": False,
        "reason": reason,
        "funded_suitable": False,
        "auto_trade_allowed": False,
        "decision_impact": "NONE",
    }


def evaluate_volatility_compression_breakout(
    candles: list[dict[str, Any]],
    *,
    symbol: str = "XAUUSD",
    config: VolatilityCompressionBreakoutConfig | None = None,
) -> dict[str, Any]:
    cfg = config or VolatilityCompressionBreakoutConfig()

    min_required = cfg.atr_candles + cfg.compression_candles + 1

    if len(candles) < min_required:
        return build_no_signal("not_enough_candles", symbol=symbol)

    atr_window = candles[-min_required:-cfg.compression_candles - 1]
    compression_window = candles[-cfg.compression_candles - 1:-1]
    breakout_candle = candles[-1]

    atr = average_true_range(atr_window)

    if atr <= 0:
        return build_no_signal("invalid_atr", symbol=symbol)

    compression_high = max(candle_value(c, "high") for c in compression_window)
    compression_low = min(candle_value(c, "low") for c in compression_window)
    compression_range = compression_high - compression_low

    if compression_range <= 0:
        return build_no_signal("invalid_compression_range", symbol=symbol)

    compression_atr_ratio = compression_range / atr

    if compression_atr_ratio > cfg.max_compression_atr_ratio:
        return build_no_signal("range_not_compressed", symbol=symbol)

    bodies = [abs(candle_value(c, "close") - candle_value(c, "open")) for c in compression_window]
    avg_body = sum(bodies) / len(bodies) if bodies else 0.0
    avg_body_atr_ratio = avg_body / atr if atr else 0.0

    if avg_body_atr_ratio > cfg.max_avg_body_atr_ratio:
        return build_no_signal("bodies_not_compressed", symbol=symbol)

    open_price = candle_value(breakout_candle, "open")
    high = candle_value(breakout_candle, "high")
    low = candle_value(breakout_candle, "low")
    close = candle_value(breakout_candle, "close")

    if min(open_price, high, low, close) <= 0:
        return build_no_signal("invalid_breakout_candle_prices", symbol=symbol)

    breakout_body = abs(close - open_price)
    breakout_body_atr_ratio = breakout_body / atr if atr else 0.0

    if breakout_body_atr_ratio < cfg.min_breakout_body_atr_ratio:
        return build_no_signal("breakout_body_too_small", symbol=symbol)

    if breakout_body_atr_ratio > cfg.max_breakout_chase_atr_ratio:
        return build_no_signal("breakout_candle_too_extended_chase_risk", symbol=symbol)

    bullish_break = close >= compression_high + cfg.min_close_beyond_range
    bearish_break = close <= compression_low - cfg.min_close_beyond_range

    if bullish_break and bearish_break:
        return build_no_signal("ambiguous_breakout", symbol=symbol)

    if not bullish_break and not bearish_break:
        return build_no_signal("no_close_outside_compression", symbol=symbol)

    if bullish_break:
        signal = "BUY"
        entry = close
        sl = compression_low - cfg.sl_buffer
        sl_distance = entry - sl
        tp = entry + (sl_distance * cfg.target_rr)
        breakout_edge = compression_high
        setup_type = "BULLISH_COMPRESSION_BREAKOUT"
    else:
        signal = "SELL"
        entry = close
        sl = compression_high + cfg.sl_buffer
        sl_distance = sl - entry
        tp = entry - (sl_distance * cfg.target_rr)
        breakout_edge = compression_low
        setup_type = "BEARISH_COMPRESSION_BREAKOUT"

    if sl_distance <= 0:
        return build_no_signal("invalid_sl_distance", symbol=symbol)

    if sl_distance > cfg.max_sl_distance:
        return build_no_signal("sl_distance_too_wide_for_funded_or_demo_test", symbol=symbol)

    rr = abs(tp - entry) / sl_distance if sl_distance else 0.0

    if rr < cfg.min_rr:
        return build_no_signal("rr_too_low", symbol=symbol)

    return {
        "phase": PHASE,
        "strategy": STRATEGY_NAME,
        "family": "VOLATILITY_COMPRESSION_BREAKOUT",
        "symbol": symbol,
        "signal": signal,
        "valid": True,
        "setup_type": setup_type,
        "entry": round(entry, 3),
        "sl": round(sl, 3),
        "tp": round(tp, 3),
        "rr": round(rr, 3),
        "score": 0,
        "time": candle_time(breakout_candle),
        "compression_high": round(compression_high, 3),
        "compression_low": round(compression_low, 3),
        "compression_range": round(compression_range, 3),
        "breakout_edge": round(breakout_edge, 3),
        "atr": round(atr, 3),
        "compression_atr_ratio": round(compression_atr_ratio, 3),
        "avg_body_atr_ratio": round(avg_body_atr_ratio, 3),
        "breakout_body_atr_ratio": round(breakout_body_atr_ratio, 3),
        "sl_distance": round(sl_distance, 3),
        "funded_suitable": True,
        "demo_execution_suitable": True,
        "funded_rules": {
            "no_martingale": True,
            "no_averaging": True,
            "one_position_only": True,
            "defined_sl": True,
            "min_rr": cfg.min_rr,
            "max_sl_distance": cfg.max_sl_distance,
        },
        "auto_trade_allowed": False,
        "decision_impact": "NONE",
        "reason": "valid_volatility_compression_breakout",
    }



def _row_to_candle(row: Any) -> dict[str, Any]:
    return {
        "time": str(row.get("time") or row.get("timestamp") or row.name or ""),
        "open": safe_float(row.get("open")),
        "high": safe_float(row.get("high")),
        "low": safe_float(row.get("low")),
        "close": safe_float(row.get("close")),
        "tick_volume": safe_float(row.get("tick_volume")),
    }


def _is_demo_account() -> bool:
    try:
        import MetaTrader5 as mt5

        info = mt5.account_info()

        if info is None:
            return False

        trade_mode = getattr(info, "trade_mode", None)
        demo_constant = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)

        if demo_constant is not None and trade_mode == demo_constant:
            return True

        server = str(getattr(info, "server", "") or "").lower()
        name = str(getattr(info, "name", "") or "").lower()

        return "demo" in server or "demo" in name

    except Exception:
        return False


def _score_signal(result: dict[str, Any], min_score: int) -> int:
    score = int(min_score)

    compression_ratio = safe_float(result.get("compression_atr_ratio"))
    avg_body_ratio = safe_float(result.get("avg_body_atr_ratio"))
    breakout_body_ratio = safe_float(result.get("breakout_body_atr_ratio"))
    rr = safe_float(result.get("rr"))

    if compression_ratio and compression_ratio <= 0.35:
        score += 1

    if compression_ratio and compression_ratio <= 0.25:
        score += 1

    if avg_body_ratio and avg_body_ratio <= 0.18:
        score += 1

    if breakout_body_ratio and breakout_body_ratio >= 0.60:
        score += 1

    if rr and rr >= 2.2:
        score += 1

    return int(min(score, 98))


def generate_signal(df):
    from config.settings import (
        ENABLE_VOLATILITY_COMPRESSION_BREAKOUT,
        VOLATILITY_COMPRESSION_BREAKOUT_DEMO_ONLY,
        VCB_ATR_CANDLES,
        VCB_COMPRESSION_CANDLES,
        VCB_MAX_AVG_BODY_ATR_RATIO,
        VCB_MAX_BREAKOUT_CHASE_ATR_RATIO,
        VCB_MAX_COMPRESSION_ATR_RATIO,
        VCB_MAX_SL_DISTANCE,
        VCB_MIN_BREAKOUT_BODY_ATR_RATIO,
        VCB_MIN_CLOSE_BEYOND_RANGE,
        VCB_MIN_RR,
        VCB_MIN_SCORE,
        VCB_SL_BUFFER,
        VCB_TARGET_RR,
    )

    if not ENABLE_VOLATILITY_COMPRESSION_BREAKOUT:
        return None

    if VOLATILITY_COMPRESSION_BREAKOUT_DEMO_ONLY and not _is_demo_account():
        return None

    min_required = VCB_ATR_CANDLES + VCB_COMPRESSION_CANDLES + 2

    if df is None or len(df) < min_required:
        return None

    # Use only closed candles, same style as the main strategies.
    closed = df.iloc[:-1].reset_index(drop=True)

    if len(closed) < min_required:
        return None

    candles = [_row_to_candle(row) for _, row in closed.iterrows()]

    cfg = VolatilityCompressionBreakoutConfig(
        compression_candles=VCB_COMPRESSION_CANDLES,
        atr_candles=VCB_ATR_CANDLES,
        max_compression_atr_ratio=VCB_MAX_COMPRESSION_ATR_RATIO,
        max_avg_body_atr_ratio=VCB_MAX_AVG_BODY_ATR_RATIO,
        min_breakout_body_atr_ratio=VCB_MIN_BREAKOUT_BODY_ATR_RATIO,
        min_close_beyond_range=VCB_MIN_CLOSE_BEYOND_RANGE,
        max_breakout_chase_atr_ratio=VCB_MAX_BREAKOUT_CHASE_ATR_RATIO,
        min_rr=VCB_MIN_RR,
        target_rr=VCB_TARGET_RR,
        sl_buffer=VCB_SL_BUFFER,
        max_sl_distance=VCB_MAX_SL_DISTANCE,
    )

    result = evaluate_volatility_compression_breakout(candles, config=cfg)

    if not result or not result.get("valid"):
        return None

    signal = result.get("signal")
    entry = safe_float(result.get("entry"))
    sl = safe_float(result.get("sl"))
    tp = safe_float(result.get("tp"))

    if signal not in {"BUY", "SELL"}:
        return None

    if entry <= 0 or sl <= 0 or tp <= 0:
        return None

    if signal == "BUY" and not (sl < entry < tp):
        return None

    if signal == "SELL" and not (tp < entry < sl):
        return None

    score = _score_signal(result, VCB_MIN_SCORE)

    result["score"] = score
    result["strategy"] = STRATEGY_NAME
    result["entry_model"] = result.get("setup_type") or "COMPRESSION_BREAKOUT"
    result["setup_source_bucket"] = "VOLATILITY_COMPRESSION_BREAKOUT"
    result["execution_mode"] = "DEMO_EXECUTION_ONLY"
    result["sl_reference"] = round(sl, 2)
    result["tp_reference"] = round(tp, 2)
    result["entry_reference"] = round(entry, 2)
    result["pattern_height"] = round(abs(tp - entry), 2)
    result["target_model"] = "COMPRESSION_BREAKOUT_RR_TARGET"
    result["orderflow_status"] = "NOT_CONNECTED_MT5_ONLY"
    result["auto_trade_allowed"] = True
    result["decision_impact"] = "MAIN_BOT_DEMO_EXECUTION_ALLOWED"
    result["reason"] = (
        f"Volatility compression breakout {signal} -> "
        f"compression={result.get('compression_low')}-{result.get('compression_high')} "
        f"ATR={result.get('atr')} compression/ATR={result.get('compression_atr_ratio')} "
        f"breakout_body/ATR={result.get('breakout_body_atr_ratio')} -> "
        f"SL {round(sl, 2)} -> TP {round(tp, 2)} score={score}"
    )

    return result
