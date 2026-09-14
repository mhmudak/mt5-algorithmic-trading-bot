from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.market_condition import (
    detect_market_condition,
    get_last_market_condition,
    get_last_market_transition,
    get_market_condition_display,
    get_last_consolidation_context,
    observe_intrabar_market_transition,
)


ROOT = Path(__file__).resolve().parents[1]


def _frame(
    closes,
    *,
    atr=1.4,
    ema_values=None,
    atr_values=None,
):
    closes = [
        float(value)
        for value in closes
    ]

    count = len(closes)

    if atr_values is None:
        atr_values = [
            float(atr)
            for _ in range(count)
        ]

    if ema_values is None:
        ema_values = (
            pd.Series(closes)
            .ewm(
                span=20,
                adjust=False,
            )
            .mean()
            .tolist()
        )

    rows = []

    for index, close in enumerate(closes):
        candle_atr = float(
            atr_values[index]
        )

        rows.append(
            {
                "open": close - 0.05,
                "high": (
                    close
                    + candle_atr * 0.30
                ),
                "low": (
                    close
                    - candle_atr * 0.30
                ),
                "close": close,
                "ema_20": float(
                    ema_values[index]
                ),
                "atr_14": candle_atr,
            }
        )

    return pd.DataFrame(rows)


def _consolidation_frame():
    pattern = [
        100.00,
        100.55,
        100.10,
        99.55,
        100.05,
        100.60,
        99.90,
        99.45,
        100.00,
        100.50,
        100.05,
        99.50,
        100.00,
        100.45,
    ]

    closes = (
        [100.0] * 30
        + pattern
        + pattern
    )

    ema_values = [
        100.0
        for _ in closes
    ]

    return _frame(
        closes,
        atr=1.4,
        ema_values=ema_values,
    )


def test_consolidation_detected():
    df = _consolidation_frame()

    result = detect_market_condition(
        df
    )

    assert result == "CONSOLIDATION"

    assert (
        get_last_market_condition()
        == "CONSOLIDATION"
    )

    context = (
        get_last_consolidation_context()
    )

    assert context is not None
    assert (
        context["range_high"]
        > context["range_low"]
    )

    assert (
        get_last_market_transition()
        == "NONE"
    )


def test_wider_sideways_is_still_ranging():
    wide_pattern = [
        100.0,
        104.0,
        97.0,
        103.0,
        96.5,
        102.5,
        97.5,
        103.5,
        98.0,
        102.0,
        97.0,
        103.0,
        98.5,
        101.0,
    ]

    closes = (
        [100.0] * 30
        + wide_pattern
        + wide_pattern
    )

    ema_values = [
        100.0
        for _ in closes
    ]

    df = _frame(
        closes,
        atr=1.4,
        ema_values=ema_values,
    )

    assert (
        detect_market_condition(df)
        == "RANGING"
    )


def test_trending_is_preserved():
    closes = [
        100.0 + index * 0.80
        for index in range(60)
    ]

    ema_values = [
        close - 2.0
        for close in closes
    ]

    df = _frame(
        closes,
        atr=1.0,
        ema_values=ema_values,
    )

    assert (
        detect_market_condition(df)
        == "TRENDING"
    )


def test_pullback_trend_is_preserved():
    ema_values = [
        100.0 + index * 0.45
        for index in range(60)
    ]

    closes = [
        ema + 0.20
        for ema in ema_values
    ]

    df = _frame(
        closes,
        atr=2.0,
        ema_values=ema_values,
    )

    assert (
        detect_market_condition(df)
        == "PULLBACK_TREND"
    )


def test_volatile_is_preserved():
    pattern = [
        100.0,
        100.4,
        99.9,
        100.3,
    ]

    closes = pattern * 15

    atr_values = [
        1.0
        for _ in closes
    ]

    atr_values[-3] = 1.0
    atr_values[-2] = 1.8

    ema_values = [
        100.0
        for _ in closes
    ]

    df = _frame(
        closes,
        atr_values=atr_values,
        ema_values=ema_values,
    )

    assert (
        detect_market_condition(df)
        == "VOLATILE"
    )


def test_intrabar_breakout_up_pending():
    df = _consolidation_frame()

    assert (
        detect_market_condition(df)
        == "CONSOLIDATION"
    )

    context = (
        get_last_consolidation_context()
    )

    price = (
        context["range_high"]
        + context["breakout_buffer"]
        + 0.10
    )

    status = (
        observe_intrabar_market_transition(
            price
        )
    )

    assert (
        status["transition"]
        == "BREAKOUT_UP_PENDING"
    )

    # Pending transition must not rewrite
    # the authoritative closed-candle regime.
    assert (
        get_last_market_condition()
        == "CONSOLIDATION"
    )

    assert (
        "BREAKOUT_UP_PENDING"
        in get_market_condition_display()
    )


