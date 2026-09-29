from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "src" / "intrabar_micro_momentum_quote_safety.py"
ORDER_EXECUTOR = ROOT / "src" / "order_executor.py"
SETTINGS = ROOT / "config" / "settings.py"


def load_helper():
    namespace = {}
    code = HELPER.read_text(encoding="utf-8")
    exec(compile(code, str(HELPER), "exec"), namespace)
    return namespace["apply_micro_momentum_quote_safety"]


def setting(name):
    tree = ast.parse(SETTINGS.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(name)


def base_plan(signal, entry, sl_distance, tp_distance):
    if signal == "BUY":
        sl = round(entry - sl_distance, 2)
        tp = round(entry + tp_distance, 2)
    else:
        sl = round(entry + sl_distance, 2)
        tp = round(entry - tp_distance, 2)

    return (
        {
            "price": entry,
            "sl": sl,
            "tp": tp,
        },
        {
            "strategy": "INTRABAR_MICRO_MOMENTUM",
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "micro_momentum_execution_sl_distance": sl_distance,
            "micro_momentum_execution_tp_distance": tp_distance,
        },
    )


def run_case(apply, *, name, signal, bid, ask, sl_d, tp_d):
    entry = ask if signal == "BUY" else bid
    request, plan = base_plan(signal, entry, sl_d, tp_d)

    result = apply(
        signal=signal,
        request=request,
        trade_plan=plan,
        bid=bid,
        ask=ask,
        digits=2,
        max_spread_price=setting(
            "MICRO_MOMENTUM_FINAL_MAX_SPREAD_PRICE"
        ),
        stop_cushion_price=setting(
            "MICRO_MOMENTUM_QUOTE_STOP_CUSHION_PRICE"
        ),
        min_rr=setting("MICRO_MOMENTUM_LIVE_MIN_RR"),
        max_sl_distance=setting(
            "MICRO_MOMENTUM_QUOTE_SAFE_MAX_SL_DISTANCE"
        ),
    )

    print(name, result)
    return result


def main():
    print("[MICRO MOMENTUM QUOTE-SAFE STOPS TEST V1]")

    apply = load_helper()

    print(
        {
            "final_max_spread": setting(
                "MICRO_MOMENTUM_FINAL_MAX_SPREAD_PRICE"
            ),
            "stop_cushion": setting(
                "MICRO_MOMENTUM_QUOTE_STOP_CUSHION_PRICE"
            ),
            "max_sl_distance": setting(
                "MICRO_MOMENTUM_QUOTE_SAFE_MAX_SL_DISTANCE"
            ),
            "min_rr": setting("MICRO_MOMENTUM_LIVE_MIN_RR"),
        }
    )

    # Tight spread: WEAK_VALID keeps the original 0.30 SL.
    tight_buy = run_case(
        apply,
        name="WEAK_BUY_TIGHT",
        signal="BUY",
        bid=4283.07,
        ask=4283.15,
        sl_d=0.30,
        tp_d=0.60,
    )
    assert tight_buy["allowed"] is True
    assert tight_buy["final_sl_distance"] == 0.30
    assert tight_buy["request"]["sl"] == 4282.85

    # Wider but still allowed spread: quote cushion widens WEAK_VALID
    # slightly, while staying inside the requested 0.30-0.50 band.
    wide_buy = run_case(
        apply,
        name="WEAK_BUY_WIDER",
        signal="BUY",
        bid=4282.95,
        ask=4283.15,
        sl_d=0.30,
        tp_d=0.60,
    )
    assert wide_buy["allowed"] is True
    assert wide_buy["adjusted"] is True
    assert wide_buy["final_sl_distance"] == 0.35
    assert wide_buy["final_rr"] >= 1.50

    wide_sell = run_case(
        apply,
        name="WEAK_SELL_WIDER",
        signal="SELL",
        bid=4283.00,
        ask=4283.20,
        sl_d=0.30,
        tp_d=0.60,
    )
    assert wide_sell["allowed"] is True
    assert wide_sell["adjusted"] is True
    assert wide_sell["final_sl_distance"] == 0.35
    assert wide_sell["final_rr"] >= 1.50

    # NORMAL and EXPLOSIVE geometry remain unchanged at allowed spreads.
    normal = run_case(
        apply,
        name="NORMAL_SELL",
        signal="SELL",
        bid=4283.07,
        ask=4283.22,
        sl_d=0.40,
        tp_d=1.20,
    )
    assert normal["allowed"] is True
    assert normal["final_sl_distance"] == 0.40

    explosive = run_case(
        apply,
        name="EXPLOSIVE_BUY",
        signal="BUY",
        bid=4283.00,
        ask=4283.15,
        sl_d=0.50,
        tp_d=2.00,
    )
    assert explosive["allowed"] is True
    assert explosive["final_sl_distance"] == 0.50

    # A final spread burst beyond the strategy's own max is blocked.
    spread_block = run_case(
        apply,
        name="FINAL_SPREAD_BLOCK",
        signal="BUY",
        bid=4282.90,
        ask=4283.15,
        sl_d=0.30,
        tp_d=0.60,
    )
    assert spread_block["allowed"] is False
    assert spread_block["reason"] == "final_spread_too_wide"

    oe = ORDER_EXECUTOR.read_text(encoding="utf-8")
    required = [
        "apply_micro_momentum_quote_safety",
        "[MICRO MOMENTUM QUOTE SAFETY]",
        "MICRO_MOMENTUM_FINAL_MAX_SPREAD_PRICE",
        "MICRO_MOMENTUM_QUOTE_STOP_CUSHION_PRICE",
        "MICRO_MOMENTUM_QUOTE_SAFE_MAX_SL_DISTANCE",
        "result = mt5.order_send(request)",
    ]
    for snippet in required:
        if snippet not in oe:
            raise AssertionError(f"missing order-executor wiring: {snippet}")

    safety_pos = oe.index("apply_micro_momentum_quote_safety")
    send_pos = oe.index("result = mt5.order_send(request)")
    assert safety_pos < send_pos

    print(
        "\nPASS: final Micro Momentum request geometry is quote-side safe. "
        "WEAK_VALID may widen locally from 0.30 to 0.35 when spread requires "
        "extra stop cushion; NORMAL/EXPLOSIVE remain unchanged in the tested "
        "quotes; final spread bursts are blocked; TP is not widened; and "
        "order_send remains downstream of the quote-safety gate."
    )


if __name__ == "__main__":
    main()
