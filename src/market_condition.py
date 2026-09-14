from src.logger import logger


_LAST_MARKET_CONDITION = "UNKNOWN"
_LAST_MARKET_TRANSITION = "NONE"
_LAST_CONSOLIDATION_CONTEXT = None


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _set_market_condition(condition, log_message):
    global _LAST_MARKET_CONDITION
    global _LAST_MARKET_TRANSITION
    global _LAST_CONSOLIDATION_CONTEXT

    condition = str(
        condition or "UNKNOWN"
    ).upper()

    _LAST_MARKET_CONDITION = condition

    # Once the closed-candle classifier confirms that the
    # market has left consolidation, any previous pending
    # consolidation transition is obsolete.
    if condition != "CONSOLIDATION":
        _LAST_MARKET_TRANSITION = "NONE"
        _LAST_CONSOLIDATION_CONTEXT = None

    logger.info(log_message)

    return _LAST_MARKET_CONDITION


def get_last_market_condition(default="UNKNOWN"):
    value = str(
        _LAST_MARKET_CONDITION or default
    ).upper()

    return value if value else str(default).upper()


def get_last_market_transition(default="NONE"):
    value = str(
        _LAST_MARKET_TRANSITION or default
    ).upper()

    return value if value else str(default).upper()


def get_market_condition_display(default="UNKNOWN"):
    """
    Human-readable live regime status.

    The core market condition remains closed-candle based.
    A pending transition is observation-only and may appear
    intrabar before the core regime is reclassified.
    """

    core = get_last_market_condition(
        default
    )

    transition = get_last_market_transition(
        "NONE"
    )

    if (
        core == "CONSOLIDATION"
        and transition
        in {
            "BREAKOUT_UP_PENDING",
            "BREAKOUT_DOWN_PENDING",
        }
    ):
        return (
            f"{core} -> {transition}"
        )

    return core


def _count_ema_crosses(
    close_series,
    ema_series,
):
    crosses = 0
    previous_sign = 0

    for close_value, ema_value in zip(
        close_series,
        ema_series,
    ):
        difference = (
            _safe_float(close_value)
            - _safe_float(ema_value)
        )

        if difference > 0:
            sign = 1
        elif difference < 0:
            sign = -1
        else:
            sign = 0

        if (
            sign != 0
            and previous_sign != 0
            and sign != previous_sign
        ):
            crosses += 1

        if sign != 0:
            previous_sign = sign

    return crosses


def _consolidation_metrics(
    df,
    *,
    atr,
    ema_slope,
):
    """
    Detect a compressed rotational auction.

    Required characteristics:
    - compact total range relative to ATR
    - relatively flat EMA structure
    - low directional efficiency
    - repeated value rotation or ATR compression
    """

    closed = df.iloc[:-1]

    if len(closed) < 20:
        return None

    recent = closed.iloc[-14:]

    if len(recent) < 10:
        return None

    required_columns = {
        "high",
        "low",
        "close",
        "ema_20",
        "atr_14",
    }

    if not required_columns.issubset(
        set(recent.columns)
    ):
        return None

    range_high = _safe_float(
        recent["high"].max()
    )

    range_low = _safe_float(
        recent["low"].min()
    )

    range_size = max(
        0.0,
        range_high - range_low,
    )

    range_atr_ratio = (
        range_size / atr
        if atr > 0
        else 999.0
    )

    closes = recent[
        "close"
    ].astype(float)

    path_length = float(
        closes.diff()
        .abs()
        .dropna()
        .sum()
    )

    net_move = abs(
        _safe_float(
            closes.iloc[-1]
        )
        - _safe_float(
            closes.iloc[0]
        )
    )

    if path_length > 0:
        directional_efficiency = (
            net_move
            / path_length
        )
    else:
        directional_efficiency = 0.0

    ema_slope_atr_ratio = (
        abs(float(ema_slope)) / atr
        if atr > 0
        else 999.0
    )

    ema_crosses = _count_ema_crosses(
        recent["close"],
        recent["ema_20"],
    )

    older = closed.iloc[:-14]

    baseline_atr = 0.0

    if len(older) >= 8:
        older_atr = (
            older["atr_14"]
            .dropna()
            .astype(float)
            .iloc[-20:]
        )

        if len(older_atr):
            baseline_atr = _safe_float(
                older_atr.median()
            )

    atr_compression_ratio = (
        atr / baseline_atr
        if baseline_atr > 0
        else 1.0
    )

    compact_range = (
        range_atr_ratio <= 3.50
    )

    flat_ema = (
        ema_slope_atr_ratio <= 0.16
    )

    low_directional_efficiency = (
        directional_efficiency <= 0.35
    )

    rotational = (
        ema_crosses >= 2
    )

    atr_compressed = (
        atr_compression_ratio <= 0.95
    )

    is_consolidation = (
        compact_range
        and flat_ema
        and low_directional_efficiency
        and (
            rotational
            or atr_compressed
        )
    )

    return {
        "is_consolidation": bool(
            is_consolidation
        ),
        "range_high": range_high,
        "range_low": range_low,
        "range_size": range_size,
        "range_atr_ratio": range_atr_ratio,
        "ema_slope_atr_ratio": (
            ema_slope_atr_ratio
        ),
        "directional_efficiency": (
            directional_efficiency
        ),
        "ema_crosses": ema_crosses,
        "atr_compression_ratio": (
            atr_compression_ratio
        ),
        "compact_range": compact_range,
        "flat_ema": flat_ema,
        "low_directional_efficiency": (
            low_directional_efficiency
        ),
        "rotational": rotational,
        "atr_compressed": atr_compressed,
    }


