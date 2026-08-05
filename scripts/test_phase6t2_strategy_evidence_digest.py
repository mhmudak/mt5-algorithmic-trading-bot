
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.strategy_evidence_digest import (
    build_phase6t_strategy_evidence_digest,
    maybe_send_phase6t_strategy_evidence_digest,
    write_phase6t_strategy_evidence_digest,
)


def _sample_dashboard():
    return {
        "phase": "PHASE_6T1_STRATEGY_EVIDENCE_DASHBOARD",
        "decision_impact": "DASHBOARD_ONLY",
        "source": {
            "attribution_counts": {
                "annotations": 54,
                "matched": 24,
                "unmatched": 30,
            }
        },
        "classification_counts": {
            "INSUFFICIENT_EVIDENCE": 5,
            "NEUTRAL_OR_MIXED": 1,
        },
        "strategy_rows": [
            {
                "strategy": "FCR_M1_FVG",
                "outlook_tag": "",
                "classification": "NEUTRAL_OR_MIXED",
                "evidence_score": 12.5,
                "matched_outcomes": 10,
                "wins": 5,
                "losses": 5,
                "net_profit": 12,
                "win_rate_pct": 50,
            }
        ],
        "strategy_tag_rows": [
            {
                "strategy": "FCR_M1_FVG",
                "outlook_tag": "OUTLOOK_CAUTION",
                "classification": "NEUTRAL_OR_MIXED",
                "evidence_score": 12.5,
                "matched_outcomes": 10,
                "wins": 5,
                "losses": 5,
                "net_profit": 12,
                "win_rate_pct": 50,
            },
            {
                "strategy": "ORB_TICK_WATCHER",
                "outlook_tag": "OUTLOOK_CAUTION",
                "classification": "INSUFFICIENT_EVIDENCE",
                "evidence_score": 3.1,
                "matched_outcomes": 2,
                "wins": 1,
                "losses": 1,
                "net_profit": -1,
                "win_rate_pct": 50,
            },
        ],
    }


def test_phase6t2_digest_safety_and_content():
    digest = build_phase6t_strategy_evidence_digest(_sample_dashboard(), top_n=5)

    assert digest["phase"] == "PHASE_6T2_STRATEGY_EVIDENCE_DIGEST"
    assert digest["decision_impact"] == "DIGEST_ONLY"
    assert digest["auto_trade_allowed"] is False
    assert digest["can_execute"] is False
    assert digest["can_block_trade"] is False
    assert digest["can_modify_risk"] is False
    assert digest["can_modify_entry_sl_tp"] is False
    assert digest["can_modify_strategy_policy"] is False

    message = digest["message"]
    assert "Phase 6T Strategy Evidence Digest" in message
    assert "Decision impact: NONE" in message
    assert "annotations=54" in message
    assert "matched=24" in message
    assert "FCR_M1_FVG / OUTLOOK_CAUTION" in message


def test_phase6t2_telegram_disabled_by_default():
    calls = []

    digest = build_phase6t_strategy_evidence_digest(_sample_dashboard(), top_n=5)

    result = maybe_send_phase6t_strategy_evidence_digest(
        digest,
        send_telegram=False,
        notifier=lambda message: calls.append(message),
    )

    assert result["telegram_sent"] is False
    assert result["reason"] == "telegram_send_disabled"
    assert calls == []


def test_phase6t2_telegram_send_when_explicit():
    calls = []

    digest = build_phase6t_strategy_evidence_digest(_sample_dashboard(), top_n=5)

    result = maybe_send_phase6t_strategy_evidence_digest(
        digest,
        send_telegram=True,
        notifier=lambda message: calls.append(message),
    )

    assert result["telegram_sent"] is True
    assert result["reason"] == "sent"
    assert len(calls) == 1
    assert "Phase 6T Strategy Evidence Digest" in calls[0]


def test_phase6t2_write_files():
    with tempfile.TemporaryDirectory() as tmp:
        digest = build_phase6t_strategy_evidence_digest(_sample_dashboard(), top_n=5)
        written = write_phase6t_strategy_evidence_digest(digest, output_dir=tmp)

        assert Path(written["json"]).exists()
        assert Path(written["latest_json"]).exists()
        assert Path(written["text"]).exists()
        assert Path(written["latest_text"]).exists()


if __name__ == "__main__":
    test_phase6t2_digest_safety_and_content()
    test_phase6t2_telegram_disabled_by_default()
    test_phase6t2_telegram_send_when_explicit()
    test_phase6t2_write_files()
    print("[PASS] Phase 6T2 strategy evidence digest passed.")
