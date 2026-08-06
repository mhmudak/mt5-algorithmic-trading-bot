from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.funded_account_safe_mode import (
    evaluate_funded_account_safe_mode,
)


LIVE = ROOT / "src" / "live_bot.py"
SETTINGS = ROOT / "config" / "settings.py"

GMT3 = timezone(timedelta(hours=3))

PROFILE_NAME = "GETLEVERAGED_TURBO_EVALUATION_50K"

PROFILES = {
    PROFILE_NAME: {
        "firm": "GETLEVERAGED",
        "program": "TURBO",
        "stage": "EVALUATION",
        "initial_balance": 50000.0,

        # Phase 7A2 identity values matching FakeMT5.account_info().
        "activation_require_explicit_identity": True,
        "expected_login": "123456",
        "expected_server": "GetLeveraged-Test",
        "expected_currency": None,
        "activation_balance_tolerance_pct": 10.0,

        "official_daily_loss_pct": 3.0,
        "official_trailing_drawdown_pct": 6.0,
        "daily_safety_buffer_pct": 0.5,
        "trailing_safety_buffer_pct": 0.5,
        "daily_reset_hour_gmt3": 23,
        "daily_reset_minute_gmt3": 0,
        "trailing_floor_locks_at_initial_balance": True,
        "max_open_positions": None,
        "max_daily_entries": None,
        "block_tick_sniper": False,
        "notify_telegram": True,
    }
}


class FakeMT5:
    def __init__(
        self,
        *,
        balance=50000.0,
        equity=50000.0,
        now=None,
    ):
        self.balance = balance
        self.equity = equity
        self.now = now or datetime(
            2026,
            8,
            6,
            12,
            0,
            tzinfo=GMT3,
        )

    def account_info(self):
        return SimpleNamespace(
            login=123456,
            server="GetLeveraged-Test",
            balance=self.balance,
            equity=self.equity,
        )

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(
            time=self.now.astimezone(timezone.utc).timestamp()
        )


def evaluate(fake, state=None, trade_plan=None):
    return evaluate_funded_account_safe_mode(
        mt5_module=fake,
        symbol="XAUUSD",
        trade_plan=trade_plan or {
            "setup_id": "TEST-SETUP",
            "strategy": "TEST_STRATEGY",
        },
        enabled=True,
        profile_name=PROFILE_NAME,
        profiles=PROFILES,
        fail_closed=True,
        state=state if state is not None else {},
        persist_state=False,
        now=fake.now,
    )


def test_healthy_account_is_allowed():
    result = evaluate(FakeMT5())

    assert result["allowed"] is True
    assert result["reason"] == "funded_safe_mode_allowed"


def test_daily_safety_floor_blocks_before_official_breach():
    state = {}

    first = FakeMT5(balance=50000.0, equity=50000.0)
    assert evaluate(first, state=state)["allowed"] is True

    # Official floor = 48,500; internal safe floor = 48,750.
    second = FakeMT5(balance=50000.0, equity=48740.0)
    result = evaluate(second, state=state)

    assert result["allowed"] is False
    assert result["reason"] == "funded_daily_safety_floor_reached"
    assert result["snapshot"]["official_daily_floor"] == 48500.0
    assert result["snapshot"]["safe_daily_floor"] == 48750.0


def test_trailing_floor_follows_highest_closed_balance():
    state = {}

    peak = FakeMT5(
        balance=52000.0,
        equity=52000.0,
        now=datetime(
            2026,
            8,
            6,
            22,
            30,
            tzinfo=GMT3,
        ),
    )
    assert evaluate(peak, state=state)["allowed"] is True

    # Start the new risk day from 50,000 while preserving
    # the 52,000 highest closed-balance watermark.
    reset = FakeMT5(
        balance=50000.0,
        equity=50000.0,
        now=datetime(
            2026,
            8,
            6,
            23,
            0,
            tzinfo=GMT3,
        ),
    )
    assert evaluate(reset, state=state)["allowed"] is True

    # Daily safe floor = 48,750.
    # Trailing safe floor = 49,250, so trailing is active.
    pullback = FakeMT5(
        balance=50000.0,
        equity=49240.0,
        now=datetime(
            2026,
            8,
            6,
            23,
            10,
            tzinfo=GMT3,
        ),
    )
    result = evaluate(pullback, state=state)

    assert result["allowed"] is False
    assert result["reason"] == "funded_trailing_safety_floor_reached"
    assert result["snapshot"]["highest_closed_balance"] == 52000.0
    assert result["snapshot"]["official_trailing_floor"] == 49000.0
    assert result["snapshot"]["safe_trailing_floor"] == 49250.0


