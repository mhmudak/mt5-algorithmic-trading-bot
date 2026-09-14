from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.live_bias import (
    MIN_DIRECTIONAL_COVERAGE,
    MIN_VALID_TIMEFRAMES,
    classify_timeframe_bias,
    combine_live_bias,
    get_live_bias_weights,
)


ROOT = Path(__file__).resolve().parents[1]


def _trend_frame(
    direction,
    count=90,
):
    if direction == "UP":
        closes = [
            100.0 + index * 0.50
            for index in range(count)
        ]
    else:
        closes = [
            150.0 - index * 0.50
            for index in range(count)
        ]

    rows = []

    for close in closes:
        rows.append(
            {
                "open": close,
                "high": close + 0.50,
                "low": close - 0.50,
                "close": close,
            }
        )

    return pd.DataFrame(rows)


def _state(score, bias):
    return {
        "score": score,
        "bias": bias,
    }


def _unknown():
    return {
        "score": None,
        "bias": "UNKNOWN",
    }


def test_timeframe_classifier():
    bullish = classify_timeframe_bias(
        _trend_frame("UP")
    )

    bearish = classify_timeframe_bias(
        _trend_frame("DOWN")
    )

    assert bullish["bias"] == "BULLISH"
    assert bullish["score"] > 0

    assert bearish["bias"] == "BEARISH"
    assert bearish["score"] < 0


def test_coverage_policy():
    assert MIN_DIRECTIONAL_COVERAGE == 0.70
    assert MIN_VALID_TIMEFRAMES == 2


def test_trending_weights():
    assert get_live_bias_weights(
        "TRENDING"
    ) == {
        "H1": 0.50,
        "M15": 0.30,
        "H4": 0.20,
    }


def test_pullback_weights():
    assert get_live_bias_weights(
        "PULLBACK_TREND"
    ) == {
        "H1": 0.45,
        "M15": 0.40,
        "H4": 0.15,
    }


def test_consolidation_weights():
    assert get_live_bias_weights(
        "CONSOLIDATION"
    ) == {
        "H1": 0.35,
        "M15": 0.50,
        "H4": 0.15,
    }


def test_ranging_weights():
    assert get_live_bias_weights(
        "RANGING"
    ) == {
        "H1": 0.40,
        "M15": 0.45,
        "H4": 0.15,
    }


def test_volatile_weights():
    assert get_live_bias_weights(
        "VOLATILE"
    ) == {
        "H1": 0.45,
        "M15": 0.40,
        "H4": 0.15,
    }


def test_default_weights():
    assert get_live_bias_weights(
        "UNKNOWN"
    ) == {
        "H1": 0.50,
        "M15": 0.35,
        "H4": 0.15,
    }


def test_pending_transition_uses_core_regime():
    assert get_live_bias_weights(
        "CONSOLIDATION -> BREAKOUT_UP_PENDING"
    ) == {
        "H1": 0.35,
        "M15": 0.50,
        "H4": 0.15,
    }


def test_bearish_live_direction():
    snapshot = combine_live_bias(
        {
            "M15": _state(
                -1.0,
                "BEARISH",
            ),
            "H1": _state(
                -1.0,
                "BEARISH",
            ),
            "H4": _state(
                1.0,
                "BULLISH",
            ),
        },
        "TRENDING",
    )

    assert snapshot["bias"] == "BEARISH"
    assert snapshot["score"] < -0.50
    assert snapshot["coverage"] == 100
    assert (
        snapshot["directional_strength"]
        > 50
    )


def test_conflict_reduces_strength():
    snapshot = combine_live_bias(
        {
            "M15": _state(
                -1.0,
                "BEARISH",
            ),
            "H1": _state(
                1.0,
                "BULLISH",
            ),
            "H4": _state(
                -1.0,
                "BEARISH",
            ),
        },
        "TRENDING",
    )

    assert snapshot["bias"] == "MIXED"

    assert (
        snapshot["directional_strength"]
        <= 15
    )

    assert snapshot["coverage"] == 100


def test_missing_h4_still_sufficient():
    snapshot = combine_live_bias(
        {
            "M15": _state(
                -1.0,
                "BEARISH",
            ),
            "H1": _state(
                -1.0,
                "BEARISH",
            ),
            "H4": _unknown(),
        },
        "TRENDING",
    )

    assert snapshot["bias"] == "BEARISH"
    assert snapshot["coverage"] == 80
    assert snapshot["valid_timeframes"] == 2


