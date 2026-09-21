from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import MetaTrader5 as mt5


DATA_PATH = Path("data/fcr_m1_fvg_regime_shadow.jsonl")
HORIZON_MINUTES = 180
SETUP_WIN_USD = 10.0


def _load():
    if not DATA_PATH.exists():
        return []

    rows = []
    for line in DATA_PATH.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():
        if not line.strip():
            continue

        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if (
            item.get("strategy") == "FCR_M1_FVG"
            and item.get("execution_authority") is False
        ):
            rows.append(item)

    return rows


def _rates(symbol, start_epoch, end_epoch):
    start = datetime.fromtimestamp(
        int(start_epoch),
        tz=timezone.utc,
    )
    end = datetime.fromtimestamp(
        int(end_epoch),
        tz=timezone.utc,
    )

    rates = mt5.copy_rates_range(
        symbol,
        mt5.TIMEFRAME_M1,
        start,
        end,
    )

    return [] if rates is None else list(rates)


def _evaluate(item):
    signal = item["signal"]
    entry = float(item["entry"])
    sl = float(item["sl"])
    tp = float(item["tp"])
    observed = int(item["closed_m1_time_epoch"])
    end_epoch = observed + HORIZON_MINUTES * 60

    rates = [
        bar
        for bar in _rates(
            item["symbol"],
            observed,
            end_epoch + 60,
        )
        if int(bar["time"]) > observed
        and int(bar["time"]) <= end_epoch
    ]

    if not rates:
        return None

    max_favorable = 0.0
    max_adverse = 0.0
    hit_plus_10 = False
    hit_tp = False
    hit_sl = False
    first_tp_sl = None
    same_m1_ambiguous = False

    for bar in rates:
        high = float(bar["high"])
        low = float(bar["low"])

        if signal == "BUY":
            favorable = max(0.0, high - entry)
            adverse = max(0.0, entry - low)
            plus_10_now = high >= entry + SETUP_WIN_USD
            tp_now = high >= tp
            sl_now = low <= sl
        else:
            favorable = max(0.0, entry - low)
            adverse = max(0.0, high - entry)
            plus_10_now = low <= entry - SETUP_WIN_USD
            tp_now = low <= tp
            sl_now = high >= sl

        max_favorable = max(max_favorable, favorable)
        max_adverse = max(max_adverse, adverse)

        hit_plus_10 = hit_plus_10 or plus_10_now
        hit_tp = hit_tp or tp_now
        hit_sl = hit_sl or sl_now

        if first_tp_sl is None:
            if tp_now and sl_now:
                first_tp_sl = "TP_SL_SAME_M1_AMBIGUOUS"
                same_m1_ambiguous = True
            elif tp_now:
                first_tp_sl = "TP"
            elif sl_now:
                first_tp_sl = "SL"

    return {
        **item,
        "horizon_minutes": HORIZON_MINUTES,
        "bars_evaluated": len(rates),
        "hit_plus_10": hit_plus_10,
        "hit_tp": hit_tp,
        "hit_sl": hit_sl,
        "first_tp_sl": first_tp_sl,
        "same_m1_ambiguous": same_m1_ambiguous,
        "max_favorable_usd": round(max_favorable, 4),
        "max_adverse_usd": round(max_adverse, 4),
        "final_outcome": (
            "SETUP_WIN_PLUS_10"
            if hit_plus_10
            else "NO_PLUS_10_WITHIN_HORIZON"
        ),
    }


def _pct(num, den):
    return 0.0 if not den else round(100.0 * num / den, 2)


def _print_group(title, rows):
    n = len(rows)
    if not n:
        print(f"{title}: n=0")
        return

    wins = sum(row["hit_plus_10"] for row in rows)
    tps = sum(row["hit_tp"] for row in rows)
    sls = sum(row["hit_sl"] for row in rows)
    ambiguous = sum(row["same_m1_ambiguous"] for row in rows)

    print(
        f"{title}: "
        f"n={n} "
        f"setup_win_plus_10={wins}/{n} ({_pct(wins, n)}%) "
        f"tp={tps}/{n} ({_pct(tps, n)}%) "
        f"sl={sls}/{n} ({_pct(sls, n)}%) "
        f"same_m1_ambiguous={ambiguous}/{n} ({_pct(ambiguous, n)}%) "
        f"avg_mfe={round(mean(row['max_favorable_usd'] for row in rows), 2)} "
        f"avg_mae={round(mean(row['max_adverse_usd'] for row in rows), 2)}"
    )


def main():
    rows = _load()

    print("FCR_M1_FVG EXCLUDED-REGIME SHADOW EVALUATOR V1")
    print(
        f"source={DATA_PATH} observations={len(rows)} "
        f"horizon_minutes={HORIZON_MINUTES}"
    )
    print(
        "Setup Win = favorable +$10 price move, independent of TP/SL."
    )

    if not rows:
        print("No shadow observations yet.")
        return

    if not mt5.initialize():
        raise RuntimeError(
            f"MT5 initialize failed: {mt5.last_error()}"
        )

    try:
        tick = mt5.symbol_info_tick(rows[0]["symbol"])
        now_epoch = (
            int(tick.time)
            if tick is not None
            else int(datetime.now(timezone.utc).timestamp())
        )

        mature = [
            row
            for row in rows
            if now_epoch
            >= int(row["closed_m1_time_epoch"])
            + HORIZON_MINUTES * 60
        ]

        evaluated = []
        for row in mature:
            result = _evaluate(row)
            if result is not None:
                evaluated.append(result)

        print(
            f"mature={len(mature)} evaluated={len(evaluated)} "
            f"pending={len(rows) - len(mature)}"
        )

        _print_group(
            "ALL_EXCLUDED_REGIMES",
            evaluated,
        )

        grouped = defaultdict(list)
        for row in evaluated:
            grouped[
                (
                    row.get("market_condition", "UNKNOWN"),
                    row.get("signal", "UNKNOWN"),
                )
            ].append(row)

        for condition, signal in sorted(grouped):
            _print_group(
                f"{condition}|{signal}",
                grouped[(condition, signal)],
            )

        n = len(evaluated)
        if n < 20:
            readiness = "TOO_EARLY"
        elif n < 50:
            readiness = "EARLY_INDICATION_ONLY"
        else:
            readiness = "SAMPLE_SIZE_MEANINGFUL"

        print(f"readiness={readiness}")

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
