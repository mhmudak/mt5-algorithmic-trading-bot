
from pathlib import Path
import json
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.market_outlook_execution_annotation import (
    classify_phase6s_outlook_execution_tag,
    build_phase6s_execution_annotation,
    append_phase6s_execution_annotation,
)


SETTINGS = Path("config/settings.py")
LIVE_BOT = Path("src/live_bot.py")


def test_phase6s8_classification_tags():
    assert classify_phase6s_outlook_execution_tag(None) == "OUTLOOK_NOT_AVAILABLE"
    assert classify_phase6s_outlook_execution_tag({"enabled": False}) == "OUTLOOK_ADVISORY_DISABLED"
    assert classify_phase6s_outlook_execution_tag({"ready": False}) == "OUTLOOK_NOT_READY"

    aligned = {
        "enabled": True,
        "ready": True,
        "alignment": "ALIGNED_WITH_OUTLOOK_LEADER",
        "risk_level": "LOW",
    }
    assert classify_phase6s_outlook_execution_tag(aligned) == "OUTLOOK_ALIGNED"

    high_risk = {
        "enabled": True,
        "ready": True,
        "alignment": "AGAINST_OUTLOOK_LEADER",
        "risk_level": "HIGH",
    }
    assert classify_phase6s_outlook_execution_tag(high_risk) == "OUTLOOK_HIGH_RISK"


def test_phase6s8_annotation_is_safety_only():
    annotation = build_phase6s_execution_annotation(
        advisory_summary={
            "enabled": True,
            "ready": True,
            "alignment": "AGAINST_OUTLOOK_LEADER",
            "risk_level": "HIGH",
            "decision_impact": "ADVISORY_ONLY",
            "can_block_trade": False,
            "can_modify_risk": False,
        },
        setup_payload={
            "symbol": "XAUUSD",
            "setup_id": "TEST-001",
            "strategy": "FCR_M1_FVG",
            "signal": "SELL",
            "entry_reference": 4043,
            "sl_reference": 4055,
            "tp_reference": 4010,
            "rr": 2.7,
        },
        execution_result=True,
    )

    assert annotation["tag"] == "OUTLOOK_HIGH_RISK"
    assert annotation["decision_impact"] == "ANNOTATION_ONLY"
    assert annotation["auto_trade_allowed"] is False
    assert annotation["can_execute"] is False
    assert annotation["can_block_trade"] is False
    assert annotation["can_modify_risk"] is False
    assert annotation["can_modify_entry_sl_tp"] is False


def test_phase6s8_jsonl_write():
    annotation = build_phase6s_execution_annotation(
        advisory_summary={"enabled": False},
        setup_payload={"symbol": "XAUUSD", "setup_id": "TEST-JSONL"},
        execution_result=False,
    )

    with tempfile.TemporaryDirectory() as tmp:
        path = append_phase6s_execution_annotation(annotation, directory=tmp)
        assert path.exists()

        rows = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(rows) == 1

        loaded = json.loads(rows[0])
        assert loaded["phase"] == "PHASE_6S8_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION"
        assert loaded["setup_id"] == "TEST-JSONL"


def test_phase6s8_settings_allow_evidence_collection_mode():
    text = SETTINGS.read_text(encoding="utf-8")

    assert "ENABLE_PHASE6S_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION = True" in text or "ENABLE_PHASE6S_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION = False" in text
    assert "PHASE6S_RUNTIME_OUTLOOK_EXECUTION_ANNOTATION_DIR" in text


def test_phase6s8_live_bot_integration_markers():
    text = LIVE_BOT.read_text(encoding="utf-8")

    assert "from src.market_outlook_execution_annotation import (" in text
    assert "def maybe_record_phase6s_runtime_outlook_execution_annotation(" in text
    assert "phase6s_runtime_outlook_advisory_summary = maybe_notify_phase6s_runtime_outlook_advisory(" in text
    assert "maybe_record_phase6s_runtime_outlook_execution_annotation(" in text
    assert "execution_result = execute_trade(signal, trade_plan, SYMBOL)" in text

    execute_index = text.find("execution_result = execute_trade(signal, trade_plan, SYMBOL)")
    record_index = text.find("maybe_record_phase6s_runtime_outlook_execution_annotation(", execute_index)

    assert execute_index != -1
    assert record_index != -1
    assert execute_index < record_index


if __name__ == "__main__":
    test_phase6s8_classification_tags()
    test_phase6s8_annotation_is_safety_only()
    test_phase6s8_jsonl_write()
    test_phase6s8_settings_allow_evidence_collection_mode()
    test_phase6s8_live_bot_integration_markers()
    print("[PASS] Phase 6S8 execution annotation passed.")
