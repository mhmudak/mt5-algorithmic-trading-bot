from __future__ import annotations

import hashlib
import math
from typing import Any

import pandas as pd

from src.daily_ladder_provider import AUTO_STRONG_MODE, DailyLadder


STRATEGY_NAME = "DAILY_LEVEL_LADDER_RECLAIM_REVERSAL"
ENTRY_MODEL = "STRONG_DAILY_LEVEL_SWEEP_RECLAIM_CISD"
SL_MODEL = "SWEEP_EXTREME_ATR_BUFFER"
TP_MODEL = "NEXT_APPROVED_STRONG_LEVEL"
DECISION_IMPACT = "MAIN_BOT_RUNTIME_CONTROLLED"


def _safe_float(value: Any) -> float | None:
    try:
        value = float(value)
    except Exception:
        return None
    if not math.isfinite(value):
        return None
    return value


def reclaim_sweep_buffer(
    *,
    atr: float | None,
    minimum_sweep_usd: float,
    atr_sweep_fraction: float,
) -> float:
    minimum = max(0.0, float(minimum_sweep_usd))
    fraction = max(0.0, float(atr_sweep_fraction))

    if atr is None or float(atr) <= 0:
        return minimum

    return max(
        minimum,
        min(0.75, float(atr) * fraction),
    )


def detect_closed_m5_reclaim(
    *,
    previous_bar: Any,
    current_bar: Any,
    approved_ladder: DailyLadder,
    atr: float | None,
    minimum_sweep_usd: float,
    atr_sweep_fraction: float,
) -> dict[str, Any] | None:
    """Detect a completed-M5 sweep/reclaim of an AUTO_STRONG rung only."""
    if not isinstance(approved_ladder, DailyLadder):
        return None
    if str(approved_ladder.source).upper() != AUTO_STRONG_MODE:
        return None

    prev_low = _safe_float(previous_bar.get("low"))
    prev_high = _safe_float(previous_bar.get("high"))
    current_high = _safe_float(current_bar.get("high"))
    current_low = _safe_float(current_bar.get("low"))
    current_close = _safe_float(current_bar.get("close"))

    if None in {
        prev_low,
        prev_high,
        current_high,
        current_low,
        current_close,
    }:
        return None

    buffer = reclaim_sweep_buffer(
        atr=atr,
        minimum_sweep_usd=minimum_sweep_usd,
        atr_sweep_fraction=atr_sweep_fraction,
    )

    events: list[dict[str, Any]] = []

    buy_hits = []
    for level in approved_ladder.lower:
        level = float(level)
        swept = min(prev_low, current_low) <= level - buffer
        reclaimed = current_close >= level + buffer
        if swept and reclaimed:
            buy_hits.append(level)

    if buy_hits:
        # If one completed M5 sweeps/reclaims multiple lower rungs, the deepest
        # swept/reclaimed AUTO_STRONG rung is the authoritative reversal level.
        level = min(buy_hits)
        events.append(
            {
                "signal": "BUY",
                "level": level,
                "level_side": "LOWER",
                "reclaim_close": current_close,
                "sweep_extreme": min(prev_low, current_low),
                "reclaim_buffer": buffer,
                "reclaim_mode": (
                    "SAME_BAR"
                    if current_low <= level - buffer
                    else "DELAYED"
                ),
            }
        )

    sell_hits = []
    for level in approved_ladder.upper:
        level = float(level)
        swept = max(prev_high, current_high) >= level + buffer
        reclaimed = current_close <= level - buffer
        if swept and reclaimed:
            sell_hits.append(level)

    if sell_hits:
        level = max(sell_hits)
        events.append(
            {
                "signal": "SELL",
                "level": level,
                "level_side": "UPPER",
                "reclaim_close": current_close,
                "sweep_extreme": max(prev_high, current_high),
                "reclaim_buffer": buffer,
                "reclaim_mode": (
                    "SAME_BAR"
                    if current_high >= level + buffer
                    else "DELAYED"
                ),
            }
        )

    if not events:
        return None

    events.sort(
        key=lambda event: abs(current_close - float(event["level"]))
    )
    return events[0]


