from __future__ import annotations

from typing import Any

from src.live_bias import get_live_bias_snapshot


# ============================================================
# SETUP QUALITY GRADE V1
#
# DISPLAY / OBSERVATION ONLY.
#
# The grade:
# - cannot execute
# - cannot block
# - cannot change score
# - cannot change risk
# - cannot modify entry / SL / TP
#
# It converts ALREADY-AVAILABLE setup evidence into a concise
# human-readable A / A+ quality label.
# ============================================================


A_PLUS_MIN_SCORE = 90.0
A_MIN_SCORE = 85.0

A_PLUS_MIN_CONFIRMATIONS = 4
A_MIN_CONFIRMATIONS = 3


def _safe_float(
    value,
    default=0.0,
):
    try:
        return float(value)
    except Exception:
        return default


def _as_list(value):
    if value is None:
        return []

    if isinstance(
        value,
        (list, tuple, set),
    ):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    text = str(value).strip()

    if not text:
        return []

    return [text]


def _normalized_unique(values):
    result = []
    seen = set()

    for value in _as_list(values):
        normalized = value.upper()

        if normalized in seen:
            continue

        seen.add(normalized)
        result.append(value)

    return result


def _directional_live_bias_state(
    signal,
    live_bias,
):
    signal = str(
        signal or ""
    ).upper()

    live_bias = str(
        live_bias or "UNKNOWN"
    ).upper()

    if signal == "BUY":
        aligned = (
            "BULLISH" in live_bias
        )
        strong_aligned = (
            live_bias == "BULLISH"
        )
        conflict = (
            "BEARISH" in live_bias
        )

    elif signal == "SELL":
        aligned = (
            "BEARISH" in live_bias
        )
        strong_aligned = (
            live_bias == "BEARISH"
        )
        conflict = (
            "BULLISH" in live_bias
        )

    else:
        aligned = False
        strong_aligned = False
        conflict = False

    return {
        "aligned": aligned,
        "strong_aligned": strong_aligned,
        "conflict": conflict,
    }


def _has_strategy_confluence(data):
    strategies = (
        _normalized_unique(
            data.get(
                "confluence_strategies"
            )
        )
    )

    return (
        len(strategies) >= 2
    )


def _has_key_level_confirmation(data):
    supply_demand = _as_list(
        data.get(
            "supply_demand_reasons"
        )
    )

    if supply_demand:
        return True

    reason = str(
        data.get(
            "reason",
            "",
        )
        or ""
    ).upper()

    return (
        "SUPPLY/DEMAND:" in reason
        or "KEY LEVEL" in reason
    )


def _has_liquidity_confirmation(data):
    structure_liquidity = (
        _as_list(
            data.get(
                "structure_liquidity_reasons"
            )
        )
    )

    if structure_liquidity:
        return True

    smc = [
        item.lower()
        for item in _as_list(
            data.get("smc")
        )
    ]

    if any(
        (
            "liquidity" in item
            or "sweep" in item
        )
        for item in smc
    ):
        return True

    reason = str(
        data.get(
            "reason",
            "",
        )
        or ""
    ).lower()

    return (
        "liquidity" in reason
        or "sweep" in reason
    )


def _has_structure_confirmation(
    data,
    signal,
):
    smc = {
        item.lower()
        for item in _as_list(
            data.get("smc")
        )
    }

    has_displacement = (
        "displacement" in smc
    )

    signal = str(
        signal or ""
    ).upper()

    if signal == "BUY":
        has_directional_structure = (
            "bullish_bos" in smc
        )

    elif signal == "SELL":
        has_directional_structure = (
            "bearish_bos" in smc
        )

    else:
        has_directional_structure = False

    return (
        has_displacement
        and has_directional_structure
    )


def _elliott_fib_state(data):
    reasons = _as_list(
        data.get(
            "elliott_fib_reasons"
        )
    )

    if not reasons:
        return {
            "confirmed": False,
            "conflict": False,
        }

    normalized = " ".join(
        reasons
    ).lower()

    conflict = (
        "conflict" in normalized
    )

    return {
        "confirmed": not conflict,
        "conflict": conflict,
    }


