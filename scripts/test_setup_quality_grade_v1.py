from __future__ import annotations

from pathlib import Path

import src.setup_quality_grade as setup_quality
from src.notifier import build_trade_message


ROOT = Path(__file__).resolve().parents[1]


def _live_bias(
    bias,
    coverage=100,
):
    return {
        "bias": bias,
        "coverage": coverage,
        "decision_impact": "DISPLAY_ONLY",
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
    }


def _base_data(
    signal="BUY",
    score=91,
):
    return {
        "stage": "SETUP DETECTED #TEST",
        "symbol": "XAUUSD",
        "signal": signal,
        "strategy": "TEST_STRATEGY",
        "entry_model": "RAW",
        "entry": "N/A",
        "sl": "N/A",
        "tp": "N/A",
        "score": score,
        "session": "LONDON",
        "market_condition": "TRENDING",
        "reason": "test setup",
        "confluence_strategies": [
            "TEST_STRATEGY",
            "SECOND_STRATEGY",
        ],
        "smc": [
            "displacement",
            (
                "bullish_bos"
                if signal == "BUY"
                else "bearish_bos"
            ),
        ],
        "structure_liquidity_reasons": [
            "liquidity_sweep_confirmed",
        ],
        "supply_demand_reasons": [
            "demand_zone_confirmed"
            if signal == "BUY"
            else "supply_zone_confirmed"
        ],
        "elliott_fib_reasons": [],
    }


def _with_live_bias(
    snapshot,
    callback,
):
    original = (
        setup_quality
        .get_live_bias_snapshot
    )

    setup_quality.get_live_bias_snapshot = (
        lambda symbol, market_condition:
        snapshot
    )

    try:
        return callback()
    finally:
        setup_quality.get_live_bias_snapshot = (
            original
        )


def test_a_plus_buy():
    data = _base_data(
        signal="BUY",
        score=91,
    )

    result = _with_live_bias(
        _live_bias("BULLISH"),
        lambda: (
            setup_quality
            .build_setup_quality_grade(
                data
            )
        ),
    )

    assert result["grade"] == "A+"
    assert result["score_10"] == 9.1
    assert result["live_bias_aligned"] is True
    assert result["confirmation_count"] >= 4


def test_a_plus_sell():
    data = _base_data(
        signal="SELL",
        score=94,
    )

    result = _with_live_bias(
        _live_bias("BEARISH"),
        lambda: (
            setup_quality
            .build_setup_quality_grade(
                data
            )
        ),
    )

    assert result["grade"] == "A+"
    assert result["score_10"] == 9.4


def test_a_accepts_mixed_directional_alignment():
    data = _base_data(
        signal="BUY",
        score=87,
    )

    result = _with_live_bias(
        _live_bias(
            "MIXED_BULLISH"
        ),
        lambda: (
            setup_quality
            .build_setup_quality_grade(
                data
            )
        ),
    )

    assert result["grade"] == "A"
    assert (
        result[
            "live_bias_strong_aligned"
        ]
        is False
    )


def test_high_score_alone_is_not_premium():
    data = _base_data(
        signal="BUY",
        score=99,
    )

    data[
        "confluence_strategies"
    ] = []

    data["smc"] = []

    data[
        "structure_liquidity_reasons"
    ] = []

    data[
        "supply_demand_reasons"
    ] = []

    result = _with_live_bias(
        _live_bias("BULLISH"),
        lambda: (
            setup_quality
            .build_setup_quality_grade(
                data
            )
        ),
    )

    assert result["grade"] is None


def test_live_bias_conflict_blocks_grade():
    data = _base_data(
        signal="BUY",
        score=100,
    )

    result = _with_live_bias(
        _live_bias("BEARISH"),
        lambda: (
            setup_quality
            .build_setup_quality_grade(
                data
            )
        ),
    )

    assert result["grade"] is None
    assert result["conflict"] is True


def test_elliott_conflict_blocks_grade():
    data = _base_data(
        signal="BUY",
        score=100,
    )

    data[
        "elliott_fib_reasons"
    ] = [
        "elliott_fib_conflict_sell"
    ]

    result = _with_live_bias(
        _live_bias("BULLISH"),
        lambda: (
            setup_quality
            .build_setup_quality_grade(
                data
            )
        ),
    )

    assert result["grade"] is None
    assert result["conflict"] is True


def test_live_bias_failure_is_fail_open():
    data = _base_data(
        signal="BUY",
        score=100,
    )

    def fail():
        original = (
            setup_quality
            .get_live_bias_snapshot
        )

        def raising(
            symbol,
            market_condition,
        ):
            raise RuntimeError(
                "synthetic live bias failure"
            )

        setup_quality.get_live_bias_snapshot = (
            raising
        )

        try:
            return (
                setup_quality
                .build_setup_quality_grade(
                    data
                )
            )
        finally:
            setup_quality.get_live_bias_snapshot = (
                original
            )

    result = fail()

    assert result["grade"] is None
    assert result["live_bias"] == "UNKNOWN"


