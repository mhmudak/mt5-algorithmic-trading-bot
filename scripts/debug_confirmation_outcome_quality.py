import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_json(path, default=None):
    path = Path(path)

    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path):
    path = Path(path)

    if not path.exists():
        return []

    rows = []

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                row = json.loads(line)
                row["_line_no"] = line_no
                rows.append(row)
            except Exception as exc:
                rows.append({
                    "_line_no": line_no,
                    "_parse_error": str(exc),
                    "_raw": line[:500],
                })

    return rows


def read_csv(path):
    path = Path(path)

    if not path.exists():
        return []

    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)

    return path


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = rows or []
    headers = []

    for row in rows:
        for key in row.keys():
            if key not in headers:
                headers.append(key)

    with path.open("w", encoding="utf-8", newline="") as f:
        if not headers:
            f.write("")
            return path

        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()

        for row in rows:
            safe = {}

            for key in headers:
                value = row.get(key)

                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False, sort_keys=True)

                safe[key] = value

            writer.writerow(safe)

    return path


def as_list(data):
    if data is None:
        return []

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        rows = []

        for key, value in data.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("setup_id", key)
                rows.append(row)

        return rows

    return []


def safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def safe_bool(value):
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    if isinstance(value, (int, float)):
        return value != 0

    text = str(value).strip().upper()

    return text in {"1", "TRUE", "YES", "Y", "TP", "SL", "WIN", "LOSS", "HIT"}


def resolve_paths(source_dir):
    source_dir = Path(source_dir)

    if not source_dir.is_absolute():
        source_dir = PROJECT_ROOT / source_dir

    account_name = source_dir.name
    output_dir = PROJECT_ROOT / "data" / "strategy_intelligence" / account_name

    return {
        "source_dir": source_dir,
        "account_name": account_name,
        "output_dir": output_dir,
        "setup_outcomes_file": source_dir / "setup_outcomes.json",
        "trades_file": source_dir / "trades.json",
        "observations_file": source_dir / "confirmation_observations.jsonl",
        "shadow_unique_csv": output_dir / "confirmation_shadow_unique_setups.csv",
        "outcome_quality_csv": output_dir / "confirmation_shadow_outcome_quality.csv",
        "debug_csv": output_dir / "confirmation_outcome_quality_debug.csv",
        "debug_json": output_dir / "confirmation_outcome_quality_debug.json",
    }


def index_by_setup_id(rows):
    index = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        setup_id = row.get("setup_id")

        if not setup_id:
            continue

        index.setdefault(str(setup_id), []).append(row)

    return index


def find_matching_trades(trades, setup_id):
    matches = []

    for trade in trades:
        if not isinstance(trade, dict):
            continue

        fields = [
            trade.get("setup_id"),
            trade.get("source_setup_id"),
            trade.get("origin_setup_id"),
            trade.get("signal_setup_id"),
            trade.get("comment"),
            trade.get("magic_comment"),
            trade.get("reason"),
        ]

        text_blob = " ".join(str(x) for x in fields if x is not None)

        if setup_id and setup_id in text_blob:
            matches.append(trade)

    return matches


def extract_outcome_flags(raw_outcome):
    text = str(
        raw_outcome.get("outcome")
        or raw_outcome.get("final_outcome")
        or raw_outcome.get("result")
        or raw_outcome.get("status")
        or ""
    ).upper()

    tp_hit = (
        safe_bool(raw_outcome.get("tp_hit"))
        or safe_bool(raw_outcome.get("hit_tp"))
        or "TP" in text
        or "WIN" in text
    )

    sl_hit = (
        safe_bool(raw_outcome.get("sl_hit"))
        or safe_bool(raw_outcome.get("hit_sl"))
        or "SL" in text
        or "LOSS" in text
    )

    w10_hit = (
        safe_bool(raw_outcome.get("w10_hit"))
        or safe_bool(raw_outcome.get("w10"))
        or safe_bool(raw_outcome.get("moved_10"))
        or safe_float(raw_outcome.get("max_favorable"), 0.0) >= 10
        or safe_float(raw_outcome.get("max_favorable_pips"), 0.0) >= 10
    )

    return {
        "outcome_text": text,
        "tp_hit": tp_hit,
        "sl_hit": sl_hit,
        "w10_hit": w10_hit,
        "mixed_tp_sl": tp_hit and sl_hit,
        "max_favorable": safe_float(
            raw_outcome.get("max_favorable")
            or raw_outcome.get("max_favorable_pips")
            or raw_outcome.get("max_favorable_move"),
            0.0,
        ),
        "max_adverse": safe_float(
            raw_outcome.get("max_adverse")
            or raw_outcome.get("max_adverse_pips")
            or raw_outcome.get("max_adverse_move"),
            0.0,
        ),
    }


