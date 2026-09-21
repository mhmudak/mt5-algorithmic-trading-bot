from __future__ import annotations

import json
import math
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

from config import settings


STRATEGY = "DAILY_LEVEL_LADDER_RECLAIM_REVERSAL"
ENTRY_MODEL = "STRONG_DAILY_LEVEL_SWEEP_RECLAIM_CISD"
SCHEMA_VERSION = "V1"

_RUNTIME = {
    "broker_date": None,
    "pending": {},
    "confirmed": set(),
    "last_m5_time": None,
}


def _safe_float(value):
    try:
        value = float(value)
    except Exception:
        return None
    if not math.isfinite(value):
        return None
    return value


def _numeric_list(value):
    out = []

    if isinstance(value, dict):
        for child in value.values():
            out.extend(_numeric_list(child))
        return out

    if isinstance(value, (list, tuple, set)):
        for child in value:
            out.extend(_numeric_list(child))
        return out

    number = _safe_float(value)
    if number is not None and 100.0 <= number <= 100000.0:
        out.append(number)

    return out


def _walk_named_values(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield child_path, child
            yield from _walk_named_values(child, child_path)


def _candidate_score(path, side):
    p = path.lower()
    score = 0

    if side in p:
        score += 8
    if "strong" in p:
        score += 8
    if "approved" in p:
        score += 8
    if "execution" in p:
        score += 4
    if "ladder" in p:
        score += 3
    if "level" in p:
        score += 2

    if "raw" in p:
        score -= 9
    if "shadow" in p:
        score -= 9
    if "candidate" in p:
        score -= 4
    if "observation" in p:
        score -= 4

    return score


def _best_side_levels(dllb_locals, side):
    candidates = []

    for name, value in dllb_locals.items():
        path = str(name)
        numbers = _numeric_list(value)

        if numbers and side in path.lower():
            candidates.append(
                (_candidate_score(path, side), path, numbers)
            )

        if isinstance(value, dict):
            for nested_path, nested_value in _walk_named_values(
                value,
                path,
            ):
                numbers = _numeric_list(nested_value)
                if numbers and side in nested_path.lower():
                    candidates.append(
                        (
                            _candidate_score(nested_path, side),
                            nested_path,
                            numbers,
                        )
                    )

    if not candidates:
        return [], None

    candidates.sort(
        key=lambda item: (item[0], -len(item[2])),
        reverse=True,
    )

    score, path, numbers = candidates[0]

    if score < 8:
        return [], None

    unique = sorted(
        {round(float(number), 5) for number in numbers}
    )

    if not unique or len(unique) > 20:
        return [], None

    return unique, path


def _best_named_number(dllb_locals, wanted):
    candidates = []

    for name, value in dllb_locals.items():
        lname = str(name).lower()
        number = _safe_float(value)

        if wanted in lname and number is not None:
            score = 3
            if "daily" in lname:
                score += 2
            if "strong" in lname or "approved" in lname:
                score += 2
            candidates.append((score, str(name), number))

        if isinstance(value, dict):
            for nested_path, nested_value in _walk_named_values(
                value,
                str(name),
            ):
                if wanted not in nested_path.lower():
                    continue

                number = _safe_float(nested_value)
                if number is None:
                    continue

                score = 3
                p = nested_path.lower()
                if "daily" in p:
                    score += 2
                if "strong" in p or "approved" in p:
                    score += 2

                candidates.append(
                    (score, nested_path, number)
                )

    if not candidates:
        return None, None

    candidates.sort(reverse=True)
    _, path, number = candidates[0]
    return number, path


def extract_approved_ladder_context(dllb_locals):
    upper, upper_source = _best_side_levels(
        dllb_locals,
        "upper",
    )
    lower, lower_source = _best_side_levels(
        dllb_locals,
        "lower",
    )
    pivot, pivot_source = _best_named_number(
        dllb_locals,
        "pivot",
    )

    broker_date = None
    for key in (
        "broker_date_text",
        "broker_date",
        "daily_broker_date",
    ):
        if key in dllb_locals:
            value = dllb_locals.get(key)
            if value is not None:
                broker_date = str(value)
                break

    if not upper or not lower:
        return None

    return {
        "upper": upper,
        "lower": lower,
        "pivot": pivot,
        "broker_date": broker_date,
        "sources": {
            "upper": upper_source,
            "lower": lower_source,
            "pivot": pivot_source,
        },
    }


def _atr_from_m5(m5_df):
    if m5_df is None or len(m5_df) < 3:
        return None

    row = m5_df.iloc[-2]

    for key in ("atr_14", "atr", "ATR"):
        if key in row:
            value = _safe_float(row[key])
            if value is not None and value > 0:
                return value

    ranges = (
        m5_df["high"].astype(float)
        - m5_df["low"].astype(float)
    ).tail(14)

    if len(ranges):
        value = _safe_float(ranges.mean())
        if value is not None and value > 0:
            return value

    return None


def _sweep_buffer(atr):
    minimum = float(
        getattr(
            settings,
            "DAILY_LEVEL_LADDER_RECLAIM_REVERSAL_MIN_SWEEP_USD",
            0.10,
        )
    )
    fraction = float(
        getattr(
            settings,
            "DAILY_LEVEL_LADDER_RECLAIM_REVERSAL_ATR_SWEEP_FRACTION",
            0.03,
        )
    )

    if atr is None:
        return minimum

    return max(
        minimum,
        min(0.75, atr * fraction),
    )


def detect_closed_m5_reclaim(
    *,
    previous_bar,
    current_bar,
    upper_levels,
    lower_levels,
    atr,
):
    prev_low = _safe_float(previous_bar.get("low"))
    prev_high = _safe_float(previous_bar.get("high"))
    current_high = _safe_float(current_bar.get("high"))
    current_low = _safe_float(current_bar.get("low"))
    current_close = _safe_float(current_bar.get("close"))

    if None in (
        prev_low,
        prev_high,
        current_high,
        current_low,
        current_close,
    ):
        return None

    buffer = _sweep_buffer(atr)

    buy_hits = []
    for level in lower_levels:
        swept = min(prev_low, current_low) <= level - buffer
        reclaimed = current_close >= level + buffer

        if swept and reclaimed:
            buy_hits.append(level)

    sell_hits = []
    for level in upper_levels:
        swept = max(prev_high, current_high) >= level + buffer
        reclaimed = current_close <= level - buffer

        if swept and reclaimed:
            sell_hits.append(level)

    events = []

    if buy_hits:
        level = min(buy_hits)
        events.append(
            {
                "signal": "BUY",
                "level": level,
                "level_side": "LOWER",
                "entry": current_close,
                "sweep_extreme": min(prev_low, current_low),
                "reclaim_buffer": buffer,
                "reclaim_mode": (
                    "SAME_BAR"
                    if current_low <= level - buffer
                    else "DELAYED"
                ),
            }
        )

    if sell_hits:
        level = max(sell_hits)
        events.append(
            {
                "signal": "SELL",
                "level": level,
                "level_side": "UPPER",
                "entry": current_close,
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
        key=lambda event: abs(
            current_close - event["level"]
        )
    )
    return events[0]


def _closed_m1(symbol, bars=40):
    rates = mt5.copy_rates_from_pos(
        symbol,
        mt5.TIMEFRAME_M1,
        1,
        bars,
    )

    if rates is None or len(rates) < 4:
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(
        df["time"],
        unit="s",
    )

    return df.sort_values("time").reset_index(drop=True)


def find_closed_m1_cisd_confirmation(
    *,
    m1_df,
    signal,
    armed_after,
):
    if m1_df is None or len(m1_df) < 3:
        return None

    armed_after = pd.Timestamp(armed_after)
    window_start = armed_after - pd.Timedelta(minutes=3)

    df = m1_df[
        m1_df["time"] >= window_start
    ].copy()

    if len(df) < 2:
        return None

    for confirm_index in range(1, len(df)):
        confirm = df.iloc[confirm_index]
        confirm_time = pd.Timestamp(confirm["time"])

        if confirm_time <= armed_after:
            continue

        prior = df.iloc[:confirm_index]

        if signal == "BUY":
            references = prior[
                prior["close"] < prior["open"]
            ]

            if references.empty:
                continue

            reference = references.iloc[-1]

            if (
                float(confirm["close"])
                > float(reference["open"])
                and float(confirm["close"])
                > float(confirm["open"])
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
            references = prior[
                prior["close"] > prior["open"]
            ]

            if references.empty:
                continue

            reference = references.iloc[-1]

            if (
                float(confirm["close"])
                < float(reference["open"])
                and float(confirm["close"])
                < float(confirm["open"])
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


def _next_target(signal, entry, upper, lower, pivot):
    candidates = list(upper) + list(lower)

    if pivot is not None:
        candidates.append(float(pivot))

    candidates = sorted(
        {round(float(level), 5) for level in candidates}
    )

    if signal == "BUY":
        higher = [
            level
            for level in candidates
            if level > entry
        ]
        return min(higher) if higher else None

    lower_candidates = [
        level
        for level in candidates
        if level < entry
    ]
    return max(lower_candidates) if lower_candidates else None


def build_shadow_observation(
    *,
    pending,
    cisd,
    ladder,
    atr,
):
    signal = pending["signal"]
    entry = float(cisd["confirmation_close"])
    level = float(pending["level"])
    sweep_extreme = float(pending["sweep_extreme"])

    sl_buffer = max(
        float(pending["reclaim_buffer"]) * 2.0,
        (atr or 0.0) * 0.15,
        0.25,
    )

    stop = (
        sweep_extreme - sl_buffer
        if signal == "BUY"
        else sweep_extreme + sl_buffer
    )

    target = _next_target(
        signal,
        entry,
        ladder["upper"],
        ladder["lower"],
        ladder.get("pivot"),
    )

    rr = None

    if target is not None:
        risk = (
            entry - stop
            if signal == "BUY"
            else stop - entry
        )
        reward = (
            target - entry
            if signal == "BUY"
            else entry - target
        )

        if risk > 0 and reward > 0:
            rr = reward / risk

    min_rr = float(
        getattr(
            settings,
            "DAILY_LEVEL_LADDER_RECLAIM_REVERSAL_MIN_RR",
            1.20,
        )
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "strategy": STRATEGY,
        "entry_model": ENTRY_MODEL,
        "signal": signal,
        "broker_date": ladder.get("broker_date"),
        "strong_level": level,
        "level_side": pending["level_side"],
        "reclaim_mode": pending["reclaim_mode"],
        "sweep_extreme": sweep_extreme,
        "reclaim_m5_time": pending["reclaim_m5_time"],
        "armed_after": pending["armed_after"],
        "cisd_policy": "CISD_REQUIRED",
        "cisd_reference_time": cisd["reference_time"],
        "cisd_reference_open": cisd["reference_open"],
        "cisd_confirmation_time": cisd["confirmation_time"],
        "cisd_confirmation_open": cisd["confirmation_open"],
        "cisd_confirmation_high": cisd["confirmation_high"],
        "cisd_confirmation_low": cisd["confirmation_low"],
        "cisd_confirmation_close": cisd["confirmation_close"],
        "shadow_entry": round(entry, 5),
        "shadow_sl": round(stop, 5),
        "shadow_tp": (
            round(target, 5)
            if target is not None
            else None
        ),
        "shadow_rr": (
            round(rr, 4)
            if rr is not None
            else None
        ),
        "required_rr": min_rr,
        "rr_pass": bool(
            rr is not None
            and rr >= min_rr
        ),
        "approved_upper_levels": ladder["upper"],
        "approved_lower_levels": ladder["lower"],
        "daily_pivot": ladder.get("pivot"),
        "ladder_sources": ladder.get("sources"),
        "decision_impact": "OBSERVE_ONLY",
        "can_execute": False,
        "can_block": False,
        "can_modify_score": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
        "can_modify_lot": False,
        "execution_authority": False,
    }


def _storage_path():
    return (
        Path(__file__).resolve().parents[1]
        / "data"
        / "daily_ladder_reclaim_reversal_shadow.jsonl"
    )


def _persist_observation(observation, logger):
    try:
        path = _storage_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open(
            "a",
            encoding="utf-8",
            newline="\n",
        ) as handle:
            handle.write(
                json.dumps(
                    observation,
                    sort_keys=True,
                    default=str,
                )
                + "\n"
            )
    except Exception as exc:
        logger.warning(
            "[DAILY LADDER RECLAIM SHADOW] "
            "persistence failed open "
            f"| error={exc}"
        )


def _notify(observation, notifier, logger):
    if not callable(notifier):
        return

    try:
        notifier(
            "🟨 DAILY LADDER RECLAIM SHADOW\n"
            f"Strategy: {STRATEGY}\n"
            f"Signal: {observation['signal']}\n"
            f"Strong Level: {observation['strong_level']}\n"
            f"Reclaim M5: {observation['reclaim_m5_time']}\n"
            f"CISD M1 CLOSED: {observation['cisd_confirmation_time']}\n"
            f"Entry: {observation['shadow_entry']}\n"
            f"SL: {observation['shadow_sl']}\n"
            f"TP: {observation['shadow_tp']}\n"
            f"RR: {observation['shadow_rr']} "
            f"/ Required: {observation['required_rr']}\n"
            f"RR Pass: {observation['rr_pass']}\n"
            "OBSERVATION ONLY — live execution unchanged."
        )
    except Exception as exc:
        logger.warning(
            "[DAILY LADDER RECLAIM SHADOW] "
            "telegram failed open "
            f"| error={exc}"
        )


def _bar_dict(row):
    return {
        key: row[key]
        for key in (
            "time",
            "open",
            "high",
            "low",
            "close",
        )
        if key in row
    }


def observe_daily_ladder_reclaim_reversal_shadow(
    *,
    symbol,
    m5_df,
    tick,
    dllb_locals,
    logger,
    notifier=None,
):
    if not bool(
        getattr(
            settings,
            "ENABLE_DAILY_LEVEL_LADDER_RECLAIM_REVERSAL_SHADOW",
            False,
        )
    ):
        return None

    if m5_df is None or len(m5_df) < 3:
        return None

    ladder = extract_approved_ladder_context(
        dllb_locals
    )

    if ladder is None:
        logger.warning(
            "[DAILY LADDER RECLAIM SHADOW] "
            "approved strong ladder context unavailable; "
            "observer skipped"
        )
        return None

    broker_date = ladder.get("broker_date")

    if _RUNTIME.get("broker_date") != broker_date:
        _RUNTIME["broker_date"] = broker_date
        _RUNTIME["pending"] = {}
        _RUNTIME["confirmed"] = set()

    current = m5_df.iloc[-2]
    previous = m5_df.iloc[-3]
    current_time = pd.Timestamp(current["time"])

    if _RUNTIME.get("last_m5_time") == current_time:
        return None

    _RUNTIME["last_m5_time"] = current_time
    atr = _atr_from_m5(m5_df)
    m1_df = _closed_m1(symbol)

    timeout_minutes = int(
        getattr(
            settings,
            "DAILY_LEVEL_LADDER_RECLAIM_REVERSAL_CISD_TIMEOUT_MINUTES",
            20,
        )
    )

    now_closed_m5_end = (
        current_time + pd.Timedelta(minutes=5)
    )

    for key, pending in list(
        _RUNTIME["pending"].items()
    ):
        armed_after = pd.Timestamp(
            pending["armed_after"]
        )

        if (
            now_closed_m5_end - armed_after
            > pd.Timedelta(minutes=timeout_minutes)
        ):
            logger.info(
                "[DAILY LADDER RECLAIM SHADOW] "
                "CISD wait expired "
                f"| signal={pending['signal']} "
                f"level={pending['level']} "
                f"reclaim_m5={pending['reclaim_m5_time']}"
            )
            del _RUNTIME["pending"][key]
            continue

        cisd = find_closed_m1_cisd_confirmation(
            m1_df=m1_df,
            signal=pending["signal"],
            armed_after=armed_after,
        )

        if cisd is None:
            continue

        observation = build_shadow_observation(
            pending=pending,
            cisd=cisd,
            ladder=ladder,
            atr=atr,
        )

        _persist_observation(
            observation,
            logger,
        )

        logger.info(
            "[DAILY LADDER RECLAIM SHADOW] "
            "CISD confirmed "
            f"| signal={observation['signal']} "
            f"level={observation['strong_level']} "
            f"entry={observation['shadow_entry']} "
            f"sl={observation['shadow_sl']} "
            f"tp={observation['shadow_tp']} "
            f"rr={observation['shadow_rr']} "
            f"rr_pass={observation['rr_pass']} "
            "| execution_authority=False"
        )

        _notify(
            observation,
            notifier,
            logger,
        )

        _RUNTIME["confirmed"].add(key)
        del _RUNTIME["pending"][key]

    reclaim = detect_closed_m5_reclaim(
        previous_bar=_bar_dict(previous),
        current_bar=_bar_dict(current),
        upper_levels=ladder["upper"],
        lower_levels=ladder["lower"],
        atr=atr,
    )

    if reclaim is None:
        return None

    key = (
        f"{broker_date}|"
        f"{reclaim['signal']}|"
        f"{round(reclaim['level'], 2)}"
    )

    if (
        key in _RUNTIME["confirmed"]
        or key in _RUNTIME["pending"]
    ):
        return None

    armed_after = (
        current_time
        + pd.Timedelta(minutes=5)
    )

    pending = {
        **reclaim,
        "reclaim_m5_time": str(current_time),
        "armed_after": str(armed_after),
    }

    _RUNTIME["pending"][key] = pending

    logger.info(
        "[DAILY LADDER RECLAIM SHADOW] "
        "reclaim detected; waiting for NEW closed-M1 CISD "
        f"| signal={pending['signal']} "
        f"level={pending['level']} "
        f"sweep_extreme={pending['sweep_extreme']} "
        f"reclaim_close={pending['entry']} "
        f"armed_after={pending['armed_after']} "
        "| execution_authority=False"
    )

    return {
        "status": "WAITING_FOR_CISD",
        "pending": pending,
        "ladder": ladder,
        "decision_impact": "OBSERVE_ONLY",
        "execution_authority": False,
    }
