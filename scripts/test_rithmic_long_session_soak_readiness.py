from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PHASE5Y_PATH = (
    ROOT
    / "scripts"
    / "run_phase5y_rithmic_long_session_history.py"
)

PHASE5Z_PATH = (
    ROOT
    / "scripts"
    / "analyze_phase5z_rithmic_long_session_orderflow.py"
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(
        spec
    )

    spec.loader.exec_module(module)

    return module


phase5y = load_module(
    "phase5y_soak_test_target",
    PHASE5Y_PATH,
)

phase5z = load_module(
    "phase5z_soak_test_target",
    PHASE5Z_PATH,
)


def sample_record():
    return {
        "metrics": {
            "bid": 4424.9,
            "ask": 4425.1,
            "spread": 0.2,
            "rolling_trade_count": 25,
            "bid_depth": 100,
            "ask_depth": 90,
        }
    }


def test_no_dated_default_contracts():
    source_y = PHASE5Y_PATH.read_text(
        encoding="utf-8-sig"
    )

    source_z = PHASE5Z_PATH.read_text(
        encoding="utf-8-sig"
    )

    assert (
        'default="MGCQ6"'
        not in source_y
    )

    assert (
        'default="GCQ6"'
        not in source_y
    )

    assert (
        'default="MGCQ6"'
        not in source_z
    )

    assert (
        'default="GCQ6"'
        not in source_z
    )

    assert "GCQ6 validation" not in source_z

    assert phase5y.resolve_symbols(
        "gcx6, mgcx6",
        None,
    ) == [
        "GCX6",
        "MGCX6",
    ]

    assert phase5y.resolve_symbols(
        None,
        "GCZ6",
    ) == [
        "GCZ6",
    ]

    try:
        phase5y.resolve_symbols(
            None,
            "",
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "missing contract must fail"
        )


def test_live_summary_memory_is_bounded():
    accumulator = (
        phase5y.SessionSummaryAccumulator()
    )

    record = sample_record()

    for _ in range(5000):
        accumulator.add_record(record)

    summary = accumulator.summary()

    assert summary["sample_count"] == 5000
    assert summary["positive_bbo_rate"] == 1.0
    assert summary["two_sided_dom_rate"] == 1.0
    assert summary["max_spread"] == 0.2
    assert summary["quality_ready"] is True

    # The running accumulator must not retain a list of
    # historical observations.
    assert not any(
        isinstance(value, list)
        for value
        in accumulator.__dict__.values()
    )


def test_append_jsonl_and_atomic_status_write():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        jsonl = root / "session.jsonl"
        status = root / "latest.json"

        phase5y.append_jsonl(
            jsonl,
            {"value": 1},
        )

        phase5y.append_jsonl(
            jsonl,
            {"value": 2},
        )

        rows = [
            json.loads(line)
            for line
            in jsonl.read_text(
                encoding="utf-8"
            ).splitlines()
        ]

        assert rows == [
            {"value": 1},
            {"value": 2},
        ]

        phase5y.write_json(
            status,
            {
                "session_status": "RUNNING",
                "sample_count": 2,
            },
        )

        loaded = json.loads(
            status.read_text(
                encoding="utf-8"
            )
        )

        assert (
            loaded["session_status"]
            == "RUNNING"
        )

        assert not (
            status.parent
            / f".{status.name}.tmp"
        ).exists()


def test_connection_recovery_has_separate_channel():
    event = {
        "event_type": "connection_recovery",
        "status": "DISCONNECTED",
        "attempt": 0,
        "max_attempts": 3,
        "error_type": (
            "ConnectionResetError"
        ),
        "received_at_epoch": 1234.5,

        # These deliberately misleading fields must not
        # cross into the connection diagnostic record.
        "trade_price": 9999.0,
        "trade_size": 999,
        "aggressor": "SELL",
        "bid_price": 9998.0,
        "ask_price": 10000.0,
    }

    record = (
        phase5y.build_connection_diagnostic_record(
            event,
            symbol="GC_TEST",
            exchange="COMEX",
        )
    )

    assert (
        record["record_kind"]
        == "CONNECTION_RECOVERY"
    )

    assert record["status"] == "DISCONNECTED"

    assert (
        record["decision_impact"]
        == "NONE"
    )

    assert (
        record["can_influence_decision"]
        is False
    )

    assert (
        record["safe_for_execution"]
        is False
    )

    for forbidden in (
        "trade_price",
        "trade_size",
        "aggressor",
        "bid_price",
        "ask_price",
    ):
        assert forbidden not in record

    with tempfile.TemporaryDirectory() as tmp:
        path = (
            Path(tmp)
            / "diagnostics.jsonl"
        )

        persisted = (
            phase5y.persist_connection_recovery_event(
                path,
                event,
                symbol="GC_TEST",
                exchange="COMEX",
            )
        )

        assert persisted is not None

        lines = path.read_text(
            encoding="utf-8"
        ).splitlines()

        assert len(lines) == 1

        saved = json.loads(lines[0])

        assert (
            saved["record_kind"]
            == "CONNECTION_RECOVERY"
        )

        ignored = (
            phase5y.persist_connection_recovery_event(
                path,
                {
                    "event_type": "last_trade"
                },
                symbol="GC_TEST",
                exchange="COMEX",
            )
        )

        assert ignored is None

        assert len(
            path.read_text(
                encoding="utf-8"
            ).splitlines()
        ) == 1


def test_analyzer_tolerates_partial_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "history.jsonl"

        path.write_text(
            '{"ok": 1}\n'
            '{"ok": 2}\n'
            '{"truncated":',
            encoding="utf-8",
        )

        rows = phase5z.load_jsonl(path)

        assert rows == [
            {"ok": 1},
            {"ok": 2},
        ]


def test_source_level_soak_guards():
    source_y = PHASE5Y_PATH.read_text(
        encoding="utf-8-sig"
    )

    collect_start = source_y.index(
        "async def collect_symbol("
    )

    collect_end = source_y.index(
        "async def main_async(",
        collect_start,
    )

    collect_source = source_y[
        collect_start:collect_end
    ]

    assert "records.append(" not in collect_source
    assert "records: list[" not in collect_source

    diagnostic_call = (
        collect_source.index(
            "persist_connection_recovery_event("
        )
    )

    timed_snapshot = (
        collect_source.index(
            "now >= next_snapshot_at"
        )
    )

    # Recovery persistence is evaluated for every event
    # before scheduled snapshot persistence.
    assert diagnostic_call < timed_snapshot

    source_z = PHASE5Z_PATH.read_text(
        encoding="utf-8-sig"
    )

    load_start = source_z.index(
        "def load_jsonl("
    )

    load_end = source_z.index(
        "def normalize_levels(",
        load_start,
    )

    load_source = source_z[
        load_start:load_end
    ]

    assert ".read_text(" not in load_source
    assert "with path.open(" in load_source


def main():
    test_no_dated_default_contracts()
    test_live_summary_memory_is_bounded()
    test_append_jsonl_and_atomic_status_write()
    test_connection_recovery_has_separate_channel()
    test_analyzer_tolerates_partial_jsonl()
    test_source_level_soak_guards()

    print(
        "[PASS] Rithmic long-session soak readiness: "
        "explicit active contracts, bounded live memory, "
        "durable snapshots, independent reconnect "
        "diagnostics, atomic progress status, and "
        "partial-JSONL analysis."
    )


if __name__ == "__main__":
    main()