def _remember_consolidation_context(
    metrics,
    *,
    atr,
):
    """
    Save the most recently confirmed consolidation box so
    the normal every-loop process can observe a live escape
    without changing execution authority.
    """

    global _LAST_CONSOLIDATION_CONTEXT
    global _LAST_MARKET_TRANSITION

    if not metrics:
        return

    breakout_buffer = max(
        0.30,
        float(atr) * 0.15,
    )

    new_context = {
        "range_high": _safe_float(
            metrics.get("range_high")
        ),
        "range_low": _safe_float(
            metrics.get("range_low")
        ),
        "range_size": _safe_float(
            metrics.get("range_size")
        ),
        "atr": _safe_float(atr),
        "breakout_buffer": (
            breakout_buffer
        ),
    }

    # detect_market_condition() can legitimately be called more
    # than once while the same closed M15 candle remains active.
    #
    # Do not erase a live BREAKOUT_*_PENDING transition merely
    # because the identical confirmed consolidation box was
    # recalculated again.
    #
    # A genuinely changed closed-candle box starts a fresh
    # transition observation window.
    if (
        _LAST_CONSOLIDATION_CONTEXT
        != new_context
    ):
        _LAST_MARKET_TRANSITION = "NONE"

    _LAST_CONSOLIDATION_CONTEXT = new_context


def get_last_consolidation_context():
    if not _LAST_CONSOLIDATION_CONTEXT:
        return None

    return dict(
        _LAST_CONSOLIDATION_CONTEXT
    )


