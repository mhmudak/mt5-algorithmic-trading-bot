from __future__ import annotations

import runpy

from config import settings


def main() -> None:
    settings.ENABLE_FCR_M1_FVG_INTRABAR_SHADOW = True

    print(
        "[RESEARCH SHADOW] FCR intrabar observer enabled for this process only"
    )
    print(
        "[RESEARCH SHADOW] FCR intrabar observer is OBSERVE_ONLY; "
        "execution authority unchanged"
    )

    runpy.run_module(
        "scripts.run_live_bot_research_shadow_fcr_regime",
        run_name="__main__",
    )


if __name__ == "__main__":
    main()
