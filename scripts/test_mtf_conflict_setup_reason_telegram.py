from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LIVE = ROOT / "src" / "live_bot.py"


def load_formatter():
    source = LIVE.read_text(
        encoding="utf-8-sig"
    )

    tree = ast.parse(
        source,
        filename=str(LIVE),
    )

    target = None

    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name
            == "_format_mtf_conflict_setup_reason"
        ):
            target = node
            break

    assert target is not None

    module = ast.Module(
        body=[target],
        type_ignores=[],
    )

    ast.fix_missing_locations(
        module
    )

    namespace = {}

    exec(
        compile(
            module,
            str(LIVE),
            "exec",
        ),
        namespace,
    )

    return namespace[
        "_format_mtf_conflict_setup_reason"
    ]


def test_head_shoulders_reason():
    formatter = load_formatter()

    reason = (
        "Head & Shoulders SELL breakout -> "
        "head=4633.41 neckline=4597.86 broken -> "
        "SL above right shoulder 4625.8 -> "
        "TP measured move 4562.31 -> "
        "price below EMA"
    )

    rendered = formatter(
        {
            "strategy": "HEAD_SHOULDERS",
            "reason": reason,
        }
    )

    assert rendered == (
        f"Setup Reason: {reason}\n"
    )

    assert "neckline=4597.86" in rendered


def test_fvg_ce_reason():
    formatter = load_formatter()

    reason = (
        "FVG CE SELL -> bearish FVG "
        "4395.34-4398.1 mitigated near CE "
        "4396.72 -> rejection confirmed -> "
        "SL 4401.25 -> TP "
        "RECENT_STRUCTURE_LOW 4386.3"
    )

    rendered = formatter(
        {
            "strategy": "FVG_CE_MITIGATION",
            "reason": reason,
        }
    )

    assert rendered == (
        f"Setup Reason: {reason}\n"
    )

    assert "bearish FVG" in rendered
    assert "rejection confirmed" in rendered


def test_generic_strategy_reason():
    formatter = load_formatter()

    reason = (
        "Any strategy-provided structural reason"
    )

    rendered = formatter(
        {
            "strategy": "SOME_OTHER_STRATEGY",
            "reason": reason,
        }
    )

    assert rendered == (
        f"Setup Reason: {reason}\n"
    )


def test_missing_reason_is_omitted():
    formatter = load_formatter()

    for candidate in (
        {},
        {"reason": None},
        {"reason": ""},
        {"reason": "   "},
        {"reason": "N/A"},
        {"reason": "NONE"},
        {"reason": "null"},
    ):
        assert formatter(candidate) == ""

    assert formatter(None) == ""


def test_notification_uses_canonical_candidate_reason():
    source = LIVE.read_text(
        encoding="utf-8-sig"
    )

    tree = ast.parse(
        source,
        filename=str(LIVE),
    )

    process_node = None

    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name
            == "process_mtf_conflict_candidate"
        ):
            process_node = node
            break

    assert process_node is not None

    process_source = ast.get_source_segment(
        source,
        process_node,
    )

    assert process_source

    strong_marker = (
        '"📌 STRONG MTF CONFLICT TRACKED\\n"'
    )

    execution_marker = (
        'f"Execution Reason: {execution_reason}\\n"'
    )

    setup_reason_marker = (
        'f"{_format_mtf_conflict_setup_reason(candidate)}\\n"'
    )

    trigger_marker = (
        'f"Telegram Trigger: '
    )

    strong_idx = process_source.index(
        strong_marker
    )

    execution_idx = process_source.index(
        execution_marker,
        strong_idx,
    )

    setup_reason_idx = process_source.index(
        setup_reason_marker,
        execution_idx,
    )

    trigger_idx = process_source.index(
        trigger_marker,
        setup_reason_idx,
    )

    assert (
        execution_idx
        < setup_reason_idx
        < trigger_idx
    )


def test_formatter_uses_candidate_reason_only():
    source = LIVE.read_text(
        encoding="utf-8-sig"
    )

    tree = ast.parse(
        source,
        filename=str(LIVE),
    )

    target = None

    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name
            == "_format_mtf_conflict_setup_reason"
        ):
            target = node
            break

    assert target is not None

    function_source = ast.get_source_segment(
        source,
        target,
    )

    assert 'candidate.get("reason")' in function_source

    assert (
        "execution_reason"
        not in function_source
    )

    assert (
        "rejection_reason"
        not in function_source
    )

    assert (
        "shadow_trade_plan"
        not in function_source
    )


def main():
    test_head_shoulders_reason()
    test_fvg_ce_reason()
    test_generic_strategy_reason()
    test_missing_reason_is_omitted()
    test_notification_uses_canonical_candidate_reason()
    test_formatter_uses_candidate_reason_only()

    print(
        "[PASS] Strong MTF-conflict Telegram now "
        "renders canonical strategy setup reasons "
        "generically, while keeping execution reason "
        "separate and leaving execution behavior untouched."
    )


if __name__ == "__main__":
    main()
