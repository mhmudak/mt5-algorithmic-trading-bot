
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import KEY_LEVEL_TP_LADDER_STRATEGIES

assert "HTF_REJECTION_CANDLE_MTF_ENTRY" in KEY_LEVEL_TP_LADDER_STRATEGIES, (
    "Phase 6K must be eligible for Phase 6E structural TP ladder"
)

print("[PASS] Phase 6K3 HTF rejection candle strategy is TP-ladder eligible.")
