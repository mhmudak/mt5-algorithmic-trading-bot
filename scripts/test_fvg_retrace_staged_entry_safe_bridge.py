from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from src.execution_engine import ExecutionEngine
from src.fvg_retrace_smc_override import (
    evaluate_fvg_retrace_smc_override,
)


def sample_setup() -> dict:
    return {
        "strategy": "FVG",
        "signal": "BUY",
        "score": 98,
        "entry_model": "FVG_RETRACE_REACTION",
        "entry_reference": 4244.70,
        "sl_reference": 4234.10,
        "tp_reference": 4265.18,
        "rr": 1.93,
        "fvg_top": 4239.03,
        "fvg_bottom": 4236.31,
        "momentum": "bullish_displacement_reaction",
        "direction_context": "price_above_ema",
        "smc": [
            "ema_bullish",
            "bullish_bos",
            "fvg_present",
            "fvg_reclaimed",
        ],
        "reason": (
            "Bullish FVG -> retrace into gap 4236.31-4239.03 "
            "-> reaction confirmed -> EMA aligned"
        ),
    }


override = evaluate_fvg_retrace_smc_override(
    sample_setup(),
    "BUY",
)

assert override["allowed"] is True
assert (
    override["reason"]
    == "fvg_retrace_strategy_smc_override_allowed"
)
assert override["snapshot"]["orders_sent"] == 0


missing_smc = sample_setup()
missing_smc["smc"] = [
    "ema_bullish",
    "bullish_bos",
    "fvg_present",
]

assert (
    evaluate_fvg_retrace_smc_override(
        missing_smc,
        "BUY",
    )["reason"]
    == "fvg_retrace_smc_evidence_missing"
)


low_rr = sample_setup()
low_rr["rr"] = 1.79

assert (
    evaluate_fvg_retrace_smc_override(
        low_rr,
        "BUY",
    )["reason"]
    == "fvg_retrace_rr_too_low"
)


df = pd.DataFrame(
    [
        {"open": 4237.0, "high": 4239.0, "low": 4236.5, "close": 4238.0},
        {"open": 4238.0, "high": 4246.0, "low": 4237.5, "close": 4245.0},
        {"open": 4240.0, "high": 4245.0, "low": 4238.5, "close": 4244.7},
        {"open": 4244.7, "high": 4245.0, "low": 4244.0, "close": 4244.5},
    ]
)

engine = ExecutionEngine()
setup = engine.register_setup(
    sample_setup(),
    current_price=4244.70,
    atr=7.0,
)

ready = engine.process_setups(
    df=df,
    price=4244.70,
    atr=7.0,
)

assert ready == [setup]
assert setup["state"] == "READY"
assert (
    setup["data"]["execution_confirmation"]
    == "strategy_confirmed_fvg_retrace_reaction"
)

engine.mark_wait_fvg_staged_entry(
    setup=setup,
    stages=[
        {
            "stage_name": "FVG_STAGE_1",
            "target_entry": 4239.03,
            "lot": 0.03,
            "executed": False,
        }
    ],
    expiry_minutes=30,
)

ready_again = engine.process_setups(
    df=df,
    price=4244.70,
    atr=7.0,
)

assert ready_again == []
assert setup["state"] == "WAIT_FVG_STAGED_ENTRY"


source_path = Path("src/live_bot.py")
source = source_path.read_text(encoding="utf-8")
tree = ast.parse(source)

helper_nodes = [
    node
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    and node.name in {
        "build_fvg_staged_entry_prices",
        "allocate_fvg_staged_lots",
    }
]

assert len(helper_nodes) == 2

namespace = {
    "FVG_ZONE_STAGED_ENTRY_LEVELS": [0.0, 0.60, 0.85],
    "mt5": SimpleNamespace(
        symbol_info=lambda _symbol: SimpleNamespace(
            volume_min=0.01,
            volume_step=0.01,
        )
    ),
}

exec(
    compile(
        ast.Module(
            body=helper_nodes,
            type_ignores=[],
        ),
        filename=str(source_path),
        mode="exec",
    ),
    namespace,
)

prices = namespace["build_fvg_staged_entry_prices"](
    "BUY",
    4239.03,
    4236.31,
)

assert prices == [4239.03, 4237.4, 4236.72]

lots = namespace["allocate_fvg_staged_lots"](
    "XAUUSD",
    0.06,
    len(prices),
)

assert lots == [0.02, 0.02, 0.02]
assert round(sum(lots), 2) == 0.06

required_markers = (
    "TOTAL_LOT_SPLIT_ACROSS_STAGES",
    "[FVG STAGED ENTRY] RR invalid",
    "[FVG STAGED ENTRY] News blocked",
    "[FVG STAGED ENTRY] Time blocked",
    "[FVG STAGED ENTRY] Guard blocked",
    "[FVG STAGED ENTRY] Exposure blocked",
    "[FVG RETRACE SMC OVERRIDE] allowed",
)

for marker in required_markers:
    assert marker in source, marker

print(
    "[PASS] FVG retrace strategy bridge, strict SMC override, "
    "staged lot preservation, and trigger safety passed."
)
