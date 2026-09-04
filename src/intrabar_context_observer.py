from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from src.account_context import get_account_file
from src.logger import logger


OBSERVATION_FILENAME = (
    "intrabar_context_observations.jsonl"
)

INTRABAR_CONTEXT_OBSERVER_STRATEGIES = {
    "AUTO_STRUCTURAL_LEVEL_SCALP",
    "FAILED_FVG_REVERSAL",
}

SCHEMA_VERSION = 1


TREND_REGIMES = {
    "TRENDING",
    "STRONG_TREND",
    "EXPANSION",
    "VOLATILE",
}

PULLBACK_REGIMES = {
    "PULLBACK",
    "PULLBACK_TREND",
    "CORRECTION",
    "RETRACE",
    "RETRACEMENT",
}

RANGE_REGIMES = {
    "RANGING",
    "RANGE",
    "SIDEWAYS",
    "CONSOLIDATION",
    "COMPRESSION",
    "LOW_VOLATILITY",
}


def _safe_text(value, default=""):
    if value is None:
        return default

    value = str(value).strip()

    return value if value else default


def _safe_float(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(value):
        return None

    return value


def _json_safe(value):
    if value is None:
        return None

    if isinstance(
        value,
        (str, int, bool),
    ):
        return value

    if isinstance(value, float):
        return (
            value
            if math.isfinite(value)
            else None
        )

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (list, tuple, set),
    ):
        return [
            _json_safe(item)
            for item in value
        ]

    converted = _safe_float(value)

    if converted is not None:
        return converted

    return str(value)


def _normalize_direction(value):
    value = _safe_text(
        value
    ).upper()

    if value in {
        "BUY",
        "BULL",
        "BULLISH",
        "LONG",
        "UP",
    }:
        return "BUY"

    if value in {
        "SELL",
        "BEAR",
        "BEARISH",
        "SHORT",
        "DOWN",
    }:
        return "SELL"

    return "UNKNOWN"


def _direction_relation(
    signal,
    direction,
    *,
    aligned_label,
    counter_label,
):
    signal = _normalize_direction(
        signal
    )

    direction = _normalize_direction(
        direction
    )

    if (
        signal == "UNKNOWN"
        or direction == "UNKNOWN"
    ):
        return "UNKNOWN"

    if signal == direction:
        return aligned_label

    return counter_label


def _regime_family(value):
    value = _safe_text(
        value,
        "UNKNOWN",
    ).upper()

    if value in TREND_REGIMES:
        return "TREND_OR_EXPANSION"

    if value in PULLBACK_REGIMES:
        return "PULLBACK_OR_CORRECTION"

    if value in RANGE_REGIMES:
        return "RANGE_OR_COMPRESSION"

    return "UNKNOWN"


def _series_tail_float(
    df,
    column,
    offset,
):
    try:
        if (
            df is None
            or column not in df.columns
            or len(df) <= offset
        ):
            return None

        return _safe_float(
            df[column].iloc[
                -(offset + 1)
            ]
        )
    except Exception:
        return None


def _atr_proxy(df, periods=14):
    try:
        if (
            df is None
            or len(df) < 3
            or "high" not in df.columns
            or "low" not in df.columns
            or "close" not in df.columns
        ):
            return None

        start = max(
            1,
            len(df) - periods,
        )

        true_ranges = []

        for i in range(
            start,
            len(df),
        ):
            high = _safe_float(
                df["high"].iloc[i]
            )

            low = _safe_float(
                df["low"].iloc[i]
            )

            previous_close = _safe_float(
                df["close"].iloc[i - 1]
            )

            if (
                high is None
                or low is None
                or previous_close is None
            ):
                continue

            true_ranges.append(
                max(
                    high - low,
                    abs(
                        high
                        - previous_close
                    ),
                    abs(
                        low
                        - previous_close
                    ),
                )
            )

        if not true_ranges:
            return None

        return (
            sum(true_ranges)
            / len(true_ranges)
        )

    except Exception:
        return None


def _normalized(
    value,
    denominator,
):
    if (
        value is None
        or denominator is None
        or denominator <= 0
    ):
        return None

    return round(
        value / denominator,
        6,
    )