def find_closed_m1_cisd_confirmation(
    *,
    m1_df: Any,
    signal: str,
    armed_after: Any,
) -> dict[str, Any] | None:
    """Return the first new CLOSED-M1 CISD after the completed-M5 reclaim."""
    if m1_df is None or len(m1_df) < 2:
        return None

    armed_after = pd.Timestamp(armed_after)
    df = m1_df.copy()
    df["time"] = pd.to_datetime(df["time"])
    window_start = armed_after - pd.Timedelta(minutes=3)
    df = df[df["time"] >= window_start].sort_values("time")

    if len(df) < 2:
        return None

    for confirm_index in range(1, len(df)):
        confirm = df.iloc[confirm_index]
        confirm_time = pd.Timestamp(confirm["time"])

        if confirm_time <= armed_after:
            continue

        prior = df.iloc[:confirm_index]

        if signal == "BUY":
            references = prior[prior["close"] < prior["open"]]
            if references.empty:
                continue
            reference = references.iloc[-1]
            if (
                float(confirm["close"]) > float(reference["open"])
                and float(confirm["close"]) > float(confirm["open"])
            ):
                return {
                    "reference_time": str(reference["time"]),
                    "reference_open": float(reference["open"]),
                    "confirmation_time": str(confirm["time"]),
                    "confirmation_open": float(confirm["open"]),
                    "confirmation_high": float(confirm["high"]),
                    "confirmation_low": float(confirm["low"]),
                    "confirmation_close": float(confirm["close"]),
                }

        elif signal == "SELL":
            references = prior[prior["close"] > prior["open"]]
            if references.empty:
                continue
            reference = references.iloc[-1]
            if (
                float(confirm["close"]) < float(reference["open"])
                and float(confirm["close"]) < float(confirm["open"])
            ):
                return {
                    "reference_time": str(reference["time"]),
                    "reference_open": float(reference["open"]),
                    "confirmation_time": str(confirm["time"]),
                    "confirmation_open": float(confirm["open"]),
                    "confirmation_high": float(confirm["high"]),
                    "confirmation_low": float(confirm["low"]),
                    "confirmation_close": float(confirm["close"]),
                }

    return None


def next_reversal_target(
    *,
    signal: str,
    entry: float,
    approved_ladder: DailyLadder,
) -> float | None:
    if not isinstance(approved_ladder, DailyLadder):
        return None
    if str(approved_ladder.source).upper() != AUTO_STRONG_MODE:
        return None

    candidates = (
        list(float(value) for value in approved_ladder.upper)
        + list(float(value) for value in approved_ladder.lower)
        + [float(approved_ladder.pivot)]
    )
    candidates = sorted({round(value, 5) for value in candidates})

    if signal == "BUY":
        higher = [level for level in candidates if level > float(entry)]
        return min(higher) if higher else None

    if signal == "SELL":
        lower = [level for level in candidates if level < float(entry)]
        return max(lower) if lower else None

    return None


