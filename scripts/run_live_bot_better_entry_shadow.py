from __future__ import annotations

import runpy

from config import settings


def main() -> int:
    """
    Start the normal live bot with Better Entry counterfactual collection
    enabled only in this process.

    This launcher does not change execution mode, live-trading permissions,
    risk, score, entry, SL, TP, lot sizing, or the committed settings file.
    """

    if settings.ENABLE_BETTER_ENTRY_OPTIMIZER is not False:
        raise RuntimeError(
            "Committed Better Entry optimizer default must remain False."
        )

    if (
        settings
        .ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER
        is not False
    ):
        raise RuntimeError(
            "Committed Better Entry counterfactual default must remain False."
        )

    if settings.FIXED_LOT != 0.25:
        raise RuntimeError(
            "FIXED_LOT must remain exactly 0.25."
        )

    settings.ENABLE_BETTER_ENTRY_OPTIMIZER_COUNTERFACTUAL_TRACKER = True

    if settings.ENABLE_BETTER_ENTRY_OPTIMIZER is not False:
        raise RuntimeError(
            "Shadow launcher must not enable the main Better Entry flag."
        )

    print(
        "[BETTER ENTRY SHADOW] "
        "counterfactual tracker enabled for this process only",
        flush=True,
    )
    print(
        "[BETTER ENTRY SHADOW] "
        "main optimizer remains disabled; execution authority unchanged",
        flush=True,
    )

    runpy.run_module(
        "src.live_bot",
        run_name="__main__",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
