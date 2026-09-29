from __future__ import annotations

from pathlib import Path

from src.intrabar_micro_momentum_execution_geometry import apply_authoritative_micro_momentum_geometry
from src.intrabar_micro_momentum_quote_safety import apply_micro_momentum_quote_safety
from src.micro_momentum_execution_reversal import apply_micro_momentum_execution_reversal

ROOT = Path(__file__).resolve().parents[1]


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)


def close(a, b, tol=1e-6):
    return abs(float(a) - float(b)) <= tol


def plan(side):
    if side == "SELL":
        sl, tp = 4300.40, 4298.80
    else:
        sl, tp = 4299.60, 4301.20
    return {
        "strategy": "INTRABAR_MICRO_MOMENTUM",
        "execution_geometry_authority": "INTRABAR_MICRO_MOMENTUM",
        "entry_price": 4300.0,
        "stop_loss": sl,
        "take_profit": tp,
        "lot": 0.25,
        "rr": 3.0,
        "risk_reward": 3.0,
    }


def main():
    sell = apply_micro_momentum_execution_reversal(signal="SELL", trade_plan=plan("SELL"), enabled=True)
    ok(sell and sell["execution_signal"] == "BUY", "SELL->BUY failed")
    sp = sell["trade_plan"]
    ok(close(sp["stop_loss"], 4298.80), "old TP did not become new SL")
    ok(close(sp["take_profit"], 4300.40), "old SL did not become new TP")
    ok(close(sp["lot"], 0.25), "lot changed")
    ok(close(sell["execution_rr"], 1 / 3), "reversed RR incorrect")
    ok(sp["micro_momentum_original_signal"] == "SELL", "original telemetry missing")

    buy = apply_micro_momentum_execution_reversal(signal="BUY", trade_plan=plan("BUY"), enabled=True)
    ok(buy and buy["execution_signal"] == "SELL", "BUY->SELL failed")
    ok(close(buy["trade_plan"]["stop_loss"], 4301.20), "BUY old TP->SL failed")
    ok(close(buy["trade_plan"]["take_profit"], 4299.60), "BUY old SL->TP failed")

    off = apply_micro_momentum_execution_reversal(signal="SELL", trade_plan=plan("SELL"), enabled=False)
    ok(off and off["execution_signal"] == "SELL", "toggle False changed signal")
    ok(close(off["trade_plan"]["stop_loss"], 4300.40), "toggle False changed SL")
    ok(close(off["trade_plan"]["take_profit"], 4298.80), "toggle False changed TP")

    request = {"price": 4300.05, "sl": sp["stop_loss"], "tp": sp["take_profit"]}
    geom = apply_authoritative_micro_momentum_geometry(
        signal="BUY", trade_plan=sp, request=request, execution_price=4300.05
    )
    ok(geom is not None, "final reversal geometry blocked")
    ok(close(request["sl"], 4298.80), "final geometry moved absolute SL")
    ok(close(request["tp"], 4300.40), "final geometry moved absolute TP")

    normal = {
        "strategy": "INTRABAR_MICRO_MOMENTUM",
        "execution_geometry_authority": "INTRABAR_MICRO_MOMENTUM",
        "entry_price": 4300.0,
        "stop_loss": 4299.60,
        "take_profit": 4301.20,
        "micro_momentum_execution_sl_distance": 0.40,
        "micro_momentum_execution_tp_distance": 1.20,
    }
    normal_req = {"price": 4300.0, "sl": 4299.60, "tp": 4301.20}
    ok(apply_authoritative_micro_momentum_geometry(
        signal="BUY", trade_plan=normal, request=normal_req, execution_price=4300.0
    ) is not None, "normal Micro geometry broke")

    quote = apply_micro_momentum_quote_safety(
        signal="BUY",
        request={"price": 4300.0, "sl": 4298.80, "tp": 4300.40},
        trade_plan=sp,
        bid=4299.90, ask=4300.00, digits=2,
        max_spread_price=0.20, stop_cushion_price=0.15,
        min_rr=1.50, max_sl_distance=0.50,
    )
    ok(quote["allowed"] is True, "original RR/SL caps blocked reversal")
    ok(quote["adjusted"] is False, "quote safety rewrote valid reversal")
    ok(close(quote["request"]["sl"], 4298.80), "quote safety moved reversed SL")

    wide = apply_micro_momentum_quote_safety(
        signal="BUY",
        request={"price": 4300.0, "sl": 4298.80, "tp": 4300.40},
        trade_plan=sp,
        bid=4299.70, ask=4300.00, digits=2,
        max_spread_price=0.20, stop_cushion_price=0.15,
        min_rr=1.50, max_sl_distance=0.50,
    )
    ok(wide["allowed"] is False and wide["reason"] == "final_spread_too_wide", "spread safety bypassed")

    other = apply_micro_momentum_quote_safety(
        signal="BUY", request={"price": 100.0, "sl": 99.0, "tp": 102.0},
        trade_plan={"strategy": "OTHER_STRATEGY"}, bid=99.9, ask=100.0, digits=2,
        max_spread_price=0.20, stop_cushion_price=0.15, min_rr=1.50, max_sl_distance=0.50,
    )
    ok(other["allowed"] is True and other["reason"] == "non_micro_momentum", "non-Micro path changed")

    live = (ROOT / "src/live_bot.py").read_text(encoding="utf-8")
    settings = (ROOT / "config/settings.py").read_text(encoding="utf-8")
    tracker = (ROOT / "src/trade_tracker.py").read_text(encoding="utf-8")
    be = (ROOT / "src/micro_momentum_breakeven.py").read_text(encoding="utf-8")
    executor = (ROOT / "src/order_executor.py").read_text(encoding="utf-8")

    ok("ENABLE_MICRO_MOMENTUM_EXECUTION_REVERSAL = True" in settings, "toggle missing")
    ok('MICRO_MOMENTUM_LIVE_ALLOWED_STRENGTHS = ("NORMAL", "EXPLOSIVE")' in settings, "WEAK_VALID enabled")
    ok("MICRO_MOMENTUM_TELEGRAM_ENABLED = False" in settings, "Telegram firewall changed")

    guard_i = live.index("check_trade_guard(\n        execution_signal,")
    plan_i = live.index("trade_plan = calculate_trade_plan(", guard_i)
    memory_i = live.index("if is_trade_blocked_by_execution_memory(", plan_i)
    reverse_i = live.index("reversal_result = apply_micro_momentum_execution_reversal(", memory_i)
    mutate_i = live.index('signal = reversal_result["execution_signal"]', reverse_i)
    m15_i = live.index("micro_momentum_m15_guard = evaluate_micro_momentum_m15_direction_lock(", mutate_i)
    execute_i = live.index("execution_result = execute_trade(signal, trade_plan, SYMBOL)", m15_i)
    runner_i = live.index("register_low_mae_momentum_trade(", execute_i)
    ok(guard_i < plan_i < memory_i < reverse_i < mutate_i < m15_i < execute_i < runner_i, "execution ordering wrong")
    ok("signal=signal," in live[m15_i:m15_i + 500], "M15 does not see execution direction")
    ok("signal=signal," in live[runner_i:runner_i + 400], "Low-MAE does not see execution direction")
    ok('if position.type == mt5.POSITION_TYPE_BUY:' in be, "breakeven not using actual MT5 side")
    ok('startswith("micro_momentum_")' in tracker, "tracker telemetry persistence missing")
    ok("apply_authoritative_micro_momentum_geometry" in executor, "final geometry hook missing")
    ok("apply_micro_momentum_quote_safety" in executor, "quote safety hook missing")

    print("[PASS] SELL->BUY and BUY->SELL absolute swap")
    print("[PASS] toggle false restores original behavior")
    print("[PASS] original RR gate -> reversal -> M15 -> execution ordering")
    print("[PASS] final absolute geometry and reversal-aware quote safety")
    print("[PASS] actual-position management / telemetry wiring")
    print("[PASS] non-Micro, Telegram firewall, and WEAK_VALID isolation")
    print("[PASS] Micro Momentum execution reversal V1")


if __name__ == "__main__":
    main()
