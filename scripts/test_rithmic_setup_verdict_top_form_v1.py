from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import rithmic_setup_verdict as verdict_module
from scripts.run_phase5p_event_driven_rithmic_watcher import (
    score_alignment_for_direction as phase5p_score_alignment,
)


def _registration_payload(symbol: str = "GCZ6") -> dict:
    return {
        "provider": "RITHMIC_R_PROTOCOL",
        "provider_role": "REAL_ORDER_FLOW_SOURCE",
        "source_market": "COMEX",
        "symbol": symbol,
        "registration_status": "REGISTERED_OBSERVE_ONLY",
        "provider_quality": "ACCEPTED_OBSERVE_ONLY",
        "mode": "OBSERVE_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
        "gates": {
            "can_register_observe_only": True,
            "trade_flow_decision_grade": True,
            "decision_influence_allowed": False,
            "execution_allowed": False,
        },
    }


def _context(
    *,
    delta: float,
    cumulative_delta: float,
    dom_imbalance: float,
    bid_depth: float,
    ask_depth: float,
    trades: int = 21,
    cache_age_seconds: float = 0.2,
    symbol: str = "GCZ6",
    available: bool = True,
) -> dict:
    return {
        "source_coverage": "MT5_PLUS_RITHMIC",
        "rithmic": {
            "available": available,
            "status": "OBSERVE_ONLY_READY",
            "rithmic_symbol": symbol,
            "exchange": "COMEX",
            "cache_status": "FRESH_CACHE",
            "cache_age_seconds": cache_age_seconds,
            "freshness": {
                "snapshot_age_seconds": 0.2,
                "snapshot_fresh": True,
                "last_trade_age_seconds": 0.3,
                "last_bbo_age_seconds": 0.1,
                "last_order_book_age_seconds": 0.2,
                "has_fresh_trade": True,
                "has_fresh_bbo": True,
                "has_fresh_order_book": True,
            },
            "metrics": {
                "trade_count": trades,
                "bbo_count": 120,
                "nonzero_bbo_count": 120,
                "order_book_count": 1333,
                "delta": delta,
                "cumulative_delta": cumulative_delta,
                "dom_depth_imbalance": dom_imbalance,
                "dom_bid_depth": bid_depth,
                "dom_ask_depth": ask_depth,
            },
        },
    }


def _evidence_families_payload(
    *,
    aggression: str = "NEUTRAL",
    auction_profile: str = "NEUTRAL",
    footprint: str = "UNAVAILABLE",
    absorption: str = "NEUTRAL",
    liquidity: str = "NEUTRAL",
    divergence: str = "NEUTRAL",
) -> dict:
    def family(
        state: str,
        reason: str,
    ) -> dict:
        return {
            "state": state,
            "reason": reason,
            "available": state != "UNAVAILABLE",
            "directional": state in {
                "BUY",
                "SELL",
            },
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "safe_for_execution": False,
        }

    return {
        "engine": "RITHMIC_EVIDENCE_FAMILIES_V2",
        "feed_gate": {
            "usable": True,
            "reason": "healthy",
        },
        "families": {
            "AGGRESSION": family(
                aggression,
                "synthetic_aggression",
            ),
            "AUCTION_PROFILE": family(
                auction_profile,
                "synthetic_auction_profile",
            ),
            "FOOTPRINT_ACCEPTANCE": family(
                footprint,
                "synthetic_footprint",
            ),
            "ABSORPTION_EXHAUSTION": family(
                absorption,
                "synthetic_absorption",
            ),
            "LIQUIDITY_DYNAMICS": family(
                liquidity,
                "synthetic_liquidity",
            ),
            "DIVERGENCE_TRAP": family(
                divergence,
                "synthetic_divergence",
            ),
        },
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
    }


