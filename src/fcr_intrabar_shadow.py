from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

from src.strategies import strategy_fcr_m1_fvg as fcr
from src.fcr_runtime_guard import validate_fcr_runtime_geometry


DEFAULT_OUTPUT_PATH = Path(
    "data/research/fcr_intrabar_shadow_observations.jsonl"
)
DEFAULT_STATE_PATH = Path(
    "data/research/fcr_intrabar_shadow_state.json"
)

EXECUTION_AUTHORITY = False
DECISION_IMPACT = "OBSERVE_ONLY"

_LAST_OBSERVE_MONOTONIC = 0.0


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    return number


def _epoch_from_value(value: Any) -> int | None:
    number = _safe_float(value)
    if number is not None:
        return int(number)

    try:
        return int(value.timestamp())
    except Exception:
        return None


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )


def _load_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    active = payload.get("active")
    if not isinstance(active, dict):
        return None

    return active


def _save_active(path: Path, active: dict[str, Any] | None) -> None:
    if active is None:
        if path.exists():
            path.unlink()
        return

    _atomic_json_write(
        path,
        {
            "version": 1,
            "execution_authority": False,
            "decision_impact": DECISION_IMPACT,
            "active": active,
        },
    )


def _tick_price(tick: Any, signal: str, fallback: float) -> float:
    if tick is None:
        return fallback

    if signal == "BUY":
        price = _safe_float(getattr(tick, "ask", None))
    else:
        price = _safe_float(getattr(tick, "bid", None))

    return fallback if price is None else price