def infer_quality_diagnosis(raw_outcome, matching_trades):
    flags = extract_outcome_flags(raw_outcome)
    notes = []

    diagnosis = "REVIEW_REQUIRED"

    if flags["mixed_tp_sl"]:
        notes.append("setup_outcome_marks_tp_and_sl_true")

    status = str(raw_outcome.get("status") or raw_outcome.get("final_outcome") or raw_outcome.get("outcome") or "").upper()

    if "OPEN" in status:
        notes.append("outcome_status_still_open_or_unfinalized")

    if "BREAKEVEN" in status or status == "BE":
        notes.append("outcome_status_breakeven")

    if matching_trades:
        closed = [
            t
            for t in matching_trades
            if str(t.get("status") or "").upper() in {"CLOSED", "TP", "SL", "BREAKEVEN"}
        ]

        if closed:
            notes.append("matching_closed_trade_found")
        else:
            notes.append("matching_trade_found_but_not_closed")

    else:
        notes.append("no_matching_trade_found_by_setup_id")

    if flags["mixed_tp_sl"]:
        diagnosis = "MIXED_TP_SL_AMBIGUOUS_EXCLUDE_FROM_CLEAN_STATS"

    return {
        "diagnosis": diagnosis,
        "diagnosis_notes": notes,
    }


def compact_raw(row):
    if not isinstance(row, dict):
        return {}

    wanted = [
        "setup_id",
        "strategy",
        "signal",
        "setup_source_bucket",
        "execution_bucket",
        "entry_model",
        "session",
        "market_condition",
        "decision",
        "decision_reason",
        "status",
        "outcome",
        "final_outcome",
        "result",
        "tp_hit",
        "sl_hit",
        "w10_hit",
        "breakeven",
        "max_favorable",
        "max_favorable_pips",
        "max_adverse",
        "max_adverse_pips",
        "entry",
        "sl",
        "tp",
        "entry_price",
        "stop_loss",
        "take_profit",
        "created_at",
        "updated_at",
        "closed_at",
        "reason",
    ]

    compact = {}

    for key in wanted:
        if key in row:
            compact[key] = row.get(key)

    extra = row.get("extra")

    if isinstance(extra, dict):
        compact["extra_keys"] = sorted(extra.keys())
        for key in ["source", "source_events", "execution_bucket", "rr", "required_rr"]:
            if key in extra:
                compact[f"extra_{key}"] = extra.get(key)

    return compact


