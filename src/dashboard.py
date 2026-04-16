import json
from pathlib import Path
from datetime import datetime

from src.logger import logger


TRADES_FILE = Path("data/trades.json")
DASHBOARD_FILE = Path("data/dashboard.json")


def load_trades():
    if not TRADES_FILE.exists():
        return {}

    try:
        with open(TRADES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[DASHBOARD] Failed to load trades: {e}")
        return {}


def save_dashboard(data):
    try:
        DASHBOARD_FILE.parent.mkdir(exist_ok=True)
        with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[DASHBOARD] Failed to save dashboard: {e}")


def ensure_strategy_bucket(dashboard, strategy_name):
    if strategy_name not in dashboard["strategies"]:
        dashboard["strategies"][strategy_name] = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "unknown": 0,
            "winrate": 0.0,
            "total_max_profit_price": 0.0,
            "avg_max_profit_price": 0.0,
            "total_tp_buffer": 0.0,
            "avg_tp_buffer": 0.0,
        }


def ensure_condition_bucket(dashboard, condition_name):
    if condition_name not in dashboard["market_conditions"]:
        dashboard["market_conditions"][condition_name] = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "unknown": 0,
            "winrate": 0.0,
        }


def ensure_reason_bucket(dashboard, reason_name):
    if reason_name not in dashboard["reasons"]:
        dashboard["reasons"][reason_name] = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "unknown": 0,
            "winrate": 0.0,
        }


def finalize_bucket(bucket):
    total = bucket.get("total_trades", 0)
    wins = bucket.get("wins", 0)

    if total > 0:
        bucket["winrate"] = round((wins / total) * 100, 2)

    if "total_max_profit_price" in bucket:
        bucket["total_max_profit_price"] = round(bucket["total_max_profit_price"], 2)
        bucket["avg_max_profit_price"] = round(
            bucket["total_max_profit_price"] / total, 2
        ) if total > 0 else 0.0
        
    if "total_tp_buffer" in bucket:
        bucket["total_tp_buffer"] = round(bucket["total_tp_buffer"], 2)
        bucket["avg_tp_buffer"] = round(
            bucket["total_tp_buffer"] / total, 2
        ) if total > 0 else 0.0    


def rebuild_dashboard():
    trades = load_trades()

    dashboard = {
        "updated_at": datetime.now().isoformat(),
        "summary": {
            "total_closed_trades": 0,
            "wins": 0,
            "losses": 0,
            "unknown": 0,
            "winrate": 0.0,
        },
        "strategies": {},
        "market_conditions": {},
        "reasons": {},
    }

    for _, trade in trades.items():
        if trade.get("status") != "CLOSED":
            continue

        dashboard["summary"]["total_closed_trades"] += 1

        final_result = trade.get("final_result")
        strategy_name = trade.get("strategy", "UNKNOWN")
        market_condition = trade.get("market_condition", "UNKNOWN")
        reason = trade.get("reason", "UNKNOWN")
        max_profit_price = float(trade.get("max_profit_price", 0.0))
        tp_buffer = float(trade.get("tp_buffer", 0.0))

        ensure_strategy_bucket(dashboard, strategy_name)
        ensure_condition_bucket(dashboard, market_condition)
        ensure_reason_bucket(dashboard, reason)

        strategy_bucket = dashboard["strategies"][strategy_name]
        condition_bucket = dashboard["market_conditions"][market_condition]
        reason_bucket = dashboard["reasons"][reason]

        for bucket in [dashboard["summary"], strategy_bucket, condition_bucket, reason_bucket]:
            if final_result == "WIN":
                bucket["wins"] += 1
            elif final_result == "LOSS":
                bucket["losses"] += 1
            else:
                bucket["unknown"] += 1

            if bucket is not dashboard["summary"]:
                bucket["total_trades"] += 1

        strategy_bucket["total_max_profit_price"] += max_profit_price
        strategy_bucket["total_tp_buffer"] += tp_buffer

    summary_total = dashboard["summary"]["total_closed_trades"]
    if summary_total > 0:
        dashboard["summary"]["winrate"] = round(
            (dashboard["summary"]["wins"] / summary_total) * 100, 2
        )

    for bucket in dashboard["strategies"].values():
        finalize_bucket(bucket)

    for bucket in dashboard["market_conditions"].values():
        finalize_bucket(bucket)

    for bucket in dashboard["reasons"].values():
        finalize_bucket(bucket)

    save_dashboard(dashboard)
    logger.info("[DASHBOARD] Dashboard rebuilt successfully")