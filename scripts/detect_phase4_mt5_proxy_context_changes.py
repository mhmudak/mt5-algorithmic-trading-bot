import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

HISTORY_PATH = INTEL_DIR / "mt5_proxy_context_snapshots.jsonl"
EVENTS_PATH = INTEL_DIR / "mt5_proxy_context_change_events.jsonl"
REPORT_PATH = INTEL_DIR / "phase4_mt5_proxy_context_changes_report.json"
SUMMARY_PATH = INTEL_DIR / "phase4_mt5_proxy_context_changes_summary.txt"


POC_MOVE_THRESHOLD = 1.00
VALUE_AREA_MOVE_THRESHOLD = 1.00
LATEST_CLOSE_MOVE_THRESHOLD = 2.00


def load_jsonl(path):
    if not path.exists():
        return []

    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue

    return rows


def append_jsonl(path, row):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def get_nested(data, *keys, default=None):
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def add_change(changes, code, message, evidence):
    changes.append({
        "change_type": "MT5_PROXY_CONTEXT_CHANGE",
        "code": code,
        "message": message,
        "evidence": evidence,
        "decision_impact": "NONE",
    })


def compare_number(changes, code, label, previous, current, threshold):
    prev = safe_float(previous)
    cur = safe_float(current)

    if prev is None or cur is None:
        return

    delta = round(cur - prev, 3)

    if abs(delta) >= threshold:
        add_change(
            changes,
            code,
            f"{label} changed by {delta}.",
            {
                "previous": prev,
                "current": cur,
                "delta": delta,
                "threshold": threshold,
            },
        )


def compare_state(changes, code, label, previous, current):
    if previous is None or current is None:
        return

    if previous != current:
        add_change(
            changes,
            code,
            f"{label} changed from {previous} to {current}.",
            {
                "previous": previous,
                "current": current,
            },
        )


