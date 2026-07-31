
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import KEY_LEVEL_TP_LADDER_STRATEGIES

required = [
    "TRIANGLE_PENNANT",
    "FLAG",
    "FLAG_REFINED",
]

for name in required:
    assert name in KEY_LEVEL_TP_LADDER_STRATEGIES, (
        f"{name} must be eligible for Phase 6E structural TP ladder"
    )

print("[PASS] Phase 6O existing triangle/flag chart patterns are TP-ladder eligible.")
