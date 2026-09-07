from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from src.key_level_smc_override import (
    MAX_EXTENSION_ATR_RATIO,
    MINIMUM_RR,
    MINIMUM_SCORE,
    MINIMUM_TOUCHES,
    evaluate_key_level_strong_smc_override,
)


SETTINGS = (
    ROOT / "config" / "settings.py"
)

LIVE_BOT = (
    ROOT / "src" / "live_bot.py"
)


def _setting(name):
    source = SETTINGS.read_text(
        encoding="utf-8-sig"
    )

    tree = ast.parse(
        source,
        filename=str(SETTINGS),
    )

    matches = []

    for node in tree.body:
        if not isinstance(
            node,
            ast.Assign,
        ):
            continue

        if len(node.targets) != 1:
            continue

        target = node.targets[0]

        if (
            isinstance(
                target,
                ast.Name,
            )
            and target.id == name
        ):
            matches.append(node)

    assert len(matches) == 1

    return ast.literal_eval(
        matches[0].value
    )


def _tracked_setup():
    return {
        "strategy": (
            "KEY_LEVEL_BREAK_HOLD"
        ),
        "signal": "BUY",
        "score": 95,
        "rr": 1.80,
        "touches": 2,
        "entry_model": (
            "KEY_LEVEL_BREAK_HOLD_BUY"
        ),
        "reason": (
            "KEY_LEVEL_BREAK_HOLD BUY -> "
            "resistance 4556.3 broken "
            "and held -> touches 2 -> "
            "SMC: ema_bullish"
        ),
    }


def test_entry_policy():
    better = _setting(
        "BETTER_ENTRY_STRATEGIES"
    )

    delayed = _setting(
        "DELAYED_ENTRY_STRATEGIES"
    )

    generic_soft = _setting(
        "SOFT_SMC_STRATEGIES"
    )

    assert (
        "KEY_LEVEL_BREAK_HOLD"
        in better
    )

    assert (
        "KEY_LEVEL_BREAK_HOLD"
        in delayed
    )

    assert (
        _setting(
            "ENABLE_SPLIT_DELAYED_ENTRY"
        )
        is True
    )

    assert (
        _setting(
            "SPLIT_DELAYED_ENTRY_IMMEDIATE_PCT"
        )
        == 0.50
    )

    # Keep KEY_LEVEL on the dedicated
    # structurally guarded SMC override,
    # not generic score-only soft SMC.
    assert (
        "KEY_LEVEL_BREAK_HOLD"
        not in generic_soft
    )


def test_existing_live_routes_exist():
    source = LIVE_BOT.read_text(
        encoding="utf-8-sig"
    )

    assert (
        "strategy_name in "
        "BETTER_ENTRY_STRATEGIES"
        in source
    )

    assert (
        "strategy_name in "
        "DELAYED_ENTRY_STRATEGIES"
        in source
    )

    assert (
        "ENABLE_SPLIT_DELAYED_ENTRY"
        in source
    )

    assert (
        "split_lot_for_delayed_entry("
        in source
    )


def test_guarded_soft_smc_thresholds():
    assert MINIMUM_SCORE == 95.0
    assert MINIMUM_RR == 1.80
    assert MINIMUM_TOUCHES == 2

    # Existing extension protection
    # must remain unchanged.
    assert (
        MAX_EXTENSION_ATR_RATIO
        == 0.75
    )


def test_tracked_shape_passes():
    result = (
        evaluate_key_level_strong_smc_override(
            _tracked_setup(),
            "BUY",
        )
    )

    assert (
        result["allowed"]
        is True
    ), result

    assert (
        result["reason"]
        == "key_level_strong_smc_override_allowed"
    )


def test_score_94_still_blocked():
    setup = _tracked_setup()
    setup["score"] = 94

    result = (
        evaluate_key_level_strong_smc_override(
            setup,
            "BUY",
        )
    )

    assert (
        result["allowed"]
        is False
    )

    assert (
        result["reason"]
        == "key_level_override_score_too_low"
    )


def test_one_touch_still_blocked():
    setup = _tracked_setup()
    setup["touches"] = 1

    result = (
        evaluate_key_level_strong_smc_override(
            setup,
            "BUY",
        )
    )

    assert (
        result["allowed"]
        is False
    )

    assert (
        result["reason"]
        == "key_level_override_touches_too_low"
    )


def test_low_rr_still_blocked():
    setup = _tracked_setup()
    setup["rr"] = 1.79

    result = (
        evaluate_key_level_strong_smc_override(
            setup,
            "BUY",
        )
    )

    assert (
        result["allowed"]
        is False
    )

    assert (
        result["reason"]
        == "key_level_override_rr_too_low"
    )


def test_break_hold_still_required():
    setup = _tracked_setup()

    setup["entry_model"] = (
        "KEY_LEVEL_GENERIC_BUY"
    )

    setup["reason"] = (
        "resistance interaction "
        "touches 2 SMC: ema_bullish"
    )

    result = (
        evaluate_key_level_strong_smc_override(
            setup,
            "BUY",
        )
    )

    assert (
        result["allowed"]
        is False
    )

    assert (
        result["reason"]
        == "key_level_break_hold_not_confirmed"
    )


def test_ema_alignment_still_required():
    setup = _tracked_setup()

    setup["reason"] = (
        "resistance broken and held "
        "touches 2"
    )

    result = (
        evaluate_key_level_strong_smc_override(
            setup,
            "BUY",
        )
    )

    assert (
        result["allowed"]
        is False
    )

    assert (
        result["reason"]
        == "key_level_ema_alignment_missing"
    )


def test_overextension_still_blocked():
    setup = _tracked_setup()

    setup[
        "extension_atr_ratio"
    ] = 0.76

    result = (
        evaluate_key_level_strong_smc_override(
            setup,
            "BUY",
        )
    )

    assert (
        result["allowed"]
        is False
    )

    assert (
        result["reason"]
        == "key_level_setup_overextended"
    )


def test_opposite_htf_still_blocked():
    setup = _tracked_setup()

    setup["htf_bias"] = "SELL"

    result = (
        evaluate_key_level_strong_smc_override(
            setup,
            "BUY",
        )
    )

    assert (
        result["allowed"]
        is False
    )

    assert (
        result["reason"]
        == "key_level_opposite_htf_context"
    )


if __name__ == "__main__":
    test_entry_policy()
    test_existing_live_routes_exist()
    test_guarded_soft_smc_thresholds()
    test_tracked_shape_passes()
    test_score_94_still_blocked()
    test_one_touch_still_blocked()
    test_low_rr_still_blocked()
    test_break_hold_still_required()
    test_ema_alignment_still_required()
    test_overextension_still_blocked()
    test_opposite_htf_still_blocked()

    print(
        "[PASS] KEY_LEVEL_BREAK_HOLD "
        "Better/Delayed/Split entry and "
        "guarded soft-SMC regression passed."
    )
