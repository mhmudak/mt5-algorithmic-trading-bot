from __future__ import annotations

from pathlib import Path
import ast
import re
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from src.strategies.strategy_daily_level_ladder_breakout import (
    build_daily_level_clusters,
    evaluate_daily_level_ladder_breakout,
)


def _daily_context(
    source_time="2026-09-16 00:00:00",
):
    return {
        "source": "BROKER_COMPLETED_D1",
        "time": source_time,
        "previous_day_high": 4351.69,
        "previous_day_low": 4255.26,
        "previous_day_close": 4290.0,
        "classic": {
            "levels": {
                "S3": 4269.0,
                "S2": 4283.0,
                "S1": 4288.0,
                "P": 4290.0,
                "R1": 4303.0,
                "R2": 4320.0,
                "R3": 4346.0,
            },
            "ordered": [
                ("S3", 4269.0),
                ("S2", 4283.0),
                ("S1", 4288.0),
                ("P", 4290.0),
                ("R1", 4303.0),
                ("R2", 4320.0),
                ("R3", 4346.0),
            ],
        },
        "five_level": {
            "mode": "EXTENDED",
            "levels": {
                "S5": 4234.0,
                "S4": 4255.0,
                "S3": 4264.0,
                "S2": 4278.0,
                "S1": 4288.0,
                "R1": 4298.0,
                "R2": 4308.0,
                "R3": 4346.0,
                "R4": 4351.0,
                "R5": 4366.0,
            },
            "ordered": [
                ("S5", 4234.0),
                ("S4", 4255.0),
                ("S3", 4264.0),
                ("S2", 4278.0),
                ("S1", 4288.0),
                ("R1", 4298.0),
                ("R2", 4308.0),
                ("R3", 4346.0),
                ("R4", 4351.0),
                ("R5", 4366.0),
            ],
        },
    }


def _m5_frame(
    *,
    previous_close,
    open_price,
    high,
    low,
    close,
    atr=5.5,
    forming_close=None,
):
    if forming_close is None:
        forming_close = close

    return pd.DataFrame(
        [
            {
                "time": "older",
                "open": previous_close - 0.5,
                "high": previous_close + 0.5,
                "low": previous_close - 1.0,
                "close": previous_close - 0.2,
                "atr_14": atr,
            },
            {
                "time": "previous",
                "open": previous_close - 0.3,
                "high": previous_close + 0.4,
                "low": previous_close - 0.5,
                "close": previous_close,
                "atr_14": atr,
            },
            {
                "time": "closed",
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "atr_14": atr,
            },
            {
                "time": "forming",
                "open": close,
                "high": max(close, forming_close) + 25.0,
                "low": min(close, forming_close) - 25.0,
                "close": forming_close,
                "atr_14": atr,
            },
        ]
    )


def test_pivot_and_nearby_level_cluster():
    ladder = build_daily_level_clusters(
        daily_context=_daily_context(),
        atr=5.5,
    )

    assert ladder is not None
    assert ladder["pivot"] == 4290.0

    pivot_cluster = next(
        item
        for item in ladder["clusters"]
        if item["contains_pivot"]
    )

    assert pivot_cluster["low"] == 4288.0
    assert pivot_cluster["high"] == 4290.0
    assert "D-P" in pivot_cluster["names"]


def test_sell_requires_outer_boundary_of_4290_4288_cluster():
    not_broken = (
        evaluate_daily_level_ladder_breakout(
            m5_df=_m5_frame(
                previous_close=4291.0,
                open_price=4290.5,
                high=4291.2,
                low=4288.2,
                close=4288.5,
            ),
            daily_context=_daily_context(),
        )
    )

    assert not_broken is None

    broken = (
        evaluate_daily_level_ladder_breakout(
            m5_df=_m5_frame(
                previous_close=4291.0,
                open_price=4290.5,
                high=4291.0,
                low=4286.8,
                close=4287.5,
            ),
            daily_context=_daily_context(),
        )
    )

    assert broken is not None
    assert broken["signal"] == "SELL"
    assert broken["broken_level"] == 4288.0
    assert broken["target_level"] == 4283.0
    assert broken["sl_reference"] == 4290.0
    assert broken["tp_reference"] == 4283.0


