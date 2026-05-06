from config.settings import ATR_MIN, ATR_MAX


AMD_LOOKBACK = 28
ACCUMULATION_BARS = 10

MAX_ACCUMULATION_RANGE_ATR = 2.8
MIN_ACCUMULATION_RANGE_ATR = 0.6

MIN_MANIPULATION_ATR = 0.15
MIN_DISPLACEMENT_BODY_ATR = 0.35
FVG_MIN_SIZE_ATR = 0.10

SL_ATR_BUFFER = 0.20
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 5.0

TARGET_ATR_MIN = 1.5
TARGET_ATR_MAX = 3.0


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, accumulation_range):
    return min(
        max(accumulation_range * 1.0, atr * TARGET_ATR_MIN),
        atr * TARGET_ATR_MAX,
    )


def _score_setup(base_score, displacement_body, atr, manipulation_depth, fvg_size):
    score = base_score

    if manipulation_depth > atr * 0.30:
        score += 2

    if displacement_body > atr * 0.50:
        score += 2

    if displacement_body > atr * 0.75:
        score += 2

    if fvg_size > atr * 0.20:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < AMD_LOOKBACK + 5:
        return None

    # Closed candles only
    accumulation = df.iloc[-(ACCUMULATION_BARS + 5):-5]
    manipulation = df.iloc[-4]
    displacement = df.iloc[-3]
    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    accumulation_high = accumulation["high"].max()
    accumulation_low = accumulation["low"].min()
    accumulation_range = accumulation_high - accumulation_low

    if accumulation_range <= 0:
        return None

    if accumulation_range > atr * MAX_ACCUMULATION_RANGE_ATR:
        return None

    if accumulation_range < atr * MIN_ACCUMULATION_RANGE_ATR:
        return None

    manipulation_body = abs(manipulation["close"] - manipulation["open"])
    displacement_body = abs(displacement["close"] - displacement["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if displacement_body < atr * MIN_DISPLACEMENT_BODY_ATR:
        return None

    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, accumulation_range)

    # =========================================================
    # BUY: sell-side manipulation + bullish displacement + bullish FVG
    # =========================================================
    swept_low = manipulation["low"] < accumulation_low
    manipulation_depth = accumulation_low - manipulation["low"]

    closed_back_inside = manipulation["close"] > accumulation_low

    bullish_displacement = (
        displacement["close"] > displacement["open"]
        and displacement["close"] > accumulation_high
        and displacement_body > atr * MIN_DISPLACEMENT_BODY_ATR
        and price > ema
    )

    bullish_fvg_exists = manipulation["high"] < entry["low"]
    bullish_fvg_bottom = manipulation["high"]
    bullish_fvg_top = entry["low"]
    bullish_fvg_size = bullish_fvg_top - bullish_fvg_bottom

    bullish_reclaim = (
        entry["close"] > entry["open"]
        and entry["close"] > bullish_fvg_top
        and entry_body > atr * 0.20
    )

    if (
        swept_low
        and manipulation_depth > atr * MIN_MANIPULATION_ATR
        and closed_back_inside
        and bullish_displacement
        and bullish_fvg_exists
        and bullish_fvg_size > atr * FVG_MIN_SIZE_ATR
        and bullish_reclaim
    ):
        sl_reference = round(manipulation["low"] - sl_buffer, 2)

        if accumulation_high > entry["close"]:
            tp_reference = accumulation_high
            target_model = "ACCUMULATION_HIGH"
        else:
            tp_reference = entry["close"] + target_distance
            target_model = "AMD_MEASURED_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            displacement_body=displacement_body,
            atr=atr,
            manipulation_depth=manipulation_depth,
            fvg_size=bullish_fvg_size,
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "AMD_FVG",
            "entry_model": "AMD_SELLSIDE_SWEEP_BULLISH_FVG",
            "pattern_height": abs(tp_reference - entry["close"]),
            "accumulation_high": accumulation_high,
            "accumulation_low": accumulation_low,
            "manipulation_low": manipulation["low"],
            "fvg_bottom": bullish_fvg_bottom,
            "fvg_top": bullish_fvg_top,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_displacement_after_sellside_sweep",
            "direction_context": "amd_bullish_reversal",
            "reason": (
                f"AMD FVG BUY -> accumulation {round(accumulation_low, 2)}-{round(accumulation_high, 2)} -> "
                f"sell-side sweep {round(manipulation['low'], 2)} -> bullish displacement + FVG "
                f"{round(bullish_fvg_bottom, 2)}-{round(bullish_fvg_top, 2)} -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
            ),
        }

    # =========================================================
    # SELL: buy-side manipulation + bearish displacement + bearish FVG
    # =========================================================
    swept_high = manipulation["high"] > accumulation_high
    manipulation_depth = manipulation["high"] - accumulation_high

    closed_back_inside = manipulation["close"] < accumulation_high

    bearish_displacement = (
        displacement["close"] < displacement["open"]
        and displacement["close"] < accumulation_low
        and displacement_body > atr * MIN_DISPLACEMENT_BODY_ATR
        and price < ema
    )

    bearish_fvg_exists = manipulation["low"] > entry["high"]
    bearish_fvg_top = manipulation["low"]
    bearish_fvg_bottom = entry["high"]
    bearish_fvg_size = bearish_fvg_top - bearish_fvg_bottom

    bearish_reclaim = (
        entry["close"] < entry["open"]
        and entry["close"] < bearish_fvg_bottom
        and entry_body > atr * 0.20
    )

    if (
        swept_high
        and manipulation_depth > atr * MIN_MANIPULATION_ATR
        and closed_back_inside
        and bearish_displacement
        and bearish_fvg_exists
        and bearish_fvg_size > atr * FVG_MIN_SIZE_ATR
        and bearish_reclaim
    ):
        sl_reference = round(manipulation["high"] + sl_buffer, 2)

        if accumulation_low < entry["close"]:
            tp_reference = accumulation_low
            target_model = "ACCUMULATION_LOW"
        else:
            tp_reference = entry["close"] - target_distance
            target_model = "AMD_MEASURED_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return None

        score = _score_setup(
            base_score=92,
            displacement_body=displacement_body,
            atr=atr,
            manipulation_depth=manipulation_depth,
            fvg_size=bearish_fvg_size,
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "AMD_FVG",
            "entry_model": "AMD_BUYSIDE_SWEEP_BEARISH_FVG",
            "pattern_height": abs(entry["close"] - tp_reference),
            "accumulation_high": accumulation_high,
            "accumulation_low": accumulation_low,
            "manipulation_high": manipulation["high"],
            "fvg_bottom": bearish_fvg_bottom,
            "fvg_top": bearish_fvg_top,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_displacement_after_buyside_sweep",
            "direction_context": "amd_bearish_reversal",
            "reason": (
                f"AMD FVG SELL -> accumulation {round(accumulation_low, 2)}-{round(accumulation_high, 2)} -> "
                f"buy-side sweep {round(manipulation['high'], 2)} -> bearish displacement + FVG "
                f"{round(bearish_fvg_bottom, 2)}-{round(bearish_fvg_top, 2)} -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
            ),
        }

    return None