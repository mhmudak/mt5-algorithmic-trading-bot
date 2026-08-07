from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import re
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
import src.execution as execution
import src.order_executor as order_executor


def test_same_direction_exposure_cap():
    original_count = (
        execution.count_same_direction_positions
    )
    original_daily = (
        execution.reached_max_trades_today
    )
    original_cooldown = (
        execution.in_cooldown_period
    )

    tick = SimpleNamespace(
        bid=4269.00,
        ask=4269.10,
    )

    try:
        execution.reached_max_trades_today = (
            lambda symbol: False
        )
        execution.in_cooldown_period = (
            lambda symbol: False
        )

        execution.count_same_direction_positions = (
            lambda symbol, signal: 3
        )

        allowed, reason = execution.check_trade_guard(
            "BUY",
            tick,
        )

        assert allowed is False
        assert (
            "Max same-direction open trades reached"
            in reason
        )

        execution.count_same_direction_positions = (
            lambda symbol, signal: 2
        )

        allowed, reason = execution.check_trade_guard(
            "BUY",
            tick,
        )

        assert allowed is True
        assert reason == "Trade allowed"

    finally:
        execution.count_same_direction_positions = (
            original_count
        )
        execution.reached_max_trades_today = (
            original_daily
        )
        execution.in_cooldown_period = (
            original_cooldown
        )


def test_tp_split_does_not_increase_total_lot():
    symbol_info = SimpleNamespace(
        volume_min=0.01,
        volume_step=0.01,
    )

    volumes = (
        order_executor._split_lot_by_symbol_rules(
            total_lot=0.03,
            symbol_info=symbol_info,
            requested_parts=3,
        )
    )

    assert volumes == [0.01, 0.01, 0.01]
    assert round(sum(volumes), 2) == 0.03


def test_risk_has_no_loss_based_escalation():
    risk_source = (
        ROOT / "src" / "risk.py"
    ).read_text(encoding="utf-8").lower()

    prohibited_patterns = (
        r"\bmartingale\b",
        r"\bgrid\b",
        r"after[_ ]?loss",
        r"loss[_ ]?multiplier",
        r"lot[_ ]?multiplier",
        r"volume[_ ]?multiplier",
    )

    for pattern in prohibited_patterns:
        assert re.search(pattern, risk_source) is None, (
            f"Prohibited risk pattern found: {pattern}"
        )

    assert 'elif position_mode == "fixed":' in risk_source
    assert "lot = fixed_lot" in risk_source


def test_recovery_uses_normal_trade_guard():
    source = (
        ROOT / "src" / "live_bot.py"
    ).read_text(encoding="utf-8")

    start = source.index(
        "def process_candidate_rejection_recovery_setups("
    )

    next_function = source.find(
        "\ndef ",
        start + 5,
    )

    function_source = source[
        start:
        next_function if next_function > start else None
    ]

    guard_marker = (
        "trade_allowed, guard_reason = "
        "check_trade_guard(signal, tick)"
    )
    execution_marker = (
        "execution_result = "
        "execute_trade(signal, trade_plan, SYMBOL)"
    )

    assert guard_marker in function_source
    assert execution_marker in function_source

    assert (
        function_source.index(guard_marker)
        < function_source.index(execution_marker)
    )


def test_protected_reentry_does_not_change_size():
    source = (
        ROOT / "src" / "protected_reentry.py"
    ).read_text(encoding="utf-8")

    assert 'trade.get("status") != "CLOSED"' in source
    assert (
        "max_profit < "
        "PROTECTED_REENTRY_MIN_PROFIT_PRICE"
        in source
    )
    assert '"lot"' not in source
    assert '"volume"' not in source


def test_safe_runtime_defaults():
    assert settings.EXECUTION_MODE == "LIVE"
    assert settings.ALLOW_LIVE_TRADING is True
    assert settings.ENABLE_PROP_FIRM_SAFE_MODE is True
    assert settings.PROP_FIRM_SAFE_MODE_FAIL_CLOSED is True

    assert settings.MAX_SAME_DIRECTION_TRADES == 3
    assert settings.POSITION_MODE == "fixed"
    assert 0 < settings.FIXED_LOT <= 0.06
    assert settings.MAX_SAME_DIRECTION_TRADES == 3
    assert round(
        settings.FIXED_LOT
        * settings.MAX_SAME_DIRECTION_TRADES,
        2,
    ) <= 0.21


if __name__ == "__main__":
    test_same_direction_exposure_cap()
    test_tp_split_does_not_increase_total_lot()
    test_risk_has_no_loss_based_escalation()
    test_recovery_uses_normal_trade_guard()
    test_protected_reentry_does_not_change_size()
    test_safe_runtime_defaults()

    print(
        "[PASS] Phase 7A6B no-grid/no-martingale "
        "audit passed."
    )