def test_authority_is_zero():
    data = _base_data()

    result = _with_live_bias(
        _live_bias("BULLISH"),
        lambda: (
            setup_quality
            .build_setup_quality_grade(
                data
            )
        ),
    )

    assert (
        result["decision_impact"]
        == "DISPLAY_ONLY"
    )

    assert result["can_execute"] is False
    assert result["can_block_trade"] is False
    assert (
        result["can_modify_score"]
        is False
    )
    assert (
        result["can_modify_risk"]
        is False
    )
    assert (
        result[
            "can_modify_entry_sl_tp"
        ]
        is False
    )


def test_formatter():
    result = {
        "grade": "A+",
        "score_10": 9.1,
        "confirmations": [
            "Live Bias aligned",
            "Multi-strategy confluence",
            "Key level",
            "Liquidity confirmation",
            "Structure confirmation",
        ],
    }

    text = (
        setup_quality
        .format_setup_quality_block(
            result
        )
    )

    assert "\u2b50 A+ SETUP" in text
    assert "Score: 9.1/10" in text
    assert "Why:" in text

    # Telegram line stays concise.
    assert (
        "Structure confirmation"
        not in text
    )


def test_notifier_integration():
    data = _base_data(
        signal="BUY",
        score=91,
    )

    message = _with_live_bias(
        _live_bias("BULLISH"),
        lambda: build_trade_message(
            data
        ),
    )

    assert "\u2b50 A+ SETUP" in message
    assert "Score: 9.1/10" in message
    assert "Why:" in message


def test_non_setup_message_not_graded():
    data = _base_data(
        signal="BUY",
        score=100,
    )

    data["stage"] = (
        "TRADE PLAN READY"
    )

    message = _with_live_bias(
        _live_bias("BULLISH"),
        lambda: build_trade_message(
            data
        ),
    )

    assert "\u2b50 A+ SETUP" not in message
    assert "\u2b50 A SETUP" not in message


def test_live_bot_only_passes_display_context():
    text = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        '"market_condition": '
        "market_condition"
        in text
    )

    assert (
        '"confluence_strategies": '
        "selected_signal_data.get("
        in text
    )

    assert (
        '"structure_liquidity_reasons": '
        "selected_signal_data.get("
        in text
    )

    assert (
        '"supply_demand_reasons": '
        "selected_signal_data.get("
        in text
    )

    # Grade logic itself must not enter live_bot.
    assert (
        "from src.setup_quality_grade"
        not in text
    )

    assert (
        "build_setup_quality_grade"
        not in text
    )

    # Preserve Live Bias V1.1 execution isolation.
    assert (
        "get_live_bias_snapshot"
        not in text
    )


def test_fixed_lot_unchanged():
    text = (
        ROOT
        / "config"
        / "settings.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "FIXED_LOT = 0.25"
        in text
    )




def test_status_aware_quality_block():
    from src.notifier import (
        build_setup_quality_alert_block,
    )

    data = _base_data(
        signal="SELL",
        score=94,
    )

    text = _with_live_bias(
        _live_bias("BEARISH"),
        lambda: (
            build_setup_quality_alert_block(
                data,
                status=(
                    "❌ REJECTED — LOW RR"
                ),
            )
        ),
    )

    assert isinstance(
        text,
        str,
    )

    assert (
        "⭐ A+ SETUP QUALITY"
        in text
    )

    assert "Score: 9.4/10" in text

    assert (
        "Status: ❌ REJECTED — LOW RR"
        in text
    )


