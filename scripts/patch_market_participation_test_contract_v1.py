from pathlib import Path

p = Path(r"scripts\test_market_participation_context.py")
text = p.read_text(encoding="utf-8-sig")

old1 = '''    assert (
        "Market Participation — MT5 Proxy"
        in block
    )

    assert "Activity: ACCELERATING" in block
    assert "Pressure: SELL" in block
    assert "5s Imbalance: -0.78" in block
    assert "Signal Relation: WITH_SIGNAL" in block
    assert "Rithmic: UNAVAILABLE" in block
    assert "Mode: OBSERVE ONLY" in block
'''

new1 = '''    assert (
        "MARKET PARTICIPATION"
        in block
    )

    assert "Activity: ACCELERATING" in block
    assert "MT5 Pressure: SELL" in block
    assert "5s Imbalance: -0.78" in block
    assert "Signal Relation: WITH_SIGNAL" in block
    assert "Cross-Market Context:" in block

    # Detailed Rithmic state belongs only in the top Rithmic verdict block.
    assert "Rithmic Aggression:" not in block
    assert "DOM:" not in block
'''

old2 = '''    assert (
        "Market Participation — MT5 + Rithmic"
        in block
    )

    assert (
        "Rithmic Aggression: BUY_AGGRESSION"
        in block
    )

    assert (
        "DOM: BID_DEPTH_DOMINANT"
        in block
    )
'''

new2 = '''    assert (
        "MARKET PARTICIPATION"
        in block
    )

    assert "Cross-Market Context:" in block

    # Do not duplicate detailed Rithmic evidence below the setup form.
    assert "Rithmic Aggression:" not in block
    assert "DOM:" not in block
'''

if old1 not in text:
    raise SystemExit("[FAIL] MT5-only legacy assertion block not found")

if old2 not in text:
    raise SystemExit("[FAIL] Rithmic legacy assertion block not found")

text = text.replace(old1, new1, 1)
text = text.replace(old2, new2, 1)

p.write_text(
    text,
    encoding="utf-8",
    newline="\n",
)

print("[PASS] Market Participation test updated to unified Rithmic-header contract")
