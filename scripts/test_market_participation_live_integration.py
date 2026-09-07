from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE_BOT = ROOT / "src" / "live_bot.py"


def _tree():
    text = LIVE_BOT.read_text(
        encoding="utf-8-sig"
    )
    return text, ast.parse(
        text,
        filename=str(LIVE_BOT),
    )


def _function(tree, name):
    matches = [
        node
        for node in tree.body
        if (
            isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name == name
        )
    ]

    assert len(matches) == 1, (
        name,
        len(matches),
    )

    return matches[0]


def _call_name(node):
    if (
        isinstance(node, ast.Call)
        and isinstance(
            node.func,
            ast.Name,
        )
    ):
        return node.func.id

    return None


def _keyword_string(call, key):
    for keyword in call.keywords:
        if (
            keyword.arg == key
            and isinstance(
                keyword.value,
                ast.Constant,
            )
        ):
            return keyword.value.value

    return None


def test_import_is_universal_and_observe_only_layer():
    _, tree = _tree()

    imports = [
        node
        for node in tree.body
        if (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
            == "src.market_participation_context"
        )
    ]

    assert len(imports) == 1

    names = {
        alias.name
        for alias
        in imports[0].names
    }

    assert {
        "build_market_participation_context",
        "build_market_participation_observation",
        "log_market_participation_observation",
        "record_mt5_tick",
        "refresh_rithmic_participation_context",
    }.issubset(names)


def test_process_cycle_records_quote_and_refreshes_rithmic():
    _, tree = _tree()
    function = _function(
        tree,
        "process_cycle",
    )

    calls = [
        node
        for node in ast.walk(
            function
        )
        if isinstance(
            node,
            ast.Call,
        )
    ]

    record_calls = [
        node
        for node in calls
        if _call_name(node)
        == "record_mt5_tick"
    ]

    refresh_calls = [
        node
        for node in calls
        if _call_name(node)
        == "refresh_rithmic_participation_context"
    ]

    waiter_calls = [
        node
        for node in calls
        if _call_name(node)
        == "process_wait_better_entry_setups"
    ]

    assert len(record_calls) == 1
    assert len(refresh_calls) == 1
    assert waiter_calls

    assert (
        record_calls[0].lineno
        < refresh_calls[0].lineno
        < min(
            node.lineno
            for node
            in waiter_calls
        )
    )


def test_closed_m15_setup_has_participation_observation():
    _, tree = _tree()
    function = _function(
        tree,
        "process_cycle",
    )

    matching_calls = []

    for node in ast.walk(
        function
    ):
        if not (
            isinstance(
                node,
                ast.Call,
            )
            and _call_name(node)
            == "_freeze_market_participation_observation"
        ):
            continue

        if (
            _keyword_string(
                node,
                "capture_phase",
            )
            == "SETUP_DETECTED_CLOSED_M15"
            and _keyword_string(
                node,
                "event",
            )
            == "SETUP_DETECTED"
        ):
            matching_calls.append(
                node
            )

    assert len(
        matching_calls
    ) == 1

    persist_calls = [
        node
        for node in ast.walk(
            function
        )
        if (
            isinstance(
                node,
                ast.Call,
            )
            and _call_name(node)
            == "_persist_market_participation_observation"
        )
    ]

    assert persist_calls

    assert (
        matching_calls[0].lineno
        < max(
            node.lineno
            for node
            in persist_calls
        )
    )


def test_intrabar_observer_embeds_participation_context():
    text, tree = _tree()
    function = _function(
        tree,
        "_freeze_intrabar_context_observation",
    )

    source = (
        ast.get_source_segment(
            text,
            function,
        )
        or ""
    )

    assert (
        "merged_extra_context"
        in source
    )

    assert (
        '"market_participation_context"'
        in source
    )

    assert (
        "_capture_market_participation_context("
        in source
    )

    assert (
        "extra_context=merged_extra_context"
        in source
    )


def test_execute_trade_has_success_only_universal_t0():
    _, tree = _tree()

    function = _function(
        tree,
        "execute_trade",
    )

    freeze_assignments = []
    raw_assignments = []
    success_ifs = []
    result_returns = []

    for node in ast.walk(
        function
    ):
        if (
            isinstance(
                node,
                ast.Assign,
            )
            and len(
                node.targets
            ) == 1
            and isinstance(
                node.targets[0],
                ast.Name,
            )
        ):
            target = (
                node.targets[0].id
            )

            if (
                target
                == "participation_t0_observation"
                and isinstance(
                    node.value,
                    ast.Call,
                )
                and _call_name(
                    node.value
                )
                == "_freeze_market_participation_observation"
            ):
                freeze_assignments.append(
                    node
                )

                assert (
                    _keyword_string(
                        node.value,
                        "capture_phase",
                    )
                    == "T0_PRE_EXECUTION"
                )

                assert (
                    _keyword_string(
                        node.value,
                        "event",
                    )
                    == "EXECUTION_T0"
                )

            if (
                target
                == "execution_result"
                and isinstance(
                    node.value,
                    ast.Call,
                )
                and _call_name(
                    node.value
                )
                == "_raw_execute_trade"
            ):
                raw_assignments.append(
                    node
                )

        if (
            isinstance(
                node,
                ast.If,
            )
            and isinstance(
                node.test,
                ast.Name,
            )
            and node.test.id
            == "execution_result"
        ):
            persist_calls = [
                child
                for child
                in ast.walk(
                    ast.Module(
                        body=node.body,
                        type_ignores=[],
                    )
                )
                if (
                    isinstance(
                        child,
                        ast.Call,
                    )
                    and _call_name(
                        child
                    )
                    == "_persist_market_participation_observation"
                )
            ]

            if persist_calls:
                success_ifs.append(
                    (
                        node,
                        persist_calls,
                    )
                )

        if (
            isinstance(
                node,
                ast.Return,
            )
            and isinstance(
                node.value,
                ast.Name,
            )
            and node.value.id
            == "execution_result"
        ):
            result_returns.append(
                node
            )

    assert len(
        freeze_assignments
    ) == 1

    assert len(
        raw_assignments
    ) == 1

    assert len(
        success_ifs
    ) == 1

    assert len(
        result_returns
    ) == 1

    success_if, persist_calls = (
        success_ifs[0]
    )

    assert len(
        persist_calls
    ) == 1

    assert (
        freeze_assignments[0].lineno
        < raw_assignments[0].lineno
        < success_if.lineno
        <= persist_calls[0].lineno
        < result_returns[0].lineno
    )

    # Universal guarantee:
    # live_bot must contain exactly one raw
    # order execution call, inside execute_trade.
    raw_calls_global = [
        node
        for node in ast.walk(tree)
        if (
            isinstance(
                node,
                ast.Call,
            )
            and _call_name(node)
            == "_raw_execute_trade"
        )
    ]

    assert len(
        raw_calls_global
    ) == 1


if __name__ == "__main__":
    test_import_is_universal_and_observe_only_layer()
    test_process_cycle_records_quote_and_refreshes_rithmic()
    test_closed_m15_setup_has_participation_observation()
    test_intrabar_observer_embeds_participation_context()
    test_execute_trade_has_success_only_universal_t0()

    print(
        "[PASS] Universal participation "
        "integration semantic regression passed."
    )
