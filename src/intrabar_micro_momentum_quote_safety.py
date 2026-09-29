from __future__ import annotations


STRATEGY_NAME = "INTRABAR_MICRO_MOMENTUM"


def _round_price(value, digits):
    return round(float(value), int(digits))


def apply_micro_momentum_quote_safety(
    *,
    signal,
    request,
    trade_plan,
    bid,
    ask,
    digits,
    max_spread_price,
    stop_cushion_price,
    min_rr,
    max_sl_distance,
):
    """
    Final local quote-side safety for Micro Momentum immediately before order_send.

    This function never sends an order. It only:
      - re-checks the final bid/ask spread,
      - ensures BUY SL is safely below bid / SELL SL safely above ask,
      - keeps TP unchanged,
      - refuses any widening that would exceed max SL or minimum RR.
    """
    if not isinstance(request, dict) or not isinstance(trade_plan, dict):
        return {
            "allowed": False,
            "reason": "invalid_inputs",
            "request": request,
            "trade_plan": trade_plan,
        }

    strategy = str(trade_plan.get("strategy") or "").upper()
    if strategy != STRATEGY_NAME:
        return {
            "allowed": True,
            "reason": "non_micro_momentum",
            "request": request,
            "trade_plan": trade_plan,
            "adjusted": False,
        }

    signal = str(signal or "").upper()
    if signal not in {"BUY", "SELL"}:
        return {
            "allowed": False,
            "reason": "invalid_signal",
            "request": request,
            "trade_plan": trade_plan,
        }

    bid = float(bid)
    ask = float(ask)
    spread = ask - bid

    if bid <= 0 or ask <= 0 or spread < 0:
        return {
            "allowed": False,
            "reason": "invalid_quote",
            "request": request,
            "trade_plan": trade_plan,
        }

    if spread > float(max_spread_price):
        return {
            "allowed": False,
            "reason": "final_spread_too_wide",
            "spread": round(spread, 6),
            "max_spread": float(max_spread_price),
            "request": request,
            "trade_plan": trade_plan,
        }

    entry = float(request.get("price"))
    tp = float(request.get("tp"))
    current_sl = float(request.get("sl"))

    nominal_sl_distance = float(
        trade_plan.get(
            "micro_momentum_execution_sl_distance",
            abs(entry - current_sl),
        )
    )
    tp_distance = float(
        trade_plan.get(
            "micro_momentum_execution_tp_distance",
            abs(tp - entry),
        )
    )

    if nominal_sl_distance <= 0 or tp_distance <= 0:
        return {
            "allowed": False,
            "reason": "invalid_geometry_distance",
            "request": request,
            "trade_plan": trade_plan,
        }

    reversal_mode = bool(trade_plan.get("micro_momentum_execution_reversal"))
    if reversal_mode:
        # The original 0.50 max-SL and 1.50 min-RR rules qualify the detector
        # geometry. Reversed geometry intentionally violates those values, so
        # only spread, quote-side stop validity and exact absolute geometry apply.
        required = spread + float(stop_cushion_price)
        if nominal_sl_distance + 1e-9 < required:
            return {
                "allowed": False,
                "reason": "reversal_quote_safety_requires_geometry_change",
                "spread": round(spread, 6),
                "nominal_sl_distance": round(nominal_sl_distance, 6),
                "required_sl_distance": round(required, 6),
                "request": request,
                "trade_plan": trade_plan,
            }
        if signal == "BUY":
            boundary = _round_price(bid - float(stop_cushion_price), digits)
            safe = current_sl <= boundary + 1e-9 and current_sl < entry < tp
        else:
            boundary = _round_price(ask + float(stop_cushion_price), digits)
            safe = current_sl >= boundary - 1e-9 and tp < entry < current_sl
        if not safe:
            return {
                "allowed": False,
                "reason": "reversal_absolute_geometry_not_quote_safe",
                "spread": round(spread, 6),
                "quote_safe_boundary": boundary,
                "request": request,
                "trade_plan": trade_plan,
            }
        final_rr = tp_distance / nominal_sl_distance
        plan = dict(trade_plan)
        plan["stop_loss"] = current_sl
        plan["stop_distance"] = round(nominal_sl_distance, 6)
        plan["micro_momentum_execution_sl_distance"] = round(nominal_sl_distance, 6)
        plan["micro_momentum_execution_tp_distance"] = round(tp_distance, 6)
        plan["micro_momentum_execution_rr"] = round(final_rr, 6)
        plan["rr"] = round(final_rr, 6)
        plan["risk_reward"] = round(final_rr, 6)
        plan["micro_momentum_quote_safe_sl_applied"] = False
        plan["micro_momentum_quote_safe_reversal_exception"] = True
        plan["micro_momentum_quote_safe_spread"] = round(spread, 6)
        plan["micro_momentum_quote_safe_cushion"] = round(float(stop_cushion_price), 6)
        plan["micro_momentum_quote_safe_rr"] = round(final_rr, 6)
        return {
            "allowed": True,
            "reason": "reversal_absolute_geometry_quote_safe",
            "adjusted": False,
            "spread": round(spread, 6),
            "nominal_sl_distance": round(nominal_sl_distance, 6),
            "final_sl_distance": round(nominal_sl_distance, 6),
            "final_rr": round(final_rr, 6),
            "request": dict(request),
            "trade_plan": plan,
        }


    min_rr = float(min_rr)
    if min_rr <= 0:
        return {
            "allowed": False,
            "reason": "invalid_min_rr",
            "request": request,
            "trade_plan": trade_plan,
        }

    rr_max_sl_distance = tp_distance / min_rr
    allowed_max_sl_distance = min(
        float(max_sl_distance),
        float(rr_max_sl_distance),
    )

    quote_required_distance = spread + float(stop_cushion_price)
    final_sl_distance = max(
        nominal_sl_distance,
        quote_required_distance,
    )

    # Round UP to price precision so the cushion is never reduced by rounding.
    scale = 10 ** int(digits)
    final_sl_distance = (
        int(final_sl_distance * scale + 0.999999999) / scale
    )

    if final_sl_distance > allowed_max_sl_distance + 1e-9:
        return {
            "allowed": False,
            "reason": "quote_safe_sl_exceeds_risk_authority",
            "spread": round(spread, 6),
            "nominal_sl_distance": round(nominal_sl_distance, 6),
            "required_sl_distance": round(final_sl_distance, 6),
            "allowed_max_sl_distance": round(allowed_max_sl_distance, 6),
            "request": request,
            "trade_plan": trade_plan,
        }

    updated_request = dict(request)
    updated_plan = dict(trade_plan)

    if signal == "BUY":
        final_sl = _round_price(entry - final_sl_distance, digits)
        quote_safe_boundary = _round_price(
            bid - float(stop_cushion_price),
            digits,
        )
        if final_sl > quote_safe_boundary:
            final_sl = quote_safe_boundary
            final_sl_distance = round(entry - final_sl, int(digits))
    else:
        final_sl = _round_price(entry + final_sl_distance, digits)
        quote_safe_boundary = _round_price(
            ask + float(stop_cushion_price),
            digits,
        )
        if final_sl < quote_safe_boundary:
            final_sl = quote_safe_boundary
            final_sl_distance = round(final_sl - entry, int(digits))

    final_rr = tp_distance / final_sl_distance

    if (
        final_sl_distance > float(max_sl_distance) + 1e-9
        or final_rr + 1e-9 < min_rr
    ):
        return {
            "allowed": False,
            "reason": "quote_safe_geometry_failed_final_validation",
            "spread": round(spread, 6),
            "final_sl_distance": round(final_sl_distance, 6),
            "final_rr": round(final_rr, 6),
            "request": request,
            "trade_plan": trade_plan,
        }

    updated_request["sl"] = final_sl
    updated_plan["stop_loss"] = final_sl
    updated_plan["stop_distance"] = round(final_sl_distance, 6)

    if "micro_momentum_nominal_sl_distance" not in updated_plan:
        updated_plan["micro_momentum_nominal_sl_distance"] = round(
            nominal_sl_distance,
            6,
        )

    updated_plan["micro_momentum_execution_sl_distance"] = round(
        final_sl_distance,
        6,
    )
    updated_plan["micro_momentum_quote_safe_sl_applied"] = (
        abs(final_sl_distance - nominal_sl_distance) > 1e-9
    )
    updated_plan["micro_momentum_quote_safe_spread"] = round(spread, 6)
    updated_plan["micro_momentum_quote_safe_cushion"] = round(
        float(stop_cushion_price),
        6,
    )
    updated_plan["micro_momentum_quote_safe_rr"] = round(final_rr, 6)

    return {
        "allowed": True,
        "reason": (
            "quote_safe_sl_adjusted"
            if updated_plan["micro_momentum_quote_safe_sl_applied"]
            else "quote_safe_sl_unchanged"
        ),
        "adjusted": updated_plan[
            "micro_momentum_quote_safe_sl_applied"
        ],
        "spread": round(spread, 6),
        "nominal_sl_distance": round(nominal_sl_distance, 6),
        "final_sl_distance": round(final_sl_distance, 6),
        "final_rr": round(final_rr, 6),
        "request": updated_request,
        "trade_plan": updated_plan,
    }
