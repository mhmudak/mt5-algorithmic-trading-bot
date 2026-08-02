
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import json
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market_outlook_engine import (
    build_market_outlook,
    format_market_outlook_telegram,
    load_latest_market_outlook,
    outlook_changed,
    save_market_outlook,
)


def _mt5_timeframe(mt5, timeframe: str):
    mapping = {
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
        "W1": mt5.TIMEFRAME_W1,
    }

    if timeframe not in mapping:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    return mapping[timeframe]


def _fetch_mt5_frame(mt5, symbol: str, timeframe: str, bars: int) -> pd.DataFrame:
    tf = _mt5_timeframe(mt5, timeframe)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)

    if rates is None or len(rates) < 60:
        raise RuntimeError(f"Not enough MT5 data for {symbol} {timeframe}")

    df = pd.DataFrame(rates)

    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], unit="s", errors="coerce")

    return df


def fetch_market_frames(symbol: str) -> dict[str, pd.DataFrame]:
    import MetaTrader5 as mt5

    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    try:
        return {
            "W1": _fetch_mt5_frame(mt5, symbol, "W1", 120),
            "D1": _fetch_mt5_frame(mt5, symbol, "D1", 180),
            "H4": _fetch_mt5_frame(mt5, symbol, "H4", 240),
            "H1": _fetch_mt5_frame(mt5, symbol, "H1", 240),
            "M15": _fetch_mt5_frame(mt5, symbol, "M15", 700),
        }
    finally:
        mt5.shutdown()


def load_news_events(path: str | None) -> list[dict]:
    if not path:
        return []

    p = Path(path)

    if not p.exists():
        raise FileNotFoundError(path)

    data = json.loads(p.read_text(encoding="utf-8"))

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        return data.get("events") or []

    return []


def ensure_likely_scenarios_heading(message: str) -> str:
    text = str(message)

    if "Likely Scenarios:" in text:
        text = text.replace("\nLikely Scenarios:\n\n1. ", "\nLikely Scenarios:\n1. ")
        return text

    return text.replace("\n\n1. ", "\n\nLikely Scenarios:\n1. ", 1)


def send_telegram_message_safe(message: str) -> bool:
    try:
        from src.notifier import send_telegram_message

        result = send_telegram_message(message)
        return result is not False
    except Exception as exc:
        print(f"[TELEGRAM] skipped/failed: {exc}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--report-type", default="daily", choices=["daily", "weekly", "ny_update", "scenario_update"])
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--notify-only-if-changed", action="store_true")
    parser.add_argument("--news-events-json", default=None)
    args = parser.parse_args()

    previous = load_latest_market_outlook(args.symbol, args.report_type)

    frames = fetch_market_frames(args.symbol)
    news_events = load_news_events(args.news_events_json)

    outlook = build_market_outlook(
        frames,
        report_type=args.report_type,
        symbol=args.symbol,
        generated_at=datetime.now(),
        news_events=news_events,
    )

    changed = outlook_changed(previous, outlook)
    output_path = save_market_outlook(outlook)
    message = ensure_likely_scenarios_heading(format_market_outlook_telegram(outlook))

    telegram_sent = False

    should_send = args.send_telegram and (
        changed or not args.notify_only_if_changed
    )

    if should_send:
        prefix = ""
        if previous and changed:
            prefix = "🔔 OUTLOOK CHANGED\n\n"
        elif not previous:
            prefix = "🆕 NEW OUTLOOK BASELINE\n\n"

        telegram_sent = send_telegram_message_safe(prefix + message)

    print("[PHASE 6S1 MARKET OUTLOOK]")
    print(f"symbol = {args.symbol}")
    print(f"report_type = {args.report_type}")
    print(f"changed = {changed}")
    print(f"saved = {output_path}")
    print(f"send_telegram = {args.send_telegram}")
    print(f"telegram_sent = {telegram_sent}")
    print(f"decision_impact = {outlook['decision_impact']}")
    print(f"auto_trade_allowed = {outlook['auto_trade_allowed']}")
    print("")
    print(message)


if __name__ == "__main__":
    main()
