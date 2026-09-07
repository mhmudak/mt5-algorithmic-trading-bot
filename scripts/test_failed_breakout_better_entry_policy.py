from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SETTINGS = (
    ROOT
    / "config"
    / "settings.py"
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


def test_failed_breakout_policy():
    strategy = (
        "FAILED_BREAKOUT_REVERSAL"
    )

    better = set(
        _setting(
            "BETTER_ENTRY_STRATEGIES"
        )
    )

    delayed = set(
        _setting(
            "DELAYED_ENTRY_STRATEGIES"
        )
    )

    soft = set(
        _setting(
            "SOFT_SMC_STRATEGIES"
        )
    )

    assert strategy in better

    # Timing-sensitive reversal:
    # do NOT put it on generic
    # delayed/split handling.
    assert strategy not in delayed

    # No evidence supports weakening
    # its SMC filter.
    assert strategy not in soft


if __name__ == "__main__":
    test_failed_breakout_policy()

    print(
        "[PASS] FAILED_BREAKOUT_REVERSAL "
        "Better Entry only policy passed."
    )
