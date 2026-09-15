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
