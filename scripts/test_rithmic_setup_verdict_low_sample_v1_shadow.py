from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.rithmic_setup_verdict as verdict_module


def _context(
    *,
    status: str = "LOW_SAMPLE_OBSERVATION_ONLY",
    fresh: bool = True,
) -> dict:
    return {
        "rithmic": {
            "available": False,
            "status": status,
            "rithmic_symbol": "GCZ6",
            "exchange": "COMEX",
            "cache_status": "FRESH",
            "cache_age_seconds": 1.0,
            "freshness": {
                "snapshot_age_seconds": 1.0,
                "last_trade_age_seconds": 1.0,
                "last_bbo_age_seconds": 1.0,
                "last_order_book_age_seconds": 1.0,
                "snapshot_fresh": fresh,
                "has_fresh_trade": fresh,
                "has_fresh_bbo": fresh,
                "has_fresh_order_book": fresh,
            },
            "metrics": {
                "trade_count": 4,
                "bbo_count": 20,
                "nonzero_bbo_count": 20,
                "order_book_count": 20,
                "delta": 14.0,
                "cumulative_delta": 14.0,
                "dom_depth_imbalance": -0.093,
                "dom_bid_depth": 100.0,
                "dom_ask_depth": 120.0,
            },
        },
    }


def _assert_zero_authority(verdict: dict) -> None:
    assert verdict["decision_impact"] == "NONE"
    assert verdict["can_influence_decision"] is False
    assert verdict["safe_for_execution"] is False
    assert verdict["execution_allowed"] is False
    assert verdict["supports_setup"] is False
    assert verdict["against_setup"] is False


def main() -> None:
    original_registration = (
        verdict_module._load_phase5v_registration
    )

    try:
        verdict_module._load_phase5v_registration = lambda: {
            "registered": True,
            "payload": {
                "symbol": "GCZ6",
                "source_market": "COMEX",
            },
        }

        # ----------------------------------------------------
        # Fresh LOW_SAMPLE:
        # V2 stays unavailable, V1 shadow may still display.
        # ----------------------------------------------------
        verdict = verdict_module.build_rithmic_setup_verdict(
            _context(),
            "SELL",
        )

        block = (
            verdict_module
            .format_rithmic_setup_verdict_telegram_block(
                verdict
            )
        )

        assert verdict["verdict"] == "UNAVAILABLE"
        assert (
            verdict["alignment"]
            == "NOT_AVAILABLE_RITHMIC_SNAPSHOT"
        )
        assert (
            verdict["reason"]
            == "LOW_SAMPLE_OBSERVATION_ONLY"
        )

        assert verdict["legacy_v1_evaluated"] is True
        assert verdict["legacy_v1_support_score"] == 1
        assert verdict["legacy_v1_against_score"] == 2

        expected_title = (
            "\U0001F9EA V1 LEGACY "
            "\u2014 SHADOW ONLY"
        )
        expected_evidence = "\U0001F4CA Evidence:"

        assert expected_title in block
        assert expected_evidence in block

        _assert_zero_authority(verdict)

        print(
            "PASS: fresh LOW_SAMPLE exposes V1 shadow "
            "while V2 remains unavailable"
        )

        # ----------------------------------------------------
        # LOW_SAMPLE but stale:
        # V1 must NOT be evaluated/displayed.
        # ----------------------------------------------------
        stale_verdict = (
            verdict_module.build_rithmic_setup_verdict(
                _context(fresh=False),
                "SELL",
            )
        )

        stale_block = (
            verdict_module
            .format_rithmic_setup_verdict_telegram_block(
                stale_verdict
            )
        )

        assert (
            stale_verdict["reason"]
            == "LOW_SAMPLE_OBSERVATION_ONLY"
        )
        assert (
            stale_verdict["legacy_v1_evaluated"]
            is False
        )
        assert expected_title not in stale_block

        _assert_zero_authority(stale_verdict)

        print(
            "PASS: stale LOW_SAMPLE cannot expose "
            "legacy V1 shadow"
        )

        # ----------------------------------------------------
        # Other unavailable state:
        # special LOW_SAMPLE exception must not broaden.
        # ----------------------------------------------------
        unavailable_verdict = (
            verdict_module.build_rithmic_setup_verdict(
                _context(
                    status="LOGIN_NOT_OK",
                    fresh=True,
                ),
                "SELL",
            )
        )

        unavailable_block = (
            verdict_module
            .format_rithmic_setup_verdict_telegram_block(
                unavailable_verdict
            )
        )

        assert unavailable_verdict["verdict"] == "UNAVAILABLE"
        assert unavailable_verdict["reason"] == "LOGIN_NOT_OK"
        assert (
            unavailable_verdict["legacy_v1_evaluated"]
            is False
        )
        assert expected_title not in unavailable_block

        _assert_zero_authority(unavailable_verdict)

        print(
            "PASS: LOW_SAMPLE exception does not broaden "
            "to other unavailable provider states"
        )

        print()
        print(
            "[PASS] Rithmic LOW_SAMPLE V1 shadow "
            "safety contract verified."
        )

    finally:
        verdict_module._load_phase5v_registration = (
            original_registration
        )


if __name__ == "__main__":
    main()