def test_buy_break_targets_next_daily_level():
    result = (
        evaluate_daily_level_ladder_breakout(
            m5_df=_m5_frame(
                previous_close=4297.0,
                open_price=4297.2,
                high=4299.4,
                low=4296.8,
                close=4298.7,
            ),
            daily_context=_daily_context(),
        )
    )

    assert result is not None
    assert result["signal"] == "BUY"
    assert result["broken_level"] == 4298.0
    assert result["target_level"] == 4303.0
    assert result["sl_reference"] == 4296.0
    assert result["tp_reference"] == 4303.0


def test_multi_level_m5_uses_furthest_cleared_cluster():
    result = (
        evaluate_daily_level_ladder_breakout(
            m5_df=_m5_frame(
                previous_close=4297.0,
                open_price=4297.3,
                high=4309.5,
                low=4297.0,
                close=4308.8,
                atr=5.5,
            ),
            daily_context=_daily_context(),
        )
    )

    assert result is not None
    assert result["signal"] == "BUY"
    assert result["broken_level"] == 4308.0
    assert result["target_level"] == 4320.0
    assert result["tp_reference"] == 4320.0
    assert result["sl_reference"] == 4303.2


def test_tiny_body_fake_break_rejected():
    result = (
        evaluate_daily_level_ladder_breakout(
            m5_df=_m5_frame(
                previous_close=4297.9,
                open_price=4298.35,
                high=4298.9,
                low=4297.7,
                close=4298.5,
                atr=5.5,
            ),
            daily_context=_daily_context(),
        )
    )

    assert result is None


def test_forming_m5_is_ignored():
    result = (
        evaluate_daily_level_ladder_breakout(
            m5_df=_m5_frame(
                previous_close=4297.0,
                open_price=4297.2,
                high=4299.4,
                low=4296.8,
                close=4298.7,
                forming_close=4400.0,
            ),
            daily_context=_daily_context(),
        )
    )

    assert result is not None
    assert result["broken_level"] == 4298.0
    assert result["target_level"] == 4303.0


def test_daily_source_changes_setup_identity():
    first = (
        evaluate_daily_level_ladder_breakout(
            m5_df=_m5_frame(
                previous_close=4297.0,
                open_price=4297.2,
                high=4299.4,
                low=4296.8,
                close=4298.7,
            ),
            daily_context=_daily_context(
                "2026-09-16 00:00:00"
            ),
        )
    )

    second = (
        evaluate_daily_level_ladder_breakout(
            m5_df=_m5_frame(
                previous_close=4297.0,
                open_price=4297.2,
                high=4299.4,
                low=4296.8,
                close=4298.7,
            ),
            daily_context=_daily_context(
                "2026-09-17 00:00:00"
            ),
        )
    )

    assert first is not None
    assert second is not None
    assert (
        first["setup_id"]
        != second["setup_id"]
    )


def test_live_integration_is_pre_m15_and_once_per_closed_m5():
    text = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8",
    )

    processor_start = text.index(
        "def process_daily_level_ladder_breakout_v1("
    )

    process_cycle_start = text.index(
        "def process_cycle(last_processed_candle_time):"
    )

    assert processor_start < process_cycle_start

    call_index = text.index(
        "if process_daily_level_ladder_breakout_v1(",
        process_cycle_start,
    )

    m15_gate = text.index(
        "# NEW CANDLE CHECK",
        process_cycle_start,
    )

    assert call_index < m15_gate

    block = text[
        processor_start:
        process_cycle_start
    ]

    assert "mt5.TIMEFRAME_M5" in block
    assert "m5_df.iloc[" in block
    assert '"last_closed_m5_time"' in block
    assert (
        "DAILY_LEVEL_LADDER_SKIP_FIRST_M5_AFTER_STARTUP"
        in block
    )

    strategy_map_region = text[
        text.index(
            "# SIGNAL GENERATION",
            m15_gate,
        ):
        text.index(
            "[STRATEGY MAP ACTIVE]",
            m15_gate,
        )
    ]

    assert (
        "DAILY_LEVEL_LADDER_BREAKOUT"
        not in strategy_map_region
    )