def test_repeated_same_box_classification_preserves_pending():
    df = _consolidation_frame()

    assert (
        detect_market_condition(df)
        == "CONSOLIDATION"
    )

    context = (
        get_last_consolidation_context()
    )

    price = (
        context["range_high"]
        + context["breakout_buffer"]
        + 0.10
    )

    status = (
        observe_intrabar_market_transition(
            price
        )
    )

    assert (
        status["transition"]
        == "BREAKOUT_UP_PENDING"
    )

    # Re-running the closed-candle classifier against
    # the exact same confirmed box must not erase the
    # already-observed live transition.
    assert (
        detect_market_condition(df)
        == "CONSOLIDATION"
    )

    assert (
        get_last_market_transition()
        == "BREAKOUT_UP_PENDING"
    )

    assert (
        "BREAKOUT_UP_PENDING"
        in get_market_condition_display()
    )


def test_changed_consolidation_box_resets_pending():
    df = _consolidation_frame()

    assert (
        detect_market_condition(df)
        == "CONSOLIDATION"
    )

    context = (
        get_last_consolidation_context()
    )

    observe_intrabar_market_transition(
        context["range_high"]
        + context["breakout_buffer"]
        + 0.10
    )

    assert (
        get_last_market_transition()
        == "BREAKOUT_UP_PENDING"
    )

    shifted = df.copy()

    # Shift exactly the recent closed-candle
    # consolidation window so it remains
    # consolidation but represents a new box.
    recent_closed_index = (
        shifted.index[-15:-1]
    )

    for column in (
        "open",
        "high",
        "low",
        "close",
    ):
        shifted.loc[
            recent_closed_index,
            column,
        ] = (
            shifted.loc[
                recent_closed_index,
                column,
            ]
            + 0.20
        )

    assert (
        detect_market_condition(
            shifted
        )
        == "CONSOLIDATION"
    )

    assert (
        get_last_market_transition()
        == "NONE"
    )


def test_intrabar_breakout_down_pending():
    df = _consolidation_frame()

    detect_market_condition(df)

    context = (
        get_last_consolidation_context()
    )

    price = (
        context["range_low"]
        - context["breakout_buffer"]
        - 0.10
    )

    status = (
        observe_intrabar_market_transition(
            price
        )
    )

    assert (
        status["transition"]
        == "BREAKOUT_DOWN_PENDING"
    )


def test_failed_breakout_reclaims_box():
    df = _consolidation_frame()

    detect_market_condition(df)

    context = (
        get_last_consolidation_context()
    )

    observe_intrabar_market_transition(
        context["range_high"]
        + context["breakout_buffer"]
        + 0.10
    )

    inside_price = (
        context["range_low"]
        + context["range_high"]
    ) / 2.0

    status = (
        observe_intrabar_market_transition(
            inside_price
        )
    )

    assert status["transition"] == "NONE"

    assert (
        get_market_condition_display()
        == "CONSOLIDATION"
    )


def test_confirmed_new_regime_clears_pending():
    df = _consolidation_frame()

    detect_market_condition(df)

    context = (
        get_last_consolidation_context()
    )

    observe_intrabar_market_transition(
        context["range_high"]
        + context["breakout_buffer"]
        + 0.10
    )

    closes = [
        100.0 + index * 0.80
        for index in range(60)
    ]

    ema_values = [
        close - 2.0
        for close in closes
    ]

    trend_df = _frame(
        closes,
        atr=1.0,
        ema_values=ema_values,
    )

    assert (
        detect_market_condition(
            trend_df
        )
        == "TRENDING"
    )

    assert (
        get_last_market_transition()
        == "NONE"
    )

    assert (
        get_market_condition_display()
        == "TRENDING"
    )


