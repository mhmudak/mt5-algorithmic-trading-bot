from __future__ import annotations


def advance_closed_m1_state(last_closed_m1_time, latest_closed_m1_time):
    """
    Pure cadence state transition.

    Returns:
        (new_last_closed_m1_time, cycle_due, startup_armed)

    Rules:
    - no data: no change, no cycle
    - first observed closed M1: arm only, no retroactive cycle
    - strictly newer closed M1: one cycle due
    - same/older M1: no duplicate cycle
    """
    if latest_closed_m1_time is None:
        return last_closed_m1_time, False, False

    latest = int(latest_closed_m1_time)

    if last_closed_m1_time is None:
        return latest, False, True

    previous = int(last_closed_m1_time)

    if latest > previous:
        return latest, True, False

    return previous, False, False
