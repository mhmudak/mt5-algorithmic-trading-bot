from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile

from config import settings
from src import setup_historical_optimizer as optimizer
from src import setup_outcome_tracker as tracker


def _history_row(setup_id, created_at, win):
    return {
        "setup_id": setup_id,
        "symbol": "XAUUSD",
        "source_events": ["TEST"],
        "status": "CLOSED",
        "created_at": created_at,
        "updated_at": created_at,
        "last_seen_at": created_at,
        "strategy": "FAILED_FVG_REVERSAL",
        "signal": "BUY",
        "entry_model": "FAILED_BEARISH_FVG_REVERSAL",
        "session": "LONDON",
        "market_condition": "RANGING",
        "score": 90,
        "entry": 100.0,
        "sl": 90.0,
        "tp": 109.0,
        "extra": {"rr": 0.90},
        "path_observed": True,
        "max_favorable_usd": 12.0 if win else 3.0,
        "max_adverse_usd": 4.0 if win else 14.0,
        "max_recovery_swing_usd": 16.0,
        "hit_plus_10": win,
        "hit_tp": win,
        "hit_sl": not win,
        "first_hit": "TP_TOUCH" if win else "SL_TOUCH",
        "final_outcome": "TP_TOUCH" if win else "SL_TOUCH",
        "context_key": "TEST",
        "scenario_key": "TEST",
        "nearby_strategies": [],
    }


def _install_temp_tracker(account_dir):
    path = account_dir / "setup_outcomes.json"
    tracker.get_setup_outcomes_file = lambda: path
    tracker.send_setup_outcome_to_google_sheets = lambda item: True
    tracker._capture_participation_statistics_fail_open = lambda **kwargs: {}
    tracker.ENABLE_SETUP_OUTCOME_TRACKER = True
    return path


def _event():
    if "CANDIDATE_REJECTED" in tracker.SETUP_OUTCOME_TRACK_EVENTS:
        return "CANDIDATE_REJECTED"
    return next(iter(tracker.SETUP_OUTCOME_TRACK_EVENTS))


def _register(setup_id):
    return tracker.register_setup_outcome(
        symbol="XAUUSD",
        setup_id=setup_id,
        event=_event(),
        strategy="FAILED_FVG_REVERSAL",
        signal="BUY",
        entry_model="FAILED_BEARISH_FVG_REVERSAL",
        score=90,
        session="LONDON",
        market_condition="RANGING",
        entry=100.0,
        sl=90.0,
        tp=109.0,
        reason="test",
        extra={"rr": 0.90, "required_rr": 1.10},
    )


def test_safe_defaults():
    assert settings.ENABLE_SETUP_HISTORICAL_OPTIMIZER is False
    assert (
        settings.ENABLE_SETUP_HISTORICAL_OPTIMIZER_WALK_FORWARD_SNAPSHOTS
        is False
    )
    assert settings.FIXED_LOT == 0.25


def test_default_zero_path_is_not_measured():
    row = {
        "path_observed": False,
        "max_favorable_usd": 0.0,
        "max_adverse_usd": 0.0,
        "max_recovery_swing_usd": 0.0,
        "hit_plus_10": False,
        "hit_tp": False,
        "hit_sl": False,
        "first_hit": None,
    }
    assert optimizer._path_measured(row) is False
    row["path_observed"] = True
    assert optimizer._path_measured(row) is True


def test_legacy_positive_path_is_measured():
    row = {
        "max_favorable_usd": 11.0,
        "max_adverse_usd": 0.0,
        "max_recovery_swing_usd": 11.0,
        "hit_plus_10": True,
        "hit_tp": False,
        "hit_sl": False,
        "first_hit": "W10",
    }
    assert optimizer._path_measured(row) is True