def build_event_fingerprint(event):
    payload = {
        "previous_recorded_at": event.get("previous_recorded_at"),
        "current_recorded_at": event.get("current_recorded_at"),
        "changes": event.get("changes"),
    }

    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def summarize_event(event):
    if not isinstance(event, dict):
        return None

    changes = event.get("changes") or []
    current_context = event.get("current_context") or {}

    summary = {
        "recorded_at": event.get("event_recorded_at"),
        "change_count": event.get("change_count"),
        "previous_recorded_at": event.get("previous_recorded_at"),
        "current_recorded_at": event.get("current_recorded_at"),
        "current_poc": current_context.get("poc"),
        "current_value_area_low": current_context.get("value_area_low"),
        "current_value_area_high": current_context.get("value_area_high"),
        "current_latest_close": current_context.get("latest_close"),
        "current_volume_state": current_context.get("volume_state"),
        "current_price_vs_value_area": current_context.get("price_vs_value_area"),
        "changes": changes[:5],
        "decision_impact": "NONE",
    }

    return summary


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    history = load_jsonl(HISTORY_PATH)
    previous_snapshot = None
    current_snapshot = history[-1] if history else None
    changes = []

    if len(history) < 2:
        status = "NOT_ENOUGH_HISTORY"
        recommendation = "COLLECT_MORE_MT5_PROXY_CONTEXT_HISTORY"
    else:
        previous_snapshot = history[-2]
        current_snapshot = history[-1]

        compare_number(
            changes,
            "PROXY_POC_MOVED",
            "Proxy POC",
            get_nested(previous_snapshot, "profile", "poc"),
            get_nested(current_snapshot, "profile", "poc"),
            POC_MOVE_THRESHOLD,
        )

        compare_number(
            changes,
            "PROXY_VALUE_AREA_LOW_MOVED",
            "Proxy value area low",
            get_nested(previous_snapshot, "profile", "value_area_low"),
            get_nested(current_snapshot, "profile", "value_area_low"),
            VALUE_AREA_MOVE_THRESHOLD,
        )

        compare_number(
            changes,
            "PROXY_VALUE_AREA_HIGH_MOVED",
            "Proxy value area high",
            get_nested(previous_snapshot, "profile", "value_area_high"),
            get_nested(current_snapshot, "profile", "value_area_high"),
            VALUE_AREA_MOVE_THRESHOLD,
        )

        compare_number(
            changes,
            "LATEST_CLOSE_MOVED",
            "Latest close",
            get_nested(previous_snapshot, "candle_context", "latest_close"),
            get_nested(current_snapshot, "candle_context", "latest_close"),
            LATEST_CLOSE_MOVE_THRESHOLD,
        )

        compare_state(
            changes,
            "PRICE_VS_VALUE_AREA_CHANGED",
            "Price vs value area",
            previous_snapshot.get("price_vs_value_area"),
            current_snapshot.get("price_vs_value_area"),
        )

        compare_state(
            changes,
            "TICK_VOLUME_STATE_CHANGED",
            "Tick-volume state",
            get_nested(previous_snapshot, "volume_context", "volume_state"),
            get_nested(current_snapshot, "volume_context", "volume_state"),
        )

        compare_state(
            changes,
            "CANDLE_DIRECTION_CHANGED",
            "Candle direction",
            get_nested(previous_snapshot, "candle_context", "candle_direction"),
            get_nested(current_snapshot, "candle_context", "candle_direction"),
        )

        if changes:
            status = "PROXY_CONTEXT_CHANGED"
            recommendation = "REVIEW_MT5_PROXY_CONTEXT_CHANGES_RESEARCH_ONLY"
        else:
            status = "NO_CHANGE_DETECTED"
            recommendation = "CONTINUE_COLLECTING_MT5_PROXY_CONTEXT_HISTORY"

    current_context = {
        "available": current_snapshot.get("available") if isinstance(current_snapshot, dict) else None,
        "status": current_snapshot.get("status") if isinstance(current_snapshot, dict) else None,
        "is_real_order_flow": current_snapshot.get("is_real_order_flow") if isinstance(current_snapshot, dict) else None,
        "data_quality": current_snapshot.get("data_quality") if isinstance(current_snapshot, dict) else None,
        "decision_impact": current_snapshot.get("decision_impact") if isinstance(current_snapshot, dict) else None,
        "price_vs_value_area": current_snapshot.get("price_vs_value_area") if isinstance(current_snapshot, dict) else None,
        "poc": get_nested(current_snapshot, "profile", "poc") if isinstance(current_snapshot, dict) else None,
        "value_area_low": get_nested(current_snapshot, "profile", "value_area_low") if isinstance(current_snapshot, dict) else None,
        "value_area_high": get_nested(current_snapshot, "profile", "value_area_high") if isinstance(current_snapshot, dict) else None,
        "volume_state": get_nested(current_snapshot, "volume_context", "volume_state") if isinstance(current_snapshot, dict) else None,
        "tick_volume_zscore": get_nested(current_snapshot, "volume_context", "tick_volume_zscore") if isinstance(current_snapshot, dict) else None,
        "latest_close": get_nested(current_snapshot, "candle_context", "latest_close") if isinstance(current_snapshot, dict) else None,
        "candle_direction": get_nested(current_snapshot, "candle_context", "candle_direction") if isinstance(current_snapshot, dict) else None,
    }

    event_action = "NONE"

    existing_events = load_jsonl(EVENTS_PATH)

    if changes:
        event = {
            "event_type": "MT5_PROXY_CONTEXT_SIGNIFICANT_CHANGE",
            "event_recorded_at": datetime.now().isoformat(timespec="seconds"),
            "previous_recorded_at": previous_snapshot.get("recorded_at") if isinstance(previous_snapshot, dict) else None,
            "current_recorded_at": current_snapshot.get("recorded_at") if isinstance(current_snapshot, dict) else None,
            "change_count": len(changes),
            "changes": changes,
            "current_context": current_context,
            "decision_impact": "NONE",
            "warning": "MT5 proxy change only. Not real COMEX order flow and not a live trade signal.",
        }

        event["fingerprint"] = build_event_fingerprint(event)

        last_fingerprint = existing_events[-1].get("fingerprint") if existing_events else None

        if event["fingerprint"] != last_fingerprint:
            append_jsonl(EVENTS_PATH, event)
            existing_events.append(event)
            event_action = "APPENDED"
        else:
            event_action = "SKIPPED_DUPLICATE"

    latest_event = existing_events[-1] if existing_events else None
    latest_event_summary = summarize_event(latest_event)

    report = {
        "phase": "PHASE_4P_MT5_PROXY_CONTEXT_CHANGE_MEMORY",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "history_count": len(history),
        "change_count": len(changes),
        "changes": changes,
        "event_action": event_action,
        "significant_change_event_count": len(existing_events),
        "latest_significant_change_event": latest_event_summary,
        "previous_recorded_at": previous_snapshot.get("recorded_at") if isinstance(previous_snapshot, dict) else None,
        "current_recorded_at": current_snapshot.get("recorded_at") if isinstance(current_snapshot, dict) else None,
        "current_context": current_context,
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "warning": "MT5 proxy context changes are research-only and are not real COMEX order-flow changes.",
        "recommendation": recommendation,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 4P MT5 PROXY CONTEXT CHANGE MEMORY]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"status = {report['status']}",
        f"history_count = {report['history_count']}",
        f"change_count = {report['change_count']}",
        f"event_action = {report['event_action']}",
        f"significant_change_event_count = {report['significant_change_event_count']}",
        "",
        "[CURRENT CONTEXT]",
    ]

    for key, value in report["current_context"].items():
        lines.append(f"{key} = {value}")

    lines += [
        "",
        "[CURRENT CHANGES]",
    ]

    if changes:
        for change in changes:
            lines.append(f"{change['code']} | decision_impact={change['decision_impact']}")
            lines.append(f"  message: {change['message']}")
            lines.append(f"  evidence: {change['evidence']}")
    else:
        lines.append("No meaningful proxy context changes detected in the latest comparison.")

    lines += [
        "",
        "[LATEST SIGNIFICANT CHANGE EVENT]",
    ]

    if latest_event_summary:
        lines.append(f"recorded_at = {latest_event_summary.get('recorded_at')}")
        lines.append(f"change_count = {latest_event_summary.get('change_count')}")
        lines.append(f"current_poc = {latest_event_summary.get('current_poc')}")
        lines.append(f"current_value_area_low = {latest_event_summary.get('current_value_area_low')}")
        lines.append(f"current_value_area_high = {latest_event_summary.get('current_value_area_high')}")
        lines.append(f"current_latest_close = {latest_event_summary.get('current_latest_close')}")

        for item in latest_event_summary.get("changes", [])[:5]:
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            previous = evidence.get("previous")
            current = evidence.get("current")
            delta = evidence.get("delta")
            detail = f"{item.get('code')}: {previous} -> {current}"
            if delta is not None:
                detail += f" | delta = {delta}"
            lines.append(detail)
    else:
        lines.append("No significant proxy context change event recorded yet.")

    lines += [
        "",
        "[WARNING]",
        report["warning"],
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nreport = {REPORT_PATH}")
    print(f"events = {EVENTS_PATH}")
    print(f"summary = {SUMMARY_PATH}")


if __name__ == "__main__":
    main()