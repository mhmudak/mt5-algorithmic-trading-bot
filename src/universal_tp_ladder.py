from __future__ import annotations

import math
from typing import Any

from config.settings import (
    ENABLE_UNIVERSAL_TP_LADDER,
    UNIVERSAL_TP1_MAX_RR,
    UNIVERSAL_TP1_REWARD_FRACTION,
    UNIVERSAL_TP2_MAX_RR,
    UNIVERSAL_TP2_REWARD_FRACTION,
)


def safe_float(
    value: Any,
    default: float | None = None,
) -> float | None:
    try:
        if value is None:
            return default

        numeric = float(value)

        if not math.isfinite(numeric):
            return default

        return numeric

    except Exception:
        return default


def calculate_rr(
    signal: str,
    entry: float,
    sl: float,
    tp: float,
) -> float | None:
    try:
        entry = float(entry)
        sl = float(sl)
        tp = float(tp)

    except Exception:
        return None

    if signal == "BUY":
        risk = entry - sl
        reward = tp - entry

    elif signal == "SELL":
        risk = sl - entry
        reward = entry - tp

    else:
        return None

    if risk <= 0 or reward <= 0:
        return None

    return round(
        reward / risk,
        2,
    )


def _directional_prices_valid(
    signal,
    entry,
    prices,
):
    try:
        entry = float(entry)

        p1, p2, p3 = [
            float(item)
            for item in prices[:3]
        ]

    except Exception:
        return False

    if signal == "BUY":
        return (
            entry
            < p1
            < p2
            < p3
        )

    if signal == "SELL":
        return (
            entry
            > p1
            > p2
            > p3
        )

    return False


def _extract_existing_ladder(
    signal,
    entry,
    trade_plan,
):
    ladder = trade_plan.get(
        "tp_ladder"
    )

    if (
        not isinstance(
            ladder,
            list,
        )
        or len(ladder) < 3
    ):
        return None

    prices = []

    for item in ladder[:3]:
        if not isinstance(
            item,
            dict,
        ):
            return None

        price = safe_float(
            item.get(
                "price",
                item.get(
                    "take_profit"
                ),
            )
        )

        if price is None:
            return None

        prices.append(
            price
        )

    if not _directional_prices_valid(
        signal,
        entry,
        prices,
    ):
        return None

    return ladder


def _select_tp3_target(
    trade_plan,
):
    for key in (
        "decision_take_profit",
        "original_take_profit",
        "take_profit",
    ):
        value = safe_float(
            trade_plan.get(key)
        )

        if value is not None:
            return value

    return None


def build_universal_tp_ladder(
    *,
    signal,
    entry,
    sl,
    tp3,
    allow_visual_without_sl=False,
):
    """
    Build management-only TP1/TP2 stages inside TP3.

    High full-RR:
      TP1 <= 1R
      TP2 <= 2R

    Lower full-RR:
      TP1 = 50% of original reward
      TP2 = 75% of original reward

    TP3 is never changed.
    """
    if not ENABLE_UNIVERSAL_TP_LADDER:
        return None

    entry = safe_float(entry)
    sl = safe_float(sl)
    tp3 = safe_float(tp3)

    if (
        entry is None
        or tp3 is None
    ):
        return None

    if signal == "BUY":
        reward = (
            tp3 - entry
        )

    elif signal == "SELL":
        reward = (
            entry - tp3
        )

    else:
        return None

    if reward <= 0:
        return None

    risk = None

    if sl is not None:
        if signal == "BUY":
            candidate_risk = (
                entry - sl
            )

        else:
            candidate_risk = (
                sl - entry
            )

        if candidate_risk > 0:
            risk = candidate_risk

    if (
        risk is None
        and not allow_visual_without_sl
    ):
        return None

    if risk is None:
        tp1_distance = (
            reward
            * float(
                UNIVERSAL_TP1_REWARD_FRACTION
            )
        )

        tp2_distance = (
            reward
            * float(
                UNIVERSAL_TP2_REWARD_FRACTION
            )
        )

    else:
        tp1_distance = min(
            risk
            * float(
                UNIVERSAL_TP1_MAX_RR
            ),
            reward
            * float(
                UNIVERSAL_TP1_REWARD_FRACTION
            ),
        )

        tp2_distance = min(
            risk
            * float(
                UNIVERSAL_TP2_MAX_RR
            ),
            reward
            * float(
                UNIVERSAL_TP2_REWARD_FRACTION
            ),
        )

    if signal == "BUY":
        tp1 = round(
            entry + tp1_distance,
            2,
        )

        tp2 = round(
            entry + tp2_distance,
            2,
        )

    else:
        tp1 = round(
            entry - tp1_distance,
            2,
        )

        tp2 = round(
            entry - tp2_distance,
            2,
        )

    tp3 = round(
        tp3,
        2,
    )

    if not _directional_prices_valid(
        signal,
        entry,
        (
            tp1,
            tp2,
            tp3,
        ),
    ):
        return None

    tp1_rr = (
        calculate_rr(
            signal,
            entry,
            sl,
            tp1,
        )
        if risk is not None
        else None
    )

    tp2_rr = (
        calculate_rr(
            signal,
            entry,
            sl,
            tp2,
        )
        if risk is not None
        else None
    )

    tp3_rr = (
        calculate_rr(
            signal,
            entry,
            sl,
            tp3,
        )
        if risk is not None
        else None
    )

    return [
        {
            "name": (
                "TP1_UNIVERSAL_PROFIT_REALIZATION"
            ),
            "price": tp1,
            "rr": tp1_rr,
            "action": (
                "partial_profit_management_only"
            ),
        },
        {
            "name": (
                "TP2_UNIVERSAL_SCALE_OUT"
            ),
            "price": tp2,
            "rr": tp2_rr,
            "action": (
                "partial_profit_management_only"
            ),
        },
        {
            "name": (
                "TP3_ORIGINAL_STRATEGY_TARGET"
            ),
            "price": tp3,
            "rr": tp3_rr,
            "action": (
                "original_strategy_target_"
                "and_rr_authority"
            ),
        },
    ]


