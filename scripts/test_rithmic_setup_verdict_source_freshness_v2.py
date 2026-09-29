from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import rithmic_setup_verdict as verdict_module

try:
    from src.market_participation_context import (
        refresh_rithmic_participation_context,
    )
except ModuleNotFoundError as exc:
    # Allows this focused test to run in the patch helper's minimal dry-run
    # repository. In the real bot repo src.logger exists and this branch is not
    # used.
    if exc.name != "src.logger":
        raise
    import types

    logger_module = types.ModuleType("src.logger")

    class _NullLogger:
        def __getattr__(self, _name):
            return lambda *args, **kwargs: None

    logger_module.logger = _NullLogger()
    sys.modules["src.logger"] = logger_module
    from src.market_participation_context import (
        refresh_rithmic_participation_context,
    )


class FakeRealShapeProvider:
    def get_latest_snapshot(self, requested_symbol: str) -> dict:
        return {
            "available": True,
            "status": "OBSERVE_ONLY_READY",
            "provider": "RITHMIC_SNAPSHOT_PROVIDER",
            "symbol": "GCZ6",
            "requested_symbol": requested_symbol,
            "exchange": "COMEX",
            "data_quality": "OBSERVE_ONLY_READY",
            # Intentionally mirrors the real adapter: no sample counts here.
            "metrics": {
                "bid_volume": 9,
                "ask_volume": 12,
                "delta": 3,
                "cumulative_delta": 3,
                "footprint_imbalance": 0.142857,
                "dom_bid_depth": 2495,
                "dom_ask_depth": 3178,
                "dom_depth_imbalance": -0.120395,
                "volume_profile_poc": 4171.1,
            },
            "rithmic_status": {
                "provider_status": "OBSERVE_ONLY_READY",
                "freshness": {
                    "snapshot_age_seconds": 0.2,
                    "snapshot_fresh": True,
                    "last_trade_age_seconds": 0.4,
                    "last_bbo_age_seconds": 0.1,
                    "last_order_book_age_seconds": 0.2,
                    "has_fresh_trade": True,
                    "has_fresh_bbo": True,
                    "has_fresh_order_book": True,
                },
                "sample": {
                    "last_trade_count_total_session": 21,
                    "rolling_trade_count": 21,
                    "bbo_count": 120,
                    "nonzero_bbo_count": 120,
                    "order_book_count": 1333,
                },
                "order_book": {
                    "available": True,
                    "bid_depth": 2495,
                    "ask_depth": 3178,
                    "depth_imbalance": -0.120395,
                    "top_bid_price": 4171.5,
                    "top_ask_price": 4171.8,
                },
            },
        }


def registration_payload() -> dict:
    return {
        "provider": "RITHMIC_R_PROTOCOL",
        "provider_role": "REAL_ORDER_FLOW_SOURCE",
        "source_market": "COMEX",
        "symbol": "GCZ6",
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


def evidence_families_payload() -> dict:
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
                "BUY",
                "synthetic_fresh_buy_aggression",
            ),
            "AUCTION_PROFILE": family(
                "BUY",
                "synthetic_fresh_buy_profile",
            ),
            "FOOTPRINT_ACCEPTANCE": family(
                "UNAVAILABLE",
                "independent_price_level_footprint_not_ready",
            ),
            "ABSORPTION_EXHAUSTION": family(
                "NEUTRAL",
                "no_absorption_event",
            ),
            "LIQUIDITY_DYNAMICS": family(
                "NEUTRAL",
                "stable_or_mixed_liquidity",
            ),
            "DIVERGENCE_TRAP": family(
                "NEUTRAL",
                "no_independent_trap_signal",
            ),
        },
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
    }


