from pathlib import Path
from datetime import datetime
import re
import shutil

ROOT = Path(".")
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / "local_backups" / f"rithmic_directional_alerts_{STAMP}"
BACKUP.mkdir(parents=True, exist_ok=True)

FILES = {
    "rithmic": ROOT / "src" / "rithmic_setup_verdict.py",
    "participation": ROOT / "src" / "market_participation_context.py",
    "live": ROOT / "src" / "live_bot.py",
}

for p in FILES.values():
    shutil.copy2(p, BACKUP / p.name)

def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)

def replace_function(text, name, new_source):
    start_match = re.search(
        rf"(?m)^def {re.escape(name)}\(",
        text,
    )
    if not start_match:
        raise RuntimeError(f"function not found: {name}")

    start = start_match.start()

    next_match = re.search(
        r"(?m)^def [A-Za-z_][A-Za-z0-9_]*\(",
        text[start_match.end():],
    )

    end = (
        start_match.end() + next_match.start()
        if next_match
        else len(text)
    )

    return (
        text[:start]
        + new_source.rstrip()
        + "\n\n\n"
        + text[end:]
    )

# ============================================================
# 1. Rithmic compact Telegram formatter
# ============================================================

rithmic_path = FILES["rithmic"]
rithmic_text = rithmic_path.read_text(encoding="utf-8")

new_formatter = r'''
def format_rithmic_setup_verdict_telegram_block(
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
        headline = f"🟢 RITHMIC: SUPPORTS {direction}"

    elif state == "AGAINST_SETUP":
        headline = f"🔴 RITHMIC: AGAINST {direction}"

    elif state == "NEUTRAL":
        headline = "⚪ RITHMIC: NEUTRAL / MIXED"

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
            headline = "⚪ RITHMIC: UNAVAILABLE / STALE"

        elif any(
            token in reason_lower
            for token in (
                "disconnect",
                "not_connected",
                "connection",
            )
        ):
            headline = "⚪ RITHMIC: UNAVAILABLE / DISCONNECTED"

        else:
            headline = "⚪ RITHMIC: UNAVAILABLE"

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
                f"Δ {_format_signed(metrics.get('delta'))} | "
                f"CumΔ {_format_signed(metrics.get('cumulative_delta'))} | "
                f"DOM {_format_signed(metrics.get('dom_depth_imbalance'))}"
            ),
            f"Evidence: {support} SUPPORT / {against} AGAINST",
            "OBSERVE ONLY — NO EXECUTION AUTHORITY",
        ]
    )

    return "\n".join(lines)
'''

rithmic_text = replace_function(
    rithmic_text,
    "format_rithmic_setup_verdict_telegram_block",
    new_formatter,
)

# ============================================================
# 2. Market Participation = MT5 summary + cross-market only
#    Remove duplicated Rithmic aggression / DOM / Mode
# ============================================================

participation_path = FILES["participation"]
participation_text = participation_path.read_text(encoding="utf-8")

func_start = participation_text.index(
    "def format_market_participation_telegram_block("
)

next_func = participation_text.index(
    "\ndef classify_market_participation_alert(",
    func_start,
)

func = participation_text[func_start:next_func]

old_title = '''    if source_coverage == "MT5_PLUS_RITHMIC":
        title = (
            "🏦 Market Participation — "
            "MT5 + Rithmic"
        )
    else:
        title = (
            "🏦 Market Participation — "
            "MT5 Proxy"
        )
'''

if old_title in func:
    func = func.replace(
        old_title,
        '    title = "🏦 MARKET PARTICIPATION"\n',
        1,
    )

func = func.replace(
    '"Pressure: "',
    '"MT5 Pressure: "',
    1,
)

tail_start = func.find(
    '''    if bool(
        rithmic.get(
            "available"
'''
)

if tail_start == -1:
    raise RuntimeError(
        "Market Participation Rithmic detail block not found"
    )

return_start = func.find(
    '    return "\\n".join(',
    tail_start,
)

if return_start == -1:
    raise RuntimeError(
        "Market Participation return block not found"
    )

new_tail = '''    combined_state = _safe_text(
        context.get("combined_state"),
        "UNRESOLVED",
    ).upper()

    if combined_state.startswith("CROSS_MARKET_"):
        combined_state = combined_state[len("CROSS_MARKET_"):]

    combined_label = combined_state.replace("_", " ")

    lines.append(
        "Cross-Market Context: "
        + combined_label
    )

'''

