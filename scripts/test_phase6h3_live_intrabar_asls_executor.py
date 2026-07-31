from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parents[1]

live_path = ROOT / "src" / "live_bot.py"
settings_path = ROOT / "config" / "settings.py"

live = live_path.read_text(encoding="utf-8")
settings = settings_path.read_text(encoding="utf-8")

assert "ASLS_INTRABAR_ENTRY_TOLERANCE = 0.30" in settings
assert "ASLS_INTRABAR_DUPLICATE_SECONDS = 180" in settings
assert "PHASE6H_INTRABAR_SCALP_MEMORY" in live
assert "PHASE 6H3 - INTRABAR STRUCTURAL LEVEL SCALP EXECUTION" in live
assert "auto_structural_level_scalp_signal(df)" in live
assert "asls_trade_plan[\"entry_price\"] = asls_entry" in live
assert "entry_distance > ASLS_INTRABAR_ENTRY_TOLERANCE" in live

phase6h3_index = live.index("PHASE 6H3 - INTRABAR STRUCTURAL LEVEL SCALP EXECUTION")
new_candle_index = live.index("# NEW CANDLE CHECK")

assert phase6h3_index < new_candle_index

py_compile.compile(str(live_path), doraise=True)
py_compile.compile(str(settings_path), doraise=True)

print("[PASS] Phase 6H3 ASLS live executor runs before M15 new-candle gate with anti-chase guard.")
