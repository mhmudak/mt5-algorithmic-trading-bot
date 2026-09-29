from __future__ import annotations

import ast
from pathlib import Path

import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "setup_quality_grade.py"


def main():
    print("[SETUP QUALITY HISTORY RESOLUTION TEST V2]")

    text = TARGET.read_text(encoding="utf-8")
    tree = ast.parse(text)

    required = [
        "from src.account_context import get_account_key",
        'if current_account_key and current_account_key != "unknown_account":',
        "Historical edge unavailable (",
        "History Scope: Trade {trade_scope} | Path {path_scope}",
        "History: UNAVAILABLE | ",
        "Source:",
    ]
    for snippet in required:
        if snippet not in text:
            raise AssertionError(
                f"missing SQ2 history-resolution wiring: {snippet}"
            )

    if "History Scope: EXACT COHORT" in text:
        raise AssertionError("misleading EXACT COHORT label still present")

    if "Exact-cohort historical edge unavailable" in text:
        raise AssertionError("misleading exact-cohort blocker still present")

    # Ensure the unavailable-history formatter really concatenates
    # "History: UNAVAILABLE | " with a Source field inside history_line.
    unavailable_formatter_found = False
    scope_formatter_found = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [
                t.id
                for t in node.targets
                if isinstance(t, ast.Name)
            ]

            if "history_line" in targets:
                try:
                    src = ast.get_source_segment(text, node.value) or ""
                except Exception:
                    src = ""

                if (
                    "History: UNAVAILABLE | " in src
                    and "Source:" in src
                ):
                    unavailable_formatter_found = True

        if isinstance(node, ast.JoinedStr):
            try:
                src = ast.get_source_segment(text, node) or ""
            except Exception:
                src = ""
            if (
                "History Scope: Trade" in src
                and "Path" in src
            ):
                scope_formatter_found = True

    if not unavailable_formatter_found:
        raise AssertionError(
            "unavailable-history formatter AST wiring not found"
        )

    if not scope_formatter_found:
        raise AssertionError(
            "real history-scope formatter AST wiring not found"
        )

    if not mt5.initialize():
        raise AssertionError(
            f"mt5.initialize failed: {mt5.last_error()}"
        )

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
            raise AssertionError(
                "resolved account history files are incomplete"
            )

        trade_rows = sq._sq2_rows(trades)
        outcome_rows = sq._sq2_rows(outcomes)

        if trade_rows is None or outcome_rows is None:
            raise AssertionError("SQ2 history read failed")

        print(f"trade_rows={len(trade_rows)}")
        print(f"outcome_rows={len(outcome_rows)}")

        # Verify a basic synthetic setup can get past account resolution/history load.
        synthetic = {
            "setup_id": "SQ2-TEST-HISTORY-RESOLUTION",
            "strategy": "WAVETREND_MOMENTUM",
            "signal": "SELL",
        }
        history = sq._sq2_history(synthetic)
        print(
            "history_probe=",
            {
                "available": history.get("available"),
                "source": history.get("source"),
                "trade_scope": history.get("trade_scope"),
                "trade_sample": history.get("trade_sample"),
                "path_scope": history.get("path_scope"),
                "path_sample": history.get("path_sample"),
            },
        )

        if history.get("source") in {
            "ACCOUNT_UNRESOLVED",
            "HISTORY_READ_FAILED",
        }:
            raise AssertionError(
                f"SQ2 still has account/history resolution failure: {history}"
            )

    finally:
        mt5.shutdown()

    print(
        "\nPASS: SQ2 resolves the current initialized MT5 account, reads "
        "trades/setup_outcomes successfully, no longer labels history as "
        "EXACT COHORT, and distinguishes unavailable history from a genuine "
        "zero-sample cohort."
    )


if __name__ == "__main__":
    main()
