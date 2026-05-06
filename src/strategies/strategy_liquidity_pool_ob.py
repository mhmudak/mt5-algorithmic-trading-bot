from config.settings import ATR_MIN, ATR_MAX


POOL_LOOKBACK = 45
EQUAL_LEVEL_TOLERANCE_ATR = 0.20

MIN_SWEEP_DISTANCE_ATR = 0.12
MAX_SWEEP_DISTANCE_ATR = 1.50

MIN_DISPLACEMENT_BODY_ATR = 0.35
MIN_ENTRY_BODY_ATR = 0.20

MAX_OB_HEIGHT_ATR = 2.20
MIN_OB_HEIGHT_ATR = 0.15

SL_ATR_BUFFER = 0.20
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 5.0

TARGET_ATR_MIN = 1.5
TARGET_ATR_MAX = 3.0


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _target_distance(atr, structure_range):
    return min(
        max(structure_range * 0.70, atr * TARGET_ATR_MIN),
        atr * TARGET_ATR_MAX,
    )


def _find_equal_high(df, atr):
    recent = df.iloc[-POOL_LOOKBACK:-4]
    if recent.empty:
        return None

    tolerance = max(atr * EQUAL_LEVEL_TOLERANCE_ATR, 1.0)
    highs = recent["high"].tolist()

    for i in range(len(highs) - 1, 1, -1):
        for j in range(i - 1, -1, -1):
            if abs(highs[i] - highs[j]) <= tolerance:
                return max(highs[i], highs[j])

    return None


def _find_equal_low(df, atr):
    recent = df.iloc[-POOL_LOOKBACK:-4]
    if recent.empty:
        return None

    tolerance = max(atr * EQUAL_LEVEL_TOLERANCE_ATR, 1.0)
    lows = recent["low"].tolist()

    for i in range(len(lows) - 1, 1, -1):
        for j in range(i - 1, -1, -1):
            if abs(lows[i] - lows[j]) <= tolerance:
                return min(lows[i], lows[j])

    return None


def _previous_session_levels(df):
    if "time" not in df.columns:
        return None

    closed = df.iloc[:-1].copy()

    if closed.empty:
        return None

    current_day = closed["time"].dt.date.iloc[-1]
    previous = closed[closed["time"].dt.date < current_day]

    if previous.empty:
        return None

    previous_day = previous["time"].dt.date.max()
    prev_day_data = previous[previous["time"].dt.date == previous_day]

    return {
        "previous_session_high": prev_day_data["high"].max(),
        "previous_session_low": prev_day_data["low"].min(),
    }


def _select_liquidity_pool(levels):
    """
    Priority:
    1. Previous session high/low
    2. Equal highs/lows
    3. Recent high/low
    """
    valid = [level for level in levels if level["price"] is not None]

    if not valid:
        return None

    valid.sort(key=lambda item: item["priority"], reverse=True)
    return valid[0]


def _valid_sweep_distance(sweep_distance, atr):
    return (
        sweep_distance >= atr * MIN_SWEEP_DISTANCE_ATR
        and sweep_distance <= atr * MAX_SWEEP_DISTANCE_ATR
    )


def _valid_ob_size(ob_height, atr):
    return (
        ob_height >= atr * MIN_OB_HEIGHT_ATR
        and ob_height <= atr * MAX_OB_HEIGHT_ATR
    )


