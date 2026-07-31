
from pathlib import Path

live = Path("src/live_bot.py").read_text(encoding="utf-8")

assert "ENABLE_HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY" in live, (
    "Phase 6M toggle must be imported in live_bot"
)

assert '"HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY"' in live, (
    "Phase 6M strategy must be added to STRATEGY_SPECIFIC_CONFIRMED"
)

assert "strategy_htf_double_top_bottom_mtf_entry" in live, (
    "Phase 6M strategy import missing"
)

assert "htf_double_top_bottom_mtf_entry_signal" in live, (
    "Phase 6M generate_signal alias missing"
)

assert '("HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY", htf_double_top_bottom_mtf_entry_signal)' in live, (
    "Phase 6M strategy_map entry missing"
)

assert "if not ENABLE_HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY:" in live, (
    "Phase 6M strategy toggle filter missing"
)

assert 'if name != "HTF_DOUBLE_TOP_BOTTOM_MTF_ENTRY"' in live, (
    "Phase 6M strategy toggle removal missing"
)

print("[PASS] Phase 6M2 live_bot integration is present.")
