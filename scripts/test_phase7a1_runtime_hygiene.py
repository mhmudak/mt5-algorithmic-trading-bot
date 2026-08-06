from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "src" / "live_bot.py"
SETTINGS = ROOT / "config" / "settings.py"


def test_phase6s_runtime_setting_name():
    text = LIVE.read_text(encoding="utf-8")

    assert "PHASE6S_RUNTIME_OUTLOOKSYMBOL" not in text
    assert (
        "report_type=PHASE6S_RUNTIME_OUTLOOK_ADVISORY_REPORT_TYPE"
        in text
    )


def test_no_deprecated_utcnow_timestamp_calls():
    text = LIVE.read_text(encoding="utf-8")

    assert "datetime.utcnow().timestamp()" not in text
    assert "datetime.now(timezone.utc).timestamp()" in text


def test_funded_mode_inactive_on_current_account():
    text = SETTINGS.read_text(encoding="utf-8")

    assert "ENABLE_PROP_FIRM_SAFE_MODE = False" in text
    assert (
        'PROP_FIRM_PROFILE = '
        '"GETLEVERAGED_TURBO_EVALUATION_50K"'
    ) in text


if __name__ == "__main__":
    test_phase6s_runtime_setting_name()
    test_no_deprecated_utcnow_timestamp_calls()
    test_funded_mode_inactive_on_current_account()

    print("[PASS] Runtime hygiene and funded activation safety passed.")
