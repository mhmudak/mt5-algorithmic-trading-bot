from __future__ import annotations

from copy import deepcopy

import src.google_sheets_logger as gsl


def _items(count):
    return [
        {
            "queue_key": f"item-{index}",
            "payload": {
                "id": index,
            },
            "attempts": 0,
        }
        for index in range(count)
    ]


def _run_case(items, outcomes, max_items):
    posts = []
    saved = {}

    original_enabled = (
        gsl.ENABLE_GOOGLE_SHEETS_LOGGING
    )
    original_load = (
        gsl.load_google_sheets_retry_queue
    )
    original_save = (
        gsl.save_google_sheets_retry_queue
    )
    original_post = (
        gsl._post_google_sheets_payload_sync
    )

    def fake_load():
        return deepcopy(items)

    def fake_save(value):
        saved["items"] = deepcopy(value)

    def fake_post(payload, label):
        position = len(posts)

        if position >= len(outcomes):
            raise AssertionError(
                "Unexpected extra HTTP retry attempt"
            )

        posts.append(
            (
                payload.get("id"),
                label,
            )
        )

        return outcomes[position]

    try:
        gsl.ENABLE_GOOGLE_SHEETS_LOGGING = True
        gsl.load_google_sheets_retry_queue = (
            fake_load
        )
        gsl.save_google_sheets_retry_queue = (
            fake_save
        )
        gsl._post_google_sheets_payload_sync = (
            fake_post
        )

        flushed = (
            gsl._flush_google_sheets_retry_queue_sync(
                max_items=max_items,
            )
        )

    finally:
        gsl.ENABLE_GOOGLE_SHEETS_LOGGING = (
            original_enabled
        )
        gsl.load_google_sheets_retry_queue = (
            original_load
        )
        gsl.save_google_sheets_retry_queue = (
            original_save
        )
        gsl._post_google_sheets_payload_sync = (
            original_post
        )

    return (
        flushed,
        posts,
        saved["items"],
    )


def test_outage_stops_after_one_attempt():
    items = _items(8)

    flushed, posts, remaining = _run_case(
        items,
        outcomes=[
            (False, "timeout"),
        ],
        max_items=5,
    )

    assert flushed == 0
    assert len(posts) == 1

    assert [
        item["queue_key"]
        for item in remaining
    ] == [
        "item-1",
        "item-2",
        "item-3",
        "item-4",
        "item-5",
        "item-6",
        "item-7",
        "item-0",
    ]

    failed = remaining[-1]

    assert failed["attempts"] == 1
    assert failed["last_error"] == "timeout"
    assert failed.get("last_attempt_at")


def test_successes_then_failure_pause_batch():
    items = _items(8)

    flushed, posts, remaining = _run_case(
        items,
        outcomes=[
            (True, None),
            (True, None),
            (True, None),
            (False, "timeout"),
        ],
        max_items=5,
    )

    assert flushed == 3
    assert len(posts) == 4

    assert [
        item["queue_key"]
        for item in remaining
    ] == [
        "item-4",
        "item-5",
        "item-6",
        "item-7",
        "item-3",
    ]

    assert remaining[-1]["attempts"] == 1


def test_max_items_caps_successful_attempts():
    items = _items(8)

    flushed, posts, remaining = _run_case(
        items,
        outcomes=[
            (True, None),
            (True, None),
        ],
        max_items=2,
    )

    assert flushed == 2
    assert len(posts) == 2

    assert [
        item["queue_key"]
        for item in remaining
    ] == [
        "item-2",
        "item-3",
        "item-4",
        "item-5",
        "item-6",
        "item-7",
    ]


def main():
    test_outage_stops_after_one_attempt()
    test_successes_then_failure_pause_batch()
    test_max_items_caps_successful_attempts()

    print(
        "PASS: Google Sheets retry fairness "
        "and outage backpressure"
    )


if __name__ == "__main__":
    main()