def _price_features(
    df,
    signal,
):
    close_0 = _series_tail_float(
        df,
        "close",
        0,
    )

    close_1 = _series_tail_float(
        df,
        "close",
        1,
    )

    close_3 = _series_tail_float(
        df,
        "close",
        3,
    )

    close_8 = _series_tail_float(
        df,
        "close",
        8,
    )

    high_0 = _series_tail_float(
        df,
        "high",
        0,
    )

    low_0 = _series_tail_float(
        df,
        "low",
        0,
    )

    open_0 = _series_tail_float(
        df,
        "open",
        0,
    )

    atr = _atr_proxy(
        df
    )

    delta_1 = (
        close_0 - close_1
        if (
            close_0 is not None
            and close_1 is not None
        )
        else None
    )

    delta_3 = (
        close_0 - close_3
        if (
            close_0 is not None
            and close_3 is not None
        )
        else None
    )

    delta_8 = (
        close_0 - close_8
        if (
            close_0 is not None
            and close_8 is not None
        )
        else None
    )

    if (
        delta_3 is not None
        and delta_8 is not None
    ):
        if (
            delta_3 > 0
            and delta_8 > 0
        ):
            momentum_shape = (
                "BULLISH_BROAD"
            )

        elif (
            delta_3 < 0
            and delta_8 < 0
        ):
            momentum_shape = (
                "BEARISH_BROAD"
            )

        elif (
            delta_3 == 0
            and delta_8 == 0
        ):
            momentum_shape = (
                "FLAT"
            )

        else:
            momentum_shape = (
                "CORRECTION_OR_TRANSITION"
            )

    else:
        momentum_shape = "UNKNOWN"

    if (
        momentum_shape
        == "BULLISH_BROAD"
    ):
        momentum_direction = "BUY"

    elif (
        momentum_shape
        == "BEARISH_BROAD"
    ):
        momentum_direction = "SELL"

    else:
        momentum_direction = (
            "UNKNOWN"
        )

    momentum_relation = (
        _direction_relation(
            signal,
            momentum_direction,
            aligned_label=(
                "WITH_PRICE_MOMENTUM"
            ),
            counter_label=(
                "COUNTER_PRICE_MOMENTUM"
            ),
        )
    )

    candle_body = (
        close_0 - open_0
        if (
            close_0 is not None
            and open_0 is not None
        )
        else None
    )

    candle_range = (
        high_0 - low_0
        if (
            high_0 is not None
            and low_0 is not None
        )
        else None
    )

    return {
        "close_now": close_0,
        "close_1_bar_ago": close_1,
        "close_3_bars_ago": close_3,
        "close_8_bars_ago": close_8,

        "delta_1": delta_1,
        "delta_3": delta_3,
        "delta_8": delta_8,

        "atr_proxy": atr,

        "delta_1_atr": _normalized(
            delta_1,
            atr,
        ),
        "delta_3_atr": _normalized(
            delta_3,
            atr,
        ),
        "delta_8_atr": _normalized(
            delta_8,
            atr,
        ),

        "last_candle_body": (
            candle_body
        ),
        "last_candle_range": (
            candle_range
        ),

        "last_candle_body_atr": (
            _normalized(
                candle_body,
                atr,
            )
        ),

        "last_candle_range_atr": (
            _normalized(
                candle_range,
                atr,
            )
        ),

        "momentum_shape": (
            momentum_shape
        ),

        "momentum_relation": (
            momentum_relation
        ),
    }