def test_weak_coverage_suppresses_direction():
    snapshot = combine_live_bias(
        {
            "M15": _state(
                -1.0,
                "BEARISH",
            ),
            "H1": _unknown(),
            "H4": _state(
                -1.0,
                "BEARISH",
            ),
        },
        "TRENDING",
    )

    # M15 30 + H4 20 = only 50% coverage.
    assert snapshot["coverage"] == 50
    assert snapshot["bias"] == "UNKNOWN"
    assert snapshot["score"] is None

    assert (
        snapshot["reason"]
        == "insufficient_timeframe_coverage"
    )


def test_one_timeframe_cannot_publish_direction():
    snapshot = combine_live_bias(
        {
            "M15": _unknown(),
            "H1": _state(
                1.0,
                "BULLISH",
            ),
            "H4": _unknown(),
        },
        "TRENDING",
    )

    assert snapshot["bias"] == "UNKNOWN"
    assert snapshot["valid_timeframes"] == 1


def test_directional_strength_is_not_confidence():
    snapshot = combine_live_bias(
        {
            "M15": _state(
                -1.0,
                "BEARISH",
            ),
            "H1": _state(
                -1.0,
                "BEARISH",
            ),
            "H4": _state(
                1.0,
                "BULLISH",
            ),
        },
        "TRENDING",
    )

    assert "directional_strength" in snapshot
    assert "confidence" not in snapshot


def test_zero_authority():
    snapshot = combine_live_bias(
        {
            "M15": _state(
                -1.0,
                "BEARISH",
            ),
            "H1": _state(
                -1.0,
                "BEARISH",
            ),
            "H4": _state(
                -1.0,
                "BEARISH",
            ),
        },
        "TRENDING",
    )

    assert (
        snapshot["decision_impact"]
        == "DISPLAY_ONLY"
    )

    assert snapshot["can_execute"] is False
    assert snapshot["can_block_trade"] is False
    assert snapshot["can_modify_risk"] is False

    assert (
        snapshot[
            "can_modify_entry_sl_tp"
        ]
        is False
    )


def test_heartbeat_semantics():
    text = (
        ROOT
        / "src"
        / "health_monitor.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "Live Bias:" in text
    assert "Directional Strength:" in text
    assert "Live TF:" in text
    assert "Data Coverage:" in text
    assert "HTF Outlook:" in text

    assert "Confidence:" not in text

    assert (
        'f"Bias: {bias}\\n"'
        not in text
    )


def test_execution_not_connected():
    live_bot = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "get_live_bias_snapshot"
        not in live_bot
    )

    assert (
        "from src.live_bias"
        not in live_bot
    )


def test_fixed_lot_unchanged():
    settings = (
        ROOT
        / "config"
        / "settings.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "FIXED_LOT = 0.25"
        in settings
    )


def main():
    test_timeframe_classifier()
    test_coverage_policy()

    test_trending_weights()
    test_pullback_weights()
    test_consolidation_weights()
    test_ranging_weights()
    test_volatile_weights()
    test_default_weights()
    test_pending_transition_uses_core_regime()

    test_bearish_live_direction()
    test_conflict_reduces_strength()
    test_missing_h4_still_sufficient()
    test_weak_coverage_suppresses_direction()
    test_one_timeframe_cannot_publish_direction()
    test_directional_strength_is_not_confidence()

    test_zero_authority()
    test_heartbeat_semantics()
    test_execution_not_connected()
    test_fixed_lot_unchanged()

    print("PASS: Live Bias V1.1")
    print(
        "PASS: regime-aware H1/M15/H4 weighting"
    )
    print(
        "PASS: 70% minimum weighted coverage"
    )
    print(
        "PASS: at least 2 valid timeframes required"
    )
    print(
        "PASS: incomplete evidence suppresses "
        "directional label"
    )
    print(
        "PASS: Directional Strength is not "
        "presented as probability/confidence"
    )
    print(
        "PASS: heartbeat exposes timeframe states"
    )
    print(
        "PASS: heartbeat exposes data coverage"
    )
    print(
        "PASS: Live Bias remains DISPLAY_ONLY"
    )
    print(
        "PASS: no live_bot integration"
    )
    print(
        "PASS: FIXED_LOT unchanged"
    )


if __name__ == "__main__":
    main()
