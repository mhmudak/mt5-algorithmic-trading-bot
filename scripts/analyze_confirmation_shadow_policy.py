import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


try:
    from src.confirmation_shadow_policy import classify_confirmation_shadow_decision
except Exception:
    classify_confirmation_shadow_decision = None


def read_json(path, default=None):
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


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def boolish(value):
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    if isinstance(value, (int, float)):
        return value != 0

    text = str(value).strip().upper()

    return text in {"1", "TRUE", "YES", "Y", "TP", "SL", "HIT", "WIN", "LOSS"}


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
        "observations_file": source_dir / "confirmation_observations.jsonl",
        "outcomes_file": source_dir / "setup_outcomes.json",
        "shadow_rows_csv": output_dir / "confirmation_shadow_observations.csv",
        "decision_perf_csv": output_dir / "confirmation_shadow_decision_performance.csv",
        "strategy_bucket_perf_csv": output_dir / "confirmation_shadow_strategy_bucket_performance.csv",
        "report_json": output_dir / "phase2_shadow_policy_report.json",
    }


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


def get_modules(row):
    for key in ["modules", "results", "module_results"]:
        value = row.get(key)

        if isinstance(value, list):
            return value

    report = row.get("report") or row.get("confirmation_report") or {}

    if isinstance(report, dict):
        for key in ["results", "modules"]:
            value = report.get(key)

            if isinstance(value, list):
                return value

    return []


def build_report_from_observation(row):
    return {
        "approved": row.get("approved"),
        "confidence": row.get("confidence"),
        "score_delta": row.get("score_delta"),
        "fail_count": row.get("fail_count"),
        "error_count": row.get("error_count"),
        "required_failed_modules": row.get("required_failed_modules") or row.get("required_failed") or [],
        "optional_failed_modules": row.get("optional_failed_modules") or row.get("optional_failed") or [],
        "results": get_modules(row),
    }


def get_shadow(row):
    if row.get("shadow_decision"):
        return {
            "shadow_decision": row.get("shadow_decision"),
            "shadow_action": row.get("shadow_action"),
            "shadow_score": row.get("shadow_score"),
            "shadow_reason": row.get("shadow_reason"),
            "shadow_policy_version": row.get("shadow_policy_version"),
            "shadow_backfilled": False,
        }

    if classify_confirmation_shadow_decision:
        shadow = classify_confirmation_shadow_decision(build_report_from_observation(row))
        shadow["shadow_backfilled"] = True
        return shadow

    return {
        "shadow_decision": "UNKNOWN",
        "shadow_action": "OBSERVE_ONLY",
        "shadow_score": None,
        "shadow_reason": "Shadow policy module unavailable.",
        "shadow_policy_version": None,
        "shadow_backfilled": True,
    }


def normalize_outcome(row):
    outcome_text = str(
        row.get("outcome")
        or row.get("final_outcome")
        or row.get("result")
        or row.get("status")
        or ""
    ).upper()

    tp_hit = (
        boolish(row.get("tp_hit"))
        or boolish(row.get("hit_tp"))
        or "TP" in outcome_text
        or "WIN" in outcome_text
    )

    sl_hit = (
        boolish(row.get("sl_hit"))
        or boolish(row.get("hit_sl"))
        or "SL" in outcome_text
        or "LOSS" in outcome_text
    )

    w10_hit = (
        boolish(row.get("w10_hit"))
        or boolish(row.get("w10"))
        or boolish(row.get("moved_10"))
        or safe_float(row.get("max_favorable_pips"), 0.0) >= 10
    )

    breakeven = (
        boolish(row.get("breakeven"))
        or "BREAKEVEN" in outcome_text
        or "BE" == outcome_text.strip()
    )

    known = tp_hit or sl_hit or w10_hit or breakeven or outcome_text in {
        "TP",
        "SL",
        "WIN",
        "LOSS",
        "BREAKEVEN",
        "BE",
        "CLOSED",
    }

    if tp_hit:
        label = "TP"
    elif sl_hit:
        label = "SL"
    elif breakeven:
        label = "BREAKEVEN"
    elif w10_hit:
        label = "W10_ONLY"
    elif known:
        label = outcome_text or "KNOWN"
    else:
        label = "UNKNOWN"

    return {
        "known_outcome": known,
        "outcome_label": label,
        "tp_hit": tp_hit,
        "sl_hit": sl_hit,
        "w10_hit": w10_hit,
        "breakeven": breakeven,
        "max_favorable": safe_float(
            row.get("max_favorable")
            or row.get("max_favorable_pips")
            or row.get("max_favorable_move"),
            0.0,
        ),
        "max_adverse": safe_float(
            row.get("max_adverse")
            or row.get("max_adverse_pips")
            or row.get("max_adverse_move"),
            0.0,
        ),
    }


