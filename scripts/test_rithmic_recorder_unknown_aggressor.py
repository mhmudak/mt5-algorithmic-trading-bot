from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "rithmic_record_market_data.py"


def load_helper():
    source = TARGET.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)

    target = None

    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name
            == "_update_rithmic_recorder_trade_stats"
        ):
            target = node
            break

    assert target is not None

    module = ast.Module(
        body=[target],
        type_ignores=[],
    )

    ast.fix_missing_locations(module)

    namespace = {}

    exec(
        compile(
            module,
            str(TARGET),
            "exec",
        ),
        namespace,
    )

    return (
        namespace[
            "_update_rithmic_recorder_trade_stats"
        ],
        ast.get_source_segment(source, target),
    )


def fresh_stats():
    return {
        "last_trade_count": 0,
        "buy_volume": 0,
        "sell_volume": 0,
        "unknown_trade_count": 0,
        "unknown_volume": 0,
        "cumulative_delta": 0,
    }


def test_buy_is_buy():
    helper, _ = load_helper()
    stats = fresh_stats()

    helper(
        stats,
        {
            "trade_size": 7,
            "aggressor": "BUY",
        },
    )

    assert stats["last_trade_count"] == 1
    assert stats["buy_volume"] == 7
    assert stats["sell_volume"] == 0
    assert stats["unknown_trade_count"] == 0
    assert stats["unknown_volume"] == 0
    assert stats["cumulative_delta"] == 7


def test_sell_is_sell():
    helper, _ = load_helper()
    stats = fresh_stats()

    helper(
        stats,
        {
            "trade_size": 5,
            "aggressor": "SELL",
        },
    )

    assert stats["last_trade_count"] == 1
    assert stats["buy_volume"] == 0
    assert stats["sell_volume"] == 5
    assert stats["unknown_trade_count"] == 0
    assert stats["unknown_volume"] == 0
    assert stats["cumulative_delta"] == -5


def test_unknown_is_neutral():
    helper, _ = load_helper()
    stats = fresh_stats()

    helper(
        stats,
        {
            "trade_size": 11,
            "aggressor": "UNKNOWN",
        },
    )

    assert stats["last_trade_count"] == 1
    assert stats["buy_volume"] == 0
    assert stats["sell_volume"] == 0
    assert stats["unknown_trade_count"] == 1
    assert stats["unknown_volume"] == 11
    assert stats["cumulative_delta"] == 0


def test_missing_and_arbitrary_aggressors_are_neutral():
    helper, _ = load_helper()
    stats = fresh_stats()

    helper(
        stats,
        {
            "trade_size": 3,
            "aggressor": None,
        },
    )

    helper(
        stats,
        {
            "trade_size": 4,
            "aggressor": "UNDEFINED_CODE",
        },
    )

    assert stats["last_trade_count"] == 2
    assert stats["buy_volume"] == 0
    assert stats["sell_volume"] == 0
    assert stats["unknown_trade_count"] == 2
    assert stats["unknown_volume"] == 7
    assert stats["cumulative_delta"] == 0


def test_source_requires_explicit_sell():
    _, function_source = load_helper()

    assert 'if aggressor == "BUY"' in function_source
    assert 'elif aggressor == "SELL"' in function_source
    assert 'stats["unknown_trade_count"]' in function_source
    assert 'stats["unknown_volume"]' in function_source


def main():
    test_buy_is_buy()
    test_sell_is_sell()
    test_unknown_is_neutral()
    test_missing_and_arbitrary_aggressors_are_neutral()
    test_source_requires_explicit_sell()

    print(
        "[PASS] Rithmic recorder now requires explicit BUY/SELL "
        "aggressors; unknown trades remain delta-neutral."
    )


if __name__ == "__main__":
    main()