def test_lifecycle_alert_coverage_static():
    text = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8"
    )

    exact_checks = [
        (
            'f"⚠️ Generic Rejected Candidate Tracked\\n"',
            "REJECTED — GENERIC",
        ),
        (
            'f"⚠️ Intrabar Candidate Rejected — Low RR\\n"',
            "LOW RR (INTRABAR)",
        ),
        (
            'f"? Candidate Recovery Waiting for Better Entry\\n"',
            "BETTER ENTRY",
        ),
        (
            'f"♻️ Candidate Recovery Executing\\n"',
            "EXECUTION ATTEMPT",
        ),
        (
            'f"❌ Candidate Recovery Execution Failed\\n"',
            "EXECUTION FAILED",
        ),
        (
            'f"⚠️ Candidate Rejected — Low RR\\n"',
            "REJECTED — LOW RR",
        ),
        (
            'f"🚫 Ready Setup Rejected by Final HTF Liquidity\\n"',
            "HTF LIQUIDITY",
        ),
    ]

    for alert_marker, status_text in (
        exact_checks
    ):
        assert (
            text.count(alert_marker)
            == 1
        )

        position = text.index(
            alert_marker
        )

        nearby = text[
            max(
                0,
                position - 3000,
            ):
            position
        ]

        assert status_text in nearby

    generic_marker = (
        'f"⚠️ Generic Rejected Candidate Tracked\\n"'
    )

    generic_position = text.index(
        generic_marker
    )

    generic_nearby = text[
        max(
            0,
            generic_position - 3000,
        ):
        generic_position
    ]

    assert (
        "REJECTED — GENERIC"
        in generic_nearby
    )

    assert (
        "LOW RR (INTRABAR)"
        not in generic_nearby
    )

    intrabar_marker = (
        'f"⚠️ Intrabar Candidate Rejected — Low RR\\n"'
    )

    intrabar_position = text.index(
        intrabar_marker
    )

    intrabar_nearby = text[
        max(
            0,
            intrabar_position - 3000,
        ):
        intrabar_position
    ]

    assert (
        "LOW RR (INTRABAR)"
        in intrabar_nearby
    )

    assert (
        "from src.setup_quality_grade"
        not in text
    )

    assert (
        "build_setup_quality_grade"
        not in text
    )

    assert (
        "get_live_bias_snapshot"
        not in text
    )


def test_notifier_public_helper_is_fail_open():
    import src.notifier as notifier

    data = _base_data(
        signal="BUY",
        score=91,
    )

    original = (
        setup_quality
        .get_live_bias_snapshot
    )

    def raising(
        symbol,
        market_condition,
    ):
        raise RuntimeError(
            "synthetic failure"
        )

    setup_quality.get_live_bias_snapshot = (
        raising
    )

    try:
        text = (
            notifier
            .build_setup_quality_alert_block(
                data,
                status="TEST",
            )
        )
    finally:
        setup_quality.get_live_bias_snapshot = (
            original
        )

    assert text == ""



# ============================================================
# SETUP QUALITY GRADE V2 TESTS
# ============================================================


def _v2_history_pass():
    return {
        "trade_sample": 30,
        "trade_win_rate": 0.80,
        "path_sample": 30,
        "hit_plus_10_rate": 0.80,
        "mae_median": 4.50,
        "mae_p75": 8.00,
        "recovery_median": 12.00,
    }


def _v2_history_fail():
    return {
        "trade_sample": 32,
        "trade_win_rate": 0.625,
        "path_sample": 75,
        "hit_plus_10_rate": 0.5867,
        "mae_median": 9.10,
        "mae_p75": 22.39,
        "recovery_median": 28.48,
    }


def test_v2_a_plus_requires_history_and_rr():
    data = _base_data(signal="BUY", score=95)
    data.update(
        {
            "setup_id": "FAI-BUY-V2-PASS",
            "entry": 100.0,
            "sl": 90.0,
            "tp": 118.0,
            "setup_quality_history_override": _v2_history_pass(),
        }
    )

    result = _with_live_bias(
        _live_bias("BULLISH"),
        lambda: setup_quality.build_setup_quality_grade(data),
    )

    assert result["setup_quality_version"] == "V2"
    assert result["grade"] == "A+"
    assert result["historical_edge_pass"] is True
    assert round(result["full_rr"], 2) == 1.80
    assert result["decision_impact"] == "DISPLAY_ONLY"
    assert result["can_execute"] is False
    assert result["can_block_trade"] is False


def test_v2_history_below_75_blocks_a_plus():
    data = _base_data(signal="BUY", score=100)
    data.update(
        {
            "setup_id": "FAI-BUY-V2-HISTORY-FAIL",
            "entry": 100.0,
            "sl": 90.0,
            "tp": 118.0,
            "setup_quality_history_override": _v2_history_fail(),
        }
    )

    result = _with_live_bias(
        _live_bias("BULLISH"),
        lambda: setup_quality.build_setup_quality_grade(data),
    )

    assert result["grade"] != "A+"
    assert result["historical_edge_pass"] is False
    assert any("Historical win rate" in item for item in result["grade_blockers"])
    assert any("Historical +10 rate" in item for item in result["grade_blockers"])


def test_v2_sub_1r_is_f_even_with_raw_100():
    data = _base_data(signal="BUY", score=100)
    data.update(
        {
            "setup_id": "FAI-BUY-1789740903",
            "entry": 4388.36,
            "sl": 4375.79,
            "tp": 4399.59,
            "setup_quality_history_override": _v2_history_fail(),
        }
    )

    result = _with_live_bias(
        _live_bias("BULLISH"),
        lambda: setup_quality.build_setup_quality_grade(data),
    )

    assert result["grade"] == "F"
    assert result["score_10"] == 10.0
    assert result["full_rr"] < 1.0

    text = setup_quality.format_setup_quality_block(result)
    assert "\U0001f7e5 F SETUP" in text
    assert "Raw Score: 10.0/10" in text
    assert "Full RR: 0.89R" in text


