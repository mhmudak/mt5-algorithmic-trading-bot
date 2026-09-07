from __future__ import annotations

import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from src.order_flow_adapter import (
    RithmicSnapshotOrderFlowProvider,
    evaluate_order_flow_availability,
)
from src.order_flow_providers.rithmic_protocol import (
    RithmicConfig,
    RithmicMarketDataClient,
)


ADAPTER = (
    ROOT
    / "src"
    / "order_flow_adapter.py"
)

PROTOCOL = (
    ROOT
    / "src"
    / "order_flow_providers"
    / "rithmic_protocol.py"
)


def test_no_implicit_gcq6_contract_fallback():
    adapter_text = ADAPTER.read_text(
        encoding="utf-8-sig"
    )

    protocol_text = PROTOCOL.read_text(
        encoding="utf-8-sig"
    )

    assert "GCQ6" not in adapter_text
    assert "GCQ6" not in protocol_text


def test_snapshot_provider_is_unavailable_without_explicit_symbol():
    with tempfile.TemporaryDirectory() as tmp:
        provider = (
            RithmicSnapshotOrderFlowProvider(
                snapshot_path=(
                    Path(tmp)
                    / "missing.json"
                ),
                rithmic_symbol="",
            )
        )

        assert (
            provider.rithmic_symbol
            == ""
        )

        assert (
            provider.is_available()
            is False
        )

        snapshot = (
            provider.get_latest_snapshot(
                "XAUUSD"
            )
        )

    assert (
        snapshot["available"]
        is False
    )

    assert (
        snapshot["status"]
        == "RITHMIC_SYMBOL_NOT_CONFIGURED"
    )

    assert (
        snapshot["symbol"]
        is None
    )

    assert (
        snapshot[
            "can_influence_decision"
        ]
        is False
    )

    assert (
        snapshot[
            "safe_for_execution"
        ]
        is False
    )

    assert snapshot["metrics"]

    assert all(
        value is None
        for value
        in snapshot[
            "metrics"
        ].values()
    )

    gate = (
        evaluate_order_flow_availability(
            snapshot
        )
    )

    assert (
        gate[
            "can_influence_decision"
        ]
        is False
    )

    assert (
        gate[
            "decision_impact"
        ]
        == "NONE"
    )


def test_explicit_test_symbol_is_preserved():
    with tempfile.TemporaryDirectory() as tmp:
        provider = (
            RithmicSnapshotOrderFlowProvider(
                snapshot_path=(
                    Path(tmp)
                    / "missing.json"
                ),
                rithmic_symbol="GC_TEST",
            )
        )

        assert (
            provider.rithmic_symbol
            == "GC_TEST"
        )


def test_protocol_refuses_missing_symbol_before_sdk_or_network_work():
    config = RithmicConfig(
        ws_url=(
            "wss://example.invalid"
        ),
        system_name="Rithmic Test",
        username="",
        password="",
        exchange="COMEX",
        symbol="",
        sdk_path=(
            "definitely_missing_sdk_path"
        ),
    )

    try:
        RithmicMarketDataClient(
            config
        )

    except ValueError as exc:
        assert (
            "RITHMIC_SYMBOL"
            in str(exc)
        )

    else:
        raise AssertionError(
            "Rithmic client accepted "
            "a missing contract symbol"
        )


if __name__ == "__main__":
    test_no_implicit_gcq6_contract_fallback()
    test_snapshot_provider_is_unavailable_without_explicit_symbol()
    test_explicit_test_symbol_is_preserved()
    test_protocol_refuses_missing_symbol_before_sdk_or_network_work()

    print(
        "[PASS] Rithmic explicit-symbol "
        "guard regression passed."
    )
