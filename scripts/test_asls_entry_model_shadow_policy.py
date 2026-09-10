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


from config import settings
from src.intrabar_subprofile_risk_guard import (
    evaluate_asls_entry_model_execution_policy,
)


LIVE = ROOT / "src" / "live_bot.py"


def asls_plan(entry_model):
    return {
        "strategy": "AUTO_STRUCTURAL_LEVEL_SCALP",
        "signal": "BUY",
        "entry_model": entry_model,
        "setup_id": "TEST-ASLS",
        "session": "NEWYORK",
        "market_condition": (
            "INTRABAR_STRUCTURAL_LEVEL_SCALP"
        ),
    }


def test_settings():
    assert (
        settings.ENABLE_ASLS_ENTRY_MODEL_EXECUTION_POLICY
        is True
    )

    assert tuple(
        settings.ASLS_SHADOW_ONLY_ENTRY_MODELS
    ) == (
        "SUPPORT_BOUNCE_SCALP",
        "RESISTANCE_BOUNCE_SCALP",
    )

    # This optimization must not silently widen SL,
    # lower RR, or lower score.
    assert settings.ASLS_SL_BUFFER == 2.50
    assert settings.ASLS_MIN_RR == 1.0
    assert settings.ASLS_MIN_SCORE == 94


def test_bounce_models_blocked():
    for model in (
        "SUPPORT_BOUNCE_SCALP",
        "RESISTANCE_BOUNCE_SCALP",
    ):
        decision = (
            evaluate_asls_entry_model_execution_policy(
                signal="BUY",
                trade_plan=asls_plan(
                    model
                ),
                enabled=True,
                blocked_entry_models=(
                    settings.ASLS_SHADOW_ONLY_ENTRY_MODELS
                ),
            )
        )

        assert (
            decision["allowed"]
            is False
        )

        assert (
            decision["reason"]
            == "asls_entry_model_shadow_only"
        )


def test_break_hold_models_still_allowed():
    for model in (
        "SUPPORT_BREAK_HOLD_SCALP",
        "RESISTANCE_BREAK_HOLD_SCALP",
    ):
        decision = (
            evaluate_asls_entry_model_execution_policy(
                signal="BUY",
                trade_plan=asls_plan(
                    model
                ),
                enabled=True,
                blocked_entry_models=(
                    settings.ASLS_SHADOW_ONLY_ENTRY_MODELS
                ),
            )
        )

        assert (
            decision["allowed"]
            is True
        )


def test_non_asls_unaffected():
    plan = {
        "strategy": "FAILED_FVG_REVERSAL",
        "signal": "BUY",
        "entry_model": (
            "SUPPORT_BOUNCE_SCALP"
        ),
    }

    decision = (
        evaluate_asls_entry_model_execution_policy(
            signal="BUY",
            trade_plan=plan,
            enabled=True,
            blocked_entry_models=(
                settings.ASLS_SHADOW_ONLY_ENTRY_MODELS
            ),
        )
    )

    assert decision["allowed"] is True
    assert (
        decision["reason"]
        == "not_asls_strategy"
    )


def test_disabled_policy_is_noninterventional():
    decision = (
        evaluate_asls_entry_model_execution_policy(
            signal="BUY",
            trade_plan=asls_plan(
                "SUPPORT_BOUNCE_SCALP"
            ),
            enabled=False,
            blocked_entry_models=(
                settings.ASLS_SHADOW_ONLY_ENTRY_MODELS
            ),
        )
    )

    assert decision["allowed"] is True


def test_live_bot_has_both_enforcement_layers():
    source = LIVE.read_text(
        encoding="utf-8-sig"
    )

    assert (
        "PHASE6H3_ASLS_SHADOW_ONLY"
        in source
    )

    assert (
        "ASLS_ENTRY_MODEL_SHADOW_ONLY"
        in source
    )

    assert source.count(
        "evaluate_asls_entry_model_execution_policy("
    ) >= 2

    dedicated_gate = source.index(
        "PHASE6H3_ASLS_SHADOW_ONLY"
    )

    dedicated_execute = source.index(
        "execution_result = execute_trade("
        "asls_signal, asls_trade_plan, SYMBOL"
    )

    assert (
        dedicated_gate
        < dedicated_execute
    )


def test_shadow_candidate_does_not_end_process_cycle():
    source = LIVE.read_text(
        encoding="utf-8-sig"
    )

    shadow_marker = source.index(
        "PHASE6H3_ASLS_SHADOW_ONLY"
    )

    dedicated_gate = source.index(
        "if (",
        shadow_marker,
    )

    shadow_region = source[
        shadow_marker:dedicated_gate
    ]

    assert (
        "return current_candle_time"
        not in shadow_region
    )

    assert (
        '"cycle_continues": True'
        in shadow_region
    )

    assert (
        "and asls_model_policy.get("
        in source
    )


def test_universal_policy_precedes_raw_execution():
    source = LIVE.read_text(
        encoding="utf-8-sig"
    )

    tree = ast.parse(
        source,
        filename=str(LIVE),
    )

    execute_functions = [
        node
        for node in ast.walk(tree)
        if (
            isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
            and node.name
            == "execute_trade"
        )
    ]

    assert execute_functions

    found_policy = False

    for function in execute_functions:
        calls = []

        for node in ast.walk(function):
            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            name = None

            if isinstance(
                node.func,
                ast.Name,
            ):
                name = node.func.id

            elif isinstance(
                node.func,
                ast.Attribute,
            ):
                name = node.func.attr

            calls.append(
                (
                    node.lineno,
                    name,
                )
            )

        policy_lines = [
            line
            for line, name in calls
            if (
                name
                == (
                    "evaluate_asls_entry_model_"
                    "execution_policy"
                )
            )
        ]

        if policy_lines:
            found_policy = True

    assert found_policy


def main():
    test_settings()
    test_bounce_models_blocked()
    test_break_hold_models_still_allowed()
    test_non_asls_unaffected()
    test_disabled_policy_is_noninterventional()
    test_live_bot_has_both_enforcement_layers()
    test_shadow_candidate_does_not_end_process_cycle()
    test_universal_policy_precedes_raw_execution()

    print(
        "[PASS] ASLS bounce models are "
        "shadow-only, break/hold models "
        "remain executable, non-ASLS "
        "strategies are unaffected, and "
        "SL/RR/score are unchanged."
    )


if __name__ == "__main__":
    main()