def observe_intrabar_market_transition(
    current_price,
):
    """
    Observe a live escape from the last confirmed
    consolidation box.

    IMPORTANT:
    - This does NOT reclassify the closed-candle core regime.
    - This does NOT authorize a trade.
    - This does NOT alter risk, position sizing, SL or TP.
    - It only exposes a fast transition state.

    The next normal closed-candle classification remains the
    authority for switching the main strategy map.
    """

    global _LAST_MARKET_TRANSITION

    core = get_last_market_condition()

    context = (
        _LAST_CONSOLIDATION_CONTEXT
    )

    if (
        core != "CONSOLIDATION"
        or not context
    ):
        _LAST_MARKET_TRANSITION = "NONE"

        return {
            "core_condition": core,
            "transition": "NONE",
            "display": core,
            "range_high": None,
            "range_low": None,
            "breakout_buffer": None,
        }

    price = _safe_float(
        current_price,
        default=float("nan"),
    )

    range_high = _safe_float(
        context["range_high"]
    )

    range_low = _safe_float(
        context["range_low"]
    )

    breakout_buffer = _safe_float(
        context["breakout_buffer"]
    )

    previous = _LAST_MARKET_TRANSITION

    if price >= (
        range_high
        + breakout_buffer
    ):
        transition = (
            "BREAKOUT_UP_PENDING"
        )

    elif price <= (
        range_low
        - breakout_buffer
    ):
        transition = (
            "BREAKOUT_DOWN_PENDING"
        )

    else:
        transition = "NONE"

    _LAST_MARKET_TRANSITION = (
        transition
    )

    if transition != previous:
        if transition == "NONE":
            logger.info(
                "[MARKET TRANSITION] "
                "Pending consolidation breakout "
                "cancelled/reclaimed | "
                f"price={price:.2f} "
                f"range={range_low:.2f}-"
                f"{range_high:.2f}"
            )

        else:
            logger.info(
                "[MARKET TRANSITION] "
                f"{transition} | "
                f"price={price:.2f} "
                f"range={range_low:.2f}-"
                f"{range_high:.2f} "
                f"buffer={breakout_buffer:.2f}"
            )

    display = get_market_condition_display()

    return {
        "core_condition": core,
        "transition": transition,
        "display": display,
        "range_high": range_high,
        "range_low": range_low,
        "breakout_buffer": (
            breakout_buffer
        ),
    }


def detect_market_condition(df):
    if len(df) < 20:
        return _set_market_condition(
            "RANGING",
            "[MARKET] Not enough data, "
            "defaulting to RANGING",
        )

    # Closed candles only for the authoritative regime.
    last = df.iloc[-2]
    prev = df.iloc[-3]

    atr = _safe_float(
        last["atr_14"]
    )

    prev_atr = _safe_float(
        prev["atr_14"]
    )

    ema = _safe_float(
        last["ema_20"]
    )

    price = _safe_float(
        last["close"]
    )

    if atr <= 0:
        return _set_market_condition(
            "RANGING",
            "[MARKET] Invalid ATR, "
            "defaulting to RANGING",
        )

    # =========================
    # VOLATILE
    # =========================
    if (
        prev_atr > 0
        and atr > prev_atr * 1.7
    ):
        return _set_market_condition(
            "VOLATILE",
            "[MARKET] VOLATILE detected",
        )

    ema_now = _safe_float(
        df["ema_20"].iloc[-2]
    )

    ema_past = _safe_float(
        df["ema_20"].iloc[-8]
    )

    ema_slope = (
        ema_now - ema_past
    )

    distance_from_ema = abs(
        price - ema
    )

    # =========================
    # CONSOLIDATION
    # =========================
    consolidation = (
        _consolidation_metrics(
            df,
            atr=atr,
            ema_slope=ema_slope,
        )
    )

    if (
        consolidation
        and consolidation[
            "is_consolidation"
        ]
    ):
        _remember_consolidation_context(
            consolidation,
            atr=atr,
        )

        return _set_market_condition(
            "CONSOLIDATION",
            (
                "[MARKET] CONSOLIDATION detected | "
                f"range_atr="
                f"{consolidation['range_atr_ratio']:.2f} "
                f"efficiency="
                f"{consolidation['directional_efficiency']:.2f} "
                f"ema_slope_atr="
                f"{consolidation['ema_slope_atr_ratio']:.2f} "
                f"ema_crosses="
                f"{consolidation['ema_crosses']} "
                f"atr_ratio="
                f"{consolidation['atr_compression_ratio']:.2f}"
            ),
        )

    # =========================
    # TRENDING
    # =========================
    if (
        distance_from_ema > atr * 1.2
        and abs(ema_slope) > atr * 0.25
    ):
        return _set_market_condition(
            "TRENDING",
            "[MARKET] TRENDING detected",
        )

    # =========================
    # PULLBACK TREND
    # =========================
    if (
        abs(ema_slope) > atr * 0.20
        and distance_from_ema <= atr * 0.90
    ):
        return _set_market_condition(
            "PULLBACK_TREND",
            "[MARKET] PULLBACK_TREND detected",
        )

    # =========================
    # NORMAL RANGE
    # =========================
    return _set_market_condition(
        "RANGING",
        "[MARKET] RANGING detected",
    )
