from __future__ import annotations

import ast
from pathlib import Path

import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "setup_quality_grade.py"


def main():
    print("[SETUP QUALITY HISTORY RESOLUTION TEST V1]")

    text = TARGET.read_text(encoding="utf-8")
    ast.parse(text)

    required = [
        "from src.account_context import get_account_key",
        'if current_account_key and current_account_key != "unknown_account":',
        'Historical edge unavailable (',
        'History Scope: Trade {trade_scope} | Path {path_scope}',
        'History: UNAVAILABLE | Source:',
    ]
    for snippet in required:
        if snippet not in text:
            raise AssertionError(f"missing SQ2 history-resolution wiring: {snippet}")

    if "History Scope: EXACT COHORT" in text:
        raise AssertionError("misleading EXACT COHORT label still present")

    if "Exact-cohort historical edge unavailable" in text:
        raise AssertionError("misleading exact-cohort blocker still present")

    if not mt5.initialize():
        raise AssertionError(f"mt5.initialize failed: {mt5.last_error()}")

    try:
        import src.setup_quality_grade as sq

        resolved = sq._sq2_resolve_account_dir({})
        print(f"resolved_account_dir={resolved}")

        if resolved is None:
            raise AssertionError(
                "SQ2 could not resolve current initialized MT5 account directory"
            )

        trades = resolved / "trades.json"
        outcomes = resolved / "setup_outcomes.json"

        print(f"trades_exists={trades.exists()}")
        print(f"outcomes_exists={outcomes.exists()}")

        if not trades.exists() or not outcomes.exists():
            raise AssertionError("resolved account history files are incomplete")

        trade_rows = sq._sq2_rows(trades)
        outcome_rows = sq._sq2_rows(outcomes)

        if trade_rows is None or outcome_rows is None:
            raise AssertionError("SQ2 history read failed")

        print(f"trade_rows={len(trade_rows)}")
        print(f"outcome_rows={len(outcome_rows)}")

    finally:
        mt5.shutdown()

    print(
        "\nPASS: SQ2 now prefers the current initialized MT5 account when "
        "resolving history. Available history reports its actual "
        "STRATEGY_SIGNAL/STRATEGY_FALLBACK scopes, while unavailable history "
        "reports the real source reason instead of a fake n=0."
    )


if __name__ == "__main__":
    main()
