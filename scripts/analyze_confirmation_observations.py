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


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_bool(value, default=False):
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    text = str(value).strip().lower()

    if text in {"true", "yes", "y", "1", "hit", "success", "passed"}:
        return True

    if text in {"false", "no", "n", "0", "miss", "failed", "none", ""}:
        return False

    return default


def _safe_upper(value, default="UNKNOWN"):
    if value is None:
        return default

    text = str(value).strip()

    if not text:
        return default

    return text.upper()


def _json_safe(value):
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]

    try:
        if hasattr(value, "item"):
            return _json_safe(value.item())
    except Exception:
        pass

    return str(value)


def _csv_safe(value):
    value = _json_safe(value)

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    return value


def read_jsonl(path):
    path = Path(path)

    if not path.exists():
        return []

    records = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                records.append(json.loads(line))
            except Exception:
                continue

    return records


def read_json(path):
    path = Path(path)

    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(_json_safe(payload), f, indent=2, ensure_ascii=False, sort_keys=True)

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
            writer.writerow({key: _csv_safe(row.get(key)) for key in headers})

    return path


def resolve_default_account_dir():
    try:
        from src.account_context import get_account_file
        return Path(get_account_file("trades.json")).parent
    except Exception:
        pass

    fallback = PROJECT_ROOT / "data" / "accounts"

    if fallback.exists():
        candidates = [
            path
            for path in fallback.iterdir()
            if path.is_dir()
        ]

        if candidates:
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return candidates[0]

    return PROJECT_ROOT / "data" / "accounts"


def resolve_output_dir(source_dir, output_dir=None):
    if output_dir:
        return Path(output_dir)

    account_name = Path(source_dir).name

    return PROJECT_ROOT / "data" / "strategy_intelligence" / account_name


def extract_setup_id(record, fallback_key=None):
    if not isinstance(record, dict):
        return fallback_key

    for key in [
        "setup_id",
        "id",
        "candidate_setup_id",
        "source_setup_id",
        "executed_setup_id",
        "trade_setup_id",
    ]:
        value = record.get(key)

        if value:
            return str(value)

    return fallback_key


def iter_outcome_records(raw):
    if raw is None:
        return []

    records = []

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                setup_id = extract_setup_id(item)
                rec = dict(item)
                if setup_id:
                    rec.setdefault("setup_id", setup_id)
                records.append(rec)

        return records

    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, dict):
                rec = dict(value)
                rec.setdefault("setup_id", extract_setup_id(rec, fallback_key=key))
                records.append(rec)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        rec = dict(item)
                        rec.setdefault("setup_id", extract_setup_id(rec, fallback_key=key))
                        records.append(rec)

        return records

    return records


def first_existing(record, keys, default=None):
    for key in keys:
        if key in record and record.get(key) is not None:
            return record.get(key)

    return default


def normalize_outcome(record):
    record = record or {}

    text_parts = []

    for key in [
        "outcome",
        "final_outcome",
        "result",
        "status",
        "close_reason",
        "exit_reason",
        "hit_type",
        "label",
        "setup_outcome",
    ]:
        value = record.get(key)

        if value is not None:
            text_parts.append(str(value))

    outcome_text = " | ".join(text_parts).upper()

    tp_hit = (
        _safe_bool(first_existing(record, [
            "tp_hit",
            "hit_tp",
            "take_profit_hit",
            "reached_tp",
            "tp_reached",
        ], None), False)
        or "TAKE_PROFIT" in outcome_text
        or "TAKE PROFIT" in outcome_text
        or "TP_HIT" in outcome_text
        or outcome_text == "TP"
        or "| TP" in outcome_text
    )

    sl_hit = (
        _safe_bool(first_existing(record, [
            "sl_hit",
            "hit_sl",
            "stop_loss_hit",
            "reached_sl",
            "sl_reached",
        ], None), False)
        or "STOP_LOSS" in outcome_text
        or "STOP LOSS" in outcome_text
        or "SL_HIT" in outcome_text
        or outcome_text == "SL"
        or "| SL" in outcome_text
    )

    w10_hit = (
        _safe_bool(first_existing(record, [
            "w10_hit",
            "hit_w10",
            "w10_success",
            "reached_w10",
            "went_10",
            "move_10_hit",
        ], None), False)
        or "W10" in outcome_text
    )

    breakeven = (
        "BREAKEVEN" in outcome_text
        or "BREAK_EVEN" in outcome_text
        or outcome_text == "BE"
    )

    max_favorable = _safe_float(first_existing(record, [
        "max_favorable",
        "max_favorable_move",
        "max_favorable_points",
        "mfe",
        "max_profit",
    ], None))

    max_adverse = _safe_float(first_existing(record, [
        "max_adverse",
        "max_adverse_move",
        "max_adverse_points",
        "mae",
        "max_drawdown",
    ], None))

    if tp_hit:
        label = "TP"
    elif sl_hit:
        label = "SL"
    elif w10_hit:
        label = "W10_ONLY"
    elif breakeven:
        label = "BREAKEVEN"
    elif outcome_text:
        label = outcome_text[:80]
    else:
        label = "UNKNOWN"

    known = label != "UNKNOWN"

    return {
        "outcome_label": label,
        "tp_hit": tp_hit,
        "sl_hit": sl_hit,
        "w10_hit": w10_hit,
        "breakeven": breakeven,
        "max_favorable": max_favorable,
        "max_adverse": max_adverse,
        "known_outcome": known,
        "raw_outcome_text": outcome_text,
    }


