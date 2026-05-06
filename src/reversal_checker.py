from config.settings import ATR_MIN, ATR_MAX


REVERSAL_LOOKBACK = 12

MIN_BODY_ATR_RATIO = 0.25
MIN_WICK_BODY_RATIO = 1.0

SL_ATR_BUFFER = 0.20
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 5.0

REVERSAL_TARGET_RR = 1.5


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _score_reversal(base_score, body, atr, sweep_confirmed, structure_shift, rejection_quality):
    score = base_score

    if body > atr * 0.35:
        score += 2

    if body > atr * 0.50:
        score += 2

    if sweep_confirmed:
        score += 3

    if structure_shift:
        score += 3

    if rejection_quality:
        score += 2

    return min(score, 99)


def build_blocked_setup_reversal(df, blocked_signal, blocked_strategy, blocked_trade_plan, blocked_signal_data):
    """
    Strict reversal check after a confirmed setup is blocked by low RR.

    It does not reverse automatically.
    It only returns an opposite signal if there is:
    - liquidity sweep
    - rejection candle
    - structure shift
    - valid SL/TP
    """

    if blocked_signal not in ["BUY", "SELL"]:
        return None

    if blocked_trade_plan is None:
        return None

    if len(df) < REVERSAL_LOOKBACK + 5:
        return None

    entry = df.iloc[-2]      # last closed candle
    prev = df.iloc[-3]

    atr = entry["atr_14"]
    ema = entry["ema_20"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body = abs(entry["close"] - entry["open"])
    candle_range = entry["high"] - entry["low"]

    if candle_range <= 0:
        return None

    if body < atr * MIN_BODY_ATR_RATIO:
        return None

    recent = df.iloc[-(REVERSAL_LOOKBACK + 2):-2]
    recent_high = recent["high"].max()
    recent_low = recent["low"].min()

    upper_wick = entry["high"] - max(entry["open"], entry["close"])
    lower_wick = min(entry["open"], entry["close"]) - entry["low"]

    sl_buffer = _sl_buffer(atr)

    # =========================================================
    # Blocked BUY -> check strict SELL reversal
    # =========================================================
    if blocked_signal == "BUY":
        buy_side_sweep = entry["high"] > recent_high

        bearish_rejection = (
            entry["close"] < entry["open"]
            and entry["close"] < recent_high
            and upper_wick > body * MIN_WICK_BODY_RATIO
        )

        bearish_structure_shift = (
            entry["close"] < prev["low"]
            or entry["close"] < ema
        )

        if buy_side_sweep and bearish_rejection and bearish_structure_shift:
            signal = "SELL"

            sl_reference = round(max(entry["high"], recent_high) + sl_buffer, 2)
            entry_price = entry["close"]
            stop_distance = sl_reference - entry_price
            tp_reference = round(entry_price - (stop_distance * REVERSAL_TARGET_RR), 2)

            if sl_reference <= entry_price or tp_reference >= entry_price:
                return None

            score = _score_reversal(
                base_score=94,
                body=body,
                atr=atr,
                sweep_confirmed=buy_side_sweep,
                structure_shift=bearish_structure_shift,
                rejection_quality=upper_wick > body * 1.5,
            )

            return {
                "signal": signal,
                "score": score,
                "strategy": "BLOCKED_SETUP_REVERSAL",
                "entry_model": "FAILED_BUY_REVERSAL",
                "blocked_strategy": blocked_strategy,
                "blocked_signal": blocked_signal,
                "pattern_height": abs(entry_price - tp_reference),
                "sweep_level": entry["high"],
                "recent_high": recent_high,
                "recent_low": recent_low,
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": "REVERSAL_1_5R_TARGET",
                "momentum": "bearish_reversal_after_failed_buy",
                "direction_context": "buy_setup_failed_bearish_sweep_reversal",
                "reason": (
                    f"Blocked BUY reversal -> original {blocked_strategy} BUY blocked by low RR -> "
                    f"buy-side sweep above {round(recent_high, 2)} -> "
                    f"bearish rejection + structure shift -> "
                    f"SL {sl_reference} -> TP {tp_reference}"
                ),
            }

    # =========================================================
    # Blocked SELL -> check strict BUY reversal
    # =========================================================
    if blocked_signal == "SELL":
        sell_side_sweep = entry["low"] < recent_low

        bullish_rejection = (
            entry["close"] > entry["open"]
            and entry["close"] > recent_low
            and lower_wick > body * MIN_WICK_BODY_RATIO
        )

        bullish_structure_shift = (
            entry["close"] > prev["high"]
            or entry["close"] > ema
        )

        if sell_side_sweep and bullish_rejection and bullish_structure_shift:
            signal = "BUY"

            sl_reference = round(min(entry["low"], recent_low) - sl_buffer, 2)
            entry_price = entry["close"]
            stop_distance = entry_price - sl_reference
            tp_reference = round(entry_price + (stop_distance * REVERSAL_TARGET_RR), 2)

            if sl_reference >= entry_price or tp_reference <= entry_price:
                return None

            score = _score_reversal(
                base_score=94,
                body=body,
                atr=atr,
                sweep_confirmed=sell_side_sweep,
                structure_shift=bullish_structure_shift,
                rejection_quality=lower_wick > body * 1.5,
            )

            return {
                "signal": signal,
                "score": score,
                "strategy": "BLOCKED_SETUP_REVERSAL",
                "entry_model": "FAILED_SELL_REVERSAL",
                "blocked_strategy": blocked_strategy,
                "blocked_signal": blocked_signal,
                "pattern_height": abs(tp_reference - entry_price),
                "sweep_level": entry["low"],
                "recent_high": recent_high,
                "recent_low": recent_low,
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": "REVERSAL_1_5R_TARGET",
                "momentum": "bullish_reversal_after_failed_sell",
                "direction_context": "sell_setup_failed_bullish_sweep_reversal",
                "reason": (
                    f"Blocked SELL reversal -> original {blocked_strategy} SELL blocked by low RR -> "
                    f"sell-side sweep below {round(recent_low, 2)} -> "
                    f"bullish rejection + structure shift -> "
                    f"SL {sl_reference} -> TP {tp_reference}"
                ),
            }

    return None