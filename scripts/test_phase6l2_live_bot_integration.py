
from pathlib import Path

live = Path("src/live_bot.py").read_text(encoding="utf-8")

assert "ENABLE_HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY" in live, (
    "Phase 6L toggle must be imported in live_bot"
)

assert '"HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY"' in live, (
    "Phase 6L strategy must be added to STRATEGY_SPECIFIC_CONFIRMED"
)

assert "strategy_htf_inside_bar_fakeout_mtf_entry" in live, (
    "Phase 6L strategy import missing"
)

assert "htf_inside_bar_fakeout_mtf_entry_signal" in live, (
    "Phase 6L generate_signal alias missing"
)

assert '("HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY", htf_inside_bar_fakeout_mtf_entry_signal)' in live, (
    "Phase 6L strategy_map entry missing"
)

assert "if not ENABLE_HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY:" in live, (
    "Phase 6L strategy toggle filter missing"
)

assert 'if name != "HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY"' in live, (
    "Phase 6L strategy toggle removal missing"
)

print("[PASS] Phase 6L2 live_bot integration is present.")
