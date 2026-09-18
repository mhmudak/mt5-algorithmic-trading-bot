from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile

import pandas as pd

from src.daily_ladder_provider import (
    AUTO_COMPOSITE_MODE,
    MANUAL_AVO_MODE,
    DailyLadderValidationError,
    build_auto_composite_execution_ladder,
    build_shadow_observations,
    calculate_shadow_levels,
    load_manual_avo_ladder,
)
from src.strategies.strategy_daily_level_ladder_breakout import (
    evaluate_daily_level_ladder_breakout,
)


ROOT = Path(__file__).resolve().parents[1]


def _frame(previous_close: float, close: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"time": "older", "open": previous_close, "high": previous_close + 1, "low": previous_close - 1, "close": previous_close, "atr_14": 5.0},
            {"time": "previous", "open": previous_close, "high": previous_close + 1, "low": previous_close - 1, "close": previous_close, "atr_14": 5.0},
            {"time": "closed", "open": previous_close, "high": max(previous_close, close) + 1, "low": min(previous_close, close) - 1, "close": close, "atr_14": 5.0},
            {"time": "forming", "open": close, "high": close + 50, "low": close - 50, "close": close + 40, "atr_14": 5.0},
        ]
    )


def test_manual_provider_feeds_dllb_and_shadow_stays_separate():
    payload = '''{
  "symbol": "XAUUSD",
  "broker_date": "2026-09-17",
  "pivot": 4290.0,
  "upper": [4300.0, 4315.0, 4330.0],
  "lower": [4275.0, 4252.0, 4239.0]
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "daily.json"
        path.write_text(payload, encoding="utf-8")
        approved = load_manual_avo_ladder(
            path,
            expected_symbol="XAUUSD",
            expected_broker_date=date(2026, 9, 17),
        )

        result = evaluate_daily_level_ladder_breakout(
            m5_df=_frame(4299.0, 4301.2),
            approved_ladder=approved,
        )
        assert result is not None
        assert result["broken_level"] == 4300.0
        assert result["target_level"] == 4315.0
        assert result["daily_approved_source"] == MANUAL_AVO_MODE

        _, raw = calculate_shadow_levels(
            previous_open=4292.62,
            previous_high=4366.73,
            previous_low=4235.24,
            previous_close=4262.63,
            current_open=4260.26,
        )
        observations = build_shadow_observations(
            approved_ladder=approved,
            raw_levels=raw,
            cluster_distance=3.0,
        )
        assert observations
        assert all(item["execution_authority"] is False for item in observations)

        # The DLLB result still targets the next approved level, not a raw level.
        assert result["target_level"] == 4315.0



def test_auto_composite_provider_feeds_dllb():
    approved = build_auto_composite_execution_ladder(
        symbol="XAUUSD",
        broker_date=date(2026, 9, 17),
        previous_open=4292.62,
        previous_high=4366.73,
        previous_low=4235.24,
        previous_close=4262.63,
        current_open=4260.26,
    )

    assert approved.source == AUTO_COMPOSITE_MODE
    assert len(approved.upper) >= 2

    source = float(approved.upper[0])
    target = float(approved.upper[1])

    result = evaluate_daily_level_ladder_breakout(
        m5_df=_frame(source - 1.0, source + 1.2),
        approved_ladder=approved,
    )

    assert result is not None
    assert result["signal"] == "BUY"
    assert abs(float(result["broken_level"]) - round(source, 2)) < 0.011
    assert abs(float(result["target_level"]) - round(target, 2)) < 0.011
    assert result["daily_approved_source"] == AUTO_COMPOSITE_MODE


def test_wrong_date_symbol_and_malformed_fail_closed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        stale = root / "stale.json"
        stale.write_text(
            '{"symbol":"XAUUSD","broker_date":"2026-09-16","pivot":4290,"upper":[4300],"lower":[4275]}',
            encoding="utf-8",
        )
        try:
            load_manual_avo_ladder(
                stale,
                expected_symbol="XAUUSD",
                expected_broker_date=date(2026, 9, 17),
            )
        except DailyLadderValidationError:
            pass
        else:
            raise AssertionError("stale ladder must fail closed")

        wrong_symbol = root / "wrong_symbol.json"
        wrong_symbol.write_text(
            '{"symbol":"EURUSD","broker_date":"2026-09-17","pivot":4290,"upper":[4300],"lower":[4275]}',
            encoding="utf-8",
        )
        try:
            load_manual_avo_ladder(
                wrong_symbol,
                expected_symbol="XAUUSD",
                expected_broker_date=date(2026, 9, 17),
            )
        except DailyLadderValidationError:
            pass
        else:
            raise AssertionError("wrong symbol must fail closed")

        malformed = root / "malformed.json"
        malformed.write_text("{", encoding="utf-8")
        try:
            load_manual_avo_ladder(
                malformed,
                expected_symbol="XAUUSD",
                expected_broker_date=date(2026, 9, 17),
            )
        except DailyLadderValidationError:
            pass
        else:
            raise AssertionError("malformed ladder must fail closed")


def test_live_authority_boundary_is_explicit():
    live = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    settings = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    start = live.index("def process_daily_level_ladder_breakout_v1(")
    end = live.index("def process_cycle(last_processed_candle_time):", start)
    block = live[start:end]

    assert (
        'DAILY_LEVEL_LADDER_DLLB_EXECUTION_MODE = "AUTO_COMPOSITE_DAILY_LADDER"'
        in settings
    )
    assert "DAILY_LEVEL_LADDER_DLLB_EXECUTION_MODE" in block
    assert "if execution_mode == AUTO_COMPOSITE_MODE:" in block
    assert "build_auto_composite_execution_ladder(" in block
    assert "elif execution_mode == MANUAL_AVO_MODE:" in block
    assert "DAILY_LEVEL_LADDER_MANUAL_REQUIRE_CURRENT_BROKER_DATE" in block
    assert "load_manual_avo_ladder(" in block
    assert "expected_broker_date=broker_date" in block
    assert "unsupported DLLB execution mode" in block
    assert "approved_ladder=approved_ladder" in block
    assert "broker_date_changed = (" in block
    assert 'previous_provider_state_key = runtime.get("provider_state_key")' in block
    assert "if broker_date_changed or previous_provider_state_key is not None:" in block
    assert "approved ladder state armed on latest closed M5" in block
    assert "no retroactive execution" in block
    assert "calculate_shadow_levels(" in block
    assert 'runtime["last_shadow_observations"]' in block
    assert "execution_authority=False" in block
    assert '"[DAILY LADDER LEVELS] "' in block
    assert "approved_ladder.upper" in block
    assert "approved_ladder.lower" in block
    assert '"[DAILY LADDER CANDIDATE] "' in block
    assert "build_daily_ladder_shadow(" in block
    assert "family_count=" in block
    assert "member_count=" in block
    assert "cluster_width=" in block
    assert "pivot_distance=" in block
    assert "families=" in block
    assert "members=" in block

    evaluator_call = block[block.index("candidate = evaluate_daily_level_ladder_breakout("):]
    evaluator_call = evaluator_call[:evaluator_call.index(")\n    except Exception")]
    assert "approved_ladder=approved_ladder" in evaluator_call
    assert "shadow" not in evaluator_call.lower()


if __name__ == "__main__":
    test_manual_provider_feeds_dllb_and_shadow_stays_separate()
    test_auto_composite_provider_feeds_dllb()
    test_wrong_date_symbol_and_malformed_fail_closed()
    test_live_authority_boundary_is_explicit()

    print("PASS: Daily Ladder Provider <-> DLLB Integration V1")
    print("PASS: AUTO composite is default DLLB execution authority")
    print("PASS: manual Avo remains explicit override")
    print("PASS: stale/wrong-symbol/malformed manual ladder fails closed in manual mode")
    print("PASS: raw AUTO shadow remains observation-only")
    print("PASS: next approved level remains authoritative TP")
    print("PASS: broker-date/provider changes arm current M5 and prevent retro-trading")