def test_trailing_floor_locks_at_initial_balance():
    state = {}

    peak = FakeMT5(balance=53000.0, equity=53000.0)
    result = evaluate(peak, state=state)

    assert result["allowed"] is True
    assert result["snapshot"]["official_trailing_floor"] == 50000.0
    assert result["snapshot"]["safe_trailing_floor"] == 50250.0


def test_daily_reference_resets_at_2300_gmt3():
    state = {}

    before_reset = FakeMT5(
        balance=50000.0,
        equity=50100.0,
        now=datetime(2026, 8, 6, 22, 59, tzinfo=GMT3),
    )
    evaluate(before_reset, state=state)

    old_key = state["risk_day_key"]
    old_reference = state["daily_reference"]

    after_reset = FakeMT5(
        balance=50200.0,
        equity=50300.0,
        now=datetime(2026, 8, 6, 23, 0, tzinfo=GMT3),
    )
    evaluate(after_reset, state=state)

    assert state["risk_day_key"] != old_key
    assert old_reference == 50100.0
    assert state["daily_reference"] == 50300.0


def test_tick_sniper_is_not_blocked_by_name():
    result = evaluate(
        FakeMT5(),
        trade_plan={
            "setup_id": "TICK-SNIPER-1",
            "strategy": "TICK_SNIPER",
        },
    )

    assert result["allowed"] is True
    assert result["snapshot"]["tick_sniper_blocked"] is False


def test_no_position_or_daily_entry_limit():
    result = evaluate(FakeMT5())

    assert result["snapshot"]["max_open_positions"] == "UNLIMITED"
    assert result["snapshot"]["max_daily_entries"] == "UNLIMITED"


def test_missing_account_info_fails_closed():
    fake = FakeMT5()
    fake.account_info = lambda: None

    result = evaluate(fake)

    assert result["allowed"] is False
    assert result["reason"] == "account_info_unavailable"


def test_live_bot_markers_exist():
    text = LIVE.read_text(encoding="utf-8")

    assert "FUNDED_SAFE_MODE_BLOCKED" in text
    assert "Daily Safety Floor" in text
    assert "Trailing Safety Floor" in text
    assert "Remaining Safety Margin" in text


def test_settings_profile_exists():
    text = SETTINGS.read_text(encoding="utf-8")

    assert (
        'PROP_FIRM_PROFILE = '
        '"GETLEVERAGED_TURBO_EVALUATION_50K"'
    ) in text
    assert '"official_daily_loss_pct": 3.0' in text
    assert '"official_trailing_drawdown_pct": 6.0' in text
    assert '"max_open_positions": None' in text
    assert '"max_daily_entries": None' in text
    assert '"block_tick_sniper": False' in text


if __name__ == "__main__":
    test_healthy_account_is_allowed()
    test_daily_safety_floor_blocks_before_official_breach()
    test_trailing_floor_follows_highest_closed_balance()
    test_trailing_floor_locks_at_initial_balance()
    test_daily_reference_resets_at_2300_gmt3()
    test_tick_sniper_is_not_blocked_by_name()
    test_no_position_or_daily_entry_limit()
    test_missing_account_info_fails_closed()
    test_live_bot_markers_exist()
    test_settings_profile_exists()

    print("[PASS] Phase 7A1 GetLeveraged Turbo Evaluation safe mode passed.")