def test_first_write_snapshot_is_immutable():
    with tempfile.TemporaryDirectory() as tmp:
        account_dir = Path(tmp)
        path = _install_temp_tracker(account_dir)

        now = datetime.now()
        rows = {}

        for index in range(20):
            created_at = (
                now - timedelta(days=2, minutes=index)
            ).isoformat()
            row = _history_row(
                f"HIST-{index}",
                created_at,
                index < 15,
            )
            rows[row["setup_id"]] = row

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(rows, indent=2),
            encoding="utf-8",
        )

        tracker.ENABLE_SETUP_HISTORICAL_OPTIMIZER_WALK_FORWARD_SNAPSHOTS = True

        assert _register("CURRENT-V2") is True

        stored = tracker.load_setup_outcomes()
        snapshot = stored["CURRENT-V2"]["historical_optimizer_snapshot"]

        assert snapshot["snapshot_schema_version"] == "V2"
        assert snapshot["optimizer_version"] == optimizer.SETUP_HISTORICAL_OPTIMIZER_VERSION
        assert snapshot["capture_mode"] == "LIVE_FILE_STATE_AT_DETECTION"
        assert snapshot["setup_win_sample"] == 20
        assert snapshot["setup_wins"] == 15
        assert snapshot["setup_win_rate"] == 0.75
        assert snapshot["rr_bucket"] == "RR_LT_1_00"
        assert snapshot["decision_impact"] == "DISPLAY_ONLY"
        assert snapshot["can_execute"] is False
        assert snapshot["can_modify_score"] is False

        original_snapshot = json.dumps(snapshot, sort_keys=True)

        original_builder = (
            optimizer.build_setup_historical_optimizer_walk_forward_snapshot
        )

        def _should_not_run(data):
            raise AssertionError("snapshot recalculated")

        optimizer.build_setup_historical_optimizer_walk_forward_snapshot = (
            _should_not_run
        )

        try:
            assert _register("CURRENT-V2") is True
        finally:
            optimizer.build_setup_historical_optimizer_walk_forward_snapshot = (
                original_builder
            )

        snapshot_again = tracker.load_setup_outcomes()[
            "CURRENT-V2"
        ]["historical_optimizer_snapshot"]

        assert json.dumps(
            snapshot_again,
            sort_keys=True,
        ) == original_snapshot


def test_toggle_off_writes_no_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        _install_temp_tracker(Path(tmp))
        tracker.ENABLE_SETUP_HISTORICAL_OPTIMIZER_WALK_FORWARD_SNAPSHOTS = False
        assert _register("NO-SNAPSHOT") is True
        item = tracker.load_setup_outcomes()["NO-SNAPSHOT"]
        assert "historical_optimizer_snapshot" not in item


def test_capture_failure_is_fail_open():
    with tempfile.TemporaryDirectory() as tmp:
        _install_temp_tracker(Path(tmp))
        tracker.ENABLE_SETUP_HISTORICAL_OPTIMIZER_WALK_FORWARD_SNAPSHOTS = True

        original_builder = (
            optimizer.build_setup_historical_optimizer_walk_forward_snapshot
        )

        def _explode(data):
            raise RuntimeError("expected failure")

        optimizer.build_setup_historical_optimizer_walk_forward_snapshot = (
            _explode
        )

        try:
            assert _register("FAIL-OPEN") is True
        finally:
            optimizer.build_setup_historical_optimizer_walk_forward_snapshot = (
                original_builder
            )

        snapshot = tracker.load_setup_outcomes()[
            "FAIL-OPEN"
        ]["historical_optimizer_snapshot"]

        assert snapshot["available"] is False
        assert snapshot["reason"] == "snapshot_capture_failed"
        assert snapshot["decision_impact"] == "DISPLAY_ONLY"


def main():
    test_safe_defaults()
    test_default_zero_path_is_not_measured()
    test_legacy_positive_path_is_measured()
    test_first_write_snapshot_is_immutable()
    test_toggle_off_writes_no_snapshot()
    test_capture_failure_is_fail_open()
    print("PASS: Setup Historical Optimizer Walk-Forward V2")


if __name__ == "__main__":
    main()
