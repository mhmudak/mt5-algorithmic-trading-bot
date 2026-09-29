from __future__ import annotations

from math import isfinite
from typing import Any


MODEL = "RITHMIC_NUMERIC_SHADOW_TRANSLATION_V1"

MIN_VALID_PAIRS = 30
MIN_VALID_PAIR_RATE = 0.90
MAX_BASIS_STD = 2.0

DEFAULT_MAX_BASIS_AGE_SECONDS = 300.0
DEFAULT_MAX_STATE_AGE_SECONDS = 15.0
DEFAULT_MAX_COMPONENT_AGE_SECONDS = 15.0
DEFAULT_MAX_GC_SPREAD = 1.0
MAX_CLOCK_SKEW_SECONDS = 5.0


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


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _summary_from_basis(
    payload: Any,
) -> dict[str, Any]:
    if not isinstance(
        payload,
        dict,
    ):
        return {}

    nested = payload.get(
        "summary"
    )

    if isinstance(
        nested,
        dict,
    ):
        return nested

    return payload


def evaluate_basis_for_numeric_shadow(
    *,
    basis_payload: Any,
    basis_file_mtime_epoch: Any,
    now_epoch: Any,
    max_basis_age_seconds: float = (
        DEFAULT_MAX_BASIS_AGE_SECONDS
    ),
    expected_mt5_symbol: str | None = "XAUUSD",
    expected_rithmic_symbol: str | None = None,
) -> dict[str, Any]:
    """
    Validate a Phase 5AC basis for numeric SHADOW translation.

    File mtime is the freshness authority because the existing
    calibration JSON's updated_at is timezone-naive.

    Passing this gate NEVER grants trading or decision authority.
    """

    result = {
        "model": MODEL,
        "status": "UNAVAILABLE",
        "usable_for_numeric_shadow": False,
        "reason": None,
        "basis": None,
        "age_seconds": None,
        "statistical_quality_ok": False,
        "freshness_ok": False,
        "symbol_contract_ok": False,
        **_authority(),
    }

    if not isinstance(
        basis_payload,
        dict,
    ):
        result["reason"] = (
            "basis_payload_missing"
        )
        return result

    summary = _summary_from_basis(
        basis_payload
    )

    avg_basis = _finite_float(
        summary.get(
            "avg_basis"
        )
    )

    if avg_basis is None:
        result["reason"] = (
            "avg_basis_missing"
        )
        return result

    sample_count = _safe_int(
        summary.get(
            "sample_count"
        )
    )

    valid_pair_count = _safe_int(
        summary.get(
            "valid_pair_count"
        )
    )

    valid_pair_rate = _finite_float(
        summary.get(
            "valid_pair_rate"
        )
    )

    basis_std = _finite_float(
        summary.get(
            "basis_std"
        )
    )

    ready_flag = bool(
        summary.get(
            "basis_ready_observe_only"
        )
    )

    statistical_quality_ok = bool(
        ready_flag
        and sample_count > 0
        and valid_pair_count
        >= MIN_VALID_PAIRS
        and valid_pair_rate
        is not None
        and valid_pair_rate
        >= MIN_VALID_PAIR_RATE
        and basis_std
        is not None
        and basis_std
        <= MAX_BASIS_STD
    )

    result[
        "statistical_quality_ok"
    ] = statistical_quality_ok

    result["basis"] = avg_basis

    if not statistical_quality_ok:
        result["reason"] = (
            "basis_statistical_quality_not_ready"
        )
        return result

    now = _finite_float(
        now_epoch
    )

    mtime = _finite_float(
        basis_file_mtime_epoch
    )

    if (
        now is None
        or mtime is None
    ):
        result["reason"] = (
            "basis_freshness_clock_missing"
        )
        return result

    age = now - mtime

    result["age_seconds"] = round(
        age,
        6,
    )

    if age < -MAX_CLOCK_SKEW_SECONDS:
        result["reason"] = (
            "basis_file_time_in_future"
        )
        return result

    if age < 0:
        age = 0.0

    max_age = _positive_float(
        max_basis_age_seconds
    )

    if max_age is None:
        result["reason"] = (
            "invalid_basis_age_policy"
        )
        return result

    freshness_ok = (
        age <= max_age
    )

    result[
        "freshness_ok"
    ] = freshness_ok

    if not freshness_ok:
        result["reason"] = (
            "basis_stale"
        )
        return result

    actual_mt5 = str(
        basis_payload.get(
            "mt5_symbol"
        )
        or ""
    ).strip().upper()

    actual_rithmic = str(
        basis_payload.get(
            "rithmic_symbol"
        )
        or ""
    ).strip().upper()

    if expected_mt5_symbol:
        if (
            actual_mt5
            != str(
                expected_mt5_symbol
            ).strip().upper()
        ):
            result["reason"] = (
                "basis_mt5_symbol_mismatch"
            )
            return result

    if expected_rithmic_symbol:
        if (
            actual_rithmic
            != str(
                expected_rithmic_symbol
            ).strip().upper()
        ):
            result["reason"] = (
                "basis_rithmic_symbol_mismatch"
            )
            return result

    result[
        "symbol_contract_ok"
    ] = True

    result["status"] = (
        "READY_FOR_NUMERIC_SHADOW"
    )

    result[
        "usable_for_numeric_shadow"
    ] = True

    result["reason"] = (
        "basis_ready_for_shadow_translation"
    )

    return result