def build_intrabar_context_snapshot(
    *,
    df,
    source,
    event,
    strategy,
    setup_id,
    signal,
    entry_model=None,
    session=None,
    execution_market_condition=None,
    observed_market_condition=None,
    signal_data=None,
    trade_plan=None,
    m15_bias=None,
    htf_context=None,
    extra_context=None,
):
    strategy = _safe_text(
        strategy
    ).upper()

    if (
        strategy
        not in
        INTRABAR_CONTEXT_OBSERVER_STRATEGIES
    ):
        return None

    signal_data = (
        signal_data
        if isinstance(
            signal_data,
            dict,
        )
        else {}
    )

    trade_plan = (
        trade_plan
        if isinstance(
            trade_plan,
            dict,
        )
        else {}
    )

    htf_context = (
        htf_context
        if isinstance(
            htf_context,
            dict,
        )
        else {}
    )

    signal = _normalize_direction(
        signal
    )

    normalized_m15 = (
        _normalize_direction(
            m15_bias
        )
    )

    normalized_htf = (
        _normalize_direction(
            htf_context.get(
                "bias"
            )
        )
    )

    entry = _safe_float(
        trade_plan.get(
            "entry_price"
        )
    )

    sl = _safe_float(
        trade_plan.get(
            "stop_loss"
        )
    )

    tp = _safe_float(
        trade_plan.get(
            "take_profit"
        )
    )

    risk_distance = (
        abs(entry - sl)
        if (
            entry is not None
            and sl is not None
            and entry != sl
        )
        else None
    )

    planned_rr = (
        abs(tp - entry)
        / risk_distance
        if (
            tp is not None
            and entry is not None
            and risk_distance
        )
        else None
    )

    market_condition = (
        _safe_text(
            observed_market_condition,
            _safe_text(
                execution_market_condition,
                "UNKNOWN",
            ),
        )
        .upper()
    )

    price_features = (
        _price_features(
            df,
            signal,
        )
    )

    return {
        "schema_version": (
            SCHEMA_VERSION
        ),

        "observed_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "record_type": (
            "INTRABAR_EXECUTION_CONTEXT"
        ),

        "source": (
            _safe_text(
                source,
                "UNKNOWN",
            ).upper()
        ),

        "event": (
            _safe_text(
                event,
                "UNKNOWN",
            ).upper()
        ),

        "setup_id": (
            _safe_text(
                setup_id
            )
        ),

        "strategy": strategy,

        "signal": signal,

        "entry_model": (
            _safe_text(
                entry_model,
                "UNKNOWN",
            ).upper()
        ),

        "session": (
            _safe_text(
                session,
                "UNKNOWN",
            ).upper()
        ),

        "execution_market_condition": (
            _safe_text(
                execution_market_condition,
                "UNKNOWN",
            ).upper()
        ),

        "market_condition": (
            market_condition
        ),

        "regime_family": (
            _regime_family(
                market_condition
            )
        ),

        "m15_bias": (
            normalized_m15
        ),

        "m15_relation": (
            _direction_relation(
                signal,
                normalized_m15,
                aligned_label=(
                    "WITH_M15"
                ),
                counter_label=(
                    "COUNTER_M15"
                ),
            )
        ),

        "htf_bias": (
            normalized_htf
        ),

        "htf_relation": (
            _direction_relation(
                signal,
                normalized_htf,
                aligned_label=(
                    "WITH_HTF"
                ),
                counter_label=(
                    "COUNTER_HTF"
                ),
            )
        ),

        "entry": entry,
        "sl": sl,
        "tp": tp,

        "risk_distance": (
            risk_distance
        ),

        "planned_rr": (
            round(
                planned_rr,
                6,
            )
            if planned_rr
            is not None
            else None
        ),

        "price_features": (
            price_features
        ),

        "strategy_context": {
            "momentum": (
                _json_safe(
                    signal_data.get(
                        "momentum"
                    )
                )
            ),

            "direction_context": (
                _json_safe(
                    signal_data.get(
                        "direction_context"
                    )
                )
            ),

            "smc_reasons": (
                _json_safe(
                    signal_data.get(
                        "smc_reasons"
                    )
                    or signal_data.get(
                        "smc"
                    )
                )
            ),

            "reason": (
                _json_safe(
                    signal_data.get(
                        "reason"
                    )
                    or trade_plan.get(
                        "reason"
                    )
                )
            ),

            "m15_direction_lock_status": (
                _json_safe(
                    trade_plan.get(
                        "m15_direction_lock_status"
                    )
                )
            ),

            "m15_direction_lock_signal": (
                _json_safe(
                    trade_plan.get(
                        "m15_direction_lock_signal"
                    )
                )
            ),
        },

        "extra_context": (
            _json_safe(
                extra_context or {}
            )
        ),
    }


def log_intrabar_context_observation(
    snapshot,
    *,
    file_path=None,
):
    if not isinstance(
        snapshot,
        dict,
    ):
        return False

    try:
        path = (
            Path(file_path)
            if file_path
            is not None
            else Path(
                get_account_file(
                    OBSERVATION_FILENAME
                )
            )
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = _json_safe(
            snapshot
        )

        with path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

        logger.info(
            "[INTRABAR CONTEXT OBSERVER] "
            f"saved | "
            f"setup_id="
            f"{snapshot.get('setup_id')} "
            f"strategy="
            f"{snapshot.get('strategy')} "
            f"source="
            f"{snapshot.get('source')}"
        )

        return True

    except Exception as exc:
        # Research instrumentation must never
        # interfere with order execution.
        logger.warning(
            "[INTRABAR CONTEXT OBSERVER] "
            f"failed open: {exc}"
        )

        return False