def main() -> None:
    original_registration_path = (
        verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH
    )
    original_evidence_loader = getattr(
        verdict_module,
        "_load_phase5g_evidence_families_v2",
        None,
    )

    active_evidence_payload = {
        "value": _evidence_families_payload()
    }

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            registration_path = Path(tmp_dir) / "phase5v.json"
            registration_path.write_text(
                json.dumps(
                    _registration_payload(),
                    indent=2,
                ),
                encoding="utf-8",
            )
            verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = (
                registration_path
            )

            verdict_module._load_phase5g_evidence_families_v2 = (
                lambda symbol: (
                    active_evidence_payload["value"],
                    "ok",
                    0.2,
                )
            )

            current_like = _context(
                delta=3,
                cumulative_delta=3,
                dom_imbalance=-0.120395,
                bid_depth=2495,
                ask_depth=3178,
            )
            active_evidence_payload["value"] = (
                _evidence_families_payload(
                    aggression="BUY",
                    auction_profile="BUY",
                    liquidity="SELL",
                )
            )

            support_buy = verdict_module.build_rithmic_setup_verdict(
                current_like,
                "BUY",
            )
            assert support_buy["verdict"] == "SUPPORTS_SETUP"
            assert support_buy["alignment"] == "SUPPORTS_BUY"
            assert support_buy["support_score"] == 2
            assert support_buy["against_score"] == 1
            assert support_buy["decision_impact"] == "NONE"
            assert support_buy["can_influence_decision"] is False
            assert support_buy["safe_for_execution"] is False
            assert support_buy["execution_allowed"] is False

            support_block = (
                verdict_module.format_rithmic_setup_verdict_telegram_block(
                    support_buy
                )
            )
            assert support_block.startswith(
                "🟢 RITHMIC: SUPPORTS BUY"
            )
            assert "GCZ6 | COMEX" in support_block
            assert "Mode: OBSERVE ONLY" in support_block

            active_evidence_payload["value"] = (
                _evidence_families_payload(
                    aggression="SELL",
                    auction_profile="SELL",
                )
            )

            against_buy = verdict_module.build_rithmic_setup_verdict(
                _context(
                    delta=-7,
                    cumulative_delta=-9,
                    dom_imbalance=-0.22,
                    bid_depth=2000,
                    ask_depth=3300,
                ),
                "BUY",
            )
            assert against_buy["verdict"] == "AGAINST_SETUP"
            assert against_buy["alignment"] == "AGAINST_BUY"

            active_evidence_payload["value"] = (
                _evidence_families_payload(
                    aggression="SELL",
                    auction_profile="SELL",
                )
            )

            support_sell = verdict_module.build_rithmic_setup_verdict(
                _context(
                    delta=-7,
                    cumulative_delta=-9,
                    dom_imbalance=-0.22,
                    bid_depth=2000,
                    ask_depth=3300,
                ),
                "SELL",
            )
            assert support_sell["verdict"] == "SUPPORTS_SETUP"
            assert support_sell["alignment"] == "SUPPORTS_SELL"

            active_evidence_payload["value"] = (
                _evidence_families_payload()
            )

            neutral = verdict_module.build_rithmic_setup_verdict(
                _context(
                    delta=0,
                    cumulative_delta=0,
                    dom_imbalance=0,
                    bid_depth=2500,
                    ask_depth=2500,
                ),
                "BUY",
            )
            assert neutral["verdict"] == "NEUTRAL"

            active_evidence_payload["value"] = (
                _evidence_families_payload(
                    aggression="BUY",
                    auction_profile="BUY",
                )
            )

            low_sample = verdict_module.build_rithmic_setup_verdict(
                _context(
                    delta=20,
                    cumulative_delta=30,
                    dom_imbalance=0.3,
                    bid_depth=3500,
                    ask_depth=1500,
                    trades=2,
                ),
                "BUY",
            )
            assert low_sample["verdict"] == "NEUTRAL"
            assert (
                low_sample["alignment"]
                == "NEUTRAL_LOW_RITHMIC_TRADE_SAMPLE"
            )

            stale = verdict_module.build_rithmic_setup_verdict(
                _context(
                    delta=20,
                    cumulative_delta=30,
                    dom_imbalance=0.3,
                    bid_depth=3500,
                    ask_depth=1500,
                    cache_age_seconds=9.0,
                ),
                "BUY",
            )
            assert stale["verdict"] == "UNAVAILABLE"
            assert stale["reason"] == "rithmic_cache_stale"

            mismatch = verdict_module.build_rithmic_setup_verdict(
                _context(
                    delta=20,
                    cumulative_delta=30,
                    dom_imbalance=0.3,
                    bid_depth=3500,
                    ask_depth=1500,
                    symbol="GCG7",
                ),
                "BUY",
            )
            assert mismatch["verdict"] == "UNAVAILABLE"
            assert mismatch["reason"] == "phase5v_symbol_mismatch"

            metrics = current_like["rithmic"]["metrics"]
            assert phase5p_score_alignment(
                "BUY",
                metrics,
            ) == verdict_module.score_rithmic_setup_alignment_for_direction(
                "BUY",
                metrics,
            )

            registration_path.unlink()
            missing_registration = (
                verdict_module.build_rithmic_setup_verdict(
                    current_like,
                    "BUY",
                )
            )
            assert missing_registration["verdict"] == "UNAVAILABLE"
            assert (
                missing_registration["reason"]
                == "phase5v_registration_missing"
            )
    finally:
        verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = (
            original_registration_path
        )

        if original_evidence_loader is not None:
            verdict_module._load_phase5g_evidence_families_v2 = (
                original_evidence_loader
            )
        elif hasattr(
            verdict_module,
            "_load_phase5g_evidence_families_v2",
        ):
            delattr(
                verdict_module,
                "_load_phase5g_evidence_families_v2",
            )

    live_text = (ROOT / "src" / "live_bot.py").read_text(
        encoding="utf-8"
    )
    setup_anchor = (
        "detected_message = (\n"
        "                    build_trade_message("
    )
    setup_start = live_text.index(setup_anchor)
    setup_end = live_text.index(
        "                send_telegram_message_async(\n"
        "                    detected_message",
        setup_start,
    )
    setup_region = live_text[setup_start:setup_end]

    assert "detected_rithmic_verdict_block" in setup_region
    assert "_rithmic_setup_verdict_telegram_fail_open(" in setup_region
    assert (
        'selected_signal_data[\n'
        '                    "rithmic_setup_verdict"\n'
        '                ] = detected_rithmic_verdict'
        in setup_region
    )
    assert (
        'detected_rithmic_verdict_block\n'
        '                        + "\\n--------------------------------\\n\\n"\n'
        '                        + detected_message'
        in setup_region
    )

    for path in [
        ROOT / "src" / "live_bot.py",
        ROOT / "src" / "market_participation_context.py",
        ROOT / "src" / "rithmic_setup_verdict.py",
        ROOT / "scripts" / "run_phase5p_event_driven_rithmic_watcher.py",
    ]:
        compile(
            path.read_text(encoding="utf-8"),
            str(path),
            "exec",
        )

    print(
        "[PASS] Rithmic setup verdict top-of-form integration: "
        "support/against/neutral/stale/low-sample/rollover guards, "
        "Phase5P scoring parity, top placement, and compile checks passed."
    )


if __name__ == "__main__":
    main()
