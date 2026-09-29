from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from src.account_context import get_account_file

ROOT = Path(__file__).resolve().parents[1]
INTELLIGENCE_ROOT = ROOT / "data" / "strategy_intelligence"
DEFAULT_MIN_RESOLVED = 30

_POLICY_CACHE: dict[str, Any] = {
    "key": None,
    "mtimes": None,
    "candidates": [],
    "coverage": [],
}

COARSE_STANCE = {
    "HARD_SKIP_CANDIDATE": "NEGATIVE",
    "PREFERRED_TAKE_CANDIDATE": "POSITIVE",
    "PROFITABLE_LOW_HIT": "POSITIVE",
    "GOOD_ENTRY_FIX_MANAGEMENT": "MANAGEMENT",
    "MANAGEMENT_PROBLEM_REVIEW": "MANAGEMENT",
    "PROFITABLE_LOW_HIT_REVIEW": "REVIEW",
    "NEUTRAL": "NEUTRAL",
}

CONTEXT_GROUPINGS = (
    "strategy|entry_model",
    "strategy|market_condition",
    "strategy|session",
    "strategy|direction",
    "strategy|stage",
)


def _safe_upper(value: Any, default: str = "UNKNOWN") -> str:
    value = str(value or "").strip()
    return value.upper() if value else default


def _to_float(value: Any) -> float | None:
    if value in (None, "", "None", "nan", "NaN"):
        return None
    try:
        value = float(value)
    except Exception:
        return None
    return value if math.isfinite(value) else None


def _to_int(value: Any) -> int:
    value = _to_float(value)
    return int(value) if value is not None else 0


def _current_account_name(default: str | None = None) -> str | None:
    """
    Resolve the current account without ever treating MT5 placeholder names as
    real policy accounts.

    Primary path:
        src.account_context -> current MT5 server/login account.

    Safe standalone fallback:
        If MT5 is not initialized and EXACTLY ONE account under
        data/strategy_intelligence contains the setup-selection policy
        artifacts, use that account. If zero or multiple accounts qualify,
        refuse to guess.
    """
    invalid_names = {
        "",
        "NEW_ACCOUNT_FOLDER",
        "UNKNOWN_ACCOUNT",
        "UNKNOWN",
        "NONE",
    }

    try:
        account_dir = get_account_file("trades.json").parent
        account_name = str(account_dir.name or "").strip()
        if account_name.upper() not in invalid_names:
            policy_base = _policy_dir(account_name)
            if (
                (policy_base / "strategy_coverage.csv").exists()
                and (policy_base / "all_policy_candidates.csv").exists()
            ):
                return account_name
    except Exception:
        pass

    try:
        candidates = []
        if INTELLIGENCE_ROOT.exists():
            for account_dir in INTELLIGENCE_ROOT.iterdir():
                if not account_dir.is_dir():
                    continue
                if account_dir.name.upper() in invalid_names:
                    continue

                policy_base = _policy_dir(account_dir.name)
                if (
                    (policy_base / "strategy_coverage.csv").exists()
                    and (policy_base / "all_policy_candidates.csv").exists()
                ):
                    candidates.append(account_dir.name)

        if len(candidates) == 1:
            return candidates[0]
    except Exception:
        pass

    return default