def build_outcome_map(source_dir):
    source_dir = Path(source_dir)
    raw = read_json(source_dir / "setup_outcomes.json")
    records = iter_outcome_records(raw)

    outcome_map = {}

    for rec in records:
        setup_id = extract_setup_id(rec)

        if not setup_id:
            continue

        normalized = normalize_outcome(rec)
        outcome_map[str(setup_id)] = {
            **normalized,
            "raw_outcome": rec,
        }

    return outcome_map


def parse_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, str):
        text = value.strip()

        if not text:
            return []

        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

        return [
            item.strip()
            for item in text.split(",")
            if item.strip()
        ]

    return [value]


def join_observations_with_outcomes(observations, outcome_map):
    rows = []

    for obs in observations:
        setup_id = extract_setup_id(obs)
        outcome = outcome_map.get(str(setup_id), {}) if setup_id else {}

        row = {
            **obs,
            "matched_outcome": bool(outcome),
            "outcome_label": outcome.get("outcome_label", "UNKNOWN"),
            "tp_hit": outcome.get("tp_hit", False),
            "sl_hit": outcome.get("sl_hit", False),
            "w10_hit": outcome.get("w10_hit", False),
            "breakeven": outcome.get("breakeven", False),
            "known_outcome": outcome.get("known_outcome", False),
            "max_favorable": outcome.get("max_favorable"),
            "max_adverse": outcome.get("max_adverse"),
        }

        rows.append(row)

    return rows


def build_module_rows(joined_rows):
    module_rows = []

    for obs in joined_rows:
        modules = obs.get("modules") or []

        for item in modules:
            if not isinstance(item, dict):
                continue

            row = {
                "created_at": obs.get("created_at"),
                "setup_id": obs.get("setup_id"),
                "strategy": obs.get("strategy"),
                "signal": obs.get("signal"),
                "entry_model": obs.get("entry_model"),
                "setup_source_bucket": obs.get("setup_source_bucket"),
                "session": obs.get("session"),
                "market_condition": obs.get("market_condition"),
                "score": obs.get("score"),
                "entry": obs.get("entry"),
                "sl": obs.get("sl"),
                "tp": obs.get("tp"),
                "rr": obs.get("rr"),
                "module": item.get("module"),
                "module_status": item.get("status"),
                "module_confidence": item.get("confidence"),
                "module_score_delta": item.get("score_delta"),
                "module_required": item.get("required"),
                "module_source_type": item.get("source_type"),
                "module_reason": item.get("reason"),
                "matched_outcome": obs.get("matched_outcome"),
                "known_outcome": obs.get("known_outcome"),
                "outcome_label": obs.get("outcome_label"),
                "tp_hit": obs.get("tp_hit"),
                "sl_hit": obs.get("sl_hit"),
                "w10_hit": obs.get("w10_hit"),
                "breakeven": obs.get("breakeven"),
                "max_favorable": obs.get("max_favorable"),
                "max_adverse": obs.get("max_adverse"),
            }

            evidence = item.get("evidence") or {}

            if item.get("module") == "CONSOLIDATION_POLICY_AUDIT":
                row["policy_family"] = evidence.get("policy_family")
                row["risk_flags"] = evidence.get("risk_flags")
                row["support_flags"] = evidence.get("support_flags")
                row["mid_range"] = evidence.get("mid_range")
                row["edge_location_confirms"] = evidence.get("edge_location_confirms")
                row["sweep_confirms"] = evidence.get("sweep_confirms")
                row["bos_confirms"] = evidence.get("bos_confirms")
                row["volume_expansion"] = evidence.get("volume_expansion")

            if item.get("module") == "MT5_VOLUME_PROXY":
                row["relative_volume_ratio"] = evidence.get("relative_volume_ratio")
                row["volume_col"] = evidence.get("volume_col")

            module_rows.append(row)

    return module_rows


