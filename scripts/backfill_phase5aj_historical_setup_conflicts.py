from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PHASE = "PHASE_5AJ_HISTORICAL_SETUP_CONFLICT_BACKFILL"

DEFAULT_ACCOUNT_DIR = ROOT / "data" / "accounts" / "Tickmill-Demo_25323531"
DEFAULT_INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

OUT_DIR = ROOT / "data" / "strategy_intelligence" / "phase5ah_setup_conflicts"
OUT_JSON = OUT_DIR / "phase5aj_historical_setup_conflicts.json"
OUT_JSONL = OUT_DIR / "phase5aj_historical_setup_conflicts.jsonl"
OUT_TXT = OUT_DIR / "phase5aj_historical_setup_conflicts_summary.txt"


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def load_json_any(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows = []

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append(dict(row))
    except Exception:
        return []

    return rows


def flatten_json_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]

    if isinstance(payload, dict):
        rows = []

        for key, value in payload.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("setup_id", key)
                rows.append(row)
            elif isinstance(value, list):
                rows.extend([x for x in value if isinstance(x, dict)])

        return rows

    return []


def pick(row: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        if key in row and row.get(key) not in [None, ""]:
            return row.get(key)
    return default


def normalize_direction(value: Any) -> str:
    text = safe_text(value).upper()
    if text in {"BUY", "LONG", "BULLISH"}:
        return "BUY"
    if text in {"SELL", "SHORT", "BEARISH"}:
        return "SELL"
    return ""


def parse_time(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value))
        except Exception:
            return None

    text = safe_text(value)
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1]

    candidates = [
        text,
        text.replace(" ", "T"),
    ]

    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            pass

    try:
        return datetime.fromtimestamp(float(text))
    except Exception:
        return None


def extract_created_at(row: dict[str, Any]) -> datetime | None:
    value = pick(
        row,
        [
            "created_at",
            "detected_at",
            "timestamp",
            "time",
            "event_time",
            "opened_at",
            "candidate_time",
            "tick_time",
        ],
    )

    parsed = parse_time(value)

    if parsed:
        return parsed

    epoch = pick(
        row,
        [
            "created_at_epoch",
            "detected_at_epoch",
            "time_epoch",
            "tick_time_epoch",
        ],
    )

    return parse_time(epoch)


def infer_family(row: dict[str, Any]) -> str:
    text = "|".join(
        [
            safe_text(row.get("strategy")),
            safe_text(row.get("entry_model")),
            safe_text(row.get("type")),
            safe_text(row.get("trigger")),
            safe_text(row.get("reason")),
            safe_text(row.get("rejection_reason")),
            safe_text(row.get("source_events")),
            safe_text(row.get("setup_source_bucket")),
        ]
    ).upper()

    if "MICRO_SR_SWEEP_RECLAIM" in text or "SWEEP_RECLAIM" in text:
        return "SWEEP_RECLAIM"

    if "FAILED_FVG_REVERSAL" in text or "FAILED_FVG" in text:
        return "FAILED_FVG_REVERSAL"

    if "KEY_LEVEL_BREAK_HOLD" in text or "BREAK_HOLD" in text:
        return "BREAK_HOLD"

    if "ORDER_BLOCK" in text or "MTF_OB" in text or "OB_ENTRY" in text:
        return "ORDER_BLOCK"

    if "PRO_TRADER_REPLICATION" in text:
        return "PRO_TRADER_REPLICATION"

    if "ORB" in text:
        return "ORB"

    if "INTRABAR" in text or "TICK_SNIPER" in text:
        return "INTRABAR"

    return safe_text(row.get("strategy")).upper() or "UNKNOWN"


