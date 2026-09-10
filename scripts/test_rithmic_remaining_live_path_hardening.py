from __future__ import annotations

import asyncio
import importlib.util
import json
import math
import statistics
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PHASE5AC_PATH = (
    ROOT
    / "scripts"
    / "run_phase5ac_xauusd_rithmic_basis_calibration.py"
)

PHASE5AG_PATH = (
    ROOT
    / "scripts"
    / "run_phase5ag_rithmic_conformance_order_plant_login.py"
)


def load_module(name, path):
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


phase5ac = load_module(
    "phase5ac_live_path_test_target",
    PHASE5AC_PATH,
)

phase5ag = load_module(
    "phase5ag_live_path_test_target",
    PHASE5AG_PATH,
)


def test_contract_resolution():
    assert (
        phase5ac.resolve_rithmic_symbol(
            "GCZ6",
            "STALE_TEST",
        )
        == "GCZ6"
    )

    assert (
        phase5ac.resolve_rithmic_symbol(
            None,
            "GCG7",
        )
        == "GCG7"
    )

    assert (
        phase5ag.resolve_rithmic_symbol(
            "MGCZ6",
            "STALE_TEST",
        )
        == "MGCZ6"
    )

    assert (
        phase5ag.resolve_rithmic_symbol(
            None,
            "MGCJ7",
        )
        == "MGCJ7"
    )

    for resolver in (
        phase5ac.resolve_rithmic_symbol,
        phase5ag.resolve_rithmic_symbol,
    ):
        try:
            resolver(
                None,
                "",
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "missing active contract "
                "must fail"
            )


def test_no_live_dated_defaults():
    ac_source = (
        PHASE5AC_PATH.read_text(
            encoding="utf-8-sig"
        )
    )

    ag_source = (
        PHASE5AG_PATH.read_text(
            encoding="utf-8-sig"
        )
    )

    for source in (
        ac_source,
        ag_source,
    ):
        assert (
            'default="MGCQ6"'
            not in source
        )

        assert (
            'default="GCQ6"'
            not in source
        )

    assert (
        "phase5ac_xauusd_mgcq6_"
        "basis_history"
        not in ac_source.lower()
    )

    assert (
        "Rithmic_MGCQ6_mid"
        not in ac_source
    )

    assert (
        "XAUUSD vs MGCQ6"
        not in ac_source
    )


def test_mt5_selection_failure_cleans_up():
    original_mt5 = phase5ac.mt5

    class FakeMT5:
        def __init__(self):
            self.shutdown_calls = 0

        def initialize(self):
            return True

        def symbol_select(
            self,
            symbol,
            enabled,
        ):
            assert symbol == "XAUUSD"
            assert enabled is True
            return False

        def last_error(self):
            return (
                123,
                "test failure",
            )

        def shutdown(self):
            self.shutdown_calls += 1

    fake = FakeMT5()

    try:
        phase5ac.mt5 = fake

        result = phase5ac.initialize_mt5(
            "XAUUSD"
        )

        assert result["ok"] is False
        assert fake.shutdown_calls == 1

    finally:
        phase5ac.mt5 = original_mt5


def test_session_status_classification():
    assert (
        phase5ac.classify_session_status(
            {
                "connection": {
                    "login_ok": True,
                }
            },
            None,
        )
        == "COMPLETED"
    )

    assert (
        phase5ac.classify_session_status(
            {
                "connection": {
                    "login_ok": False,
                }
            },
            None,
        )
        == "LOGIN_NOT_OK"
    )

    assert (
        phase5ac.classify_session_status(
            {
                "connection": {
                    "login_ok": True,
                }
            },
            "RECONNECT_EXHAUSTED",
        )
        == "RECOVERY_EXHAUSTED"
    )


def test_basis_trigger_guard():
    for event_type in (
        "last_trade",
        "best_bid_offer",
        "order_book",
    ):
        assert (
            phase5ac.should_sample_basis_event(
                {
                    "event_type": (
                        event_type
                    )
                }
            )
            is True
        )

    for event_type in (
        "connection_recovery",
        "login_response",
        "market_data_response",
        "heartbeat_response",
        "unhandled",
    ):
        assert (
            phase5ac.should_sample_basis_event(
                {
                    "event_type": (
                        event_type
                    )
                }
            )
            is False
        )


