from src.strategy_performance import load_performance, get_strategy_winrate
from src.logger import logger
from config.settings import (
    ENABLE_ADAPTIVE_THRESHOLDS,
    ENABLE_MARKET_ADAPTATION,
    MARKET_THRESHOLD_MODIFIERS,
    ADAPTIVE_MIN_TRADES,
    ADAPTIVE_WINRATE_HIGH,
    ADAPTIVE_WINRATE_LOW,
    ADAPTIVE_SCORE_STEP,
    FAST_BASE_MIN_SCORE,
    SNIPER_V2_BASE_MIN_SCORE,
    STRICT_BASE_MIN_SCORE,
    FLAG_BASE_MIN_SCORE,
    FLAG_REFINED_BASE_MIN_SCORE,
    LIQUIDITY_SWEEP_BASE_MIN_SCORE,
    HEAD_SHOULDERS_BASE_MIN_SCORE,
    TRIANGLE_PENNANT_BASE_MIN_SCORE,
    FVG_BASE_MIN_SCORE,
    ORDER_BLOCK_BASE_MIN_SCORE,
    LIQUIDITY_CANDLE_BASE_MIN_SCORE,
    ORB_BASE_MIN_SCORE,
    FRACTAL_SWEEP_BASE_MIN_SCORE,
    SMT_BASE_MIN_SCORE,
    SMT_PRO_BASE_MIN_SCORE,
    CRT_TBS_BASE_MIN_SCORE,
    OB_FVG_COMBO_BASE_MIN_SCORE,
    LIQUIDITY_TRAP_BASE_MIN_SCORE,
    RELIEF_RALLY_BASE_MIN_SCORE,
    HTF_TREND_PULLBACK_BASE_MIN_SCORE,
    SESSION_ORB_RETEST_BASE_MIN_SCORE,
)

BASE_THRESHOLDS = {
    "FAST": FAST_BASE_MIN_SCORE,
    "SNIPER_V2": SNIPER_V2_BASE_MIN_SCORE,
    "STRICT": STRICT_BASE_MIN_SCORE,
    "FLAG": FLAG_BASE_MIN_SCORE,
    "FLAG_REFINED": FLAG_REFINED_BASE_MIN_SCORE,
    "LIQUIDITY_SWEEP": LIQUIDITY_SWEEP_BASE_MIN_SCORE,
    "HEAD_SHOULDERS": HEAD_SHOULDERS_BASE_MIN_SCORE,
    "TRIANGLE_PENNANT": TRIANGLE_PENNANT_BASE_MIN_SCORE,
    "FVG": FVG_BASE_MIN_SCORE,
    "ORDER_BLOCK": ORDER_BLOCK_BASE_MIN_SCORE,
    "LIQUIDITY_CANDLE": LIQUIDITY_CANDLE_BASE_MIN_SCORE,
    "ORB": ORB_BASE_MIN_SCORE,
    "FRACTAL_SWEEP": FRACTAL_SWEEP_BASE_MIN_SCORE,
    "SMT": SMT_BASE_MIN_SCORE,
    "SMT_PRO": SMT_PRO_BASE_MIN_SCORE,
    "CRT_TBS": CRT_TBS_BASE_MIN_SCORE,
    "OB_FVG_COMBO": OB_FVG_COMBO_BASE_MIN_SCORE,
    "LIQUIDITY_TRAP": LIQUIDITY_TRAP_BASE_MIN_SCORE,
    "RELIEF_RALLY": RELIEF_RALLY_BASE_MIN_SCORE,
    "HTF_TREND_PULLBACK": HTF_TREND_PULLBACK_BASE_MIN_SCORE,
    "SESSION_ORB_RETEST": SESSION_ORB_RETEST_BASE_MIN_SCORE,
}


def get_adaptive_min_score(strategy_name: str, market_condition: str) -> int:
    base = BASE_THRESHOLDS.get(strategy_name, 0)

    final_score = base

    # =========================
    # 1) Performance Adaptation
    # =========================
    if ENABLE_ADAPTIVE_THRESHOLDS:
        performance = load_performance()
        strategy_data = performance.get(strategy_name)

        if strategy_data:
            total_trades = strategy_data.get("total_trades", 0)

            if total_trades >= ADAPTIVE_MIN_TRADES:
                winrate = get_strategy_winrate(strategy_name, performance)

                if winrate >= ADAPTIVE_WINRATE_HIGH:
                    final_score -= ADAPTIVE_SCORE_STEP
                    logger.info(
                        f"[ADAPTIVE] {strategy_name} strong -> {winrate}%"
                    )

                elif winrate <= ADAPTIVE_WINRATE_LOW:
                    final_score += ADAPTIVE_SCORE_STEP
                    logger.info(
                        f"[ADAPTIVE] {strategy_name} weak -> {winrate}%"
                    )

    # =========================
    # 2) Market Adaptation
    # =========================
    if ENABLE_MARKET_ADAPTATION:
        modifier = MARKET_THRESHOLD_MODIFIERS.get(market_condition, 0)
        final_score += modifier

        logger.info(
            f"[MARKET ADAPT] {strategy_name} | {market_condition} "
            f"modifier={modifier}"
        )

    return max(0, final_score)