from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


REQUIRED_ADAPTER_METRICS = [
    "bid_volume",
    "ask_volume",
    "delta",
    "cumulative_delta",
    "footprint_imbalance",
    "dom_bid_depth",
    "dom_ask_depth",
]


def load_latest_rithmic_state(path: str | Path) -> dict[str, Any]:
    p = Path(path)

    if not p.exists():
        return {
            "loaded": False,
            "error": f"snapshot_not_found: {p}",
            "path": str(p),
        }

    try:
        return {
            "loaded": True,
            "path": str(p),
            "snapshot": json.loads(p.read_text(encoding="utf-8")),
        }
    except Exception as exc:
        return {
            "loaded": False,
            "error": f"snapshot_read_error: {exc}",
            "path": str(p),
        }


def build_rithmic_provider_status(
    snapshot: dict[str, Any] | None,
    *,
    snapshot_path: str | Path,
    stale_after_seconds: int = 30,
) -> dict[str, Any]:
    """
    Normalize one Rithmic rolling-state snapshot for observe-only use.

    Safety invariants:
    - missing data stays None; zero is a real observation
    - freshness is recalculated at read time
    - stale files can never remain falsely fresh
    - this adapter never influences MT5 execution
    """

    now_epoch = time.time()

    try:
        stale_after_seconds = max(
            1,
            int(stale_after_seconds),
        )
    except (TypeError, ValueError):
        stale_after_seconds = 30

    def _positive_epoch(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None

        if value <= 0:
            return None

        return value

    def _nonnegative_age(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None

        if value < 0:
            return None

        return value

    if not snapshot:
        return {
            "phase": "PHASE_5F_RITHMIC_PROVIDER_STATUS",
            "provider_name": "RITHMIC_PROTOCOL",
            "source": "RITHMIC_STATE_SNAPSHOT",
            "snapshot_path": str(snapshot_path),
            "loaded": False,
            "provider_status": "SNAPSHOT_MISSING",
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "safe_for_live_decision": False,
            "safe_for_execution": False,
            "updated_at_epoch": now_epoch,
            "freshness": {
                "snapshot_age_seconds": None,
                "snapshot_fresh": False,
                "last_trade_age_seconds": None,
                "last_bbo_age_seconds": None,
                "last_order_book_age_seconds": None,
                "has_fresh_trade": False,
                "has_fresh_bbo": False,
                "has_fresh_order_book": False,
            },
            "connection": {
                "login_ok": False,
                "market_data_ok": False,
            },
            "sample": {},
            "latest_trade": {},
            "trade_flow": {},
            "volume_profile": {},
            "footprint": {
                "candle_count": 0,
            },
            "order_book": {
                "available": False,
                "last_update_type_name": None,
                "bid_level_count": None,
                "ask_level_count": None,
                "bid_depth": None,
                "ask_depth": None,
                "depth_imbalance": None,
                "top_bid_price": None,
                "top_ask_price": None,
            },
            "adapter_metrics": {
                key: None
                for key in REQUIRED_ADAPTER_METRICS
            },
            "required_adapter_metrics": (
                REQUIRED_ADAPTER_METRICS
            ),
            "warnings": [
                "RITHMIC_STATE_SNAPSHOT_NOT_FOUND",
                "DECISION_IMPACT_DISABLED",
            ],
        }

    connection = (
        snapshot.get("connection")
        or {}
    )

    stored_freshness = (
        snapshot.get("freshness")
        or {}
    )

    quality = (
        snapshot.get("quality")
        or {}
    )

    adapter_metrics = (
        snapshot.get(
            "adapter_compatible_metrics"
        )
        or {}
    )

    latest_trade = (
        snapshot.get("latest_trade")
        or {}
    )

    order_book = (
        snapshot.get("order_book")
        or {}
    )

    login_ok = bool(
        connection.get("login_ok")
    )

    market_data_ok = bool(
        connection.get("market_data_ok")
    )

    state_status = str(
        snapshot.get("state_status")
        or "UNKNOWN"
    ).strip().upper()

    snapshot_updated_at = _positive_epoch(
        snapshot.get("updated_at_epoch")
    )

    snapshot_age_seconds = None

    if snapshot_updated_at is not None:
        snapshot_age_seconds = max(
            0.0,
            round(
                now_epoch
                - snapshot_updated_at,
                3,
            ),
        )

    snapshot_fresh = bool(
        snapshot_age_seconds is not None
        and snapshot_age_seconds
        <= stale_after_seconds
    )

    # --------------------------------------------------------
    # Trade freshness.
    # Prefer the actual received timestamp.
    # If unavailable, age the stored age by file age.
    # --------------------------------------------------------

    trade_received_at = _positive_epoch(
        latest_trade.get(
            "received_at_epoch"
        )
    )

    if trade_received_at is not None:
        last_trade_age = max(
            0.0,
            round(
                now_epoch
                - trade_received_at,
                3,
            ),
        )
    else:
        last_trade_age = _nonnegative_age(
            stored_freshness.get(
                "last_trade_age_seconds"
            )
        )

        if (
            last_trade_age is not None
            and snapshot_age_seconds
            is not None
        ):
            last_trade_age = round(
                last_trade_age
                + snapshot_age_seconds,
                3,
            )

    has_fresh_trade = bool(
        snapshot_fresh
        and last_trade_age is not None
        and last_trade_age
        <= stale_after_seconds
    )

    # --------------------------------------------------------
    # BBO freshness.
    # The current state snapshot stores BBO age but not its
    # received timestamp, so add elapsed snapshot age.
    # --------------------------------------------------------

    last_bbo_age = _nonnegative_age(
        stored_freshness.get(
            "last_bbo_age_seconds"
        )
    )

    if (
        last_bbo_age is not None
        and snapshot_age_seconds
        is not None
    ):
        last_bbo_age = round(
            last_bbo_age
            + snapshot_age_seconds,
            3,
        )

    has_fresh_bbo = bool(
        snapshot_fresh
        and last_bbo_age is not None
        and last_bbo_age
        <= stale_after_seconds
    )

    # --------------------------------------------------------
    # DOM freshness.
    # --------------------------------------------------------

    order_book_received_at = (
        _positive_epoch(
            order_book.get(
                "last_received_at_epoch"
            )
        )
    )

    if order_book_received_at is not None:
        last_order_book_age = max(
            0.0,
            round(
                now_epoch
                - order_book_received_at,
                3,
            ),
        )
    else:
        last_order_book_age = (
            _nonnegative_age(
                stored_freshness.get(
                    "last_order_book_age_seconds"
                )
            )
        )

        if (
            last_order_book_age is not None
            and snapshot_age_seconds
            is not None
        ):
            last_order_book_age = round(
                last_order_book_age
                + snapshot_age_seconds,
                3,
            )

    has_fresh_order_book = bool(
        snapshot_fresh
        and last_order_book_age is not None
        and last_order_book_age
        <= stale_after_seconds
    )

    dom_available = bool(
        order_book.get("available")
        or adapter_metrics.get(
            "dom_available"
        )
    )

    # Missing values remain None.
    normalized_metrics = {
        key: adapter_metrics.get(key)
        for key in REQUIRED_ADAPTER_METRICS
    }

    normalized_metrics[
        "dom_depth_imbalance"
    ] = adapter_metrics.get(
        "dom_depth_imbalance"
    )

    normalized_metrics[
        "dom_available"
    ] = dom_available

    warnings = list(
        quality.get("warnings")
        or []
    )

    if not login_ok:
        provider_status = "LOGIN_NOT_OK"
        warnings.append(
            "RITHMIC_LOGIN_NOT_OK"
        )

    elif not market_data_ok:
        provider_status = (
            "MARKET_DATA_NOT_OK"
        )

        warnings.append(
            "RITHMIC_MARKET_DATA_NOT_OK"
        )

    elif not snapshot_fresh:
        provider_status = (
            "STALE_SNAPSHOT_OBSERVATION_ONLY"
        )

        warnings.append(
            "RITHMIC_STATE_SNAPSHOT_STALE"
        )

    elif not has_fresh_trade:
        provider_status = (
            "STALE_OR_LOW_ACTIVITY_"
            "OBSERVATION_ONLY"
        )

        warnings.append(
            "RITHMIC_TRADE_FLOW_NOT_FRESH"
        )

    elif (
        state_status
        == "LOW_SAMPLE_OBSERVATION_ONLY"
    ):
        provider_status = (
            "LOW_SAMPLE_OBSERVATION_ONLY"
        )

        warnings.append(
            "RITHMIC_LOW_SAMPLE_"
            "OBSERVATION_ONLY"
        )

    else:
        provider_status = (
            "OBSERVE_ONLY_READY"
        )

    if snapshot_updated_at is None:
        warnings.append(
            "RITHMIC_SNAPSHOT_UPDATED_AT_MISSING"
        )

    if (
        last_trade_age is not None
        and last_trade_age
        > stale_after_seconds
    ):
        warnings.append(
            "RITHMIC_TRADE_FLOW_"
            "STALE_FOR_CONTEXT_USE"
        )

    if snapshot.get(
        "is_test_environment"
    ):
        warnings.append(
            "RITHMIC_TEST_ENVIRONMENT_"
            "NOT_PRODUCTION"
        )

    if not dom_available:
        warnings.append(
            "DOM_NOT_AVAILABLE_OR_NO_BOOK"
        )

    warnings.append(
        "DECISION_IMPACT_DISABLED"
    )

    return {
        "phase": "PHASE_5F_RITHMIC_PROVIDER_STATUS",
        "provider_name": "RITHMIC_PROTOCOL",
        "source": "RITHMIC_STATE_SNAPSHOT",
        "snapshot_path": str(snapshot_path),
        "loaded": True,
        "symbol": snapshot.get("symbol"),
        "exchange": snapshot.get("exchange"),
        "system_name": snapshot.get(
            "system_name"
        ),
        "is_test_environment": snapshot.get(
            "is_test_environment"
        ),
        "provider_status": provider_status,
        "source_state_status": state_status,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_live_decision": False,
        "safe_for_execution": False,
        "updated_at_epoch": now_epoch,
        "freshness": {
            "snapshot_age_seconds": (
                snapshot_age_seconds
            ),
            "snapshot_fresh": snapshot_fresh,
            "last_trade_age_seconds": (
                last_trade_age
            ),
            "last_bbo_age_seconds": (
                last_bbo_age
            ),
            "last_order_book_age_seconds": (
                last_order_book_age
            ),
            "has_fresh_trade": (
                has_fresh_trade
            ),
            "has_fresh_bbo": (
                has_fresh_bbo
            ),
            "has_fresh_order_book": (
                has_fresh_order_book
            ),
        },
        "connection": {
            "login_ok": login_ok,
            "market_data_ok": market_data_ok,
        },
        "sample": (
            snapshot.get("sample")
            or {}
        ),
        "latest_trade": latest_trade,
        "trade_flow": (
            snapshot.get("trade_flow")
            or {}
        ),
        "volume_profile": (
            snapshot.get("volume_profile")
            or {}
        ),
        "footprint": {
            "candle_count": (
                snapshot.get("footprint")
                or {}
            ).get(
                "candle_count",
                0,
            ),
        },
        "order_book": {
            "available": dom_available,
            "last_update_type_name": (
                order_book.get(
                    "last_update_type_name"
                )
            ),
            "bid_level_count": (
                order_book.get(
                    "bid_level_count"
                )
            ),
            "ask_level_count": (
                order_book.get(
                    "ask_level_count"
                )
            ),
            "bid_depth": (
                order_book.get(
                    "bid_depth"
                )
            ),
            "ask_depth": (
                order_book.get(
                    "ask_depth"
                )
            ),
            "depth_imbalance": (
                order_book.get(
                    "depth_imbalance"
                )
            ),
            "top_bid_price": (
                order_book.get(
                    "top_bid_price"
                )
            ),
            "top_ask_price": (
                order_book.get(
                    "top_ask_price"
                )
            ),
        },
        "adapter_metrics": (
            normalized_metrics
        ),
        "required_adapter_metrics": (
            REQUIRED_ADAPTER_METRICS
        ),
        "warnings": sorted(
            set(warnings)
        ),
        "notes": [
            (
                "Rithmic data is connected "
                "through snapshot adapter only."
            ),
            (
                "This provider status is "
                "observe-only."
            ),
            (
                "No MT5 live execution decision "
                "may use this yet."
            ),
        ],
    }


def write_provider_status_text(status: dict[str, Any], output_path: str | Path) -> None:
    lines = [
        "PHASE 5F RITHMIC PROVIDER STATUS",
        "================================",
        f"provider_name: {status.get('provider_name')}",
        f"symbol: {status.get('symbol')}",
        f"exchange: {status.get('exchange')}",
        f"system_name: {status.get('system_name')}",
        f"is_test_environment: {status.get('is_test_environment')}",
        f"provider_status: {status.get('provider_status')}",
        f"source_state_status: {status.get('source_state_status')}",
        f"decision_impact: {status.get('decision_impact')}",
        f"can_influence_decision: {status.get('can_influence_decision')}",
        f"safe_for_live_decision: {status.get('safe_for_live_decision')}",
        "",
        "[CONNECTION]",
        f"login_ok: {status['connection']['login_ok']}",
        f"market_data_ok: {status['connection']['market_data_ok']}",
        "",
        "[FRESHNESS]",
        f"last_trade_age_seconds: {status['freshness']['last_trade_age_seconds']}",
        f"has_fresh_trade: {status['freshness']['has_fresh_trade']}",
        f"last_order_book_age_seconds: {status['freshness']['last_order_book_age_seconds']}",
        f"has_fresh_order_book: {status['freshness']['has_fresh_order_book']}",
        "",
        "[ADAPTER METRICS]",
    ]

    for key, value in (status.get("adapter_metrics") or {}).items():
        lines.append(f"{key}: {value}")

    lines.extend([
        "",
        "[ORDER BOOK]",
        f"available: {status['order_book']['available']}",
        f"last_update_type_name: {status['order_book']['last_update_type_name']}",
        f"bid_level_count: {status['order_book']['bid_level_count']}",
        f"ask_level_count: {status['order_book']['ask_level_count']}",
        f"bid_depth: {status['order_book']['bid_depth']}",
        f"ask_depth: {status['order_book']['ask_depth']}",
        f"depth_imbalance: {status['order_book']['depth_imbalance']}",
        "",
        "[WARNINGS]",
        ", ".join(status.get("warnings") or []),
        "",
        "NOTE:",
        "This file is observe-only and must not influence MT5 execution yet.",
    ])

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