def _score_setup(
    base_score,
    displacement_body,
    entry_body,
    atr,
    liquidity_priority,
    sweep_distance,
    clean_ob_retest,
    close_aligned,
):
    score = base_score

    if displacement_body > atr * 0.50:
        score += 2

    if displacement_body > atr * 0.75:
        score += 2

    if entry_body > atr * 0.30:
        score += 2

    if clean_ob_retest:
        score += 2

    if close_aligned:
        score += 2

    # Previous session liquidity is strongest, equal highs/lows second.
    if liquidity_priority >= 3:
        score += 3
    elif liquidity_priority == 2:
        score += 2
    else:
        score += 1

    if sweep_distance > atr * 0.30:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < POOL_LOOKBACK + 8:
        return None

    # Closed candles:
    # ob_candle = potential order block / base candle
    # displacement = move away after liquidity sweep
    # entry = retest / reclaim candle
    ob_candle = df.iloc[-4]
    displacement = df.iloc[-3]
    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    displacement_body = abs(displacement["close"] - displacement["open"])
    entry_body = abs(entry["close"] - entry["open"])

    if displacement_body < atr * MIN_DISPLACEMENT_BODY_ATR:
        return None

    if entry_body < atr * MIN_ENTRY_BODY_ATR:
        return None

    recent = df.iloc[-POOL_LOOKBACK:-4]

    if recent.empty:
        return None

    recent_high = recent["high"].max()
    recent_low = recent["low"].min()
    structure_range = recent_high - recent_low

    if structure_range <= 0:
        return None

    equal_high = _find_equal_high(df, atr)
    equal_low = _find_equal_low(df, atr)

    previous_session = _previous_session_levels(df)

    previous_high = previous_session.get("previous_session_high") if previous_session else None
    previous_low = previous_session.get("previous_session_low") if previous_session else None

    sl_buffer = _sl_buffer(atr)
    target_distance = _target_distance(atr, structure_range)

    # =========================================================
    # BUY: sell-side liquidity swept -> bullish displacement -> OB retest/reclaim
    # =========================================================
    sell_side_pool = _select_liquidity_pool(
        [
            {
                "price": previous_low,
                "type": "PREVIOUS_SESSION_LOW",
                "priority": 3,
            },
            {
                "price": equal_low,
                "type": "EQUAL_LOWS",
                "priority": 2,
            },
            {
                "price": recent_low,
                "type": "RECENT_LOW",
                "priority": 1,
            },
        ]
    )

    if sell_side_pool is not None:
        liquidity_level = sell_side_pool["price"]

        sweep_low = min(ob_candle["low"], displacement["low"])
        sweep_distance = liquidity_level - sweep_low

        swept_sell_side = (
            sweep_low < liquidity_level
            and _valid_sweep_distance(sweep_distance, atr)
        )

        bullish_displacement = (
            displacement["close"] > displacement["open"]
            and displacement["close"] > ob_candle["high"]
            and displacement_body > atr * MIN_DISPLACEMENT_BODY_ATR
            and price > ema
        )

        bullish_ob = ob_candle["close"] < ob_candle["open"]
        ob_high = ob_candle["high"]
        ob_low = ob_candle["low"]
        ob_height = ob_high - ob_low

        valid_ob = bullish_ob and _valid_ob_size(ob_height, atr)

        retested_ob = (
            entry["low"] <= ob_high
            and entry["close"] > ob_low
        )

        bullish_reclaim = (
            entry["close"] > entry["open"]
            and entry["close"] > ob_high
            and entry["close"] > ema
        )

        if (
            swept_sell_side
            and bullish_displacement
            and valid_ob
            and retested_ob
            and bullish_reclaim
        ):
            sl_reference = round(min(ob_low, sweep_low, liquidity_level) - sl_buffer, 2)

            if recent_high > entry["close"]:
                tp_reference = recent_high
                target_model = "RECENT_STRUCTURE_HIGH"
            else:
                tp_reference = entry["close"] + target_distance
                target_model = "LIQUIDITY_OB_EXTENSION"

            tp_reference = round(tp_reference, 2)

            if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
                return None

            score = _score_setup(
                base_score=93,
                displacement_body=displacement_body,
                entry_body=entry_body,
                atr=atr,
                liquidity_priority=sell_side_pool["priority"],
                sweep_distance=sweep_distance,
                clean_ob_retest=True,
                close_aligned=price > ema,
            )

            return {
                "signal": "BUY",
                "score": score,
                "strategy": "LIQUIDITY_POOL_OB",
                "entry_model": "SELLSIDE_LIQUIDITY_SWEEP_OB_RECLAIM",
                "pattern_height": abs(tp_reference - entry["close"]),
                "liquidity_level": liquidity_level,
                "liquidity_type": sell_side_pool["type"],
                "equal_low": equal_low,
                "previous_session_low": previous_low,
                "recent_high": recent_high,
                "recent_low": recent_low,
                "sweep_low": sweep_low,
                "sweep_distance": round(sweep_distance, 2),
                "ob_high": ob_high,
                "ob_low": ob_low,
                "ob_height": round(ob_height, 2),
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": target_model,
                "momentum": "bullish_displacement_after_sellside_sweep",
                "direction_context": "liquidity_pool_sweep_order_block_reclaim",
                "reason": (
                    f"Liquidity Pool OB BUY -> {sell_side_pool['type']} swept near "
                    f"{round(liquidity_level, 2)} by {round(sweep_distance, 2)} -> "
                    f"bullish displacement -> OB retest/reclaim confirmed -> "
                    f"SL {sl_reference} -> TP {target_model} {tp_reference}"
                ),
            }

    # =========================================================
    # SELL: buy-side liquidity swept -> bearish displacement -> OB retest/rejection
    # =========================================================
    buy_side_pool = _select_liquidity_pool(
        [
            {
                "price": previous_high,
                "type": "PREVIOUS_SESSION_HIGH",
                "priority": 3,
            },
            {
                "price": equal_high,
                "type": "EQUAL_HIGHS",
                "priority": 2,
            },
            {
                "price": recent_high,
                "type": "RECENT_HIGH",
                "priority": 1,
            },
        ]
    )

    if buy_side_pool is not None:
        liquidity_level = buy_side_pool["price"]

        sweep_high = max(ob_candle["high"], displacement["high"])
        sweep_distance = sweep_high - liquidity_level

        swept_buy_side = (
            sweep_high > liquidity_level
            and _valid_sweep_distance(sweep_distance, atr)
        )

        bearish_displacement = (
            displacement["close"] < displacement["open"]
            and displacement["close"] < ob_candle["low"]
            and displacement_body > atr * MIN_DISPLACEMENT_BODY_ATR
            and price < ema
        )

        bearish_ob = ob_candle["close"] > ob_candle["open"]
        ob_high = ob_candle["high"]
        ob_low = ob_candle["low"]
        ob_height = ob_high - ob_low

        valid_ob = bearish_ob and _valid_ob_size(ob_height, atr)

        retested_ob = (
            entry["high"] >= ob_low
            and entry["close"] < ob_high
        )

        bearish_reclaim = (
            entry["close"] < entry["open"]
            and entry["close"] < ob_low
            and entry["close"] < ema
        )

        if (
            swept_buy_side
            and bearish_displacement
            and valid_ob
            and retested_ob
            and bearish_reclaim
        ):
            sl_reference = round(max(ob_high, sweep_high, liquidity_level) + sl_buffer, 2)

            if recent_low < entry["close"]:
                tp_reference = recent_low
                target_model = "RECENT_STRUCTURE_LOW"
            else:
                tp_reference = entry["close"] - target_distance
                target_model = "LIQUIDITY_OB_EXTENSION"

            tp_reference = round(tp_reference, 2)

            if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
                return None

            score = _score_setup(
                base_score=93,
                displacement_body=displacement_body,
                entry_body=entry_body,
                atr=atr,
                liquidity_priority=buy_side_pool["priority"],
                sweep_distance=sweep_distance,
                clean_ob_retest=True,
                close_aligned=price < ema,
            )

            return {
                "signal": "SELL",
                "score": score,
                "strategy": "LIQUIDITY_POOL_OB",
                "entry_model": "BUYSIDE_LIQUIDITY_SWEEP_OB_REJECT",
                "pattern_height": abs(entry["close"] - tp_reference),
                "liquidity_level": liquidity_level,
                "liquidity_type": buy_side_pool["type"],
                "equal_high": equal_high,
                "previous_session_high": previous_high,
                "recent_high": recent_high,
                "recent_low": recent_low,
                "sweep_high": sweep_high,
                "sweep_distance": round(sweep_distance, 2),
                "ob_high": ob_high,
                "ob_low": ob_low,
                "ob_height": round(ob_height, 2),
                "sl_reference": sl_reference,
                "tp_reference": tp_reference,
                "target_model": target_model,
                "momentum": "bearish_displacement_after_buyside_sweep",
                "direction_context": "liquidity_pool_sweep_order_block_rejection",
                "reason": (
                    f"Liquidity Pool OB SELL -> {buy_side_pool['type']} swept near "
                    f"{round(liquidity_level, 2)} by {round(sweep_distance, 2)} -> "
                    f"bearish displacement -> OB retest/rejection confirmed -> "
                    f"SL {sl_reference} -> TP {target_model} {tp_reference}"
                ),
            }

    return None