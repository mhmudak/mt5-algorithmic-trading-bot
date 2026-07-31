from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.strategies.strategy_volatility_compression_breakout import (  # noqa: E402
    STRATEGY_NAME,
    VolatilityCompressionBreakoutConfig,
    evaluate_volatility_compression_breakout,
)


STATE_DIR = ROOT / "data" / "strategy_intelligence" / "phase6a_volatility_compression_breakout"
STATE_PATH = STATE_DIR / "phase6a_live_state.json"
SIGNALS_JSONL = STATE_DIR / "phase6a_signals.jsonl"

MAGIC = 606010
COMMENT = "PHASE6A_VCB_DEMO"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}

    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def append_signal(signal: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with SIGNALS_JSONL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(signal, ensure_ascii=False) + "\n")


def send_telegram_message(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TG_CHAT_ID")

    if not token or not chat_id:
        print("[TELEGRAM] skipped: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID missing")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")

    try:
        with urllib.request.urlopen(url, data=payload, timeout=10) as response:
            return 200 <= response.status < 300
    except Exception as exc:
        print(f"[TELEGRAM] failed: {exc}")
        return False


def mt5_timeframe(mt5: Any, name: str) -> int:
    normalized = name.upper()

    mapping = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
    }

    if normalized not in mapping:
        raise ValueError(f"Unsupported timeframe: {name}")

    return mapping[normalized]


def rates_to_candles(rates: Any) -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []

    for item in rates:
        ts = int(item["time"])
        candles.append(
            {
                "time": datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"),
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "tick_volume": int(item["tick_volume"]),
            }
        )

    return candles


def has_existing_position(mt5: Any, symbol: str) -> bool:
    positions = mt5.positions_get(symbol=symbol)

    if positions is None:
        return False

    return len(positions) > 0


def get_spread_points(mt5: Any, symbol: str) -> float | None:
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)

    if tick is None or info is None:
        return None

    point = float(info.point or 0.0)

    if point <= 0:
        return None

    return abs(float(tick.ask) - float(tick.bid)) / point


def build_signal_key(signal: dict[str, Any]) -> str:
    return "|".join(
        [
            str(signal.get("strategy")),
            str(signal.get("symbol")),
            str(signal.get("signal")),
            str(signal.get("time")),
            str(signal.get("compression_high")),
            str(signal.get("compression_low")),
            str(signal.get("entry")),
        ]
    )


def format_message(signal: dict[str, Any], *, execute: bool, execution_result: dict[str, Any] | None = None) -> str:
    lines = [
        "🚀 PHASE 6A VOLATILITY COMPRESSION BREAKOUT",
        f"Mode: {'DEMO EXECUTION' if execute else 'TELEGRAM ONLY'}",
        f"Strategy: {signal.get('strategy')}",
        f"Symbol: {signal.get('symbol')}",
        f"Signal: {signal.get('signal')}",
        "",
        f"Entry: {signal.get('entry')}",
        f"SL: {signal.get('sl')}",
        f"TP: {signal.get('tp')}",
        f"RR: {signal.get('rr')}",
        "",
        f"Compression High: {signal.get('compression_high')}",
        f"Compression Low: {signal.get('compression_low')}",
        f"ATR: {signal.get('atr')}",
        f"Compression/ATR: {signal.get('compression_atr_ratio')}",
        f"Breakout Body/ATR: {signal.get('breakout_body_atr_ratio')}",
        "",
        "Risk Rules:",
        "- One position only",
        "- No averaging",
        "- No martingale",
        "- Defined SL",
        "",
        f"Execution requested: {execute}",
    ]

    if execution_result is not None:
        lines.extend(
            [
                "",
                "Execution Result:",
                f"- sent: {execution_result.get('sent')}",
                f"- retcode: {execution_result.get('retcode')}",
                f"- comment: {execution_result.get('comment')}",
                f"- order: {execution_result.get('order')}",
                f"- deal: {execution_result.get('deal')}",
            ]
        )

    return "\n".join(lines)


