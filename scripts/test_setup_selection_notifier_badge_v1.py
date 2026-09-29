from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.notifier import (
    build_setup_quality_alert_block,
    build_setup_selection_advisory_block,
    build_trade_message,
)


ACCOUNT = "Tickmill-Demo_25323531"


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    print("[SETUP SELECTION NOTIFIER BADGE TEST V1]")

    psych_data = {
        "strategy": "PSYCH_ROUND_NUMBER_REJECTION",
        "signal": "BUY",
        "entry_model": "TEST",
        "session": "NEWYORK",
        "market_condition": "RANGING",
        "stage": "SIGNAL DETECTED",
        "score": 90,
    }

    psych_block = build_setup_selection_advisory_block(
        psych_data,
        account_name=ACCOUNT,
    )
    print("\n[DIRECT PSYCH BLOCK]")
    print(psych_block)
    assert_true("[SETUP SELECTION] INSUFFICIENT_DATA" in psych_block, psych_block)
    assert_true("Win Quality: 94.1%" in psych_block, psych_block)
    assert_true("Samples: 17/30" in psych_block, psych_block)
    assert_true("Final Exp: +0.11R" in psych_block, psych_block)
    assert_true("Mode: ADVISORY ONLY" in psych_block, psych_block)

    ffr_data = {
        "strategy": "FAILED_FVG_REVERSAL",
        "signal": "BUY",
        "entry_model": "FAILED_BULLISH_FVG_REVERSAL",
        "session": "NEWYORK",
        "market_condition": "RANGING",
        "stage": "SIGNAL DETECTED",
        "score": 95,
        "entry": 4300.0,
        "sl": 4295.0,
        "tp": 4310.0,
    }

    ffr_block = build_setup_selection_advisory_block(
        ffr_data,
        account_name=ACCOUNT,
    )
    print("\n[DIRECT FFR BLOCK]")
    print(ffr_block)
    assert_true("[SETUP SELECTION]" in ffr_block, ffr_block)
    assert_true("Mode: ADVISORY ONLY" in ffr_block, ffr_block)
    if "[SETUP SELECTION] MIXED_CONTEXT" in ffr_block:
        assert_true("Context Evidence:" in ffr_block, ffr_block)
        assert_true("Win " in ffr_block, ffr_block)
        assert_true("Exp " in ffr_block, ffr_block)

    # Existing setup-quality formatter must remain usable and receive exactly
    # one statistical block.
    premium = build_setup_quality_alert_block(
        ffr_data,
        status="TEST STATUS",
    )
    print("\n[PREMIUM BLOCK + SELECTION BADGE]")
    print(premium)
    assert_true(premium.count("[SETUP SELECTION]") == 1, premium)
    assert_true("[SETUP SELECTION] NO_DATA" not in premium, premium)
    if "[SETUP SELECTION] MIXED_CONTEXT" in premium:
        assert_true("Context Evidence:" in premium, premium)

    # Normal trade/setup message path must also get exactly one badge.
    normal = build_trade_message(ffr_data)
    print("\n[NORMAL MESSAGE + SELECTION BADGE]")
    print(normal)
    assert_true(normal.count("[SETUP SELECTION]") == 1, normal)
    assert_true("[SETUP SELECTION] NO_DATA" not in normal, normal)

    unknown = build_setup_selection_advisory_block(
        {"strategy": "THIS_STRATEGY_DOES_NOT_EXIST", "signal": "SELL"},
        account_name=ACCOUNT,
    )
    print("\n[UNKNOWN STRATEGY BLOCK]")
    print(repr(unknown))
    assert_true(unknown == "", unknown)

    print("\nPASS: notifier badge enrichment is idempotent, advisory-only, preserves existing message paths, and suppresses NO_DATA noise.")


if __name__ == "__main__":
    main()
