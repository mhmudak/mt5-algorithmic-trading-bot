
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import KEY_LEVEL_TP_LADDER_STRATEGIES

assert "HEAD_SHOULDERS" in KEY_LEVEL_TP_LADDER_STRATEGIES, (
    "Existing HEAD_SHOULDERS strategy must be eligible for Phase 6E structural TP ladder"
)

print("[PASS] Phase 6N existing HEAD_SHOULDERS is TP-ladder eligible.")
