from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LIVE_BOT = (
    ROOT
    / "src"
    / "live_bot.py"
)


def _function_node(
    source,
    name,
):
    tree = ast.parse(
        source,
        filename=str(LIVE_BOT),
    )

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

    assert len(matches) == 1

    return matches[0]


def _function_source(
    source,
    node,
):
    lines = source.splitlines()

    return "\n".join(
        lines[
            node.lineno - 1:
            node.end_lineno
        ]
    )


def _audit_calls(function_node):
    calls = {}

    for node in ast.walk(
        function_node
    ):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        if not (
            isinstance(
                node.func,
                ast.Name,
            )
            and node.func.id
            == (
                "_log_better_entry_"
                "lifecycle_event_fail_open"
            )
        ):
            continue

        event_value = None

        for keyword in node.keywords:
            if (
                keyword.arg == "event"
                and isinstance(
                    keyword.value,
                    ast.Constant,
                )
                and isinstance(
                    keyword.value.value,
                    str,
                )
            ):
                event_value = (
                    keyword.value.value
                )
                break

        assert event_value is not None
        assert event_value not in calls

        calls[event_value] = node

    return calls


def _execute_trade_calls(function_node):
    return [
        node
        for node in ast.walk(
            function_node
        )
        if (
            isinstance(
                node,
                ast.Call,
            )
            and isinstance(
                node.func,
                ast.Name,
            )
            and node.func.id
            == "execute_trade"
        )
    ]


def test_better_entry_audit_lifecycle():
    source = LIVE_BOT.read_text(
        encoding="utf-8-sig"
    )

    helper_node = _function_node(
        source,
        (
            "_log_better_entry_"
            "lifecycle_event_fail_open"
        ),
    )

    process_node = _function_node(
        source,
        (
            "process_wait_"
            "better_entry_setups"
        ),
    )

    helper_source = (
        _function_source(
            source,
            helper_node,
        )
    )

    process_source = (
        _function_source(
            source,
            process_node,
        )
    )

    # Fail-open observer semantics.
    assert "try:" in helper_source
    assert (
        "except Exception"
        in helper_source
    )

    assert (
        '"decision_impact": "NONE"'
        in helper_source
    )

    assert (
        '"can_influence_decision": False'
        in helper_source
    )

    # Existing getter remains the authority
    # for expiration/state transitions.
    assert (
        process_source.count(
            "execution_engine."
            "get_wait_better_entry_setups()"
        )
        == 1
    )

    # The observer-side pre-expiry snapshot
    # must also fail open. The logger message
    # is split across adjacent source literals,
    # so assert its semantic components instead
    # of requiring one contiguous source string.
    assert (
        "Pre-expiry lifecycle snapshot "
        in process_source
    )

    assert (
        "failed open "
        in process_source
    )

    assert (
        "wait_candidates_before_refresh = []"
        in process_source
    )

    assert (
        "except Exception as exc:"
        in process_source
    )

    snapshot_index = process_source.index(
        "wait_candidates_before_refresh = ["
    )

    getter_index = process_source.index(
        "execution_engine."
        "get_wait_better_entry_setups()"
    )

    assert snapshot_index < getter_index

    # Audit calls only.
    audit_calls = _audit_calls(
        process_node
    )

    required = {
        "BETTER_ENTRY_EXPIRED",
        "BETTER_ENTRY_EXECUTION_ATTEMPT",
        "BETTER_ENTRY_EXECUTED",
        "BETTER_ENTRY_EXECUTION_FAILED",
    }

    assert (
        set(audit_calls)
        == required
    ), audit_calls

    # Singular execution path is preserved.
    execute_calls = (
        _execute_trade_calls(
            process_node
        )
    )

    assert len(execute_calls) == 1

    execute_line = (
        execute_calls[0].lineno
    )

    assert (
        audit_calls[
            "BETTER_ENTRY_EXECUTION_ATTEMPT"
        ].lineno
        < execute_line
    )

    assert (
        audit_calls[
            "BETTER_ENTRY_EXECUTED"
        ].lineno
        > execute_line
    )

    assert (
        audit_calls[
            "BETTER_ENTRY_EXECUTION_FAILED"
        ].lineno
        > execute_line
    )

    # Existing memory-decision instrumentation
    # remains intact.
    decisions = set()

    for node in ast.walk(
        process_node
    ):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        if not (
            isinstance(
                node.func,
                ast.Name,
            )
            and node.func.id
            == "save_execution_memory_report"
        ):
            continue

        for keyword in node.keywords:
            if (
                keyword.arg == "decision"
                and isinstance(
                    keyword.value,
                    ast.Constant,
                )
                and isinstance(
                    keyword.value.value,
                    str,
                )
            ):
                decisions.add(
                    keyword.value.value
                )

    assert (
        "BETTER_ENTRY_EXECUTION_ATTEMPT"
        in decisions
    )

    assert (
        "BETTER_ENTRY_EXECUTION_SUCCESS"
        in decisions
    )

    assert (
        "BETTER_ENTRY_EXECUTION_FAILED"
        in decisions
    )


if __name__ == "__main__":
    test_better_entry_audit_lifecycle()

    print(
        "[PASS] Better Entry setup-audit "
        "lifecycle observer is fail-open, "
        "complete, and non-interventional."
    )
