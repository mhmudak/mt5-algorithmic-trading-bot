from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.order_flow_features.rithmic_state_cache import (
    RithmicRollingStateCache,
    write_state_json,
    write_state_text,
)
from src.order_flow_providers.rithmic_protocol import (
    RithmicConfig,
    RithmicMarketDataClient,
    load_rithmic_config,
)


def _safe_symbol_for_file(symbol: str) -> str:
    return symbol.replace("/", "_").replace("\\", "_").replace(".", "_")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--exchange", default=None)
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--rolling-window-seconds", type=int, default=300)
    parser.add_argument("--bucket-seconds", type=int, default=60)
    parser.add_argument("--stale-after-seconds", type=int, default=15)
    parser.add_argument("--tick-size", type=float, default=0.1)
    parser.add_argument("--snapshot-interval-seconds", type=int, default=5)
    parser.add_argument("--output-dir", default="data/order_flow/rithmic")
    args = parser.parse_args()

    base = load_rithmic_config()

    config = RithmicConfig(
        ws_url=base.ws_url,
        system_name=base.system_name,
        username=base.username,
        password=base.password,
        exchange=args.exchange or base.exchange,
        symbol=args.symbol or base.symbol,
        sdk_path=base.sdk_path,
    )

    if not config.username or not config.password:
        raise SystemExit("[STOP] Missing RITHMIC_USERNAME or RITHMIC_PASSWORD in .env")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_symbol = _safe_symbol_for_file(config.symbol)
    latest_json = output_dir / f"{safe_symbol}_phase5c_rithmic_state_latest.json"
    latest_txt = output_dir / f"{safe_symbol}_phase5c_rithmic_state_latest.txt"

    client = RithmicMarketDataClient(config)
    cache = RithmicRollingStateCache(
        symbol=config.symbol,
        exchange=config.exchange,
        tick_size=args.tick_size,
        rolling_window_seconds=args.rolling_window_seconds,
        bucket_seconds=args.bucket_seconds,
        stale_after_seconds=args.stale_after_seconds,
    )

    latest_snapshot = None
    last_snapshot_write = 0.0

    print("[START] Phase 5C Rithmic real-time state cache")
    print("symbol =", config.symbol)
    print("exchange =", config.exchange)
    print("duration_seconds =", args.duration_seconds)
    print("decision_impact = NONE")

    async for event in client.stream(duration_seconds=args.duration_seconds):
        latest_snapshot = cache.update(event)
        now = time.time()

        event_type = event.get("event_type")

        if event_type == "login_response":
            print("[LOGIN]", "ok=", event.get("ok"), "rp_code=", event.get("rp_code"))

        elif event_type == "market_data_response":
            print("[MARKET_DATA_RESPONSE]", "rp_code=", event.get("rp_code"))

        elif event_type == "last_trade":
            flow = latest_snapshot["trade_flow"]
            print(
                "[TRADE]",
                event.get("symbol"),
                event.get("trade_price"),
                event.get("trade_size"),
                event.get("aggressor"),
                "rolling_delta=",
                flow["rolling_delta"],
                "session_cum_delta=",
                flow["session_cumulative_delta"],
                "rolling_poc=",
                latest_snapshot["volume_profile"]["rolling_poc_price"],
            )

        elif event_type == "best_bid_offer":
            print(
                "[BBO]",
                event.get("symbol"),
                "bid=",
                event.get("bid_price"),
                "ask=",
                event.get("ask_price"),
            )

        if latest_snapshot and (
            now - last_snapshot_write >= args.snapshot_interval_seconds
            or event_type in {"login_response", "market_data_response", "last_trade"}
        ):
            write_state_json(latest_snapshot, latest_json)
            write_state_text(latest_snapshot, latest_txt)
            last_snapshot_write = now

    if latest_snapshot:
        final_snapshot = cache.snapshot()
        write_state_json(final_snapshot, latest_json)
        write_state_text(final_snapshot, latest_txt)

        print("")
        print("[FINAL]")
        print("state_status =", final_snapshot["state_status"])
        print("rolling_trade_count =", final_snapshot["sample"]["rolling_trade_count"])
        print("rolling_delta =", final_snapshot["trade_flow"]["rolling_delta"])
        print("session_cumulative_delta =", final_snapshot["trade_flow"]["session_cumulative_delta"])
        print("rolling_poc_price =", final_snapshot["volume_profile"]["rolling_poc_price"])
        print("footprint_candle_count =", final_snapshot["footprint"]["candle_count"])
        print("adapter_metrics =", json.dumps(final_snapshot["adapter_compatible_metrics"], indent=2))
        print("latest_json =", latest_json)
        print("latest_txt =", latest_txt)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("")
        print("[STOPPED] Interrupted by user. Latest state snapshot was saved if data was received.")
