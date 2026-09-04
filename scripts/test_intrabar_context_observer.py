from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from src.intrabar_context_observer import (
    build_intrabar_context_snapshot,
    log_intrabar_context_observation,
)


def synthetic_bearish_df():
    closes = [
        120.0 - (i * 0.5)
        for i in range(30)
    ]

    return pd.DataFrame(
        {
            "open": [
                value + 0.20
                for value in closes
            ],
            "high": [
                value + 0.60
                for value in closes
            ],
            "low": [
                value - 0.60
                for value in closes
            ],
            "close": closes,
        }
    )


def test_snapshot_direction_and_risk():
    snapshot = (
        build_intrabar_context_snapshot(
            df=synthetic_bearish_df(),
            source="PHASE6H3_ASLS",
            event=(
                "PHASE6H3_ASLS_EXECUTED"
            ),
            strategy=(
                "AUTO_STRUCTURAL_LEVEL_SCALP"
            ),
            setup_id="TEST-ASLS-1",
            signal="SELL",
            entry_model=(
                "SUPPORT_BREAK_HOLD_SCALP"
            ),
            session="LONDON",
            execution_market_condition=(
                "INTRABAR_STRUCTURAL_LEVEL_SCALP"
            ),
            observed_market_condition=(
                "TRENDING"
            ),
            signal_data={
                "momentum": (
                    "bearish_structure_momentum"
                ),
                "direction_context": (
                    "bearish_break_hold"
                ),
                "smc_reasons": [
                    "ema_bearish",
                    "bearish_bos",
                    "displacement",
                ],
            },
            trade_plan={
                "entry_price": 100.0,
                "stop_loss": 105.0,
                "take_profit": 90.0,
                "reason": (
                    "synthetic test"
                ),
            },
            m15_bias="SELL",
            htf_context={
                "bias": "BULLISH",
            },
        )
    )

    assert snapshot is not None

    assert (
        snapshot["m15_bias"]
        == "SELL"
    )

    assert (
        snapshot["m15_relation"]
        == "WITH_M15"
    )

    assert (
        snapshot["htf_bias"]
        == "BUY"
    )

    assert (
        snapshot["htf_relation"]
        == "COUNTER_HTF"
    )

    assert (
        snapshot["regime_family"]
        == "TREND_OR_EXPANSION"
    )

    assert (
        snapshot["risk_distance"]
        == 5.0
    )

    assert (
        snapshot["planned_rr"]
        == 2.0
    )

    features = (
        snapshot[
            "price_features"
        ]
    )

    assert (
        features[
            "momentum_shape"
        ]
        == "BEARISH_BROAD"
    )

    assert (
        features[
            "momentum_relation"
        ]
        == "WITH_PRICE_MOMENTUM"
    )


def test_non_target_strategy_ignored():
    snapshot = (
        build_intrabar_context_snapshot(
            df=synthetic_bearish_df(),
            source="TEST",
            event="EXECUTED",
            strategy="ORB",
            setup_id="TEST-ORB",
            signal="SELL",
        )
    )

    assert snapshot is None


def test_jsonl_persistence():
    snapshot = (
        build_intrabar_context_snapshot(
            df=synthetic_bearish_df(),
            source=(
                "INTRABAR_PRICE_EVENT"
            ),
            event=(
                "INTRABAR_PRICE_EVENT_EXECUTED"
            ),
            strategy=(
                "FAILED_FVG_REVERSAL"
            ),
            setup_id="TEST-FVG-1",
            signal="SELL",
            entry_model="FAILED_FVG",
            session="ASIA",
            execution_market_condition=(
                "INTRABAR_PENDING"
            ),
            observed_market_condition=(
                "RANGING"
            ),
            trade_plan={
                "entry_price": 100.0,
                "stop_loss": 104.0,
                "take_profit": 92.0,
            },
            m15_bias="SELL",
            htf_context={
                "bias": "BEARISH",
            },
        )
    )

    with tempfile.TemporaryDirectory() as tmp:
        path = (
            Path(tmp)
            / "observations.jsonl"
        )

        assert (
            log_intrabar_context_observation(
                snapshot,
                file_path=path,
            )
            is True
        )

        lines = (
            path.read_text(
                encoding="utf-8",
            )
            .splitlines()
        )

        assert len(lines) == 1

        row = json.loads(
            lines[0]
        )

        assert (
            row["setup_id"]
            == "TEST-FVG-1"
        )

        assert (
            row["regime_family"]
            == "RANGE_OR_COMPRESSION"
        )


def test_live_hook_is_post_execution():
    source = (
        ROOT
        / "src"
        / "live_bot.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "def _capture_intrabar_context_observation("
        in source
    )

    generic_execute = source.index(
        "execution_result = "
        "execute_trade(signal, trade_plan, SYMBOL)"
    )

    generic_observer = source.index(
        'source="INTRABAR_PRICE_EVENT"',
        generic_execute,
    )

    assert (
        generic_execute
        < generic_observer
    )

    phase_start = source.index(
        "PHASE 6H3 - INTRABAR "
        "STRUCTURAL LEVEL SCALP EXECUTION"
    )

    phase_execute = source.index(
        "execution_result = "
        "execute_trade("
        "asls_signal, "
        "asls_trade_plan, "
        "SYMBOL"
        ")",
        phase_start,
    )

    phase_observer = source.index(
        'source="PHASE6H3_ASLS"',
        phase_execute,
    )

    assert (
        phase_execute
        < phase_observer
    )


def main():
    test_snapshot_direction_and_risk()
    test_non_target_strategy_ignored()
    test_jsonl_persistence()
    test_live_hook_is_post_execution()

    print(
        "[PASS] Intrabar context observer "
        "is execution-independent, "
        "post-order only, and records "
        "direction/momentum/regime/risk context."
    )


if __name__ == "__main__":
    main()
