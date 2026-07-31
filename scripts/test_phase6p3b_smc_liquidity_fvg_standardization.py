
from pathlib import Path
import ast
import importlib
import sys
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

TARGETS = [
    ("src/strategies/strategy_amd_fvg.py", "src.strategies.strategy_amd_fvg", "AMD_FVG", "AMD"),
    ("src/strategies/strategy_breaker_block.py", "src.strategies.strategy_breaker_block", "BREAKER_BLOCK", "BRK"),
    ("src/strategies/strategy_extreme_sweep_reclaim.py", "src.strategies.strategy_extreme_sweep_reclaim", "EXTREME_SWEEP_RECLAIM", "ESR"),
    ("src/strategies/strategy_fvg.py", "src.strategies.strategy_fvg", "FVG", "FVG"),
    ("src/strategies/strategy_fvg_ce_mitigation.py", "src.strategies.strategy_fvg_ce_mitigation", "FVG_CE_MITIGATION", "FVGCE"),
    ("src/strategies/strategy_liquidity_sweep.py", "src.strategies.strategy_liquidity_sweep", "LIQUIDITY_SWEEP", "LSW"),
    ("src/strategies/strategy_liquidity_trap.py", "src.strategies.strategy_liquidity_trap", "LIQUIDITY_TRAP", "LTRAP"),
    ("src/strategies/strategy_lvn_fvg_reclaim.py", "src.strategies.strategy_lvn_fvg_reclaim", "LVN_FVG_RECLAIM", "LVN"),
    ("src/strategies/strategy_ob_fvg_combo.py", "src.strategies.strategy_ob_fvg_combo", "OB_FVG_COMBO", "OBFVG"),
    ("src/strategies/strategy_order_block.py", "src.strategies.strategy_order_block", "ORDER_BLOCK", "OB"),
]


def build_df():
    rows = []
    price = 4000.0

    for i in range(100):
        close_price = price + 0.20
        rows.append(
            {
                "open": round(price, 2),
                "high": round(close_price + 1.0, 2),
                "low": round(price - 1.0, 2),
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
        price = close_price

    df = pd.DataFrame(rows)
    df.index = pd.date_range("2026-01-01", periods=len(df), freq="15min")
    return df


for file_path, module_name, strategy, prefix in TARGETS:
    source = Path(file_path).read_text(encoding="utf-8")
    ast.parse(source)

    for text in [
        "import hashlib",
        "PHASE6P3B_SMC_LIQUIDITY_STANDARDIZATION = True",
        "def _phase6p3b_generate_signal_raw(df):",
        "def _phase6p3b_standardize_signal",
        "def generate_signal(df):",
        "setup_id",
        "entry_reference",
        "rr",
        "risk_reward",
        "auto_trade_allowed",
        "decision_impact",
        "duplicate_policy",
    ]:
        assert text in source, f"{strategy} missing source text: {text}"

    assert source.count("def generate_signal(df):") == 1, f"{strategy} must expose one generate_signal wrapper"

    module = importlib.import_module(module_name)
    df = build_df()
    entry = float(df.iloc[-2]["close"])

    original_raw = module._phase6p3b_generate_signal_raw

    def fake_raw(_df):
        return {
            "strategy": strategy,
            "entry_model": "PHASE6P3B_TEST_BUY",
            "signal": "BUY",
            "score": 95,
            "sl_reference": round(entry - 2.0, 2),
            "tp_reference": round(entry + 6.0, 2),
            "reason": "Phase 6P3B standardization smoke payload",
        }

    module._phase6p3b_generate_signal_raw = fake_raw
    result = module.generate_signal(df.copy())
    module._phase6p3b_generate_signal_raw = original_raw

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
    assert str(result["setup_id"]).startswith(f"{prefix}-BUY-")
    assert result["rr"] == 3.0
    assert result["risk_reward"] == 3.0
    assert result["auto_trade_allowed"] is True
    assert result["decision_impact"] == "MAIN_BOT_RUNTIME_CONTROLLED"
    assert result["duplicate_policy"] == "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

print("[PASS] Phase 6P3B SMC/liquidity/FVG strategy standardization passed.")
