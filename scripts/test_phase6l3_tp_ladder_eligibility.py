
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import KEY_LEVEL_TP_LADDER_STRATEGIES

assert "HTF_INSIDE_BAR_FAKEOUT_MTF_ENTRY" in KEY_LEVEL_TP_LADDER_STRATEGIES, (
    "Phase 6L must be eligible for Phase 6E structural TP ladder"
)

print("[PASS] Phase 6L3 HTF inside bar fakeout strategy is TP-ladder eligible.")
