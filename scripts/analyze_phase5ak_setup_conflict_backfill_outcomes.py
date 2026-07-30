from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PHASE = "PHASE_5AK_SETUP_CONFLICT_BACKFILL_OUTCOME_REVIEW"

DEFAULT_ACCOUNT_DIR = ROOT / "data" / "accounts" / "Tickmill-Demo_25323531"
PHASE5AH_DIR = ROOT / "data" / "strategy_intelligence" / "phase5ah_setup_conflicts"

INPUT_JSON = PHASE5AH_DIR / "phase5aj_historical_setup_conflicts.json"
OUT_JSON = PHASE5AH_DIR / "phase5ak_setup_conflict_backfill_outcome_review.json"
OUT_TXT = PHASE5AH_DIR / "phase5ak_setup_conflict_backfill_outcome_review_summary.txt"


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


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def flatten_records(payload: Any) -> list[dict[str, Any]]:
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


def base_setup_id(value: Any) -> str:
    text = safe_text(value)

    for suffix in [
        "-MTFOVERRIDE",
        "-MTFSCALP",
        "-EXTRA",
        "-STAGE1",
        "-STAGE2",
        "-STAGE3",
    ]:
        if text.endswith(suffix):
            return text[: -len(suffix)]

    return text


def normalize_outcome(row: dict[str, Any]) -> str:
    text = "|".join(
        [
            safe_text(row.get("final_outcome")),
            safe_text(row.get("outcome")),
            safe_text(row.get("result")),
            safe_text(row.get("status")),
            safe_text(row.get("decision")),
        ]
    ).upper()

    if any(x in text for x in ["TP", "WIN", "PROFIT", "PROFITABLE"]):
        return "WIN"

    if any(x in text for x in ["SL", "LOSS", "STOP"]):
        return "LOSS"

    if any(x in text for x in ["BE", "BREAKEVEN"]):
        return "BE"

    if any(x in text for x in ["OPEN", "PENDING", "TRACKING"]):
        return "OPEN_OR_TRACKING"

    return "UNKNOWN"


def row_profit(row: dict[str, Any]) -> float | None:
    for key in [
        "realized_profit",
        "profit",
        "pnl",
        "net_profit",
        "max_favorable_excursion",
        "mfe",
    ]:
        if key in row and safe_text(row.get(key)) != "":
            return safe_float(row.get(key))

    outcome = normalize_outcome(row)
    if outcome == "WIN":
        return 1.0
    if outcome == "LOSS":
        return -1.0
    if outcome == "BE":
        return 0.0

    return None


def setup_id_index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        ids = [
            row.get("setup_id"),
            row.get("source_setup_id"),
            row.get("executed_setup_id"),
            row.get("parent_setup_id"),
            row.get("candidate_setup_id"),
            row.get("trade_setup_id"),
        ]

        for raw_id in ids:
            sid = base_setup_id(raw_id)
            if sid:
                index.setdefault(sid, []).append(row)

    return index


def conflict_unique_key(conflict: dict[str, Any]) -> str:
    prev = conflict.get("previous_setup") or {}
    new = conflict.get("new_setup") or {}
    matrix = conflict.get("strategy_family_matrix") or {}
    metrics = conflict.get("conflict_metrics") or {}

    prev_id = base_setup_id(prev.get("setup_id"))
    new_id = base_setup_id(new.get("setup_id"))

    if prev_id and new_id:
        id_part = f"{prev_id}|{new_id}"
    else:
        id_part = "|".join(
            [
                safe_text(conflict.get("previous_created_at")),
                safe_text(conflict.get("new_created_at")),
                safe_text(prev.get("strategy")),
                safe_text(prev.get("direction")),
                safe_text(prev.get("entry")),
                safe_text(new.get("strategy")),
                safe_text(new.get("direction")),
                safe_text(new.get("entry")),
            ]
        )

    return "|".join(
        [
            id_part,
            safe_text(matrix.get("pair")),
            safe_text(matrix.get("priority_side")),
            str(round(safe_float(metrics.get("entry_distance")), 2)),
        ]
    )


