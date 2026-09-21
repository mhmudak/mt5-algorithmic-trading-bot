from __future__ import annotations

from pathlib import Path

from src.fcr_m1_cadence import advance_closed_m1_state


ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "src" / "live_bot.py"
SETTINGS = ROOT / "config" / "settings.py"


def test_state_machine():
    last, due, armed = advance_closed_m1_state(None, 100)
    assert last == 100
    assert due is False
    assert armed is True

    last, due, armed = advance_closed_m1_state(last, 100)
    assert last == 100
    assert due is False
    assert armed is False

    last, due, armed = advance_closed_m1_state(last, 160)
    assert last == 160
    assert due is True
    assert armed is False

    last, due, armed = advance_closed_m1_state(last, 160)
    assert last == 160
    assert due is False
    assert armed is False

    last, due, armed = advance_closed_m1_state(last, 120)
    assert last == 160
    assert due is False
    assert armed is False


def test_live_wiring():
    live = LIVE.read_text(encoding="utf-8", errors="replace")
    settings = SETTINGS.read_text(encoding="utf-8", errors="replace")

    assert "ENABLE_FCR_M1_FVG_CLOSED_M1_CADENCE = True" in settings
    assert "[PHASE 6R FCR M1 CADENCE]" in live
    assert "startup armed on latest closed M1" in live
    assert "new closed M1 detected" in live
    assert "fcr_m1_cycle_due" in live
    assert "fcr_m1_only_cycle" in live
    assert 'if name != "FCR_M1_FVG"' in live
    assert 'if name == "FCR_M1_FVG"' in live
    assert "mt5.TIMEFRAME_M1" in live
    assert "start_pos=1 intentionally excludes" in live

    cadence = (
        ROOT / "src" / "fcr_m1_cadence.py"
    ).read_text(encoding="utf-8", errors="replace")

    assert "execute_trade(" not in cadence
    assert "order_send(" not in cadence


def main():
    test_state_machine()
    test_live_wiring()

    print("PASS: FCR closed-M1 cadence state machine")
    print("PASS: startup arms latest closed M1 with no retroactive cycle")
    print("PASS: duplicate closed M1 does not re-evaluate")
    print("PASS: newer closed M1 schedules exactly one FCR cycle")
    print("PASS: cadence layer has no direct execution authority")


if __name__ == "__main__":
    main()