def _setup_id(
    *,
    approved_ladder: DailyLadder,
    signal: str,
    level: float,
    reclaim_m5_time: Any,
    cisd_confirmation_time: Any,
) -> str:
    raw = "|".join(
        (
            STRATEGY_NAME,
            approved_ladder.broker_date.isoformat(),
            str(approved_ladder.source),
            str(signal),
            f"{float(level):.5f}",
            str(reclaim_m5_time),
            str(cisd_confirmation_time),
        )
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"DLRR-{signal}-{digest}"


def build_reversal_candidate(
    *,
    pending: dict[str, Any],
    cisd: dict[str, Any],
    approved_ladder: DailyLadder,
    atr: float | None,
    minimum_rr: float,
) -> dict[str, Any] | None:
    """Build authoritative execution geometry after M5 reclaim + closed-M1 CISD."""
    if not isinstance(approved_ladder, DailyLadder):
        return None
    if str(approved_ladder.source).upper() != AUTO_STRONG_MODE:
        return None

    signal = str(pending.get("signal", "")).upper()
    if signal not in {"BUY", "SELL"}:
        return None

    entry = _safe_float(cisd.get("confirmation_close"))
    level = _safe_float(pending.get("level"))
    sweep_extreme = _safe_float(pending.get("sweep_extreme"))
    reclaim_buffer = _safe_float(pending.get("reclaim_buffer"))

    if None in {entry, level, sweep_extreme, reclaim_buffer}:
        return None

    sl_buffer = max(
        float(reclaim_buffer) * 2.0,
        (float(atr) if atr is not None and float(atr) > 0 else 0.0) * 0.15,
        0.25,
    )

    stop = (
        float(sweep_extreme) - sl_buffer
        if signal == "BUY"
        else float(sweep_extreme) + sl_buffer
    )

    target = next_reversal_target(
        signal=signal,
        entry=float(entry),
        approved_ladder=approved_ladder,
    )

    if target is None:
        return None

    risk = (
        float(entry) - float(stop)
        if signal == "BUY"
        else float(stop) - float(entry)
    )
    reward = (
        float(target) - float(entry)
        if signal == "BUY"
        else float(entry) - float(target)
    )

    if risk <= 0 or reward <= 0:
        return None

    rr = reward / risk
    setup_id = _setup_id(
        approved_ladder=approved_ladder,
        signal=signal,
        level=float(level),
        reclaim_m5_time=pending.get("reclaim_m5_time"),
        cisd_confirmation_time=cisd.get("confirmation_time"),
    )

    reason = (
        f"{STRATEGY_NAME} {signal} -> AUTO_STRONG {pending.get('level_side')} "
        f"level={round(float(level), 2)} swept/reclaimed on completed M5 -> "
        f"new closed-M1 CISD confirmed -> next approved strong target="
        f"{round(float(target), 2)}"
    )

    return {
        "signal": signal,
        "score": 95,
        "strategy": STRATEGY_NAME,
        "entry_model": ENTRY_MODEL,
        "sl_model": SL_MODEL,
        "tp_model": TP_MODEL,
        "target_model": TP_MODEL,
        "decision_impact": DECISION_IMPACT,
        "auto_trade_allowed": True,
        "setup_id": setup_id,
        "daily_approved_source": approved_ladder.source,
        "daily_broker_date": approved_ladder.broker_date.isoformat(),
        "daily_pivot": round(float(approved_ladder.pivot), 2),
        "strong_level": round(float(level), 2),
        "level_side": pending.get("level_side"),
        "reclaim_mode": pending.get("reclaim_mode"),
        "reclaim_m5_time": pending.get("reclaim_m5_time"),
        "reclaim_close": round(float(pending.get("reclaim_close")), 2),
        "sweep_extreme": round(float(sweep_extreme), 2),
        "reclaim_buffer": round(float(reclaim_buffer), 4),
        "cisd_reference_time": cisd.get("reference_time"),
        "cisd_reference_open": cisd.get("reference_open"),
        "cisd_confirmation_time": cisd.get("confirmation_time"),
        "cisd_confirmation_close": round(float(entry), 2),
        "entry_reference": round(float(entry), 2),
        "sl_reference": round(float(stop), 2),
        "tp_reference": round(float(target), 2),
        "rr_reference": round(float(rr), 4),
        "required_rr": float(minimum_rr),
        "rr_reference_pass": bool(rr >= float(minimum_rr)),
        "strategy_geometry_authoritative": True,
        "tp_authority": "DLRR_NEXT_APPROVED_STRONG_LEVEL",
        "position_management_mode": "DLRR_FIXED_LEVEL_EXIT",
        "reason": reason,
    }
