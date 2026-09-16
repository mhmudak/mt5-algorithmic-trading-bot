from pathlib import Path
import ast
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


LIVE_BOT = ROOT / "src" / "live_bot.py"


def _source():
    return LIVE_BOT.read_text(encoding="utf-8")


def _setup_detected_region(source):
    start = source.index(
        "                detected_message = ("
    )
    end = source.index(
        "                log_setup_event(",
        start,
    )
    return source[start:end]


def test_setup_detected_receives_entry_tp_context():
    region = _setup_detected_region(_source())

    assert "_entry_tp_opportunity_block_fail_open(" in region

    for required in (
        "df=df",
        "signal_data=selected_signal_data",
        "trade_plan=detected_trade_plan",
        "signal=signal",
        "required_rr=min_rr_required",
    ):
        assert required in region

    assert '"entry_price": close_price' in region
    assert '"sl_reference"' in region
    assert '"tp_reference"' in region
    assert '"pivot_target_level"' in region


def test_tp_context_appended_before_participation():
    region = _setup_detected_region(_source())

    assert (
        region.index("if detected_entry_tp_block:")
        < region.index("if detected_participation_block:")
        < region.index("send_telegram_message_async(")
    )


def test_existing_setup_message_preserved():
    region = _setup_detected_region(_source())

    assert "build_trade_message(" in region
    assert "_market_participation_telegram_block_fail_open(" in region
    assert "setup_participation_context" in region
    assert "send_telegram_message_async(" in region


def test_v1_4_is_presentation_only():
    region = _setup_detected_region(_source())

    for forbidden in (
        "selected_signal_data[",
        "trade_allowed =",
        "execution_allowed =",
        "rr_value =",
        "min_rr_required =",
        "FIXED_LOT =",
    ):
        assert forbidden not in region

    assert (
        "This must never alter entry, SL, TP1-TP3,"
        in region
    )


def test_helper_call_count_is_five():
    source = _source()

    assert (
        source.count(
            "_entry_tp_opportunity_block_fail_open("
        )
        == 5
    )


def test_live_bot_parses():
    ast.parse(_source())


def test_fixed_lot_unchanged():
    settings = (
        ROOT
        / "config"
        / "settings.py"
    ).read_text(encoding="utf-8")

    assert "FIXED_LOT = 0.25" in settings


if __name__ == "__main__":
    test_setup_detected_receives_entry_tp_context()
    test_tp_context_appended_before_participation()
    test_existing_setup_message_preserved()
    test_v1_4_is_presentation_only()
    test_helper_call_count_is_five()
    test_live_bot_parses()
    test_fixed_lot_unchanged()

    print("PASS: Entry/TP Opportunity V1.4")
    print("PASS: normal SETUP DETECTED receives TP Context")
    print("PASS: TP Context precedes Market Participation")
    print("PASS: existing SETUP DETECTED message preserved")
    print("PASS: TP1-TP3 / RR / execution authority unchanged")
    print("PASS: helper call count is five")
    print("PASS: FIXED_LOT remains 0.25")
