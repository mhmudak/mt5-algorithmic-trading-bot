def detect_session(current_time):
    hour = current_time.hour

    if 0 <= hour < 7:
        return "ASIA"
    elif 7 <= hour < 13:
        return "LONDON"
    elif 13 <= hour < 21:
        return "NEWYORK"
    return "OFF_HOURS"


def session_score_adjustment(strategy_name: str, session_name: str):
    score_boost = 0
    reasons = []

    # London / NY = strongest momentum sessions
    if strategy_name in ["ORB", "TRIANGLE_PENNANT", "FLAG", "FLAG_REFINED", "SNIPER_V2", "STRICT"]:
        if session_name in ["LONDON", "NEWYORK"]:
            score_boost += 2
            reasons.append(f"{session_name.lower()}_momentum_session")
        elif session_name == "OFF_HOURS":
            score_boost -= 3
            reasons.append("off_hours_penalty")

    # reversal / trap logic works well in volatility sessions too
    if strategy_name in ["LIQUIDITY_SWEEP", "LIQUIDITY_TRAP", "CRT_TBS", "SMT", "SMT_PRO"]:
        if session_name in ["LONDON", "NEWYORK"]:
            score_boost += 2
            reasons.append(f"{session_name.lower()}_reversal_session")
        elif session_name == "ASIA":
            score_boost -= 1
            reasons.append("asia_reversal_penalty")

    # structural strategies can work broadly, but still prefer active sessions
    if strategy_name in ["FVG", "ORDER_BLOCK", "OB_FVG_COMBO", "RELIEF_RALLY"]:
        if session_name in ["LONDON", "NEWYORK"]:
            score_boost += 1
            reasons.append(f"{session_name.lower()}_structure_support")
        elif session_name == "OFF_HOURS":
            score_boost -= 2
            reasons.append("off_hours_structure_penalty")

    # pivot scalping session bias
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