def rate(numerator, denominator):
    if denominator <= 0:
        return None

    return round(numerator / denominator, 4)


def recommend_module(row, min_samples):
    n = row.get("known_n", 0)
    avg_delta = row.get("avg_score_delta")
    sl_rate = row.get("sl_rate")
    tp_rate = row.get("tp_rate")
    w10_rate = row.get("w10_rate")
    module_status = row.get("module_status")

    if n < min_samples:
        return "TRACK_MORE"

    if module_status == "DISABLED":
        return "DATA_OR_PROVIDER_DISABLED"

    if avg_delta is not None and avg_delta <= -2:
        if sl_rate is not None and sl_rate >= 0.45:
            return "USE_AS_RISK_WARNING"
        if w10_rate is not None and w10_rate < 0.45:
            return "LIKELY_RISK_WARNING_TRACK_MORE"

    if avg_delta is not None and avg_delta >= 1:
        if tp_rate is not None and tp_rate >= 0.45:
            return "USE_AS_SUPPORT_SIGNAL"
        if w10_rate is not None and w10_rate >= 0.55:
            return "USE_AS_EARLY_SUPPORT_SIGNAL"

    return "OBSERVE_MORE"


def aggregate_module_performance(module_rows, min_samples=5):
    groups = defaultdict(list)

    for row in module_rows:
        key = (
            row.get("module"),
            row.get("module_status"),
            "NEGATIVE" if _safe_float(row.get("module_score_delta"), 0) < 0 else (
                "POSITIVE" if _safe_float(row.get("module_score_delta"), 0) > 0 else "NEUTRAL_DELTA"
            ),
            row.get("strategy"),
            row.get("market_condition"),
        )

        groups[key].append(row)

    output = []

    for key, rows in groups.items():
        module, status, delta_family, strategy, market_condition = key

        known_rows = [r for r in rows if _safe_bool(r.get("known_outcome"), False)]

        n = len(rows)
        known_n = len(known_rows)

        tp_count = sum(1 for r in known_rows if _safe_bool(r.get("tp_hit"), False))
        sl_count = sum(1 for r in known_rows if _safe_bool(r.get("sl_hit"), False))
        w10_count = sum(1 for r in known_rows if _safe_bool(r.get("w10_hit"), False))

        score_values = [
            _safe_float(r.get("module_score_delta"))
            for r in rows
            if _safe_float(r.get("module_score_delta")) is not None
        ]

        confidence_values = [
            _safe_float(r.get("module_confidence"))
            for r in rows
            if _safe_float(r.get("module_confidence")) is not None
        ]

        result = {
            "module": module,
            "module_status": status,
            "delta_family": delta_family,
            "strategy": strategy,
            "market_condition": market_condition,
            "n": n,
            "known_n": known_n,
            "tp_count": tp_count,
            "sl_count": sl_count,
            "w10_count": w10_count,
            "tp_rate": rate(tp_count, known_n),
            "sl_rate": rate(sl_count, known_n),
            "w10_rate": rate(w10_count, known_n),
            "avg_score_delta": round(sum(score_values) / len(score_values), 4) if score_values else None,
            "avg_confidence": round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else None,
            "min_samples": min_samples,
        }

        result["recommendation"] = recommend_module(result, min_samples)

        output.append(result)

    output.sort(
        key=lambda r: (
            r.get("recommendation") == "TRACK_MORE",
            -(r.get("known_n") or 0),
            r.get("module") or "",
        )
    )

    return output


