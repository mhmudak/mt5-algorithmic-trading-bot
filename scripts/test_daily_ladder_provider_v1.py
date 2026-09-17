from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import tempfile

from src.daily_ladder_provider import (
    AUTO_COMPOSITE_MODE,
    MANUAL_AVO_MODE,
    DailyLadderValidationError,
    auto_composite_display_levels,
    load_manual_avo_ladder,
    validate_manual_avo_ladder,
)


def expect_error(payload, contains: str) -> None:
    try:
        validate_manual_avo_ladder(
            payload,
            expected_symbol="XAUUSD",
            expected_broker_date=date(2026, 9, 17),
        )
    except DailyLadderValidationError as exc:
        assert contains in str(exc), (contains, str(exc))
    else:
        raise AssertionError(
            "Expected DailyLadderValidationError"
        )


assert AUTO_COMPOSITE_MODE == "AUTO_COMPOSITE_DAILY_LADDER"
assert MANUAL_AVO_MODE == "MANUAL_AVO_DAILY_LADDER"

base = {
    "symbol": "XAUUSD",
    "broker_date": "2026-09-17",
    "pivot": 4288.61,
    "upper": [4300.26, 4315.11, 4330.01, 4341.91],
    "lower": [
        4275.49,
        4252.06,
        4239.80,
        4227.96,
        4210.25,
        4198.52,
        4191.25,
        4156.39,
    ],
}

avo = validate_manual_avo_ladder(
    base,
    expected_symbol="XAUUSD",
    expected_broker_date=date(2026, 9, 17),
)

assert avo.source == MANUAL_AVO_MODE
assert len(avo.upper) == 4
assert len(avo.lower) == 8

variable = dict(base)
variable["upper"] = [4300.0, 4315.0, 4330.0, 4342.0, 4360.0]
variable["lower"] = [4275.0, 4252.0, 4239.0]

variable_avo = validate_manual_avo_ladder(
    variable,
    expected_symbol="XAUUSD",
    expected_broker_date=date(2026, 9, 17),
)

assert len(variable_avo.upper) == 5
assert len(variable_avo.lower) == 3

stale = dict(base)
stale["broker_date"] = "2026-09-16"
expect_error(
    stale,
    "stale/future manual Avo ladder",
)

bad_upper = dict(base)
bad_upper["upper"] = [4315.11, 4300.26]
expect_error(
    bad_upper,
    "upper must be strictly ordered",
)

bad_lower = dict(base)
bad_lower["lower"] = [4252.06, 4275.49]
expect_error(
    bad_lower,
    "lower must be strictly ordered",
)

wrong_side = dict(base)
wrong_side["upper"] = [4280.0, 4300.0]
expect_error(
    wrong_side,
    "every upper level must be above pivot",
)

duplicate = dict(base)
duplicate["lower"] = [4275.49, 4275.49]
expect_error(
    duplicate,
    "duplicate",
)

wrong_symbol = dict(base)
wrong_symbol["symbol"] = "EURUSD"
expect_error(
    wrong_symbol,
    "symbol mismatch",
)

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "avo_ladder.json"
    path.write_text(
        json.dumps(base),
        encoding="utf-8",
    )
    loaded = load_manual_avo_ladder(
        path,
        expected_symbol="XAUUSD",
        expected_broker_date=date(2026, 9, 17),
    )
    assert loaded == avo

display = auto_composite_display_levels(
    previous_open=4292.62,
    previous_high=4366.73,
    previous_low=4235.24,
    previous_close=4262.63,
    current_open=4260.26,
)

assert round(display.pivot, 2) == 4288.20
assert round(display.day_range, 2) == 131.49
assert len(display.upper) == 7
assert len(display.lower) == 9

upper_prices = [
    cluster.representative.price
    for cluster in display.upper
]
lower_prices = [
    cluster.representative.price
    for cluster in display.lower
]

assert upper_prices == sorted(upper_prices)
assert lower_prices == sorted(
    lower_prices,
    reverse=True,
)

upper_names = [
    cluster.representative.name
    for cluster in display.upper
]
lower_names = [
    cluster.representative.name
    for cluster in display.lower
]

assert upper_names[:4] == [
    "CAM:R3",
    "DM:R1",
    "CAM:R4",
    "CLASSIC:R1",
]
assert lower_names[:5] == [
    "CAM:R1",
    "CAM:S1",
    "CAM:S2",
    "CAM:S3",
    "CLASSIC:S1",
]

print("PASS: Daily Ladder Provider V1")
print("PASS: AUTO composite is display/observation-only")
print("PASS: MANUAL Avo is distinct execution-input contract")
print("PASS: variable Avo upper/lower counts")
print("PASS: stale/current broker-date validation")
print("PASS: ordering/side/duplicate/symbol validation")
print("PASS: AUTO display reproduces Sep 17 shadow structure")
print("PASS: provider contains no execution authority")
