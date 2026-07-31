
from pathlib import Path

live = Path("src/live_bot.py").read_text(encoding="utf-8")

assert "ENABLE_HTF_REJECTION_CANDLE_MTF_ENTRY" in live, (
    "Phase 6K toggle must be imported in live_bot"
)

assert '"HTF_REJECTION_CANDLE_MTF_ENTRY"' in live, (
    "Phase 6K strategy must be added to STRATEGY_SPECIFIC_CONFIRMED"
)

assert "strategy_htf_rejection_candle_mtf_entry" in live, (
    "Phase 6K strategy import missing"
)

assert "htf_rejection_candle_mtf_entry_signal" in live, (
    "Phase 6K generate_signal alias missing"
)

assert '("HTF_REJECTION_CANDLE_MTF_ENTRY", htf_rejection_candle_mtf_entry_signal)' in live, (
    "Phase 6K strategy_map entry missing"
)

assert "if not ENABLE_HTF_REJECTION_CANDLE_MTF_ENTRY:" in live, (
    "Phase 6K strategy toggle filter missing"
)

assert 'if name != "HTF_REJECTION_CANDLE_MTF_ENTRY"' in live, (
    "Phase 6K strategy toggle removal missing"
)

print("[PASS] Phase 6K2 live_bot integration is present.")
