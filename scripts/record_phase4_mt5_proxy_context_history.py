import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

SOURCE_REPORT_PATH = INTEL_DIR / "phase4_mt5_proxy_context_report.json"
HISTORY_PATH = INTEL_DIR / "mt5_proxy_context_snapshots.jsonl"
LATEST_PATH = INTEL_DIR / "phase4_mt5_proxy_context_history_latest.json"
SUMMARY_PATH = INTEL_DIR / "phase4_mt5_proxy_context_history_summary.txt"


def load_json(path, default):
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def stable_fingerprint(context):
    profile = context.get("profile") or {}
    volume_context = context.get("volume_context") or {}
    candle_context = context.get("candle_context") or {}

    payload = {
        "symbol": context.get("symbol"),
        "timeframe": context.get("timeframe"),
        "available": context.get("available"),
        "status": context.get("status"),
        "data_quality": context.get("data_quality"),
        "price_vs_value_area": context.get("price_vs_value_area"),
        "poc": profile.get("poc"),
        "value_area_low": profile.get("value_area_low"),
        "value_area_high": profile.get("value_area_high"),
        "latest_tick_volume": volume_context.get("latest_tick_volume"),
        "tick_volume_zscore": volume_context.get("tick_volume_zscore"),
        "volume_state": volume_context.get("volume_state"),
        "latest_close": candle_context.get("latest_close"),
        "candle_direction": candle_context.get("candle_direction"),
    }

    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_last_snapshot():
    if not HISTORY_PATH.exists():
        return None

    try:
        lines = [line.strip() for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])
    except Exception:
        return None


def append_snapshot(snapshot):
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    source_report = load_json(SOURCE_REPORT_PATH, {})

    if not source_report:
        report = {
            "phase": "PHASE_4J_MT5_PROXY_CONTEXT_HISTORY",
            "mode": "OBSERVE_ONLY",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "history_action": "SKIPPED_SOURCE_REPORT_MISSING",
            "history_count": 0,
            "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
            "recommendation": "RUN_PHASE4_MT5_PROXY_CONTEXT_FIRST",
        }

        LATEST_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        lines = [
            "[PHASE 4J MT5 PROXY CONTEXT HISTORY]",
            f"updated_at = {report['updated_at']}",
            f"mode = {report['mode']}",
            f"history_action = {report['history_action']}",
            "",
            "[RECOMMENDATION]",
            report["recommendation"],
        ]

        SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        return

    context = source_report.get("context") or {}

    profile = context.get("profile") or {}
    volume_context = context.get("volume_context") or {}
    candle_context = context.get("candle_context") or {}

    snapshot = {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "OBSERVE_ONLY",
        "context_family": context.get("context_family"),
        "symbol": context.get("symbol"),
        "timeframe": context.get("timeframe"),
        "available": context.get("available"),
        "status": context.get("status"),
        "is_real_order_flow": context.get("is_real_order_flow"),
        "data_quality": context.get("data_quality"),
        "decision_impact": context.get("decision_impact"),
        "price_vs_value_area": context.get("price_vs_value_area"),
        "profile": {
            "poc": profile.get("poc"),
            "value_area_low": profile.get("value_area_low"),
            "value_area_high": profile.get("value_area_high"),
            "total_tick_volume": profile.get("total_tick_volume"),
            "bin_size": profile.get("bin_size"),
        },
        "volume_context": volume_context,
        "candle_context": candle_context,
        "warning": context.get("warning"),
    }

    snapshot["fingerprint"] = stable_fingerprint(context)

    last_snapshot = read_last_snapshot()
    last_fingerprint = last_snapshot.get("fingerprint") if isinstance(last_snapshot, dict) else None

    if snapshot["fingerprint"] != last_fingerprint:
        append_snapshot(snapshot)
        history_action = "APPENDED"
    else:
        history_action = "SKIPPED_DUPLICATE"

    history_count = 0
    if HISTORY_PATH.exists():
        history_count = len([line for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()])

    report = {
        "phase": "PHASE_4J_MT5_PROXY_CONTEXT_HISTORY",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "history_action": history_action,
        "history_count": history_count,
        "latest_snapshot": snapshot,
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": "MT5_PROXY_CONTEXT_HISTORY_AVAILABLE_FOR_RESEARCH_ONLY",
    }

    LATEST_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 4J MT5 PROXY CONTEXT HISTORY]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"history_action = {history_action}",
        f"history_count = {history_count}",
        "",
        "[LATEST SNAPSHOT]",
        f"available = {snapshot.get('available')}",
        f"status = {snapshot.get('status')}",
        f"is_real_order_flow = {snapshot.get('is_real_order_flow')}",
        f"data_quality = {snapshot.get('data_quality')}",
        f"decision_impact = {snapshot.get('decision_impact')}",
        f"price_vs_value_area = {snapshot.get('price_vs_value_area')}",
        f"poc = {snapshot['profile'].get('poc')}",
        f"value_area_low = {snapshot['profile'].get('value_area_low')}",
        f"value_area_high = {snapshot['profile'].get('value_area_high')}",
        f"volume_state = {volume_context.get('volume_state')}",
        f"tick_volume_zscore = {volume_context.get('tick_volume_zscore')}",
        f"latest_close = {candle_context.get('latest_close')}",
        f"candle_direction = {candle_context.get('candle_direction')}",
        "",
        "[WARNING]",
        str(snapshot.get("warning")),
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nlatest = {LATEST_PATH}")
    print(f"history = {HISTORY_PATH}")
    print(f"summary = {SUMMARY_PATH}")


if __name__ == "__main__":
    main()