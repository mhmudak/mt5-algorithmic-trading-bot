
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.market_outlook_change_detector import (
    detect_outlook_changes,
    format_outlook_change_telegram,
    outlook_watch_snapshot,
)


def sample_outlook(
    *,
    leader="BUY",
    closer="BUY_SCENARIO_CLOSER_NEAR_LONDON_LOW",
    buy_score=65,
    sell_score=45,
    buy_state="APPROACHING",
    sell_state="WAITING",
    buy_status="WAIT_FOR_SWEEP_OR_PULLBACK",
):
    return {
        "symbol": "XAUUSD",
        "report_type": "SCENARIO_UPDATE",
        "last_price": 4043.77,
        "combined_htf_bias": "BEARISH",
        "range_zone": "DISCOUNT_SUPPORT_SIDE",
        "scenario_closer": closer,
        "scenario_maturity": {
            "leader": leader,
            "BUY": {"score": buy_score, "state": buy_state},
            "SELL": {"score": sell_score, "state": sell_state},
        },
        "nearest_liquidity": {
            "buy": {"label": "LONDON_LOW", "price": 4050.31, "distance": 6.54},
            "sell": {"label": "NEWYORK_HIGH", "price": 4059.43, "distance": 15.66},
        },
        "news_filter": {"status": "MANUAL_REVIEW_REQUIRED"},
        "likely_scenarios": [
            {
                "scenario_id": "XAUUSD-BUY-SUPPORT-SWEEP-RECLAIM",
                "title": "Support sweep and reclaim",
                "direction": "BUY",
                "level": 4021.14,
                "status": buy_status,
                "maturity_score": buy_score,
                "action_state": buy_state,
                "can_become_setup": True,
            },
            {
                "scenario_id": "XAUUSD-SELL-RESISTANCE-REJECTION",
                "title": "Resistance rejection or sweep failure",
                "direction": "SELL",
                "level": 4120.25,
                "status": "WAIT_FOR_SWEEP_OR_REJECTION",
                "maturity_score": sell_score,
                "action_state": sell_state,
                "can_become_setup": True,
            },
        ],
    }


def test_new_baseline_is_change():
    current = sample_outlook()
    change = detect_outlook_changes(None, current)

    assert change["changed"] is True
    assert change["severity"] == "BASELINE"
    assert "new_scenario_watch_baseline" in change["reasons"]


def test_no_change():
    current = sample_outlook()
    previous = outlook_watch_snapshot(current)

    change = detect_outlook_changes(previous, current)

    assert change["changed"] is False
    assert change["severity"] == "NONE"


def test_leader_change():
    previous_outlook = sample_outlook(leader="SELL")
    current = sample_outlook(leader="BUY")

    change = detect_outlook_changes(outlook_watch_snapshot(previous_outlook), current)

    assert change["changed"] is True
    assert any("scenario_leader_changed" in item for item in change["reasons"])


def test_maturity_delta_change():
    previous_outlook = sample_outlook(buy_score=45)
    current = sample_outlook(buy_score=67)

    change = detect_outlook_changes(
        outlook_watch_snapshot(previous_outlook),
        current,
        score_delta_threshold=10,
    )

    assert change["changed"] is True
    assert any("BUY_maturity_delta" in item for item in change["reasons"])


def test_trigger_state_change():
    previous_outlook = sample_outlook(buy_state="APPROACHING", buy_status="WAIT_FOR_SWEEP_OR_PULLBACK")
    current = sample_outlook(buy_state="CONFIRMATION_PENDING", buy_status="AT_TRIGGER_ZONE")

    change = detect_outlook_changes(outlook_watch_snapshot(previous_outlook), current)

    assert change["changed"] is True
    assert change["severity"] == "HIGH"
    assert any("scenario_entered_trigger_or_confirmation_state" in item for item in change["reasons"])

    message = format_outlook_change_telegram(current, change)
    assert "PHASE 6S2 OUTLOOK CHANGE WATCH" in message
    assert "Trigger / Confirmation Watch:" in message
    assert "Decision Impact: NONE" in message
    assert "Execution: NO" in message


def test_watcher_dry_run_uses_last_checked_snapshot():
    watcher_source = Path("scripts/watch_phase6s_market_outlook_changes.py").read_text(encoding="utf-8")

    assert "if args.send_telegram:" in watcher_source
    assert 'previous_snapshot = state.get("last_notified_snapshot")' in watcher_source
    assert 'previous_snapshot = state.get("last_checked_snapshot")' in watcher_source
    assert "previous_notified" not in watcher_source


if __name__ == "__main__":
    test_new_baseline_is_change()
    test_no_change()
    test_leader_change()
    test_maturity_delta_change()
    test_trigger_state_change()
    test_watcher_dry_run_uses_last_checked_snapshot()
    print("[PASS] Phase 6S2 scenario change watcher passed.")
