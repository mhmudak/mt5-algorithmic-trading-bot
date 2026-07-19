import hashlib
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

HISTORY_PATH = INTEL_DIR / "mt5_proxy_context_snapshots.jsonl"
CHANGE_REPORT_PATH = INTEL_DIR / "phase4_mt5_proxy_context_changes_report.json"
EVENTS_PATH = INTEL_DIR / "mt5_proxy_context_change_events.jsonl"
SUMMARY_PATH = INTEL_DIR / "phase4_mt5_proxy_context_change_events_summary.txt"

POC_MOVE_THRESHOLD = 1.00
VALUE_AREA_MOVE_THRESHOLD = 1.00
LATEST_CLOSE_MOVE_THRESHOLD = 2.00


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


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


def compare_snapshots(previous, current):
    changes = []

    compare_number(
        changes,
        "PROXY_POC_MOVED",
        "Proxy POC",
        get_nested(previous, "profile", "poc"),
        get_nested(current, "profile", "poc"),
        POC_MOVE_THRESHOLD,
    )

    compare_number(
        changes,
        "PROXY_VALUE_AREA_LOW_MOVED",
        "Proxy value area low",
        get_nested(previous, "profile", "value_area_low"),
        get_nested(current, "profile", "value_area_low"),
        VALUE_AREA_MOVE_THRESHOLD,
    )

    compare_number(
        changes,
        "PROXY_VALUE_AREA_HIGH_MOVED",
        "Proxy value area high",
        get_nested(previous, "profile", "value_area_high"),
        get_nested(current, "profile", "value_area_high"),
        VALUE_AREA_MOVE_THRESHOLD,
    )

    compare_number(
        changes,
        "LATEST_CLOSE_MOVED",
        "Latest close",
        get_nested(previous, "candle_context", "latest_close"),
        get_nested(current, "candle_context", "latest_close"),
        LATEST_CLOSE_MOVE_THRESHOLD,
    )

    compare_state(
        changes,
        "PRICE_VS_VALUE_AREA_CHANGED",
        "Price vs value area",
        previous.get("price_vs_value_area"),
        current.get("price_vs_value_area"),
    )

    compare_state(
        changes,
        "TICK_VOLUME_STATE_CHANGED",
        "Tick-volume state",
        get_nested(previous, "volume_context", "volume_state"),
        get_nested(current, "volume_context", "volume_state"),
    )

    compare_state(
        changes,
        "CANDLE_DIRECTION_CHANGED",
        "Candle direction",
        get_nested(previous, "candle_context", "candle_direction"),
        get_nested(current, "candle_context", "candle_direction"),
    )

    return changes


def current_context_from_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        return {}

    return {
        "available": snapshot.get("available"),
        "status": snapshot.get("status"),
        "is_real_order_flow": snapshot.get("is_real_order_flow"),
        "data_quality": snapshot.get("data_quality"),
        "decision_impact": snapshot.get("decision_impact"),
        "price_vs_value_area": snapshot.get("price_vs_value_area"),
        "poc": get_nested(snapshot, "profile", "poc"),
        "value_area_low": get_nested(snapshot, "profile", "value_area_low"),
        "value_area_high": get_nested(snapshot, "profile", "value_area_high"),
        "volume_state": get_nested(snapshot, "volume_context", "volume_state"),
        "tick_volume_zscore": get_nested(snapshot, "volume_context", "tick_volume_zscore"),
        "latest_close": get_nested(snapshot, "candle_context", "latest_close"),
        "candle_direction": get_nested(snapshot, "candle_context", "candle_direction"),
    }


def event_fingerprint(event):
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

    current_context = event.get("current_context") or {}

    return {
        "event_recorded_at": event.get("event_recorded_at"),
        "previous_recorded_at": event.get("previous_recorded_at"),
        "current_recorded_at": event.get("current_recorded_at"),
        "change_count": event.get("change_count"),
        "current_poc": current_context.get("poc"),
        "current_value_area_low": current_context.get("value_area_low"),
        "current_value_area_high": current_context.get("value_area_high"),
        "current_latest_close": current_context.get("latest_close"),
        "current_volume_state": current_context.get("volume_state"),
        "current_price_vs_value_area": current_context.get("price_vs_value_area"),
        "changes": event.get("changes", [])[:5],
        "decision_impact": "NONE",
    }


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    history = load_jsonl(HISTORY_PATH)
    events = load_jsonl(EVENTS_PATH)
    existing_fingerprints = {
        event.get("fingerprint")
        for event in events
        if isinstance(event, dict) and event.get("fingerprint")
    }

    new_event_count = 0

    for index in range(1, len(history)):
        previous = history[index - 1]
        current = history[index]

        changes = compare_snapshots(previous, current)

        if not changes:
            continue

        event = {
            "event_type": "MT5_PROXY_CONTEXT_SIGNIFICANT_CHANGE",
            "event_recorded_at": datetime.now().isoformat(timespec="seconds"),
            "previous_recorded_at": previous.get("recorded_at"),
            "current_recorded_at": current.get("recorded_at"),
            "change_count": len(changes),
            "changes": changes,
            "current_context": current_context_from_snapshot(current),
            "decision_impact": "NONE",
            "warning": "MT5 proxy change only. Not real COMEX order flow and not a live trade signal.",
        }

        event["fingerprint"] = event_fingerprint(event)

        if event["fingerprint"] in existing_fingerprints:
            continue

        append_jsonl(EVENTS_PATH, event)
        events.append(event)
        existing_fingerprints.add(event["fingerprint"])
        new_event_count += 1

    latest_event = events[-1] if events else None
    latest_event_summary = summarize_event(latest_event)

    change_report = load_json(CHANGE_REPORT_PATH, {})

    change_report["event_memory"] = {
        "enabled": True,
        "event_action": f"APPENDED_{new_event_count}" if new_event_count else "NONE",
        "new_event_count": new_event_count,
        "significant_change_event_count": len(events),
        "latest_significant_change_event": latest_event_summary,
        "decision_impact": "NONE",
        "warning": "Persistent memory is research-only. It does not influence live execution.",
    }

    change_report["event_action"] = change_report["event_memory"]["event_action"]
    change_report["significant_change_event_count"] = len(events)
    change_report["latest_significant_change_event"] = latest_event_summary

    write_json(CHANGE_REPORT_PATH, change_report)

    lines = [
        "[PHASE 4P MT5 PROXY CHANGE EVENT MEMORY]",
        f"updated_at = {datetime.now().isoformat(timespec='seconds')}",
        "mode = OBSERVE_ONLY",
        f"history_count = {len(history)}",
        f"new_event_count = {new_event_count}",
        f"significant_change_event_count = {len(events)}",
        f"event_action = {change_report['event_action']}",
        "",
        "[LATEST SIGNIFICANT CHANGE EVENT]",
    ]

    if latest_event_summary:
        lines.append(f"event_recorded_at = {latest_event_summary.get('event_recorded_at')}")
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
        lines.append("No significant proxy change event recorded yet.")

    lines += [
        "",
        "[WARNING]",
        "MT5 proxy change memory is research-only. It is not real COMEX order flow and not a live trade signal.",
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nevents = {EVENTS_PATH}")
    print(f"summary = {SUMMARY_PATH}")


if __name__ == "__main__":
    main()