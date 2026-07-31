
from pathlib import Path
import ast
import importlib
import sys
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

TARGETS = [
    ("src/strategies/strategy_auto_structural_level_scalp.py", "src.strategies.strategy_auto_structural_level_scalp", "AUTO_STRUCTURAL_LEVEL_SCALP", "ASLS"),
    ("src/strategies/strategy_psych_round_number_rejection.py", "src.strategies.strategy_psych_round_number_rejection", "PSYCH_ROUND_NUMBER_REJECTION", "PSYCH"),
    ("src/strategies/strategy_session_exhaustion_reversal.py", "src.strategies.strategy_session_exhaustion_reversal", "SESSION_EXHAUSTION_REVERSAL", "SER"),
    ("src/strategies/strategy_volatility_compression_breakout.py", "src.strategies.strategy_volatility_compression_breakout", "VOLATILITY_COMPRESSION_BREAKOUT", "VCB"),
]

for file_path, module_name, strategy, prefix in TARGETS:
    source = Path(file_path).read_text(encoding="utf-8")
    ast.parse(source)

    assert "import hashlib" in source, f"{strategy} missing hashlib"
    assert "PHASE6P1_STANDARDIZATION_COMPLETION = True" in source, f"{strategy} missing marker"
    assert "def _phase6p1_generate_signal_raw(df):" in source, f"{strategy} missing raw wrapper target"
    assert "def _phase6p1_standardize_signal" in source, f"{strategy} missing standardizer"
    assert source.count("def generate_signal(df):") == 1, f"{strategy} must expose one generate_signal wrapper"

    module = importlib.import_module(module_name)

    rows = []
    price = 4000.0
    for i in range(80):
        close_price = price + 0.2
        rows.append(
            {
                "open": price,
                "high": close_price + 1.0,
                "low": price - 1.0,
                "close": close_price,
                "tick_volume": 100 + i,
                "volume": 100 + i,
                "atr_14": 2.5,
                "atr": 2.5,
                "ema_20": close_price,
                "ema_50": close_price - 1.0,
                "rsi_14": 55.0,
            }
        )
        price = close_price

    df = pd.DataFrame(rows)
    df.index = pd.date_range("2026-01-01", periods=len(df), freq="15min")
    entry = float(df.iloc[-2]["close"])

    original_raw = module._phase6p1_generate_signal_raw

    def fake_raw(_df):
        return {
            "strategy": strategy,
            "phase": "EXISTING_PHASE_SHOULD_BE_PRESERVED",
            "entry_model": "PHASE6P1_TEST_BUY",
            "signal": "BUY",
            "score": 95,
            "entry_reference": round(entry, 2),
            "sl_reference": round(entry - 2.0, 2),
            "tp_reference": round(entry + 6.0, 2),
            "rr": 3.0,
            "auto_trade_allowed": True,
            "decision_impact": "MAIN_BOT_RUNTIME_CONTROLLED",
            "reason": "Phase 6P1 standardization completion smoke payload",
        }

    module._phase6p1_generate_signal_raw = fake_raw
    result = module.generate_signal(df.copy())
    module._phase6p1_generate_signal_raw = original_raw

    for field in [
        "strategy",
        "phase",
        "setup_id",
        "entry_reference",
        "rr",
        "risk_reward",
        "auto_trade_allowed",
        "decision_impact",
        "duplicate_policy",
    ]:
        assert field in result, f"{strategy} runtime payload missing {field}"

    assert result["strategy"] == strategy
    assert result["phase"] == "EXISTING_PHASE_SHOULD_BE_PRESERVED"
    assert str(result["setup_id"]).startswith(f"{prefix}-BUY-")
    assert result["rr"] == 3.0
    assert result["risk_reward"] == 3.0
    assert result["duplicate_policy"] == "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

print("[PASS] Phase 6P1 partially standardized strategies are completed.")
