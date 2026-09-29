from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_momentum_family_shadow_v1 import analyze


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def make_item(
    setup_id,
    signal,
    strength,
    entry,
    sl,
    tp,
    mfe,
    mae,
    *,
    hit_tp=False,
    hit_sl=False,
    pivot_aligned=True,
    nearest_kind="UPPER",
    nearest_distance=0.30,
):
    return {
        "setup_id": setup_id,
        "created_at": "2026-09-23T20:00:00",
        "strategy": "INTRABAR_MICRO_MOMENTUM",
        "signal": signal,
        "entry_model": "TICK_VELOCITY_ACCELERATION_PERSISTENCE",
        "score": 95,
        "session": "NEWYORK",
        "market_condition": "TRENDING",
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "max_favorable_usd": mfe,
        "max_adverse_usd": mae,
        "hit_tp": hit_tp,
        "hit_sl": hit_sl,
        "first_hit": (
            "TP_TOUCH" if hit_tp and not hit_sl
            else "SL_TOUCH" if hit_sl and not hit_tp
            else None
        ),
        "final_outcome": (
            "TP_TOUCH" if hit_tp and not hit_sl
            else "SL_TOUCH" if hit_sl and not hit_tp
            else None
        ),
        "extra": {
            "family": "MOMENTUM_FAMILY",
            "shadow_only": True,
            "execution_mode": "SHADOW_ONLY",
            "decision_impact": "NONE",
            "orders_sent": 0,
            "strength": strength,
            "sample_count": 8,
            "span_seconds": 4.0,
            "absolute_move": 0.50,
            "velocity_price_per_sec": 0.125,
            "persistence": 0.875,
            "acceleration_ratio": 1.8,
            "spread": 0.10,
            "daily_level_context": {
                "available": True,
                "source": "AUTO_STRONG_DAILY_LADDER",
                "pivot_side": "ABOVE" if signal == "BUY" else "BELOW",
                "pivot_direction_aligned": pivot_aligned,
                "nearest_level_kind": nearest_kind,
                "nearest_level_distance": nearest_distance,
                "next_level_distance": 4.0,
                "execution_authority": False,
                "role": "MOMENTUM_CONTEXT_ONLY",
            },
            "runner_research_role": "LOW_MAE_MOMENTUM_RUNNER_SOURCE",
        },
    }


def main():
    print("[MOMENTUM FAMILY SHADOW ANALYZER TEST V1]")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        source = tmp / "Demo_123"
        output = tmp / "out"
        source.mkdir(parents=True)

        # A: clear low-MAE runner: risk=.40, MFE=1.80=4.5R, MAE=.10=.25R
        a = make_item(
            "A", "BUY", "NORMAL",
            100.0, 99.6, 101.2,
            1.80, 0.10,
            hit_tp=True,
        )

        # B: profitable impulse but too much adverse excursion for runner label.
        b = make_item(
            "B", "BUY", "NORMAL",
            100.0, 99.6, 101.2,
            1.60, 0.30,
            hit_tp=True,
        )

        # C: stop / weak path.
        c = make_item(
            "C", "SELL", "WEAK_VALID",
            100.0, 100.3, 99.4,
            0.20, 0.35,
            hit_sl=True,
            pivot_aligned=False,
            nearest_kind="PIVOT",
            nearest_distance=0.10,
        )

        # D: explosive runner: risk=.50, MFE=2.50=5R, MAE=.20=.4R.
        d = make_item(
            "D", "SELL", "EXPLOSIVE",
            100.0, 100.5, 98.0,
            2.50, 0.20,
            hit_tp=True,
        )

        # Different strategy must be excluded.
        other = dict(a)
        other["setup_id"] = "OTHER"
        other["strategy"] = "FAILED_FVG_REVERSAL"

        # Same strategy but not shadow-only must be excluded.
        invalid = dict(a)
        invalid["setup_id"] = "INVALID"
        invalid["extra"] = dict(a["extra"])
        invalid["extra"]["shadow_only"] = False

        items = {
            x["setup_id"]: x
            for x in (a, b, c, d, other, invalid)
        }

        (source / "setup_outcomes.json").write_text(
            json.dumps(items, indent=2),
            encoding="utf-8",
        )

        manifest, rows, by_strength, runners = analyze(
            source_dir=source,
            output_dir=output,
            min_review_samples=2,
        )

        print("\n[MANIFEST]")
        print(json.dumps(manifest, indent=2, sort_keys=True))

        assert_true(manifest["total_setup_outcomes"] == 6, manifest)
        assert_true(manifest["momentum_shadow_rows"] == 4, manifest)
        assert_true(manifest["excluded_other_strategy_rows"] == 1, manifest)
        assert_true(manifest["excluded_invalid_shadow_rows"] == 1, manifest)
        assert_true(manifest["low_mae_runner_observed_rows"] == 2, manifest)
        assert_true(manifest["live_authority"] is False, manifest)

        by_id = {row["setup_id"]: row for row in rows}

        print("\n[RUNNER A]")
        print(by_id["A"])
        assert_true(by_id["A"]["low_mae_runner_observed"] is True, by_id["A"])
        assert_true(abs(by_id["A"]["mfe_r"] - 4.5) < 1e-12, by_id["A"])
        assert_true(abs(by_id["A"]["mae_r"] - 0.25) < 1e-12, by_id["A"])

        print("\n[NON-RUNNER B]")
        print(by_id["B"])
        assert_true(by_id["B"]["low_mae_runner_observed"] is False, by_id["B"])
        assert_true(by_id["B"]["mae_r"] > 0.50, by_id["B"])

        runner_ids = {row["setup_id"] for row in runners}
        assert_true(runner_ids == {"A", "D"}, runner_ids)

        strengths = {row["strength"]: row for row in by_strength}
        print("\n[NORMAL SUMMARY]")
        print(strengths["NORMAL"])
        assert_true(strengths["NORMAL"]["n"] == 2, strengths["NORMAL"])
        assert_true(strengths["NORMAL"]["review_status"] == "ELIGIBLE_FOR_REVIEW", strengths["NORMAL"])

        required = [
            "momentum_shadow_rows.csv",
            "summary_by_strength.csv",
            "summary_by_direction_strength.csv",
            "summary_by_session.csv",
            "summary_by_market_condition.csv",
            "summary_by_daily_context.csv",
            "low_mae_runner_candidates.csv",
            "manifest.json",
            "summary.txt",
        ]
        for name in required:
            assert_true((output / name).exists(), name)

        with (output / "low_mae_runner_candidates.csv").open(
            "r",
            encoding="utf-8",
        ) as fh:
            csv_rows = list(csv.DictReader(fh))
        assert_true(len(csv_rows) == 2, csv_rows)

        print(
            "\nPASS: shadow-only isolation, MFE/MAE normalization, "
            "context summaries, and descriptive Low-MAE Runner extraction verified."
        )


if __name__ == "__main__":
    main()
