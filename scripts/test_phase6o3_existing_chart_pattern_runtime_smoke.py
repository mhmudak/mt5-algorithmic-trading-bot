
from pathlib import Path
import sys
import importlib
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

MODULES = [
    (
        "src.strategies.strategy_triangle_pennant",
        "TRIANGLE_PENNANT",
        "PHASE_6O2_EXISTING_TRIANGLE_PENNANT_STANDARDIZED",
        "TRI",
    ),
    (
        "src.strategies.strategy_flag",
        "FLAG",
        "PHASE_6O2_EXISTING_FLAG_STANDARDIZED",
        "FLAG",
    ),
    (
        "src.strategies.strategy_flag_refined",
        "FLAG_REFINED",
        "PHASE_6O2_EXISTING_FLAG_REFINED_STANDARDIZED",
        "FLAGR",
    ),
]


def build_market_df():
    rows = []
    price = 4000.0

    for i in range(90):
        drift = 0.18 if i % 3 != 0 else -0.07
        open_price = price
        close_price = price + drift
        high_price = max(open_price, close_price) + 1.25
        low_price = min(open_price, close_price) - 1.25

        rows.append(
            {
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "tick_volume": 100 + i,
                "volume": 100 + i,
                "atr_14": 2.5,
                "atr": 2.5,
                "ema_20": round(close_price, 2),
                "ema_50": round(close_price - 1.0, 2),
                "rsi_14": 55.0,
            }
        )

        price = close_price + 0.10

    df = pd.DataFrame(rows)
    df.index = pd.date_range("2026-01-01", periods=len(df), freq="15min")
    return df


def assert_standardized_payload(result, strategy, phase, prefix, signal):
    assert isinstance(result, dict), "generate_signal must return a dict when raw payload exists"

    required_fields = [
        "strategy",
        "phase",
        "setup_id",
        "entry_reference",
        "min_required_score",
        "rr",
        "risk_reward",
        "auto_trade_allowed",
        "decision_impact",
        "duplicate_policy",
        "orderflow_status",
    ]

    for field in required_fields:
        assert field in result, f"{strategy} missing standardized field: {field}"

    assert result["strategy"] == strategy
    assert result["phase"] == phase
    assert str(result["setup_id"]).startswith(f"{prefix}-{signal}-")
    assert result["min_required_score"] == 94
    assert result["rr"] == result["risk_reward"]
    assert result["auto_trade_allowed"] is True
    assert result["decision_impact"] == "MAIN_BOT_RUNTIME_CONTROLLED"
    assert result["duplicate_policy"] == "setup_id_by_entry_model_entry_sl_tp_pattern_height"
    assert result["orderflow_status"] == "NOT_REQUIRED_FOR_EXISTING_CHART_PATTERN"


def run_module_smoke(module_name, strategy, phase, prefix):
    module = importlib.import_module(module_name)
    df = build_market_df()

    assert hasattr(module, "_generate_signal_raw"), f"{strategy} missing _generate_signal_raw"
    assert hasattr(module, "generate_signal"), f"{strategy} missing generate_signal wrapper"

    original_raw = module._generate_signal_raw

    # Smoke 1: original raw engine and wrapper must not crash on normal OHLC data.
    raw_result = original_raw(df.copy())
    assert raw_result is None or isinstance(raw_result, dict), f"{strategy} raw result must be None or dict"

    wrapped_result = module.generate_signal(df.copy())
    assert wrapped_result is None or isinstance(wrapped_result, dict), f"{strategy} wrapped result must be None or dict"

    if wrapped_result is not None:
        assert "setup_id" in wrapped_result, f"{strategy} real wrapped signal missing setup_id"
        assert "entry_reference" in wrapped_result, f"{strategy} real wrapped signal missing entry_reference"

    # Smoke 2: force BUY raw payload and verify runtime standardization.
    entry = float(df.iloc[-2]["close"])

    def fake_buy_raw(_df):
        return {
            "strategy": strategy,
            "entry_model": "PHASE6O3_TEST_BUY",
            "signal": "BUY",
            "score": 95,
            "sl_reference": round(entry - 2.0, 2),
            "tp_reference": round(entry + 6.0, 2),
            "pattern_height": 6.0,
            "reason": "Phase 6O3 runtime smoke BUY payload",
        }

    module._generate_signal_raw = fake_buy_raw
    buy_result = module.generate_signal(df.copy())
    assert_standardized_payload(buy_result, strategy, phase, prefix, "BUY")
    assert buy_result["rr"] == 3.0

    # Smoke 3: force SELL raw payload and verify runtime standardization.
    def fake_sell_raw(_df):
        return {
            "strategy": strategy,
            "entry_model": "PHASE6O3_TEST_SELL",
            "signal": "SELL",
            "score": 95,
            "sl_reference": round(entry + 2.0, 2),
            "tp_reference": round(entry - 6.0, 2),
            "pattern_height": 6.0,
            "reason": "Phase 6O3 runtime smoke SELL payload",
        }

    module._generate_signal_raw = fake_sell_raw
    sell_result = module.generate_signal(df.copy())
    assert_standardized_payload(sell_result, strategy, phase, prefix, "SELL")
    assert sell_result["rr"] == 3.0

    module._generate_signal_raw = original_raw


for item in MODULES:
    run_module_smoke(*item)

print("[PASS] Phase 6O3 existing chart-pattern runtime smoke tests passed.")
