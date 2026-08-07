from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
import src.funded_account_runtime_watch as watch


def test_floor_breach_requests_close():
    result = watch.classify_funded_watch_decision({
        "allowed": False,
        "reason": (
            "funded_daily_safety_floor_reached"
        ),
        "profile": (
            "GETLEVERAGED_TURBO_EVALUATION_50K"
        ),
        "snapshot": {
            "equity": 49280.0,
            "effective_safe_floor": 49289.26,
        },
    })

    assert result["should_block_cycle"] is True
    assert result["should_close_positions"] is True
    assert result["snapshot"]["orders_sent"] == 0


def test_trailing_breach_requests_close():
    result = watch.classify_funded_watch_decision({
        "allowed": False,
        "reason": (
            "funded_trailing_safety_floor_reached"
        ),
        "snapshot": {},
    })

    assert result["should_block_cycle"] is True
    assert result["should_close_positions"] is True


def test_identity_failure_blocks_without_closing():
    result = watch.classify_funded_watch_decision({
        "allowed": False,
        "reason": (
            "funded_account_login_mismatch"
        ),
        "snapshot": {},
    })

    assert result["should_block_cycle"] is True
    assert result["should_close_positions"] is False
    assert result["snapshot"]["orders_sent"] == 0


def test_healthy_decision_continues():
    result = watch.classify_funded_watch_decision({
        "allowed": True,
        "reason": "funded_safe_mode_allowed",
        "snapshot": {
            "equity_safety_margin": 1250.0,
        },
    })

    assert result["should_block_cycle"] is False
    assert result["should_close_positions"] is False


def test_runtime_watch_has_zero_order_capability():
    original_evaluator = (
        watch.evaluate_funded_account_safe_mode
    )
    original_enabled = (
        settings.ENABLE_PROP_FIRM_SAFE_MODE
    )

    calls = []

    try:
        settings.ENABLE_PROP_FIRM_SAFE_MODE = True

        def synthetic_evaluator(**kwargs):
            calls.append(kwargs)

            return {
                "allowed": False,
                "reason": (
                    "funded_daily_safety_floor_reached"
                ),
                "profile": settings.PROP_FIRM_PROFILE,
                "snapshot": {
                    "balance": 50000.0,
                    "equity": 48740.0,
                    "effective_safe_floor": 48750.0,
                    "orders_sent": 0,
                },
            }

        watch.evaluate_funded_account_safe_mode = (
            synthetic_evaluator
        )

        result = (
            watch.evaluate_runtime_funded_account_watch(
                mt5_module=object(),
                symbol="XAUUSD",
            )
        )

        assert len(calls) == 1
        assert result["should_close_positions"] is True
        assert result["snapshot"]["orders_sent"] == 0

    finally:
        watch.evaluate_funded_account_safe_mode = (
            original_evaluator
        )
        settings.ENABLE_PROP_FIRM_SAFE_MODE = (
            original_enabled
        )


def test_live_bot_source_ordering():
    source = (
        ROOT / "src" / "live_bot.py"
    ).read_text(encoding="utf-8")

    watcher_marker = (
        "evaluate_runtime_funded_account_watch("
    )
    generic_marker = (
        "if ENABLE_GLOBAL_DRAWDOWN_STOP:"
    )

    assert watcher_marker in source
    assert generic_marker in source

    main_start = source.index("def main():")

    watcher_index = source.index(
        watcher_marker,
        main_start,
    )
    generic_index = source.index(
        generic_marker,
        main_start,
    )

    assert watcher_index < generic_index

    assert (
        "Funded safety floor reached and "
        in source
    )
    assert (
        "Emergency close blocked by "
        in source
    )


def test_safe_persistent_defaults():
    assert settings.EXECUTION_MODE == "LIVE"
    assert settings.ALLOW_LIVE_TRADING is True
    assert settings.ENABLE_PROP_FIRM_SAFE_MODE is True
    assert settings.PROP_FIRM_SAFE_MODE_FAIL_CLOSED is True


if __name__ == "__main__":
    test_floor_breach_requests_close()
    test_trailing_breach_requests_close()
    test_identity_failure_blocks_without_closing()
    test_healthy_decision_continues()
    test_runtime_watch_has_zero_order_capability()
    test_live_bot_source_ordering()
    test_safe_persistent_defaults()

    print(
        "[PASS] Phase 7A6C continuous funded-equity "
        "watcher passed."
    )
