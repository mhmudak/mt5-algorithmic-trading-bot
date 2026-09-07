from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parents[1]

live_path = ROOT / "src" / "live_bot.py"
settings_path = ROOT / "config" / "settings.py"

live = live_path.read_text(encoding="utf-8-sig")
settings = settings_path.read_text(encoding="utf-8-sig")

assert "ENABLE_INTRABAR_ENGINE = True" in settings
assert "ASLS_INTRABAR_ENTRY_TOLERANCE = 0.30" in settings
assert "ASLS_INTRABAR_DUPLICATE_SECONDS = 180" in settings
assert "ASLS_BREAK_HOLD_MIN_HOLD_DISTANCE = 0.30" in settings
assert "ASLS_CONTEXT_COUNTER_MIN_BODY_ATR = 0.45" in settings

assert "PHASE6H_INTRABAR_SCALP_MEMORY" in live
assert "PHASE 6H3 - INTRABAR STRUCTURAL LEVEL SCALP EXECUTION" in live
assert "if ENABLE_INTRABAR_ENGINE and ENABLE_AUTO_STRUCTURAL_LEVEL_SCALP:" in live
assert "auto_structural_level_scalp_signal(df)" in live
assert 'asls_trade_plan["entry_price"] = asls_entry' in live
assert "entry_distance > ASLS_INTRABAR_ENTRY_TOLERANCE" in live
assert "asls_allowlist_decision = explain_intrabar_strategy_allowlist_decision(" in live
assert "asls_t0_snapshot = _freeze_intrabar_context_observation(" in live
assert "_persist_intrabar_context_observation(asls_t0_snapshot)" in live

phase6h3_index = live.index("PHASE 6H3 - INTRABAR STRUCTURAL LEVEL SCALP EXECUTION")
new_candle_index = live.index("# NEW CANDLE CHECK")
assert phase6h3_index < new_candle_index

phase = live[phase6h3_index:new_candle_index]
freeze_index = phase.index("asls_t0_snapshot = _freeze_intrabar_context_observation(")
execute_index = phase.index("execution_result = execute_trade(asls_signal, asls_trade_plan, SYMBOL)")
persist_index = phase.index("_persist_intrabar_context_observation(asls_t0_snapshot)")
assert freeze_index < execute_index < persist_index

py_compile.compile(str(live_path), doraise=True)
py_compile.compile(str(settings_path), doraise=True)

print(
    "[PASS] Phase 6H3 ASLS is master-gated, canonical-allowlisted, "
    "causal-T0 observed, and still runs before the M15 new-candle gate."
)
