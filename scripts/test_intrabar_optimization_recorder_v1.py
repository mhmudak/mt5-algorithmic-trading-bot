from src.intrabar_optimization_recorder import build_candidate_context, build_excursion_snapshot


def main():
    print("[INTRABAR OPTIMIZATION RECORDER TEST V1]")
    buy = build_excursion_snapshot(signal="BUY", entry_price=4250.0, current_price=4251.25)
    sell = build_excursion_snapshot(signal="SELL", entry_price=4250.0, current_price=4251.25)
    assert buy["favorable"] == 1.25 and buy["adverse"] == 0.0
    assert sell["favorable"] == 0.0 and sell["adverse"] == 1.25

    micro = build_candidate_context({
        "setup_id": "IMM-BUY-1",
        "strategy": "INTRABAR_MICRO_MOMENTUM",
        "signal": "BUY",
        "entry_model": "TICK_VELOCITY_ACCELERATION_PERSISTENCE",
        "score": 91,
        "session": "NEW_YORK",
        "market_condition": "TRENDING",
        "entry": 4250.0,
        "extra": {
            "strength": "EXPLOSIVE",
            "sample_count": 9,
            "span_seconds": 3.2,
            "velocity_price_per_sec": 0.24,
            "persistence": 0.88,
            "acceleration_ratio": 1.35,
            "spread": 0.12,
        },
    })
    assert micro and micro["live_authority"] is False
    assert micro["detector_features"]["strength"] == "EXPLOSIVE"

    step = build_candidate_context({
        "setup_id": "IST-BUY-1",
        "strategy": "INTRABAR_STEP_TRAIL",
        "signal": "BUY",
        "entry_model": "INTRABAR_IMPULSE_PULLBACK_RESUME",
        "impulse": 0.80,
        "pullback": 0.24,
        "resume": 0.34,
        "quality": 1.08,
        "span_seconds": 3.1,
        "sample_count": 12,
        "spread": 0.11,
        "entry_reference": 4250.50,
    })
    assert step
    assert step["detector_features"]["pullback_to_impulse"] == 0.30
    assert step["detector_features"]["resume_to_impulse"] == 0.425

    print("buy_sell_excursion_math=True")
    print("micro_features=True")
    print("step_features=True")
    print("live_authority=False")
    print("PASS")


if __name__ == "__main__":
    main()
