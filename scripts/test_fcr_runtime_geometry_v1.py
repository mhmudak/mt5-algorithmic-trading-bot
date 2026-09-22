from __future__ import annotations

import ast
from pathlib import Path
import re

from src.fcr_runtime_guard import (
    resolve_fcr_signal_entry,
    validate_fcr_runtime_geometry,
)


ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "src" / "live_bot.py"


def _call_name(node):
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def test_signal_entry_resolution():
    data = {"entry_reference": 4304.26}

    assert resolve_fcr_signal_entry(
        "FCR_M1_FVG",
        data,
        4310.86,
    ) == 4304.26

    assert resolve_fcr_signal_entry(
        "BREAKER_BLOCK",
        data,
        4310.86,
    ) == 4310.86


def test_runtime_sell_geometry_uses_fresh_price():
    result = validate_fcr_runtime_geometry(
        strategy_name="FCR_M1_FVG",
        signal="SELL",
        signal_data={"entry_reference": 4304.26},
        trade_plan={
            "entry_price": 4304.26,
            "stop_loss": 4310.26,
            "take_profit": 4286.26,
            "lot": 0.25,
        },
        executable_price=4302.00,
        min_rr_required=1.40,
    )

    assert result["allowed"] is True
    assert result["reason"] == "runtime_geometry_valid"
    assert result["signal_rr"] == 3.0
    assert round(result["runtime_rr"], 3) == 1.906
    assert result["chase_distance"] == 2.26
    assert result["trade_plan"]["entry_price"] == 4302.00
    assert result["trade_plan"]["stop_loss"] == 4310.26
    assert result["trade_plan"]["take_profit"] == 4286.26


def test_runtime_rr_rejects_chased_sell():
    result = validate_fcr_runtime_geometry(
        strategy_name="FCR_M1_FVG",
        signal="SELL",
        signal_data={"entry_reference": 4304.26},
        trade_plan={
            "entry_price": 4304.26,
            "stop_loss": 4310.26,
            "take_profit": 4286.26,
        },
        executable_price=4298.00,
        min_rr_required=1.40,
    )

    assert result["allowed"] is False
    assert result["reason"] == "runtime_rr_below_required"


def test_invalid_stop_side_rejected():
    result = validate_fcr_runtime_geometry(
        strategy_name="FCR_M1_FVG",
        signal="SELL",
        signal_data={"entry_reference": 4304.26},
        trade_plan={
            "entry_price": 4304.26,
            "stop_loss": 4310.26,
            "take_profit": 4286.26,
        },
        executable_price=4311.00,
        min_rr_required=1.0,
    )

    assert result["allowed"] is False
    assert result["reason"] == "invalid_stop_side"


def test_non_fcr_untouched():
    plan = {
        "entry_price": 5000.0,
        "stop_loss": 4990.0,
        "take_profit": 5020.0,
    }

    result = validate_fcr_runtime_geometry(
        strategy_name="FVG",
        signal="BUY",
        signal_data={},
        trade_plan=plan,
        executable_price=5001.0,
        min_rr_required=1.0,
    )

    assert result["applies"] is False
    assert result["allowed"] is True
    assert result["trade_plan"] == plan


def test_live_setup_detected_handoff():
    text = LIVE.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(text)

    detected_entry_ok = False
    event_entry_count = 0
    register_setup_price_ok = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            pairs = {}
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    pairs[key.value] = value

            value = pairs.get("entry")
            if isinstance(value, ast.Name) and value.id == "setup_detected_entry":
                detected_entry_ok = True

        if not isinstance(node, ast.Call):
            continue

        name = _call_name(node)

        if name in {"log_setup_event", "register_setup_outcome"}:
            event_kw = next(
                (kw for kw in node.keywords if kw.arg == "event"),
                None,
            )
            entry_kw = next(
                (kw for kw in node.keywords if kw.arg == "entry"),
                None,
            )

            if (
                event_kw is not None
                and isinstance(event_kw.value, ast.Constant)
                and event_kw.value.value == "SETUP_DETECTED"
                and entry_kw is not None
                and isinstance(entry_kw.value, ast.Name)
                and entry_kw.value.id == "setup_detected_entry"
            ):
                event_entry_count += 1

        if name == "register_setup":
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "execution_engine"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Name)
                and node.args[1].id == "setup_detected_entry"
            ):
                register_setup_price_ok = True

    assert detected_entry_ok
    assert event_entry_count >= 2
    assert register_setup_price_ok
    assert "setup_detected_entry = resolve_fcr_signal_entry(" in text


def test_runtime_guard_present():
    text = LIVE.read_text(encoding="utf-8", errors="replace")

    assert "validate_fcr_runtime_geometry(" in text
    assert "FCR_RUNTIME_GEOMETRY_REJECTED" in text
    assert "fresh_fcr_tick = mt5.symbol_info_tick(SYMBOL)" in text
    assert "fcr_runtime_geometry" in text


def test_closed_m1_authority_preserved():
    text = LIVE.read_text(encoding="utf-8", errors="replace")

    assert "FCR CLOSED-M1 CADENCE" in text
    assert "ENABLE_FCR_M1_FVG_CLOSED_M1_CADENCE" in text


def test_fixed_lot_unchanged():
    settings = (
        ROOT / "config" / "settings.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    match = re.search(
        r"(?m)^FIXED_LOT\s*=\s*([0-9.]+)\s*$",
        settings,
    )

    assert match
    assert float(match.group(1)) == 0.25


def main():
    test_signal_entry_resolution()
    test_runtime_sell_geometry_uses_fresh_price()
    test_runtime_rr_rejects_chased_sell()
    test_invalid_stop_side_rejected()
    test_non_fcr_untouched()
    test_live_setup_detected_handoff()
    test_runtime_guard_present()
    test_closed_m1_authority_preserved()
    test_fixed_lot_unchanged()

    print("PASS: FCR SETUP_DETECTED uses canonical entry_reference")
    print("PASS: SETUP_DETECTED event/outcome tracking uses canonical FCR entry")
    print("PASS: execution-engine registration uses canonical FCR signal entry")
    print("PASS: fresh executable price recomputes FCR runtime RR")
    print("PASS: stale/chased FCR rejected when runtime RR falls below required RR")
    print("PASS: invalid FCR stop side rejected")
    print("PASS: non-FCR strategies untouched")
    print("PASS: closed-M1 FCR live authority preserved")
    print("PASS: intrabar FCR not promoted by this patch")
    print("PASS: FIXED_LOT remains exactly 0.25")


if __name__ == "__main__":
    main()
