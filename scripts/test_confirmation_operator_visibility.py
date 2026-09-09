from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )

from config import settings
from src.confirmation_summary_notifier import (
    build_confirmation_summary_message,
)


def test_shadow_geometry_is_visible():
    report = {
        "approved": True,
        "confidence": 50,
        "score_delta": -4.0,
        "mode": "MT5_ONLY",
        "summary": "synthetic",
        "shadow_decision": "CAUTION",
        "shadow_score": 30.0,
        "shadow_action": "OBSERVE_ONLY",
        "shadow_reason": "synthetic",
        "results": [
            {
                "module": "ENTRY_QUALITY",
                "status": "PASS",
                "confidence": 70,
                "score_delta": 0.0,
                "reason": "rr available",
            }
        ],
    }

    signal_data = {
        "setup_id": "HTF-SELL-TEST",
        "strategy": (
            "HTF_REJECTION_CANDLE_MTF_ENTRY"
        ),
        "signal": "SELL",
        "setup_source_bucket": (
            "MTF_CONFLICT_TRACKED"
        ),
        "confirmation_stage": (
            "MTF_CONFLICT_CANDIDATE"
        ),
        "confirmation_geometry_role": (
            "SHADOW_REFERENCE"
        ),
    }

    trade_plan = {
        "entry_price": 4397.42,
        "stop_loss": 4405.50,
        "take_profit": 4381.20,
        "rr": 2.02,
    }

    message = (
        build_confirmation_summary_message(
            report=report,
            signal_data=signal_data,
            trade_plan=trade_plan,
            setup_source_bucket=(
                "MTF_CONFLICT_TRACKED"
            ),
        )
    )

    assert (
        "Lifecycle Stage: "
        "MTF_CONFLICT_CANDIDATE"
        in message
    )

    assert (
        "Geometry Role: SHADOW_REFERENCE"
        in message
    )

    assert (
        "Execution Geometry: COMPLETE"
        in message
    )

    assert "Entry: 4397.42" in message
    assert "SL: 4405.5" in message
    assert "TP: 4381.2" in message
    assert "RR: 2.02" in message

    assert (
        "Confirmation Approved: True"
        in message
    )

    assert (
        "Trade Approval: NOT DETERMINED "
        "BY CONFIRMATION ENGINE"
        in message
    )

    assert (
        "Trading Impact: NONE "
        "(observe-only)"
        in message
    )


def test_missing_geometry_is_explicit():
    message = (
        build_confirmation_summary_message(
            report={
                "approved": True,
                "results": [],
            },
            signal_data={
                "strategy": "TEST",
                "signal": "SELL",
                "setup_id": "TEST-1",
            },
            trade_plan={},
            setup_source_bucket=(
                "MTF_CONFLICT_TRACKED"
            ),
        )
    )

    assert (
        "Execution Geometry: INCOMPLETE"
        in message
    )

    assert "Entry: N/A" in message
    assert "SL: N/A" in message
    assert "TP: N/A" in message
    assert "RR: N/A" in message


def test_operator_notifications_are_dedicated():
    assert (
        settings
        .TELEGRAM_NOTIFY_SETUP_CONFIRMED
        is True
    )

    assert (
        settings
        .TELEGRAM_NOTIFY_TRADE_PLAN_READY
        is True
    )

    live_source = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "TELEGRAM_NOTIFY_SETUP_CONFIRMED "
        "and not best_setup.get(\"notified\")"
        in live_source
    )

    assert (
        "TELEGRAM_NOTIFY_TRADE_PLAN_READY "
        "and not best_setup.get("
        "\"trade_plan_notified\")"
        in live_source
    )

    assert (
        "trade_plan_override=("
        in live_source
    )

    assert (
        "shadow_trade_plan"
        in live_source
    )

    assert (
        "if isinstance(shadow_trade_plan, dict)"
        in live_source
    )

    assert (
        "else {}"
        in live_source
    )

    assert (
        'confirmation_stage_override='
        '"MTF_CONFLICT_CANDIDATE"'
        in live_source
    )

    assert (
        'geometry_role_override='
        '"SHADOW_REFERENCE"'
        in live_source
    )


def main():
    test_shadow_geometry_is_visible()
    test_missing_geometry_is_explicit()
    test_operator_notifications_are_dedicated()

    print(
        "[PASS] Confirmation Telegram now "
        "distinguishes candidate vs canonical "
        "geometry, exposes MTF shadow Entry/SL/"
        "TP/RR, and keeps canonical setup/trade "
        "plan notifications independent of "
        "verbose Telegram mode."
    )


if __name__ == "__main__":
    main()