def _build_summary(
    ladder,
):
    if (
        not isinstance(
            ladder,
            list,
        )
        or len(ladder) < 3
    ):
        return None

    return (
        f"TP1 {ladder[0].get('price')} | "
        f"TP2 {ladder[1].get('price')} | "
        f"TP3 {ladder[2].get('price')}"
    )


def ensure_universal_tp_ladder(
    signal,
    trade_plan,
    *,
    source="UNIVERSAL",
    geometry_phase=None,
):
    """
    Add TP metadata only.

    This function does NOT:
      - change take_profit
      - change original_take_profit
      - change rr
      - change risk_reward
      - change original_rr
      - approve/block execution

    Existing valid structural ladders always win.
    """
    if not isinstance(
        trade_plan,
        dict,
    ):
        return trade_plan

    adjusted = dict(
        trade_plan
    )

    if not ENABLE_UNIVERSAL_TP_LADDER:
        return adjusted

    entry = safe_float(
        adjusted.get(
            "entry_price"
        )
    )

    existing = (
        _extract_existing_ladder(
            signal,
            entry,
            adjusted,
        )
        if entry is not None
        else None
    )

    if existing is not None:
        adjusted[
            "universal_tp_ladder_preserved_existing"
        ] = True

        adjusted[
            "universal_tp_ladder_generated"
        ] = False

        return adjusted

    tp3 = _select_tp3_target(
        adjusted
    )

    ladder = (
        build_universal_tp_ladder(
            signal=signal,
            entry=entry,
            sl=adjusted.get(
                "stop_loss"
            ),
            tp3=tp3,
            allow_visual_without_sl=False,
        )
    )

    if ladder is None:
        return adjusted

    adjusted[
        "tp_ladder"
    ] = ladder

    adjusted[
        "tp_plan_summary"
    ] = _build_summary(
        ladder
    )

    adjusted[
        "universal_tp_ladder_applied"
    ] = True

    adjusted[
        "universal_tp_ladder_generated"
    ] = True

    adjusted[
        "universal_tp_ladder_source"
    ] = source

    adjusted[
        "universal_tp3_decision_target"
    ] = ladder[2][
        "price"
    ]

    if geometry_phase:
        adjusted[
            "tp_ladder_geometry_phase"
        ] = geometry_phase

    return adjusted


def format_tp_plan_from_levels(
    signal,
    entry,
    sl,
    tp,
):
    ladder = build_universal_tp_ladder(
        signal=signal,
        entry=entry,
        sl=sl,
        tp3=tp,
        allow_visual_without_sl=True,
    )

    if ladder is None:
        return (
            f"TP: {tp}"
        )

    return format_tp_ladder(
        ladder
    )


def format_tp_ladder(
    ladder,
):
    if (
        not isinstance(
            ladder,
            list,
        )
        or len(ladder) < 3
    ):
        return "TP Plan: unavailable"

    lines = [
        "TP Plan:",
    ]

    for index, item in enumerate(
        ladder[:3],
        start=1,
    ):
        price = item.get(
            "price",
            item.get(
                "take_profit"
            ),
        )

        rr = item.get(
            "rr"
        )

        rr_text = (
            rr
            if rr is not None
            else "N/A"
        )

        # Internal ladder names remain stored in metadata,
        # but Telegram/output should stay human-readable.
        lines.append(
            f"TP{index}: {price} "
            f"| RR {rr_text}"
        )

    return "\n".join(
        lines
    )


def format_tp_plan_from_trade_plan(
    signal,
    trade_plan,
):
    if not isinstance(
        trade_plan,
        dict,
    ):
        return "TP Plan: unavailable"

    entry = safe_float(
        trade_plan.get(
            "entry_price"
        )
    )

    existing = (
        _extract_existing_ladder(
            signal,
            entry,
            trade_plan,
        )
        if entry is not None
        else None
    )

    if existing is not None:
        return format_tp_ladder(
            existing
        )

    tp3 = _select_tp3_target(
        trade_plan
    )

    ladder = build_universal_tp_ladder(
        signal=signal,
        entry=entry,
        sl=trade_plan.get(
            "stop_loss"
        ),
        tp3=tp3,
        allow_visual_without_sl=True,
    )

    if ladder is not None:
        return format_tp_ladder(
            ladder
        )

    return (
        f"TP: "
        f"{trade_plan.get('take_profit')}"
    )