def best_outcome_for_setup(
    setup_id: Any,
    *,
    outcome_index: dict[str, list[dict[str, Any]]],
    trade_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    sid = base_setup_id(setup_id)

    rows = []
    rows.extend(outcome_index.get(sid, []))
    rows.extend(trade_index.get(sid, []))

    if not rows:
        return {
            "setup_id": sid,
            "matched": False,
            "outcome": "UNKNOWN",
            "profit": None,
            "source_count": 0,
        }

    outcomes = Counter(normalize_outcome(row) for row in rows)
    profits = [row_profit(row) for row in rows]
    known_profits = [p for p in profits if p is not None]

    if outcomes.get("WIN", 0) > 0:
        outcome = "WIN"
    elif outcomes.get("LOSS", 0) > 0:
        outcome = "LOSS"
    elif outcomes.get("BE", 0) > 0:
        outcome = "BE"
    elif outcomes.get("OPEN_OR_TRACKING", 0) > 0:
        outcome = "OPEN_OR_TRACKING"
    else:
        outcome = "UNKNOWN"

    return {
        "setup_id": sid,
        "matched": True,
        "outcome": outcome,
        "profit": sum(known_profits) if known_profits else None,
        "source_count": len(rows),
        "outcome_counts": dict(outcomes),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-dir", default=str(DEFAULT_ACCOUNT_DIR))
    args = parser.parse_args()

    account_dir = Path(args.account_dir)

    setup_outcomes = flatten_records(load_json(account_dir / "setup_outcomes.json", []))
    trades = flatten_records(load_json(account_dir / "trades.json", []))

    outcome_index = setup_id_index(setup_outcomes)
    trade_index = setup_id_index(trades)

    phase5aj = load_json(INPUT_JSON, {})
    conflicts = phase5aj.get("conflicts") or []
    conflicts = [x for x in conflicts if isinstance(x, dict)]

    priority_conflicts = [
        item for item in conflicts
        if item.get("priority_conflict_review") is True
    ]

    deduped = {}
    for conflict in priority_conflicts:
        deduped[conflict_unique_key(conflict)] = conflict

    unique_priority_conflicts = list(deduped.values())

    reviewed = []

    for conflict in unique_priority_conflicts:
        prev = conflict.get("previous_setup") or {}
        new = conflict.get("new_setup") or {}
        matrix = conflict.get("strategy_family_matrix") or {}

        priority_side = safe_text(matrix.get("priority_side"))

        priority_setup = new if priority_side == "NEW_SETUP" else prev
        non_priority_setup = prev if priority_side == "NEW_SETUP" else new

        priority_outcome = best_outcome_for_setup(
            priority_setup.get("setup_id"),
            outcome_index=outcome_index,
            trade_index=trade_index,
        )

        non_priority_outcome = best_outcome_for_setup(
            non_priority_setup.get("setup_id"),
            outcome_index=outcome_index,
            trade_index=trade_index,
        )

        reviewed.append(
            {
                "previous_created_at": conflict.get("previous_created_at"),
                "new_created_at": conflict.get("new_created_at"),
                "pair": matrix.get("pair"),
                "rule": matrix.get("rule"),
                "priority_side": priority_side,
                "previous_setup": prev,
                "new_setup": new,
                "priority_setup": priority_setup,
                "non_priority_setup": non_priority_setup,
                "priority_outcome": priority_outcome,
                "non_priority_outcome": non_priority_outcome,
                "needs_manual_chart_review": True,
            }
        )

    outcome_counts = Counter()
    matched_priority = 0
    priority_wins = 0
    priority_losses = 0
    priority_be = 0

    for item in reviewed:
        outcome = item["priority_outcome"]["outcome"]
        outcome_counts[outcome] += 1

        if item["priority_outcome"]["matched"]:
            matched_priority += 1

        if outcome == "WIN":
            priority_wins += 1
        elif outcome == "LOSS":
            priority_losses += 1
        elif outcome == "BE":
            priority_be += 1

    decisive = priority_wins + priority_losses
    priority_win_rate = priority_wins / decisive if decisive else None

    report = {
        "phase": PHASE,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "AUDIT_ONLY",
        "decision_impact": "NONE",
        "execution_change": "NONE",
        "inputs": {
            "phase5aj": str(INPUT_JSON),
            "setup_outcomes": str(account_dir / "setup_outcomes.json"),
            "trades": str(account_dir / "trades.json"),
        },
        "raw_priority_conflict_count": len(priority_conflicts),
        "unique_priority_conflict_count": len(unique_priority_conflicts),
        "matched_priority_outcome_count": matched_priority,
        "priority_outcome_counts": dict(outcome_counts),
        "priority_wins": priority_wins,
        "priority_losses": priority_losses,
        "priority_breakeven": priority_be,
        "priority_decisive_count": decisive,
        "priority_win_rate": priority_win_rate,
        "reviewed_priority_conflicts": reviewed,
        "readiness_note": (
            "This is still not enough to enable execution. Use this to manually review unique conflicts and improve statistics."
        ),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "[PHASE 5AK SETUP CONFLICT BACKFILL OUTCOME REVIEW]",
        f"updated_at = {report['updated_at']}",
        f"mode = {report['mode']}",
        f"decision_impact = {report['decision_impact']}",
        f"execution_change = {report['execution_change']}",
        "",
        "[SUMMARY]",
        f"raw_priority_conflict_count = {report['raw_priority_conflict_count']}",
        f"unique_priority_conflict_count = {report['unique_priority_conflict_count']}",
        f"matched_priority_outcome_count = {report['matched_priority_outcome_count']}",
        f"priority_wins = {priority_wins}",
        f"priority_losses = {priority_losses}",
        f"priority_breakeven = {priority_be}",
        f"priority_decisive_count = {decisive}",
        f"priority_win_rate = {priority_win_rate}",
        f"priority_outcome_counts = {dict(outcome_counts)}",
        "",
        "[UNIQUE PRIORITY CONFLICTS]",
    ]

    for item in reviewed:
        p = item["priority_setup"]
        np = item["non_priority_setup"]
        po = item["priority_outcome"]
        npo = item["non_priority_outcome"]

        lines.append(
            f"- {item['previous_created_at']} -> {item['new_created_at']} | "
            f"priority={item['priority_side']} | "
            f"{p.get('strategy')} {p.get('direction')} @ {p.get('entry')} "
            f"outcome={po.get('outcome')} matched={po.get('matched')} | "
            f"against {np.get('strategy')} {np.get('direction')} @ {np.get('entry')} "
            f"outcome={npo.get('outcome')} matched={npo.get('matched')}"
        )

    lines.extend(
        [
            "",
            "[READINESS NOTE]",
            report["readiness_note"],
            "",
            f"json = {OUT_JSON}",
            f"summary = {OUT_TXT}",
        ]
    )

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()