def execute_demo_order(
    mt5: Any,
    signal: dict[str, Any],
    *,
    lot: float,
    max_spread_points: float,
    deviation: int,
) -> dict[str, Any]:
    symbol = str(signal["symbol"])
    direction = str(signal["signal"]).upper()

    if has_existing_position(mt5, symbol):
        return {
            "sent": False,
            "reason": "existing_position_on_symbol",
        }

    spread = get_spread_points(mt5, symbol)

    if spread is None:
        return {
            "sent": False,
            "reason": "spread_unavailable",
        }

    if spread > max_spread_points:
        return {
            "sent": False,
            "reason": f"spread_too_high {spread:.1f}>{max_spread_points}",
        }

    info = mt5.symbol_info(symbol)

    if info is None:
        return {
            "sent": False,
            "reason": "symbol_info_unavailable",
        }

    if not info.visible:
        mt5.symbol_select(symbol, True)

    tick = mt5.symbol_info_tick(symbol)

    if tick is None:
        return {
            "sent": False,
            "reason": "tick_unavailable",
        }

    if direction == "BUY":
        order_type = mt5.ORDER_TYPE_BUY
        price = float(tick.ask)
    elif direction == "SELL":
        order_type = mt5.ORDER_TYPE_SELL
        price = float(tick.bid)
    else:
        return {
            "sent": False,
            "reason": f"invalid_direction {direction}",
        }

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot),
        "type": order_type,
        "price": price,
        "sl": float(signal["sl"]),
        "tp": float(signal["tp"]),
        "deviation": int(deviation),
        "magic": MAGIC,
        "comment": COMMENT,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result is None:
        return {
            "sent": False,
            "reason": "order_send_returned_none",
        }

    return {
        "sent": True,
        "retcode": getattr(result, "retcode", None),
        "comment": getattr(result, "comment", ""),
        "order": getattr(result, "order", None),
        "deal": getattr(result, "deal", None),
        "price": price,
        "spread_points": spread,
        "request": request,
    }


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    import MetaTrader5 as mt5

    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    try:
        timeframe = mt5_timeframe(mt5, args.timeframe)
        candles_needed = args.atr_candles + args.compression_candles + 10

        rates = mt5.copy_rates_from_pos(args.symbol, timeframe, 0, candles_needed)

        if rates is None or len(rates) < candles_needed - 5:
            return {
                "valid": False,
                "reason": "not_enough_mt5_rates",
            }

        candles = rates_to_candles(rates)

        cfg = VolatilityCompressionBreakoutConfig(
            compression_candles=args.compression_candles,
            atr_candles=args.atr_candles,
            max_compression_atr_ratio=args.max_compression_atr_ratio,
            max_avg_body_atr_ratio=args.max_avg_body_atr_ratio,
            min_breakout_body_atr_ratio=args.min_breakout_body_atr_ratio,
            min_close_beyond_range=args.min_close_beyond_range,
            max_breakout_chase_atr_ratio=args.max_breakout_chase_atr_ratio,
            min_rr=args.min_rr,
            target_rr=args.target_rr,
            sl_buffer=args.sl_buffer,
            max_sl_distance=args.max_sl_distance,
        )

        signal = evaluate_volatility_compression_breakout(
            candles,
            symbol=args.symbol,
            config=cfg,
        )

        signal["checked_at"] = datetime.now().isoformat(timespec="seconds")
        signal["timeframe"] = args.timeframe
        signal["mode"] = "DEMO_EXECUTION" if args.execute else "TELEGRAM_ONLY"
        signal["live_runner"] = True

        print(json.dumps(signal, indent=2))
        append_signal(signal)

        if not signal.get("valid"):
            return signal

        state = load_state()
        signal_key = build_signal_key(signal)

        if state.get("last_signal_key") == signal_key:
            print("[SKIP] duplicate signal key")
            signal["duplicate_skipped"] = True
            return signal

        execution_result = None

        if args.execute:
            execution_result = execute_demo_order(
                mt5,
                signal,
                lot=args.lot,
                max_spread_points=args.max_spread_points,
                deviation=args.deviation,
            )

            signal["execution_result"] = execution_result

        message = format_message(signal, execute=args.execute, execution_result=execution_result)
        send_telegram_message(message)

        state["last_signal_key"] = signal_key
        state["last_signal_at"] = signal["checked_at"]
        state["last_signal"] = signal
        save_state(state)

        return signal

    finally:
        mt5.shutdown()


def main() -> None:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="M5")
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--lot", type=float, default=0.01)
    parser.add_argument("--max-spread-points", type=float, default=80)
    parser.add_argument("--deviation", type=int, default=30)
    parser.add_argument("--compression-candles", type=int, default=8)
    parser.add_argument("--atr-candles", type=int, default=30)
    parser.add_argument("--max-compression-atr-ratio", type=float, default=0.55)
    parser.add_argument("--max-avg-body-atr-ratio", type=float, default=0.28)
    parser.add_argument("--min-breakout-body-atr-ratio", type=float, default=0.45)
    parser.add_argument("--min-close-beyond-range", type=float, default=0.20)
    parser.add_argument("--max-breakout-chase-atr-ratio", type=float, default=1.80)
    parser.add_argument("--min-rr", type=float, default=2.0)
    parser.add_argument("--target-rr", type=float, default=2.2)
    parser.add_argument("--sl-buffer", type=float, default=0.35)
    parser.add_argument("--max-sl-distance", type=float, default=7.0)

    args = parser.parse_args()

    print("[PHASE 6A VOLATILITY COMPRESSION BREAKOUT LIVE RUNNER]")
    print(f"symbol = {args.symbol}")
    print(f"timeframe = {args.timeframe}")
    print(f"execute = {args.execute}")
    print(f"lot = {args.lot}")
    print(f"interval_seconds = {args.interval_seconds}")
    print(f"duration_seconds = {args.duration_seconds}")
    print("safety = one-position-only, duplicate-guard, defined SL/TP")
    print("")

    start = time.time()

    while True:
        try:
            run_once(args)
        except Exception as exc:
            print(f"[ERROR] {exc}")

        if args.duration_seconds <= 0:
            break

        if time.time() - start >= args.duration_seconds:
            break

        time.sleep(max(1, args.interval_seconds))


if __name__ == "__main__":
    main()