func = (
    func[:tail_start]
    + new_tail
    + func[return_start:]
)

participation_text = (
    participation_text[:func_start]
    + func
    + participation_text[next_func:]
)

# ============================================================
# 3. Shared fail-open helper for directional Telegram alerts
# ============================================================

live_path = FILES["live"]
live_text = live_path.read_text(encoding="utf-8")

helper_anchor = (
    "def _notify_market_participation_high_impact_fail_open("
)

if "_directional_alert_context_blocks_fail_open" not in live_text:
    helper = r'''
def _directional_alert_context_blocks_fail_open(
    *,
    signal,
    tick=None,
    context=None,
):
    """
    Display-only helper for directional setup/candidate Telegram forms.

    Rithmic remains observe-only and cannot change candidate state,
    score, RR, entry, SL, TP, risk, confirmation, or execution.
    """

    resolved_context = (
        context
        if isinstance(context, dict)
        else None
    )

    if resolved_context is None:
        try:
            resolved_context = (
                _capture_market_participation_context(
                    signal=signal,
                    symbol=SYMBOL,
                )
            )
        except Exception as exc:
            logger.warning(
                "[DIRECTIONAL ALERT CONTEXT] "
                f"capture failed open: {exc}"
            )
            resolved_context = None

    direction = str(signal or "").upper()

    rithmic_block = ""

    if direction in {"BUY", "SELL"}:
        _, rithmic_block = (
            _rithmic_setup_verdict_telegram_fail_open(
                signal=direction,
                context=resolved_context,
            )
        )

    participation_block = (
        _market_participation_telegram_block_fail_open(
            signal=signal,
            tick=tick,
            context=resolved_context,
        )
    )

    return (
        resolved_context,
        rithmic_block,
        participation_block,
    )


'''

    live_text = replace_once(
        live_text,
        helper_anchor,
        helper + helper_anchor,
        "insert directional alert helper",
    )

# ============================================================
# 4. Strong rejected candidate tracked
# ============================================================

new_strong_rejected = r'''
def notify_rejected_candidate_if_relevant(
    *,
    setup_id,
    strategy,
    signal,
    entry_model,
    session_name,
    market_condition,
    score,
    rr,
    entry,
    sl,
    tp,
    reason,
):
    if not TELEGRAM_NOTIFY_REJECTED_CANDIDATE_TRACKED:
        return

    try:
        score_value = float(score or 0)
    except Exception:
        score_value = 0.0

    try:
        rr_value = float(rr or 0)
    except Exception:
        rr_value = 0.0

    strong_rejected_candidate = (
        score_value >= REJECTED_CANDIDATE_TELEGRAM_MIN_SCORE
        or rr_value >= REJECTED_CANDIDATE_TELEGRAM_MIN_RR
    )

    if not strong_rejected_candidate:
        return

    now_ts = time.time()
    cooldown_seconds = (
        REJECTED_CANDIDATE_TELEGRAM_COOLDOWN_MINUTES
        * 60
    )

    alert_key = (
        strategy,
        signal,
        entry_model,
        session_name,
        market_condition,
        reason,
    )

    last_sent_ts = (
        _REJECTED_CANDIDATE_TELEGRAM_CACHE.get(
            alert_key,
            0,
        )
    )

    if now_ts - last_sent_ts < cooldown_seconds:
        logger.info(
            "[REJECTED CANDIDATE] Telegram skipped by cooldown | "
            f"key={alert_key}"
        )
        return

    _REJECTED_CANDIDATE_TELEGRAM_CACHE[
        alert_key
    ] = now_ts

    (
        _rejected_context,
        rejected_rithmic_block,
        rejected_participation_block,
    ) = _directional_alert_context_blocks_fail_open(
        signal=signal,
    )

    message = (
        "📌 STRONG REJECTED CANDIDATE TRACKED\n"
        f"Setup ID: {setup_id}\n"
        f"Strategy: {strategy}\n"
        f"Signal: {signal}\n"
        f"Entry Model: {entry_model}\n"
        f"Session: {session_name}\n"
        f"Market: {market_condition}\n"
        f"Score: {score_value}\n"
        f"RR: {rr_value}\n\n"
        f"Entry: {entry}\n"
        f"SL: {sl}\n"
        f"{_format_telegram_tp123_from_levels(signal, entry, sl, tp)}\n\n"
        f"Reason: {reason}\n"
        "Action: tracked for promotion; execution only if RR and "
        "confirmation gate pass; low RR waits for better entry."
    )

    if rejected_rithmic_block:
        message = (
            rejected_rithmic_block
            + "\n--------------------------------\n\n"
            + message
        )

    if rejected_participation_block:
        message += (
            "\n\n"
            + rejected_participation_block
        )

    send_telegram_message_async(message)
'''