def normalize_event(row: dict[str, Any], source: str) -> dict[str, Any] | None:
    strategy = safe_text(pick(row, ["strategy", "strategy_name"]))
    signal = normalize_direction(pick(row, ["signal", "direction", "side"]))

    entry = safe_float(
        pick(
            row,
            [
                "entry",
                "entry_price",
                "planned_entry",
                "price",
                "candidate_entry",
                "trade_entry",
            ],
        )
    )

    created_at_dt = extract_created_at(row)

    if not strategy or not signal or entry <= 0 or created_at_dt is None:
        return None

    reason = safe_text(
        pick(
            row,
            [
                "rejection_reason",
                "entry_skip_reason",
                "reason",
                "decision_reason",
                "source_events",
            ],
        )
    )

    state = safe_text(pick(row, ["state", "status", "setup_state"])).upper()

    reason_upper = reason.upper()

    if not state:
        if "M5_BODY_TOO_SMALL" in reason_upper:
            state = "ENTRY_SKIPPED_WEAK_CONFIRMATION"
        elif "SCORE_TOO_LOW" in reason_upper:
            state = "REJECTED_SCORE_TOO_LOW"
        elif "REJECTED_CANDIDATE_TRACKED" in reason_upper or "REJECTED" in reason_upper:
            state = "TRACKED_REJECTED_CANDIDATE"
        else:
            state = "SETUP_DETECTED"

    return {
        "source": source,
        "setup_id": safe_text(pick(row, ["setup_id", "source_setup_id", "candidate_setup_id", "executed_setup_id"])),
        "symbol": safe_text(pick(row, ["symbol"], "XAUUSD")).upper() or "XAUUSD",
        "strategy": strategy,
        "family": infer_family(row),
        "signal": signal,
        "direction": signal,
        "entry_model": safe_text(pick(row, ["entry_model"])),
        "session": safe_text(pick(row, ["session", "session_name"])),
        "market_condition": safe_text(pick(row, ["market_condition", "market"])),
        "score": safe_float(pick(row, ["score", "setup_score"])),
        "min_required_score": safe_float(pick(row, ["min_required_score", "required_score", "min_score"])),
        "entry": entry,
        "sl": safe_float(pick(row, ["sl", "stop_loss"])),
        "tp": safe_float(pick(row, ["tp", "take_profit"])),
        "rr": safe_float(pick(row, ["rr", "risk_reward", "rr_value", "rejected_rr_value"])),
        "state": state,
        "reason": reason,
        "rejection_reason": safe_text(pick(row, ["rejection_reason"])),
        "entry_skip_reason": safe_text(pick(row, ["entry_skip_reason"])),
        "created_at": created_at_dt.isoformat(timespec="seconds"),
        "created_at_epoch": created_at_dt.timestamp(),
        "raw_keys": sorted(row.keys()),
    }


