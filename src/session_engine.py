def detect_session(current_time):
    hour = current_time.hour

    if 0 <= hour < 7:
        return "ASIA"

    if 7 <= hour < 13:
        return "LONDON"

    if 13 <= hour < 21:
        return "NEWYORK"

    return "OFF_HOURS"


def session_score_adjustment(strategy_name: str, session_name: str):
    score_boost = 0
    reasons = []

    # =========================
    # Momentum / breakout strategies
    # Best during London and New York
    # =========================
    momentum_strategies = {
        "ORB",
        "SESSION_ORB_RETEST",
        "FCR_M1_FVG",
        "TRIANGLE_PENNANT",
        "FLAG",
        "FLAG_REFINED",
        "SNIPER_V2",
        "STRICT",
        "FAST",
    }

    if strategy_name in momentum_strategies:
        if session_name in ["LONDON", "NEWYORK"]:
            score_boost += 2
            reasons.append(f"{session_name.lower()}_momentum_session")
        elif session_name == "ASIA":
            score_boost -= 1
            reasons.append("asia_momentum_penalty")
        elif session_name == "OFF_HOURS":
            score_boost -= 3
            reasons.append("off_hours_momentum_penalty")

    # =========================
    # Reversal / liquidity-trap strategies
    # Can work well during active liquidity sessions
    # =========================
    reversal_strategies = {
        "LIQUIDITY_SWEEP",
        "LIQUIDITY_TRAP",
        "CRT_TBS",
        "FRACTAL_SWEEP",
        "SMT",
        "SMT_PRO",
        "LIQUIDITY_CANDLE",
        "VWAP_RECLAIM",
        "STRUCTURE_LIQUIDITY",
        "AMD_FVG",
        "LIQUIDITY_POOL_OB",
    }

    if strategy_name in reversal_strategies:
        if session_name in ["LONDON", "NEWYORK"]:
            score_boost += 2
            reasons.append(f"{session_name.lower()}_reversal_session")
        elif session_name == "ASIA":
            score_boost -= 1
            reasons.append("asia_reversal_penalty")
        elif session_name == "OFF_HOURS":
            score_boost -= 3
            reasons.append("off_hours_reversal_penalty")

    # =========================
    # Structural / smart-money strategies
    # Can work broadly, but active sessions are preferred
    # =========================
    structural_strategies = {
        "FVG",
        "ORDER_BLOCK",
        "OB_FVG_COMBO",
        "BREAKER_BLOCK",
        "RELIEF_RALLY",
        "HTF_TREND_PULLBACK",
        "MTF_OB_ENTRY",
        "HEAD_SHOULDERS",
        "LVN_FVG_RECLAIM",
        "FVG_CE_MITIGATION",
    }

    if strategy_name in structural_strategies:
        if session_name in ["LONDON", "NEWYORK"]:
            score_boost += 1
            reasons.append(f"{session_name.lower()}_structure_support")
        elif session_name == "OFF_HOURS":
            score_boost -= 2
            reasons.append("off_hours_structure_penalty")

    # =========================
    # M5 WaveTrend Pivot scalping
    # Best during London / New York
    # Penalize Asia and off-hours because pivot scalping can get choppy
    # =========================
    if strategy_name == "WAVETREND_PIVOT":
        if session_name in ["LONDON", "NEWYORK"]:
            score_boost += 2
            reasons.append(f"{session_name.lower()}_pivot_scalping_session")
        elif session_name == "ASIA":
            score_boost -= 2
            reasons.append("asia_pivot_penalty")
        elif session_name == "OFF_HOURS":
            score_boost -= 4
            reasons.append("off_hours_pivot_penalty")

    return score_boost, reasons