live_text = replace_function(
    live_text,
    "notify_rejected_candidate_if_relevant",
    new_strong_rejected,
)

# ============================================================
# 5. MTF conflict tracked candidate
# ============================================================

live_text = replace_once(
    live_text,
'''                mtf_participation_block = (
                    _market_participation_telegram_block_fail_open(
                        signal=signal,
                        tick=tick,
                    )
                )
''',
'''                (
                    _mtf_alert_context,
                    mtf_rithmic_block,
                    mtf_participation_block,
                ) = _directional_alert_context_blocks_fail_open(
                    signal=signal,
                    tick=tick,
                )
''',
    "MTF directional blocks",
)

live_text = replace_once(
    live_text,
'''                if mtf_entry_tp_block:
''',
'''                if mtf_rithmic_block:
                    mtf_message = (
                        mtf_rithmic_block
                        + "\\n--------------------------------\\n\\n"
                        + mtf_message
                    )

                if mtf_entry_tp_block:
''',
    "MTF Rithmic prepend",
)

# ============================================================
# 6. Generic Candidate Rejected
# ============================================================

live_text = replace_once(
    live_text,
'''                    rejected_participation_block = (
                        _market_participation_telegram_block_fail_open(
                            signal=(
                                candidate.get(
                                    "signal"
                                )
                            ),
                            tick=tick,
                        )
                    )
''',
'''                    (
                        _generic_rejected_context,
                        rejected_rithmic_block,
                        rejected_participation_block,
                    ) = _directional_alert_context_blocks_fail_open(
                        signal=candidate.get("signal"),
                        tick=tick,
                    )
''',
    "generic rejected directional blocks",
)

live_text = replace_once(
    live_text,
'''                    if rejected_participation_block:
''',
'''                    if rejected_rithmic_block:
                        rejected_message = (
                            rejected_rithmic_block
                            + "\\n--------------------------------\\n\\n"
                            + rejected_message
                        )

                    if rejected_participation_block:
''',
    "generic rejected Rithmic prepend",
)

# ============================================================
# 7. Candidate Rejected — Low RR
# ============================================================

live_text = replace_once(
    live_text,
'''                    low_rr_participation_block = (
                        _market_participation_telegram_block_fail_open(
                            signal=candidate_signal,
                            tick=tick,
                        )
                    )
''',
'''                    (
                        _low_rr_alert_context,
                        low_rr_rithmic_block,
                        low_rr_participation_block,
                    ) = _directional_alert_context_blocks_fail_open(
                        signal=candidate_signal,
                        tick=tick,
                    )
''',
    "low RR directional blocks",
)

live_text = replace_once(
    live_text,
'''                    if low_rr_entry_tp_block:
''',
'''                    if low_rr_rithmic_block:
                        low_rr_message = (
                            low_rr_rithmic_block
                            + "\\n--------------------------------\\n\\n"
                            + low_rr_message
                        )

                    if low_rr_entry_tp_block:
''',
    "low RR Rithmic prepend",
)

# ============================================================
# 8. Candidate Recovery Invalidated
# ============================================================

old_invalidated = '''                send_telegram_message(
                    f"🛑 Candidate Recovery Invalidated\\n"
                    f"Symbol: {SYMBOL}\\n"
                    f"Strategy: {strategy_name}\\n"
                    f"Signal: {signal}\\n"
                    f"Setup ID: {setup_id}\\n"
                    f"Recovery ID: {recovery_id}\\n\\n"
                    f"Reason: {consumed_reason}\\n"
                    f"Current Price: {current_recovery_price}\\n"
                    f"Original TP: {signal_data.get('tp_reference') or signal_data.get('take_profit') or signal_data.get('tp')}\\n"
                    f"Original SL: {signal_data.get('sl_reference') or signal_data.get('stop_loss') or signal_data.get('sl')}"
                )
'''

