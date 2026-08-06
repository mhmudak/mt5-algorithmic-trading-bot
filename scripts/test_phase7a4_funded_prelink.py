from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from src.funded_account_safe_mode import (
    evaluate_funded_account_activation,
    evaluate_funded_account_safe_mode,
)
from src.prop_firm_news_guard import (
    evaluate_prop_firm_news_restriction,
)


PROFILE_NAME = "GETLEVERAGED_TURBO_EVALUATION_50K"
GMT3 = timezone(timedelta(hours=3))
NOW = datetime(
    2026,
    8,
    6,
    15,
    30,
    tzinfo=GMT3,
)


def configured_profile():
    profile = settings.PROP_FIRM_PROFILES.get(
        PROFILE_NAME
    )

    assert isinstance(profile, dict)
    return dict(profile)


def synthetic_profile():
    profile = configured_profile()

    profile.update({
        "activation_require_explicit_identity": True,
        "expected_login": "777001",
        "expected_server": "GetLeveraged-Test",
        "expected_currency": "USD",
    })

    return profile


def account(
    *,
    login=777001,
    server="GetLeveraged-Test",
    balance=50000.0,
    equity=50000.0,
):
    return SimpleNamespace(
        login=login,
        server=server,
        currency="USD",
        balance=balance,
        equity=equity,
    )


class FakeMT5:
    def __init__(self, account_info):
        self._account_info = account_info

    def account_info(self):
        return self._account_info

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(
            time=NOW.astimezone(
                timezone.utc
            ).timestamp()
        )


def test_default_mode_remains_disabled():
    assert settings.ENABLE_PROP_FIRM_SAFE_MODE is False
    assert settings.PROP_FIRM_PROFILE == PROFILE_NAME


def test_profile_configuration():
    profile = configured_profile()

    expected = {
        "firm": "GETLEVERAGED",
        "program": "TURBO",
        "stage": "EVALUATION",
        "initial_balance": 50000.0,
        "official_daily_loss_pct": 3.0,
        "official_trailing_drawdown_pct": 6.0,
        "daily_safety_buffer_pct": 0.5,
        "trailing_safety_buffer_pct": 0.5,
        "news_before_minutes": 5,
        "news_after_minutes": 5,
    }

    for key, value in expected.items():
        assert profile.get(key) == value, (
            f"{key}: expected={value!r} "
            f"actual={profile.get(key)!r}"
        )

    assert (
        profile.get("activation_require_explicit_identity")
        is True
    )
    assert profile.get("news_calendar_fail_closed") is True
    assert (
        profile.get(
            "news_block_automated_position_closes"
        )
        is True
    )
    assert (
        profile.get("news_freeze_sl_tp_modifications")
        is True
    )
    assert (
        profile.get("news_preserve_existing_sl_tp")
        is True
    )


def test_correct_50k_activation_simulation():
    profile = synthetic_profile()

    result = evaluate_funded_account_activation(
        account=account(),
        enabled=True,
        profile_name=PROFILE_NAME,
        profile=profile,
        fail_closed=True,
    )

    assert result["allowed"] is True
    assert (
        result["reason"]
        == "funded_account_activation_allowed"
    )
    assert result["snapshot"]["orders_sent"] == 0


def test_wrong_account_refusal_simulation():
    profile = synthetic_profile()

    wrong_login = evaluate_funded_account_activation(
        account=account(login=999999),
        enabled=True,
        profile_name=PROFILE_NAME,
        profile=profile,
        fail_closed=True,
    )

    assert wrong_login["allowed"] is False
    assert (
        wrong_login["reason"]
        == "funded_account_login_mismatch"
    )

    wrong_size = evaluate_funded_account_activation(
        account=account(balance=6000.0, equity=6000.0),
        enabled=True,
        profile_name=PROFILE_NAME,
        profile=profile,
        fail_closed=True,
    )

    assert wrong_size["allowed"] is False
    assert (
        wrong_size["reason"]
        == "funded_account_size_mismatch"
    )


