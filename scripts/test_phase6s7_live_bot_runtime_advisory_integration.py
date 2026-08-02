from pathlib import Path


SETTINGS = Path("config/settings.py")
LIVE_BOT = Path("src/live_bot.py")


def test_phase6s7_settings_flags_exist_and_keep_telegram_safe():
    text = SETTINGS.read_text(encoding="utf-8")

    assert "ENABLE_PHASE6S_RUNTIME_OUTLOOK_ADVISORY = True" in text or "ENABLE_PHASE6S_RUNTIME_OUTLOOK_ADVISORY = False" in text
    assert "SEND_PHASE6S_RUNTIME_OUTLOOK_ADVISORY_TELEGRAM = False" in text
    assert 'PHASE6S_RUNTIME_OUTLOOK_ADVISORY_REPORT_TYPE = "scenario_update"' in text
    assert "PHASE6S_RUNTIME_OUTLOOK_ADVISORY_FORCE_SEND = False" in text


def test_phase6s7_live_bot_imports_runtime_hook_and_flags():
    text = LIVE_BOT.read_text(encoding="utf-8")

    assert "from src.market_outlook_advisory_runtime import maybe_send_runtime_outlook_advisory" in text
    assert "ENABLE_PHASE6S_RUNTIME_OUTLOOK_ADVISORY" in text
    assert "SEND_PHASE6S_RUNTIME_OUTLOOK_ADVISORY_TELEGRAM" in text
    assert "PHASE6S_RUNTIME_OUTLOOK_ADVISORY_REPORT_TYPE" in text
    assert "PHASE6S_RUNTIME_OUTLOOK_ADVISORY_FORCE_SEND" in text


def test_phase6s7_helper_is_advisory_only():
    text = LIVE_BOT.read_text(encoding="utf-8")

    assert "def maybe_notify_phase6s_runtime_outlook_advisory(" in text
    assert "Advisory only:" in text
    assert '"auto_trade_allowed": False' in text
    assert '"can_execute": False' in text
    assert '"can_block_trade": False' in text
    assert '"can_modify_risk": False' in text


def test_phase6s7_hook_is_before_main_execute_trade():
    text = LIVE_BOT.read_text(encoding="utf-8")

    hook_index = text.find('trigger_context="before_execute_trade"')
    execute_index = text.find("execution_result = execute_trade(signal, trade_plan, SYMBOL)")

    assert hook_index != -1
    assert execute_index != -1
    assert hook_index < execute_index


if __name__ == "__main__":
    test_phase6s7_settings_flags_exist_and_keep_telegram_safe()
    test_phase6s7_live_bot_imports_runtime_hook_and_flags()
    test_phase6s7_helper_is_advisory_only()
    test_phase6s7_hook_is_before_main_execute_trade()
    print("[PASS] Phase 6S7 live_bot runtime advisory integration passed.")
