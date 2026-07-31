
from pathlib import Path
import ast
import importlib
import sys
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

TARGETS = [
    ("src/strategies/strategy_crt_tbs.py", "src.strategies.strategy_crt_tbs", "CRT_TBS", "CRT"),
    ("src/strategies/strategy_fast.py", "src.strategies.strategy_fast", "FAST", "FAST"),
    ("src/strategies/strategy_fractal_sweep.py", "src.strategies.strategy_fractal_sweep", "FRACTAL_SWEEP", "FSW"),
    ("src/strategies/strategy_htf_fib_confluence.py", "src.strategies.strategy_htf_fib_confluence", "HTF_FIB_CONFLUENCE", "HFIB"),
    ("src/strategies/strategy_htf_trend_pullback.py", "src.strategies.strategy_htf_trend_pullback", "HTF_TREND_PULLBACK", "HTP"),
    ("src/strategies/strategy_liquidity_candle.py", "src.strategies.strategy_liquidity_candle", "LIQUIDITY_CANDLE", "LC"),
    ("src/strategies/strategy_mtf_sr_fvg_reclaim.py", "src.strategies.strategy_mtf_sr_fvg_reclaim", "MTF_SR_FVG_RECLAIM", "MSFVG"),
    ("src/strategies/strategy_range_sweep_reclaim.py", "src.strategies.strategy_range_sweep_reclaim", "RANGE_SWEEP_RECLAIM", "RSR"),
    ("src/strategies/strategy_relief_rally.py", "src.strategies.strategy_relief_rally", "RELIEF_RALLY", "RRL"),
    ("src/strategies/strategy_smt.py", "src.strategies.strategy_smt", "SMT", "SMT"),
    ("src/strategies/strategy_sniper_v2.py", "src.strategies.strategy_sniper_v2", "SNIPER_V2", "SNP"),
    ("src/strategies/strategy_strict.py", "src.strategies.strategy_strict", "STRICT", "STR"),
    ("src/strategies/strategy_structure_liquidity.py", "src.strategies.strategy_structure_liquidity", "STRUCTURE_LIQUIDITY", "SLQ"),
    ("src/strategies/strategy_supply_demand_retest.py", "src.strategies.strategy_supply_demand_retest", "SUPPLY_DEMAND_RETEST", "SDR"),
    ("src/strategies/strategy_vwap_range_mean_reversion.py", "src.strategies.strategy_vwap_range_mean_reversion", "VWAP_RANGE_MEAN_REVERSION", "VRMR"),
    ("src/strategies/strategy_vwap_reclaim.py", "src.strategies.strategy_vwap_reclaim", "VWAP_RECLAIM", "VWAP"),
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
        "PHASE6P3C_REMAINING_LEGACY_STANDARDIZATION = True",
        "def _phase6p3c_generate_signal_raw(df):",
        "def _phase6p3c_standardize_signal",
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

    original_raw = module._phase6p3c_generate_signal_raw

    def fake_raw(_df):
        return {
            "strategy": strategy,
            "entry_model": "PHASE6P3C_TEST_BUY",
            "signal": "BUY",
            "score": 95,
            "sl_reference": round(entry - 2.0, 2),
            "tp_reference": round(entry + 6.0, 2),
            "reason": "Phase 6P3C standardization smoke payload",
        }

    module._phase6p3c_generate_signal_raw = fake_raw
    result = module.generate_signal(df.copy())
    module._phase6p3c_generate_signal_raw = original_raw

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

print("[PASS] Phase 6P3C remaining legacy strategy standardization passed.")