def test_live_strategy_routing():
    text = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8"
    )

    start_marker = (
        '    elif market_condition '
        '== "CONSOLIDATION":\n'
    )

    end_marker = (
        '    elif market_condition '
        '== "RANGING":\n'
    )

    assert text.count(start_marker) == 1
    assert text.count(end_marker) == 1

    start = text.index(start_marker)
    end = text.index(
        end_marker,
        start,
    )

    branch = text[start:end]

    expected = {
        "BALANCED_AUCTION_RANGE",
        "RANGE_SWEEP_RECLAIM",
        "VWAP_RANGE_MEAN_REVERSION",
        "CRT_TBS",
        "LIQUIDITY_TRAP",
        "LIQUIDITY_SWEEP",
        "MICRO_SR_SWEEP_RECLAIM",
        "FAILED_BREAKOUT_REVERSAL",
        "FAILED_FVG_REVERSAL",
        "FRACTAL_SWEEP",
        "VWAP_RECLAIM",
    }

    for strategy in expected:
        assert strategy in branch, strategy

    # Intentionally excluded from tight
    # consolidation core.
    excluded = {
        "ORB",
        "ORB_V00",
        "HTF_TREND_PULLBACK",
        "WAVETREND_MOMENTUM",
        "EXTREME_SWEEP_RECLAIM",
    }

    for strategy in excluded:
        assert strategy not in branch, strategy


def test_intrabar_transition_is_observation_only():
    text = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "observe_intrabar_market_transition"
        in text
    )

    observer_call = text.index(
        "transition_status = (\n"
        "            observe_intrabar_market_transition("
    )

    intrabar_toggle = text.index(
        "if ENABLE_INTRABAR_ENGINE "
        "and ENABLE_INTRABAR_PRICE_EVENT_DETECTOR:"
    )

    # Regime-transition observation must remain
    # independent of intrabar execution toggles.
    assert observer_call < intrabar_toggle

    assert (
        "observer failed open"
        in text
    )

    assert (
        'intrabar_market_condition = '
        '"INTRABAR_PENDING"'
        in text
    )

    # The live transition display must remain
    # observational and must not become the
    # intrabar execution market_condition.
    assert (
        "intrabar_market_condition = (\n"
        "            live_market_condition_display"
        not in text
    )

    assert (
        "market_condition=intrabar_market_condition"
        in text
    )

    assert (
        'if market_condition in {\n'
        '        "RANGING",\n'
        '        "CONSOLIDATION",'
        in text
    )

    # Existing Phase 6U allowlist must remain
    # untouched by this feature.
    settings = (
        ROOT
        / "config"
        / "settings.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "ENABLE_INTRABAR_STRATEGY_ALLOWLIST = True"
        in settings
    )

    assert (
        '"AUTO_STRUCTURAL_LEVEL_SCALP",'
        in settings
    )

    assert (
        '"FAILED_FVG_REVERSAL",'
        in settings
    )


def test_heartbeat_reports_transition():
    text = (
        ROOT
        / "src"
        / "health_monitor.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "get_market_condition_display"
        in text
    )

    assert (
        "Market Condition:"
        in text
    )


def test_settings_safety():
    text = (
        ROOT
        / "config"
        / "settings.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        '"CONSOLIDATION": +3,'
        in text
    )

    assert (
        "FIXED_LOT = 0.25"
        in text
    )


def main():
    test_consolidation_detected()
    test_wider_sideways_is_still_ranging()
    test_trending_is_preserved()
    test_pullback_trend_is_preserved()
    test_volatile_is_preserved()

    test_intrabar_breakout_up_pending()
    test_repeated_same_box_classification_preserves_pending()
    test_changed_consolidation_box_resets_pending()
    test_intrabar_breakout_down_pending()
    test_failed_breakout_reclaims_box()
    test_confirmed_new_regime_clears_pending()

    test_live_strategy_routing()
    test_intrabar_transition_is_observation_only()
    test_heartbeat_reports_transition()
    test_settings_safety()

    print(
        "PASS: Consolidation Regime V1.3"
    )

    print(
        "PASS: refined consolidation "
        "strategy family"
    )

    print(
        "PASS: fast intrabar transition "
        "observer"
    )

    print(
        "PASS: transition observer "
        "independent of intrabar execution"
    )

    print(
        "PASS: repeated same-box detection "
        "preserves pending transition"
    )

    print(
        "PASS: pending breakout does not "
        "rewrite authoritative regime"
    )

    print(
        "PASS: failed breakout can reclaim "
        "back to consolidation"
    )

    print(
        "PASS: confirmed new regime clears "
        "pending transition"
    )

    print(
        "PASS: existing intrabar execution "
        "allowlist unchanged"
    )

    print(
        "PASS: transition display does not "
        "enter intrabar execution context"
    )

    print(
        "PASS: changed consolidation box "
        "resets pending transition"
    )

    print(
        "PASS: heartbeat reports live "
        "transition status"
    )

    print(
        "PASS: FIXED_LOT unchanged"
    )


if __name__ == "__main__":
    main()