def test_healthy_50k_risk_snapshot():
    profile = synthetic_profile()
    fake = FakeMT5(account())

    result = evaluate_funded_account_safe_mode(
        mt5_module=fake,
        symbol="XAUUSD",
        trade_plan={
            "setup_id": "PHASE7A4-HEALTHY",
            "strategy": "SYNTHETIC_TEST",
        },
        enabled=True,
        profile_name=PROFILE_NAME,
        profiles={PROFILE_NAME: profile},
        fail_closed=True,
        state={},
        persist_state=False,
        now=NOW,
    )

    assert result["allowed"] is True

    snapshot = result.get("snapshot") or {}

    required_snapshot_fields = (
        "safe_daily_floor",
        "safe_trailing_floor",
        "active_floor_type",
    )

    for field in required_snapshot_fields:
        assert field in snapshot, (
            f"Missing risk snapshot field: {field}"
        )

    safe_daily_floor = float(
        snapshot["safe_daily_floor"]
    )
    safe_trailing_floor = float(
        snapshot["safe_trailing_floor"]
    )

    # The production engine derives the effective blocking floor
    # from the stricter of the daily and trailing safety floors.
    effective_floor = max(
        safe_daily_floor,
        safe_trailing_floor,
    )

    assert safe_daily_floor == 48750.0
    assert safe_trailing_floor == 47250.0
    assert effective_floor == 48750.0
    assert snapshot["active_floor_type"] == "DAILY"


def synthetic_calendar():
    return {
        "available": True,
        "provider": "SYNTHETIC_TEST",
        "events": [
            {
                "name": "Synthetic High Impact",
                "time": NOW,
                "currency": "USD",
                "impact": "High",
                "source": "SYNTHETIC_TEST",
            }
        ],
        "error": None,
    }


def test_every_restricted_news_action():
    profile = synthetic_profile()

    restricted_actions = (
        "OPEN_POSITION",
        "INCREASE_POSITION",
        "PLACE_PENDING_ORDER",
        "PARTIAL_CLOSE_POSITION",
        "FULL_CLOSE_POSITION",
        "MODIFY_PROTECTIVE_SL_TP",
    )

    for action in restricted_actions:
        result = evaluate_prop_firm_news_restriction(
            enabled=True,
            profile_name=PROFILE_NAME,
            profile=profile,
            calendar_snapshot=synthetic_calendar(),
            action=action,
            now=NOW,
            fail_closed=True,
        )

        assert result["allowed"] is False, action
        assert (
            result["reason"]
            == "prop_firm_restricted_news_window_active"
        )
        assert result["snapshot"]["orders_sent"] == 0

    broker_protection = (
        evaluate_prop_firm_news_restriction(
            enabled=True,
            profile_name=PROFILE_NAME,
            profile=profile,
            calendar_snapshot=synthetic_calendar(),
            action="BROKER_TRIGGERED_SL_TP",
            now=NOW,
            fail_closed=True,
        )
    )

    assert broker_protection["allowed"] is True


def test_final_source_guards_exist():
    required_markers = {
        ROOT / "src" / "order_executor.py": (
            "PROP FIRM NEWS GUARD",
        ),
        ROOT / "src" / "position_manager.py": (
            "PROP FIRM NEWS EXIT GUARD",
            "PROP FIRM NEWS PROTECTION GUARD",
        ),
        ROOT / "src" / "manual_trailing_manager.py": (
            "PROP FIRM NEWS PROTECTION GUARD",
        ),
        ROOT / "src" / "emergency_close.py": (
            "PROP FIRM NEWS EMERGENCY GUARD",
        ),
        ROOT / "src" / "telegram_signal_executor.py": (
            "PROP FIRM NEWS TELEGRAM GUARD",
        ),
        ROOT / "src" / "live_bot.py": (
            "emergency_result = close_all_positions",
            "Bot remains active and will retry",
        ),
    }

    for path, markers in required_markers.items():
        source = path.read_text(encoding="utf-8")

        for marker in markers:
            assert marker in source, (
                f"Missing marker {marker!r} in {path}"
            )


if __name__ == "__main__":
    test_default_mode_remains_disabled()
    test_profile_configuration()
    test_correct_50k_activation_simulation()
    test_wrong_account_refusal_simulation()
    test_healthy_50k_risk_snapshot()
    test_every_restricted_news_action()
    test_final_source_guards_exist()

    print(
        "[PASS] Phase 7A4 funded pre-link "
        "simulation passed."
    )
