
from pathlib import Path
import importlib
import sys
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

strategy_source = Path("src/strategies/strategy_fcr_m1_fvg.py").read_text(encoding="utf-8")
settings_source = Path("config/settings.py").read_text(encoding="utf-8")
live_bot_source = Path("src/live_bot.py").read_text(encoding="utf-8")

assert strategy_source.count('"entry_reference": round(entry["close"], 2),') == 2
assert strategy_source.count('"m1_entry_time": entry.get("time"),') == 2
assert 'tp_reference = round(entry["close"] + (stop_distance * TARGET_R_MULTIPLIER), 2)' in strategy_source
assert 'tp_reference = round(entry["close"] - (stop_distance * TARGET_R_MULTIPLIER), 2)' in strategy_source

assert "ENABLE_FCR_M1_FVG_STARTUP_GUARD = True" in settings_source
assert "FCR_M1_FVG_SKIP_ON_FIRST_CYCLE_AFTER_STARTUP = True" in settings_source

assert "ENABLE_FCR_M1_FVG_STARTUP_GUARD" in live_bot_source
assert "FCR_M1_FVG_SKIP_ON_FIRST_CYCLE_AFTER_STARTUP" in live_bot_source
assert "[PHASE 6R FCR STARTUP GUARD]" in live_bot_source
assert "last_processed_candle_time is None" in live_bot_source
assert 'if name != "FCR_M1_FVG"' in live_bot_source

module = importlib.import_module("src.strategies.strategy_fcr_m1_fvg")

rows = []
for i in range(20):
    close_price = 4042.56
    rows.append(
        {
            "open": close_price,
            "high": close_price + 1,
            "low": close_price - 1,
            "close": close_price,
            "atr_14": 2.5,
            "ema_20": close_price,
            "time": pd.Timestamp("2026-01-01") + pd.Timedelta(minutes=15 * i),
        }
    )

df = pd.DataFrame(rows)

original_raw = module._phase6p2_generate_signal_raw

def fake_raw(_df):
    # This reproduces the bug shape:
    # M15 df close is 4042.56, but true M1 entry is 4039.08.
    # Correct RR = (4039.08 - 4026.90) / (4043.14 - 4039.08) = 3.0
    return {
        "strategy": "FCR_M1_FVG",
        "entry_model": "M5_FCR_LOW_BREAK_M1_FVG_ENGULF",
        "signal": "SELL",
        "score": 100,
        "entry_reference": 4039.08,
        "sl_reference": 4043.14,
        "tp_reference": 4026.90,
        "target_model": "FIXED_3R_AFTER_M1_FVG",
        "reason": "Phase 6R FCR metadata smoke payload",
    }

module._phase6p2_generate_signal_raw = fake_raw
result = module.generate_signal(df.copy())
module._phase6p2_generate_signal_raw = original_raw

assert result["entry_reference"] == 4039.08
assert result["rr"] == 3.0
assert result["risk_reward"] == 3.0
assert result["tp_reference"] == 4026.90
assert result["target_model"] == "FIXED_3R_AFTER_M1_FVG"

print("[PASS] Phase 6R FCR restart/metadata guard passed.")