new_invalidated = '''                (
                    _recovery_invalidated_context,
                    recovery_invalidated_rithmic_block,
                    recovery_invalidated_participation_block,
                ) = _directional_alert_context_blocks_fail_open(
                    signal=signal,
                )

                recovery_invalidated_message = (
                    f"🛑 Candidate Recovery Invalidated\\n"
                    f"Symbol: {SYMBOL}\\n"
                    f"Strategy: {strategy_name}\\n"
                    f"Signal: {signal}\\n"
                    f"Setup ID: {setup_id}\\n"
                    f"Recovery ID: {recovery_id}\\n\\n"
                    f"Reason: {consumed_reason}\\n"
                    f"Current Price: {current_recovery_price}\\n"
                    f"Original TP: {signal_data.get('tp_reference') or signal_data.get('take_profit') or signal_data.get('tp')}\\n"
                    f"Original SL: {signal_data.get('sl_reference') or signal_data.get('stop_loss') or signal_data.get('sl')}"
                )

                if recovery_invalidated_rithmic_block:
                    recovery_invalidated_message = (
                        recovery_invalidated_rithmic_block
                        + "\\n--------------------------------\\n\\n"
                        + recovery_invalidated_message
                    )

                if recovery_invalidated_participation_block:
                    recovery_invalidated_message += (
                        "\\n\\n"
                        + recovery_invalidated_participation_block
                    )

                send_telegram_message(
                    recovery_invalidated_message
                )
'''

live_text = replace_once(
    live_text,
    old_invalidated,
    new_invalidated,
    "candidate recovery invalidated",
)

# ============================================================
# 9. Low-RR recovery -> Better Entry Retry
# ============================================================

old_retry = '''                send_telegram_message(
                    f"⏳ Low RR Recovery Moved to Better Entry Retry\\n"
                    f"Symbol: {SYMBOL}\\n"
                    f"Strategy: {strategy_name}\\n"
                    f"Signal: {signal}\\n"
                    f"Setup ID: {setup_id}\\n"
                    f"RR: {rr_value} / Required: {min_rr}"
                )
'''

new_retry = '''                (
                    _recovery_retry_context,
                    recovery_retry_rithmic_block,
                    recovery_retry_participation_block,
                ) = _directional_alert_context_blocks_fail_open(
                    signal=signal,
                )

                recovery_retry_message = (
                    f"⏳ Low RR Recovery Moved to Better Entry Retry\\n"
                    f"Symbol: {SYMBOL}\\n"
                    f"Strategy: {strategy_name}\\n"
                    f"Signal: {signal}\\n"
                    f"Setup ID: {setup_id}\\n"
                    f"RR: {rr_value} / Required: {min_rr}"
                )

                if recovery_retry_rithmic_block:
                    recovery_retry_message = (
                        recovery_retry_rithmic_block
                        + "\\n--------------------------------\\n\\n"
                        + recovery_retry_message
                    )

                if recovery_retry_participation_block:
                    recovery_retry_message += (
                        "\\n\\n"
                        + recovery_retry_participation_block
                    )

                send_telegram_message(
                    recovery_retry_message
                )
'''

live_text = replace_once(
    live_text,
    old_retry,
    new_retry,
    "low RR recovery better-entry retry",
)

# ============================================================
# Write only after every assertion succeeded
# ============================================================

rithmic_path.write_text(
    rithmic_text,
    encoding="utf-8",
    newline="\n",
)

participation_path.write_text(
    participation_text,
    encoding="utf-8",
    newline="\n",
)

live_path.write_text(
    live_text,
    encoding="utf-8",
    newline="\n",
)

print("[PASS] Rithmic directional Telegram patch applied")
print(f"[BACKUP] {BACKUP}")
print("[CHANGED] src/rithmic_setup_verdict.py")
print("[CHANGED] src/market_participation_context.py")
print("[CHANGED] src/live_bot.py")
print("[NOTE] Intrabar/Micro Momentum fast lane was not modified")
print("[NOTE] Rithmic remains OBSERVE ONLY / zero execution authority")