def evaluate_phase5c_state_for_numeric_shadow(
    *,
    state: Any,
    now_epoch: Any,
    max_state_age_seconds: float = (
        DEFAULT_MAX_STATE_AGE_SECONDS
    ),
    max_component_age_seconds: float = (
        DEFAULT_MAX_COMPONENT_AGE_SECONDS
    ),
    max_gc_spread: float = (
        DEFAULT_MAX_GC_SPREAD
    ),
    expected_symbol: str | None = None,
    expected_exchange: str | None = "COMEX",
) -> dict[str, Any]:
    """
    Validate Phase5C state for numeric SHADOW translation.

    Requires:
    - recent state snapshot
    - fresh trade
    - fresh BBO
    - fresh order book
    - two-sided BBO
    - sane positive spread
    - available depth on both sides
    """

    result = {
        "model": MODEL,
        "status": "UNAVAILABLE",
        "usable_for_numeric_shadow": False,
        "reason": None,
        "snapshot_age_seconds": None,
        "spread": None,
        "mid": None,
        "freshness_ok": False,
        "book_ok": False,
        "symbol_contract_ok": False,
        **_authority(),
    }

    if not isinstance(
        state,
        dict,
    ):
        result["reason"] = (
            "phase5c_state_missing"
        )
        return result

    state_status = str(
        state.get(
            "state_status"
        )
        or ""
    ).strip().upper()

    if (
        state_status
        != "OBSERVE_ONLY_READY"
    ):
        result["reason"] = (
            "phase5c_state_not_ready"
        )
        return result

    actual_symbol = str(
        state.get("symbol")
        or ""
    ).strip().upper()

    actual_exchange = str(
        state.get("exchange")
        or ""
    ).strip().upper()

    if expected_symbol:
        if (
            actual_symbol
            != str(
                expected_symbol
            ).strip().upper()
        ):
            result["reason"] = (
                "phase5c_symbol_mismatch"
            )
            return result

    if expected_exchange:
        if (
            actual_exchange
            != str(
                expected_exchange
            ).strip().upper()
        ):
            result["reason"] = (
                "phase5c_exchange_mismatch"
            )
            return result

    result[
        "symbol_contract_ok"
    ] = True

    now = _finite_float(
        now_epoch
    )

    updated = _finite_float(
        state.get(
            "updated_at_epoch"
        )
    )

    if (
        now is None
        or updated is None
    ):
        result["reason"] = (
            "phase5c_snapshot_clock_missing"
        )
        return result

    age = now - updated

    result[
        "snapshot_age_seconds"
    ] = round(
        age,
        6,
    )

    if age < -MAX_CLOCK_SKEW_SECONDS:
        result["reason"] = (
            "phase5c_snapshot_time_in_future"
        )
        return result

    if age < 0:
        age = 0.0

    max_state_age = _positive_float(
        max_state_age_seconds
    )

    if (
        max_state_age is None
        or age > max_state_age
    ):
        result["reason"] = (
            "phase5c_snapshot_stale"
        )
        return result

    freshness = state.get(
        "freshness"
    )

    if not isinstance(
        freshness,
        dict,
    ):
        result["reason"] = (
            "phase5c_freshness_missing"
        )
        return result

    if not all(
        bool(
            freshness.get(key)
        )
        for key in (
            "has_fresh_trade",
            "has_fresh_bbo",
            "has_fresh_order_book",
        )
    ):
        result["reason"] = (
            "phase5c_component_not_fresh"
        )
        return result

    component_limit = _positive_float(
        max_component_age_seconds
    )

    if component_limit is None:
        result["reason"] = (
            "invalid_component_age_policy"
        )
        return result

    source_limit = _positive_float(
        freshness.get(
            "stale_after_seconds"
        )
    )

    if source_limit is not None:
        component_limit = min(
            component_limit,
            source_limit,
        )

    for key in (
        "last_trade_age_seconds",
        "last_bbo_age_seconds",
        "last_order_book_age_seconds",
    ):
        value = _finite_float(
            freshness.get(key)
        )

        if (
            value is None
            or value < 0
            or value > component_limit
        ):
            result["reason"] = (
                "phase5c_component_age_stale"
            )
            return result

    result[
        "freshness_ok"
    ] = True

    bbo = state.get("bbo")

    if not isinstance(
        bbo,
        dict,
    ):
        result["reason"] = (
            "phase5c_bbo_missing"
        )
        return result

    bid = _positive_float(
        bbo.get(
            "last_bid"
        )
    )

    ask = _positive_float(
        bbo.get(
            "last_ask"
        )
    )

    if (
        bid is None
        or ask is None
        or ask <= bid
    ):
        result["reason"] = (
            "phase5c_two_sided_bbo_invalid"
        )
        return result

    spread = ask - bid

    result["spread"] = round(
        spread,
        6,
    )

    result["mid"] = round(
        (bid + ask) / 2.0,
        6,
    )

    spread_limit = _positive_float(
        max_gc_spread
    )

    if spread_limit is None:
        result["reason"] = (
            "invalid_spread_policy"
        )
        return result

    if spread > spread_limit:
        result["reason"] = (
            "phase5c_spread_too_wide"
        )
        return result

    book = state.get(
        "order_book"
    )

    if not isinstance(
        book,
        dict,
    ):
        result["reason"] = (
            "phase5c_order_book_missing"
        )
        return result

    if not bool(
        book.get(
            "available"
        )
    ):
        result["reason"] = (
            "phase5c_order_book_unavailable"
        )
        return result

    bid_levels = book.get(
        "bid_levels"
    )

    ask_levels = book.get(
        "ask_levels"
    )

    if (
        not isinstance(
            bid_levels,
            list,
        )
        or not isinstance(
            ask_levels,
            list,
        )
        or not bid_levels
        or not ask_levels
    ):
        result["reason"] = (
            "phase5c_two_sided_depth_missing"
        )
        return result

    result[
        "book_ok"
    ] = True

    result["status"] = (
        "READY_FOR_NUMERIC_SHADOW"
    )

    result[
        "usable_for_numeric_shadow"
    ] = True

    result["reason"] = (
        "phase5c_ready_for_shadow_translation"
    )

    return result