def test_live_execution_preserves_next_level_tp_and_guards():
    text = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8",
    )

    start = text.index(
        "def process_daily_level_ladder_breakout_v1("
    )

    end = text.index(
        "def process_cycle(last_processed_candle_time):",
        start,
    )

    block = text[
        start:
        end
    ]

    for required in (
        "calculate_trade_plan(",
        "calculate_rr_value(",
        "get_min_rr(",
        "is_news_blackout_active()",
        "is_trading_blackout_active()",
        "check_trade_guard(",
        "_daily_level_ladder_execution_memory_blocked_fail_closed(",
        "execute_trade(",
        "authoritative next-level TP",
    ):
        assert required in block

    assert (
        "apply_universal_tp_ladder"
        not in block
    )


def test_risk_accepts_strategy_sl_reference_and_fixed_lot_unchanged():
    risk = (
        ROOT
        / "src"
        / "risk.py"
    ).read_text(
        encoding="utf-8",
    )

    match = re.search(
        r"STRATEGY_SL_REFERENCE_MODELS\s*=\s*\{(.*?)\n\}",
        risk,
        flags=re.DOTALL,
    )

    assert match is not None
    assert (
        '"DAILY_LEVEL_LADDER_BREAKOUT"'
        in match.group(
            0
        )
    )

    settings = (
        ROOT
        / "config"
        / "settings.py"
    ).read_text(
        encoding="utf-8",
    )

    assert (
        "FIXED_LOT = 0.25"
        in settings
    )



def test_already_cleared_level_requires_fresh_cross():
    result = (
        evaluate_daily_level_ladder_breakout(
            m5_df=_m5_frame(
                previous_close=4298.60,
                open_price=4298.40,
                high=4300.30,
                low=4298.10,
                close=4300.00,
                atr=5.5,
            ),
            daily_context=_daily_context(),
        )
    )

    assert result is None


def test_transient_d1_failure_cannot_consume_new_closed_m5():
    text = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8",
    )

    start = text.index(
        "def process_daily_level_ladder_breakout_v1("
    )

    end = text.index(
        "def process_cycle(last_processed_candle_time):",
        start,
    )

    block = text[
        start:
        end
    ]

    assignment_pattern = re.compile(
        r'runtime\[\s*'
        r'"last_closed_m5_time"'
        r'\s*\]\s*=\s*latest_closed_time'
    )

    startup_index = block.index(
        "if previous_seen is None:"
    )

    same_candle_index = block.index(
        "elif (\n"
        "        latest_closed_time\n"
        "        == previous_seen",
        startup_index,
    )

    d1_index = block.index(
        "d1_rates = mt5.copy_rates_from_pos(",
        same_candle_index,
    )

    evaluation_index = block.index(
        "evaluate_daily_level_ladder_breakout(",
        d1_index,
    )

    consume_comment_index = block.index(
        "Consume this closed M5 exactly once here.",
        evaluation_index,
    )

    candidate_check_index = block.index(
        "if not isinstance(\n"
        "        candidate,\n"
        "        dict,",
        consume_comment_index,
    )

    startup_region = block[
        startup_index:
        same_candle_index
    ]

    pre_d1_region = block[
        same_candle_index:
        d1_index
    ]

    post_evaluation_region = block[
        consume_comment_index:
        candidate_check_index
    ]

    # Startup intentionally consumes/arms the current
    # closed M5 so restart cannot retro-trade history.
    assert (
        assignment_pattern.search(
            startup_region
        )
        is not None
    )

    # Normal new-M5 processing must NOT consume the bar
    # before D1/context/evaluation succeeds.
    assert (
        assignment_pattern.search(
            pre_d1_region
        )
        is None
    )

    # Successful strategy evaluation consumes it before
    # RR/news/time/guard/execution-memory decisions.
    assert (
        assignment_pattern.search(
            post_evaluation_region
        )
        is not None
    )

    assert (
        d1_index
        < evaluation_index
        < consume_comment_index
        < candidate_check_index
    )

    assert (
        "closed M5 remains unconsumed"
        in block[
            evaluation_index:
            consume_comment_index
        ]
    )

    assert (
        "Downstream RR/news/time/guard/execution-memory rejection"
        in block
    )

    assert (
        "Do not chase an old"
        in block
    )


