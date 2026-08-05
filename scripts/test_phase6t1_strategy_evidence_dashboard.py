
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.strategy_evidence_dashboard import (
    build_phase6t_strategy_evidence_dashboard,
    classify_strategy_evidence,
    write_phase6t_strategy_evidence_dashboard,
)


def test_phase6t1_classification():
    assert classify_strategy_evidence({"matched_outcomes": 2, "wins": 2, "losses": 0}) == "INSUFFICIENT_EVIDENCE"

    assert classify_strategy_evidence(
        {
            "matched_outcomes": 10,
            "wins": 7,
            "losses": 3,
            "breakeven": 0,
            "net_profit": 100,
            "win_rate_pct": 70,
        }
    ) == "PROMISING_EVIDENCE"

    assert classify_strategy_evidence(
        {
            "matched_outcomes": 10,
            "wins": 3,
            "losses": 7,
            "breakeven": 0,
            "net_profit": -50,
            "win_rate_pct": 30,
        }
    ) == "WEAK_EVIDENCE"


def test_phase6t1_dashboard_from_attribution_report():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        attribution_path = root / "phase6s_outcome_attribution_latest.json"

        attribution_path.write_text(
            json.dumps(
                {
                    "phase": "PHASE_6S9_OUTLOOK_OUTCOME_ATTRIBUTION_REPORT",
                    "counts": {
                        "annotations": 20,
                        "outcome_records": 20,
                        "matched": 20,
                        "unmatched": 0,
                    },
                    "by_tag": {
                        "OUTLOOK_CAUTION": {
                            "count": 10,
                            "matched_outcomes": 10,
                            "unmatched": 0,
                            "closed": 10,
                            "wins": 6,
                            "losses": 4,
                            "breakeven": 0,
                            "unknown": 0,
                            "net_profit": 80,
                            "avg_profit": 8,
                            "win_rate_pct": 60,
                            "loss_rate_pct": 40,
                        }
                    },
                    "by_strategy": {
                        "FCR_M1_FVG": {
                            "count": 10,
                            "matched_outcomes": 10,
                            "unmatched": 0,
                            "closed": 10,
                            "wins": 7,
                            "losses": 3,
                            "breakeven": 0,
                            "unknown": 0,
                            "net_profit": 120,
                            "avg_profit": 12,
                            "win_rate_pct": 70,
                            "loss_rate_pct": 30,
                        }
                    },
                    "by_strategy_tag": {
                        "FCR_M1_FVG|OUTLOOK_CAUTION": {
                            "count": 10,
                            "matched_outcomes": 10,
                            "unmatched": 0,
                            "closed": 10,
                            "wins": 7,
                            "losses": 3,
                            "breakeven": 0,
                            "unknown": 0,
                            "net_profit": 120,
                            "avg_profit": 12,
                            "win_rate_pct": 70,
                            "loss_rate_pct": 30,
                        }
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        dashboard = build_phase6t_strategy_evidence_dashboard(
            attribution_report_path=attribution_path,
            min_matched_samples=5,
        )

        assert dashboard["phase"] == "PHASE_6T1_STRATEGY_EVIDENCE_DASHBOARD"
        assert dashboard["decision_impact"] == "DASHBOARD_ONLY"
        assert dashboard["auto_trade_allowed"] is False
        assert dashboard["can_execute"] is False
        assert dashboard["can_block_trade"] is False
        assert dashboard["can_modify_risk"] is False
        assert dashboard["can_modify_entry_sl_tp"] is False
        assert dashboard["can_modify_strategy_policy"] is False

        assert len(dashboard["strategy_rows"]) == 1
        assert dashboard["strategy_rows"][0]["strategy"] == "FCR_M1_FVG"
        assert dashboard["strategy_rows"][0]["classification"] == "PROMISING_EVIDENCE"

        assert len(dashboard["strategy_tag_rows"]) == 1
        assert dashboard["strategy_tag_rows"][0]["outlook_tag"] == "OUTLOOK_CAUTION"


def test_phase6t1_missing_attribution_report_is_safe():
    with tempfile.TemporaryDirectory() as tmp:
        dashboard = build_phase6t_strategy_evidence_dashboard(
            attribution_report_path=Path(tmp) / "missing.json"
        )

        assert dashboard["source"]["attribution_report_exists"] is False
        assert dashboard["strategy_rows"] == []
        assert dashboard["strategy_tag_rows"] == []
        assert dashboard["decision_impact"] == "DASHBOARD_ONLY"


def test_phase6t1_write_dashboard_files():
    with tempfile.TemporaryDirectory() as tmp:
        dashboard = {
            "phase": "PHASE_6T1_STRATEGY_EVIDENCE_DASHBOARD",
            "strategy_rows": [],
            "strategy_tag_rows": [],
            "tag_rows": [],
        }

        written = write_phase6t_strategy_evidence_dashboard(dashboard, output_dir=tmp)

        assert Path(written["json"]).exists()
        assert Path(written["latest_json"]).exists()
        assert Path(written["by_strategy_csv"]).exists()
        assert Path(written["by_strategy_tag_csv"]).exists()
        assert Path(written["by_tag_csv"]).exists()


if __name__ == "__main__":
    test_phase6t1_classification()
    test_phase6t1_dashboard_from_attribution_report()
    test_phase6t1_missing_attribution_report_is_safe()
    test_phase6t1_write_dashboard_files()
    print("[PASS] Phase 6T1 strategy evidence dashboard passed.")
