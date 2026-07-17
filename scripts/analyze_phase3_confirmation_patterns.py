import json
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_DIR = ROOT / "data" / "accounts" / "Tickmill-Demo_25323531"
INTEL_DIR = ROOT / "data" / "strategy_intelligence" / "Tickmill-Demo_25323531"

BASELINE_PATH = INTEL_DIR / "phase3_baseline.json"
REPORT_PATH = INTEL_DIR / "phase3_confirmation_patterns_report.json"
SUMMARY_PATH = INTEL_DIR / "phase3_confirmation_patterns_summary.txt"


def load_json_records(path):
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for key in ("outcomes", "setup_outcomes", "setups", "records", "items", "trades"):
                if isinstance(data.get(key), list):
                    return data[key]

            return list(data.values())
    except Exception:
        return []

    return []


def load_jsonl_records(path):
    if not path.exists():
        return []

    records = []

    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                pass
    except Exception:
        return []

    return records


def text(value):
    if value is None:
        return ""
    return str(value)


def get_setup_id(record):
    if not isinstance(record, dict):
        return None

    for key in ("setup_id", "source_setup_id", "executed_setup_id", "parent_setup_id"):
        value = record.get(key)
        if value:
            return str(value)

    return None


def classify_outcome(record):
    blob = " ".join(
        text(record.get(k))
        for k in ("event", "final_result", "result", "status", "reason", "decision", "decision_reason")
        if isinstance(record, dict)
    ).upper()

    if "TP_TOUCH" in blob or "TAKE_PROFIT" in blob or "FINAL_TP" in blob:
        return "WIN_OR_TP"

    if "SL_TOUCH" in blob or "STOP_LOSS" in blob or "FINAL_SL" in blob:
        return "LOSS_OR_SL"

    if "BREAKEVEN" in blob or "BREAK_EVEN" in blob or "BE" == blob.strip():
        return "BREAKEVEN"

    if "EXECUTION_SUCCESS" in blob or "TRADE_EXECUTED" in blob:
        return "EXECUTED_PENDING"

    if "TRACKED" in blob:
        return "TRACKED_PENDING"

    if "REJECTED" in blob:
        return "REJECTED_TRACKED"

    return "UNKNOWN"


def confirmation_key(record):
    if not isinstance(record, dict):
        return "UNKNOWN|UNKNOWN|UNKNOWN"

    strategy = text(record.get("strategy") or record.get("strategy_name") or "UNKNOWN")
    signal = text(record.get("signal") or "UNKNOWN")
    bucket = text(record.get("setup_source_bucket") or record.get("bucket") or record.get("source") or "UNKNOWN")

    decision = text(
        record.get("shadow_decision")
        or record.get("decision")
        or record.get("shadow_action")
        or record.get("action")
        or "UNKNOWN"
    )

    confidence = record.get("confidence")
    score_delta = record.get("score_delta")

    try:
        confidence_bucket = f"conf_{int(float(confidence) // 10 * 10)}s"
    except Exception:
        confidence_bucket = "conf_unknown"

    try:
        delta = float(score_delta)
        if delta >= 5:
            delta_bucket = "delta_5_plus"
        elif delta >= 3:
            delta_bucket = "delta_3_to_5"
        elif delta >= 0:
            delta_bucket = "delta_0_to_3"
        else:
            delta_bucket = "delta_negative"
    except Exception:
        delta_bucket = "delta_unknown"

    return f"{strategy}|{signal}|{bucket}|{decision}|{confidence_bucket}|{delta_bucket}"


def main():
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    if not BASELINE_PATH.exists():
        raise SystemExit("[STOP] Missing phase3_baseline.json. Run create_phase3_baseline.py first.")

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    counts = baseline.get("counts", {})

    outcomes = load_json_records(ACCOUNT_DIR / "setup_outcomes.json")
    confirmations = load_jsonl_records(ACCOUNT_DIR / "confirmation_observations.jsonl")

    base_outcomes = int(counts.get("setup_outcomes_records") or max(0, len(outcomes)))
    base_confirmations = int(counts.get("confirmation_observations_records") or max(0, len(confirmations)))

    new_outcomes = outcomes[base_outcomes:]
    new_confirmations = confirmations[base_confirmations:]

    outcomes_by_setup = defaultdict(list)

    for outcome in new_outcomes:
        setup_id = get_setup_id(outcome)
        if setup_id:
            outcomes_by_setup[setup_id].append(outcome)

    pattern_stats = defaultdict(lambda: Counter())
    pending_setups = []

    for confirmation in new_confirmations:
        setup_id = get_setup_id(confirmation)
        key = confirmation_key(confirmation)

        matched_outcomes = outcomes_by_setup.get(setup_id, [])

        if not matched_outcomes:
            pattern_stats[key]["NO_MATCHED_OUTCOME_YET"] += 1
            pending_setups.append(setup_id)
            continue

        for outcome in matched_outcomes:
            pattern_stats[key][classify_outcome(outcome)] += 1

    ranked = []

    for key, counter in pattern_stats.items():
        total = sum(counter.values())
        wins = counter.get("WIN_OR_TP", 0)
        losses = counter.get("LOSS_OR_SL", 0)
        be = counter.get("BREAKEVEN", 0)
        pending = counter.get("EXECUTED_PENDING", 0) + counter.get("TRACKED_PENDING", 0) + counter.get("NO_MATCHED_OUTCOME_YET", 0)

        decisive = wins + losses
        win_rate_decisive = round(wins / decisive, 4) if decisive > 0 else None

        ranked.append({
            "pattern": key,
            "total": total,
            "wins": wins,
            "losses": losses,
            "breakeven": be,
            "pending": pending,
            "win_rate_decisive": win_rate_decisive,
            "counts": dict(counter),
        })

    ranked.sort(
        key=lambda item: (
            item["win_rate_decisive"] if item["win_rate_decisive"] is not None else -1,
            item["total"],
        ),
        reverse=True,
    )

    report = {
        "phase": "PHASE_3D_CONFIRMATION_PATTERNS",
        "mode": "OBSERVE_ONLY",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline_created_at": baseline.get("created_at"),
        "post_baseline_counts": {
            "new_setup_outcomes": len(new_outcomes),
            "new_confirmation_observations": len(new_confirmations),
            "matched_confirmation_patterns": len(ranked),
        },
        "patterns": ranked,
        "decision": "NO_LIVE_BLOCKING_NO_AUTO_EXECUTION",
        "recommendation": (
            "COLLECT_MORE_CONFIRMATION_PATTERN_EVIDENCE"
            if len(new_confirmations) < 50
            else "READY_FOR_MANUAL_PATTERN_REVIEW_ONLY"
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "[PHASE 3D CONFIRMATION PATTERNS]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        "",
        "[POST-BASELINE COUNTS]",
        f"new_setup_outcomes = {len(new_outcomes)}",
        f"new_confirmation_observations = {len(new_confirmations)}",
        f"matched_patterns = {len(ranked)}",
        "",
        "[TOP PATTERNS]",
    ]

    for item in ranked[:15]:
        lines.append(
            f"{item['pattern']} | total={item['total']} "
            f"wins={item['wins']} losses={item['losses']} be={item['breakeven']} "
            f"pending={item['pending']} win_rate_decisive={item['win_rate_decisive']}"
        )

    lines += [
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
    ]

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nreport = {REPORT_PATH}")
    print(f"summary = {SUMMARY_PATH}")


if __name__ == "__main__":
    main()