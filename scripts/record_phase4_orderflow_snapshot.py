import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

HISTORY_PATH = INTEL_DIR / "orderflow_snapshots.jsonl"
LATEST_PATH = INTEL_DIR / "phase4_orderflow_snapshot_latest.json"
SUMMARY_PATH = INTEL_DIR / "phase4_orderflow_snapshot_summary.txt"


def stable_fingerprint(snapshot):
    payload = {
        "provider": snapshot.get("provider"),
        "symbol": snapshot.get("symbol"),
        "available": snapshot.get("available"),
        "status": snapshot.get("status"),
        "data_quality": snapshot.get("data_quality"),
        "decision_impact": snapshot.get("decision_impact"),
        "metrics": snapshot.get("metrics"),
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--force-append", action="store_true")
    args = parser.parse_args()

    from src.order_flow_adapter import get_order_flow_snapshot

    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    snapshot = get_order_flow_snapshot(symbol=args.symbol)
    snapshot["recorded_at"] = datetime.now().isoformat(timespec="seconds")
    snapshot["fingerprint"] = stable_fingerprint(snapshot)

    last_snapshot = read_last_snapshot()
    last_fingerprint = last_snapshot.get("fingerprint") if isinstance(last_snapshot, dict) else None

    should_append = args.force_append or snapshot["fingerprint"] != last_fingerprint

    if should_append:
        append_snapshot(snapshot)
        history_action = "APPENDED"
    else:
        history_action = "SKIPPED_DUPLICATE"

    latest_report = {
        "phase": "PHASE_4B_ORDERFLOW_SNAPSHOT_HISTORY",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "history_action": history_action,
        "snapshot": snapshot,
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": (
            "CONNECT_REAL_COMEX_OR_FUTURES_DATA_PROVIDER_BEFORE_USING_ORDER_FLOW"
            if not snapshot.get("available")
            else "ORDER_FLOW_SNAPSHOT_AVAILABLE_OBSERVE_ONLY_REVIEW_REQUIRED"
        ),
    }

    LATEST_PATH.write_text(json.dumps(latest_report, indent=2, ensure_ascii=False), encoding="utf-8")

    history_count = 0
    if HISTORY_PATH.exists():
        history_count = len([line for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()])

    lines = [
        "[PHASE 4B ORDER-FLOW SNAPSHOT HISTORY]",
        f"updated_at = {latest_report['updated_at']}",
        f"mode = {latest_report['mode']}",
        f"history_action = {history_action}",
        f"history_count = {history_count}",
        "",
        "[SNAPSHOT]",
        f"provider = {snapshot.get('provider')}",
        f"symbol = {snapshot.get('symbol')}",
        f"available = {snapshot.get('available')}",
        f"status = {snapshot.get('status')}",
        f"data_quality = {snapshot.get('data_quality')}",
        f"decision_impact = {snapshot.get('decision_impact')}",
        "",
        "[WARNING]",
        str(snapshot.get("warning")),
        "",
        "[RECOMMENDATION]",
        latest_report["recommendation"],
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nlatest = {LATEST_PATH}")
    print(f"history = {HISTORY_PATH}")
    print(f"summary = {SUMMARY_PATH}")


if __name__ == "__main__":
    main()