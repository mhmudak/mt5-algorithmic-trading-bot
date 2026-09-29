from __future__ import annotations

from math import isfinite
from typing import Any


MODEL = "RITHMIC_NUMERIC_SHADOW_PLAN_V1"

SUPPORTED_ALIGNMENT = "SUPPORTS_SETUP"


def _authority() -> dict[str, Any]:
    return {
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "execution_allowed": False,
        "trade_action": "NO_AUTO_TRADE",
        "can_modify_entry": False,
        "can_modify_sl": False,
        "can_modify_tp": False,
        "can_modify_size": False,
    }


def _finite_float(
    value: Any,
) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not isfinite(result):
        return None

    return result


def _positive_float(
    value: Any,
) -> float | None:
    result = _finite_float(value)

    if (
        result is None
        or result <= 0
    ):
        return None

    return result


def _normalize_signal(
    signal: Any,
) -> str | None:
    value = str(
        signal or ""
    ).strip().upper()

    if value in {
        "BUY",
        "LONG",
        "BULLISH",
    }:
        return "BUY"

    if value in {
        "SELL",
        "SHORT",
        "BEARISH",
    }:
        return "SELL"

    return None


def _normalize_alignment(
    alignment: Any,
) -> str:
    return str(
        alignment or ""
    ).strip().upper()


def _candidate_price(
    candidate: Any,
) -> float | None:
    if not isinstance(
        candidate,
        dict,
    ):
        return None

    return _positive_float(
        candidate.get(
            "xauusd_price"
        )
    )


def _price_key(
    value: float,
) -> float:
    return round(
        float(value),
        6,
    )


def _upstream_shadow_contract_ok(
    payload: Any,
) -> bool:
    if not isinstance(
        payload,
        dict,
    ):
        return False

    if (
        str(
            payload.get(
                "decision_impact"
            )
            or ""
        ).upper()
        != "NONE"
    ):
        return False

    if bool(
        payload.get(
            "can_influence_decision"
        )
    ):
        return False

    if bool(
        payload.get(
            "safe_for_execution"
        )
    ):
        return False

    if bool(
        payload.get(
            "execution_allowed"
        )
    ):
        return False

    return True


