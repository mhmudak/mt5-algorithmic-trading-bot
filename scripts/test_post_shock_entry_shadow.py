from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from src.post_shock_entry_shadow import (
    build_post_shock_entry_shadow,
    build_post_shock_entry_shadow_fail_open,
)


def context(
    *,
    state,
    stop_distance,
    shock_range=95.0,
    active=True,
    m5_fresh_structure=False,
):
    return {
        "observer_only": True,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "state": state,
        "active_post_shock_mode": active,
        "shock_range_price": shock_range,
        "m5_fresh_structure": (
            m5_fresh_structure
        ),
        "setup_geometry": {
            "entry_reference": 4390.57,
            "sl_reference": (
                4390.57
                + stop_distance
            ),
            "stop_distance": stop_distance,
        },
    }


def setup():
    return {
        "strategy": (
            "FAILED_FVG_REVERSAL"
        ),
        "signal": "SELL",
        "entry_reference": 4390.57,
        "sl_reference": 4483.83,
    }




def buy_m1_pattern():
    return [
        {
            "time": (
                "2026-09-12T12:00:00+00:00"
            ),
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
        },
        {
            "time": (
                "2026-09-12T12:01:00+00:00"
            ),
            "open": 100.5,
            "high": 103.0,
            "low": 100.0,
            "close": 102.5,
        },
    ]


def sell_m1_pattern():
    return [
        {
            "time": (
                "2026-09-12T12:00:00+00:00"
            ),
            "open": 101.0,
            "high": 102.0,
            "low": 99.0,
            "close": 100.0,
        },
        {
            "time": (
                "2026-09-12T12:01:00+00:00"
            ),
            "open": 100.5,
            "high": 101.0,
            "low": 97.5,
            "close": 98.5,
        },
    ]


def neutral_m1_pattern():
    return [
        {
            "time": (
                "2026-09-12T12:00:00+00:00"
            ),
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
        },
        {
            "time": (
                "2026-09-12T12:01:00+00:00"
            ),
            "open": 101.0,
            "high": 101.5,
            "low": 100.5,
            "close": 101.0,
        },
    ]


def assert_observer_only(result):
    assert result["observer_only"] is True
    assert result["decision_impact"] == "NONE"

    assert (
        result["can_influence_decision"]
        is False
    )

    assert (
        result["safe_for_execution"]
        is False
    )

    assert (
        result["execution_allowed"]
        is False
    )

    plan = result[
        "shadow_plan"
    ]

    assert (
        plan["observer_only"]
        is True
    )

    assert (
        plan["decision_impact"]
        == "NONE"
    )

    assert (
        plan["safe_for_execution"]
        is False
    )

    assert (
        plan["execution_allowed"]
        is False
    )


def assert_shadow_plan_unconstructed(
    result,
):
    plan = result[
        "shadow_plan"
    ]

    assert (
        plan["status"]
        == "NOT_CONSTRUCTED"
    )

    assert (
        plan["entry_price"]
        is None
    )

    assert (
        plan["stop_loss"]
        is None
    )

    assert (
        plan["take_profit"]
        is None
    )

    assert (
        plan["risk_reward"]
        is None
    )

class ExplodingContext(dict):
    def get(
        self,
        key,
        default=None,
    ):
        raise RuntimeError(
            "forced_shadow_classifier_failure"
        )


def test_fail_open_wrapper_never_raises():
    result = (
        build_post_shock_entry_shadow_fail_open(
            post_shock_context=(
                ExplodingContext(
                    {
                        "state": (
                            "POST_SHOCK_ENTRY_MODE"
                        ),
                    }
                )
            ),
            setup=setup(),
            current_price=4390.57,
        )
    )

    assert_observer_only(result)

    assert (
        result["available"]
        is False
    )

    assert (
        result["state"]
        == "OBSERVER_ERROR"
    )

    assert (
        result["reason"]
        == "shadow_classifier_failed_open"
    )

    assert (
        result["shadow_candidate"]
        is False
    )

    assert (
        result["abnormal_stop_geometry"]
        is False
    )




def test_normal_geometry_is_untouched():
    result = build_post_shock_entry_shadow(
        post_shock_context=context(
            state="POST_SHOCK_ENTRY_MODE",
            stop_distance=20.0,
            m5_fresh_structure=True,
        ),
        setup=setup(),
        current_price=4390.57,
    )

    assert_observer_only(result)

    assert_shadow_plan_unconstructed(
        result
    )

    assert (
        result["state"]
        == "NORMAL_STOP_GEOMETRY"
    )

    assert (
        result["abnormal_stop_geometry"]
        is False
    )

    assert (
        result["shadow_candidate"]
        is False
    )

