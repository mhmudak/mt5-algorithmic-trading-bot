from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PHASE = "PHASE_5AF_RITHMIC_DOM_BBO_CONSISTENCY_CHECK"

ROOT = Path(__file__).resolve().parents[1]
ORDER_FLOW_DIR = ROOT / "data" / "order_flow" / "rithmic"

OUT_JSON = ORDER_FLOW_DIR / "phase5af_rithmic_dom_bbo_consistency_check.json"
OUT_TXT = ORDER_FLOW_DIR / "phase5af_rithmic_dom_bbo_consistency_check_summary.txt"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def deep_find(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]

        for value in obj.values():
            found = deep_find(value, key)
            if found is not None:
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = deep_find(item, key)
            if found is not None:
                return found

    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="MGCQ6")
    parser.add_argument("--max-difference", type=float, default=1.0)
    args = parser.parse_args()

    symbol = args.symbol.upper()
    state_path = ORDER_FLOW_DIR / f"{symbol}_phase5c_rithmic_state_latest.json"
    state = load_json(state_path)

    order_book = state.get("order_book") or {}
    latest_bbo = state.get("latest_bbo") or {}

    bbo_bid = as_float(
        latest_bbo.get("last_bid")
        or latest_bbo.get("bid")
        or latest_bbo.get("bid_price")
        or deep_find(state, "last_bid")
    )
    bbo_ask = as_float(
        latest_bbo.get("last_ask")
        or latest_bbo.get("ask")
        or latest_bbo.get("ask_price")
        or deep_find(state, "last_ask")
    )

    dom_bid = as_float(order_book.get("top_bid_price") or deep_find(state, "top_bid_price"))
    dom_ask = as_float(order_book.get("top_ask_price") or deep_find(state, "top_ask_price"))

    bid_diff = abs(dom_bid - bbo_bid) if dom_bid > 0 and bbo_bid > 0 else None
    ask_diff = abs(dom_ask - bbo_ask) if dom_ask > 0 and bbo_ask > 0 else None

    bbo_available = bbo_bid > 0 and bbo_ask > 0
    dom_available = dom_bid > 0 and dom_ask > 0

    bid_consistent = bid_diff is not None and bid_diff <= args.max_difference
    ask_consistent = ask_diff is not None and ask_diff <= args.max_difference

    consistent = bool(bbo_available and dom_available and bid_consistent and ask_consistent)

    if consistent:
        status = "DOM_BBO_CONSISTENT_OBSERVE_ONLY"
        recommendation = "DOM top of book and BBO are consistent. Keep observe-only."
    else:
        status = "REJECTED_DOM_BBO_MISMATCH_OR_MISSING"
        recommendation = (
            "Do not use DOM for manual confidence or automation until DOM/BBO consistency passes. "
            "This may be a Rithmic Test/feed issue or a parser/cache issue."
        )

    report = {
        "phase": PHASE,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol,
        "state_path": str(state_path),
        "mode": "OBSERVE_ONLY",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "safe_for_execution": False,
        "trade_action": "NO_AUTO_TRADE",
        "status": status,
        "consistent": consistent,
        "max_difference": args.max_difference,
        "bbo": {
            "available": bbo_available,
            "bid": bbo_bid,
            "ask": bbo_ask,
            "spread": round(bbo_ask - bbo_bid, 10) if bbo_available else None,
        },
        "dom": {
            "available": dom_available,
            "top_bid": dom_bid,
            "top_ask": dom_ask,
            "spread": round(dom_ask - dom_bid, 10) if dom_available else None,
            "bid_depth": order_book.get("bid_depth"),
            "ask_depth": order_book.get("ask_depth"),
        },
        "diff": {
            "bid_diff": bid_diff,
            "ask_diff": ask_diff,
            "bid_consistent": bid_consistent,
            "ask_consistent": ask_consistent,
        },
        "recommendation": recommendation,
    }

    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "[PHASE 5AF RITHMIC DOM/BBO CONSISTENCY CHECK]",
        f"updated_at = {report['updated_at']}",
        f"symbol = {symbol}",
        f"mode = {report['mode']}",
        f"decision_impact = {report['decision_impact']}",
        f"can_influence_decision = {report['can_influence_decision']}",
        f"safe_for_execution = {report['safe_for_execution']}",
        f"trade_action = {report['trade_action']}",
        "",
        "[STATUS]",
        f"status = {status}",
        f"consistent = {consistent}",
        f"max_difference = {args.max_difference}",
        "",
        "[BBO]",
        f"available = {bbo_available}",
        f"bid = {bbo_bid}",
        f"ask = {bbo_ask}",
        f"spread = {report['bbo']['spread']}",
        "",
        "[DOM TOP]",
        f"available = {dom_available}",
        f"top_bid = {dom_bid}",
        f"top_ask = {dom_ask}",
        f"spread = {report['dom']['spread']}",
        f"bid_depth = {report['dom']['bid_depth']}",
        f"ask_depth = {report['dom']['ask_depth']}",
        "",
        "[DIFF]",
        f"bid_diff = {bid_diff}",
        f"ask_diff = {ask_diff}",
        f"bid_consistent = {bid_consistent}",
        f"ask_consistent = {ask_consistent}",
        "",
        "[RECOMMENDATION]",
        recommendation,
        "",
        f"json = {OUT_JSON}",
        f"summary = {OUT_TXT}",
    ]

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()