def load_outcomes_by_setup_id(path):
    rows = as_list(read_json(path, default=[]))
    by_id = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        setup_id = row.get("setup_id")

        if not setup_id:
            continue

        by_id[str(setup_id)] = {
            **normalize_outcome(row),
            "raw_outcome": row,
        }

    return by_id


def normalize_observations(rows, outcomes_by_id):
    normalized = []

    for row in rows:
        if row.get("_parse_error"):
            continue

        setup_id = row.get("setup_id")
        strategy = row.get("strategy") or "UNKNOWN"
        signal = row.get("signal") or "UNKNOWN"
        bucket = row.get("setup_source_bucket") or row.get("execution_bucket") or "UNKNOWN"

        shadow = get_shadow(row)
        outcome = outcomes_by_id.get(str(setup_id), {})

        modules = get_modules(row)

        normalized.append({
            "line_no": row.get("_line_no"),
            "created_at": row.get("created_at"),
            "setup_id": setup_id,
            "strategy": strategy,
            "signal": signal,
            "bucket": bucket,
            "entry_model": row.get("entry_model"),
            "session": row.get("session"),
            "market_condition": row.get("market_condition"),
            "approved": row.get("approved"),
            "confidence": safe_float(row.get("confidence"), 0.0),
            "score_delta": safe_float(row.get("score_delta"), 0.0),
            "module_count": len(modules),
            "shadow_decision": shadow.get("shadow_decision"),
            "shadow_action": shadow.get("shadow_action"),
            "shadow_score": safe_float(shadow.get("shadow_score"), 0.0),
            "shadow_reason": shadow.get("shadow_reason"),
            "shadow_policy_version": shadow.get("shadow_policy_version"),
            "shadow_backfilled": shadow.get("shadow_backfilled"),
            "matched_outcome": bool(outcome),
            "known_outcome": outcome.get("known_outcome", False),
            "outcome_label": outcome.get("outcome_label", "UNKNOWN"),
            "tp_hit": outcome.get("tp_hit", False),
            "sl_hit": outcome.get("sl_hit", False),
            "w10_hit": outcome.get("w10_hit", False),
            "breakeven": outcome.get("breakeven", False),
            "max_favorable": outcome.get("max_favorable"),
            "max_adverse": outcome.get("max_adverse"),
        })

    return normalized


