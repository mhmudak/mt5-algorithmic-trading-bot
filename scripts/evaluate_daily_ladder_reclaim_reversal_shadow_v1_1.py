from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[1]
OUTCOMES = (
    ROOT
    / "data"
    / "daily_ladder_reclaim_reversal_outcomes.jsonl"
)


def _safe_float(value):
    try:
        value = float(value)
    except Exception:
        return None

    if not math.isfinite(value):
        return None

    return value


def load_terminal_outcomes(path=OUTCOMES):
    if not path.exists():
        return []

    rows = []

    for line in path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():
        line = line.strip()

        if not line:
            continue

        try:
            row = json.loads(line)
        except Exception:
            continue

        if not isinstance(row, dict):
            continue

        if row.get("final_outcome") == "TRACKING":
            continue

        rows.append(row)

    return rows


def wilson_interval(wins, n, z=1.96):
    if n <= 0:
        return None, None

    p = wins / n
    denom = 1.0 + (z * z / n)
    centre = (
        p
        + z * z / (2.0 * n)
    ) / denom

    margin = (
        z
        * math.sqrt(
            (
                p * (1.0 - p) / n
                + z * z / (4.0 * n * n)
            )
        )
        / denom
    )

    return (
        max(0.0, centre - margin),
        min(1.0, centre + margin),
    )


def summarize(rows):
    n = len(rows)

    if n == 0:
        return {"n": 0}

    wins = sum(
        1 for row in rows
        if row.get("hit_plus_10")
    )
    hit_tp = sum(
        1 for row in rows
        if row.get("hit_tp")
    )
    hit_sl = sum(
        1 for row in rows
        if row.get("hit_sl")
    )
    ambiguous = sum(
        1 for row in rows
        if row.get("first_hit")
        == "TP_SL_SAME_M1_AMBIGUOUS"
    )

    rr_values = [
        value
        for value in (
            _safe_float(row.get("rr"))
            for row in rows
        )
        if value is not None
    ]
    mfe = [
        value
        for value in (
            _safe_float(
                row.get("max_favorable_usd")
            )
            for row in rows
        )
        if value is not None
    ]
    mae = [
        value
        for value in (
            _safe_float(
                row.get("max_adverse_usd")
            )
            for row in rows
        )
        if value is not None
    ]

    low, high = wilson_interval(wins, n)

    return {
        "n": n,
        "setup_wins_plus_10": wins,
        "setup_win_rate": wins / n,
        "setup_win_wilson_low": low,
        "setup_win_wilson_high": high,
        "tp_hit_rate": hit_tp / n,
        "sl_hit_rate": hit_sl / n,
        "same_m1_ambiguous_rate": ambiguous / n,
        "avg_shadow_rr": (
            mean(rr_values)
            if rr_values
            else None
        ),
        "avg_mfe_usd": (
            mean(mfe)
            if mfe
            else None
        ),
        "avg_mae_usd": (
            mean(mae)
            if mae
            else None
        ),
    }


def _fmt(value):
    if value is None:
        return "N/A"

    if isinstance(value, float):
        return f"{value:.3f}"

    return str(value)


def print_summary(title, rows):
    stats = summarize(rows)

    print()
    print(title)
    print("-" * len(title))
    print(f"n={stats.get('n', 0)}")

    if stats.get("n", 0) == 0:
        return

    print(
        "setup_win_+10="
        f"{stats['setup_wins_plus_10']}/"
        f"{stats['n']} "
        f"rate={stats['setup_win_rate']:.1%} "
        "wilson95="
        f"[{stats['setup_win_wilson_low']:.1%}, "
        f"{stats['setup_win_wilson_high']:.1%}]"
    )
    print(
        f"tp_hit_rate={stats['tp_hit_rate']:.1%} "
        f"sl_hit_rate={stats['sl_hit_rate']:.1%} "
        "same_m1_ambiguous="
        f"{stats['same_m1_ambiguous_rate']:.1%}"
    )
    print(
        "avg_shadow_rr="
        f"{_fmt(stats['avg_shadow_rr'])} "
        "avg_mfe_usd="
        f"{_fmt(stats['avg_mfe_usd'])} "
        "avg_mae_usd="
        f"{_fmt(stats['avg_mae_usd'])}"
    )


def main():
    rows = load_terminal_outcomes()

    print(
        "DAILY LEVEL LADDER RECLAIM REVERSAL "
        "SHADOW EVALUATOR V1.1"
    )
    print(
        "Setup Win = favorable +$10 price move "
        "within the observation horizon."
    )
    print(
        "Observer-only counterfactual data; "
        "not causal live-execution evidence."
    )

    print_summary(
        "ALL TERMINAL OBSERVATIONS",
        rows,
    )

    groups = defaultdict(list)

    for row in rows:
        groups[
            (
                row.get("signal"),
                row.get("strong_level"),
                bool(row.get("rr_pass")),
            )
        ].append(row)

    for key in sorted(
        groups,
        key=lambda item: (
            str(item[0]),
            float(item[1])
            if item[1] is not None
            else 0.0,
            str(item[2]),
        ),
    ):
        signal, level, rr_pass = key

        print_summary(
            (
                f"signal={signal} "
                f"level={level} "
                f"rr_pass={rr_pass}"
            ),
            groups[key],
        )

    if len(rows) < 20:
        print()
        print(
            "PROMOTION READINESS: TOO EARLY "
            "(fewer than 20 terminal observations)."
        )
    elif len(rows) < 50:
        print()
        print(
            "PROMOTION READINESS: EARLY INDICATION ONLY "
            "(20-49 terminal observations)."
        )
    else:
        print()
        print(
            "PROMOTION READINESS: SAMPLE SIZE IS MEANINGFUL; "
            "still require stable results by level/direction "
            "and low ambiguity before any execution promotion."
        )


if __name__ == "__main__":
    main()
