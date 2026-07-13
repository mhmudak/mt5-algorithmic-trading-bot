import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def resolve_paths(source_dir):
    source_dir = Path(source_dir)

    if not source_dir.is_absolute():
        source_dir = PROJECT_ROOT / source_dir

    account_name = source_dir.name
    output_dir = PROJECT_ROOT / "data" / "strategy_intelligence" / account_name
    output_dir.mkdir(parents=True, exist_ok=True)

    return {
        "source_dir": source_dir,
        "account_name": account_name,
        "output_dir": output_dir,
        "trades_file": source_dir / "trades.json",
        "report_json": output_dir / "mt5_closed_deal_history_report.json",
    }


def read_json(path, default=None):
    path = Path(path)

    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)

    return path


def flatten_json_container(payload):
    rows = []

    if isinstance(payload, list):
        rows.extend([x for x in payload if isinstance(x, dict)])
    elif isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                rows.extend([x for x in value if isinstance(x, dict)])
            elif isinstance(value, dict):
                rows.append(value)

    return rows


def parse_dt(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def safe_int(value):
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def find_trade(trades, setup_id):
    matches = []

    for row in trades:
        if setup_id in json.dumps(row, ensure_ascii=False, default=str):
            matches.append(row)

    return matches[-1] if matches else None


def namedtuple_to_dict(item):
    if item is None:
        return None

    if hasattr(item, "_asdict"):
        return dict(item._asdict())

    try:
        return dict(item)
    except Exception:
        return {"repr": repr(item)}


def map_entry(mt5, value):
    mapping = {
        getattr(mt5, "DEAL_ENTRY_IN", None): "IN",
        getattr(mt5, "DEAL_ENTRY_OUT", None): "OUT",
        getattr(mt5, "DEAL_ENTRY_INOUT", None): "INOUT",
        getattr(mt5, "DEAL_ENTRY_OUT_BY", None): "OUT_BY",
    }
    return mapping.get(value, value)


def map_reason(mt5, value):
    mapping = {
        getattr(mt5, "DEAL_REASON_CLIENT", None): "CLIENT",
        getattr(mt5, "DEAL_REASON_MOBILE", None): "MOBILE",
        getattr(mt5, "DEAL_REASON_WEB", None): "WEB",
        getattr(mt5, "DEAL_REASON_EXPERT", None): "EXPERT",
        getattr(mt5, "DEAL_REASON_SL", None): "SL",
        getattr(mt5, "DEAL_REASON_TP", None): "TP",
        getattr(mt5, "DEAL_REASON_SO", None): "SO",
    }
    return mapping.get(value, value)


def enrich_deal(mt5, deal):
    d = namedtuple_to_dict(deal)

    if not d:
        return d

    if "time" in d and d.get("time") is not None:
        try:
            d["time_iso"] = datetime.fromtimestamp(d["time"]).isoformat()
        except Exception:
            pass

    d["entry_label"] = map_entry(mt5, d.get("entry"))
    d["reason_label"] = map_reason(mt5, d.get("reason"))

    return d


def main():
    parser = argparse.ArgumentParser(
        description="Inspect MT5 deal history for a closed trade setup."
    )

    parser.add_argument(
        "--source-dir",
        default=r"data/accounts/Tickmill-Demo_25323531",
    )

    parser.add_argument(
        "--setup-id",
        required=True,
    )

    parser.add_argument(
        "--minutes-buffer",
        type=int,
        default=30,
    )

    args = parser.parse_args()

    paths = resolve_paths(args.source_dir)

    trades_payload = read_json(paths["trades_file"], default=[])
    trades = flatten_json_container(trades_payload)

    trade = find_trade(trades, args.setup_id)

    if not trade:
        raise SystemExit(f"[STOP] No trade found for setup_id={args.setup_id}")

    open_time = parse_dt(trade.get("open_time"))
    close_time = parse_dt(trade.get("close_time"))

    if not open_time:
        raise SystemExit("[STOP] Trade has no valid open_time")

    from_time = open_time - timedelta(minutes=args.minutes_buffer)
    to_time = (close_time or datetime.now()) + timedelta(minutes=args.minutes_buffer)

    ids = {
        "position_id": safe_int(trade.get("position_id")),
        "main_position_id": safe_int(trade.get("main_position_id")),
        "order_id": safe_int(trade.get("order_id")),
        "deal_id": safe_int(trade.get("deal_id")),
        "raw_deal_id": safe_int(trade.get("raw_deal_id")),
        "raw_order_id": safe_int(trade.get("raw_order_id")),
    }

    symbol = trade.get("symbol")

    try:
        import MetaTrader5 as mt5
    except Exception as exc:
        raise SystemExit(f"[STOP] MetaTrader5 import failed: {exc}")

    initialized = mt5.initialize()

    if not initialized:
        report = {
            "created_at": datetime.now().isoformat(),
            "phase": "Phase 2Y",
            "setup_id": args.setup_id,
            "mt5_initialized": False,
            "mt5_last_error": mt5.last_error(),
            "trade": trade,
            "generated_files": {
                "report_json": str(paths["report_json"]),
            },
        }
        write_json(paths["report_json"], report)

        print("[PHASE 2Y MT5 CLOSED DEAL HISTORY]")
        print("setup_id =", args.setup_id)
        print("mt5_initialized = False")
        print("mt5_last_error =", mt5.last_error())
        print("report =", paths["report_json"])
        return

    deals = mt5.history_deals_get(from_time, to_time)
    orders = mt5.history_orders_get(from_time, to_time)

    raw_deals = [enrich_deal(mt5, deal) for deal in deals] if deals else []
    raw_orders = [namedtuple_to_dict(order) for order in orders] if orders else []

    id_values = {v for v in ids.values() if v is not None}

    matched_deals = []

    for deal in raw_deals:
        text = json.dumps(deal, ensure_ascii=False, default=str)

        numeric_match = any(str(v) in text for v in id_values)
        symbol_match = not symbol or deal.get("symbol") == symbol

        if numeric_match and symbol_match:
            matched_deals.append(deal)

    symbol_window_deals = [
        deal
        for deal in raw_deals
        if not symbol or deal.get("symbol") == symbol
    ]

    close_deals = [
        deal
        for deal in matched_deals
        if deal.get("entry_label") in ["OUT", "INOUT", "OUT_BY"]
    ]

    # Phase 2Z:
    # Strict mode. Never infer the target trade result from unrelated
    # XAUUSD close deals in the same time window.
    unrelated_symbol_close_deals = [
        deal
        for deal in symbol_window_deals
        if deal.get("entry_label") in ["OUT", "INOUT", "OUT_BY"]
        and deal not in close_deals
    ]

    total_profit = sum(float(deal.get("profit") or 0) for deal in close_deals)
    total_commission = sum(float(deal.get("commission") or 0) for deal in close_deals)
    total_swap = sum(float(deal.get("swap") or 0) for deal in close_deals)

    close_prices = [
        deal.get("price")
        for deal in close_deals
        if deal.get("price") is not None
    ]

    close_reasons = sorted({
        str(deal.get("reason_label"))
        for deal in close_deals
        if deal.get("reason_label") is not None
    })

    inferred = {
        "has_close_deal": bool(close_deals),
        "close_deal_count": len(close_deals),
        "total_profit": round(total_profit, 2),
        "total_commission": round(total_commission, 2),
        "total_swap": round(total_swap, 2),
        "net_profit": round(total_profit + total_commission + total_swap, 2),
        "close_prices": close_prices,
        "close_reasons": close_reasons,
    }

    if close_reasons:
        if "TP" in close_reasons:
            inferred["final_result_guess"] = "TP"
        elif "SL" in close_reasons:
            inferred["final_result_guess"] = "SL"
        elif inferred["net_profit"] > 0:
            inferred["final_result_guess"] = "CLOSED_PROFIT"
        elif inferred["net_profit"] < 0:
            inferred["final_result_guess"] = "CLOSED_LOSS"
        else:
            inferred["final_result_guess"] = "CLOSED_FLAT"
    else:
        inferred["final_result_guess"] = "TARGET_CLOSE_DEAL_NOT_FOUND"

    inferred["unrelated_symbol_close_deal_count"] = len(unrelated_symbol_close_deals)

    report = {
        "created_at": datetime.now().isoformat(),
        "phase": "Phase 2Y",
        "setup_id": args.setup_id,
        "source_dir": str(paths["source_dir"]),
        "output_dir": str(paths["output_dir"]),
        "mt5_initialized": True,
        "time_window": {
            "from": from_time.isoformat(),
            "to": to_time.isoformat(),
        },
        "ids": ids,
        "trade": trade,
        "inferred": inferred,
        "matched_deals": matched_deals,
        "close_deals": close_deals,
        "unrelated_symbol_close_deals": unrelated_symbol_close_deals,
        "symbol_window_deals": symbol_window_deals,
        "orders_in_window": raw_orders,
        "generated_files": {
            "report_json": str(paths["report_json"]),
        },
        "notes": [
            "This script is diagnostic only.",
            "It does not modify trades.json or setup_outcomes.json.",
            "Use close_deals to decide whether trade_tracker reconciliation is required.",
        ],
    }

    write_json(paths["report_json"], report)

    print("[PHASE 2Y MT5 CLOSED DEAL HISTORY]")
    print("setup_id =", args.setup_id)
    print("mt5_initialized = True")

    print()
    print("[TRADE]")
    print("position_id =", trade.get("position_id"))
    print("main_position_id =", trade.get("main_position_id"))
    print("order_id =", trade.get("order_id"))
    print("deal_id =", trade.get("deal_id"))
    print("status =", trade.get("status"))
    print("open_time =", trade.get("open_time"))
    print("close_time =", trade.get("close_time"))
    print("entry_price =", trade.get("entry_price"))
    print("stop_loss =", trade.get("stop_loss"))
    print("take_profit =", trade.get("take_profit"))

    print()
    print("[DEALS]")
    print("matched_deal_count =", len(matched_deals))
    print("close_deal_count =", len(close_deals))
    print("unrelated_symbol_close_deal_count =", len(unrelated_symbol_close_deals))
    print("symbol_window_deal_count =", len(symbol_window_deals))

    print()
    print("[INFERRED]")
    for key, value in inferred.items():
        print(f"{key} = {value}")

    print()
    print("[CLOSE DEALS]")
    for deal in close_deals:
        print(json.dumps({
            "ticket": deal.get("ticket"),
            "order": deal.get("order"),
            "position_id": deal.get("position_id"),
            "time_iso": deal.get("time_iso"),
            "symbol": deal.get("symbol"),
            "type": deal.get("type"),
            "entry": deal.get("entry"),
            "entry_label": deal.get("entry_label"),
            "reason": deal.get("reason"),
            "reason_label": deal.get("reason_label"),
            "volume": deal.get("volume"),
            "price": deal.get("price"),
            "profit": deal.get("profit"),
            "commission": deal.get("commission"),
            "swap": deal.get("swap"),
            "comment": deal.get("comment"),
        }, indent=2, ensure_ascii=False))

    print()
    print("report =", paths["report_json"])

    mt5.shutdown()


if __name__ == "__main__":
    main()
