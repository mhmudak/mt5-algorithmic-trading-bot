from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from src.account_context import get_account_file


STATE_VERSION = 2
STATE_FILENAME = "funded_safe_mode_state.json"
GMT_PLUS_3 = timezone(timedelta(hours=3))


def _get_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)

    return getattr(obj, key, default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def get_funded_safe_mode_state_file() -> Path:
    return get_account_file(STATE_FILENAME)


def load_funded_safe_mode_state() -> Dict[str, Any]:
    path = get_funded_safe_mode_state_file()

    if not path.exists() or path.stat().st_size == 0:
        return {}

    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)

        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def save_funded_safe_mode_state(state: Dict[str, Any]) -> Path:
    path = get_funded_safe_mode_state_file()
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(path.suffix + ".tmp")

    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(
            state,
            handle,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )

    temporary.replace(path)
    return path


def _resolve_gmt3_time(
    mt5_module: Any,
    symbol: Optional[str],
    now: Optional[datetime],
) -> datetime:
    if now is not None:
        if now.tzinfo is None:
            return now.replace(tzinfo=GMT_PLUS_3)

        return now.astimezone(GMT_PLUS_3)

    try:
        tick = mt5_module.symbol_info_tick(symbol) if symbol else None
        timestamp = _get_value(tick, "time")

        if timestamp:
            return datetime.fromtimestamp(
                float(timestamp),
                tz=timezone.utc,
            ).astimezone(GMT_PLUS_3)
    except Exception:
        pass

    return datetime.now(tz=GMT_PLUS_3)


def _risk_day_key(
    current_time: datetime,
    reset_hour: int,
    reset_minute: int,
) -> str:
    reset_today = current_time.replace(
        hour=reset_hour,
        minute=reset_minute,
        second=0,
        microsecond=0,
    )

    if current_time < reset_today:
        return (current_time - timedelta(days=1)).date().isoformat()

    return current_time.date().isoformat()


def _decision(
    *,
    allowed: bool,
    reason: str,
    profile_name: str,
    snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "allowed": bool(allowed),
        "reason": reason,
        "profile": profile_name,
        "snapshot": snapshot or {},
    }


def evaluate_funded_account_activation(
    *,
    account: Any,
    enabled: bool,
    profile_name: str,
    profile: Optional[Dict[str, Any]],
    fail_closed: bool = True,
) -> Dict[str, Any]:
    """
    Verify that funded-account safe mode is being activated against
    the intended MT5 account.

    This function never submits, modifies, or closes an order.
    """
    normalized_profile = str(profile_name or "").strip().upper()

    if not enabled:
        return _decision(
            allowed=True,
            reason="funded_safe_mode_disabled",
            profile_name=normalized_profile,
        )

    if not isinstance(profile, dict):
        return _decision(
            allowed=not fail_closed,
            reason="funded_profile_missing",
            profile_name=normalized_profile,
        )

    if account is None:
        return _decision(
            allowed=not fail_closed,
            reason="account_info_unavailable",
            profile_name=normalized_profile,
        )

    connected_login = str(
        _get_value(account, "login", "") or ""
    ).strip()
    connected_server = str(
        _get_value(account, "server", "") or ""
    ).strip()
    connected_currency = str(
        _get_value(account, "currency", "") or ""
    ).strip().upper()
    connected_balance = _safe_float(
        _get_value(account, "balance")
    )

    expected_login = str(
        profile.get("expected_login") or ""
    ).strip()
    expected_server = str(
        profile.get("expected_server") or ""
    ).strip()
    expected_currency = str(
        profile.get("expected_currency") or ""
    ).strip().upper()

    require_explicit_identity = bool(
        profile.get(
            "activation_require_explicit_identity",
            True,
        )
    )

    expected_balance = _safe_float(
        profile.get("initial_balance")
    )
    balance_tolerance_pct = max(
        _safe_float(
            profile.get(
                "activation_balance_tolerance_pct",
                10.0,
            )
        ),
        0.0,
    )

    balance_tolerance_amount = (
        expected_balance * balance_tolerance_pct / 100.0
    )
    minimum_allowed_balance = (
        expected_balance - balance_tolerance_amount
    )
    maximum_allowed_balance = (
        expected_balance + balance_tolerance_amount
    )

    snapshot = {
        "connected_login": connected_login,
        "connected_server": connected_server,
        "connected_currency": connected_currency,
        "connected_balance": round(connected_balance, 2),
        "expected_login": expected_login or "NOT_CONFIGURED",
        "expected_server": expected_server or "NOT_CONFIGURED",
        "expected_currency": (
            expected_currency or "NOT_CONFIGURED"
        ),
        "expected_initial_balance": round(
            expected_balance,
            2,
        ),
        "balance_tolerance_pct": balance_tolerance_pct,
        "minimum_allowed_balance": round(
            minimum_allowed_balance,
            2,
        ),
        "maximum_allowed_balance": round(
            maximum_allowed_balance,
            2,
        ),
        "orders_sent": 0,
    }

    if require_explicit_identity and not expected_login:
        return _decision(
            allowed=False,
            reason="funded_account_identity_not_configured",
            profile_name=normalized_profile,
            snapshot=snapshot,
        )

    if not connected_login:
        return _decision(
            allowed=not fail_closed,
            reason="funded_account_login_unavailable",
            profile_name=normalized_profile,
            snapshot=snapshot,
        )

    if expected_login and connected_login != expected_login:
        return _decision(
            allowed=False,
            reason="funded_account_login_mismatch",
            profile_name=normalized_profile,
            snapshot=snapshot,
        )

    if (
        expected_server
        and connected_server.casefold()
        != expected_server.casefold()
    ):
        return _decision(
            allowed=False,
            reason="funded_account_server_mismatch",
            profile_name=normalized_profile,
            snapshot=snapshot,
        )

    if (
        expected_currency
        and connected_currency
        and connected_currency != expected_currency
    ):
        return _decision(
            allowed=False,
            reason="funded_account_currency_mismatch",
            profile_name=normalized_profile,
            snapshot=snapshot,
        )

    if connected_balance <= 0:
        return _decision(
            allowed=not fail_closed,
            reason="funded_account_balance_unavailable",
            profile_name=normalized_profile,
            snapshot=snapshot,
        )

    if (
        expected_balance > 0
        and not (
            minimum_allowed_balance
            <= connected_balance
            <= maximum_allowed_balance
        )
    ):
        return _decision(
            allowed=False,
            reason="funded_account_size_mismatch",
            profile_name=normalized_profile,
            snapshot=snapshot,
        )

    return _decision(
        allowed=True,
        reason="funded_account_activation_allowed",
        profile_name=normalized_profile,
        snapshot=snapshot,
    )


