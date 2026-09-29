from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.setup_selection_advisory import (
    format_setup_selection_advisory,
    resolve_setup_selection_advisory,
)


ACCOUNT = "Tickmill-Demo_25323531"


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    print("[SETUP SELECTION ADVISORY TEST V1]")

    psych = resolve_setup_selection_advisory(
        strategy="PSYCH_ROUND_NUMBER_REJECTION",
        account_name=ACCOUNT,
    )
    print("\n[PSYCH_ROUND_NUMBER_REJECTION]")
    print(format_setup_selection_advisory(psych))
    assert_true(psych["badge"] == "INSUFFICIENT_DATA", psych)
    assert_true(psych["sample_count"] == 17, psych)
    assert_true(round(psych["win_quality_pct"], 1) == 94.1, psych)
    assert_true(psych["live_authority"] is False, psych)
    assert_true(psych["decision_impact"] == "NONE", psych)

    ffr = resolve_setup_selection_advisory(
        strategy="FAILED_FVG_REVERSAL",
        direction="BUY",
        session="NEWYORK",
        account_name=ACCOUNT,
    )
    print("\n[FAILED_FVG_REVERSAL BUY NEWYORK]")
    print(format_setup_selection_advisory(ffr))
    assert_true(ffr["badge"] not in {"NO_DATA", "INSUFFICIENT_DATA"}, ffr)
    assert_true(ffr["sample_count"] >= 30, ffr)
    assert_true(ffr["live_authority"] is False, ffr)

    asls = resolve_setup_selection_advisory(
        strategy="AUTO_STRUCTURAL_LEVEL_SCALP",
        session="LONDON_OPEN",
        account_name=ACCOUNT,
    )
    print("\n[AUTO_STRUCTURAL_LEVEL_SCALP LONDON_OPEN]")
    print(format_setup_selection_advisory(asls))
    assert_true(asls["badge"] not in {"NO_DATA", "INSUFFICIENT_DATA"}, asls)
    assert_true(asls["live_authority"] is False, asls)

    unknown = resolve_setup_selection_advisory(
        strategy="THIS_STRATEGY_DOES_NOT_EXIST",
        account_name=ACCOUNT,
    )
    print("\n[UNKNOWN STRATEGY]")
    print(format_setup_selection_advisory(unknown))
    assert_true(unknown["badge"] == "NO_DATA", unknown)
    assert_true(unknown["live_authority"] is False, unknown)

    print("\nPASS: account-scoped resolver, sample threshold, context matching, and advisory-only safety verified.")


if __name__ == "__main__":
    main()
