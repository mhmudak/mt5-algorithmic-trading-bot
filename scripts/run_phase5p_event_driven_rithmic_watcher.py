from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ACCOUNT_NAME = "Tickmill-Demo_25323531"
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / ACCOUNT_NAME
ACCOUNT_DIR = ROOT / "data" / "accounts" / ACCOUNT_NAME
RITHMIC_DIR = ROOT / "data" / "order_flow" / "rithmic"

STATE_PATH = INTEL_DIR / "phase5p_event_driven_rithmic_watcher_state.json"
REPORT_PATH = INTEL_DIR / "phase5p_event_driven_rithmic_watcher_report.json"
SUMMARY_PATH = INTEL_DIR / "phase5p_event_driven_rithmic_watcher_summary.txt"

RITHMIC_QUALITY_PATH = RITHMIC_DIR / "phase5l_rithmic_data_quality_gate_report.json"

WATCH_FILES = [
    INTEL_DIR / "phase4_opportunity_alerts_report.json",
    INTEL_DIR / "phase3_decision_candidates_report.json",
    INTEL_DIR / "phase3_alerts_report.json",
    INTEL_DIR / "phase3_mtf_conflicts_report.json",
    INTEL_DIR / "phase3_low_rr_slippage_recovery_report.json",
    INTEL_DIR / "phase3_confirmation_patterns_report.json",
    INTEL_DIR / "phase3_mtf_conflict_report.json",
    ACCOUNT_DIR / "missed_profitable_rejected_candidates.csv",
    ACCOUNT_DIR / "rejected_candidates.csv",
]

EXCLUDED_RESEARCH_CODES = {
    "LIQUIDITY_POC_CONTEXT_SAMPLE_READY",
    "SESSION_POC_CONFIRMATION_SAMPLE_READY",
    "MTF_CONFLICT_SAMPLE_READY",
    "POC_CONTEXT_SAMPLE_READY",
    "PROXY_CONTEXT_CHANGED",
    "MT5_PROXY_CONTEXT_CHANGED",
}

EXCLUDED_STATUSES = {
    "NOT_READY",
    "NO_CASES_YET",
    "NOT_NEEDED_NOW",
    "OBSERVE_ONLY_NOT_DECISION_GRADE",
    "MONITOR_MORE",
    "NOT_CONNECTED",
}

VOLATILE_KEYS = {
    "updated_at",
    "created_at",
    "recorded_at",
    "timestamp",
    "last_checked_at",
    "last_sent_at",
    "generated_at",
    "report",
    "summary",
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): canonicalize(v)
            for k, v in sorted(value.items())
            if str(k).lower() not in VOLATILE_KEYS
        }

    if isinstance(value, list):
        return [canonicalize(v) for v in value[:50]]

    return value


