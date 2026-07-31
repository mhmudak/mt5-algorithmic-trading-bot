
from pathlib import Path
import ast
import importlib
import sys
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

source = Path("src/strategies/strategy_orb_v00.py").read_text(encoding="utf-8")
ast.parse(source)

for text in [
    "import hashlib",
    "PHASE6P3D_ORB_V00_STANDARDIZATION = True",
    "def _phase6p3d_generate_signal_raw(df):",
    "def _phase6p3d_standardize_signal",
    "def generate_signal(df):",
    "tp_reference = round(price + orb_width, 2)",
    "tp_reference = round(price - orb_width, 2)",
    '"tp_reference": tp_reference,',
    '"target_model": "ORB_V00_RANGE_EXTENSION"',
    "setup_id",
    "entry_reference",
    "rr",
    "risk_reward",
    "auto_trade_allowed",
    "decision_impact",
    "duplicate_policy",
]:
    assert text in source, f"ORB_V00 missing source text: {text}"

assert "\ufeff" not in source, "ORB_V00 still contains BOM U+FEFF"
assert source.count("def generate_signal(df):") == 1, "ORB_V00 must expose one generate_signal wrapper"
assert source.count('"tp_reference": tp_reference,') == 2, "ORB_V00 must return tp_reference for BUY and SELL"

module = importlib.import_module("src.strategies.strategy_orb_v00")

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
entry = float(df.iloc[-2]["close"])

original_raw = module._phase6p3d_generate_signal_raw

def fake_raw(_df):
    return {
        "strategy": "ORB_V00",
        "entry_model": "PHASE6P3D_TEST_BUY",
        "signal": "BUY",
        "score": 92,
        "sl_reference": round(entry - 2.0, 2),
        "tp_reference": round(entry + 6.0, 2),
        "target_model": "ORB_V00_RANGE_EXTENSION",
        "reason": "Phase 6P3D ORB_V00 standardization smoke payload",
    }

module._phase6p3d_generate_signal_raw = fake_raw
result = module.generate_signal(df.copy())
module._phase6p3d_generate_signal_raw = original_raw

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
    assert field in result, f"ORB_V00 runtime payload missing {field}"

assert result["strategy"] == "ORB_V00"
assert str(result["setup_id"]).startswith("ORBV00-BUY-")
assert result["rr"] == 3.0
assert result["risk_reward"] == 3.0
assert result["auto_trade_allowed"] is True
assert result["decision_impact"] == "MAIN_BOT_RUNTIME_CONTROLLED"
assert result["duplicate_policy"] == "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

print("[PASS] Phase 6P3D ORB_V00 standardization passed.")
