from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import tempfile

from src.daily_ladder_provider import (
    AUTO_COMPOSITE_MODE,
    MANUAL_AVO_MODE,
    DailyLadderValidationError,
    build_auto_composite_execution_ladder,
    build_daily_ladder_shadow,
    build_shadow_observations,
    calculate_shadow_levels,
    derive_broker_date_from_current_d1_time,
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
        raise AssertionError("Expected DailyLadderValidationError")


BASE = {
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


def test_constants_and_valid_manual_ladder():
    assert AUTO_COMPOSITE_MODE == "AUTO_COMPOSITE_DAILY_LADDER"
    assert MANUAL_AVO_MODE == "MANUAL_AVO_DAILY_LADDER"

    ladder = validate_manual_avo_ladder(
        BASE,
        expected_symbol="XAUUSD",
        expected_broker_date=date(2026, 9, 17),
    )
    assert ladder.symbol == "XAUUSD"
    assert ladder.broker_date == date(2026, 9, 17)
    assert len(ladder.upper) == 4
    assert len(ladder.lower) == 8
    assert ladder.source == MANUAL_AVO_MODE


def test_variable_counts_and_validation():
    variable = dict(BASE)
    variable["upper"] = [4300.26, 4315.11]
    variable["lower"] = [4275.49, 4252.06, 4239.80]
    ladder = validate_manual_avo_ladder(
        variable,
        expected_symbol="XAUUSD",
        expected_broker_date=date(2026, 9, 17),
    )
    assert len(ladder.upper) == 2
    assert len(ladder.lower) == 3

    stale = dict(BASE)
    stale["broker_date"] = "2026-09-16"
    expect_error(stale, "stale/future")

    wrong_symbol = dict(BASE)
    wrong_symbol["symbol"] = "EURUSD"
    expect_error(wrong_symbol, "symbol mismatch")

    bad_upper_order = dict(BASE)
    bad_upper_order["upper"] = [4315.11, 4300.26]
    expect_error(bad_upper_order, "upper must be strictly ordered")

    bad_lower_order = dict(BASE)
    bad_lower_order["lower"] = [4252.06, 4275.49]
    expect_error(bad_lower_order, "lower must be strictly ordered")

    wrong_side = dict(BASE)
    wrong_side["upper"] = [4280.0]
    expect_error(wrong_side, "every upper level must be above pivot")

    duplicate = dict(BASE)
    duplicate["upper"] = [4300.26, 4300.26]
    expect_error(duplicate, "duplicate")


def test_missing_malformed_and_valid_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        missing = root / "missing.json"
        try:
            load_manual_avo_ladder(
                missing,
                expected_symbol="XAUUSD",
                expected_broker_date=date(2026, 9, 17),
            )
        except DailyLadderValidationError as exc:
            assert "does not exist" in str(exc)
        else:
            raise AssertionError("missing file must fail closed")

        malformed = root / "malformed.json"
        malformed.write_text("{not-json", encoding="utf-8")
        try:
            load_manual_avo_ladder(
                malformed,
                expected_symbol="XAUUSD",
                expected_broker_date=date(2026, 9, 17),
            )
        except DailyLadderValidationError as exc:
            assert "JSON is invalid" in str(exc)
        else:
            raise AssertionError("malformed JSON must fail closed")

        valid = root / "valid.json"
        valid.write_text(json.dumps(BASE), encoding="utf-8")
        ladder = load_manual_avo_ladder(
            valid,
            expected_symbol="XAUUSD",
            expected_broker_date=date(2026, 9, 17),
        )
        assert ladder.pivot == 4288.61


def test_broker_date_reconstructs_broker_midnight_from_mt5_utc_open():
    # MT5 bar times are UTC.  A broker D1 opening at 21:00 UTC corresponds
    # to the following broker calendar day when server midnight is UTC+3.
    assert derive_broker_date_from_current_d1_time(
        "2026-09-17 21:00:00"
    ) == date(2026, 9, 18)
    assert derive_broker_date_from_current_d1_time(
        "2026-09-17 22:00:00"
    ) == date(2026, 9, 18)
    assert derive_broker_date_from_current_d1_time(
        "2026-09-18 00:00:00"
    ) == date(2026, 9, 18)
    assert derive_broker_date_from_current_d1_time(
        "2026-09-18 01:00:00"
    ) == date(2026, 9, 18)
    assert derive_broker_date_from_current_d1_time(
        "2026-09-20 21:00:00"
    ) == date(2026, 9, 21)



def test_auto_composite_execution_adapter_uses_existing_clusters():
    kwargs = {
        "previous_open": 4292.62,
        "previous_high": 4366.73,
        "previous_low": 4235.24,
        "previous_close": 4262.63,
        "current_open": 4260.26,
    }

    shadow = build_daily_ladder_shadow(**kwargs)
    ladder = build_auto_composite_execution_ladder(
        symbol="XAUUSD",
        broker_date=date(2026, 9, 17),
        **kwargs,
    )

    assert ladder.symbol == "XAUUSD"
    assert ladder.broker_date == date(2026, 9, 17)
    assert ladder.source == AUTO_COMPOSITE_MODE
    assert ladder.pivot == shadow.pivot
    assert ladder.upper == tuple(
        cluster.representative.price
        for cluster in shadow.upper
    )
    assert ladder.lower == tuple(
        cluster.representative.price
        for cluster in shadow.lower
    )
    assert ladder.upper
    assert ladder.lower


def test_shadow_reproduces_sep17_structure_and_has_no_authority():
    pivot, raw = calculate_shadow_levels(
        previous_open=4292.62,
        previous_high=4366.73,
        previous_low=4235.24,
        previous_close=4262.63,
        current_open=4260.26,
    )
    assert round(pivot, 2) == 4288.20

    by_name = {item.name: item.price for item in raw}
    assert abs(by_name["CAM:R3"] - 4298.79) < 0.02
    assert abs(by_name["CLASSIC:R1"] - 4341.16) < 0.02
    assert abs(by_name["CLASSIC:S1"] - 4209.67) < 0.02

    approved = validate_manual_avo_ladder(
        BASE,
        expected_symbol="XAUUSD",
        expected_broker_date=date(2026, 9, 17),
    )
    observations = build_shadow_observations(
        approved_ladder=approved,
        raw_levels=raw,
        cluster_distance=3.0,
    )
    assert observations
    assert all(item["execution_authority"] is False for item in observations)
    assert {
        item["classification"]
        for item in observations
    } <= {
        "APPROVED",
        "CLUSTERED_WITH_APPROVED",
        "EXTRA_RAW",
    }


if __name__ == "__main__":
    test_constants_and_valid_manual_ladder()
    test_variable_counts_and_validation()
    test_missing_malformed_and_valid_files()
    test_broker_date_reconstructs_broker_midnight_from_mt5_utc_open()
    test_auto_composite_execution_adapter_uses_existing_clusters()
    test_shadow_reproduces_sep17_structure_and_has_no_authority()

    print("PASS: Daily Ladder Provider V1")
    print("PASS: variable upper/lower counts")
    print("PASS: stale/current broker-date validation")
    print("PASS: ordering/side/duplicate/symbol validation")
    print("PASS: missing/malformed manual files fail closed")
    print("PASS: broker date reconstructs broker midnight from MT5 UTC D1 open")
    print("PASS: AUTO composite converts existing clusters to DLLB ladder")
    print("PASS: AUTO shadow reproduces Sep 17 diagnostic structure")
    print("PASS: raw shadow observations remain execution_authority=False")
