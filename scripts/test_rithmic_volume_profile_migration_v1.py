from __future__ import annotations

import tempfile
from pathlib import Path

from src.order_flow_features.rithmic_volume_profile_migration import (
    evaluate_rithmic_volume_profile_migration,
)


ROOT = Path(__file__).resolve().parents[1]


def integrity_ok():
    return {
        "integrity_ok": True,
        "continuity_valid": True,
    }


def snapshot(
    *,
    updated_at: float,
    poc: float,
    price: float,
    trade_count: int = 30,
    fresh_trade: bool = True,
):
    return {
        "symbol": "GCZ6",
        "exchange": "COMEX",
        "updated_at_epoch": updated_at,
        "freshness": {
            "has_fresh_trade": fresh_trade,
        },
        "sample": {
            "last_trade_count_total_session": trade_count,
            "rolling_trade_count": trade_count,
        },
        "latest_trade": {
            "price": price,
            "received_at_epoch": updated_at,
        },
        "volume_profile": {
            "rolling_poc_price": poc,
        },
    }


def run_pair(first, second, *, signal="BUY"):
    tmp = tempfile.TemporaryDirectory()
    path = Path(tmp.name) / "history.json"

    evaluate_rithmic_volume_profile_migration(
        first,
        history_path=path,
        feed_integrity=integrity_ok(),
        signal=signal,
        session="NEW_YORK_OPEN",
        tick_size=0.1,
    )

    result = evaluate_rithmic_volume_profile_migration(
        second,
        history_path=path,
        feed_integrity=integrity_ok(),
        signal=signal,
        session="NEW_YORK_OPEN",
        tick_size=0.1,
    )

    return tmp, result


def test_poc_migrates_up_with_price():
    tmp, result = run_pair(
        snapshot(
            updated_at=1.0,
            poc=2400.0,
            price=2400.1,
        ),
        snapshot(
            updated_at=2.0,
            poc=2400.3,
            price=2400.5,
            trade_count=60,
        ),
        signal="BUY",
    )

    try:
        assert result["status"] == "POC_MIGRATING_UP_WITH_PRICE"
        assert result["poc"]["migrating_up"] is True
        assert (
            result["signal_context"]["profile_supports_signal"]
            is True
        )
    finally:
        tmp.cleanup()


def test_poc_migrates_down_with_price():
    tmp, result = run_pair(
        snapshot(
            updated_at=1.0,
            poc=2400.5,
            price=2400.4,
        ),
        snapshot(
            updated_at=2.0,
            poc=2400.2,
            price=2400.0,
            trade_count=60,
        ),
        signal="SELL",
    )

    try:
        assert result["status"] == "POC_MIGRATING_DOWN_WITH_PRICE"
        assert result["poc"]["migrating_down"] is True
        assert (
            result["signal_context"]["profile_supports_signal"]
            is True
        )
    finally:
        tmp.cleanup()


def test_acceptance_near_stable_poc():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "history.json"

        evaluate_rithmic_volume_profile_migration(
            snapshot(
                updated_at=1.0,
                poc=2400.0,
                price=2400.1,
            ),
            history_path=path,
            feed_integrity=integrity_ok(),
            session="NEW_YORK_OPEN",
            tick_size=0.1,
        )

        result = evaluate_rithmic_volume_profile_migration(
            snapshot(
                updated_at=2.0,
                poc=2400.0,
                price=2399.9,
                trade_count=60,
            ),
            history_path=path,
            feed_integrity=integrity_ok(),
            session="NEW_YORK_OPEN",
            tick_size=0.1,
        )

        assert result["status"] == "PRICE_ACCEPTING_NEAR_STABLE_POC"
        assert (
            result["price_context"]["accepting_near_poc"]
            is True
        )


