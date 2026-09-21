from __future__ import annotations

import runpy

from config import settings


def main():
    if bool(
        getattr(
            settings,
            "ENABLE_BETTER_ENTRY_OPTIMIZER",
            False,
        )
    ):
        raise RuntimeError(
            "Refusing research shadow launch: "
            "ENABLE_BETTER_ENTRY_OPTIMIZER must remain False"
        )

    if bool(
        getattr(
            settings,
            "ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER",
            False,
        )
    ):
        raise RuntimeError(
            "Refusing research shadow launch: committed/default "
            "Better Entry counterfactual tracker must remain False"
        )

    if bool(
        getattr(
            settings,
            "ENABLE_DAILY_LEVEL_LADDER_RECLAIM_REVERSAL_SHADOW",
            False,
        )
    ):
        raise RuntimeError(
            "Refusing research shadow launch: committed/default "
            "daily-ladder reclaim observer must remain False"
        )

    if abs(
        float(
            getattr(
                settings,
                "FIXED_LOT",
                0.0,
            )
        )
        - 0.25
    ) > 1e-12:
        raise RuntimeError(
            "FIXED_LOT must remain exactly 0.25"
        )

    settings.ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER = True
    settings.ENABLE_DAILY_LEVEL_LADDER_RECLAIM_REVERSAL_SHADOW = True

    if bool(
        getattr(
            settings,
            "ENABLE_BETTER_ENTRY_OPTIMIZER",
            False,
        )
    ):
        raise RuntimeError(
            "Main Better Entry optimizer unexpectedly enabled"
        )

    print(
        "[RESEARCH SHADOW] Better Entry counterfactual tracker "
        "enabled for this process only"
    )
    print(
        "[RESEARCH SHADOW] Daily Ladder Reclaim Reversal "
        "shadow enabled for this process only"
    )
    print(
        "[RESEARCH SHADOW] Main Better Entry optimizer remains "
        "disabled; live execution authority unchanged"
    )

    runpy.run_module(
        "src.live_bot",
        run_name="__main__",
    )


if __name__ == "__main__":
    main()
