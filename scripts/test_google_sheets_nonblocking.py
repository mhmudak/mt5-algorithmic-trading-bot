from __future__ import annotations

import ast
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


import src.google_sheets_logger as gs


class _FakeResponse:
    status_code = 200
    text = "OK"

    @staticmethod
    def json():
        return {"ok": True}


def _assert_fast(
    elapsed,
    label,
    threshold=0.10,
):
    assert elapsed < threshold, (
        f"{label} blocked caller for "
        f"{elapsed:.4f}s"
    )


def test_worker_is_prestarted():
    assert (
        gs.ENABLE_GOOGLE_SHEETS_LOGGING
        is True
    )

    assert (
        gs.GOOGLE_SHEETS_ASYNC_NONBLOCKING
        is True
    )

    worker = (
        gs._GOOGLE_SHEETS_WORKER_THREAD
    )

    assert worker is not None, (
        "Google worker was not created "
        "during module/bootstrap time"
    )

    assert worker.is_alive(), (
        "Google worker is not alive"
    )


def test_slow_google_does_not_block_producer():
    original_enabled = (
        gs.ENABLE_GOOGLE_SHEETS_LOGGING
    )

    original_url = (
        gs.GOOGLE_SHEETS_WEBHOOK_URL
    )

    original_post = gs.requests.post

    started = threading.Event()
    finished = threading.Event()

    def slow_post(*args, **kwargs):
        started.set()

        time.sleep(1.0)

        finished.set()

        return _FakeResponse()

    try:
        gs.ENABLE_GOOGLE_SHEETS_LOGGING = (
            True
        )

        gs.GOOGLE_SHEETS_WEBHOOK_URL = (
            "https://example.invalid/test"
        )

        gs.requests.post = slow_post

        started_at = time.perf_counter()

        accepted = (
            gs.send_setup_event_to_google_sheets(
                {
                    "setup_id": "ASYNC-TEST-1",
                    "event": "EXECUTED",
                    "strategy": "TEST",
                    "signal": "BUY",
                }
            )
        )

        elapsed = (
            time.perf_counter()
            - started_at
        )

        assert accepted is True

        _assert_fast(
            elapsed,
            "setup-event enqueue",
        )

        assert started.wait(1.0), (
            "background HTTP did not start"
        )

        assert finished.wait(2.0), (
            "background HTTP did not finish"
        )

        assert (
            gs
            ._wait_for_google_sheets_worker_idle_for_test(
                timeout_seconds=2.0,
            )
        )

    finally:
        gs.requests.post = original_post

        gs.ENABLE_GOOGLE_SHEETS_LOGGING = (
            original_enabled
        )

        gs.GOOGLE_SHEETS_WEBHOOK_URL = (
            original_url
        )


def test_retry_flush_is_nonblocking():
    original_enabled = (
        gs.ENABLE_GOOGLE_SHEETS_LOGGING
    )

    original_flush = (
        gs
        ._flush_google_sheets_retry_queue_sync
    )

    original_last = (
        gs
        ._GOOGLE_SHEETS_LAST_RETRY_REQUEST
    )

    started = threading.Event()
    finished = threading.Event()

    def slow_flush(max_items=5):
        started.set()

        time.sleep(1.0)

        finished.set()

        return 0

    try:
        gs.ENABLE_GOOGLE_SHEETS_LOGGING = (
            True
        )

        gs._flush_google_sheets_retry_queue_sync = (
            slow_flush
        )

        gs._GOOGLE_SHEETS_LAST_RETRY_REQUEST = (
            0.0
        )

        started_at = time.perf_counter()

        result = (
            gs.flush_google_sheets_retry_queue(
                max_items=5
            )
        )

        elapsed = (
            time.perf_counter()
            - started_at
        )

        assert result == 0

        _assert_fast(
            elapsed,
            "retry-flush scheduling",
        )

        assert started.wait(1.0), (
            "background retry flush "
            "did not start"
        )

        assert finished.wait(2.0), (
            "background retry flush "
            "did not finish"
        )

        assert (
            gs
            ._wait_for_google_sheets_worker_idle_for_test(
                timeout_seconds=2.0,
            )
        )

    finally:
        (
            gs
            ._flush_google_sheets_retry_queue_sync
        ) = original_flush

        (
            gs
            ._GOOGLE_SHEETS_LAST_RETRY_REQUEST
        ) = original_last

        gs.ENABLE_GOOGLE_SHEETS_LOGGING = (
            original_enabled
        )