def test_basis_accumulator_matches_legacy_math():
    records = [
        {
            "basis_valid": True,
            "basis": 1.25,
        },
        {
            "basis_valid": False,
            "basis": None,
        },
        {
            "basis_valid": True,
            "basis": -0.50,
        },
        {
            "basis_valid": True,
            "basis": 2.00,
        },
        {
            "basis_valid": True,
            "basis": 1.00,
        },
    ]

    accumulator = (
        phase5ac.BasisSummaryAccumulator()
    )

    for record in records:
        accumulator.add_record(
            record
        )

    summary = (
        accumulator.summary()
    )

    values = [
        1.25,
        -0.50,
        2.00,
        1.00,
    ]

    jumps = [
        abs(cur - prev)
        for prev, cur
        in zip(
            values,
            values[1:],
        )
    ]

    assert (
        summary["sample_count"]
        == len(records)
    )

    assert (
        summary["valid_pair_count"]
        == len(values)
    )

    assert (
        summary["valid_pair_rate"]
        == round(
            len(values)
            / len(records),
            4,
        )
    )

    assert math.isclose(
        summary["avg_basis"],
        round(
            sum(values)
            / len(values),
            6,
        ),
        abs_tol=1e-9,
    )

    assert (
        summary["min_basis"]
        == min(values)
    )

    assert (
        summary["max_basis"]
        == max(values)
    )

    assert math.isclose(
        summary["avg_abs_basis"],
        round(
            sum(
                abs(value)
                for value in values
            )
            / len(values),
            6,
        ),
        abs_tol=1e-9,
    )

    assert math.isclose(
        summary["basis_std"],
        round(
            statistics.pstdev(
                values
            ),
            6,
        ),
        abs_tol=1e-9,
    )

    assert (
        summary[
            "max_abs_basis_jump"
        ]
        == round(
            max(jumps),
            6,
        )
    )

    # Live accumulator itself must remain constant-memory.
    assert not any(
        isinstance(value, list)
        for value
        in accumulator.__dict__.values()
    )


def test_basis_accumulator_long_soak():
    accumulator = (
        phase5ac.BasisSummaryAccumulator()
    )

    for index in range(10000):
        accumulator.add_record(
            {
                "basis_valid": True,
                "basis": (
                    10.0
                    + (
                        (index % 7)
                        * 0.1
                    )
                ),
            }
        )

    summary = (
        accumulator.summary()
    )

    assert (
        summary["sample_count"]
        == 10000
    )

    assert (
        summary["valid_pair_count"]
        == 10000
    )

    assert not any(
        isinstance(value, list)
        for value
        in accumulator.__dict__.values()
    )


def test_durable_jsonl_and_atomic_report():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        history = (
            root
            / "basis.jsonl"
        )

        report = (
            root
            / "latest.json"
        )

        phase5ac.append_jsonl(
            history,
            {
                "basis": 1.0,
            },
        )

        phase5ac.append_jsonl(
            history,
            {
                "basis": 2.0,
            },
        )

        rows = [
            json.loads(line)
            for line
            in history.read_text(
                encoding="utf-8"
            ).splitlines()
        ]

        assert rows == [
            {"basis": 1.0},
            {"basis": 2.0},
        ]

        phase5ac.write_json(
            report,
            {
                "session_status": (
                    "RUNNING"
                )
            },
        )

        loaded = json.loads(
            report.read_text(
                encoding="utf-8"
            )
        )

        assert (
            loaded["session_status"]
            == "RUNNING"
        )

        temporary = (
            report.parent
            / f".{report.name}.tmp"
        )

        assert not temporary.exists()


class FakeWebSocket:
    def __init__(self):
        self.close_calls = []

    async def close(
        self,
        code,
        reason,
    ):
        self.close_calls.append(
            (
                code,
                reason,
            )
        )


class FakeClient:
    def __init__(self):
        self.ws = FakeWebSocket()


def test_phase5ag_transport_cleanup():
    client = FakeClient()
    ws = client.ws

    asyncio.run(
        phase5ag.close_transport_quietly(
            client
        )
    )

    assert client.ws is None

    assert ws.close_calls == [
        (
            1000,
            "phase5ag conformance done",
        )
    ]


def test_source_level_live_guards():
    ac_source = (
        PHASE5AC_PATH.read_text(
            encoding="utf-8-sig"
        )
    )

    main_start = ac_source.index(
        "async def main_async("
    )

    main_end = ac_source.index(
        "def main() -> None:",
        main_start,
    )

    main_source = ac_source[
        main_start:main_end
    ]

    assert (
        "records.append("
        not in main_source
    )

    assert (
        "records: list["
        not in main_source
    )

    assert (
        "should_sample_basis_event("
        in main_source
    )

    recovery_index = (
        main_source.index(
            '== "connection_recovery"'
        )
    )

    sample_guard_index = (
        main_source.index(
            "should_sample_basis_event("
        )
    )

    assert (
        recovery_index
        < sample_guard_index
    )

    ag_source = (
        PHASE5AG_PATH.read_text(
            encoding="utf-8-sig"
        )
    )

    assert (
        "finally:"
        in ag_source
    )

    assert (
        "close_transport_quietly("
        in ag_source
    )


def main():
    test_contract_resolution()
    test_no_live_dated_defaults()
    test_mt5_selection_failure_cleans_up()
    test_session_status_classification()
    test_basis_trigger_guard()
    test_basis_accumulator_matches_legacy_math()
    test_basis_accumulator_long_soak()
    test_durable_jsonl_and_atomic_report()
    test_phase5ag_transport_cleanup()
    test_source_level_live_guards()

    print(
        "[PASS] Remaining Rithmic live paths use "
        "explicit/current contracts; Phase 5AC has "
        "bounded basis statistics, durable capture and "
        "cannot sample on recovery telemetry; Phase 5AG "
        "closes its conformance websocket without orders."
    )


if __name__ == "__main__":
    main()