def _find_current_mid(
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for candidate in candidates:
        if (
            candidate.get(
                "anchor_id"
            )
            == "CURRENT_MID"
        ):
            if (
                _candidate_price(
                    candidate
                )
                is not None
            ):
                return candidate

    return None


def _entry_candidate(
    *,
    signal: str,
    candidates: list[dict[str, Any]],
    current_mid: float,
) -> dict[str, Any] | None:
    """
    Entry must come from executed profile structure:

    - rolling POC
    - top volume-at-price

    It may not come from an arbitrary numeric offset.
    """

    pool = []

    for candidate in candidates:
        family = str(
            candidate.get(
                "family"
            )
            or ""
        ).upper()

        if family not in {
            "VOLUME_PROFILE",
            "VOLUME_AT_PRICE",
        }:
            continue

        price = _candidate_price(
            candidate
        )

        if price is None:
            continue

        if signal == "BUY":
            if price > current_mid:
                continue
        else:
            if price < current_mid:
                continue

        anchor_id = str(
            candidate.get(
                "anchor_id"
            )
            or ""
        )

        priority = (
            0
            if anchor_id
            == "ROLLING_POC"
            else 1
        )

        pool.append(
            (
                abs(
                    current_mid
                    - price
                ),
                priority,
                anchor_id,
                candidate,
            )
        )

    if not pool:
        return None

    pool.sort(
        key=lambda row: (
            row[0],
            row[1],
            row[2],
        )
    )

    return pool[0][3]


def _sl_candidate(
    *,
    signal: str,
    candidates: list[dict[str, Any]],
    entry: float,
) -> dict[str, Any] | None:
    """
    Structural invalidation comes only from executed-price
    rolling range extremes.

    BUY  -> ROLLING_LOW
    SELL -> ROLLING_HIGH
    """

    wanted = (
        "ROLLING_LOW"
        if signal == "BUY"
        else "ROLLING_HIGH"
    )

    for candidate in candidates:
        if (
            candidate.get(
                "anchor_id"
            )
            != wanted
        ):
            continue

        price = _candidate_price(
            candidate
        )

        if price is None:
            return None

        if (
            signal == "BUY"
            and price >= entry
        ):
            return None

        if (
            signal == "SELL"
            and price <= entry
        ):
            return None

        return candidate

    return None


def _wall_strength(
    candidate: dict[str, Any],
) -> tuple[float, float]:
    metadata = candidate.get(
        "metadata"
    )

    if not isinstance(
        metadata,
        dict,
    ):
        metadata = {}

    size = _finite_float(
        metadata.get(
            "size"
        )
    )

    orders = _finite_float(
        metadata.get(
            "orders"
        )
    )

    return (
        max(
            0.0,
            size or 0.0,
        ),
        max(
            0.0,
            orders or 0.0,
        ),
    )


def _tp_candidates(
    *,
    signal: str,
    candidates: list[dict[str, Any]],
    entry: float,
) -> list[dict[str, Any]]:
    """
    TP structure comes only from displayed opposing DOM walls.

    BUY  -> ASK depth above entry
    SELL -> BID depth below entry

    Selection:
    1. Rank all eligible walls by displayed size.
    2. Break size ties by number of orders.
    3. Break remaining ties by proximity.
    4. Keep the strongest two.
    5. Sort those two into TP1 / TP2 price order.

    No fixed price-distance threshold is invented here.
    """

    wanted_side = (
        "ASK"
        if signal == "BUY"
        else "BID"
    )

    unique: dict[
        float,
        dict[str, Any],
    ] = {}

    for candidate in candidates:
        if (
            str(
                candidate.get(
                    "family"
                )
                or ""
            ).upper()
            != "ORDER_BOOK_DEPTH"
        ):
            continue

        if (
            str(
                candidate.get(
                    "side"
                )
                or ""
            ).upper()
            != wanted_side
        ):
            continue

        price = _candidate_price(
            candidate
        )

        if price is None:
            continue

        if signal == "BUY":
            if price <= entry:
                continue
        else:
            if price >= entry:
                continue

        key = _price_key(
            price
        )

        existing = unique.get(
            key
        )

        if existing is None:
            unique[key] = candidate
            continue

        if (
            _wall_strength(
                candidate
            )
            > _wall_strength(
                existing
            )
        ):
            unique[key] = candidate

    pool = list(
        unique.values()
    )

    if len(pool) < 2:
        return []

    def rank_key(
        candidate: dict[str, Any],
    ):
        price = (
            _candidate_price(
                candidate
            )
            or 0.0
        )

        size, orders = (
            _wall_strength(
                candidate
            )
        )

        return (
            -size,
            -orders,
            abs(
                price
                - entry
            ),
            str(
                candidate.get(
                    "anchor_id"
                )
                or ""
            ),
        )

    strongest = sorted(
        pool,
        key=rank_key,
    )[:2]

    if signal == "BUY":
        strongest.sort(
            key=lambda candidate: (
                _candidate_price(
                    candidate
                )
                or 0.0
            )
        )
    else:
        strongest.sort(
            key=lambda candidate: -(
                _candidate_price(
                    candidate
                )
                or 0.0
            )
        )

    return strongest


def _geometry_valid(
    *,
    signal: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
) -> bool:
    if signal == "BUY":
        return bool(
            sl
            < entry
            < tp1
            < tp2
        )

    return bool(
        tp2
        < tp1
        < entry
        < sl
    )


def _rr(
    *,
    entry: float,
    sl: float,
    target: float,
) -> float | None:
    risk = abs(
        entry - sl
    )

    reward = abs(
        target - entry
    )

    if risk <= 0:
        return None

    return round(
        reward / risk,
        4,
    )


def build_rithmic_numeric_shadow_plan(
    *,
    signal: Any,
    rithmic_alignment: Any,
    translation_context: Any,
) -> dict[str, Any]:
    """
    Select a fully structural numeric SHADOW plan.

    This is NOT an execution plan.

    Selection policy:
    - Entry: favorable profile/VAP structure
    - SL: rolling executed-price invalidation extreme
    - TP1/TP2: strongest two opposing DOM walls

    All prices must already have been translated from GC to
    XAUUSD by the Phase 3A translation layer.

    Failure at any stage withholds the entire numeric plan.
    """

    result = {
        "model": MODEL,
        "mode": "SHADOW_ONLY",
        "status": "WITHHELD",
        "reason": None,
        "selection_policy": (
            "PROFILE_ENTRY__"
            "ROLLING_RANGE_INVALIDATION__"
            "OPPOSING_DEPTH_TARGETS_V1"
        ),
        "numeric_plan_available": False,
        "signal": None,
        "rithmic_alignment": (
            _normalize_alignment(
                rithmic_alignment
            )
        ),
        "current_mid": None,
        "suggested_entry": None,
        "suggested_sl": None,
        "suggested_tp": None,
        "suggested_tp_ladder": [],
        "entry_anchor": None,
        "sl_anchor": None,
        "tp_anchors": [],
        "rr_tp1": None,
        "rr_tp2": None,
        **_authority(),
    }

    direction = _normalize_signal(
        signal
    )

    result["signal"] = direction

    if direction is None:
        result["reason"] = (
            "invalid_signal"
        )
        return result

    alignment = (
        _normalize_alignment(
            rithmic_alignment
        )
    )

    if (
        alignment
        != SUPPORTED_ALIGNMENT
    ):
        result["reason"] = (
            "rithmic_alignment_not_supportive"
        )
        return result

    if not isinstance(
        translation_context,
        dict,
    ):
        result["reason"] = (
            "translation_context_missing"
        )
        return result

    if not _upstream_shadow_contract_ok(
        translation_context
    ):
        result["reason"] = (
            "upstream_authority_contract_invalid"
        )
        return result

    if (
        translation_context.get(
            "status"
        )
        != "SHADOW_CANDIDATES_READY"
    ):
        result["reason"] = (
            "translation_context_not_ready"
        )
        return result

    translation = (
        translation_context.get(
            "translation"
        )
    )

    if not isinstance(
        translation,
        dict,
    ):
        result["reason"] = (
            "translated_candidates_missing"
        )
        return result

    if not _upstream_shadow_contract_ok(
        translation
    ):
        result["reason"] = (
            "translation_authority_contract_invalid"
        )
        return result

    if (
        translation.get(
            "status"
        )
        != "TRANSLATED_SHADOW_CANDIDATES"
    ):
        result["reason"] = (
            "translated_candidates_not_ready"
        )
        return result

    candidates = (
        translation.get(
            "candidates"
        )
    )

    if not isinstance(
        candidates,
        list,
    ):
        result["reason"] = (
            "candidate_list_missing"
        )
        return result

    candidates = [
        candidate
        for candidate in candidates
        if isinstance(
            candidate,
            dict,
        )
    ]

    current_mid_candidate = (
        _find_current_mid(
            candidates
        )
    )

    if (
        current_mid_candidate
        is None
    ):
        result["reason"] = (
            "current_mid_missing"
        )
        return result

    current_mid = (
        _candidate_price(
            current_mid_candidate
        )
    )

    if current_mid is None:
        result["reason"] = (
            "current_mid_invalid"
        )
        return result

    result["current_mid"] = (
        current_mid
    )

    entry_candidate = (
        _entry_candidate(
            signal=direction,
            candidates=candidates,
            current_mid=current_mid,
        )
    )

    if entry_candidate is None:
        result["reason"] = (
            "favorable_profile_entry_missing"
        )
        return result

    entry = _candidate_price(
        entry_candidate
    )

    if entry is None:
        result["reason"] = (
            "entry_anchor_invalid"
        )
        return result

    sl_candidate = (
        _sl_candidate(
            signal=direction,
            candidates=candidates,
            entry=entry,
        )
    )

    if sl_candidate is None:
        result["reason"] = (
            "structural_invalidation_missing"
        )
        return result

    sl = _candidate_price(
        sl_candidate
    )

    if sl is None:
        result["reason"] = (
            "sl_anchor_invalid"
        )
        return result

    tp_candidates = (
        _tp_candidates(
            signal=direction,
            candidates=candidates,
            entry=entry,
        )
    )

    if len(tp_candidates) != 2:
        result["reason"] = (
            "two_opposing_depth_targets_required"
        )
        return result

    tp1 = _candidate_price(
        tp_candidates[0]
    )

    tp2 = _candidate_price(
        tp_candidates[1]
    )

    if (
        tp1 is None
        or tp2 is None
    ):
        result["reason"] = (
            "target_anchor_invalid"
        )
        return result

    if not _geometry_valid(
        signal=direction,
        entry=entry,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
    ):
        result["reason"] = (
            "numeric_plan_geometry_invalid"
        )
        return result

    rr1 = _rr(
        entry=entry,
        sl=sl,
        target=tp1,
    )

    rr2 = _rr(
        entry=entry,
        sl=sl,
        target=tp2,
    )

    if (
        rr1 is None
        or rr2 is None
    ):
        result["reason"] = (
            "numeric_plan_rr_invalid"
        )
        return result

    result.update(
        {
            "status": (
                "NUMERIC_SHADOW_PLAN"
            ),
            "reason": (
                "structural_numeric_shadow_plan_ready"
            ),
            "numeric_plan_available": True,
            "suggested_entry": entry,
            "suggested_sl": sl,
            "suggested_tp": tp1,
            "suggested_tp_ladder": [
                {
                    "label": "TP1",
                    "price": tp1,
                    "rr": rr1,
                    "anchor_id": (
                        tp_candidates[0].get(
                            "anchor_id"
                        )
                    ),
                },
                {
                    "label": "TP2",
                    "price": tp2,
                    "rr": rr2,
                    "anchor_id": (
                        tp_candidates[1].get(
                            "anchor_id"
                        )
                    ),
                },
            ],
            "entry_anchor": {
                "anchor_id": (
                    entry_candidate.get(
                        "anchor_id"
                    )
                ),
                "family": (
                    entry_candidate.get(
                        "family"
                    )
                ),
                "price": entry,
            },
            "sl_anchor": {
                "anchor_id": (
                    sl_candidate.get(
                        "anchor_id"
                    )
                ),
                "family": (
                    sl_candidate.get(
                        "family"
                    )
                ),
                "price": sl,
            },
            "tp_anchors": [
                {
                    "anchor_id": (
                        candidate.get(
                            "anchor_id"
                        )
                    ),
                    "family": (
                        candidate.get(
                            "family"
                        )
                    ),
                    "price": (
                        _candidate_price(
                            candidate
                        )
                    ),
                    "metadata": (
                        candidate.get(
                            "metadata"
                        )
                        if isinstance(
                            candidate.get(
                                "metadata"
                            ),
                            dict,
                        )
                        else {}
                    ),
                }
                for candidate
                in tp_candidates
            ],
            "rr_tp1": rr1,
            "rr_tp2": rr2,
        }
    )

    return result