def test_shock_active_waits():
    result = build_post_shock_entry_shadow(
        post_shock_context=context(
            state="SHOCK_ACTIVE",
            stop_distance=93.26,
        ),
        setup=setup(),
        current_price=4390.57,
    )

    assert_observer_only(result)

    assert (
        result["state"]
        == "WAIT_POST_SHOCK_STRUCTURE"
    )

    assert (
        result["shadow_candidate"]
        is True
    )

    assert (
        result["abnormal_stop_geometry"]
        is True
    )


def test_post_shock_waits_for_m5():
    result = build_post_shock_entry_shadow(
        post_shock_context=context(
            state="POST_SHOCK_ENTRY_MODE",
            stop_distance=93.26,
            m5_fresh_structure=False,
        ),
        setup=setup(),
        current_price=4390.57,
    )

    assert_observer_only(result)

    assert (
        result["state"]
        == "WAIT_M5_STRUCTURE"
    )

    assert (
        result["shadow_candidate"]
        is True
    )



def test_fresh_m5_waits_for_m1_data():
    result = build_post_shock_entry_shadow(
        post_shock_context=context(
            state="POST_SHOCK_ENTRY_MODE",
            stop_distance=93.26,
            m5_fresh_structure=True,
        ),
        setup=setup(),
        current_price=4390.57,
    )

    assert_observer_only(result)

    assert_shadow_plan_unconstructed(
        result
    )

    assert (
        result["state"]
        == "WAIT_M1_DATA"
    )

    assert (
        result["shadow_candidate"]
        is True
    )

    assert (
        result["m1_observation"][
            "available"
        ]
        is False
    )

    ratio = result[
        "shock_scale_stop_ratio"
    ]

    assert ratio is not None
    assert ratio > 0.98
    assert ratio < 0.99


def test_buy_m1_retrace_reclaim_observed():
    buy_setup = setup()
    buy_setup["signal"] = "BUY"
    buy_setup["tp_reference"] = 110.0

    original_setup = dict(
        buy_setup
    )

    result = build_post_shock_entry_shadow(
        post_shock_context=context(
            state="POST_SHOCK_ENTRY_MODE",
            stop_distance=93.26,
            m5_fresh_structure=True,
        ),
        setup=buy_setup,
        current_price=4390.57,
        m1_closed_bars=(
            buy_m1_pattern()
        ),
    )

    assert_observer_only(result)

    observation = result[
        "m1_observation"
    ]

    assert (
        observation["available"]
        is True
    )

    assert (
        observation[
            "directional_pattern_observed"
        ]
        is True
    )

    assert (
        result["state"]
        == "SHADOW_LOCAL_PLAN_CONSTRUCTED"
    )

    plan = result[
        "shadow_plan"
    ]

    assert (
        plan["status"]
        == "HYPOTHETICAL_LOCAL_PLAN_CONSTRUCTED"
    )

    assert (
        plan["entry_price"]
        == 102.5
    )

    assert (
        plan["entry_source"]
        == "latest_closed_m1_close"
    )

    assert (
        plan["stop_loss"]
        == 99.0
    )

    assert (
        plan["stop_source"]
        == "two_closed_m1_bar_structure"
    )

    assert (
        plan["stop_distance"]
        == 3.5
    )

    assert (
        plan["take_profit"]
        == 110.0
    )

    assert (
        plan["target_source"]
        == "tp_reference"
    )

    assert (
        plan["target_valid_for_signal"]
        is True
    )

    assert (
        plan["risk_reward"]
        == 2.142857
    )

    assert (
        buy_setup
        == original_setup
    )


def test_sell_m1_retrace_reclaim_observed():
    sell_setup = setup()
    sell_setup["tp_reference"] = 90.0

    original_setup = dict(
        sell_setup
    )

    result = build_post_shock_entry_shadow(
        post_shock_context=context(
            state="POST_SHOCK_ENTRY_MODE",
            stop_distance=93.26,
            m5_fresh_structure=True,
        ),
        setup=sell_setup,
        current_price=4390.57,
        m1_closed_bars=(
            sell_m1_pattern()
        ),
    )

    assert_observer_only(result)

    observation = result[
        "m1_observation"
    ]

    assert (
        observation["available"]
        is True
    )

    assert (
        observation[
            "directional_pattern_observed"
        ]
        is True
    )

    assert (
        result["state"]
        == "SHADOW_LOCAL_PLAN_CONSTRUCTED"
    )

    plan = result[
        "shadow_plan"
    ]

    assert (
        plan["status"]
        == "HYPOTHETICAL_LOCAL_PLAN_CONSTRUCTED"
    )

    assert (
        plan["entry_price"]
        == 98.5
    )

    assert (
        plan["stop_loss"]
        == 102.0
    )

    assert (
        plan["stop_distance"]
        == 3.5
    )

    assert (
        plan["take_profit"]
        == 90.0
    )

    assert (
        plan["target_source"]
        == "tp_reference"
    )

    assert (
        plan["target_valid_for_signal"]
        is True
    )

    assert (
        plan["risk_reward"]
        == 2.428571
    )

    assert (
        sell_setup
        == original_setup
    )


