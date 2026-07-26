from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.order_flow_providers.rithmic_protocol import (
    RithmicConfig,
    RithmicMarketDataClient,
    load_rithmic_config,
)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _safe_symbol_for_file(symbol: str) -> str:
    return symbol.replace("/", "_").replace("\\", "_").replace(".", "_")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--exchange", default=None)
    parser.add_argument("--duration-seconds", type=int, default=60)
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
    output_jsonl = output_dir / f"{safe_symbol}_{_utc_stamp()}_phase5d_order_book_discovery.jsonl"
    output_summary = output_dir / f"{safe_symbol}_phase5d_order_book_discovery_summary.json"

    client = RithmicMarketDataClient(config)

    counts = defaultdict(int)
    template_counts = defaultdict(int)
    unhandled_template_counts = defaultdict(int)

    summary = {
        "phase": "PHASE_5D_RITHMIC_ORDER_BOOK_DISCOVERY",
        "source": "RITHMIC_R_PROTOCOL",
        "decision_impact": "NONE",
        "can_influence_decision": False,
        "symbol": config.symbol,
        "exchange": config.exchange,
        "duration_seconds": args.duration_seconds,
        "order_book_requested": True,
        "login_ok": False,
        "market_data_ok": False,
        "event_counts": {},
        "template_counts": {},
        "unhandled_template_counts": {},
        "output_jsonl": str(output_jsonl),
        "notes": [
            "This is discovery only.",
            "ORDER_BOOK subscription bit is requested.",
            "Unknown template IDs are recorded for parser mapping.",
            "No MT5 decision impact.",
        ],
    }

    print("[START] Phase 5D ORDER_BOOK discovery")
    print("symbol =", config.symbol)
    print("exchange =", config.exchange)
    print("duration_seconds =", args.duration_seconds)
    print("decision_impact = NONE")

    try:
        await client.connect()

        with output_jsonl.open("w", encoding="utf-8") as f:
            login_event = await client.login()
            counts[login_event.get("event_type", "unknown")] += 1
            template_counts[str(login_event.get("template_id"))] += 1
            summary["login_ok"] = bool(login_event.get("ok"))

            f.write(json.dumps(login_event, ensure_ascii=False) + "\n")
            f.flush()

            print("[LOGIN]", "ok=", login_event.get("ok"), "rp_code=", login_event.get("rp_code"))

            if not login_event.get("ok"):
                return

            await client.subscribe_market_data(include_order_book=True)
            await client.send_heartbeat()

            end_time = time.time() + args.duration_seconds

            while time.time() < end_time:
                try:
                    raw = await asyncio.wait_for(client.ws.recv(), timeout=5)
                    event = client.parse_message(raw)

                    event_type = event.get("event_type", "unknown")
                    template_id = str(event.get("template_id"))

                    counts[event_type] += 1
                    template_counts[template_id] += 1

                    if event_type == "unhandled":
                        unhandled_template_counts[template_id] += 1
                        print("[UNHANDLED]", "template_id=", template_id)

                    elif event_type == "market_data_response":
                        rp_code = event.get("rp_code") or []
                        summary["market_data_ok"] = bool(rp_code and rp_code[0] == "0")
                        print("[MARKET_DATA_RESPONSE]", "rp_code=", rp_code)

                    elif event_type == "last_trade":
                        print(
                            "[TRADE]",
                            event.get("symbol"),
                            event.get("trade_price"),
                            event.get("trade_size"),
                            event.get("aggressor"),
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

                    elif event_type == "order_book":
                        print(
                            "[ORDER_BOOK]",
                            event.get("symbol"),
                            "update_type=",
                            event.get("update_type_name"),
                            "bid_levels=",
                            event.get("bid_level_count"),
                            "ask_levels=",
                            event.get("ask_level_count"),
                            "bid_depth=",
                            event.get("bid_depth"),
                            "ask_depth=",
                            event.get("ask_depth"),
                            "imbalance=",
                            event.get("depth_imbalance"),
                        )

                    elif event_type == "heartbeat_response":
                        pass

                    else:
                        print("[EVENT]", event_type, "template_id=", template_id)

                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
                    f.flush()

                except asyncio.TimeoutError:
                    await client.send_heartbeat()

    finally:
        try:
            await client.logout()
        except Exception:
            pass

        summary["event_counts"] = dict(counts)
        summary["template_counts"] = dict(template_counts)
        summary["unhandled_template_counts"] = dict(unhandled_template_counts)

        output_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

        print("")
        print("[SUMMARY]")
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("")
        print("[STOPPED] Interrupted by user.")
