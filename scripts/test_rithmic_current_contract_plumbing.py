from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from src.order_flow_providers.rithmic_contract_identity import (
    require_rithmic_symbol,
    require_rithmic_symbols,
    resolve_rithmic_symbol,
    resolve_rithmic_symbols,
    safe_symbol_for_file,
)


OPERATIONAL_FILES = (
    "scripts/build_phase3_dashboard_summary.py",
    "scripts/build_phase4_orderflow_status.py",
    "scripts/build_phase5b_rithmic_orderflow_summary.py",
    "scripts/build_phase5f_rithmic_provider_status.py",
    "scripts/build_phase5g_rithmic_monitoring_bridge.py",
    "scripts/check_phase5af_rithmic_dom_bbo_consistency.py",
    "scripts/check_phase5l_rithmic_data_quality_gate.py",
    "scripts/run_phase5j_rithmic_manual_refresh_pipeline.py",
    "scripts/run_phase5o_rithmic_setup_filter_watcher.py",
    "scripts/run_phase5p_event_driven_rithmic_watcher.py",
    "scripts/run_phase5u_rithmic_real_orderflow_acceptance.py",
    "scripts/notify_phase4_unified_monitoring_telegram.py",
    "scripts/notify_phase5n_setup_gated_rithmic_filter.py",
    "scripts/register_phase5v_rithmic_observe_only_provider.py",
    "scripts/build_phase5x_rithmic_professional_orderflow_features.py",
    "scripts/build_phase5ad_rithmic_production_subscription_checkpoint.py",
    "scripts/build_phase5ae_rithmic_production_onboarding_runbook.py",
    "scripts/validate_phase5k_rithmic_open_market_data.py",
)


def load_module(
    name: str,
    relative: str,
):
    path = ROOT / relative

    spec = (
        importlib.util.spec_from_file_location(
            name,
            path,
        )
    )

    assert spec is not None
    assert spec.loader is not None

    module = (
        importlib.util.module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        module
    )

    return module


def test_contract_resolver():
    with patch.dict(
        os.environ,
        {
            "RITHMIC_SYMBOL": "gcz6",
        },
        clear=False,
    ):
        assert (
            resolve_rithmic_symbol(
                None,
                root=None,
            )
            == "GCZ6"
        )

        assert (
            resolve_rithmic_symbol(
                "mgcz6",
                root=None,
            )
            == "MGCZ6"
        )

        assert (
            require_rithmic_symbol(
                "GCJ7",
                root=None,
            )
            == "GCJ7"
        )

        assert (
            resolve_rithmic_symbols(
                None,
                root=None,
            )
            == ["GCZ6"]
        )

        assert (
            resolve_rithmic_symbols(
                "GCZ6,MGCZ6,GCZ6",
                root=None,
            )
            == [
                "GCZ6",
                "MGCZ6",
            ]
        )

        assert (
            require_rithmic_symbols(
                "MGCJ7;GCJ7",
                root=None,
            )
            == [
                "MGCJ7",
                "GCJ7",
            ]
        )

    with patch.dict(
        os.environ,
        {},
        clear=True,
    ):
        assert (
            resolve_rithmic_symbol(
                None,
                root=None,
            )
            is None
        )

        try:
            require_rithmic_symbol(
                None,
                root=None,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "missing contract must fail"
            )

        try:
            require_rithmic_symbols(
                None,
                root=None,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "missing symbols must fail"
            )

    assert (
        safe_symbol_for_file(
            "GC/Z6"
        )
        == "GC_Z6"
    )


def test_no_dated_operational_authority():
    pattern = re.compile(
        r"\b(?:GC|MGC)[A-Z][0-9]\b"
    )

    offenders = []

    for relative in OPERATIONAL_FILES:
        source = (
            ROOT
            / relative
        ).read_text(
            encoding="utf-8-sig"
        )

        if pattern.search(
            source
        ):
            offenders.append(
                relative
            )

    assert not offenders, (
        "dated current-contract references remain: "
        + ", ".join(offenders)
    )


def test_historical_matrix_is_not_production_command():
    runbook_source = (
        ROOT
        / "scripts"
        / "build_phase5ae_rithmic_production_onboarding_runbook.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    checkpoint_source = (
        ROOT
        / "scripts"
        / "build_phase5ad_rithmic_production_subscription_checkpoint.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "build_phase5aa_"
        not in runbook_source
    )

    assert (
        "SYMBOL_MATRIX_PATH"
        not in checkpoint_source
    )