def aggregate_risk_flag_performance(joined_rows, min_samples=5):
    groups = defaultdict(list)

    for obs in joined_rows:
        flags = parse_list(obs.get("consolidation_risk_flags"))

        if not flags:
            modules = obs.get("modules") or []

            for item in modules:
                if item.get("module") == "CONSOLIDATION_POLICY_AUDIT":
                    evidence = item.get("evidence") or {}
                    flags = parse_list(evidence.get("risk_flags"))
                    break

        for flag in flags:
            groups[str(flag)].append(obs)

    output = []

    for flag, rows in groups.items():
        known_rows = [r for r in rows if _safe_bool(r.get("known_outcome"), False)]

        known_n = len(known_rows)
        tp_count = sum(1 for r in known_rows if _safe_bool(r.get("tp_hit"), False))
        sl_count = sum(1 for r in known_rows if _safe_bool(r.get("sl_hit"), False))
        w10_count = sum(1 for r in known_rows if _safe_bool(r.get("w10_hit"), False))

        if known_n < min_samples:
            recommendation = "TRACK_MORE"
        elif sl_count / known_n >= 0.45:
            recommendation = "STRONG_RISK_FLAG"
        elif w10_count / known_n < 0.45:
            recommendation = "WEAK_FOLLOW_THROUGH_FLAG"
        else:
            recommendation = "OBSERVE_MORE"

        output.append({
            "risk_flag": flag,
            "n": len(rows),
            "known_n": known_n,
            "tp_count": tp_count,
            "sl_count": sl_count,
            "w10_count": w10_count,
            "tp_rate": rate(tp_count, known_n),
            "sl_rate": rate(sl_count, known_n),
            "w10_rate": rate(w10_count, known_n),
            "min_samples": min_samples,
            "recommendation": recommendation,
        })

    output.sort(key=lambda r: (r["recommendation"] == "TRACK_MORE", -(r["known_n"] or 0), r["risk_flag"]))

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Analyze confirmation-engine observations against setup outcomes."
    )

    parser.add_argument(
        "--source-dir",
        default=None,
        help="Account data directory containing confirmation_observations.jsonl and setup_outcomes.json.",
    )

    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for confirmation analysis reports.",
    )

    parser.add_argument(
        "--min-samples",
        type=int,
        default=5,
    )

    args = parser.parse_args()

    source_dir = Path(args.source_dir) if args.source_dir else resolve_default_account_dir()
    output_dir = resolve_output_dir(source_dir, args.output_dir)

    observations_file = source_dir / "confirmation_observations.jsonl"
    outcomes_file = source_dir / "setup_outcomes.json"

    observations = read_jsonl(observations_file)
    outcome_map = build_outcome_map(source_dir)

    joined_rows = join_observations_with_outcomes(observations, outcome_map)
    module_rows = build_module_rows(joined_rows)

    module_performance = aggregate_module_performance(
        module_rows,
        min_samples=args.min_samples,
    )

    risk_flag_performance = aggregate_risk_flag_performance(
        joined_rows,
        min_samples=args.min_samples,
    )

    summary = {
        "created_at": datetime.now().isoformat(),
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "observations_file": str(observations_file),
        "outcomes_file": str(outcomes_file),
        "observation_count": len(observations),
        "joined_observation_count": len(joined_rows),
        "module_row_count": len(module_rows),
        "outcome_count": len(outcome_map),
        "matched_outcome_count": sum(1 for r in joined_rows if r.get("matched_outcome")),
        "known_outcome_count": sum(1 for r in joined_rows if r.get("known_outcome")),
        "min_samples": args.min_samples,
        "generated_files": {
            "summary": str(output_dir / "confirmation_observation_summary.json"),
            "joined": str(output_dir / "confirmation_observations_joined.csv"),
            "module_performance": str(output_dir / "confirmation_module_performance.csv"),
            "risk_flag_performance": str(output_dir / "confirmation_risk_flag_performance.csv"),
        },
        "top_module_recommendations": module_performance[:20],
        "top_risk_flag_recommendations": risk_flag_performance[:20],
    }

    write_csv(output_dir / "confirmation_observations_joined.csv", joined_rows)
    write_csv(output_dir / "confirmation_module_rows.csv", module_rows)
    write_csv(output_dir / "confirmation_module_performance.csv", module_performance)
    write_csv(output_dir / "confirmation_risk_flag_performance.csv", risk_flag_performance)
    write_json(output_dir / "confirmation_observation_summary.json", summary)

    print("[CONFIRMATION ANALYZER] done")
    print("source_dir =", source_dir)
    print("output_dir =", output_dir)
    print("observation_count =", len(observations))
    print("matched_outcome_count =", summary["matched_outcome_count"])
    print("module_row_count =", len(module_rows))
    print("summary =", output_dir / "confirmation_observation_summary.json")
    print("module_performance =", output_dir / "confirmation_module_performance.csv")
    print("risk_flag_performance =", output_dir / "confirmation_risk_flag_performance.csv")


if __name__ == "__main__":
    main()
