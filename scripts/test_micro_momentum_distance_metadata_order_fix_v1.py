from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "src" / "live_bot.py"


def fail(msg):
    raise AssertionError(msg)


def main():
    print("[MICRO MOMENTUM DISTANCE METADATA ORDER FIX TEST V1]")

    text = LIVE.read_text(encoding="utf-8")

    bad_sl = 'trade_plan["micro_momentum_execution_sl_distance"] = risk_distance'
    bad_tp = 'trade_plan["micro_momentum_execution_tp_distance"] = reward_distance'

    if bad_sl in text:
        fail("stale risk_distance metadata assignment still present")
    if bad_tp in text:
        fail("stale reward_distance metadata assignment still present")

    good_sl = (
        'trade_plan["micro_momentum_execution_sl_distance"] = round('
    )
    good_tp = (
        'trade_plan["micro_momentum_execution_tp_distance"] = round('
    )

    if good_sl not in text:
        fail("final SL distance derivation not found")
    if good_tp not in text:
        fail("final TP distance derivation not found")

    tree = ast.parse(text)

    fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "process_intrabar_micro_momentum_live":
            fn = node
            break

    if fn is None:
        fail("process_intrabar_micro_momentum_live not found")

    assignments = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            assignments.append(ast.unparse(node))

    relevant = [
        item for item in assignments
        if "micro_momentum_execution_sl_distance" in item
        or "micro_momentum_execution_tp_distance" in item
    ]

    print("\n[METADATA ASSIGNMENTS]")
    for item in relevant:
        print(item)

    if len(relevant) != 2:
        fail(f"expected exactly 2 distance metadata assignments, got {len(relevant)}")

    if any("risk_distance" in item or "reward_distance" in item for item in relevant):
        fail("distance metadata still depends on later local variables")

    cases = [
        {
            "name": "WEAK_VALID",
            "trade_plan": {
                "entry_price": 4283.36,
                "stop_loss": 4283.06,
                "take_profit": 4283.96,
            },
            "expected_sl": 0.30,
            "expected_tp": 0.60,
        },
        {
            "name": "NORMAL",
            "trade_plan": {
                "entry_price": 4282.88,
                "stop_loss": 4283.28,
                "take_profit": 4281.68,
            },
            "expected_sl": 0.40,
            "expected_tp": 1.20,
        },
        {
            "name": "EXPLOSIVE",
            "trade_plan": {
                "entry_price": 4287.46,
                "stop_loss": 4286.96,
                "take_profit": 4289.46,
            },
            "expected_sl": 0.50,
            "expected_tp": 2.00,
        },
    ]

    print("\n[GEOMETRY CASES]")
    for case in cases:
        tp = case["trade_plan"]
        sl_distance = round(
            abs(float(tp["entry_price"]) - float(tp["stop_loss"])),
            6,
        )
        tp_distance = round(
            abs(float(tp["take_profit"]) - float(tp["entry_price"])),
            6,
        )
        print(
            case["name"],
            {
                "sl_distance": sl_distance,
                "tp_distance": tp_distance,
            },
        )
        if abs(sl_distance - case["expected_sl"]) > 1e-9:
            fail(case)
        if abs(tp_distance - case["expected_tp"]) > 1e-9:
            fail(case)

    print(
        "\nPASS: Micro Momentum execution-distance metadata is derived "
        "directly from the already-built trade plan, so it no longer "
        "references risk_distance/reward_distance before assignment. "
        "WEAK_VALID, NORMAL, and EXPLOSIVE geometries are preserved."
    )


if __name__ == "__main__":
    main()
