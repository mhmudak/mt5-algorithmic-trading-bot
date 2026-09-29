from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_setup_selection_oos_shadow_v1 import analyze


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def _shadow(badge, expected_win, expected_exp):
    return {
        "schema_version": 1,
        "captured_at_utc": "2026-09-23T16:00:00+00:00",
        "live_authority": False,
        "decision_impact": "NONE",
        "stage": "DETECTED",
        "badge": badge,
        "coarse_stance": "TEST",
        "win_quality": expected_win,
        "win_quality_pct": expected_win * 100.0,
        "final_expectancy_r": expected_exp,
        "evidence_grouping": "strategy",
        "sample_count": 100,
        "evidence": [],
    }


def _item(setup_id, badge, w10, outcome, expected_win, expected_exp):
    return {
        "setup_id": setup_id,
        "created_at": "2026-09-23T16:00:00",
        "strategy": "TEST_STRATEGY",
        "signal": "BUY",
        "entry_model": "TEST_MODEL",
        "session": "NEWYORK",
        "market_condition": "RANGING",
        "entry": 100.0,
        "sl": 95.0,
        "tp": 110.0,
        "hit_plus_10": w10,
        "hit_tp": outcome == "TP_TOUCH",
        "hit_sl": outcome == "SL_TOUCH",
        "final_outcome": outcome,
        "setup_selection_shadow": _shadow(badge, expected_win, expected_exp),
    }


def main():
    print("[SETUP SELECTION OOS ANALYZER TEST V1]")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        source = tmp / "Demo_123"
        output = tmp / "out"
        source.mkdir(parents=True)

        items = {
            "A": _item("A", "PREFERRED_TAKE_CANDIDATE", True, "TP_TOUCH", 0.70, 0.40),
            "B": _item("B", "PREFERRED_TAKE_CANDIDATE", True, "SL_TOUCH", 0.70, 0.40),
            "C": _item("C", "PREFERRED_TAKE_CANDIDATE", False, "SL_TOUCH", 0.70, 0.40),
            "D": _item("D", "GOOD_ENTRY_FIX_MANAGEMENT", True, "SL_TOUCH", 0.75, 0.05),
            "E": _item("E", "GOOD_ENTRY_FIX_MANAGEMENT", True, None, 0.75, 0.05),
            # Pre-snapshot history must be excluded, never backfilled.
            "OLD": {
                "setup_id": "OLD",
                "strategy": "TEST_STRATEGY",
                "signal": "BUY",
                "hit_plus_10": True,
                "final_outcome": "TP_TOUCH",
            },
        }

        (source / "setup_outcomes.json").write_text(
            json.dumps(items, indent=2),
            encoding="utf-8",
        )

        manifest, badge_summary = analyze(
            source_dir=source,
            output_dir=output,
            min_oos_resolved=3,
        )

        print(json.dumps(manifest, indent=2, sort_keys=True))
        assert_true(manifest["total_setup_outcomes"] == 6, manifest)
        assert_true(manifest["frozen_snapshot_rows"] == 5, manifest)
        assert_true(manifest["excluded_pre_snapshot_rows"] == 1, manifest)
        assert_true(manifest["selection_resolved_rows"] == 5, manifest)
        assert_true(manifest["final_path_resolved_rows"] == 4, manifest)
        assert_true(manifest["live_authority"] is False, manifest)

        by_badge = {row["badge"]: row for row in badge_summary}

        preferred = by_badge["PREFERRED_TAKE_CANDIDATE"]
        print("\n[PREFERRED]")
        print(preferred)
        assert_true(preferred["selection_resolved"] == 3, preferred)
        assert_true(preferred["selection_wins"] == 2, preferred)
        assert_true(abs(preferred["actual_selection_win_rate"] - (2 / 3)) < 1e-12, preferred)
        assert_true(preferred["w10_to_tp"] == 1, preferred)
        assert_true(preferred["w10_to_sl"] == 1, preferred)
        assert_true(abs(preferred["w10_to_sl_giveback_rate"] - 0.5) < 1e-12, preferred)
        # TP is +2R, SL is -1R, SL is -1R => 0R mean.
        assert_true(abs(preferred["actual_final_expectancy_r"] - 0.0) < 1e-12, preferred)
        assert_true(preferred["oos_validation_status"] == "ELIGIBLE_FOR_REVIEW", preferred)

        management = by_badge["GOOD_ENTRY_FIX_MANAGEMENT"]
        print("\n[MANAGEMENT]")
        print(management)
        assert_true(management["selection_resolved"] == 2, management)
        assert_true(management["selection_wins"] == 2, management)
        assert_true(management["w10_to_sl"] == 1, management)
        assert_true(management["w10_only"] == 1, management)
        assert_true(management["oos_validation_status"] == "COLLECTING", management)

        required = [
            output / "setup_selection_oos_rows.csv",
            output / "badge_oos_summary.csv",
            output / "strategy_badge_oos_summary.csv",
            output / "manifest.json",
            output / "summary.txt",
        ]
        for path in required:
            assert_true(path.exists(), path)

        with (output / "badge_oos_summary.csv").open("r", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert_true(len(rows) == 2, rows)

        print("\nPASS: pre-snapshot history excluded, frozen predictions calibrated against later outcomes, W10->SL leakage measured, and live authority remains disabled.")


if __name__ == "__main__":
    main()
