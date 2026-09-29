from __future__ import annotations

from src.intrabar_step_trail_detector import (
    DEFAULT_POLICY,
    detect_step_trail_pattern,
)


def samples(prices, spread=0.10, dt=0.25, start_ts=1000.0):
    return [
        {
            "ts": start_ts + i * dt,
            "bid": mid - spread / 2.0,
            "ask": mid + spread / 2.0,
            "mid": mid,
            "spread": spread,
        }
        for i, mid in enumerate(prices)
    ]


def main():
    print("[INTRABAR STEP TRAIL DETECTOR TEST V1]")

    buy_prices = [
        4250.00, 4250.10, 4250.25, 4250.45, 4250.70, 4250.68,
        4250.50, 4250.42, 4250.50, 4250.60, 4250.66, 4250.69,
    ]
    buy = detect_step_trail_pattern(samples(buy_prices))
    assert buy is not None and buy["signal"] == "BUY"
    assert buy["impulse"] >= DEFAULT_POLICY.min_impulse
    assert buy["pullback"] >= DEFAULT_POLICY.min_pullback
    assert buy["resume"] >= DEFAULT_POLICY.min_resume

    sell_prices = [
        4250.00, 4249.90, 4249.75, 4249.55, 4249.30, 4249.32,
        4249.50, 4249.58, 4249.50, 4249.40, 4249.34, 4249.31,
    ]
    sell = detect_step_trail_pattern(samples(sell_prices, start_ts=2000.0))
    assert sell is not None and sell["signal"] == "SELL"

    monotonic = [
        4250.00, 4250.08, 4250.16, 4250.24, 4250.32, 4250.40,
        4250.48, 4250.56, 4250.64, 4250.72, 4250.80, 4250.88,
    ]
    assert detect_step_trail_pattern(
        samples(monotonic, start_ts=3000.0)
    ) is None

    assert detect_step_trail_pattern(
        samples(buy_prices, spread=0.25, start_ts=4000.0)
    ) is None

    print("buy_pattern_detected=True")
    print("sell_pattern_detected=True")
    print("pure_momentum_rejected=True")
    print("wide_spread_rejected=True")
    print(
        "PASS: entry is impulse -> controlled pullback -> resume, "
        "distinct from Micro Momentum."
    )


if __name__ == "__main__":
    main()