def fingerprint_event(source: Path, event: dict[str, Any]) -> str:
    payload = {
        "source": str(source),
        "event": canonicalize(event),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def iter_json_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    if isinstance(value, dict):
        found.append(value)
        for child in value.values():
            found.extend(iter_json_dicts(child))

    elif isinstance(value, list):
        for child in value:
            found.extend(iter_json_dicts(child))

    return found


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
    except Exception:
        return []


def item_text(item: dict[str, Any]) -> str:
    return json.dumps(item, ensure_ascii=False, default=str).upper()


def value_upper(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None:
            return str(value).upper()
    return ""


def is_research_only(item: dict[str, Any]) -> bool:
    code = value_upper(item, "code", "event_code", "alert_code", "type")
    grade = value_upper(item, "grade")
    status = value_upper(item, "status", "state")

    if code in EXCLUDED_RESEARCH_CODES:
        return True

    if "SAMPLE_READY" in code:
        return True

    if grade in EXCLUDED_STATUSES or status in EXCLUDED_STATUSES:
        return True

    return False


def classify_event(item: dict[str, Any], source: Path) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    if is_research_only(item):
        return None

    text = item_text(item)

    has_direction = any(token in text for token in [
        '"BUY"',
        '"SELL"',
        "DIRECTION",
        "SIGNAL_SIDE",
        "TRADE_DIRECTION",
        "BUY ",
        "SELL ",
    ])

    has_trade_prices = any(token in text for token in [
        "ENTRY",
        "ENTRY_PRICE",
        "SL",
        "STOP_LOSS",
        "TP",
        "TAKE_PROFIT",
        "RR",
        "RISK_REWARD",
    ])

    has_setup_identity = any(token in text for token in [
        "SETUP_ID",
        "SETUP",
        "STRATEGY",
        "SIGNAL",
        "CANDIDATE",
        "SOURCE_BUCKET",
    ])

    is_rejected = any(token in text for token in [
        "REJECTED",
        "REJECTED_CANDIDATE",
        "REJECTED_LOW_RR",
        "LOW_RR",
        "WAIT_BETTER_ENTRY",
    ])

    is_mtf_conflict = "MTF_CONFLICT" in text

    # Strict rule:
    # Do not treat broad research/summary records as setup events.
    # A usable event must carry directional/trade-price evidence, or it is too vague for Telegram/manual decision context.
    is_real_setup = bool(has_direction and has_trade_prices and has_setup_identity)
    is_real_rejected = bool(is_rejected and has_setup_identity and (has_direction or has_trade_prices))
    is_real_mtf = bool(is_mtf_conflict and has_setup_identity and (has_direction or has_trade_prices) and not is_research_only(item))

    if not (is_real_setup or is_real_rejected or is_real_mtf):
        return None

    if is_real_rejected:
        event_type = "REJECTED_OR_WAIT_BETTER_ENTRY_CANDIDATE"
    elif is_real_mtf:
        event_type = "MTF_CONFLICT_ATTACHED_TO_SETUP"
    else:
        event_type = "SETUP_CANDIDATE"

    strategy = item.get("strategy") or item.get("strategy_name") or item.get("source_bucket")
    setup_id = item.get("setup_id") or item.get("id") or item.get("candidate_id") or item.get("recovery_id")
    direction = item.get("direction") or item.get("side") or item.get("signal_side") or item.get("trade_direction")
    entry = item.get("entry") or item.get("entry_price") or item.get("expected_entry")
    sl = item.get("sl") or item.get("stop_loss") or item.get("stop")
    tp = item.get("tp") or item.get("take_profit") or item.get("target")
    rr = item.get("rr") or item.get("risk_reward") or item.get("actual_rr") or item.get("required_rr")

    has_concrete_identity = bool(strategy or setup_id)
    has_explicit_direction = str(direction or "").upper() in {"BUY", "SELL"}
    has_price_or_rr_detail = bool(entry or sl or tp or rr)

    # Final safety filter:
    # Avoid Telegram/Rithmic refresh for vague report-level summaries.
    # A usable event needs concrete identity, explicit BUY/SELL direction,
    # and at least one price/RR detail.
    if not (has_concrete_identity and has_explicit_direction and has_price_or_rr_detail):
        return None

    summary = (
        item.get("message")
        or item.get("summary")
        or item.get("reason")
        or item.get("code")
        or item.get("status")
        or event_type
    )

    event = {
        "event_type": event_type,
        "source_file": str(source),
        "code": item.get("code") or item.get("event_code") or item.get("alert_code"),
        "status": item.get("status"),
        "grade": item.get("grade"),
        "strategy": strategy,
        "setup_id": setup_id,
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rr": rr,
        "summary": str(summary)[:500],
        "raw": item,
    }

    event["fingerprint"] = fingerprint_event(source, event)
    return event


def scan_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for path in WATCH_FILES:
        if not path.exists():
            continue

        if path.suffix.lower() == ".json":
            data = load_json(path, {})
            for item in iter_json_dicts(data):
                event = classify_event(item, path)
                if event:
                    events.append(event)

        elif path.suffix.lower() == ".csv":
            for row in read_csv_rows(path):
                event = classify_event(row, path)
                if event:
                    events.append(event)

    deduped: dict[str, dict[str, Any]] = {}
    for event in events:
        deduped[event["fingerprint"]] = event

    return list(deduped.values())


def run_command(name: str, cmd: list[str]) -> dict[str, Any]:
    started = time.time()

    result: dict[str, Any] = {
        "name": name,
        "cmd": cmd,
        "started_at": now_iso(),
        "success": False,
        "returncode": None,
        "duration_seconds": None,
        "stdout_tail": "",
        "stderr_tail": "",
    }

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        result["returncode"] = proc.returncode
        result["success"] = proc.returncode == 0
        result["stdout_tail"] = (proc.stdout or "")[-3000:]
        result["stderr_tail"] = (proc.stderr or "")[-3000:]

    except Exception as exc:
        result["returncode"] = "ERROR"
        result["success"] = False
        result["stderr_tail"] = repr(exc)

    result["duration_seconds"] = round(time.time() - started, 2)
    result["finished_at"] = now_iso()
    return result


def refresh_rithmic(args: argparse.Namespace) -> list[dict[str, Any]]:
    commands: list[tuple[str, list[str]]] = []

    refresh_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_phase5j_rithmic_manual_refresh_pipeline.py"),
        "--symbols",
        args.symbols,
        "--exchange",
        args.exchange,
        "--duration-seconds",
        str(args.duration_seconds),
    ]

    if args.include_order_book:
        refresh_cmd.append("--include-order-book")

    commands.append(("phase5j_rithmic_refresh", refresh_cmd))

    commands.append((
        "phase5l_rithmic_data_quality_gate",
        [
            sys.executable,
            str(ROOT / "scripts" / "check_phase5l_rithmic_data_quality_gate.py"),
            "--symbols",
            args.symbols,
            "--max-bbo-spread",
            str(args.max_bbo_spread),
            "--min-trades",
            str(args.min_trades),
            "--require-two-sided-dom",
        ],
    ))

    results = []

    for name, cmd in commands:
        print(f"[RUN] {name}")
        result = run_command(name, cmd)
        results.append(result)
        print(f"{name} | success={result['success']} | returncode={result['returncode']} | duration={result['duration_seconds']}")

    return results


def load_rithmic_quality() -> dict[str, Any]:
    quality = load_json(RITHMIC_QUALITY_PATH, {})
    if not quality:
        return {
            "overall_status": "RITHMIC_QUALITY_NOT_AVAILABLE",
            "all_quality_ok": False,
            "decision_impact": "NONE",
            "can_influence_decision": False,
            "validations": [],
        }
    return quality


def summarize_quality_for_message(quality: dict[str, Any]) -> list[str]:
    lines = [
        f"quality_status: {quality.get('overall_status')}",
        f"all_hard_ok: {quality.get('all_hard_ok')}",
        f"all_quality_ok: {quality.get('all_quality_ok')}",
        f"decision_impact: {quality.get('decision_impact', 'NONE')}",
        f"can_influence_decision: {quality.get('can_influence_decision', False)}",
    ]

    validations = quality.get("validations") or []

    if isinstance(validations, list):
        for item in validations[:4]:
            metrics = item.get("metrics") or {}
            lines += [
                f"- {item.get('symbol')}: {item.get('status')}",
                f"  failures: {item.get('quality_failures')}",
                f"  trades: {metrics.get('trade_count')} | spread: {metrics.get('spread')}",
                f"  DOM: {metrics.get('dom_available')} | bid_depth: {metrics.get('dom_bid_depth')} | ask_depth: {metrics.get('dom_ask_depth')}",
                f"  delta: {metrics.get('delta')} | cum_delta: {metrics.get('cumulative_delta')}",
            ]

    return lines


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def clean_direction(value: Any) -> str | None:
    direction = str(value or "").upper().strip()

    if direction in {"BUY", "LONG"}:
        return "BUY"

    if direction in {"SELL", "SHORT"}:
        return "SELL"

    return None


def get_primary_setup_direction(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        direction = clean_direction(event.get("direction"))

        if direction:
            return direction

        raw = event.get("raw")
        if isinstance(raw, dict):
            for key in ["direction", "side", "signal_side", "trade_direction"]:
                direction = clean_direction(raw.get(key))
                if direction:
                    return direction

    return None


def score_alignment_for_direction(direction: str, metrics: dict[str, Any]) -> tuple[int, int, list[str]]:
    support = 0
    against = 0
    evidence: list[str] = []

    delta = as_float(metrics.get("delta"))
    cumulative_delta = as_float(metrics.get("cumulative_delta"))
    dom_imbalance = metrics.get("dom_depth_imbalance")
    dom_imbalance_float = as_float(dom_imbalance) if dom_imbalance is not None else None
    bid_depth = as_float(metrics.get("dom_bid_depth"))
    ask_depth = as_float(metrics.get("dom_ask_depth"))

    if direction == "BUY":
        if delta > 0:
            support += 1
            evidence.append(f"delta positive supports BUY: {delta}")
        elif delta < 0:
            against += 1
            evidence.append(f"delta negative is against BUY: {delta}")

        if cumulative_delta > 0:
            support += 1
            evidence.append(f"cumulative_delta positive supports BUY: {cumulative_delta}")
        elif cumulative_delta < 0:
            against += 1
            evidence.append(f"cumulative_delta negative is against BUY: {cumulative_delta}")

        if dom_imbalance_float is not None:
            if dom_imbalance_float > 0.15:
                support += 1
                evidence.append(f"DOM bid-heavy supports BUY: {dom_imbalance_float}")
            elif dom_imbalance_float < -0.15:
                against += 1
                evidence.append(f"DOM ask-heavy is against BUY: {dom_imbalance_float}")

        if bid_depth > 0 or ask_depth > 0:
            if bid_depth > ask_depth:
                support += 1
                evidence.append(f"bid_depth > ask_depth supports BUY: {bid_depth} > {ask_depth}")
            elif ask_depth > bid_depth:
                against += 1
                evidence.append(f"ask_depth > bid_depth is against BUY: {ask_depth} > {bid_depth}")

    elif direction == "SELL":
        if delta < 0:
            support += 1
            evidence.append(f"delta negative supports SELL: {delta}")
        elif delta > 0:
            against += 1
            evidence.append(f"delta positive is against SELL: {delta}")

        if cumulative_delta < 0:
            support += 1
            evidence.append(f"cumulative_delta negative supports SELL: {cumulative_delta}")
        elif cumulative_delta > 0:
            against += 1
            evidence.append(f"cumulative_delta positive is against SELL: {cumulative_delta}")

        if dom_imbalance_float is not None:
            if dom_imbalance_float < -0.15:
                support += 1
                evidence.append(f"DOM ask-heavy supports SELL: {dom_imbalance_float}")
            elif dom_imbalance_float > 0.15:
                against += 1
                evidence.append(f"DOM bid-heavy is against SELL: {dom_imbalance_float}")

        if bid_depth > 0 or ask_depth > 0:
            if ask_depth > bid_depth:
                support += 1
                evidence.append(f"ask_depth > bid_depth supports SELL: {ask_depth} > {bid_depth}")
            elif bid_depth > ask_depth:
                against += 1
                evidence.append(f"bid_depth > ask_depth is against SELL: {bid_depth} > {ask_depth}")

    return support, against, evidence


def compute_rithmic_directional_alignment(
    events: list[dict[str, Any]],
    quality: dict[str, Any],
    *,
    quality_ok: bool,
) -> dict[str, Any]:
    setup_direction = get_primary_setup_direction(events)

    if not setup_direction:
        return {
            "setup_direction": None,
            "alignment": "NOT_AVAILABLE_NO_SETUP_DIRECTION",
            "supports_setup": False,
            "against_setup": False,
            "support_score": 0,
            "against_score": 0,
            "evidence": ["No explicit BUY/SELL setup direction found."],
        }

    if not quality_ok:
        return {
            "setup_direction": setup_direction,
            "alignment": "NOT_AVAILABLE_DATA_QUALITY_BAD",
            "supports_setup": False,
            "against_setup": False,
            "support_score": 0,
            "against_score": 0,
            "evidence": ["Rithmic data quality gate did not pass. Do not use Rithmic as confirmation."],
        }

    validations = quality.get("validations") or []
    support_score = 0
    against_score = 0
    evidence: list[str] = []

    if not isinstance(validations, list) or not validations:
        return {
            "setup_direction": setup_direction,
            "alignment": "NOT_AVAILABLE_NO_RITHMIC_VALIDATIONS",
            "supports_setup": False,
            "against_setup": False,
            "support_score": 0,
            "against_score": 0,
            "evidence": ["No Phase 5L validation metrics available."],
        }

    for item in validations:
        if not isinstance(item, dict):
            continue

        symbol = item.get("symbol")
        metrics = item.get("metrics") or {}

        s, a, ev = score_alignment_for_direction(setup_direction, metrics)
        support_score += s
        against_score += a

        for line in ev:
            evidence.append(f"{symbol}: {line}")

    if support_score >= 2 and support_score > against_score:
        alignment = f"SUPPORTS_{setup_direction}"
        supports_setup = True
        against_setup = False
    elif against_score >= 2 and against_score > support_score:
        alignment = f"AGAINST_{setup_direction}"
        supports_setup = False
        against_setup = True
    elif support_score == 0 and against_score == 0:
        alignment = "NEUTRAL_INSUFFICIENT_RITHMIC_EVIDENCE"
        supports_setup = False
        against_setup = False
    else:
        alignment = "NEUTRAL_OR_MIXED_RITHMIC_EVIDENCE"
        supports_setup = False
        against_setup = False

    return {
        "setup_direction": setup_direction,
        "alignment": alignment,
        "supports_setup": supports_setup,
        "against_setup": against_setup,
        "support_score": support_score,
        "against_score": against_score,
        "evidence": evidence[:12],
    }


def format_alignment_for_message(alignment: dict[str, Any]) -> list[str]:
    lines = [
        f"setup_direction: {alignment.get('setup_direction')}",
        f"rithmic_alignment: {alignment.get('alignment')}",
        f"rithmic_supports_setup: {alignment.get('supports_setup')}",
        f"rithmic_against_setup: {alignment.get('against_setup')}",
        f"support_score: {alignment.get('support_score')}",
        f"against_score: {alignment.get('against_score')}",
    ]

    evidence = alignment.get("evidence") or []

    if evidence:
        lines.append("evidence:")
        for line in evidence[:8]:
            lines.append(f"- {line}")

    return lines



def format_telegram_message(events: list[dict[str, Any]], quality: dict[str, Any]) -> str:
    quality_ok = quality.get("overall_status") == "RITHMIC_DATA_QUALITY_VALIDATED_OBSERVE_ONLY"
    alignment = compute_rithmic_directional_alignment(events, quality, quality_ok=quality_ok)

    if quality_ok:
        filter_result = "RITHMIC_CONTEXT_AVAILABLE_OBSERVE_ONLY"

        if alignment.get("supports_setup"):
            conclusion = "A real setup/review event was detected and Rithmic context supports the setup direction. Manual review only."
        elif alignment.get("against_setup"):
            conclusion = "A real setup/review event was detected, but Rithmic context is against the setup direction. Manual review only."
        else:
            conclusion = "A real setup/review event was detected and Rithmic quality passed, but directional evidence is neutral or mixed. Manual review only."
    else:
        filter_result = "BLOCKED_RITHMIC_DATA_QUALITY_BAD"
        conclusion = "A real setup/review event was detected, but Rithmic data quality is not reliable enough for confirmation."

    lines = [
        "🚨 EVENT-DETECTED RITHMIC FILTER — MANUAL REVIEW ONLY",
        "",
        "TRADE ACTION: NO AUTO TRADE",
        "MANUAL ACTION: REVIEW ONLY",
        "DECISION IMPACT: NONE",
        "CAN INFLUENCE DECISION: False",
        f"RITHMIC FILTER RESULT: {filter_result}",
        f"RITHMIC DIRECTIONAL ALIGNMENT: {alignment.get('alignment')}",
        f"RITHMIC SUPPORTS SETUP: {alignment.get('supports_setup')}",
        f"RITHMIC AGAINST SETUP: {alignment.get('against_setup')}",
        "",
        "[DETECTED EVENT]",
    ]

    for event in events[:3]:
        lines += [
            f"- event_type: {event.get('event_type')}",
            f"  source: {Path(str(event.get('source_file'))).name}",
            f"  code: {event.get('code')}",
            f"  status: {event.get('status')}",
            f"  grade: {event.get('grade')}",
            f"  strategy: {event.get('strategy')}",
            f"  setup_id: {event.get('setup_id')}",
            f"  direction: {event.get('direction')}",
            f"  entry: {event.get('entry')}",
            f"  sl: {event.get('sl')}",
            f"  tp: {event.get('tp')}",
            f"  rr: {event.get('rr')}",
            f"  summary: {event.get('summary')}",
        ]

    lines += [
        "",
        "[RITHMIC DIRECTIONAL ALIGNMENT]",
        *format_alignment_for_message(alignment),
        "",
        "[RITHMIC QUALITY]",
        *summarize_quality_for_message(quality),
        "",
        "[CONCLUSION]",
        conclusion,
        "",
        "Do not treat this as an automatic trade signal.",
    ]

    message = "\n".join(lines)

    if len(message) > 3900:
        message = message[:3850] + "\n\n[TRUNCATED] Open Phase 5P report for full details."

    return message


def send_telegram(message: str) -> dict[str, Any]:
    from src.notifier import send_telegram_message

    result = send_telegram_message(message)
    return {
        "ok": result is not False,
        "response": str(result)[:300],
    }


def run_cycle(args: argparse.Namespace) -> dict[str, Any]:
    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    state = load_json(STATE_PATH, {})

    seen = set(state.get("seen_fingerprints") or [])
    events = scan_events()
    new_events = [event for event in events if event["fingerprint"] not in seen]

    if args.prime_existing:
        seen.update(event["fingerprint"] for event in events)
        state["seen_fingerprints"] = sorted(seen)[-1000:]
        state["last_checked_at"] = now_iso()
        state["last_event_count"] = len(events)
        state["last_new_event_count"] = 0
        write_json(STATE_PATH, state)

        status = "PRIMED_EXISTING_EVENTS"
        results: list[dict[str, Any]] = []
        quality = load_rithmic_quality()
        telegram_sent = False

    elif not new_events and not args.force:
        status = "NO_NEW_REAL_EVENT"
        results = []
        quality = load_rithmic_quality()
        telegram_sent = False

    else:
        last_trigger_epoch = float(state.get("last_trigger_epoch") or 0)
        cooldown_remaining = args.cooldown_seconds - (time.time() - last_trigger_epoch)

        if cooldown_remaining > 0 and not args.force:
            status = "SKIPPED_COOLDOWN_ACTIVE"
            results = []
            quality = load_rithmic_quality()
            telegram_sent = False
        else:
            selected_events = new_events[: args.max_events] if new_events else events[: args.max_events]
            print(f"[TRIGGER] real event count = {len(selected_events)}")

            results = refresh_rithmic(args)
            quality = load_rithmic_quality()

            message = format_telegram_message(selected_events, quality)
            telegram_sent = False
            send_result = None

            if args.send_telegram:
                send_result = send_telegram(message)
                telegram_sent = bool(send_result.get("ok"))

            seen.update(event["fingerprint"] for event in selected_events)
            state["seen_fingerprints"] = sorted(seen)[-1000:]
            state["last_trigger_at"] = now_iso()
            state["last_trigger_epoch"] = time.time()
            state["last_send_result"] = send_result
            status = "TRIGGERED_RITHMIC_REFRESH"

    state["last_checked_at"] = now_iso()
    state["last_event_count"] = len(events)
    state["last_new_event_count"] = len(new_events)
    state["last_status"] = status
    state["last_rithmic_quality_status"] = quality.get("overall_status")
    write_json(STATE_PATH, state)

    report = {
        "phase": "PHASE_5P_EVENT_DRIVEN_RITHMIC_WATCHER",
        "mode": "OBSERVE_ONLY",
        "updated_at": now_iso(),
        "status": status,
        "event_count": len(events),
        "new_event_count": len(new_events),
        "send_telegram": args.send_telegram,
        "telegram_sent": telegram_sent,
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "trade_action": "NO_AUTO_TRADE",
        "manual_review_only": True,
        "rithmic_quality_status": quality.get("overall_status"),
        "events_preview": new_events[: args.max_events],
        "command_results": results,
        "recommendation": "Event-driven observe-only Rithmic filter. No live execution impact.",
    }

    write_json(REPORT_PATH, report)

    lines = [
        "[PHASE 5P EVENT-DRIVEN RITHMIC WATCHER]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"status = {status}",
        f"event_count = {len(events)}",
        f"new_event_count = {len(new_events)}",
        f"send_telegram = {args.send_telegram}",
        f"telegram_sent = {telegram_sent}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        f"trade_action = {report['trade_action']}",
        f"manual_review_only = {report['manual_review_only']}",
        f"rithmic_quality_status = {quality.get('overall_status')}",
        "",
        "[COMMANDS]",
    ]

    if results:
        for item in results:
            lines.append(
                f"{item['name']} | success={item['success']} | returncode={item['returncode']} | duration={item['duration_seconds']}"
            )
    else:
        lines.append("- No Rithmic refresh needed this cycle.")

    lines += [
        "",
        "[EVENTS PREVIEW]",
    ]

    if new_events:
        for event in new_events[: args.max_events]:
            lines += [
                f"- event_type = {event.get('event_type')}",
                f"  source = {Path(str(event.get('source_file'))).name}",
                f"  code = {event.get('code')}",
                f"  status = {event.get('status')}",
                f"  strategy = {event.get('strategy')}",
                f"  direction = {event.get('direction')}",
                f"  summary = {event.get('summary')}",
            ]
    else:
        lines.append("- No new real setup/review event detected.")

    lines += [
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nreport = {REPORT_PATH}")
    print(f"summary = {SUMMARY_PATH}")
    print(f"state = {STATE_PATH}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="GCQ6,MGCQ6")
    parser.add_argument("--exchange", default="COMEX")
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--include-order-book", action="store_true")
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--max-bbo-spread", type=float, default=5.0)
    parser.add_argument("--min-trades", type=int, default=5)
    parser.add_argument("--cooldown-seconds", type=int, default=300)
    parser.add_argument("--max-events", type=int, default=3)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--prime-existing", action="store_true")
    args = parser.parse_args()

    if args.interval_seconds < 30 and not args.once:
        raise SystemExit("[STOP] Use interval >= 30 seconds.")

    while True:
        started = time.time()
        run_cycle(args)

        if args.once:
            break

        elapsed = time.time() - started
        sleep_for = max(5, args.interval_seconds - elapsed)
        print(f"\n[SLEEP] next event scan in {round(sleep_for, 1)} seconds")
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()