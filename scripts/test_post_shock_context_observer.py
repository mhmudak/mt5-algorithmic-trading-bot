from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from config import settings

from src.post_shock_context import (
    build_post_shock_context,
)


def _m15(
    shock_position=None,
):
    start = pd.Timestamp(
        "2026-09-07 15:00:00"
    )

    rows = []

    for index in range(7):
        row = {
            "time": (
                start
                + pd.Timedelta(
                    minutes=15 * index
                )
            ),
            "open": 4400.0,
            "high": 4407.0,
            "low": 4397.0,
            "close": 4402.0,
            "atr_14": 15.0,
        }

        if index == shock_position:
            row.update(
                {
                    "open": 4470.0,
                    "high": 4480.0,
                    "low": 4385.0,
                    "close": 4390.0,
                }
            )

        rows.append(row)

    # Final row = forming M15.
    return pd.DataFrame(rows)


def _m5(
    normalized,
):
    start = pd.Timestamp(
        "2026-09-07 16:15:00"
    )

    if normalized:
        values = [
            (4390, 4396, 4388, 4394),
            (4394, 4402, 4392, 4398),
            (4398, 4400, 4391, 4393),
            (4393, 4397, 4390, 4395),
            (4395, 4398, 4392, 4396),
        ]

        atr = 8.0

    else:
        values = [
            (4390, 4425, 4380, 4415),
            (4415, 4440, 4395, 4400),
            (4400, 4430, 4370, 4380),
            (4380, 4415, 4365, 4405),
            (4405, 4435, 4380, 4390),
        ]

        atr = 10.0

    rows = []

    for index, (
        open_price,
        high,
        low,
        close,
    ) in enumerate(values):
        rows.append(
            {
                "time": (
                    start
                    + pd.Timedelta(
                        minutes=5
                        * index
                    )
                ),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "atr_14": atr,
            }
        )

    # Forming M5.
    rows.append(
        {
            "time": (
                start
                + pd.Timedelta(
                    minutes=25
                )
            ),
            "open": 4396.0,
            "high": 4399.0,
            "low": 4394.0,
            "close": 4397.0,
            "atr_14": atr,
        }
    )

    return pd.DataFrame(rows)


def _build(
    m15,
    m5=None,
    *,
    now,
):
    return build_post_shock_context(
        m15_df=m15,
        m5_df=m5,
        setup={
            "strategy": (
                "FAILED_FVG_REVERSAL"
            ),
            "entry_reference": 4390.57,
            "sl_reference": 4483.83,
        },
        now=now,
        enabled=True,
        m15_abs_range_price=(
            settings.
            POST_SHOCK_M15_ABS_RANGE_PRICE
        ),
        m15_range_atr_ratio=(
            settings.
            POST_SHOCK_M15_RANGE_ATR_RATIO
        ),
        m15_body_atr_ratio=(
            settings.
            POST_SHOCK_M15_BODY_ATR_RATIO
        ),
        lookback_m15_bars=(
            settings.
            POST_SHOCK_LOOKBACK_M15_BARS
        ),
        max_age_minutes=(
            settings.
            POST_SHOCK_MAX_AGE_MINUTES
        ),
        m5_min_closed_bars=(
            settings.
            POST_SHOCK_M5_MIN_CLOSED_BARS
        ),
        m5_normalized_bars=(
            settings.
            POST_SHOCK_M5_NORMALIZED_BARS
        ),
        m5_max_range_atr_ratio=(
            settings.
            POST_SHOCK_M5_MAX_RANGE_ATR_RATIO
        ),
        m5_max_body_atr_ratio=(
            settings.
            POST_SHOCK_M5_MAX_BODY_ATR_RATIO
        ),
    )


def test_normal_market():
    result = _build(
        _m15(),
        now=pd.Timestamp(
            "2026-09-07 16:30:00"
        ),
    )

    assert (
        result["state"]
        == "NORMAL"
    )

    assert (
        result[
            "recent_shock_detected"
        ]
        is False
    )


def test_shock_active_before_enough_m5():
    result = _build(
        _m15(
            shock_position=5
        ),
        None,
        now=pd.Timestamp(
            "2026-09-07 16:32:00"
        ),
    )

    assert (
        result["state"]
        == "SHOCK_ACTIVE"
    )

    assert (
        result[
            "active_post_shock_mode"
        ]
        is True
    )

    assert (
        result[
            "shock_range_price"
        ]
        == 95.0
    )

    assert (
        result[
            "setup_geometry"
        ][
            "stop_distance"
        ]
        == 93.26
    )


def test_post_shock_mode():
    result = _build(
        _m15(
            shock_position=4
        ),
        _m5(
            normalized=False
        ),
        now=pd.Timestamp(
            "2026-09-07 16:40:00"
        ),
    )

    assert (
        result["state"]
        == "POST_SHOCK_ENTRY_MODE"
    )

    assert (
        result[
            "active_post_shock_mode"
        ]
        is True
    )


def test_normalized_exit():
    result = _build(
        _m15(
            shock_position=4
        ),
        _m5(
            normalized=True
        ),
        now=pd.Timestamp(
            "2026-09-07 16:40:00"
        ),
    )

    assert (
        result["state"]
        == "NORMAL"
    )

    assert (
        result["exit_ready"]
        is True
    )

    assert (
        result[
            "m5_fresh_structure"
        ]
        is True
    )

    assert (
        result[
            "m5_volatility_normalized"
        ]
        is True
    )


def test_timeout_reclassification():
    result = _build(
        _m15(
            shock_position=1
        ),
        None,
        now=pd.Timestamp(
            "2026-09-07 17:00:00"
        ),
    )

    assert (
        result["state"]
        == "NORMAL"
    )

    assert (
        result["reason"]
        == (
            "post_shock_max_age_"
            "reclassification"
        )
    )


def test_integration_is_observer_only():
    live_source = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    risk_source = (
        ROOT
        / "src"
        / "risk.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    execution_source = (
        ROOT
        / "src"
        / "execution_engine.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "POST_SHOCK_CONTEXT_OBSERVATION"
        in live_source
    )

    assert (
        '"decision_impact": "NONE"'
        in live_source
    )

    assert (
        "post_shock_context"
        not in risk_source
    )

    assert (
        "post_shock_context"
        not in execution_source
    )

    # No state-based trading control yet.
    assert (
        "if post_shock_context"
        not in live_source
    )

    assert (
        'if selected_signal_data.get('
        '"post_shock_context"'
        not in live_source
    )


if __name__ == "__main__":
    test_normal_market()
    test_shock_active_before_enough_m5()
    test_post_shock_mode()
    test_normalized_exit()
    test_timeout_reclassification()
    test_integration_is_observer_only()

    print(
        "[PASS] Post-shock context observer "
        "classifies shock/normalization state "
        "without influencing trading."
    )
