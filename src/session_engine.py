from config.settings import (
    ENABLE_SESSION_STRATEGY_BLOCKS,
    ENABLE_SESSION_STRATEGY_BOOSTS,
    SESSION_STRATEGY_BLOCKS,
    SESSION_STRATEGY_BOOSTS,
    SESSION_STRATEGY_BOOST_VALUE,
    SESSION_WINDOWS_BROKER_TIME,
    SESSION_FAMILY_MAP,
)


def _time_to_minutes(value):
    if isinstance(value, str):
        hour, minute = value.split(":")[:2]
        return int(hour) * 60 + int(minute)

    return int(value)


def _current_time_to_minutes(current_time):
    return int(current_time.hour) * 60 + int(current_time.minute)


def _is_time_inside_window(current_minutes, start_minutes, end_minutes):
    # Normal same-day window, e.g. 10:00 -> 15:00
    if start_minutes < end_minutes:
        return start_minutes <= current_minutes < end_minutes

    # Overnight window, e.g. 23:00 -> 00:00
    if start_minutes > end_minutes:
        return current_minutes >= start_minutes or current_minutes < end_minutes

    return False


def detect_session(current_time):
    current_minutes = _current_time_to_minutes(current_time)

    for session_name, window in SESSION_WINDOWS_BROKER_TIME.items():
        start_minutes = _time_to_minutes(window["start"])
        end_minutes = _time_to_minutes(window["end"])

        if _is_time_inside_window(current_minutes, start_minutes, end_minutes):
            return session_name

    return "OFF_HOURS"


def get_session_family(session_name):
    session_key = str(session_name or "").upper()
    return SESSION_FAMILY_MAP.get(session_key, session_key)


def get_session_key_candidates(session_name):
    session_key = str(session_name or "").upper()
    family_key = get_session_family(session_key)

    keys = [session_key]

    if family_key and family_key not in keys:
        keys.append(family_key)

    return keys


def session_score_adjustment(strategy_name: str, session_name: str):
    score_boost = 0
    reasons = []

    session_key = str(session_name or "").upper()
    session_family = get_session_family(session_key)

    strategy_name = str(strategy_name or "").upper()

    # =========================
    # Momentum / breakout strategies
    # Best during London and New York
    # =========================
    momentum_strategies = {
        "ORB",
        "ORB_V00",
        "SESSION_ORB_RETEST",
        "FCR_M1_FVG",
        "TRIANGLE_PENNANT",
        "FLAG",
        "FLAG_REFINED",
        "SNIPER_V2",
        "STRICT",
        "FAST",
        "WAVETREND_MOMENTUM",
    }

    if strategy_name in momentum_strategies:
        if session_family in ["LONDON", "NEWYORK"]:
            score_boost += 2
            reasons.append(f"{session_key.lower()}_momentum_session")
        elif session_family == "ASIA":
            score_boost -= 1
            reasons.append("asia_momentum_penalty")
        elif session_family == "OFF_HOURS":
            score_boost -= 3
            reasons.append("off_hours_momentum_penalty")

    # =========================
    # Reversal / liquidity-trap strategies
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
        "FAILED_BREAKOUT_REVERSAL",
        "FAILED_FVG_REVERSAL",
        "EXTREME_SWEEP_RECLAIM",
        "IFVG_RETEST_CONFLUENCE",
    }

    if strategy_name in reversal_strategies:
        if session_family in ["LONDON", "NEWYORK"]:
            score_boost += 2
            reasons.append(f"{session_key.lower()}_reversal_session")
        elif session_family == "ASIA":
            score_boost -= 1
            reasons.append("asia_reversal_penalty")
        elif session_family == "OFF_HOURS":
            score_boost -= 3
            reasons.append("off_hours_reversal_penalty")

    # =========================
    # Structural / smart-money strategies
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
        "HTF_FIB_CONFLUENCE",
        "SUPPLY_DEMAND_RETEST",
        "MTF_SR_FVG_RECLAIM",
        "IFVG_RETEST_CONFLUENCE",
    }

    if strategy_name in structural_strategies:
        if session_family in ["LONDON", "NEWYORK"]:
            score_boost += 1
            reasons.append(f"{session_key.lower()}_structure_support")
        elif session_family == "OFF_HOURS":
            score_boost -= 2
            reasons.append("off_hours_structure_penalty")

    if strategy_name == "WAVETREND_PIVOT":
        if session_family in ["LONDON", "NEWYORK"]:
            score_boost += 2
            reasons.append(f"{session_key.lower()}_pivot_scalping_session")
        elif session_family == "ASIA":
            score_boost -= 2
            reasons.append("asia_pivot_penalty")
        elif session_family == "OFF_HOURS":
            score_boost -= 4
            reasons.append("off_hours_pivot_penalty")

    # =========================
    # Empirical suitable-session boost
    # Check detailed session first, then family session.
    # =========================
    if ENABLE_SESSION_STRATEGY_BOOSTS:
        for key in get_session_key_candidates(session_key):
            boosted = SESSION_STRATEGY_BOOSTS.get(key, [])

            if strategy_name in boosted:
                score_boost += SESSION_STRATEGY_BOOST_VALUE
                reasons.append(f"empirical_session_boost_{key}")
                break

    return score_boost, reasons


def session_blocks_strategy(strategy_name: str, session_name: str):
    if not ENABLE_SESSION_STRATEGY_BLOCKS:
        return False, None

    strategy_key = str(strategy_name or "").upper()
    session_key = str(session_name or "").upper()

    # Check detailed session first, then family session.
    for key in get_session_key_candidates(session_key):
        blocked = SESSION_STRATEGY_BLOCKS.get(key, [])

        if strategy_key in blocked:
            return True, f"session_blocked strategy={strategy_key} session={session_key} matched_key={key}"

    return False, None