def test_telegram_uses_real_newline_escapes():
    text = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8",
    )

    start = text.index(
        '"✅ Daily Level Ladder Breakout'
    )

    end = text.index(
        "    except Exception:",
        start,
    )

    block = text[
        start:
        end
    ]

    assert (
        r'"✅ Daily Level Ladder Breakout\n"'
        in block
    )

    assert (
        r'"✅ Daily Level Ladder Breakout\\n"'
        not in block
    )



def test_telegram_includes_authoritative_target_price():
    text = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8",
    )

    marker_index = text.index(
        "Daily Level Ladder Breakout"
    )

    send_index = text.rfind(
        "send_telegram_message(",
        0,
        marker_index,
    )

    assert send_index >= 0

    end = text.index(
        "    except Exception:",
        marker_index,
    )

    block = text[
        send_index:
        end
    ]

    assert (
        "candidate.get('target_cluster_names')"
        in block
    )

    assert (
        "candidate.get('target_level')"
        in block
    )

    target_names_index = block.index(
        "candidate.get('target_cluster_names')"
    )

    target_level_index = block.index(
        "candidate.get('target_level')"
    )

    entry_index = block.index(
        "trade_plan.get('entry_price')"
    )

    assert (
        target_names_index
        < target_level_index
        < entry_index
    )


def test_sources_parse():
    for relative in (
        "src/strategies/strategy_daily_level_ladder_breakout.py",
        "src/risk.py",
        "src/live_bot.py",
    ):
        ast.parse(
            (
                ROOT
                / relative
            ).read_text(
                encoding="utf-8",
            )
        )


if __name__ == "__main__":
    test_pivot_and_nearby_level_cluster()
    test_sell_requires_outer_boundary_of_4290_4288_cluster()
    test_buy_break_targets_next_daily_level()
    test_multi_level_m5_uses_furthest_cleared_cluster()
    test_tiny_body_fake_break_rejected()
    test_forming_m5_is_ignored()
    test_daily_source_changes_setup_identity()
    test_live_integration_is_pre_m15_and_once_per_closed_m5()
    test_live_execution_preserves_next_level_tp_and_guards()
    test_risk_accepts_strategy_sl_reference_and_fixed_lot_unchanged()
    test_already_cleared_level_requires_fresh_cross()
    test_transient_d1_failure_cannot_consume_new_closed_m5()
    test_telegram_uses_real_newline_escapes()
    test_telegram_includes_authoritative_target_price()
    test_sources_parse()

    print("PASS: Daily Level Ladder Breakout V1")
    print("PASS: latest completed broker D1 is strategy source")
    print("PASS: Pivot + nearby daily level clustering")
    print("PASS: 4290/4288 SELL requires outer 4288 break")
    print("PASS: BUY/SELL daily ladder direction")
    print("PASS: next unresolved daily level is authoritative TP")
    print("PASS: 40% source-to-target structural SL")
    print("PASS: one closed M5 candle can clear multiple levels")
    print("PASS: furthest cleared cluster becomes source")
    print("PASS: tiny-body fake break rejected")
    print("PASS: forming M5 candle excluded")
    print("PASS: completed-D1 rollover changes setup identity")
    print("PASS: M5 processor runs before M15 gate")
    print("PASS: startup does not retro-trade old M5 break")
    print("PASS: fresh live RR required")
    print("PASS: news/time/trade/execution-memory guards preserved")
    print("PASS: Universal TP ladder does not replace next-level TP")
    print("PASS: fresh crossing required; already-cleared level cannot retrade")
    print("PASS: transient D1/evaluation failure cannot consume new M5")
    print("PASS: downstream rejection remains one-shot / no chasing")
    print("PASS: Telegram uses real newline escapes")
    print("PASS: FIXED_LOT remains 0.25")