def _authority_fields():
    return {
        "decision_impact": "DISPLAY_ONLY",
        "can_execute": False,
        "can_block_trade": False,
        "can_modify_score": False,
        "can_modify_risk": False,
        "can_modify_entry_sl_tp": False,
    }


def build_setup_quality_grade(
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a conservative A / A+ display grade.

    The existing bot score remains untouched.

    A+:
    - score >= 90
    - strong Live Bias alignment
    - at least 4 independent confirmation buckets
    - key-level or liquidity confirmation
    - no directional/conflict evidence

    A:
    - score >= 85
    - Live Bias directionally aligned
    - at least 3 independent confirmation buckets
    - key-level or liquidity confirmation
    - no directional/conflict evidence

    Anything below these standards receives no premium grade.
    """

    data = dict(
        data or {}
    )

    signal = str(
        data.get(
            "signal",
            "",
        )
        or ""
    ).upper()

    score = _safe_float(
        data.get(
            "score",
            0,
        ),
        0.0,
    )

    score = max(
        0.0,
        min(100.0, score),
    )

    score_10 = round(
        score / 10.0,
        1,
    )

    symbol = data.get(
        "symbol"
    )

    market_condition = data.get(
        "market_condition",
        "UNKNOWN",
    )

    live_bias_snapshot = None

    if (
        symbol
        and signal in {
            "BUY",
            "SELL",
        }
    ):
        try:
            live_bias_snapshot = (
                get_live_bias_snapshot(
                    symbol,
                    market_condition,
                )
            )
        except Exception:
            # Fail-open:
            # setup alert must never fail because the
            # informational grader could not load context.
            live_bias_snapshot = None

    live_bias = "UNKNOWN"
    live_bias_coverage = 0

    if isinstance(
        live_bias_snapshot,
        dict,
    ):
        live_bias = str(
            live_bias_snapshot.get(
                "bias",
                "UNKNOWN",
            )
            or "UNKNOWN"
        ).upper()

        try:
            live_bias_coverage = int(
                live_bias_snapshot.get(
                    "coverage",
                    0,
                )
                or 0
            )
        except Exception:
            live_bias_coverage = 0

    directional = (
        _directional_live_bias_state(
            signal,
            live_bias,
        )
    )

    strategy_confluence = (
        _has_strategy_confluence(
            data
        )
    )

    key_level = (
        _has_key_level_confirmation(
            data
        )
    )

    liquidity = (
        _has_liquidity_confirmation(
            data
        )
    )

    structure = (
        _has_structure_confirmation(
            data,
            signal,
        )
    )

    elliott_fib = (
        _elliott_fib_state(
            data
        )
    )

    confirmations = []

    if directional["aligned"]:
        confirmations.append(
            "Live Bias aligned"
        )

    if strategy_confluence:
        confirmations.append(
            "Multi-strategy confluence"
        )

    if key_level:
        confirmations.append(
            "Key level"
        )

    if liquidity:
        confirmations.append(
            "Liquidity confirmation"
        )

    if structure:
        confirmations.append(
            "Structure confirmation"
        )

    if elliott_fib[
        "confirmed"
    ]:
        confirmations.append(
            "Elliott/Fib confluence"
        )

    conflict = (
        directional["conflict"]
        or elliott_fib["conflict"]
    )

    has_required_location_context = (
        key_level
        or liquidity
    )

    confirmation_count = len(
        confirmations
    )

    grade = None

    if (
        not conflict
        and score
        >= A_PLUS_MIN_SCORE
        and directional[
            "strong_aligned"
        ]
        and confirmation_count
        >= A_PLUS_MIN_CONFIRMATIONS
        and has_required_location_context
    ):
        grade = "A+"

    elif (
        not conflict
        and score
        >= A_MIN_SCORE
        and directional[
            "aligned"
        ]
        and confirmation_count
        >= A_MIN_CONFIRMATIONS
        and has_required_location_context
    ):
        grade = "A"

    result = {
        "grade": grade,
        "score_raw": round(
            score,
            2,
        ),
        "score_10": score_10,
        "confirmations": confirmations,
        "confirmation_count": (
            confirmation_count
        ),
        "live_bias": live_bias,
        "live_bias_coverage": (
            live_bias_coverage
        ),
        "live_bias_aligned": (
            directional["aligned"]
        ),
        "live_bias_strong_aligned": (
            directional[
                "strong_aligned"
            ]
        ),
        "strategy_confluence": (
            strategy_confluence
        ),
        "key_level_confirmation": (
            key_level
        ),
        "liquidity_confirmation": (
            liquidity
        ),
        "structure_confirmation": (
            structure
        ),
        "elliott_fib_confirmation": (
            elliott_fib["confirmed"]
        ),
        "conflict": conflict,
        "reason": (
            "premium_grade"
            if grade
            else "premium_grade_not_met"
        ),
    }

    result.update(
        _authority_fields()
    )

    return result


def format_setup_quality_block(
    result: dict[str, Any],
) -> str:
    result = dict(
        result or {}
    )

    grade = result.get(
        "grade"
    )

    if grade not in {
        "A",
        "A+",
    }:
        return ""

    score_10 = result.get(
        "score_10",
        0,
    )

    reasons = list(
        result.get(
            "confirmations",
            [],
        )
        or []
    )

    # Keep Telegram concise.
    reasons = reasons[:4]

    why = (
        " | ".join(reasons)
        if reasons
        else "Premium setup criteria met"
    )

    return (
        f"\u2b50 {grade} SETUP\n"
        f"Score: {score_10:.1f}/10\n"
        f"Why: {why}"
    )

# ============================================================
# SETUP QUALITY GRADE V2 — HISTORICAL EDGE GATE
# DISPLAY / OBSERVATION ONLY.
# ============================================================

import json as _sq2_json
import math as _sq2_math
import os as _sq2_os
from pathlib import Path as _Sq2Path
import statistics as _sq2_stats


SQ2_A_PLUS_MIN_RR = 1.50
SQ2_A_MIN_RR = 1.20
SQ2_F_RR_THRESHOLD = 1.00

SQ2_MIN_TRADE_SAMPLE = 20
SQ2_MIN_TRADE_WIN_RATE = 0.75

SQ2_MIN_PATH_SAMPLE = 20
SQ2_MIN_HIT_PLUS_10_RATE = 0.75

_SQ2_CACHE = {}


def _sq2_float(value):
    try:
        value = float(value)
    except Exception:
        return None
    return value if _sq2_math.isfinite(value) else None


def _sq2_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _sq2_strategy(row):
    if not isinstance(row, dict):
        return ""
    for key in ("strategy", "strategy_name", "Strategy", "STRATEGY"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip().upper()
    return ""


def _sq2_signal(row):
    if not isinstance(row, dict):
        return ""
    return str(row.get("signal", "") or "").strip().upper()


def _sq2_setup_id(row):
    if not isinstance(row, dict):
        return ""
    for key in ("setup_id", "setupId", "signal_id", "id"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _sq2_flatten(payload):
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("records", "items", "trades", "outcomes", "setup_outcomes", "setups"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if payload and all(isinstance(value, dict) for value in payload.values()):
            return list(payload.values())
    return []


def _sq2_repo_root():
    return _Sq2Path(__file__).resolve().parents[1]


def _sq2_resolve_account_dir(data):
    explicit = data.get("setup_quality_account_dir") or _sq2_os.getenv("SETUP_QUALITY_ACCOUNT_DIR")
    if explicit:
        path = _Sq2Path(explicit)
        if not path.is_absolute():
            path = _sq2_repo_root() / path
        if (path / "trades.json").exists() and (path / "setup_outcomes.json").exists():
            return path

    base = _sq2_repo_root() / "data" / "accounts"
    if not base.exists():
        return None

    candidates = [
        path for path in base.iterdir()
        if path.is_dir()
        and (path / "trades.json").exists()
        and (path / "setup_outcomes.json").exists()
    ]

    hints = []
    for key in ("account", "account_id", "account_login", "login", "mt5_login", "account_key"):
        value = data.get(key)
        if value not in (None, ""):
            hints.append(str(value).strip().lower())

    if hints:
        matched = [
            path for path in candidates
            if any(
                hint == path.name.lower()
                or hint in path.name.lower()
                or path.name.lower() in hint
                for hint in hints
            )
        ]
        if len(matched) == 1:
            return matched[0]

    if len(candidates) == 1:
        return candidates[0]

    return None


def _sq2_rows(path):
    try:
        stat = path.stat()
    except Exception:
        return None

    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key in _SQ2_CACHE:
        return _SQ2_CACHE[key]

    try:
        payload = _sq2_json.loads(path.read_text(encoding="utf-8", errors="replace"))
        rows = _sq2_flatten(payload)
    except Exception:
        return None

    for old in list(_SQ2_CACHE):
        if old[0] == str(path) and old != key:
            _SQ2_CACHE.pop(old, None)

    _SQ2_CACHE[key] = rows
    return rows


def _sq2_trade_class(row):
    for key in ("realized_profit", "profit", "pnl", "net_profit"):
        value = _sq2_float(row.get(key))
        if value is not None:
            if value > 0:
                return "WIN"
            if value < 0:
                return "LOSS"
            return "BE"

    reason = str(
        row.get("close_reason", "")
        or row.get("final_result", "")
        or ""
    ).strip().upper()

    if reason in {"PROFIT_CLOSE", "TAKE_PROFIT", "TP", "SL_IN_PROFIT"}:
        return "WIN"
    if reason in {"SL_LOSS", "STOP_LOSS", "SL", "LOSS"}:
        return "LOSS"
    if reason in {"SL_BREAKEVEN", "BREAKEVEN", "BREAK_EVEN", "BE"}:
        return "BE"
    return "UNRESOLVED"


def _sq2_dedupe_trades(rows):
    chosen = {}
    for row in rows:
        setup_id = _sq2_setup_id(row)
        if not setup_id:
            continue
        old = chosen.get(setup_id)
        if old is None:
            chosen[setup_id] = row
            continue
        old_time = str(old.get("close_time", "") or old.get("open_time", "") or "")
        row_time = str(row.get("close_time", "") or row.get("open_time", "") or "")
        if row_time >= old_time:
            chosen[setup_id] = row
    return list(chosen.values())


def _sq2_trade_stats(rows, strategy, signal):
    strategy_rows = _sq2_dedupe_trades([
        row for row in rows
        if _sq2_strategy(row) == strategy
    ])

    def summarize(items):
        wins = 0
        losses = 0
        for row in items:
            result = _sq2_trade_class(row)
            if result == "WIN":
                wins += 1
            elif result == "LOSS":
                losses += 1
        sample = wins + losses
        return {
            "sample": sample,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / sample if sample else None,
        }

    signal_stats = summarize([
        row for row in strategy_rows
        if _sq2_signal(row) == signal
    ])
    if signal_stats["sample"] >= SQ2_MIN_TRADE_SAMPLE:
        signal_stats["scope"] = "STRATEGY_SIGNAL"
        return signal_stats

    stats = summarize(strategy_rows)
    stats["scope"] = "STRATEGY_FALLBACK"
    return stats


def _sq2_percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * q
    low = int(_sq2_math.floor(position))
    high = int(_sq2_math.ceil(position))
    if low == high:
        return values[low]
    fraction = position - low
    return values[low] * (1.0 - fraction) + values[high] * fraction


def _sq2_current_created(data):
    for key in ("created_at", "setup_created_at", "timestamp", "time"):
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _sq2_is_historical(row, data):
    current_id = _sq2_setup_id(data)
    if current_id and _sq2_setup_id(row) == current_id:
        return False

    current_created = _sq2_current_created(data)
    row_created = str(row.get("created_at", "") or "")
    if current_created and row_created and row_created >= current_created:
        return False

    return True


def _sq2_path_stats(rows, data, strategy, signal):
    strategy_rows = [
        row for row in rows
        if _sq2_strategy(row) == strategy
        and _sq2_is_historical(row, data)
    ]

    def measured(items):
        result = []
        for row in items:
            hit = _sq2_bool(row.get("hit_plus_10"))
            if hit is not None:
                result.append((row, hit))
        return result

    signal_rows = measured([
        row for row in strategy_rows
        if _sq2_signal(row) == signal
    ])

    if len(signal_rows) >= SQ2_MIN_PATH_SAMPLE:
        cohort = signal_rows
        scope = "STRATEGY_SIGNAL"
    else:
        cohort = measured(strategy_rows)
        scope = "STRATEGY_FALLBACK"

    sample = len(cohort)
    hits = sum(1 for _, hit in cohort if hit)

    adverse = []
    recovery = []
    for row, _ in cohort:
        value = _sq2_float(row.get("max_adverse_usd"))
        if value is not None:
            adverse.append(abs(value))
        value = _sq2_float(row.get("max_recovery_swing_usd"))
        if value is not None:
            recovery.append(abs(value))

    return {
        "scope": scope,
        "sample": sample,
        "hit_plus_10_rate": hits / sample if sample else None,
        "mae_median": _sq2_stats.median(adverse) if adverse else None,
        "mae_p75": _sq2_percentile(adverse, 0.75) if adverse else None,
        "recovery_median": _sq2_stats.median(recovery) if recovery else None,
    }


def _sq2_history_override(data):
    value = data.get("setup_quality_history_override")
    if not isinstance(value, dict):
        return None

    trade_sample = int(value.get("trade_sample", 0) or 0)
    trade_rate = _sq2_float(value.get("trade_win_rate"))
    path_sample = int(value.get("path_sample", 0) or 0)
    path_rate = _sq2_float(value.get("hit_plus_10_rate"))

    passed = bool(
        trade_sample >= SQ2_MIN_TRADE_SAMPLE
        and trade_rate is not None
        and trade_rate >= SQ2_MIN_TRADE_WIN_RATE
        and path_sample >= SQ2_MIN_PATH_SAMPLE
        and path_rate is not None
        and path_rate >= SQ2_MIN_HIT_PLUS_10_RATE
    )

    return {
        "available": True,
        "source": "OVERRIDE",
        "trade_scope": value.get("trade_scope", "OVERRIDE"),
        "trade_sample": trade_sample,
        "trade_win_rate": trade_rate,
        "path_scope": value.get("path_scope", "OVERRIDE"),
        "path_sample": path_sample,
        "hit_plus_10_rate": path_rate,
        "mae_median": _sq2_float(value.get("mae_median")),
        "mae_p75": _sq2_float(value.get("mae_p75")),
        "recovery_median": _sq2_float(value.get("recovery_median")),
        "history_pass": passed,
    }


def _sq2_history(data):
    override = _sq2_history_override(data)
    if override is not None:
        return override

    strategy = _sq2_strategy(data)
    signal = _sq2_signal(data)
    if not strategy or signal not in {"BUY", "SELL"}:
        return {"available": False, "source": "MISSING_CONTEXT", "history_pass": False}

    account_dir = _sq2_resolve_account_dir(data)
    if account_dir is None:
        return {"available": False, "source": "ACCOUNT_UNRESOLVED", "history_pass": False}

    trades = _sq2_rows(account_dir / "trades.json")
    outcomes = _sq2_rows(account_dir / "setup_outcomes.json")
    if trades is None or outcomes is None:
        return {"available": False, "source": "HISTORY_READ_FAILED", "history_pass": False}

    trade = _sq2_trade_stats(trades, strategy, signal)
    path = _sq2_path_stats(outcomes, data, strategy, signal)

    trade_rate = trade.get("win_rate")
    path_rate = path.get("hit_plus_10_rate")
    passed = bool(
        trade.get("sample", 0) >= SQ2_MIN_TRADE_SAMPLE
        and trade_rate is not None
        and trade_rate >= SQ2_MIN_TRADE_WIN_RATE
        and path.get("sample", 0) >= SQ2_MIN_PATH_SAMPLE
        and path_rate is not None
        and path_rate >= SQ2_MIN_HIT_PLUS_10_RATE
    )

    return {
        "available": True,
        "source": account_dir.name,
        "trade_scope": trade.get("scope"),
        "trade_sample": trade.get("sample", 0),
        "trade_win_rate": trade_rate,
        "path_scope": path.get("scope"),
        "path_sample": path.get("sample", 0),
        "hit_plus_10_rate": path_rate,
        "mae_median": path.get("mae_median"),
        "mae_p75": path.get("mae_p75"),
        "recovery_median": path.get("recovery_median"),
        "history_pass": passed,
    }


def _sq2_dicts(data):
    queue = [data]
    seen = set()
    while queue:
        item = queue.pop(0)
        if not isinstance(item, dict):
            continue
        ident = id(item)
        if ident in seen:
            continue
        seen.add(ident)
        yield item
        for value in item.values():
            if isinstance(value, dict):
                queue.append(value)


def _sq2_full_rr(data):
    for item in _sq2_dicts(data):
        for key in ("full_rr", "rr", "rr_value", "risk_reward", "risk_reward_ratio", "full_risk_reward", "tp3_rr"):
            value = _sq2_float(item.get(key))
            if value is not None:
                return value

    def find(keys):
        for item in _sq2_dicts(data):
            for key in keys:
                value = _sq2_float(item.get(key))
                if value is not None:
                    return value
        return None

    entry = find(("entry", "entry_price"))
    sl = find(("sl", "stop_loss"))
    tp = find(("tp", "take_profit"))
    if entry is None or sl is None or tp is None:
        return None

    risk = abs(entry - sl)
    if risk <= 0:
        return None
    return abs(tp - entry) / risk


def _sq2_text(value, depth=0):
    if depth > 5:
        return []
    if isinstance(value, dict):
        result = []
        for key, child in value.items():
            result.append(str(key))
            result.extend(_sq2_text(child, depth + 1))
        return result
    if isinstance(value, (list, tuple, set)):
        result = []
        for child in value:
            result.extend(_sq2_text(child, depth + 1))
        return result
    return [] if value is None else [str(value)]


def _sq2_macro_conflict(data, signal):
    token = f"conflict_{signal.lower()}"
    return token in " ".join(_sq2_text(data)).lower()


def _sq2_participation_unresolved(data):
    def walk(value, depth=0):
        if depth > 5:
            return False
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key).lower()
                if (
                    "participation" in key_text
                    or "pressure" in key_text
                    or "combined_state" in key_text
                ) and "UNRESOLVED" in str(child).upper():
                    return True
                if walk(child, depth + 1):
                    return True
        elif isinstance(value, (list, tuple)):
            return any(walk(child, depth + 1) for child in value)
        return False
    return walk(data)


_build_setup_quality_grade_v1 = build_setup_quality_grade


def build_setup_quality_grade(data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data or {})
    result = dict(_build_setup_quality_grade_v1(data) or {})

    # V2 applies only to identified real setups. This preserves the V1
    # public surface for legacy/synthetic callers and existing observers.
    if not _sq2_setup_id(data):
        result["setup_quality_version"] = "V1_COMPAT"
        return result

    signal = _sq2_signal(data)
    rr = _sq2_full_rr(data)
    history = _sq2_history(data)
    macro_conflict = _sq2_macro_conflict(data, signal)
    participation_unresolved = _sq2_participation_unresolved(data)

    base_grade = result.get("grade")
    score = _sq2_float(result.get("score_raw")) or 0.0

    blockers = []

    if rr is None:
        blockers.append("RR unavailable")
    elif rr < SQ2_A_PLUS_MIN_RR:
        blockers.append(f"RR {rr:.2f}R < {SQ2_A_PLUS_MIN_RR:.2f}R A+")

    if not history.get("available", False):
        blockers.append("Historical edge unavailable")
    else:
        trade_sample = int(history.get("trade_sample", 0) or 0)
        trade_rate = _sq2_float(history.get("trade_win_rate"))
        path_sample = int(history.get("path_sample", 0) or 0)
        path_rate = _sq2_float(history.get("hit_plus_10_rate"))

        if trade_sample < SQ2_MIN_TRADE_SAMPLE:
            blockers.append(f"Trade history n={trade_sample} < {SQ2_MIN_TRADE_SAMPLE}")
        elif trade_rate is None or trade_rate < SQ2_MIN_TRADE_WIN_RATE:
            blockers.append(
                "Historical win rate unavailable"
                if trade_rate is None
                else f"Historical win rate {trade_rate * 100:.1f}% < {SQ2_MIN_TRADE_WIN_RATE * 100:.0f}%"
            )

        if path_sample < SQ2_MIN_PATH_SAMPLE:
            blockers.append(f"Path history n={path_sample} < {SQ2_MIN_PATH_SAMPLE}")
        elif path_rate is None or path_rate < SQ2_MIN_HIT_PLUS_10_RATE:
            blockers.append(
                "Historical +10 rate unavailable"
                if path_rate is None
                else f"Historical +10 rate {path_rate * 100:.1f}% < {SQ2_MIN_HIT_PLUS_10_RATE * 100:.0f}%"
            )

    if macro_conflict:
        blockers.append("Macro conflict")
    if participation_unresolved:
        blockers.append("Participation unresolved")

    a_plus_pass = bool(
        base_grade == "A+"
        and rr is not None
        and rr >= SQ2_A_PLUS_MIN_RR
        and history.get("history_pass", False)
        and not macro_conflict
        and not participation_unresolved
    )

    hard_f = bool(rr is not None and rr < SQ2_F_RR_THRESHOLD)
    if macro_conflict and rr is not None and rr < SQ2_A_MIN_RR:
        hard_f = True

    if a_plus_pass:
        grade = "A+"
    elif hard_f:
        grade = "F"
    elif (
        base_grade in {"A+", "A"}
        and rr is not None
        and rr >= SQ2_A_MIN_RR
        and not macro_conflict
        and not participation_unresolved
    ):
        grade = "A"
    elif base_grade in {"A+", "A"} and rr is not None and rr >= 1.00:
        grade = "B"
    elif score >= 85.0 and rr is not None and rr >= 1.00:
        grade = "C"
    elif score >= 70.0:
        grade = "D"
    else:
        grade = "F"

    result.update(
        {
            "grade": grade,
            "setup_quality_version": "V2",
            "v1_grade": base_grade,
            "full_rr": round(rr, 4) if rr is not None else None,
            "historical_edge": history,
            "historical_edge_pass": bool(history.get("history_pass", False)),
            "macro_conflict": macro_conflict,
            "participation_unresolved": participation_unresolved,
            "grade_blockers": blockers,
            "reason": "a_plus_proven_edge" if grade == "A+" else "v2_quality_grade",
        }
    )

    result.update(_authority_fields())
    return result


_format_setup_quality_block_v1 = format_setup_quality_block


def _sq2_pct(value):
    value = _sq2_float(value)
    return "N/A" if value is None else f"{value * 100:.1f}%"


def format_setup_quality_block(result: dict[str, Any]) -> str:
    result = dict(result or {})

    if result.get("setup_quality_version") != "V2":
        return _format_setup_quality_block_v1(result)

    grade = str(result.get("grade", "") or "")
    if grade not in {"A+", "A", "B", "C", "D", "F"}:
        return ""

    if grade in {"A+", "A"}:
        icon = "\u2b50"
    elif grade == "F":
        icon = "\U0001f7e5"
    else:
        icon = "\U0001f539"

    score_10 = _sq2_float(result.get("score_10")) or 0.0
    rr = _sq2_float(result.get("full_rr"))
    rr_text = f"{rr:.2f}R" if rr is not None else "N/A"

    blockers = list(result.get("grade_blockers", []) or [])
    if blockers:
        why = " | ".join(blockers[:3])
    else:
        confirmations = list(result.get("confirmations", []) or [])
        why = " | ".join(confirmations[:3]) if confirmations else "V2 setup-quality criteria"

    history = dict(result.get("historical_edge", {}) or {})
    trade_sample = int(history.get("trade_sample", 0) or 0)
    path_sample = int(history.get("path_sample", 0) or 0)

    history_line = (
        "History: "
        f"Win {_sq2_pct(history.get('trade_win_rate'))} (n={trade_sample}) | "
        f"+10 {_sq2_pct(history.get('hit_plus_10_rate'))} (n={path_sample})"
    )

    mae = _sq2_float(history.get("mae_median"))
    if mae is not None:
        history_line += f" | MAE med ${mae:.2f}"

    return (
        f"{icon} {grade} SETUP\n"
        f"Raw Score: {score_10:.1f}/10 | Full RR: {rr_text}\n"
        f"Why: {why}\n"
        f"{history_line}"
    )
