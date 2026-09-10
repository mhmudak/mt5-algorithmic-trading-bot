from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "validate_phase5k_rithmic_open_market_data.py"


def load_target():
    spec = importlib.util.spec_from_file_location(
        "phase5k_current_contract_target",
        TARGET,
    )

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    module = load_target()
    source = TARGET.read_text(encoding="utf-8-sig")

    assert module.parse_symbols("") == []

    assert "GCQ6" not in source
    assert "MGCQ6" not in source

    assert (
        'parser.add_argument("--symbols", default=None)'
        in source
    )

    assert "_require_rithmic_symbols(" in source

    assert (
        module.freshness_with_threshold(
            {
                "has_fresh_trade": False,
                "last_trade_age_seconds": 5.0,
            },
            flag_key="has_fresh_trade",
            age_key="last_trade_age_seconds",
            stale_after_seconds=10,
        )
        is True
    )

    assert (
        module.freshness_with_threshold(
            {
                "has_fresh_trade": True,
                "last_trade_age_seconds": 11.0,
            },
            flag_key="has_fresh_trade",
            age_key="last_trade_age_seconds",
            stale_after_seconds=10,
        )
        is False
    )

    assert (
        module.freshness_with_threshold(
            {
                "has_fresh_trade": True,
            },
            flag_key="has_fresh_trade",
            age_key="last_trade_age_seconds",
            stale_after_seconds=10,
        )
        is True
    )

    assert '    elif not report["all_dom_quality_ok"]:\n        report["overall_status"] = "TRADE_FLOW_VALIDATED_DOM_NOT_READY"\n        report["recommendation"] = "Trade flow is usable for observe-only research, but DOM depth is not validated."\n    else:\n        report["overall_status"] = "OPEN_MARKET_RITHMIC_VALIDATED_OBSERVE_ONLY"\n        report["recommendation"] = "Rithmic open-market data is validated for observe-only research. Keep decision impact disabled."\n' in source

    assert '    dom_quality_checks = [\n        "order_book_observed",\n        "dom_available",\n        "has_fresh_order_book",\n    ]\n' in source

    assert '"decision_impact": "NONE"' in source
    assert '"can_influence_decision": False' in source
    assert '"safe_for_execution": False' in source

    print(
        "[PASS] Phase 5K uses explicit/current contracts, "
        "honors its freshness threshold for trade/BBO/DOM, "
        "requires fresh DOM, retains correct status routing, "
        "and remains observe-only."
    )


if __name__ == "__main__":
    main()