def _valid_signal(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    if str(payload.get("strategy") or "").upper() != "FCR_M1_FVG":
        return None

    if str(payload.get("signal") or "").upper() not in {"BUY", "SELL"}:
        return None

    return payload


def evaluate_forming_m1_candidate(
    m5_df: Any,
    m1_df: Any,
) -> dict[str, Any] | None:
    """
    Shadow-only approximation of the existing FCR strategy using the current
    forming M1 as the provisional entry candle.

    No result from this function is allowed to enter the live execution path.
    """
    if m5_df is None or m1_df is None:
        return None

    m5_closed = m5_df.iloc[:-1].copy()
    m1_live = m1_df.copy()

    if len(m5_closed) < 10 or len(m1_live) < 10:
        return None

    fcr_row = m5_closed.iloc[-1]

    fcr_high = _safe_float(fcr_row["high"])
    fcr_low = _safe_float(fcr_row["low"])
    fcr_open = _safe_float(fcr_row["open"])
    fcr_close = _safe_float(fcr_row["close"])
    fcr_atr = _safe_float(fcr_row["atr_14"])

    if None in {
        fcr_high,
        fcr_low,
        fcr_open,
        fcr_close,
        fcr_atr,
    }:
        return None

    fcr_range = fcr_high - fcr_low
    fcr_body = abs(fcr_close - fcr_open)

    if fcr_range <= 0 or fcr_atr <= 0:
        return None

    if fcr_range < fcr_atr * fcr.FCR_MIN_RANGE_ATR:
        return None

    if fcr_body < fcr_atr * fcr.FCR_MIN_BODY_ATR:
        return None

    c1 = m1_live.iloc[-4]
    c2 = m1_live.iloc[-3]
    c3 = m1_live.iloc[-2]
    entry = m1_live.iloc[-1]

    atr = _safe_float(entry["atr_14"])
    ema = _safe_float(entry["ema_20"])
    entry_open = _safe_float(entry["open"])
    entry_high = _safe_float(entry["high"])
    entry_low = _safe_float(entry["low"])
    entry_close = _safe_float(entry["close"])

    if None in {
        atr,
        ema,
        entry_open,
        entry_high,
        entry_low,
        entry_close,
    }:
        return None

    if atr < fcr.ATR_MIN or atr > fcr.ATR_MAX:
        return None

    body = abs(entry_close - entry_open)
    candle_range = entry_high - entry_low

    if candle_range <= 0:
        return None

    if body < atr * fcr.MIN_M1_BODY_ATR:
        return None

    sl_buffer = fcr._sl_buffer(atr)

    c1_low = _safe_float(c1["low"])
    c1_high = _safe_float(c1["high"])
    c2_close = _safe_float(c2["close"])
    c3_open = _safe_float(c3["open"])
    c3_high = _safe_float(c3["high"])
    c3_low = _safe_float(c3["low"])
    c3_close = _safe_float(c3["close"])

    if None in {
        c1_low,
        c1_high,
        c2_close,
        c3_open,
        c3_high,
        c3_low,
        c3_close,
    }:
        return None

    broke_high = c2_close > fcr_high or c3_close > fcr_high
    bullish_fvg = fcr._detect_bullish_fvg(c1, c3, atr)
    bullish_engulfing = (
        entry_close > entry_open
        and entry_close > c3_high
        and entry_open <= c3_close
    )
    bullish_reclaim = entry_close > fcr_high and entry_close > ema
    buy_extension = entry_close - fcr_high
    buy_not_chasing = (
        buy_extension >= 0
        and buy_extension <= atr * fcr.MAX_EXTENSION_ATR
    )

    if (
        broke_high
        and bullish_fvg
        and bullish_engulfing
        and bullish_reclaim
        and buy_not_chasing
    ):
        gap_bottom, gap_top, gap_size = bullish_fvg
        sl_reference = round(
            min(gap_bottom, c3_low, entry_low) - sl_buffer,
            2,
        )
        stop_distance = entry_close - sl_reference
        tp_reference = round(
            entry_close
            + stop_distance * fcr.TARGET_R_MULTIPLIER,
            2,
        )

        if sl_reference < entry_close < tp_reference:
            score = fcr._score_setup(
                base_score=93,
                body=body,
                atr=atr,
                has_fvg=True,
                engulfing=bullish_engulfing,
                fcr_quality=True,
            )
            return {
                "strategy": "FCR_M1_FVG",
                "signal": "BUY",
                "score": score,
                "entry_model": "M5_FCR_HIGH_BREAK_M1_FVG_ENGULF",
                "entry_reference": round(entry_close, 2),
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "fcr_high": round(fcr_high, 2),
                "fcr_low": round(fcr_low, 2),
                "fcr_time": fcr_row.get("time"),
                "fvg_bottom": gap_bottom,
                "fvg_top": gap_top,
                "fvg_size": gap_size,
                "forming_m1_time": entry.get("time"),
                "execution_authority": False,
                "decision_impact": DECISION_IMPACT,
            }

    broke_low = c2_close < fcr_low or c3_close < fcr_low
    bearish_fvg = fcr._detect_bearish_fvg(c1, c3, atr)
    bearish_engulfing = (
        entry_close < entry_open
        and entry_close < c3_low
        and entry_open >= c3_close
    )
    bearish_reclaim = entry_close < fcr_low and entry_close < ema
    sell_extension = fcr_low - entry_close
    sell_not_chasing = (
        sell_extension >= 0
        and sell_extension <= atr * fcr.MAX_EXTENSION_ATR
    )

    if (
        broke_low
        and bearish_fvg
        and bearish_engulfing
        and bearish_reclaim
        and sell_not_chasing
    ):
        gap_bottom, gap_top, gap_size = bearish_fvg
        sl_reference = round(
            max(gap_top, c3_high, entry_high) + sl_buffer,
            2,
        )
        stop_distance = sl_reference - entry_close
        tp_reference = round(
            entry_close
            - stop_distance * fcr.TARGET_R_MULTIPLIER,
            2,
        )

        if tp_reference < entry_close < sl_reference:
            score = fcr._score_setup(
                base_score=93,
                body=body,
                atr=atr,
                has_fvg=True,
                engulfing=bearish_engulfing,
                fcr_quality=True,
            )
            return {
                "strategy": "FCR_M1_FVG",
                "signal": "SELL",
                "score": score,
                "entry_model": "M5_FCR_LOW_BREAK_M1_FVG_ENGULF",
                "entry_reference": round(entry_close, 2),
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "fcr_high": round(fcr_high, 2),
                "fcr_low": round(fcr_low, 2),
                "fcr_time": fcr_row.get("time"),
                "fvg_bottom": gap_bottom,
                "fvg_top": gap_top,
                "fvg_size": gap_size,
                "forming_m1_time": entry.get("time"),
                "execution_authority": False,
                "decision_impact": DECISION_IMPACT,
            }

    return None


def finalize_observation(
    active: dict[str, Any],
    closed_signal: dict[str, Any] | None,
    *,
    close_epoch: int,
) -> dict[str, Any]:
    signal = str(active.get("signal") or "").upper()
    trigger_price = _safe_float(active.get("market_price_at_trigger"))
    min_price = _safe_float(active.get("min_price_after_trigger"))
    max_price = _safe_float(active.get("max_price_after_trigger"))

    if trigger_price is None:
        trigger_price = _safe_float(active.get("intrabar_signal_entry"))

    if min_price is None:
        min_price = trigger_price
    if max_price is None:
        max_price = trigger_price

    mfe = None
    mae = None

    if None not in {trigger_price, min_price, max_price}:
        if signal == "BUY":
            mfe = max(0.0, max_price - trigger_price)
            mae = max(0.0, trigger_price - min_price)
        elif signal == "SELL":
            mfe = max(0.0, trigger_price - min_price)
            mae = max(0.0, max_price - trigger_price)

    closed = _valid_signal(closed_signal)
    survived = bool(
        closed
        and str(closed.get("signal") or "").upper() == signal
        and str(closed.get("entry_model") or "")
        == str(active.get("entry_model") or "")
    )

    first_trigger_epoch = int(active.get("first_trigger_epoch") or close_epoch)
    lead_seconds = max(0, close_epoch - first_trigger_epoch)

    closed_entry = (
        _safe_float(closed.get("entry_reference"))
        if closed
        else None
    )
    intrabar_entry = _safe_float(active.get("intrabar_signal_entry"))

    entry_improvement = None
    if closed_entry is not None and intrabar_entry is not None:
        if signal == "BUY":
            entry_improvement = closed_entry - intrabar_entry
        elif signal == "SELL":
            entry_improvement = intrabar_entry - closed_entry

    record = dict(active)
    record.update(
        {
            "finalized_epoch": close_epoch,
            "survived_close": survived,
            "false_positive": not survived,
            "lead_seconds": lead_seconds,
            "mfe_to_close": (
                round(mfe, 6)
                if mfe is not None
                else None
            ),
            "mae_to_close": (
                round(mae, 6)
                if mae is not None
                else None
            ),
            "closed_signal": (
                closed.get("signal")
                if closed
                else None
            ),
            "closed_entry_model": (
                closed.get("entry_model")
                if closed
                else None
            ),
            "closed_entry_reference": closed_entry,
            "closed_sl_reference": (
                _safe_float(closed.get("sl_reference"))
                if closed
                else None
            ),
            "closed_tp_reference": (
                _safe_float(closed.get("tp_reference"))
                if closed
                else None
            ),
            "entry_improvement_vs_close": (
                round(entry_improvement, 6)
                if entry_improvement is not None
                else None
            ),
            "execution_authority": False,
            "decision_impact": DECISION_IMPACT,
        }
    )

    return record


def observe_fcr_intrabar_shadow(
    *,
    symbol: str,
    tick: Any,
    min_interval_seconds: float = 1.0,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    state_path: str | Path = DEFAULT_STATE_PATH,
    now_epoch: int | None = None,
) -> dict[str, Any] | None:
    """
    Observe the forming M1 only.

    This function never registers a setup, never builds a trade plan, never
    changes SL/TP/risk, and never calls execute_trade/order_send.
    """
    global _LAST_OBSERVE_MONOTONIC

    now_mono = time.monotonic()
    if (
        _LAST_OBSERVE_MONOTONIC > 0
        and now_mono - _LAST_OBSERVE_MONOTONIC
        < max(0.0, float(min_interval_seconds))
    ):
        return None

    _LAST_OBSERVE_MONOTONIC = now_mono

    output_path = Path(output_path)
    state_path = Path(state_path)
    now_epoch = int(time.time()) if now_epoch is None else int(now_epoch)

    m5_df = fcr._fetch_df(fcr.FCR_TIMEFRAME, fcr.FCR_BARS)
    m1_df = fcr._fetch_df(fcr.ENTRY_TIMEFRAME, fcr.ENTRY_BARS)

    if m5_df is None or m1_df is None or len(m1_df) < 2:
        return None

    current_candle_epoch = _epoch_from_value(
        m1_df.iloc[-1].get("time")
    )
    if current_candle_epoch is None:
        return None

    active = _load_state(state_path)

    if (
        active is not None
        and int(active.get("m1_candle_epoch") or -1)
        != current_candle_epoch
    ):
        try:
            closed_payload = fcr.generate_signal(m1_df)
        except Exception:
            closed_payload = None

        prior_epoch = int(active.get("m1_candle_epoch") or current_candle_epoch - 60)
        finalized = finalize_observation(
            active,
            _valid_signal(closed_payload),
            close_epoch=prior_epoch + 60,
        )
        _append_jsonl(output_path, finalized)
        active = None
        _save_active(state_path, None)

    candidate = evaluate_forming_m1_candidate(
        m5_df,
        m1_df,
    )

    if active is None and candidate is not None:
        signal = str(candidate["signal"]).upper()
        signal_entry = float(candidate["entry_reference"])
        market_price = _tick_price(
            tick,
            signal,
            signal_entry,
        )

        runtime = validate_fcr_runtime_geometry(
            strategy_name="FCR_M1_FVG",
            signal=signal,
            signal_data={
                "entry_reference": signal_entry,
            },
            trade_plan={
                "entry_price": signal_entry,
                "stop_loss": candidate["sl_reference"],
                "take_profit": candidate["tp_reference"],
            },
            executable_price=market_price,
            min_rr_required=0.0,
        )

        active = {
            "observer_version": 1,
            "symbol": symbol,
            "strategy": "FCR_M1_FVG",
            "signal": signal,
            "entry_model": candidate["entry_model"],
            "m1_candle_epoch": current_candle_epoch,
            "first_trigger_epoch": now_epoch,
            "last_seen_epoch": now_epoch,
            "intrabar_signal_entry": signal_entry,
            "market_price_at_trigger": round(market_price, 6),
            "market_drift_at_trigger": round(
                market_price - signal_entry,
                6,
            ),
            "sl_reference": candidate["sl_reference"],
            "tp_reference": candidate["tp_reference"],
            "shadow_runtime_rr_at_trigger": runtime.get("runtime_rr"),
            "fcr_high": candidate.get("fcr_high"),
            "fcr_low": candidate.get("fcr_low"),
            "fcr_time": _epoch_from_value(candidate.get("fcr_time")),
            "fvg_bottom": candidate.get("fvg_bottom"),
            "fvg_top": candidate.get("fvg_top"),
            "fvg_size": candidate.get("fvg_size"),
            "min_price_after_trigger": round(market_price, 6),
            "max_price_after_trigger": round(market_price, 6),
            "condition_present_last_loop": True,
            "execution_authority": False,
            "decision_impact": DECISION_IMPACT,
        }
        _save_active(state_path, active)
        return dict(active)

    if active is not None:
        signal = str(active.get("signal") or "").upper()
        fallback = _safe_float(active.get("market_price_at_trigger")) or 0.0
        market_price = _tick_price(
            tick,
            signal,
            fallback,
        )

        min_price = _safe_float(active.get("min_price_after_trigger"))
        max_price = _safe_float(active.get("max_price_after_trigger"))

        active["min_price_after_trigger"] = round(
            min(
                market_price,
                market_price if min_price is None else min_price,
            ),
            6,
        )
        active["max_price_after_trigger"] = round(
            max(
                market_price,
                market_price if max_price is None else max_price,
            ),
            6,
        )
        active["last_seen_epoch"] = now_epoch
        active["condition_present_last_loop"] = bool(
            candidate
            and str(candidate.get("signal") or "").upper() == signal
            and str(candidate.get("entry_model") or "")
            == str(active.get("entry_model") or "")
        )
        _save_active(state_path, active)

    return None
