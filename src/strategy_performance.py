import json
from pathlib import Path
from datetime import datetime

from src.logger import logger


TRADES_FILE = Path("data/trades.json")
PERFORMANCE_FILE = Path("data/strategy_performance.json")


def load_trades():
    if not TRADES_FILE.exists():
        return {}

    try:
        with open(TRADES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[PERF] Failed to load trades: {e}")
        return {}


def load_performance():
    if not PERFORMANCE_FILE.exists():
        return {}

    try:
        with open(PERFORMANCE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[PERF] Failed to load performance: {e}")
        return {}


def save_performance(data):
    try:
        PERFORMANCE_FILE.parent.mkdir(exist_ok=True)
        with open(PERFORMANCE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[PERF] Failed to save performance: {e}")


def ensure_strategy_bucket(performance, strategy_name):
    if strategy_name not in performance:
        performance[strategy_name] = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "unknown": 0,
            "total_max_profit_price": 0.0,
            "avg_max_profit_price": 0.0,
            "last_updated": None,
        }


def rebuild_strategy_performance():
    trades = load_trades()
    performance = {}

    for _, trade in trades.items():
        if trade.get("status") != "CLOSED":
            continue

        strategy_name = trade.get("strategy", "UNKNOWN")
        ensure_strategy_bucket(performance, strategy_name)

        bucket = performance[strategy_name]
        bucket["total_trades"] += 1

        final_result = trade.get("final_result")
        if final_result == "WIN":
            bucket["wins"] += 1
        elif final_result == "LOSS":
            bucket["losses"] += 1
        else:
            bucket["unknown"] += 1

        bucket["total_max_profit_price"] += float(trade.get("max_profit_price", 0.0))

    for strategy_name, bucket in performance.items():
        total = bucket["total_trades"]
        if total > 0:
            bucket["avg_max_profit_price"] = round(
                bucket["total_max_profit_price"] / total, 2
            )
        bucket["total_max_profit_price"] = round(bucket["total_max_profit_price"], 2)
        bucket["last_updated"] = datetime.now().isoformat()

    save_performance(performance)
    logger.info("[PERF] Strategy performance rebuilt successfully")


def get_strategy_winrate(strategy_name, performance=None):
    if performance is None:
        performance = load_performance()

    bucket = performance.get(strategy_name)
    if not bucket:
        return 0.0

    total = bucket.get("total_trades", 0)
    wins = bucket.get("wins", 0)

    if total == 0:
        return 0.0

    return round((wins / total) * 100, 2)