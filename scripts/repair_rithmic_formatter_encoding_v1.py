from pathlib import Path
import re

p = Path(r"src\rithmic_setup_verdict.py")
text = p.read_text(encoding="utf-8-sig")

start = re.search(
    r"(?m)^def format_rithmic_setup_verdict_telegram_block\(",
    text,
)
if not start:
    raise SystemExit("formatter not found")

next_func = re.search(
    r"(?m)^def [A-Za-z_][A-Za-z0-9_]*\(",
    text[start.end():],
)

end = (
    start.end() + next_func.start()
    if next_func
    else len(text)
)

new_func = r'''def format_rithmic_setup_verdict_telegram_block(
    verdict: dict | None,
) -> str:
    """Format compact display-only Rithmic context for directional alerts."""

    verdict = verdict if isinstance(verdict, dict) else {}

    state = _safe_text(
        verdict.get("verdict"),
        "UNAVAILABLE",
    ).upper()

    direction = _safe_text(
        verdict.get("setup_direction"),
        "UNKNOWN",
    ).upper()

    reason = _safe_text(
        verdict.get("reason"),
        "rithmic_context_unavailable",
    )
    reason_lower = reason.lower()

    if state == "SUPPORTS_SETUP":
        headline = f"\U0001F7E2 RITHMIC: SUPPORTS {direction}"
    elif state == "AGAINST_SETUP":
        headline = f"\U0001F534 RITHMIC: AGAINST {direction}"
    elif state == "NEUTRAL":
        headline = "\u26AA RITHMIC: NEUTRAL / MIXED"
    else:
        if any(
            token in reason_lower
            for token in (
                "stale",
                "not_fully_fresh",
                "source_age",
                "age_missing",
            )
        ):
            headline = "\u26AA RITHMIC: UNAVAILABLE / STALE"
        elif any(
            token in reason_lower
            for token in (
                "disconnect",
                "not_connected",
                "connection",
            )
        ):
            headline = "\u26AA RITHMIC: UNAVAILABLE / DISCONNECTED"
        else:
            headline = "\u26AA RITHMIC: UNAVAILABLE"

    symbol = _safe_text(
        verdict.get("rithmic_symbol"),
        "RITHMIC",
    )
    exchange = _safe_text(
        verdict.get("exchange"),
        "COMEX",
    )

    source_age = _safe_float(
        verdict.get("source_age_seconds")
    )
    cache_age = _safe_float(
        verdict.get("cache_age_seconds")
    )

    display_age = (
        source_age
        if source_age is not None
        else cache_age
    )

    if display_age is None:
        freshness = "Freshness unavailable"
    elif display_age <= RITHMIC_SETUP_CACHE_MAX_AGE_SECONDS:
        freshness = f"Fresh {round(display_age, 1)}s"
    else:
        freshness = f"Stale {round(display_age, 1)}s"

    metrics = (
        verdict.get("metrics")
        if isinstance(verdict.get("metrics"), dict)
        else {}
    )

    trades = verdict.get("trade_count")
    trades_label = (
        str(trades)
        if trades is not None
        else "N/A"
    )

    support = int(verdict.get("support_score", 0) or 0)
    against = int(verdict.get("against_score", 0) or 0)

    lines = [headline]

    if state == "UNAVAILABLE":
        lines.append(
            "Reason: " + reason
        )

    lines.extend(
        [
            f"{symbol} | {exchange} | {freshness}",
            (
                f"Trades {trades_label} | "
                f"\u0394 {_format_signed(metrics.get('delta'))} | "
                f"Cum\u0394 {_format_signed(metrics.get('cumulative_delta'))} | "
                f"DOM {_format_signed(metrics.get('dom_depth_imbalance'))}"
            ),
            f"Evidence: {support} SUPPORT / {against} AGAINST",
            "Mode: OBSERVE ONLY \u2014 NO EXECUTION AUTHORITY",
        ]
    )

    return "\n".join(lines)
'''

text = (
    text[:start.start()]
    + new_func
    + "\n\n\n"
    + text[end:]
)

p.write_text(
    text,
    encoding="utf-8",
    newline="\n",
)

print("[PASS] Rithmic formatter repaired with ASCII-safe Unicode escapes")