def test_neutral_m1_waits():
    result = build_post_shock_entry_shadow(
        post_shock_context=context(
            state="POST_SHOCK_ENTRY_MODE",
            stop_distance=93.26,
            m5_fresh_structure=True,
        ),
        setup=setup(),
        current_price=4390.57,
        m1_closed_bars=(
            neutral_m1_pattern()
        ),
    )

    assert_observer_only(result)

    observation = result[
        "m1_observation"
    ]

    assert (
        observation["available"]
        is True
    )

    assert (
        observation[
            "directional_pattern_observed"
        ]
        is False
    )

    assert (
        result["state"]
        == "WAIT_M1_RETRACE_RECLAIM"
    )

    assert_shadow_plan_unconstructed(
        result
    )


def test_targetless_plan_never_fabricates_tp():
    targetless_setup = setup()

    original_setup = dict(
        targetless_setup
    )

    result = build_post_shock_entry_shadow(
        post_shock_context=context(
            state="POST_SHOCK_ENTRY_MODE",
            stop_distance=93.26,
            m5_fresh_structure=True,
        ),
        setup=targetless_setup,
        current_price=4390.57,
        m1_closed_bars=(
            sell_m1_pattern()
        ),
    )

    assert_observer_only(result)

    assert (
        result["state"]
        == "SHADOW_LOCAL_GEOMETRY_CONSTRUCTED"
    )

    plan = result[
        "shadow_plan"
    ]

    assert (
        plan["status"]
        == (
            "LOCAL_GEOMETRY_CONSTRUCTED_"
            "TARGET_UNAVAILABLE"
        )
    )

    assert (
        plan["entry_price"]
        == 98.5
    )

    assert (
        plan["stop_loss"]
        == 102.0
    )

    assert (
        plan["take_profit"]
        is None
    )

    assert (
        plan["risk_reward"]
        is None
    )

    assert (
        targetless_setup
        == original_setup
    )


def test_normal_context_is_inactive():
    result = build_post_shock_entry_shadow(
        post_shock_context=context(
            state="NORMAL",
            stop_distance=93.26,
            active=False,
            m5_fresh_structure=True,
        ),
        setup=setup(),
        current_price=4390.57,
    )

    assert_observer_only(result)

    assert (
        result["state"]
        == "INACTIVE_POST_SHOCK_CONTEXT"
    )

    assert (
        result["shadow_candidate"]
        is False
    )


def test_live_integration_is_non_interventional():
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
        "build_post_shock_entry_shadow"
        in live_source
    )

    assert (
        '"post_shock_entry_shadow"'
        in live_source
    )


    assert (
        "build_post_shock_entry_shadow_fail_open("
        in live_source
    )

    assert (
        "build_post_shock_entry_shadow("
        not in live_source
    )

    assert (
        "POST_SHOCK_ENTRY_SHADOW_OBSERVATION"
        in live_source
    )


    assert (
        "_capture_post_shock_m1_closed_bars_fail_open("
        in live_source
    )

    assert (
        "mt5.TIMEFRAME_M1"
        in live_source
    )

    assert (
        "m1_closed_bars=("
        in live_source
    )

    # Shadow output is attached, never used as a
    # trading branch or execution authority.
    assert (
        "if post_shock_entry_shadow"
        not in live_source
    )

    assert (
        'if selected_signal_data.get('
        '"post_shock_entry_shadow"'
        not in live_source
    )

    assert (
        "post_shock_entry_shadow"
        not in risk_source
    )

    assert (
        "post_shock_entry_shadow"
        not in execution_source
    )



def main():
    test_normal_geometry_is_untouched()
    test_shock_active_waits()
    test_post_shock_waits_for_m5()
    test_fresh_m5_waits_for_m1_data()
    test_buy_m1_retrace_reclaim_observed()
    test_sell_m1_retrace_reclaim_observed()
    test_neutral_m1_waits()
    test_targetless_plan_never_fabricates_tp()
    test_normal_context_is_inactive()
    test_fail_open_wrapper_never_raises()
    test_live_integration_is_non_interventional()

    print(
        "[PASS] Post-shock local-entry shadow "
        "keeps live setup/risk/execution untouched, "
        "and constructs hypothetical local entry, "
        "structural stop and RR telemetry only."
    )

if __name__ == "__main__":
    main()
