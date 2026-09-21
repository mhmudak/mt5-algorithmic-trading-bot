from __future__ import annotations

import runpy

from config import settings


settings.ENABLE_FCR_M1_FVG_REGIME_SHADOW = True

print(
    "[RESEARCH SHADOW] "
    "FCR excluded-regime observer enabled for this process only"
)
print(
    "[RESEARCH SHADOW] "
    "FCR regime shadow is OBSERVE_ONLY; execution authority unchanged"
)

runpy.run_module(
    "scripts.run_live_bot_research_shadow",
    run_name="__main__",
)