def main() -> None:
    rithmic = refresh_rithmic_participation_context(
        symbol="XAUUSD",
        provider=FakeRealShapeProvider(),
        min_refresh_interval_seconds=0,
    )

    metrics = rithmic["metrics"]
    assert metrics["trade_count"] == 21
    assert metrics["bbo_count"] == 120
    assert metrics["nonzero_bbo_count"] == 120
    assert metrics["order_book_count"] == 1333
    assert metrics["last_bid"] == 4171.5
    assert metrics["last_ask"] == 4171.8
    assert rithmic["freshness"]["has_fresh_trade"] is True
    assert rithmic["freshness"]["has_fresh_bbo"] is True
    assert rithmic["freshness"]["has_fresh_order_book"] is True

    original_registration_path = verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH
    original_evidence_loader = getattr(
        verdict_module,
        "_load_phase5g_evidence_families_v2",
        None,
    )

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            registration_path = Path(tmp_dir) / "phase5v.json"
            registration_path.write_text(
                json.dumps(registration_payload(), indent=2),
                encoding="utf-8",
            )
            verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = registration_path

            verdict_module._load_phase5g_evidence_families_v2 = (
                lambda symbol: (
                    evidence_families_payload(),
                    "ok",
                    0.2,
                )
            )

            context = {"rithmic": rithmic}
            fresh = verdict_module.build_rithmic_setup_verdict(context, "BUY")
            assert fresh["verdict"] == "SUPPORTS_SETUP"
            assert fresh["alignment"] == "SUPPORTS_BUY"
            assert fresh["trade_count"] == 21
            assert fresh["bbo_count"] == 120
            assert fresh["order_book_count"] == 1333
            assert fresh["source_age_seconds"] == 0.4
            assert fresh["decision_impact"] == "NONE"
            assert fresh["can_influence_decision"] is False
            assert fresh["safe_for_execution"] is False
            assert fresh["execution_allowed"] is False

            block = verdict_module.format_rithmic_setup_verdict_telegram_block(fresh)
            assert block.startswith("🟢 RITHMIC: SUPPORTS BUY")
            assert "Fresh 0.4s" in block
            assert "Trades 21" in block
            assert "OBSERVE ONLY" in block

            missing_trade = copy.deepcopy(context)
            missing_trade["rithmic"]["metrics"].pop("trade_count", None)
            result = verdict_module.build_rithmic_setup_verdict(
                missing_trade,
                "BUY",
            )
            assert result["verdict"] == "UNAVAILABLE"
            assert result["reason"] == "rithmic_trade_count_missing"

            low_sample = copy.deepcopy(context)
            low_sample["rithmic"]["metrics"]["trade_count"] = 2
            result = verdict_module.build_rithmic_setup_verdict(
                low_sample,
                "BUY",
            )
            assert result["verdict"] == "NEUTRAL"
            assert result["alignment"] == "NEUTRAL_LOW_RITHMIC_TRADE_SAMPLE"

            missing_freshness = copy.deepcopy(context)
            missing_freshness["rithmic"].pop("freshness", None)
            result = verdict_module.build_rithmic_setup_verdict(
                missing_freshness,
                "BUY",
            )
            assert result["verdict"] == "UNAVAILABLE"
            assert result["reason"] == "rithmic_source_not_fully_fresh"

            stale_trade = copy.deepcopy(context)
            stale_trade["rithmic"]["freshness"]["last_trade_age_seconds"] = 7.0
            result = verdict_module.build_rithmic_setup_verdict(
                stale_trade,
                "BUY",
            )
            assert result["verdict"] == "UNAVAILABLE"
            assert result["reason"] == "rithmic_source_stale"

            stale_flag = copy.deepcopy(context)
            stale_flag["rithmic"]["freshness"]["has_fresh_order_book"] = False
            result = verdict_module.build_rithmic_setup_verdict(
                stale_flag,
                "BUY",
            )
            assert result["verdict"] == "UNAVAILABLE"
            assert result["reason"] == "rithmic_source_not_fully_fresh"

            missing_bbo_count = copy.deepcopy(context)
            missing_bbo_count["rithmic"]["metrics"].pop("bbo_count", None)
            result = verdict_module.build_rithmic_setup_verdict(
                missing_bbo_count,
                "BUY",
            )
            assert result["verdict"] == "UNAVAILABLE"
            assert result["reason"] == "rithmic_market_structure_sample_missing"

            one_sided_dom = copy.deepcopy(context)
            one_sided_dom["rithmic"]["metrics"]["dom_ask_depth"] = 0
            result = verdict_module.build_rithmic_setup_verdict(
                one_sided_dom,
                "BUY",
            )
            assert result["verdict"] == "UNAVAILABLE"
            assert result["reason"] == "rithmic_two_sided_dom_missing"
    finally:
        verdict_module.RITHMIC_PROVIDER_REGISTRATION_PATH = original_registration_path

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

    for path in [
        ROOT / "src" / "market_participation_context.py",
        ROOT / "src" / "rithmic_setup_verdict.py",
    ]:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")

    print(
        "[PASS] Rithmic source-freshness hardening: real provider sample counts "
        "are flattened correctly; source freshness, missing counts, low sample, "
        "and two-sided DOM guards fail safe with decision_impact NONE."
    )


if __name__ == "__main__":
    main()
