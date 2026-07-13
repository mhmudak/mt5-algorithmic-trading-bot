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
        "unique_rows_csv": output_dir / "confirmation_shadow_unique_setups.csv",
        "decision_perf_csv": output_dir / "confirmation_shadow_decision_performance.csv",
        "decision_perf_unique_csv": output_dir / "confirmation_shadow_decision_performance_unique.csv",
        "strategy_bucket_perf_csv": output_dir / "confirmation_shadow_strategy_bucket_performance.csv",
        "strategy_bucket_perf_unique_csv": output_dir / "confirmation_shadow_strategy_bucket_performance_unique.csv",
        "outcome_quality_csv": output_dir / "confirmation_shadow_outcome_quality.csv",
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
        or safe_float(row.get("max_favorable"), 0.0) >= 10
    )

    breakeven = (
        boolish(row.get("breakeven"))
        or "BREAKEVEN" in outcome_text
        or "BE" == outcome_text.strip()
    )

    mixed_tp_sl = tp_hit and sl_hit

    known = tp_hit or sl_hit or w10_hit or breakeven or outcome_text in {
        "TP",
        "SL",
        "WIN",
        "LOSS",
        "BREAKEVEN",
        "BE",
        "CLOSED",
    }

    if mixed_tp_sl:
        label = "MIXED_TP_AND_SL"
    elif tp_hit:
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

    max_favorable = safe_float(
        row.get("max_favorable")
        or row.get("max_favorable_pips")
        or row.get("max_favorable_move"),
        0.0,
    )

    max_adverse = safe_float(
        row.get("max_adverse")
        or row.get("max_adverse_pips")
        or row.get("max_adverse_move"),
        0.0,
    )

    outcome_quality_flags = []

    if mixed_tp_sl:
        outcome_quality_flags.append("tp_and_sl_both_true")

    if known and label == "UNKNOWN":
        outcome_quality_flags.append("known_but_label_unknown")

    if w10_hit and not tp_hit and not sl_hit:
        outcome_quality_flags.append("w10_without_final_tp_sl")

    return {
        "known_outcome": known,
        "outcome_label": label,
        "tp_hit": tp_hit,
        "sl_hit": sl_hit,
        "w10_hit": w10_hit,
        "breakeven": breakeven,
        "mixed_tp_sl": mixed_tp_sl,
        "max_favorable": max_favorable,
        "max_adverse": max_adverse,
        "outcome_quality_flags": outcome_quality_flags,
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


def make_unique_key(row):
    setup_id = row.get("setup_id")

    if setup_id:
        return f"setup_id::{setup_id}"

    return "|".join([
        "fallback",
        str(row.get("strategy")),
        str(row.get("signal")),
        str(row.get("bucket")),
        str(row.get("entry")),
        str(row.get("created_at")),
    ])


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
            "unique_key": make_unique_key({
                "setup_id": setup_id,
                "strategy": strategy,
                "signal": signal,
                "bucket": bucket,
                "entry": row.get("entry"),
                "created_at": row.get("created_at"),
            }),
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
            "mixed_tp_sl": outcome.get("mixed_tp_sl", False),
            "max_favorable": outcome.get("max_favorable"),
            "max_adverse": outcome.get("max_adverse"),
            "outcome_quality_flags": outcome.get("outcome_quality_flags", []),
        })

    return normalized