def main():
    parser = argparse.ArgumentParser(
        description="Debug ambiguous confirmation outcome quality issues."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--setup-id",
        default=None,
        help="Optional specific setup_id to debug.",
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)

    setup_outcomes = as_list(load_json(paths["setup_outcomes_file"], default=[]))
    trades = as_list(load_json(paths["trades_file"], default=[]))
    observations = read_jsonl(paths["observations_file"])
    shadow_unique_rows = read_csv(paths["shadow_unique_csv"])
    quality_rows = read_csv(paths["outcome_quality_csv"])

    setup_outcomes_by_id = index_by_setup_id(setup_outcomes)
    observations_by_id = index_by_setup_id(observations)
    shadow_unique_by_id = index_by_setup_id(shadow_unique_rows)

    target_setup_ids = []

    if args.setup_id:
        target_setup_ids = [args.setup_id]
    else:
        for row in quality_rows:
            setup_id = row.get("setup_id")
            if setup_id:
                target_setup_ids.append(setup_id)

    target_setup_ids = sorted(set(target_setup_ids))

    debug_rows = []
    debug_details = []

    for setup_id in target_setup_ids:
        raw_outcome_rows = setup_outcomes_by_id.get(str(setup_id), [])
        raw_outcome = raw_outcome_rows[-1] if raw_outcome_rows else {}

        matching_observations = observations_by_id.get(str(setup_id), [])
        matching_shadow = shadow_unique_by_id.get(str(setup_id), [])
        matching_trades = find_matching_trades(trades, str(setup_id))

        outcome_flags = extract_outcome_flags(raw_outcome)
        diagnosis = infer_quality_diagnosis(raw_outcome, matching_trades)

        shadow = matching_shadow[-1] if matching_shadow else {}

        row = {
            "setup_id": setup_id,
            "strategy": raw_outcome.get("strategy") or shadow.get("strategy"),
            "signal": raw_outcome.get("signal") or shadow.get("signal"),
            "bucket": (
                raw_outcome.get("setup_source_bucket")
                or raw_outcome.get("execution_bucket")
                or shadow.get("bucket")
            ),
            "shadow_decision": shadow.get("shadow_decision"),
            "shadow_score": shadow.get("shadow_score"),
            "known_outcome": shadow.get("known_outcome"),
            "outcome_label": shadow.get("outcome_label"),
            "raw_outcome_rows_count": len(raw_outcome_rows),
            "matching_observation_count": len(matching_observations),
            "matching_trade_count": len(matching_trades),
            "outcome_text": outcome_flags["outcome_text"],
            "tp_hit": outcome_flags["tp_hit"],
            "sl_hit": outcome_flags["sl_hit"],
            "w10_hit": outcome_flags["w10_hit"],
            "mixed_tp_sl": outcome_flags["mixed_tp_sl"],
            "max_favorable": outcome_flags["max_favorable"],
            "max_adverse": outcome_flags["max_adverse"],
            "diagnosis": diagnosis["diagnosis"],
            "diagnosis_notes": diagnosis["diagnosis_notes"],
        }

        debug_rows.append(row)

        debug_details.append({
            **row,
            "raw_outcome_compact": compact_raw(raw_outcome),
            "raw_outcome_keys": sorted(raw_outcome.keys()) if isinstance(raw_outcome, dict) else [],
            "matching_shadow_row": matching_shadow[-1] if matching_shadow else None,
            "matching_observation_lines": [
                obs.get("_line_no")
                for obs in matching_observations
            ],
            "matching_observation_compact": [
                compact_raw(obs)
                for obs in matching_observations[-5:]
            ],
            "matching_trade_compact": [
                compact_raw(trade)
                for trade in matching_trades[-5:]
            ],
        })

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2F",
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "target_setup_count": len(target_setup_ids),
        "debugged_issue_count": len(debug_rows),
        "mixed_tp_sl_count": sum(1 for row in debug_rows if row.get("mixed_tp_sl")),
        "debug_rows": debug_rows,
        "debug_details": debug_details,
        "generated_files": {
            "debug_csv": str(paths["debug_csv"]),
            "debug_json": str(paths["debug_json"]),
        },
        "notes": [
            "This script does not modify setup_outcomes.json.",
            "Mixed TP/SL outcomes should remain excluded from clean shadow performance until reviewed.",
            "Use this report to decide whether the tracker or outcome classifier needs a future fix.",
        ],
    }

    write_csv(paths["debug_csv"], debug_rows)
    write_json(paths["debug_json"], report)

    print("[PHASE 2F OUTCOME QUALITY DEBUGGER] done")
    print("target_setup_count =", report["target_setup_count"])
    print("debugged_issue_count =", report["debugged_issue_count"])
    print("mixed_tp_sl_count =", report["mixed_tp_sl_count"])
    print("debug_csv =", paths["debug_csv"])
    print("debug_json =", paths["debug_json"])

    if debug_rows:
        print()
        print("[ISSUES]")
        for row in debug_rows:
            print(
                f"{row.get('setup_id')} | "
                f"{row.get('strategy')} | "
                f"tp={row.get('tp_hit')} sl={row.get('sl_hit')} "
                f"w10={row.get('w10_hit')} | "
                f"diagnosis={row.get('diagnosis')} | "
                f"notes={row.get('diagnosis_notes')}"
            )


if __name__ == "__main__":
    main()