def test_v2_macro_conflict_plus_low_rr_is_f():
    data = _base_data(signal="BUY", score=100)
    data.update(
        {
            "setup_id": "FAI-BUY-V2-MACRO",
            "entry": 100.0,
            "sl": 90.0,
            "tp": 111.0,
            "macro_reasons": ["dxy_inverse_conflict_buy"],
            "setup_quality_history_override": _v2_history_pass(),
        }
    )

    result = _with_live_bias(
        _live_bias("BULLISH"),
        lambda: setup_quality.build_setup_quality_grade(data),
    )

    assert result["grade"] == "F"
    assert result["macro_conflict"] is True


def test_v2_unresolved_participation_blocks_a_plus():
    data = _base_data(signal="BUY", score=95)
    data.update(
        {
            "setup_id": "FAI-BUY-V2-PART",
            "entry": 100.0,
            "sl": 90.0,
            "tp": 118.0,
            "participation_combined_state": "NORMAL / UNRESOLVED",
            "setup_quality_history_override": _v2_history_pass(),
        }
    )

    result = _with_live_bias(
        _live_bias("BULLISH"),
        lambda: setup_quality.build_setup_quality_grade(data),
    )

    assert result["grade"] != "A+"
    assert result["participation_unresolved"] is True


def test_v2_does_not_require_current_future_path():
    data = _base_data(signal="BUY", score=95)
    data.update(
        {
            "setup_id": "FAI-BUY-V2-NO-FUTURE",
            "entry": 100.0,
            "sl": 90.0,
            "tp": 118.0,
            "setup_quality_history_override": _v2_history_pass(),
        }
    )

    forbidden = {
        "max_favorable_usd",
        "max_adverse_usd",
        "max_recovery_swing_usd",
        "hit_plus_10",
        "final_outcome",
        "first_hit",
    }
    assert forbidden.isdisjoint(data.keys())

    result = _with_live_bias(
        _live_bias("BULLISH"),
        lambda: setup_quality.build_setup_quality_grade(data),
    )
    assert result["grade"] == "A+"

def main():
    test_v2_a_plus_requires_history_and_rr()
    test_v2_history_below_75_blocks_a_plus()
    test_v2_sub_1r_is_f_even_with_raw_100()
    test_v2_macro_conflict_plus_low_rr_is_f()
    test_v2_unresolved_participation_blocks_a_plus()
    test_v2_does_not_require_current_future_path()
    test_a_plus_buy()
    test_a_plus_sell()
    test_a_accepts_mixed_directional_alignment()

    test_high_score_alone_is_not_premium()
    test_live_bias_conflict_blocks_grade()
    test_elliott_conflict_blocks_grade()
    test_live_bias_failure_is_fail_open()

    test_authority_is_zero()
    test_formatter()
    test_notifier_integration()
    test_non_setup_message_not_graded()

    test_live_bot_only_passes_display_context()
    test_fixed_lot_unchanged()
    test_status_aware_quality_block()
    test_lifecycle_alert_coverage_static()
    test_notifier_public_helper_is_fail_open()

    print(
        "PASS: Setup Quality Grade V1"
    )
    print(
        "PASS: A+ requires score >= 90"
    )
    print(
        "PASS: A requires score >= 85"
    )
    print(
        "PASS: A+ requires strong Live Bias alignment"
    )
    print(
        "PASS: A requires directional Live Bias alignment"
    )
    print(
        "PASS: high score alone cannot earn premium grade"
    )
    print(
        "PASS: independent confirmation buckets required"
    )
    print(
        "PASS: key-level/liquidity context required"
    )
    print(
        "PASS: directional conflict suppresses grade"
    )
    print(
        "PASS: notifier shows A/A+ block only for setup alerts"
    )
    print(
        "PASS: grade remains DISPLAY_ONLY"
    )
    print(
        "PASS: live_bot receives display context only"
    )
    print(
        "PASS: no Live Bias execution integration"
    )
    print(
        "PASS: FIXED_LOT unchanged"
    )
    print(
        "PASS: Setup Quality Grade V1.1 lifecycle coverage"
    )
    print(
        "PASS: rejected candidate quality status"
    )
    print(
        "PASS: low-RR quality status"
    )
    print(
        "PASS: intrabar rejection quality status"
    )
    print(
        "PASS: recovery lifecycle quality status"
    )
    print(
        "PASS: final HTF liquidity rejection quality status"
    )
    print(
        "PASS: generic rejected candidate quality status"
    )
    print(
        "PASS: exact alert marker associations"
    )
    print(
        "PASS: status-aware SETUP QUALITY wording"
    )


if __name__ == "__main__":
    main()