def aggregate(rows, group_fields, min_samples=5, min_known=10):
    groups = defaultdict(list)

    for row in rows:
        key = tuple(row.get(field) for field in group_fields)
        groups[key].append(row)

    output = []

    for key, items in groups.items():
        n = len(items)
        matched = sum(1 for x in items if x.get("matched_outcome"))
        known = sum(1 for x in items if x.get("known_outcome"))
        tp = sum(1 for x in items if x.get("tp_hit"))
        sl = sum(1 for x in items if x.get("sl_hit"))
        w10 = sum(1 for x in items if x.get("w10_hit"))
        be = sum(1 for x in items if x.get("breakeven"))

        avg_conf = round(sum(safe_float(x.get("confidence")) for x in items) / n, 3) if n else 0
        avg_delta = round(sum(safe_float(x.get("score_delta")) for x in items) / n, 3) if n else 0
        avg_shadow = round(sum(safe_float(x.get("shadow_score")) for x in items) / n, 3) if n else 0

        known_base = known if known else 0

        tp_rate = round(tp / known_base, 4) if known_base else None
        sl_rate = round(sl / known_base, 4) if known_base else None
        w10_rate = round(w10 / known_base, 4) if known_base else None

        row = {
            "group": "|".join(str(x) for x in key),
            "n": n,
            "matched_outcome_count": matched,
            "known_outcome_count": known,
            "tp_count": tp,
            "sl_count": sl,
            "w10_count": w10,
            "breakeven_count": be,
            "tp_rate": tp_rate,
            "sl_rate": sl_rate,
            "w10_rate": w10_rate,
            "avg_confidence": avg_conf,
            "avg_score_delta": avg_delta,
            "avg_shadow_score": avg_shadow,
        }

        for field, value in zip(group_fields, key):
            row[field] = value

        decision = str(row.get("shadow_decision", "")).upper()

        if n < min_samples:
            recommendation = "TRACK_MORE"
        elif known < min_known:
            recommendation = "SHADOW_ONLY_NEED_MORE_OUTCOMES"
        elif decision in {"HIGH_RISK", "BLOCK_CANDIDATE_OBSERVE_ONLY"} and sl_rate is not None and sl_rate >= 0.60:
            recommendation = "FUTURE_BLOCK_REVIEW_CANDIDATE"
        elif decision in {"CAUTION"} and sl_rate is not None and sl_rate >= 0.50:
            recommendation = "KEEP_CAUTION_LABEL"
        elif decision in {"STRONG_SUPPORT", "SUPPORT"} and w10_rate is not None and w10_rate >= 0.60 and (sl_rate is None or sl_rate <= 0.35):
            recommendation = "SUPPORT_LABEL_LOOKS_USEFUL"
        else:
            recommendation = "OBSERVE_MORE"

        row["recommendation"] = recommendation

        output.append(row)

    output.sort(
        key=lambda x: (
            str(x.get("shadow_decision", "")),
            -safe_int(x.get("n"), 0),
            -safe_float(x.get("avg_shadow_score"), 0.0),
        )
    )

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Phase 2A shadow confirmation policy labels."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--min-samples",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--min-known-outcomes",
        type=int,
        default=10,
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)
    paths["output_dir"].mkdir(parents=True, exist_ok=True)

    observations = read_jsonl(paths["observations_file"])
    outcomes_by_id = load_outcomes_by_setup_id(paths["outcomes_file"])

    rows = normalize_observations(observations, outcomes_by_id)

    decision_perf = aggregate(
        rows,
        ["shadow_decision"],
        min_samples=args.min_samples,
        min_known=args.min_known_outcomes,
    )

    strategy_bucket_perf = aggregate(
        rows,
        ["shadow_decision", "strategy", "bucket"],
        min_samples=args.min_samples,
        min_known=args.min_known_outcomes,
    )

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2B",
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "observation_count": len(rows),
        "matched_outcome_count": sum(1 for x in rows if x.get("matched_outcome")),
        "known_outcome_count": sum(1 for x in rows if x.get("known_outcome")),
        "shadow_backfilled_count": sum(1 for x in rows if x.get("shadow_backfilled")),
        "decision_performance": decision_perf,
        "top_strategy_bucket_performance": strategy_bucket_perf[:50],
        "generated_files": {
            "shadow_rows_csv": str(paths["shadow_rows_csv"]),
            "decision_perf_csv": str(paths["decision_perf_csv"]),
            "strategy_bucket_perf_csv": str(paths["strategy_bucket_perf_csv"]),
            "report_json": str(paths["report_json"]),
        },
        "notes": [
            "Phase 2B is analyzer-only.",
            "No trades are blocked.",
            "Old observations without shadow fields are backfilled using current Phase 2A policy.",
            "Blocking decisions require more known outcomes.",
        ],
    }

    write_csv(paths["shadow_rows_csv"], rows)
    write_csv(paths["decision_perf_csv"], decision_perf)
    write_csv(paths["strategy_bucket_perf_csv"], strategy_bucket_perf)
    write_json(paths["report_json"], report)

    print("[PHASE 2B SHADOW POLICY ANALYZER] done")
    print("observation_count =", report["observation_count"])
    print("matched_outcome_count =", report["matched_outcome_count"])
    print("known_outcome_count =", report["known_outcome_count"])
    print("shadow_backfilled_count =", report["shadow_backfilled_count"])
    print("shadow_rows_csv =", paths["shadow_rows_csv"])
    print("decision_perf_csv =", paths["decision_perf_csv"])
    print("strategy_bucket_perf_csv =", paths["strategy_bucket_perf_csv"])
    print("report =", paths["report_json"])

    if decision_perf:
        print()
        print("[DECISION PERFORMANCE]")
        for row in decision_perf:
            print(
                f"{row.get('shadow_decision')} | "
                f"n={row.get('n')} known={row.get('known_outcome_count')} "
                f"tp_rate={row.get('tp_rate')} sl_rate={row.get('sl_rate')} "
                f"w10_rate={row.get('w10_rate')} "
                f"rec={row.get('recommendation')}"
            )


if __name__ == "__main__":
    main()
