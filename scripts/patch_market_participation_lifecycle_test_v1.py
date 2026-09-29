from pathlib import Path

p = Path(r"scripts\test_market_participation_context.py")
text = p.read_text(encoding="utf-8-sig")

old = '''    # Definition + five lifecycle notification uses.
    assert (
        live_source.count(
            "_market_participation_telegram_"
            "block_fail_open("
        )
        == 6
    )
'''

new = '''    # Direct Market Participation helper remains available for
    # non-directional / legacy presentation paths.
    assert (
        live_source.count(
            "_market_participation_telegram_"
            "block_fail_open("
        )
        == 4
    )

    # Definition + six directional setup/candidate notification uses.
    assert (
        live_source.count(
            "_directional_alert_context_"
            "blocks_fail_open("
        )
        == 7
    )
'''

if old not in text:
    raise SystemExit("[FAIL] legacy lifecycle count assertion not found")

text = text.replace(old, new, 1)

p.write_text(
    text,
    encoding="utf-8",
    newline="\n",
)

print("[PASS] lifecycle notification source-contract updated")
