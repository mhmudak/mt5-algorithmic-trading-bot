
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.market_outlook_outcome_attribution import (
    build_phase6s_outcome_attribution_report,
    write_phase6s_outcome_attribution_report,
    load_trade_outcomes,
)


def _write_jsonl(path: Path, rows):
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_phase6s9_attribution_by_tag_and_strategy():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        annotation_dir = root / "annotations"
        annotation_dir.mkdir()

        _write_jsonl(
            annotation_dir / "phase6s_execution_annotations_20260803.jsonl",
            [
                {
                    "phase": "PHASE_6S8_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION",
                    "setup_id": "SETUP-A",
                    "tag": "OUTLOOK_ALIGNED",
                    "strategy": "FCR_M1_FVG",
                    "signal": "BUY",
                    "created_at_utc": "2026-08-03T00:00:00+00:00",
                },
                {
                    "phase": "PHASE_6S8_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION",
                    "setup_id": "SETUP-B",
                    "tag": "OUTLOOK_HIGH_RISK",
                    "strategy": "FCR_M1_FVG",
                    "signal": "SELL",
                    "created_at_utc": "2026-08-03T00:01:00+00:00",
                },
                {
                    "phase": "PHASE_6S8_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION",
                    "setup_id": "SETUP-C",
                    "tag": "OUTLOOK_CAUTION",
                    "strategy": "ORB_TICK_WATCHER",
                    "signal": "BUY",
                    "created_at_utc": "2026-08-03T00:02:00+00:00",
                },
            ],
        )

        outcome_path = root / "setup_outcomes.json"
        outcome_path.write_text(
            json.dumps(
                [
                    {"setup_id": "SETUP-A", "realized_profit": 10.0, "status": "CLOSED"},
                    {"setup_id": "SETUP-B", "realized_profit": -5.0, "status": "CLOSED"},
                    {"setup_id": "SETUP-C", "realized_profit": 0.0, "status": "CLOSED"},
                ],
                indent=2,
            ),
            encoding="utf-8",
        )

        report = build_phase6s_outcome_attribution_report(
            annotation_dir=annotation_dir,
            outcome_paths=[outcome_path],
            min_samples=2,
        )

        assert report["phase"] == "PHASE_6S9_OUTLOOK_OUTCOME_ATTRIBUTION_REPORT"
        assert report["decision_impact"] == "REPORT_ONLY"
        assert report["auto_trade_allowed"] is False
        assert report["can_execute"] is False
        assert report["can_block_trade"] is False
        assert report["can_modify_risk"] is False
        assert report["can_modify_entry_sl_tp"] is False

        assert report["counts"]["annotations"] == 3
        assert report["counts"]["matched"] == 3
        assert report["counts"]["unmatched"] == 0

        assert report["by_tag"]["OUTLOOK_ALIGNED"]["wins"] == 1
        assert report["by_tag"]["OUTLOOK_HIGH_RISK"]["losses"] == 1
        assert report["by_tag"]["OUTLOOK_CAUTION"]["breakeven"] == 1

        assert report["by_strategy_tag"]["FCR_M1_FVG|OUTLOOK_ALIGNED"]["net_profit"] == 10.0
        assert report["by_strategy_tag"]["FCR_M1_FVG|OUTLOOK_HIGH_RISK"]["net_profit"] == -5.0


def test_phase6s9_unmatched_is_not_guessed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        annotation_dir = root / "annotations"
        annotation_dir.mkdir()

        _write_jsonl(
            annotation_dir / "phase6s_execution_annotations_20260803.jsonl",
            [
                {
                    "phase": "PHASE_6S8_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION",
                    "setup_id": "MISSING-SETUP",
                    "tag": "OUTLOOK_HIGH_RISK",
                    "strategy": "FCR_M1_FVG",
                    "signal": "SELL",
                }
            ],
        )

        outcome_path = root / "setup_outcomes.json"
        outcome_path.write_text(
            json.dumps([{"setup_id": "OTHER-SETUP", "realized_profit": 50.0}]),
            encoding="utf-8",
        )

        report = build_phase6s_outcome_attribution_report(
            annotation_dir=annotation_dir,
            outcome_paths=[outcome_path],
        )

        assert report["counts"]["matched"] == 0
        assert report["counts"]["unmatched"] == 1
        assert report["by_tag"]["OUTLOOK_HIGH_RISK"]["unmatched"] == 1


def test_phase6s9_load_nested_trade_outcomes():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "trades.json"
        path.write_text(
            json.dumps(
                {
                    "trades": {
                        "SETUP-NESTED": {
                            "realized_profit": 12.5,
                            "status": "CLOSED",
                            "strategy": "TEST_STRATEGY",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        outcomes = load_trade_outcomes([path])

        assert len(outcomes) == 1
        assert outcomes[0]["setup_id"] == "SETUP-NESTED"
        assert outcomes[0]["profit"] == 12.5
        assert outcomes[0]["outcome_class"] == "WIN"


def test_phase6s9_write_report_files():
    with tempfile.TemporaryDirectory() as tmp:
        report = {
            "phase": "PHASE_6S9_OUTLOOK_OUTCOME_ATTRIBUTION_REPORT",
            "by_tag": {"OUTLOOK_ALIGNED": {"count": 1, "matched_outcomes": 1}},
            "by_strategy_tag": {"TEST|OUTLOOK_ALIGNED": {"count": 1, "matched_outcomes": 1}},
        }

        written = write_phase6s_outcome_attribution_report(report, output_dir=tmp)

        assert Path(written["json"]).exists()
        assert Path(written["latest_json"]).exists()
        assert Path(written["by_tag_csv"]).exists()
        assert Path(written["by_strategy_tag_csv"]).exists()


if __name__ == "__main__":
    test_phase6s9_attribution_by_tag_and_strategy()
    test_phase6s9_unmatched_is_not_guessed()
    test_phase6s9_load_nested_trade_outcomes()
    test_phase6s9_write_report_files()
    print("[PASS] Phase 6S9 outcome attribution report passed.")
