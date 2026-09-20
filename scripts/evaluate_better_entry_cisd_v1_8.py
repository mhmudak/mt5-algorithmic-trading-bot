from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from statistics import median

TERMINAL_PARENT_STATUSES = {"CLOSED", "EXPIRED"}
CISD_APPLICABLE_POLICIES = {"CISD_REQUIRED", "CISD_ON_RETEST", "CISD_OPTIONAL"}
GROUP_FIELDS = ("research_scope", "cisd_policy", "strategy", "entry_model", "signal")


def _upper(v):
    return str(v or "").strip().upper()


def _float(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _int(v):
    try:
        return int(v)
    except Exception:
        return None


def _ratio(a, b):
    return None if not b else round(a / b, 6)


def _dist(values):
    xs = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not xs:
        return {"n": 0, "mean": None, "p25": None, "p50": None, "p75": None}

    def pct(p):
        if len(xs) == 1:
            return xs[0]
        pos = (len(xs) - 1) * p
        lo = int(math.floor(pos))
        hi = int(math.ceil(pos))
        if lo == hi:
            return xs[lo]
        w = pos - lo
        return xs[lo] * (1 - w) + xs[hi] * w

    return {
        "n": len(xs),
        "mean": round(sum(xs) / len(xs), 6),
        "p25": round(pct(0.25), 6),
        "p50": round(float(median(xs)), 6),
        "p75": round(pct(0.75), 6),
    }


def _rr(signal, entry, sl, tp):
    e, s, t = _float(entry), _float(sl), _float(tp)
    if e is None or s is None or t is None or _upper(signal) not in {"BUY", "SELL"}:
        return None
    risk = abs(e - s)
    return None if risk <= 0 else round(abs(t - e) / risk, 6)


def _load_rows(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("items", "setups"):
            if isinstance(payload.get(key), list):
                return [x for x in payload[key] if isinstance(x, dict)]
        return [x for x in payload.values() if isinstance(x, dict)]
    return []


def _default_path():
    try:
        from src.setup_outcome_tracker import get_setup_outcomes_file
        p = get_setup_outcomes_file()
        if p:
            return Path(p)
    except Exception:
        pass
    for p in (Path("data/setup_outcomes.json"), Path("setup_outcomes.json")):
        if p.exists():
            return p
    return Path("data/setup_outcomes.json")


def _records(rows):
    out = []
    for row in rows:
        if _upper(row.get("status")) not in TERMINAL_PARENT_STATUSES:
            continue
        candidates = row.get("better_entry_counterfactuals")
        if not isinstance(candidates, dict):
            continue

        scope = _upper(row.get("better_entry_counterfactual_scope")) or "LEGACY_UNSCOPED"
        strategy = _upper(row.get("strategy")) or "UNKNOWN"
        entry_model = _upper(row.get("entry_model")) or "UNKNOWN"
        signal = _upper(row.get("signal")) or "UNKNOWN"
        snapshot = row.get("better_entry_observer_snapshot")
        snapshot = snapshot if isinstance(snapshot, dict) else {}

        for candidate_id, c in candidates.items():
            if not isinstance(c, dict):
                continue
            obs = c.get("cisd_observer")
            obs = obs if isinstance(obs, dict) else {}
            policy = _upper(obs.get("policy") or snapshot.get("cisd_policy")) or "UNKNOWN"

            original_rr = _rr(signal, c.get("original_entry"), c.get("original_sl"), c.get("original_tp"))
            candidate_rr = _rr(signal, c.get("candidate_entry"), c.get("original_sl"), c.get("original_tp"))
            rr_improvement = None
            if original_rr is not None and candidate_rr is not None:
                rr_improvement = round(candidate_rr - original_rr, 6)

            armed_bar = _int(obs.get("armed_closed_bar_time"))
            confirmed_bar = _int(obs.get("confirmed_at_bar_time"))
            cisd_wait = None
            if armed_bar is not None and confirmed_bar is not None and confirmed_bar >= armed_bar:
                cisd_wait = confirmed_bar - armed_bar

            out.append({
                "setup_id": row.get("setup_id"),
                "candidate_id": c.get("candidate_id") or candidate_id,
                "candidate_basis": c.get("basis"),
                "research_scope": scope,
                "strategy": strategy,
                "entry_model": entry_model,
                "signal": signal,
                "filled": bool(c.get("filled")),
                "candidate_setup_win": bool(c.get("hit_plus_10_after_fill")),
                "missed_winner": bool(c.get("missed_winner")),
                "candidate_mae": _float(c.get("max_adverse_usd_after_fill")),
                "candidate_mfe": _float(c.get("max_favorable_usd_after_fill")),
                "fill_wait_seconds": _float(c.get("fill_wait_seconds")),
                "rr_improvement": rr_improvement,
                "cisd_observed": bool(obs),
                "cisd_policy": policy,
                "cisd_status": _upper(obs.get("status")) or ("NOT_OBSERVED" if not obs else "UNKNOWN"),
                "cisd_armed": bool(obs.get("armed")),
                "cisd_confirmed": bool(obs.get("confirmed")),
                "shadow_entry_qualified": bool(obs.get("shadow_entry_qualified")),
                "cisd_confirm_wait_seconds": cisd_wait,
            })
    return out


def _summary(records):
    n = len(records)
    observed = [r for r in records if r["cisd_observed"]]
    applicable = [r for r in records if r["cisd_policy"] in CISD_APPLICABLE_POLICIES]
    armed = [r for r in applicable if r["cisd_armed"]]
    confirmed = [r for r in armed if r["cisd_confirmed"]]
    filled = [r for r in records if r["filled"]]
    qualified = [r for r in filled if r["shadow_entry_qualified"]]
    unqualified = [r for r in filled if not r["shadow_entry_qualified"]]
    applicable_filled = [r for r in filled if r["cisd_policy"] in CISD_APPLICABLE_POLICIES]
    confirmed_filled = [r for r in applicable_filled if r["cisd_confirmed"]]
    unconfirmed_filled = [r for r in applicable_filled if not r["cisd_confirmed"]]

    def win_rate(rs):
        return _ratio(sum(1 for r in rs if r["candidate_setup_win"]), len(rs))

    return {
        "n": n,
        "cisd_observed_n": len(observed),
        "cisd_observed_rate": _ratio(len(observed), n),
        "cisd_applicable_n": len(applicable),
        "cisd_armed_n": len(armed),
        "cisd_armed_rate": _ratio(len(armed), len(applicable)),
        "cisd_confirmed_n": len(confirmed),
        "cisd_confirmation_rate_given_armed": _ratio(len(confirmed), len(armed)),
        "cisd_confirmation_wait_seconds": _dist(r["cisd_confirm_wait_seconds"] for r in confirmed),
        "filled_n": len(filled),
        "fill_rate": _ratio(len(filled), n),
        "candidate_setup_win_n": sum(1 for r in filled if r["candidate_setup_win"]),
        "candidate_setup_win_rate": win_rate(filled),
        "qualified_filled_n": len(qualified),
        "qualification_rate_given_fill": _ratio(len(qualified), len(filled)),
        "qualified_setup_win_rate": win_rate(qualified),
        "unqualified_filled_n": len(unqualified),
        "unqualified_setup_win_rate": win_rate(unqualified),
        "confirmed_filled_n": len(confirmed_filled),
        "confirmed_filled_setup_win_rate": win_rate(confirmed_filled),
        "unconfirmed_filled_n": len(unconfirmed_filled),
        "unconfirmed_filled_setup_win_rate": win_rate(unconfirmed_filled),
        "missed_winner_n": sum(1 for r in records if r["missed_winner"]),
        "missed_winner_rate": _ratio(sum(1 for r in records if r["missed_winner"]), n),
        "candidate_mae": _dist(r["candidate_mae"] for r in filled),
        "candidate_mfe": _dist(r["candidate_mfe"] for r in filled),
        "fill_wait_seconds": _dist(r["fill_wait_seconds"] for r in filled),
        "rr_improvement": _dist(r["rr_improvement"] for r in records),
    }


def _group(records, field):
    groups = defaultdict(list)
    for r in records:
        groups[str(r.get(field) or "UNKNOWN")].append(r)
    return {k: _summary(v) for k, v in sorted(groups.items())}


def evaluate_rows(rows):
    records = _records(rows)
    primary = [r for r in records if r["research_scope"] == "PRIMARY"]
    rescue = [r for r in records if r["research_scope"] == "ENTRY_RESCUE"]
    legacy = [r for r in records if r["research_scope"] == "LEGACY_UNSCOPED"]

    return {
        "schema_version": "V1.8",
        "authority": {
            "decision_impact": "EVALUATION_ONLY",
            "can_execute": False,
            "can_block_trade": False,
            "can_modify_score": False,
            "can_modify_risk": False,
            "can_modify_entry_sl_tp": False,
            "can_modify_lot": False,
        },
        "all": _summary(records),
        "primary_only": _summary(primary),
        "entry_rescue_only": _summary(rescue),
        "legacy_unscoped_only": _summary(legacy),
        "groups": {f: _group(records, f) for f in GROUP_FIELDS},
        "interpretation": {
            "promotion_evidence_scope": "PRIMARY only; ENTRY_RESCUE is separate and LEGACY_UNSCOPED is not promotion evidence.",
            "setup_win_definition": "Candidate Setup Win = hit_plus_10_after_fill; this is not executed trade P&L.",
            "cisd_denominator": "Confirmation rate uses armed CISD-applicable candidates only.",
            "causality_warning": "Confirmed-vs-unconfirmed differences are observational and may be selection-confounded; they are not causal proof.",
        },
        "records": records,
    }


def _pct(v):
    return "N/A" if v is None else f"{100*v:.2f}%"


def format_report(report):
    lines = [
        "BETTER ENTRY CISD EVALUATOR V1.8",
        "",
        "AUTHORITY: EVALUATION_ONLY",
        "Better Entry and CISD remain shadow-only.",
        "",
    ]
    for title, key in (
        ("PRIMARY ONLY", "primary_only"),
        ("ENTRY RESCUE ONLY", "entry_rescue_only"),
        ("ALL TERMINAL RESEARCH CANDIDATES", "all"),
    ):
        m = report[key]
        lines += [
            title,
            f"  n: {m['n']}",
            f"  CISD observed: {_pct(m['cisd_observed_rate'])}",
            f"  CISD armed: {_pct(m['cisd_armed_rate'])}",
            f"  CISD confirmed | armed: {_pct(m['cisd_confirmation_rate_given_armed'])}",
            f"  Fill rate: {_pct(m['fill_rate'])}",
            f"  Candidate Setup Win | filled: {_pct(m['candidate_setup_win_rate'])}",
            f"  Qualified Setup Win: {_pct(m['qualified_setup_win_rate'])}",
            f"  Unqualified Setup Win: {_pct(m['unqualified_setup_win_rate'])}",
            f"  Confirmed filled Setup Win: {_pct(m['confirmed_filled_setup_win_rate'])}",
            f"  Unconfirmed filled Setup Win: {_pct(m['unconfirmed_filled_setup_win_rate'])}",
            f"  Missed winner rate: {_pct(m['missed_winner_rate'])}",
            "",
        ]
    lines += [
        "INTERPRETATION",
        "- Promotion evidence scope: PRIMARY only.",
        "- Candidate Setup Win means +$10 after hypothetical fill, not trade P&L.",
        "- Confirmed-vs-unconfirmed differences are observational, not causal proof.",
        "- Better Entry and CISD remain shadow-only.",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=None)
    parser.add_argument("--json-output", type=Path, default=None)
    parser.add_argument("--text-output", type=Path, default=None)
    args = parser.parse_args()

    path = args.path or _default_path()
    if not path.exists():
        raise SystemExit(f"Setup outcomes file not found: {path}")

    report = evaluate_rows(_load_rows(path))
    json_out = args.json_output or path.parent / "better_entry_cisd_evaluation_v1_8.json"
    text_out = args.text_output or path.parent / "better_entry_cisd_evaluation_v1_8.txt"

    json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    text_out.write_text(format_report(report), encoding="utf-8")

    print(format_report(report), end="")
    print(f"JSON: {json_out}")
    print(f"TEXT: {text_out}")


if __name__ == "__main__":
    main()