def event_key(event: dict[str, Any]) -> str:
    return "|".join(
        [
            safe_text(event.get("setup_id")),
            safe_text(event.get("source")),
            safe_text(event.get("strategy")),
            safe_text(event.get("signal")),
            safe_text(event.get("entry")),
            safe_text(event.get("created_at")),
            safe_text(event.get("state")),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-dir", default=str(DEFAULT_ACCOUNT_DIR))
    parser.add_argument("--intel-dir", default=str(DEFAULT_INTEL_DIR))
    parser.add_argument("--max-minutes", type=int, default=30)
    parser.add_argument("--max-entry-distance", type=float, default=3.0)
    parser.add_argument("--min-conflict-rr", type=float, default=2.5)
    args = parser.parse_args()

    account_dir = Path(args.account_dir)
    intel_dir = Path(args.intel_dir)

    from src.setup_conflict_resolver import resolve_setup_conflict

    input_files = {
        "setup_outcomes": account_dir / "setup_outcomes.json",
        "trades": account_dir / "trades.json",
        "missed_profitable_rejected_candidates": intel_dir / "missed_profitable_rejected_candidates.csv",
        "setup_audit": account_dir / "setup_audit.json",
    }

    raw_rows = []

    setup_payload = load_json_any(input_files["setup_outcomes"], [])
    for row in flatten_json_records(setup_payload):
        raw_rows.append(("setup_outcomes", row))

    trade_payload = load_json_any(input_files["trades"], [])
    for row in flatten_json_records(trade_payload):
        raw_rows.append(("trades", row))

    missed_rows = load_csv_rows(input_files["missed_profitable_rejected_candidates"])
    for row in missed_rows:
        raw_rows.append(("missed_profitable_rejected_candidates", row))

    audit_payload = load_json_any(input_files["setup_audit"], [])
    for row in flatten_json_records(audit_payload):
        raw_rows.append(("setup_audit", row))

    events = []

    for source, row in raw_rows:
        event = normalize_event(row, source)
        if event:
            events.append(event)

    deduped = {}
    for event in events:
        deduped[event_key(event)] = event

    events = list(deduped.values())
    events.sort(key=lambda item: item["created_at_epoch"])

    conflicts = []

    for i, previous in enumerate(events):
        for new in events[i + 1 :]:
            time_gap = abs(float(new["created_at_epoch"]) - float(previous["created_at_epoch"])) / 60.0

            if time_gap > args.max_minutes:
                break

            if previous["symbol"] != new["symbol"]:
                continue

            report = resolve_setup_conflict(
                previous,
                new,
                max_minutes=args.max_minutes,
                max_entry_distance=args.max_entry_distance,
                min_conflict_rr=args.min_conflict_rr,
            )

            if not report.get("conflict_detected"):
                continue

            report["phase"] = PHASE
            report["historical_backfill"] = True
            report["symbol"] = previous["symbol"]
            report["previous_source"] = previous["source"]
            report["new_source"] = new["source"]
            report["previous_created_at"] = previous["created_at"]
            report["new_created_at"] = new["created_at"]
            conflicts.append(report)

    priority_conflicts = [item for item in conflicts if item.get("priority_conflict_review")]
    sweep_priority_conflicts = [
        item
        for item in priority_conflicts
        if (item.get("strategy_family_matrix") or {}).get("priority_family") == "SWEEP_RECLAIM"
    ]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "phase": PHASE,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "BACKFILL_AUDIT_ONLY",
        "decision_impact": "NONE",
        "execution_change": "NONE",
        "thresholds": {
            "max_minutes": args.max_minutes,
            "max_entry_distance": args.max_entry_distance,
            "min_conflict_rr": args.min_conflict_rr,
        },
        "inputs": {key: str(path) for key, path in input_files.items()},
        "raw_rows_scanned": len(raw_rows),
        "events_normalized": len(events),
        "conflict_count": len(conflicts),
        "priority_conflict_count": len(priority_conflicts),
        "sweep_priority_conflict_count": len(sweep_priority_conflicts),
        "top_priority_conflicts": priority_conflicts[-20:],
        "conflicts": conflicts,
        "recommendation": (
            "Use this as historical evidence only. Do not enable live decision influence until Phase5AI passes and samples are manually reviewed."
        ),
    }

    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    with OUT_JSONL.open("w", encoding="utf-8") as fh:
        for item in conflicts:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    lines = [
        "[PHASE 5AJ HISTORICAL SETUP CONFLICT BACKFILL]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"decision_impact = {report['decision_impact']}",
        f"execution_change = {report['execution_change']}",
        "",
        "[INPUTS]",
        *[f"{key} = {path}" for key, path in report["inputs"].items()],
        "",
        "[THRESHOLDS]",
        f"max_minutes = {args.max_minutes}",
        f"max_entry_distance = {args.max_entry_distance}",
        f"min_conflict_rr = {args.min_conflict_rr}",
        "",
        "[RESULTS]",
        f"raw_rows_scanned = {report['raw_rows_scanned']}",
        f"events_normalized = {report['events_normalized']}",
        f"conflict_count = {report['conflict_count']}",
        f"priority_conflict_count = {report['priority_conflict_count']}",
        f"sweep_priority_conflict_count = {report['sweep_priority_conflict_count']}",
        "",
        "[TOP PRIORITY CONFLICTS]",
    ]

    for item in priority_conflicts[-10:]:
        prev = item.get("previous_setup") or {}
        new = item.get("new_setup") or {}
        matrix = item.get("strategy_family_matrix") or {}
        metrics = item.get("conflict_metrics") or {}

        lines.append(
            f"- {item.get('previous_created_at')} -> {item.get('new_created_at')} | "
            f"{prev.get('strategy')} {prev.get('direction')} @ {prev.get('entry')} "
            f"vs {new.get('strategy')} {new.get('direction')} @ {new.get('entry')} | "
            f"pair={matrix.get('pair')} | priority={matrix.get('priority_side')} | "
            f"distance={metrics.get('entry_distance')}"
        )

    lines.extend(
        [
            "",
            "[RECOMMENDATION]",
            report["recommendation"],
            "",
            f"json = {OUT_JSON}",
            f"jsonl = {OUT_JSONL}",
            f"summary = {OUT_TXT}",
        ]
    )

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()