def extract_gc_structural_anchors(
    state: Any,
    *,
    max_depth_levels: int = 20,
    max_vap_levels: int = 20,
) -> list[dict[str, Any]]:
    """
    Extract raw GC structural candidates.

    This function does NOT decide which candidate is Entry, SL or TP.
    """

    if not isinstance(
        state,
        dict,
    ):
        return []

    anchors: list[
        dict[str, Any]
    ] = []

    def add(
        anchor_id: str,
        family: str,
        price: Any,
        *,
        side: str = "NEUTRAL",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        numeric = _positive_float(
            price
        )

        if numeric is None:
            return

        anchors.append(
            {
                "anchor_id": anchor_id,
                "family": family,
                "side": side,
                "gc_price": numeric,
                "metadata": (
                    metadata
                    if isinstance(
                        metadata,
                        dict,
                    )
                    else {}
                ),
            }
        )

    bbo = state.get(
        "bbo"
    )

    if isinstance(
        bbo,
        dict,
    ):
        bid = _positive_float(
            bbo.get(
                "last_bid"
            )
        )

        ask = _positive_float(
            bbo.get(
                "last_ask"
            )
        )

        if (
            bid is not None
            and ask is not None
            and ask > bid
        ):
            add(
                "CURRENT_MID",
                "CURRENT_MARKET",
                (bid + ask) / 2.0,
            )

    latest = state.get(
        "latest_trade"
    )

    if isinstance(
        latest,
        dict,
    ):
        add(
            "LATEST_TRADE",
            "CURRENT_MARKET",
            latest.get(
                "price"
            ),
        )

    profile = state.get(
        "volume_profile"
    )

    if isinstance(
        profile,
        dict,
    ):
        add(
            "ROLLING_POC",
            "VOLUME_PROFILE",
            profile.get(
                "rolling_poc_price"
            ),
        )

        vap = profile.get(
            "top_volume_at_price"
        )

        if isinstance(
            vap,
            list,
        ):
            for index, row in enumerate(
                vap[
                    :max(
                        0,
                        int(
                            max_vap_levels
                        ),
                    )
                ],
                1,
            ):
                if not isinstance(
                    row,
                    dict,
                ):
                    continue

                add(
                    f"TOP_VAP_{index}",
                    "VOLUME_AT_PRICE",
                    row.get(
                        "price"
                    ),
                    metadata={
                        "buy_volume": row.get(
                            "buy_volume"
                        ),
                        "sell_volume": row.get(
                            "sell_volume"
                        ),
                        "total_volume": row.get(
                            "total_volume"
                        ),
                        "delta": row.get(
                            "delta"
                        ),
                        "trade_count": row.get(
                            "trade_count"
                        ),
                    },
                )

    trade_flow = state.get(
        "trade_flow"
    )

    if isinstance(
        trade_flow,
        dict,
    ):
        add(
            "ROLLING_HIGH",
            "TRADE_RANGE",
            trade_flow.get(
                "high_trade_price"
            ),
            side="ABOVE",
        )

        add(
            "ROLLING_LOW",
            "TRADE_RANGE",
            trade_flow.get(
                "low_trade_price"
            ),
            side="BELOW",
        )

    book = state.get(
        "order_book"
    )

    if isinstance(
        book,
        dict,
    ):
        depth_limit = max(
            0,
            int(
                max_depth_levels
            ),
        )

        for side_name, rows in (
            (
                "BID",
                book.get(
                    "bid_levels"
                ),
            ),
            (
                "ASK",
                book.get(
                    "ask_levels"
                ),
            ),
        ):
            if not isinstance(
                rows,
                list,
            ):
                continue

            for index, row in enumerate(
                rows[:depth_limit],
                1,
            ):
                if not isinstance(
                    row,
                    dict,
                ):
                    continue

                add(
                    (
                        f"{side_name}_DEPTH_"
                        f"{index}"
                    ),
                    "ORDER_BOOK_DEPTH",
                    row.get(
                        "price"
                    ),
                    side=side_name,
                    metadata={
                        "level": row.get(
                            "level"
                        ),
                        "size": row.get(
                            "size"
                        ),
                        "orders": row.get(
                            "orders"
                        ),
                        "implicit_size": row.get(
                            "implicit_size"
                        ),
                    },
                )

    return anchors


def translate_gc_anchors_to_xauusd(
    *,
    anchors: Any,
    basis_evaluation: Any,
) -> dict[str, Any]:
    """
    Translate raw GC structural prices into XAUUSD shadow prices.

    Formula:
        XAUUSD = GC + basis

    No Entry / SL / TP selection occurs here.
    """

    result = {
        "model": MODEL,
        "status": "BLOCKED",
        "reason": None,
        "basis": None,
        "candidate_count": 0,
        "candidates": [],
        **_authority(),
    }

    if not isinstance(
        basis_evaluation,
        dict,
    ):
        result["reason"] = (
            "basis_evaluation_missing"
        )
        return result

    if not bool(
        basis_evaluation.get(
            "usable_for_numeric_shadow"
        )
    ):
        result["reason"] = (
            "basis_not_usable"
        )
        return result

    basis = _finite_float(
        basis_evaluation.get(
            "basis"
        )
    )

    if basis is None:
        result["reason"] = (
            "basis_value_missing"
        )
        return result

    if not isinstance(
        anchors,
        list,
    ):
        result["reason"] = (
            "anchors_missing"
        )
        return result

    translated = []

    for anchor in anchors:
        if not isinstance(
            anchor,
            dict,
        ):
            continue

        gc_price = _positive_float(
            anchor.get(
                "gc_price"
            )
        )

        if gc_price is None:
            continue

        xauusd_price = (
            gc_price
            + basis
        )

        if (
            not isfinite(
                xauusd_price
            )
            or xauusd_price <= 0
        ):
            continue

        translated.append(
            {
                **anchor,
                "xauusd_price": round(
                    xauusd_price,
                    6,
                ),
                "translation": (
                    "XAUUSD=GC+BASIS"
                ),
            }
        )

    if not translated:
        result["reason"] = (
            "no_valid_structural_anchors"
        )
        return result

    result["status"] = (
        "TRANSLATED_SHADOW_CANDIDATES"
    )

    result["reason"] = (
        "numeric_shadow_candidates_ready"
    )

    result["basis"] = basis

    result["candidate_count"] = len(
        translated
    )

    result["candidates"] = (
        translated
    )

    return result


def build_numeric_shadow_translation_context(
    *,
    state: Any,
    basis_payload: Any,
    basis_file_mtime_epoch: Any,
    now_epoch: Any,
    expected_symbol: str,
    expected_exchange: str = "COMEX",
    max_basis_age_seconds: float = (
        DEFAULT_MAX_BASIS_AGE_SECONDS
    ),
    max_state_age_seconds: float = (
        DEFAULT_MAX_STATE_AGE_SECONDS
    ),
    max_component_age_seconds: float = (
        DEFAULT_MAX_COMPONENT_AGE_SECONDS
    ),
    max_gc_spread: float = (
        DEFAULT_MAX_GC_SPREAD
    ),
) -> dict[str, Any]:
    """
    End-to-end Phase 3A translation gate.

    Produces translated structural candidates only.

    It deliberately does NOT select:
    - suggested_entry
    - suggested_sl
    - suggested_tp
    """

    result = {
        "model": MODEL,
        "status": "BLOCKED",
        "reason": None,
        "basis_gate": None,
        "state_gate": None,
        "translation": None,
        "selection_status": (
            "NOT_IMPLEMENTED_PHASE3A"
        ),
        "suggested_entry": None,
        "suggested_sl": None,
        "suggested_tp": None,
        **_authority(),
    }

    basis_gate = (
        evaluate_basis_for_numeric_shadow(
            basis_payload=basis_payload,
            basis_file_mtime_epoch=(
                basis_file_mtime_epoch
            ),
            now_epoch=now_epoch,
            max_basis_age_seconds=(
                max_basis_age_seconds
            ),
            expected_mt5_symbol="XAUUSD",
            expected_rithmic_symbol=(
                expected_symbol
            ),
        )
    )

    result[
        "basis_gate"
    ] = basis_gate

    if not bool(
        basis_gate.get(
            "usable_for_numeric_shadow"
        )
    ):
        result["reason"] = (
            "basis_gate_blocked"
        )
        return result

    state_gate = (
        evaluate_phase5c_state_for_numeric_shadow(
            state=state,
            now_epoch=now_epoch,
            max_state_age_seconds=(
                max_state_age_seconds
            ),
            max_component_age_seconds=(
                max_component_age_seconds
            ),
            max_gc_spread=max_gc_spread,
            expected_symbol=(
                expected_symbol
            ),
            expected_exchange=(
                expected_exchange
            ),
        )
    )

    result[
        "state_gate"
    ] = state_gate

    if not bool(
        state_gate.get(
            "usable_for_numeric_shadow"
        )
    ):
        result["reason"] = (
            "state_gate_blocked"
        )
        return result

    anchors = (
        extract_gc_structural_anchors(
            state
        )
    )

    translation = (
        translate_gc_anchors_to_xauusd(
            anchors=anchors,
            basis_evaluation=(
                basis_gate
            ),
        )
    )

    result[
        "translation"
    ] = translation

    if (
        translation.get("status")
        != "TRANSLATED_SHADOW_CANDIDATES"
    ):
        result["reason"] = (
            "translation_blocked"
        )
        return result

    result["status"] = (
        "SHADOW_CANDIDATES_READY"
    )

    result["reason"] = (
        "phase3a_translation_ready"
    )

    return result