def deduplicate_rows(rows):
    grouped = defaultdict(list)

    for row in rows:
        grouped[row.get("unique_key")].append(row)

    unique_rows = []

    for unique_key, items in grouped.items():
        # Keep the latest observation for the same setup, because it has the most recent shadow policy fields.
        items_sorted = sorted(items, key=lambda x: safe_int(x.get("line_no"), 0))
        latest = dict(items_sorted[-1])

        latest["duplicate_observation_count"] = len(items_sorted)
        latest["first_line_no"] = items_sorted[0].get("line_no")
        latest["last_line_no"] = items_sorted[-1].get("line_no")
        latest["dedupe_method"] = "latest_by_setup_id_or_fallback_key"

        unique_rows.append(latest)

    unique_rows.sort(key=lambda x: safe_int(x.get("last_line_no"), 0))

    return unique_rows


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
        mixed = sum(1 for x in items if x.get("mixed_tp_sl"))

        avg_conf = round(sum(safe_float(x.get("confidence")) for x in items) / n, 3) if n else 0
        avg_delta = round(sum(safe_float(x.get("score_delta")) for x in items) / n, 3) if n else 0
        avg_shadow = round(sum(safe_float(x.get("shadow_score")) for x in items) / n, 3) if n else 0

        known_base = known if known else 0

        tp_rate = round(tp / known_base, 4) if known_base else None
        sl_rate = round(sl / known_base, 4) if known_base else None
        w10_rate = round(w10 / known_base, 4) if known_base else None
        mixed_rate = round(mixed / known_base, 4) if known_base else None

        row = {
            "group": "|".join(str(x) for x in key),
            "n": n,
            "matched_outcome_count": matched,
            "known_outcome_count": known,
            "tp_count": tp,
            "sl_count": sl,
            "w10_count": w10,
            "breakeven_count": be,
            "mixed_tp_sl_count": mixed,
            "tp_rate": tp_rate,
            "sl_rate": sl_rate,
            "w10_rate": w10_rate,
            "mixed_tp_sl_rate": mixed_rate,
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
        elif mixed_rate is not None and mixed_rate >= 0.30:
            recommendation = "OUTCOME_DATA_AMBIGUOUS_REVIEW_FIRST"
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


def build_outcome_quality_rows(rows):
    output = []

    for row in rows:
        flags = row.get("outcome_quality_flags") or []

        if flags or row.get("mixed_tp_sl"):
            output.append({
                "setup_id": row.get("setup_id"),
                "strategy": row.get("strategy"),
                "signal": row.get("signal"),
                "bucket": row.get("bucket"),
                "shadow_decision": row.get("shadow_decision"),
                "known_outcome": row.get("known_outcome"),
                "outcome_label": row.get("outcome_label"),
                "tp_hit": row.get("tp_hit"),
                "sl_hit": row.get("sl_hit"),
                "w10_hit": row.get("w10_hit"),
                "mixed_tp_sl": row.get("mixed_tp_sl"),
                "flags": flags,
                "max_favorable": row.get("max_favorable"),
                "max_adverse": row.get("max_adverse"),
            })

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Phase 2A shadow confirmation policy labels with dedupe and outcome quality checks."
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
    unique_rows = deduplicate_rows(rows)

    decision_perf = aggregate(
        rows,
        ["shadow_decision"],
        min_samples=args.min_samples,
        min_known=args.min_known_outcomes,
    )

    decision_perf_unique = aggregate(
        unique_rows,
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

    strategy_bucket_perf_unique = aggregate(
        unique_rows,
        ["shadow_decision", "strategy", "bucket"],
        min_samples=args.min_samples,
        min_known=args.min_known_outcomes,
    )

    outcome_quality_rows = build_outcome_quality_rows(unique_rows)

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2C",
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "raw_observation_count": len(rows),
        "unique_setup_count": len(unique_rows),
        "duplicate_observation_count": max(0, len(rows) - len(unique_rows)),
        "matched_outcome_count_raw": sum(1 for x in rows if x.get("matched_outcome")),
        "known_outcome_count_raw": sum(1 for x in rows if x.get("known_outcome")),
        "matched_outcome_count_unique": sum(1 for x in unique_rows if x.get("matched_outcome")),
        "known_outcome_count_unique": sum(1 for x in unique_rows if x.get("known_outcome")),
        "mixed_tp_sl_count_unique": sum(1 for x in unique_rows if x.get("mixed_tp_sl")),
        "shadow_backfilled_count_raw": sum(1 for x in rows if x.get("shadow_backfilled")),
        "shadow_backfilled_count_unique": sum(1 for x in unique_rows if x.get("shadow_backfilled")),
        "decision_performance_raw": decision_perf,
        "decision_performance_unique": decision_perf_unique,
        "top_strategy_bucket_performance_raw": strategy_bucket_perf[:50],
        "top_strategy_bucket_performance_unique": strategy_bucket_perf_unique[:50],
        "outcome_quality_issue_count": len(outcome_quality_rows),
        "generated_files": {
            "shadow_rows_csv": str(paths["shadow_rows_csv"]),
            "unique_rows_csv": str(paths["unique_rows_csv"]),
            "decision_perf_csv": str(paths["decision_perf_csv"]),
            "decision_perf_unique_csv": str(paths["decision_perf_unique_csv"]),
            "strategy_bucket_perf_csv": str(paths["strategy_bucket_perf_csv"]),
            "strategy_bucket_perf_unique_csv": str(paths["strategy_bucket_perf_unique_csv"]),
            "outcome_quality_csv": str(paths["outcome_quality_csv"]),
            "report_json": str(paths["report_json"]),
        },
        "notes": [
            "Phase 2C is analyzer-only.",
            "No trades are blocked.",
            "Unique setup performance is more important than raw observation performance.",
            "If TP and SL are both true, the outcome is treated as mixed/ambiguous for future blocking decisions.",
            "Blocking decisions require more unique known outcomes.",
        ],
    }

    write_csv(paths["shadow_rows_csv"], rows)
    write_csv(paths["unique_rows_csv"], unique_rows)
    write_csv(paths["decision_perf_csv"], decision_perf)
    write_csv(paths["decision_perf_unique_csv"], decision_perf_unique)
    write_csv(paths["strategy_bucket_perf_csv"], strategy_bucket_perf)
    write_csv(paths["strategy_bucket_perf_unique_csv"], strategy_bucket_perf_unique)
    write_csv(paths["outcome_quality_csv"], outcome_quality_rows)
    write_json(paths["report_json"], report)

    print("[PHASE 2C SHADOW ANALYZER QUALITY] done")
    print("raw_observation_count =", report["raw_observation_count"])
    print("unique_setup_count =", report["unique_setup_count"])
    print("duplicate_observation_count =", report["duplicate_observation_count"])
    print("known_outcome_count_raw =", report["known_outcome_count_raw"])
    print("known_outcome_count_unique =", report["known_outcome_count_unique"])
    print("mixed_tp_sl_count_unique =", report["mixed_tp_sl_count_unique"])
    print("outcome_quality_issue_count =", report["outcome_quality_issue_count"])
    print("unique_rows_csv =", paths["unique_rows_csv"])
    print("decision_perf_unique_csv =", paths["decision_perf_unique_csv"])
    print("outcome_quality_csv =", paths["outcome_quality_csv"])
    print("report =", paths["report_json"])

    if decision_perf_unique:
        print()
        print("[UNIQUE DECISION PERFORMANCE]")
        for row in decision_perf_unique:
            print(
                f"{row.get('shadow_decision')} | "
                f"n={row.get('n')} known={row.get('known_outcome_count')} "
                f"tp_rate={row.get('tp_rate')} sl_rate={row.get('sl_rate')} "
                f"mixed={row.get('mixed_tp_sl_rate')} "
                f"rec={row.get('recommendation')}"
            )

    if outcome_quality_rows:
        print()
        print("[OUTCOME QUALITY ISSUES]")
        for row in outcome_quality_rows[:10]:
            print(
                f"{row.get('setup_id')} | "
                f"{row.get('strategy')} | "
                f"label={row.get('outcome_label')} | "
                f"flags={row.get('flags')}"
            )


if __name__ == "__main__":
    main()