def test_rejection_up_from_poc():
    tmp, result = run_pair(
        snapshot(
            updated_at=1.0,
            poc=2400.0,
            price=2400.0,
        ),
        snapshot(
            updated_at=2.0,
            poc=2400.0,
            price=2400.4,
            trade_count=60,
        ),
        signal="BUY",
    )

    try:
        assert result["status"] == "PRICE_REJECTED_UP_FROM_POC"
        assert (
            result["price_context"]["rejection_above_poc"]
            is True
        )
        assert (
            result["signal_context"]["profile_supports_signal"]
            is True
        )
    finally:
        tmp.cleanup()


def test_migration_price_conflict():
    tmp, result = run_pair(
        snapshot(
            updated_at=1.0,
            poc=2400.0,
            price=2400.2,
        ),
        snapshot(
            updated_at=2.0,
            poc=2400.3,
            price=2400.1,
            trade_count=60,
        ),
        signal="BUY",
    )

    try:
        assert result["status"] == "POC_PRICE_MIGRATION_CONFLICT"
        assert (
            result["price_context"]["migration_price_conflict"]
            is True
        )
    finally:
        tmp.cleanup()


def test_feed_integrity_blocks():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_volume_profile_migration(
            snapshot(
                updated_at=1.0,
                poc=2400.0,
                price=2400.0,
            ),
            history_path=Path(tmp) / "history.json",
            feed_integrity={
                "integrity_ok": False,
                "continuity_valid": False,
            },
            signal="BUY",
            session="NEW_YORK_OPEN",
        )

        assert result["status"] == "FEED_INTEGRITY_NOT_USABLE"
        assert result["safe_for_execution"] is False


def test_duplicate_does_not_expand_history():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "history.json"

        item = snapshot(
            updated_at=1.0,
            poc=2400.0,
            price=2400.0,
        )

        first = evaluate_rithmic_volume_profile_migration(
            item,
            history_path=path,
            feed_integrity=integrity_ok(),
        )
        second = evaluate_rithmic_volume_profile_migration(
            item,
            history_path=path,
            feed_integrity=integrity_ok(),
        )

        assert first["history"]["snapshot_count"] == 1
        assert second["history"]["snapshot_count"] == 1
        assert (
            second["history"]["current_snapshot_was_duplicate"]
            is True
        )


def test_vah_val_not_fabricated():
    with tempfile.TemporaryDirectory() as tmp:
        result = evaluate_rithmic_volume_profile_migration(
            snapshot(
                updated_at=1.0,
                poc=2400.0,
                price=2400.0,
            ),
            history_path=Path(tmp) / "history.json",
            feed_integrity=integrity_ok(),
        )

        assert result["policy"]["vah_val_available"] is False
        assert (
            result["policy"][
                "full_volume_at_price_export_required_for_vah_val"
            ]
            is True
        )


def test_phase5g_wiring_is_observe_only():
    source = (
        ROOT
        / "scripts"
        / "build_phase5g_rithmic_monitoring_bridge.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    required = (
        'bridge["volume_profile_migration"]',
        "evaluate_rithmic_volume_profile_migration",
        "format_volume_profile_migration_text",
        "phase5g_rithmic_volume_profile_migration_history.json",
        "volume_profile_migration_history.unlink()",
    )

    for marker in required:
        assert marker in source, marker

    assert "execute_trade(" not in source
    assert "order_send(" not in source


def main():
    test_poc_migrates_up_with_price()
    test_poc_migrates_down_with_price()
    test_acceptance_near_stable_poc()
    test_rejection_up_from_poc()
    test_migration_price_conflict()
    test_feed_integrity_blocks()
    test_duplicate_does_not_expand_history()
    test_vah_val_not_fabricated()
    test_phase5g_wiring_is_observe_only()

    print("PASS: upward POC migration with price is detected")
    print("PASS: downward POC migration with price is detected")
    print("PASS: repeated price acceptance near stable POC is detected")
    print("PASS: rejection away from POC is detected")
    print("PASS: POC/price migration conflict is identified")
    print("PASS: bad feed integrity blocks profile classification")
    print("PASS: duplicate snapshots do not inflate profile history")
    print("PASS: VAH/VAL are not fabricated without full volume-at-price export")
    print("PASS: Phase 5G volume-profile wiring has no execution authority")


if __name__ == "__main__":
    main()
