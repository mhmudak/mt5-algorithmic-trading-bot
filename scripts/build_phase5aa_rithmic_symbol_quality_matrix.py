from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


PHASE = "PHASE_5AA_RITHMIC_SYMBOL_QUALITY_MATRIX"

ROOT = Path(__file__).resolve().parents[1]
ORDER_FLOW_DIR = ROOT / "data" / "order_flow" / "rithmic"

SYMBOLS = ["MGCQ6", "GCQ6"]

OUT_JSON = ORDER_FLOW_DIR / "phase5aa_rithmic_symbol_quality_matrix.json"
OUT_TXT = ORDER_FLOW_DIR / "phase5aa_rithmic_symbol_quality_matrix_summary.txt"


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows = []

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line:
            continue

        try:
            obj = json.loads(line)
        except Exception:
            continue

        if isinstance(obj, dict):
            rows.append(obj)

    return rows


def summarize_symbol(symbol: str) -> dict[str, Any]:
    path = ORDER_FLOW_DIR / f"{symbol}_phase5y_long_session_history.jsonl"
    records = load_jsonl(path)

    metrics = [r.get("metrics") or {} for r in records]

    sample_count = len(records)

    positive_bbo = [
        m for m in metrics
        if as_float(m.get("bid")) > 0 and as_float(m.get("ask")) > 0
    ]

    two_sided_dom = [
        m for m in metrics
        if as_float(m.get("bid_depth")) > 0 and as_float(m.get("ask_depth")) > 0
    ]

    spreads = [
        as_float(m.get("spread"))
        for m in metrics
        if as_float(m.get("spread")) > 0
    ]

    trade_counts = [
        as_float(m.get("rolling_trade_count"))
        for m in metrics
    ]

    avg_spread = round(sum(spreads) / len(spreads), 6) if spreads else None
    max_spread = max(spreads) if spreads else None

    positive_bbo_rate = round(len(positive_bbo) / sample_count, 4) if sample_count else 0.0
    two_sided_dom_rate = round(len(two_sided_dom) / sample_count, 4) if sample_count else 0.0
    avg_trade_count = round(sum(trade_counts) / len(trade_counts), 4) if trade_counts else 0.0
    max_trade_count = max(trade_counts) if trade_counts else 0.0

    checks = {
        "has_samples": sample_count >= 10,
        "positive_bbo_rate_ok": positive_bbo_rate >= 0.80,
        "two_sided_dom_rate_ok": two_sided_dom_rate >= 0.80,
        "spread_ok_observe_only": max_spread is not None and 0 < as_float(max_spread) <= 1.0,
        "trade_flow_seen": max_trade_count > 0,
        "trade_flow_decision_grade": max_trade_count >= 5,
    }

    hard_reject_reasons = []

    if not checks["has_samples"]:
        hard_reject_reasons.append("NOT_ENOUGH_SAMPLES")

    if not checks["spread_ok_observe_only"]:
        hard_reject_reasons.append("BAD_OR_IMPOSSIBLE_SPREAD")

    if not checks["positive_bbo_rate_ok"]:
        hard_reject_reasons.append("LOW_POSITIVE_BBO_RATE")

    if not checks["two_sided_dom_rate_ok"]:
        hard_reject_reasons.append("LOW_TWO_SIDED_DOM_RATE")

    if not hard_reject_reasons:
        status = "ACCEPTED_OBSERVE_ONLY"
    else:
        status = "REJECTED_BAD_QUALITY"

    score = 0

    if checks["has_samples"]:
        score += 20
    if checks["positive_bbo_rate_ok"]:
        score += 20
    if checks["two_sided_dom_rate_ok"]:
        score += 20
    if checks["spread_ok_observe_only"]:
        score += 25
    if checks["trade_flow_seen"]:
        score += 10
    if checks["trade_flow_decision_grade"]:
        score += 5

    return {
        "symbol": symbol,
        "jsonl": str(path),
        "status": status,
        "score": score,
        "sample_count": sample_count,
        "positive_bbo_rate": positive_bbo_rate,
        "two_sided_dom_rate": two_sided_dom_rate,
        "avg_spread": avg_spread,
        "max_spread": max_spread,
        "avg_rolling_trade_count": avg_trade_count,
        "max_rolling_trade_count": max_trade_count,
        "checks": checks,
        "hard_reject_reasons": hard_reject_reasons,
        "decision_grade_ready": False,
        "automation_allowed": False,
        "decision_impact": "NONE",
        "can_influence_decision": False,
    }


def choose_primary(symbols: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [s for s in symbols if s.get("status") == "ACCEPTED_OBSERVE_ONLY"]

    if not accepted:
        return {
            "primary_symbol": None,
            "backup_symbol": None,
            "selection_status": "NO_SYMBOL_ACCEPTED",
            "reason": "No symbol passed observe-only quality checks.",
        }

    ordered = sorted(accepted, key=lambda x: x.get("score", 0), reverse=True)

    primary = ordered[0]
    backup = ordered[1] if len(ordered) > 1 else None

    return {
        "primary_symbol": primary.get("symbol"),
        "backup_symbol": backup.get("symbol") if backup else None,
        "selection_status": "PRIMARY_SELECTED_OBSERVE_ONLY",
        "reason": "Primary selected by BBO, DOM, spread, samples, and trade-flow availability. Still observe-only.",
    }


def main() -> None:
    ORDER_FLOW_DIR.mkdir(parents=True, exist_ok=True)

    results = [summarize_symbol(symbol) for symbol in SYMBOLS]
    selection = choose_primary(results)

    report = {
        "phase": PHASE,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "provider": "RITHMIC_R_PROTOCOL",
        "source_market": "COMEX",
        "mode": "OBSERVE_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
        "symbols": results,
        "selection": selection,
        "recommendation": (
            "Use selected primary symbol for manual-review Rithmic context only. "
            "Do not allow automatic decision influence until repeated-session production validation passes."
        ),
    }

    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "[PHASE 5AA RITHMIC SYMBOL QUALITY MATRIX]",
        f"updated_at = {report['updated_at']}",
        f"provider = {report['provider']}",
        f"mode = {report['mode']}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        f"safe_for_execution = {report['safe_for_execution']}",
        f"trade_action = {report['trade_action']}",
        "",
        "[SYMBOLS]",
    ]

    for item in results:
        lines += [
            f"- {item['symbol']}",
            f"  status = {item['status']}",
            f"  score = {item['score']}",
            f"  sample_count = {item['sample_count']}",
            f"  positive_bbo_rate = {item['positive_bbo_rate']}",
            f"  two_sided_dom_rate = {item['two_sided_dom_rate']}",
            f"  avg_spread = {item['avg_spread']}",
            f"  max_spread = {item['max_spread']}",
            f"  avg_rolling_trade_count = {item['avg_rolling_trade_count']}",
            f"  max_rolling_trade_count = {item['max_rolling_trade_count']}",
            f"  hard_reject_reasons = {item['hard_reject_reasons']}",
        ]

    lines += [
        "",
        "[SELECTION]",
        f"selection_status = {selection.get('selection_status')}",
        f"primary_symbol = {selection.get('primary_symbol')}",
        f"backup_symbol = {selection.get('backup_symbol')}",
        f"reason = {selection.get('reason')}",
        "",
        "[RECOMMENDATION]",
        report["recommendation"],
        "",
        f"json = {OUT_JSON}",
        f"summary = {OUT_TXT}",
    ]

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()