def _policy_dir(account_name: str) -> Path:
    return (
        INTELLIGENCE_ROOT
        / account_name
        / "setup_selection_optimizer_v2"
        / "consolidated_policy_v2"
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _load(account_name: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    base = _policy_dir(account_name)
    candidates_path = base / "all_policy_candidates.csv"
    coverage_path = base / "strategy_coverage.csv"

    mtimes = (
        candidates_path.stat().st_mtime if candidates_path.exists() else None,
        coverage_path.stat().st_mtime if coverage_path.exists() else None,
    )
    key = str(base.resolve())

    if (
        _POLICY_CACHE["key"] == key
        and _POLICY_CACHE["mtimes"] == mtimes
    ):
        return _POLICY_CACHE["candidates"], _POLICY_CACHE["coverage"]

    candidates = _read_csv(candidates_path)
    coverage = _read_csv(coverage_path)

    _POLICY_CACHE.update(
        {
            "key": key,
            "mtimes": mtimes,
            "candidates": candidates,
            "coverage": coverage,
        }
    )
    return candidates, coverage


def _row_matches(
    row: dict[str, str],
    *,
    strategy: str,
    direction: str,
    entry_model: str,
    session: str,
    market_condition: str,
    stage: str,
) -> bool:
    grouping = str(row.get("grouping") or "").strip()
    values = {
        "strategy": strategy,
        "direction": direction,
        "entry_model": entry_model,
        "session": session,
        "market_condition": market_condition,
        "stage": stage,
    }

    fields = grouping.split("|") if grouping else []
    if not fields:
        return False

    for field in fields:
        expected = values.get(field, "UNKNOWN")
        actual = _safe_upper(row.get(field))
        if expected == "UNKNOWN" or actual != expected:
            return False
    return True


def _normalize_candidate(row: dict[str, str]) -> dict[str, Any]:
    win_rate = _to_float(row.get("selection_win_rate"))
    return {
        "grouping": row.get("grouping"),
        "strategy": row.get("strategy"),
        "direction": row.get("direction"),
        "entry_model": row.get("entry_model"),
        "session": row.get("session"),
        "market_condition": row.get("market_condition"),
        "stage": row.get("stage"),
        "badge": row.get("policy_category") or "NEUTRAL",
        "reason": row.get("policy_reason") or "",
        "sample_count": _to_int(row.get("selection_resolved_count")),
        "win_quality": win_rate,
        "win_quality_pct": (win_rate * 100.0) if win_rate is not None else None,
        "final_expectancy_r": _to_float(row.get("final_path_expectancy_r")),
        "w10_to_sl_rate": _to_float(row.get("w10_giveback_to_sl_rate")),
        "selection_edge_ci95_low": _to_float(row.get("selection_edge_ci95_low")),
        "selection_edge_ci95_high": _to_float(row.get("selection_edge_ci95_high")),
        "final_expectancy_ci95_low": _to_float(row.get("final_path_expectancy_ci95_low")),
        "final_expectancy_ci95_high": _to_float(row.get("final_path_expectancy_ci95_high")),
    }


def _coverage_result(
    row: dict[str, str],
    *,
    min_resolved: int,
) -> dict[str, Any]:
    n = _to_int(row.get("selection_resolved_count"))
    win_rate = _to_float(row.get("selection_win_rate"))
    exp_r = _to_float(row.get("final_path_expectancy_r"))
    return {
        "badge": "INSUFFICIENT_DATA",
        "coarse_stance": "RESEARCH",
        "sample_count": n,
        "min_resolved": min_resolved,
        "samples_needed": max(0, min_resolved - n),
        "win_quality": win_rate,
        "win_quality_pct": (win_rate * 100.0) if win_rate is not None else None,
        "final_expectancy_r": exp_r,
        "evidence_grouping": "strategy",
        "evidence": [],
        "reason": "strategy has historical outcomes but has not reached the minimum resolved sample threshold",
        "live_authority": False,
        "decision_impact": "NONE",
    }


def resolve_setup_selection_advisory(
    *,
    strategy: Any,
    direction: Any = None,
    entry_model: Any = None,
    session: Any = None,
    market_condition: Any = None,
    stage: Any = None,
    account_name: str | None = None,
    min_resolved: int = DEFAULT_MIN_RESOLVED,
) -> dict[str, Any]:
    """
    Account-scoped, display-only setup-selection advisory.

    This function NEVER blocks execution, changes risk, changes RR, or changes
    order parameters. It only resolves the best available historical evidence.
    """
    account_name = account_name or _current_account_name()
    strategy_u = _safe_upper(strategy)
    if not account_name or strategy_u == "UNKNOWN":
        return {
            "badge": "NO_DATA",
            "reason": "missing account or strategy identity",
            "live_authority": False,
            "decision_impact": "NONE",
            "evidence": [],
        }

    direction_u = _safe_upper(direction)
    entry_model_u = _safe_upper(entry_model)
    session_u = _safe_upper(session)
    market_condition_u = _safe_upper(market_condition)
    stage_u = _safe_upper(stage)

    candidates, coverage = _load(account_name)

    strategy_coverage = next(
        (
            row for row in coverage
            if _safe_upper(row.get("strategy")) == strategy_u
        ),
        None,
    )
    if strategy_coverage is None:
        return {
            "badge": "NO_DATA",
            "strategy": strategy_u,
            "reason": "strategy has no setup-selection coverage row",
            "live_authority": False,
            "decision_impact": "NONE",
            "evidence": [],
        }

    coverage_n = _to_int(strategy_coverage.get("selection_resolved_count"))
    if coverage_n < int(min_resolved):
        result = _coverage_result(strategy_coverage, min_resolved=int(min_resolved))
        result["strategy"] = strategy_u
        return result

    matched_context = []
    strategy_baseline = None

    for row in candidates:
        if _safe_upper(row.get("strategy")) != strategy_u:
            continue

        grouping = str(row.get("grouping") or "").strip()
        if grouping == "strategy":
            strategy_baseline = _normalize_candidate(row)
            continue

        if grouping not in CONTEXT_GROUPINGS:
            continue

        if _row_matches(
            row,
            strategy=strategy_u,
            direction=direction_u,
            entry_model=entry_model_u,
            session=session_u,
            market_condition=market_condition_u,
            stage=stage_u,
        ):
            matched_context.append(_normalize_candidate(row))

    # Ignore neutral context for stance resolution, but retain it as evidence.
    non_neutral = [
        row for row in matched_context
        if row.get("badge") not in (None, "", "NEUTRAL")
    ]

    if non_neutral:
        stances = {
            COARSE_STANCE.get(str(row.get("badge")), "REVIEW")
            for row in non_neutral
        }

        if len(stances) == 1:
            # Same stance: choose the most statistically reliable row (largest N)
            # as the headline, while retaining all matching rows as evidence.
            primary = max(
                non_neutral,
                key=lambda row: (
                    int(row.get("sample_count") or 0),
                    str(row.get("grouping") or ""),
                ),
            )
            result = dict(primary)
            result["coarse_stance"] = next(iter(stances))
            result["evidence_grouping"] = primary.get("grouping")
            result["evidence"] = matched_context
            result["strategy_baseline"] = strategy_baseline
            result["live_authority"] = False
            result["decision_impact"] = "NONE"
            return result

        # Conflicting contextual evidence must not be collapsed into a false
        # precision TAKE/SKIP badge.
        reference = strategy_baseline or max(
            non_neutral,
            key=lambda row: int(row.get("sample_count") or 0),
        )
        return {
            "badge": "MIXED_CONTEXT",
            "coarse_stance": "MIXED",
            "strategy": strategy_u,
            "sample_count": reference.get("sample_count"),
            "win_quality": reference.get("win_quality"),
            "win_quality_pct": reference.get("win_quality_pct"),
            "final_expectancy_r": reference.get("final_expectancy_r"),
            "w10_to_sl_rate": reference.get("w10_to_sl_rate"),
            "evidence_grouping": "multiple_context_buckets",
            "evidence": matched_context,
            "strategy_baseline": strategy_baseline,
            "reason": "eligible context buckets disagree; no single directional policy conclusion is authorized",
            "live_authority": False,
            "decision_impact": "NONE",
        }

    if strategy_baseline:
        result = dict(strategy_baseline)
        result["coarse_stance"] = COARSE_STANCE.get(
            str(result.get("badge")), "NEUTRAL"
        )
        result["evidence_grouping"] = "strategy"
        result["evidence"] = matched_context
        result["strategy_baseline"] = strategy_baseline
        result["live_authority"] = False
        result["decision_impact"] = "NONE"
        return result

    # Eligible in coverage but no policy row can occur when the strategy is
    # statistically neutral after consolidation.
    win_rate = _to_float(strategy_coverage.get("selection_win_rate"))
    return {
        "badge": "NEUTRAL",
        "coarse_stance": "NEUTRAL",
        "strategy": strategy_u,
        "sample_count": coverage_n,
        "win_quality": win_rate,
        "win_quality_pct": (win_rate * 100.0) if win_rate is not None else None,
        "final_expectancy_r": _to_float(strategy_coverage.get("final_path_expectancy_r")),
        "evidence_grouping": "strategy_coverage",
        "evidence": matched_context,
        "reason": "strategy is sample-eligible but no non-neutral consolidated strategy policy row applies",
        "live_authority": False,
        "decision_impact": "NONE",
    }


def _format_context_evidence_row(row: dict[str, Any]) -> str:
    grouping = str(row.get("grouping") or "context")
    fields = grouping.split("|")
    labels = []

    for field in fields:
        if field == "strategy":
            continue
        value = row.get(field)
        if value not in (None, "", "UNKNOWN"):
            labels.append(f"{field}={value}")

    context_label = ", ".join(labels) if labels else grouping
    badge = str(row.get("badge") or "NEUTRAL")
    win_pct = row.get("win_quality_pct")
    sample_count = row.get("sample_count")
    exp_r = row.get("final_expectancy_r")

    win_text = "N/A" if win_pct is None else f"{float(win_pct):.1f}%"
    exp_text = "N/A" if exp_r is None else f"{float(exp_r):+.2f}R"

    return (
        f"- {context_label} | {badge} | "
        f"Win {win_text} | n={sample_count} | Exp {exp_text}"
    )


def format_setup_selection_advisory(advisory: dict[str, Any] | None) -> str:
    if not advisory:
        return ""

    badge = str(advisory.get("badge") or "NO_DATA")
    n = advisory.get("sample_count")
    min_resolved = advisory.get("min_resolved")
    needed = advisory.get("samples_needed")
    win_pct = advisory.get("win_quality_pct")
    exp_r = advisory.get("final_expectancy_r")
    grouping = advisory.get("evidence_grouping") or "N/A"

    win_text = "N/A" if win_pct is None else f"{float(win_pct):.1f}%"
    exp_text = "N/A" if exp_r is None else f"{float(exp_r):+.2f}R"

    lines = [
        f"[SETUP SELECTION] {badge}",
        f"Win Quality: {win_text}",
    ]

    if n is not None:
        if badge == "INSUFFICIENT_DATA" and min_resolved is not None:
            lines.append(f"Samples: {n}/{min_resolved} (need {needed} more)")
        else:
            lines.append(f"Samples: {n}")

    lines.extend(
        [
            f"Final Exp: {exp_text}",
            f"Evidence: {grouping}",
        ]
    )

    if badge == "MIXED_CONTEXT":
        evidence = [
            row
            for row in (advisory.get("evidence") or [])
            if str(row.get("badge") or "") not in ("", "NEUTRAL")
        ]

        # Keep Telegram concise. The resolver retains all evidence internally;
        # the alert displays the four largest statistically eligible context
        # buckets so the reason for MIXED_CONTEXT is visible at a glance.
        evidence.sort(
            key=lambda row: (
                -int(row.get("sample_count") or 0),
                str(row.get("grouping") or ""),
            )
        )

        if evidence:
            lines.append("Context Evidence:")
            for row in evidence[:4]:
                lines.append(_format_context_evidence_row(row))

            hidden = len(evidence) - 4
            if hidden > 0:
                lines.append(f"- +{hidden} additional eligible context bucket(s)")

    lines.append("Mode: ADVISORY ONLY")
    return "\n".join(lines)
# ============================================================
# Setup-selection out-of-sample shadow snapshot
# IMMUTABLE RESEARCH METADATA / NO EXECUTION AUTHORITY
# ============================================================

SETUP_SELECTION_SHADOW_SCHEMA_VERSION = 1


def normalize_setup_selection_stage(event: Any = None, extra: Any = None) -> str:
    """
    Map heterogeneous runtime events into the stage taxonomy used by the
    setup-selection research dataset.

    This is intentionally conservative. Unknown events become OTHER rather
    than being forced into an existing historical bucket.
    """
    extra = extra if isinstance(extra, dict) else {}

    explicit = (
        extra.get("stage")
        or extra.get("setup_stage")
        or extra.get("selection_stage")
    )
    if explicit:
        explicit_u = _safe_upper(explicit)
        aliases = {
            "SIGNAL DETECTED": "DETECTED",
            "SETUP DETECTED": "DETECTED",
            "REJECTED LOW RR": "LOW_RR",
            "REJECTED_LOW_RR": "LOW_RR",
            "LOW RR": "LOW_RR",
        }
        return aliases.get(explicit_u, explicit_u)

    event_u = _safe_upper(event)

    if "LOW_RR" in event_u or "LOW RR" in event_u:
        return "LOW_RR"
    if "EXECUT" in event_u:
        return "EXECUTED"
    if "BLOCK" in event_u or "REJECT" in event_u:
        return "BLOCKED"
    if "DETECT" in event_u:
        return "DETECTED"

    return "OTHER"


def build_setup_selection_shadow_snapshot(
    *,
    strategy: Any,
    direction: Any = None,
    entry_model: Any = None,
    session: Any = None,
    market_condition: Any = None,
    event: Any = None,
    stage: Any = None,
    extra: Any = None,
    account_name: str | None = None,
    min_resolved: int = DEFAULT_MIN_RESOLVED,
) -> dict[str, Any]:
    """
    Freeze the setup-selection evidence available at setup registration time.

    The returned object is research metadata only. It must never be used by
    execution, risk, position sizing, SL/TP, RR, or order-routing code.
    """
    from datetime import datetime, timezone

    normalized_stage = (
        _safe_upper(stage)
        if stage not in (None, "")
        else normalize_setup_selection_stage(event=event, extra=extra)
    )

    advisory = resolve_setup_selection_advisory(
        strategy=strategy,
        direction=direction,
        entry_model=entry_model,
        session=session,
        market_condition=market_condition,
        stage=normalized_stage,
        account_name=account_name,
        min_resolved=min_resolved,
    )

    snapshot = {
        "schema_version": SETUP_SELECTION_SHADOW_SCHEMA_VERSION,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "live_authority": False,
        "decision_impact": "NONE",
        "strategy": _safe_upper(strategy),
        "direction": _safe_upper(direction),
        "entry_model": _safe_upper(entry_model),
        "session": _safe_upper(session),
        "market_condition": _safe_upper(market_condition),
        "stage": normalized_stage,
        "event": _safe_upper(event),
        "badge": advisory.get("badge") if advisory else "NO_DATA",
        "coarse_stance": advisory.get("coarse_stance") if advisory else None,
        "sample_count": advisory.get("sample_count") if advisory else None,
        "min_resolved": advisory.get("min_resolved") if advisory else min_resolved,
        "samples_needed": advisory.get("samples_needed") if advisory else None,
        "win_quality": advisory.get("win_quality") if advisory else None,
        "win_quality_pct": advisory.get("win_quality_pct") if advisory else None,
        "final_expectancy_r": advisory.get("final_expectancy_r") if advisory else None,
        "w10_to_sl_rate": advisory.get("w10_to_sl_rate") if advisory else None,
        "evidence_grouping": advisory.get("evidence_grouping") if advisory else None,
        "reason": advisory.get("reason") if advisory else "no advisory resolved",
        "evidence": advisory.get("evidence") if advisory else [],
    }

    # Keep strategy baseline for later OOS attribution if available.
    if advisory and advisory.get("strategy_baseline") is not None:
        snapshot["strategy_baseline"] = advisory.get("strategy_baseline")

    return snapshot
