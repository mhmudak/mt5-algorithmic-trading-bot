
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.market_outlook_evidence_health import (
    build_phase6s_evidence_health_report,
    classify_phase6s_evidence_health,
    scan_phase6s_execution_annotations,
    write_phase6s_evidence_health_report,
)


def test_phase6s10_ready_waiting_for_executions():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        settings_path = root / "settings.py"
        annotation_dir = root / "annotations"

        settings_path.write_text(
            """
ENABLE_PHASE6S_RUNTIME_OUTLOOK_ADVISORY = True
SEND_PHASE6S_RUNTIME_OUTLOOK_ADVISORY_TELEGRAM = False
PHASE6S_RUNTIME_OUTLOOK_ADVISORY_FORCE_SEND = False
ENABLE_PHASE6S_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION = True
""",
            encoding="utf-8",
        )

        report = build_phase6s_evidence_health_report(
            settings_path=settings_path,
            annotation_dir=annotation_dir,
            latest_attribution_path=root / "missing_attribution.json",
        )

        assert report["phase"] == "PHASE_6S10_EVIDENCE_COLLECTION_HEALTH"
        assert report["health_status"] == "EVIDENCE_COLLECTION_READY_WAITING_FOR_EXECUTIONS"
        assert report["decision_impact"] == "REPORT_ONLY"
        assert report["auto_trade_allowed"] is False
        assert report["can_execute"] is False
        assert report["can_block_trade"] is False
        assert report["can_modify_risk"] is False
        assert report["can_modify_entry_sl_tp"] is False


def test_phase6s10_active_with_data():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        annotation_dir = root / "annotations"
        annotation_dir.mkdir()

        row = {
            "phase": "PHASE_6S8_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION",
            "created_at_utc": "2026-08-03T00:00:00+00:00",
            "setup_id": "TEST-001",
            "tag": "OUTLOOK_ALIGNED",
            "strategy": "FCR_M1_FVG",
        }

        (annotation_dir / "phase6s_execution_annotations_20260803.jsonl").write_text(
            json.dumps(row) + "\n",
            encoding="utf-8",
        )

        scan = scan_phase6s_execution_annotations(annotation_dir)

        assert scan["annotations"] == 1
        assert scan["tags"]["OUTLOOK_ALIGNED"] == 1
        assert scan["strategies"]["FCR_M1_FVG"] == 1

        status = classify_phase6s_evidence_health(
            {
                "ENABLE_PHASE6S_RUNTIME_OUTLOOK_ADVISORY": True,
                "SEND_PHASE6S_RUNTIME_OUTLOOK_ADVISORY_TELEGRAM": False,
                "PHASE6S_RUNTIME_OUTLOOK_ADVISORY_FORCE_SEND": False,
                "ENABLE_PHASE6S_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION": True,
            },
            scan,
        )

        assert status == "EVIDENCE_COLLECTION_ACTIVE_WITH_DATA"


def test_phase6s10_telegram_enabled_requires_review():
    status = classify_phase6s_evidence_health(
        {
            "ENABLE_PHASE6S_RUNTIME_OUTLOOK_ADVISORY": True,
            "SEND_PHASE6S_RUNTIME_OUTLOOK_ADVISORY_TELEGRAM": True,
            "PHASE6S_RUNTIME_OUTLOOK_ADVISORY_FORCE_SEND": False,
            "ENABLE_PHASE6S_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION": True,
        },
        {"annotations": 0},
    )

    assert status == "REVIEW_TELEGRAM_OR_FORCE_SEND_ENABLED"


def test_phase6s10_write_report():
    with tempfile.TemporaryDirectory() as tmp:
        report = {
            "phase": "PHASE_6S10_EVIDENCE_COLLECTION_HEALTH",
            "health_status": "TEST",
        }

        written = write_phase6s_evidence_health_report(report, output_dir=tmp)

        assert Path(written["json"]).exists()
        assert Path(written["latest_json"]).exists()


if __name__ == "__main__":
    test_phase6s10_ready_waiting_for_executions()
    test_phase6s10_active_with_data()
    test_phase6s10_telegram_enabled_requires_review()
    test_phase6s10_write_report()
    print("[PASS] Phase 6S10 evidence health passed.")
