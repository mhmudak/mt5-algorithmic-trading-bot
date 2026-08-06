from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.funded_account_safe_mode import (
    evaluate_funded_account_activation,
    evaluate_funded_account_safe_mode,
)


PROFILE_NAME = "GETLEVERAGED_TURBO_EVALUATION_50K"
GMT3 = timezone(timedelta(hours=3))


def build_profile(**overrides):
    profile = {
        "firm": "GETLEVERAGED",
        "program": "TURBO",
        "stage": "EVALUATION",
        "initial_balance": 50000.0,
        "activation_require_explicit_identity": True,
        "expected_login": "777001",
        "expected_server": "GetLeveraged-Server",
        "expected_currency": "USD",
        "activation_balance_tolerance_pct": 10.0,
        "official_daily_loss_pct": 3.0,
        "official_trailing_drawdown_pct": 6.0,
        "daily_safety_buffer_pct": 0.5,
        "trailing_safety_buffer_pct": 0.5,
        "daily_reset_hour_gmt3": 23,
        "daily_reset_minute_gmt3": 0,
        "trailing_floor_locks_at_initial_balance": True,
    }
    profile.update(overrides)
    return profile


def build_account(
    *,
    login=777001,
    server="GetLeveraged-Server",
    currency="USD",
    balance=50000.0,
    equity=50000.0,
):
    return SimpleNamespace(
        login=login,
        server=server,
        currency=currency,
        balance=balance,
        equity=equity,
    )


def activate(account, profile=None, enabled=True):
    return evaluate_funded_account_activation(
        account=account,
        enabled=enabled,
        profile_name=PROFILE_NAME,
        profile=profile or build_profile(),
        fail_closed=True,
    )


def test_disabled_guard_allows_without_validation():
    result = activate(
        build_account(login=999),
        enabled=False,
    )

    assert result["allowed"] is True
    assert result["reason"] == "funded_safe_mode_disabled"


def test_missing_explicit_identity_blocks_activation():
    result = activate(
        build_account(),
        profile=build_profile(expected_login=None),
    )

    assert result["allowed"] is False
    assert (
        result["reason"]
        == "funded_account_identity_not_configured"
    )


def test_wrong_login_is_blocked():
    result = activate(build_account(login=888002))

    assert result["allowed"] is False
    assert result["reason"] == "funded_account_login_mismatch"
    assert result["snapshot"]["orders_sent"] == 0


def test_wrong_server_is_blocked():
    result = activate(
        build_account(server="Wrong-Server")
    )

    assert result["allowed"] is False
    assert result["reason"] == "funded_account_server_mismatch"


def test_wrong_currency_is_blocked():
    result = activate(build_account(currency="EUR"))

    assert result["allowed"] is False
    assert result["reason"] == "funded_account_currency_mismatch"


def test_wrong_account_size_is_blocked():
    result = activate(build_account(balance=5940.73))

    assert result["allowed"] is False
    assert result["reason"] == "funded_account_size_mismatch"
    assert result["snapshot"]["minimum_allowed_balance"] == 45000.0
    assert result["snapshot"]["maximum_allowed_balance"] == 55000.0


def test_correct_account_is_allowed():
    result = activate(build_account(balance=50000.0))

    assert result["allowed"] is True
    assert result["reason"] == "funded_account_activation_allowed"


class FakeMT5:
    def __init__(self, account):
        self.account = account

    def account_info(self):
        return self.account

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(
            time=datetime(
                2026,
                8,
                6,
                12,
                0,
                tzinfo=GMT3,
            ).astimezone(timezone.utc).timestamp()
        )


def test_safe_mode_refuses_wrong_account_before_risk_checks():
    profile = build_profile()
    fake = FakeMT5(build_account(login=999999))

    result = evaluate_funded_account_safe_mode(
        mt5_module=fake,
        symbol="XAUUSD",
        trade_plan={
            "setup_id": "ACTIVATION-TEST",
            "strategy": "FAILED_FVG_REVERSAL",
        },
        enabled=True,
        profile_name=PROFILE_NAME,
        profiles={PROFILE_NAME: profile},
        fail_closed=True,
        state={},
        persist_state=False,
        now=datetime(
            2026,
            8,
            6,
            12,
            0,
            tzinfo=GMT3,
        ),
    )

    assert result["allowed"] is False
    assert result["reason"] == "funded_account_login_mismatch"


def test_current_settings_remain_safe():
    settings = (
        ROOT / "config" / "settings.py"
    ).read_text(encoding="utf-8")

    assert "ENABLE_PROP_FIRM_SAFE_MODE = False" in settings
    assert '"activation_require_explicit_identity": True' in settings
    assert '"expected_login": None' in settings
    assert '"activation_balance_tolerance_pct": 10.0' in settings


if __name__ == "__main__":
    test_disabled_guard_allows_without_validation()
    test_missing_explicit_identity_blocks_activation()
    test_wrong_login_is_blocked()
    test_wrong_server_is_blocked()
    test_wrong_currency_is_blocked()
    test_wrong_account_size_is_blocked()
    test_correct_account_is_allowed()
    test_safe_mode_refuses_wrong_account_before_risk_checks()
    test_current_settings_remain_safe()

    print("[PASS] Phase 7A2 funded activation guard passed.")