def test_http_is_worker_only():
    path = (
        ROOT
        / "src"
        / "google_sheets_logger.py"
    )

    source = path.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(source)

    request_post_functions = []

    for node in tree.body:
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            continue

        segment = ast.get_source_segment(
            source,
            node,
        ) or ""

        if "requests.post(" in segment:
            request_post_functions.append(
                node.name
            )

    assert request_post_functions == [
        "_post_google_sheets_payload_sync"
    ], request_post_functions

    for function_name in (
        "post_google_sheets_payload",
        "send_setup_event_to_google_sheets",
        "send_setup_outcome_to_google_sheets",
        (
            "send_memory_decision_report_"
            "to_google_sheets"
        ),
        "flush_google_sheets_retry_queue",
    ):
        node = next(
            item
            for item in tree.body
            if isinstance(
                item,
                ast.FunctionDef,
            )
            and item.name
            == function_name
        )

        segment = ast.get_source_segment(
            source,
            node,
        ) or ""

        assert "requests.post(" not in segment
        assert "time.sleep(" not in segment


def test_google_calls_are_telemetry_only():
    public_calls = {
        "send_setup_event_to_google_sheets",
        "send_setup_outcome_to_google_sheets",
        (
            "send_memory_decision_report_"
            "to_google_sheets"
        ),
        "flush_google_sheets_retry_queue",
    }

    violations = []

    for path in (
        ROOT / "src"
    ).rglob("*.py"):
        # utf-8-sig is UTF-8 compatible and strips an
        # optional BOM before ast.parse(). Some existing
        # project modules legitimately contain a UTF-8 BOM.
        module_source = path.read_text(
            encoding="utf-8-sig"
        )

        tree = ast.parse(
            module_source,
            filename=str(path),
        )

        parents = {}

        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(
                parent
            ):
                parents[child] = parent

        for node in ast.walk(tree):
            if not isinstance(
                node,
                ast.Call,
            ):
                continue

            function_name = None

            if isinstance(
                node.func,
                ast.Name,
            ):
                function_name = (
                    node.func.id
                )

            elif isinstance(
                node.func,
                ast.Attribute,
            ):
                function_name = (
                    node.func.attr
                )

            if (
                function_name
                not in public_calls
            ):
                continue

            parent = parents.get(node)

            if isinstance(
                parent,
                ast.Expr,
            ):
                continue

            violations.append(
                (
                    str(
                        path.relative_to(
                            ROOT
                        )
                    ),
                    node.lineno,
                    function_name,
                    type(parent).__name__
                    if parent is not None
                    else "NONE",
                )
            )

    assert not violations, (
        "Google Sheets telemetry return "
        "value influences program flow: "
        f"{violations}"
    )


def test_settings_enable_async_google():
    from config import settings

    assert (
        settings.ENABLE_GOOGLE_SHEETS_LOGGING
        is True
    )

    assert (
        settings
        .GOOGLE_SHEETS_ASYNC_NONBLOCKING
        is True
    )

    assert (
        settings
        .GOOGLE_SHEETS_HTTP_TIMEOUT_SECONDS
        > 0
    )


def main():
    test_worker_is_prestarted()

    test_slow_google_does_not_block_producer()

    test_retry_flush_is_nonblocking()

    test_http_is_worker_only()

    test_google_calls_are_telemetry_only()

    test_settings_enable_async_google()

    print(
        "[PASS] Google Sheets publication is "
        "asynchronous: a 1-second HTTP stall "
        "does not block setup/event callers, "
        "retry flushing is off the trading "
        "thread, and requests.post exists only "
        "inside the background transport."
    )


if __name__ == "__main__":
    main()
