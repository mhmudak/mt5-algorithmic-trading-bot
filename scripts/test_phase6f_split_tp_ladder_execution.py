from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import src.order_executor as oe  # noqa: E402


class FakeSymbolInfo:
    volume_min = 0.01
    volume_step = 0.01


def main() -> None:
    assert oe._split_lot_by_symbol_rules(0.03, FakeSymbolInfo(), 3) == [0.01, 0.01, 0.01]
    assert oe._split_lot_by_symbol_rules(0.05, FakeSymbolInfo(), 3) == [0.02, 0.02, 0.01]
    assert oe._split_lot_by_symbol_rules(0.02, FakeSymbolInfo(), 3) == []
    assert oe._split_lot_by_symbol_rules(0.02, FakeSymbolInfo(), 2) == [0.01, 0.01]

    old_symbol_info = oe.mt5.symbol_info

    try:
        oe.mt5.symbol_info = lambda symbol: FakeSymbolInfo()

        trade_plan = {
            "strategy": "SESSION_ORB_RETEST",
            "signal": "SELL",
            "entry_price": 4082.89,
            "stop_loss": 4091.48,
            "take_profit": 4075.27,
            "original_take_profit": 4066.92,
            "original_rr": 1.86,
            "rr": 1.86,
            "lot": 0.03,
            "comment": "SESORB",
            "tp_ladder": [
                {"name": "TP1_BEFORE_KEY_BARRIER", "price": 4075.27, "rr": 0.89},
                {"name": "TP2_AFTER_BARRIER_BREAK", "price": 4071.10, "rr": 1.37},
                {"name": "TP3_ORIGINAL_EXTENSION", "price": 4066.92, "rr": 1.86},
            ],
        }

        children = oe._build_tp_ladder_split_children("SELL", trade_plan, "XAUUSD")

    finally:
        oe.mt5.symbol_info = old_symbol_info

    print("[SPLIT CHILDREN]")
    for child in children:
        print(child)

    assert len(children) == 3
    assert [child["lot"] for child in children] == [0.01, 0.01, 0.01]
    assert [child["take_profit"] for child in children] == [4075.27, 4071.10, 4066.92]
    assert all(child["tp_ladder_child_order"] is True for child in children)
    assert all(child["rr"] == 1.86 for child in children)
    assert all(child["original_rr"] == 1.86 for child in children)
    assert children[0]["comment"].endswith("_TP1")
    assert children[1]["comment"].endswith("_TP2")
    assert children[2]["comment"].endswith("_TP3")

    live_text = (ROOT / "src" / "live_bot.py").read_text(encoding="utf-8")
    ladder_text = (ROOT / "src" / "key_level_tp_ladder.py").read_text(encoding="utf-8")

    assert "ORIGINAL_FULL_TP_RR_AFTER_TP_LADDER" in ladder_text
    assert "key_level_tp_ladder_applied" in live_text
    assert "original_rr" in live_text

    print("")
    print("[PASS] Phase 6F split TP ladder execution uses dynamic lot split and original RR.")


if __name__ == "__main__":
    main()