def test_neutral_readers_without_symbol():
    targets = (
        (
            "phase3_contract_reader",
            "scripts/build_phase3_dashboard_summary.py",
            "configured_rithmic_symbol",
            "load_rithmic_bridge",
        ),
        (
            "phase4_contract_reader",
            "scripts/build_phase4_orderflow_status.py",
            "_configured_rithmic_symbol",
            "_load_rithmic_bridge",
        ),
    )

    for (
        name,
        relative,
        resolver_name,
        loader_name,
    ) in targets:
        module = load_module(
            name,
            relative,
        )

        setattr(
            module,
            "_resolve_rithmic_symbol",
            lambda *args, **kwargs: None,
        )

        result = getattr(
            module,
            loader_name,
        )()

        assert (
            result["loaded"]
            is False
        )

        assert (
            result["bridge_status"]
            == "RITHMIC_SYMBOL_NOT_CONFIGURED"
        )

        assert (
            result["decision_impact"]
            == "NONE"
        )

        assert (
            result["can_influence_decision"]
            is False
        )


def test_phase5n_missing_symbol_is_neutral():
    module = load_module(
        "phase5n_contract_reader",
        "scripts/notify_phase5n_setup_gated_rithmic_filter.py",
    )

    module._resolve_rithmic_symbol = (
        lambda *args, **kwargs: None
    )

    result = (
        module.load_rithmic_quality()
    )

    assert (
        result["overall_status"]
        == "RITHMIC_SYMBOL_NOT_CONFIGURED"
    )

    assert (
        result["decision_impact"]
        == "NONE"
    )

    assert (
        result["can_influence_decision"]
        is False
    )


def test_phase5ad_current_symbol_match():
    module = load_module(
        "phase5ad_contract_checkpoint",
        "scripts/build_phase5ad_rithmic_production_subscription_checkpoint.py",
    )

    analysis = {
        "symbol": "GCZ6",
        "quality": {
            "sample_count": 60,
            "positive_bbo_rate": 0.99,
            "two_sided_dom_rate": 0.99,
            "max_spread": 0.5,
            "max_rolling_trade_count": 2,
        },
        "decision_readiness": {
            "passed": [
                "dom_dynamics_available",
            ],
            "automation_allowed": False,
        },
    }

    basis = {
        "rithmic_symbol": "GCZ6",
        "summary": {
            "basis_ready_observe_only": True,
            "valid_pair_rate": 0.95,
            "basis_std": 0.5,
        },
    }

    result = (
        module.classify_checkpoint(
            symbol="GCZ6",
            analysis=analysis,
            basis=basis,
        )
    )

    assert (
        result[
            "production_subscription_recommended"
        ]
        is True
    )

    mismatch = (
        module.classify_checkpoint(
            symbol="GCG7",
            analysis=analysis,
            basis=basis,
        )
    )

    assert (
        mismatch[
            "production_subscription_recommended"
        ]
        is False
    )

    assert (
        mismatch["checks"][
            "analysis_symbol_matches"
        ]
        is False
    )


def test_phase5v_and_5x_current_identity():
    phase5v = (
        ROOT
        / "scripts"
        / "register_phase5v_rithmic_observe_only_provider.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    phase5x = (
        ROOT
        / "scripts"
        / "build_phase5x_rithmic_professional_orderflow_features.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert (
        "PHASE5C_LATEST"
        not in phase5v
    )

    assert (
        "STATE_PATH = "
        not in phase5x
    )

    assert (
        'registration.get('
        in phase5x
    )

    assert (
        '"symbol"'
        in phase5x
    )


def main():
    test_contract_resolver()
    test_no_dated_operational_authority()
    test_historical_matrix_is_not_production_command()
    test_neutral_readers_without_symbol()
    test_phase5n_missing_symbol_is_neutral()
    test_phase5ad_current_symbol_match()
    test_phase5v_and_5x_current_identity()

    print(
        "[PASS] Rithmic current-contract plumbing "
        "has no dated operational authority: "
        "CLI/configured contracts drive current "
        "file selection and subprocesses; missing "
        "reader configuration remains neutral; "
        "historical symbol comparison is no longer "
        "a production-validation dependency."
    )


if __name__ == "__main__":
    main()
