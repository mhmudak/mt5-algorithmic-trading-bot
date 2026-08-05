
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intrabar_json_optimization_report import (
    build_phase6u_intrabar_json_optimization_report,
    parse_policy_key,
    write_phase6u_intrabar_json_optimization_report,
)


SETTINGS = Path("config/settings.py")


def test_phase6u2_parse_policy_key():
    parsed = parse_policy_key(
        "FAILED_FVG_REVERSAL|BUY|UNKNOWN|ASIA|INTRABAR_PENDING|INTRABAR"
    )

    assert parsed["strategy"] == "FAILED_FVG_REVERSAL"
    assert parsed["direction"] == "BUY"
    assert parsed["session"] == "ASIA"
    assert parsed["source_bucket"] == "INTRABAR"


def test_phase6u2_build_report_from_json_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        perf = {
            "top_intrabar_trade_diagnostic": [
                {
                    "policy_key": "AUTO_STRUCTURAL_LEVEL_SCALP|BUY|ASIA|INTRABAR_STRUCTURAL_LEVEL_SCALP|INTRABAR",
                    "sample_count": 21,
                    "closed_count": 21,
                    "realized_count": 0,
                    "decision": "DIAGNOSTIC_ONLY",
                    "decision_reason": "trade tracker not reliable yet",
                    "w10_rate": 0.0,
                    "tp_rate": 0.0,
                    "sl_rate": 0.0,
                },
                {
                    "policy_key": "MICRO_SR_SWEEP_RECLAIM|BUY|LONDON_OPEN|INTRABAR_PENDING|INTRABAR",
                    "sample_count": 2,
                    "closed_count": 1,
                    "realized_count": 0,
                    "decision": "DIAGNOSTIC_ONLY",
                    "decision_reason": "trade tracker not reliable yet",
                    "w10_rate": 0.0,
                    "tp_rate": 0.0,
                    "sl_rate": 0.0,
                },
            ]
        }

        outcomes = [
            {
                "strategy": "FAILED_FVG_REVERSAL",
                "source_bucket": "INTRABAR",
                "session": "ASIA",
                "sample_count": 5,
                "decision": "TRACK_ONLY",
            }
        ]

        perf_path = root / "strategy_performance_report.json"
        outcomes_path = root / "setup_outcomes.json"

        perf_path.write_text(json.dumps(perf), encoding="utf-8")
        outcomes_path.write_text(json.dumps(outcomes), encoding="utf-8")

        report = build_phase6u_intrabar_json_optimization_report(
            strategy_performance_report_path=perf_path,
            setup_outcomes_path=outcomes_path,
            allowed_strategies=("AUTO_STRUCTURAL_LEVEL_SCALP", "FAILED_FVG_REVERSAL"),
            block_others=True,
        )

        assert report["phase"] == "PHASE_6U2_INTRABAR_JSON_OPTIMIZATION_REPORT"
        assert report["decision_impact"] == "REPORT_ONLY"
        assert report["can_execute"] is False
        assert report["can_block_trade"] is False
        assert report["can_modify_risk"] is False
        assert report["can_modify_entry_sl_tp"] is False
        assert report["can_modify_detection"] is False

        actions = report["by_recommended_action"]
        assert actions["KEEP_EXECUTING_BY_USER_ALLOWLIST"] >= 2
        assert actions["BLOCK_INTRABAR_DETECTION_AND_EXECUTION_BY_USER_RULE"] >= 1

        blocked = report["block_or_disable"]
        assert any(row["strategy"] == "MICRO_SR_SWEEP_RECLAIM" for row in blocked)



def test_phase6u2_ignores_container_rows_and_generic_intrabar_rows():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        perf = {
            "bad_container": {
                "strategy": [{"policy_key": "ORB_V00", "strategy": "ORB_V00"}],
                "decision": "TRACK_ONLY",
            },
            "generic_intrabar": {
                "policy_key": "INTRABAR",
                "strategy": "INTRABAR",
                "sample_count": 94,
                "decision": "TRACK_ONLY",
            },
            "valid_intrabar": {
                "policy_key": "MICRO_SR_SWEEP_RECLAIM|BUY|LONDON_OPEN|INTRABAR_PENDING|INTRABAR",
                "strategy": "MICRO_SR_SWEEP_RECLAIM",
                "sample_count": 2,
                "decision": "TRACK_ONLY",
            },
        }

        perf_path = root / "strategy_performance_report.json"
        outcomes_path = root / "setup_outcomes.json"

        perf_path.write_text(json.dumps(perf), encoding="utf-8")
        outcomes_path.write_text(json.dumps([]), encoding="utf-8")

        report = build_phase6u_intrabar_json_optimization_report(
            strategy_performance_report_path=perf_path,
            setup_outcomes_path=outcomes_path,
            allowed_strategies=("AUTO_STRUCTURAL_LEVEL_SCALP", "FAILED_FVG_REVERSAL"),
            block_others=True,
        )

        assert "INTRABAR" not in report["by_strategy"]
        assert "" not in report["by_strategy"]
        assert not any("[" in key or "{" in key for key in report["by_strategy"])
        assert report["by_strategy"]["MICRO_SR_SWEEP_RECLAIM"] == 1
def test_phase6u2_write_report():
    with tempfile.TemporaryDirectory() as tmp:
        report = {
            "phase": "PHASE_6U2_INTRABAR_JSON_OPTIMIZATION_REPORT",
            "user_rule": {"allowed_strategies": ["FAILED_FVG_REVERSAL"], "block_others": True},
            "counts": {"intrabar_rows": 0, "keep_rows": 0, "blocked_rows": 0},
            "keep_executing": [],
            "block_or_disable": [],
            "warning": "test",
        }

        written = write_phase6u_intrabar_json_optimization_report(report, output_dir=tmp)

        assert Path(written["json"]).exists()
        assert Path(written["latest_json"]).exists()
        assert Path(written["text"]).exists()
        assert Path(written["latest_text"]).exists()


def test_phase6u2_settings_exist():
    text = SETTINGS.read_text(encoding="utf-8")

    assert "PHASE6U_INTRABAR_JSON_OPTIMIZATION_OUTPUT_DIR" in text
    assert "PHASE6U_INTRABAR_JSON_OPTIMIZATION_ALLOWED_STRATEGIES" in text
    assert '"AUTO_STRUCTURAL_LEVEL_SCALP"' in text
    assert '"FAILED_FVG_REVERSAL"' in text
    assert "PHASE6U_INTRABAR_JSON_OPTIMIZATION_BLOCK_OTHERS = True" in text


if __name__ == "__main__":
    test_phase6u2_parse_policy_key()
    test_phase6u2_build_report_from_json_files()
    test_phase6u2_ignores_container_rows_and_generic_intrabar_rows()
    test_phase6u2_write_report()
    test_phase6u2_settings_exist()
    print("[PASS] Phase 6U2 intrabar JSON optimizer passed.")