def evaluate_funded_account_safe_mode(
    *,
    mt5_module: Any,
    symbol: Optional[str],
    trade_plan: Optional[Dict[str, Any]],
    enabled: bool,
    profile_name: str,
    profiles: Dict[str, Dict[str, Any]],
    fail_closed: bool = True,
    account_wide: bool = True,
    state: Optional[Dict[str, Any]] = None,
    persist_state: bool = True,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    # Equity and drawdown limits already apply to the whole MT5 account.
    del account_wide

    normalized_profile = str(profile_name or "").strip().upper()

    if not enabled:
        return _decision(
            allowed=True,
            reason="funded_safe_mode_disabled",
            profile_name=normalized_profile,
        )

    profile = (profiles or {}).get(normalized_profile)

    if not isinstance(profile, dict):
        return _decision(
            allowed=not fail_closed,
            reason="funded_profile_missing",
            profile_name=normalized_profile,
        )

    try:
        account = mt5_module.account_info()
    except Exception:
        account = None

    if account is None:
        return _decision(
            allowed=not fail_closed,
            reason="account_info_unavailable",
            profile_name=normalized_profile,
        )

    activation_decision = evaluate_funded_account_activation(
        account=account,
        enabled=True,
        profile_name=normalized_profile,
        profile=profile,
        fail_closed=fail_closed,
    )

    if not activation_decision.get("allowed", False):
        return activation_decision

    balance = _safe_float(_get_value(account, "balance"))
    equity = _safe_float(_get_value(account, "equity"))

    if balance <= 0 or equity <= 0:
        return _decision(
            allowed=not fail_closed,
            reason="invalid_account_balance_or_equity",
            profile_name=normalized_profile,
            snapshot={
                "balance": balance,
                "equity": equity,
            },
        )

    initial_balance = _safe_float(profile.get("initial_balance"))

    if initial_balance <= 0:
        return _decision(
            allowed=not fail_closed,
            reason="invalid_profile_initial_balance",
            profile_name=normalized_profile,
        )

    official_daily_pct = _safe_float(
        profile.get("official_daily_loss_pct")
    )
    official_trailing_pct = _safe_float(
        profile.get("official_trailing_drawdown_pct")
    )

    daily_buffer_pct = max(
        _safe_float(profile.get("daily_safety_buffer_pct")),
        0.0,
    )
    trailing_buffer_pct = max(
        _safe_float(profile.get("trailing_safety_buffer_pct")),
        0.0,
    )

    reset_hour = int(profile.get("daily_reset_hour_gmt3", 23))
    reset_minute = int(profile.get("daily_reset_minute_gmt3", 0))

    current_time = _resolve_gmt3_time(
        mt5_module,
        symbol,
        now,
    )

    current_risk_day = _risk_day_key(
        current_time,
        reset_hour,
        reset_minute,
    )

    active_state = (
        state
        if isinstance(state, dict)
        else load_funded_safe_mode_state()
    )

    login = str(_get_value(account, "login", ""))
    server = str(_get_value(account, "server", ""))

    state_is_stale = (
        int(active_state.get("version") or 0) != STATE_VERSION
        or str(active_state.get("login") or "") != login
        or str(active_state.get("server") or "") != server
        or str(active_state.get("profile") or "") != normalized_profile
    )

    if state_is_stale:
        active_state.clear()

    if active_state.get("risk_day_key") != current_risk_day:
        daily_reference = max(balance, equity)
        daily_reference_captured_at = current_time.isoformat()
    else:
        daily_reference = _safe_float(
            active_state.get("daily_reference"),
            max(balance, equity),
        )
        daily_reference_captured_at = active_state.get(
            "daily_reference_captured_at",
            current_time.isoformat(),
        )

    highest_closed_balance = max(
        initial_balance,
        _safe_float(
            active_state.get("highest_closed_balance"),
            initial_balance,
        ),
        balance,
    )

    daily_loss_amount = (
        initial_balance * official_daily_pct / 100.0
    )
    daily_buffer_amount = (
        initial_balance * daily_buffer_pct / 100.0
    )

    official_daily_floor = (
        daily_reference - daily_loss_amount
    )
    safe_daily_floor = (
        official_daily_floor + daily_buffer_amount
    )

    trailing_loss_amount = (
        initial_balance * official_trailing_pct / 100.0
    )
    trailing_buffer_amount = (
        initial_balance * trailing_buffer_pct / 100.0
    )

    raw_trailing_floor = (
        highest_closed_balance - trailing_loss_amount
    )

    if bool(
        profile.get(
            "trailing_floor_locks_at_initial_balance",
            True,
        )
    ):
        official_trailing_floor = min(
            raw_trailing_floor,
            initial_balance,
        )
    else:
        official_trailing_floor = raw_trailing_floor

    safe_trailing_floor = (
        official_trailing_floor + trailing_buffer_amount
    )

    effective_safe_floor = max(
        safe_daily_floor,
        safe_trailing_floor,
    )

    active_floor_type = (
        "DAILY"
        if safe_daily_floor >= safe_trailing_floor
        else "TRAILING"
    )

    active_state.update(
        {
            "version": STATE_VERSION,
            "login": login,
            "server": server,
            "profile": normalized_profile,
            "risk_day_key": current_risk_day,
            "daily_reference": round(daily_reference, 2),
            "daily_reference_captured_at": (
                daily_reference_captured_at
            ),
            "highest_closed_balance": round(
                highest_closed_balance,
                2,
            ),
            "last_balance": round(balance, 2),
            "last_equity": round(equity, 2),
            "last_checked_at": current_time.isoformat(),
        }
    )

    if persist_state:
        try:
            save_funded_safe_mode_state(active_state)
        except Exception:
            if fail_closed:
                return _decision(
                    allowed=False,
                    reason="funded_state_persistence_failed",
                    profile_name=normalized_profile,
                )

    snapshot = {
        "firm": profile.get("firm"),
        "program": profile.get("program"),
        "stage": profile.get("stage"),
        "activation": activation_decision.get(
            "snapshot",
            {},
        ),
        "broker_time_gmt3": current_time.isoformat(),
        "risk_day_key": current_risk_day,
        "balance": round(balance, 2),
        "equity": round(equity, 2),
        "initial_balance": round(initial_balance, 2),
        "daily_reference": round(daily_reference, 2),
        "official_daily_loss_pct": official_daily_pct,
        "daily_safety_buffer_pct": daily_buffer_pct,
        "official_daily_floor": round(
            official_daily_floor,
            2,
        ),
        "safe_daily_floor": round(safe_daily_floor, 2),
        "highest_closed_balance": round(
            highest_closed_balance,
            2,
        ),
        "official_trailing_drawdown_pct": (
            official_trailing_pct
        ),
        "trailing_safety_buffer_pct": trailing_buffer_pct,
        "official_trailing_floor": round(
            official_trailing_floor,
            2,
        ),
        "safe_trailing_floor": round(
            safe_trailing_floor,
            2,
        ),
        "effective_safe_floor": round(
            effective_safe_floor,
            2,
        ),
        "active_floor_type": active_floor_type,
        "equity_safety_margin": round(
            equity - effective_safe_floor,
            2,
        ),
        "max_open_positions": "UNLIMITED",
        "max_daily_entries": "UNLIMITED",
        "tick_sniper_blocked": False,
        "setup_id": (
            trade_plan.get("setup_id")
            if isinstance(trade_plan, dict)
            else None
        ),
        "strategy": (
            trade_plan.get("strategy")
            if isinstance(trade_plan, dict)
            else None
        ),
    }

    if equity <= effective_safe_floor:
        reason = (
            "funded_daily_safety_floor_reached"
            if active_floor_type == "DAILY"
            else "funded_trailing_safety_floor_reached"
        )

        return _decision(
            allowed=False,
            reason=reason,
            profile_name=normalized_profile,
            snapshot=snapshot,
        )

    return _decision(
        allowed=True,
        reason="funded_safe_mode_allowed",
        profile_name=normalized_profile,
        snapshot=snapshot,
    )
