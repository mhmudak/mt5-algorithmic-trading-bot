from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.order_flow_providers.rithmic_protocol import (
    RithmicMarketDataClient,
    load_rithmic_config,
    RithmicConfig,
)


def _utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--exchange", default=None)
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--output-dir", default="data/order_flow/rithmic")
    args = parser.parse_args()

    base_config = load_rithmic_config()

    config = RithmicConfig(
        ws_url=base_config.ws_url,
        system_name=base_config.system_name,
        username=base_config.username,
        password=base_config.password,
        exchange=args.exchange or base_config.exchange,
        symbol=args.symbol or base_config.symbol,
        sdk_path=base_config.sdk_path,
    )

    if not config.username or not config.password:
        raise SystemExit("[STOP] Missing RITHMIC_USERNAME or RITHMIC_PASSWORD in .env")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{config.symbol}_{_utc_stamp()}_market_data.jsonl"

    client = RithmicMarketDataClient(config)

    stats = {
        "symbol": config.symbol,
        "exchange": config.exchange,
        "duration_seconds": args.duration_seconds,
        "login_ok": False,
        "market_data_ok": False,
        "last_trade_count": 0,
        "bbo_count": 0,
        "buy_volume": 0,
        "sell_volume": 0,
        "cumulative_delta": 0,
        "output_path": str(output_path),
    }

    with output_path.open("w", encoding="utf-8") as f:
        async for event in client.stream(duration_seconds=args.duration_seconds):
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()

            event_type = event.get("event_type")

            if event_type == "login_response":
                stats["login_ok"] = bool(event.get("ok"))
                print("[LOGIN]", event)

            elif event_type == "market_data_response":
                rp_code = event.get("rp_code")
                stats["market_data_ok"] = bool(rp_code and rp_code[0] == "0")
                print("[MARKET_DATA_RESPONSE]", event)

            elif event_type == "last_trade":
                stats["last_trade_count"] += 1

                size = int(event.get("trade_size") or 0)
                if event.get("aggressor") == "BUY":
                    stats["buy_volume"] += size
                    stats["cumulative_delta"] += size
                else:
                    stats["sell_volume"] += size
                    stats["cumulative_delta"] -= size

                print(
                    "[LAST_TRADE]",
                    event.get("symbol"),
                    event.get("trade_price"),
                    event.get("trade_size"),
                    event.get("aggressor"),
                    "cum_delta=",
                    stats["cumulative_delta"],
                )

            elif event_type == "best_bid_offer":
                stats["bbo_count"] += 1
                print(
                    "[BBO]",
                    event.get("symbol"),
                    "bid=",
                    event.get("bid_price"),
                    "ask=",
                    event.get("ask_price"),
                )

    print("")
    print("[SUMMARY]")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("")
        print("[STOPPED] Interrupted by user. Partial data was already saved to JSONL.")
