from config.settings import ATR_MIN, ATR_MAX
from src.strategy_debug import reject_strategy
from src.volume_profile_context import (
    build_volume_profile,
    find_nearest_lvn,
    find_target_hvn_or_poc,
)


LVN_FVG_LOOKBACK = 120

FVG_MIN_SIZE_ATR = 0.12
LVN_MAX_DISTANCE_ATR = 0.45

MIN_REACTION_BODY_ATR = 0.20

SL_ATR_BUFFER = 0.20
MIN_SL_BUFFER = 2.0
MAX_SL_BUFFER = 5.0

FALLBACK_TARGET_ATR = 1.8


def _sl_buffer(atr):
    return min(max(atr * SL_ATR_BUFFER, MIN_SL_BUFFER), MAX_SL_BUFFER)


def _score_setup(base_score, body, atr, lvn_found, reclaim_quality, target_quality):
    score = base_score

    if body > atr * 0.30:
        score += 2

    if body > atr * 0.50:
        score += 2

    if lvn_found:
        score += 3

    if reclaim_quality:
        score += 3

    if target_quality:
        score += 2

    return min(score, 99)


def generate_signal(df):
    if len(df) < LVN_FVG_LOOKBACK:
        return reject_strategy(
            "LVN_FVG_RECLAIM",
            "not_enough_data",
            bars=len(df),
            required=LVN_FVG_LOOKBACK,
        )

    profile = build_volume_profile(df, lookback=LVN_FVG_LOOKBACK)

    if profile is None:
        return reject_strategy(
            "LVN_FVG_RECLAIM",
            "volume_profile_unavailable",
        )

    c1 = df.iloc[-4]
    c2 = df.iloc[-3]
    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return reject_strategy(
            "LVN_FVG_RECLAIM",
            "atr_out_of_range",
            atr=atr,
        )

    body_c2 = abs(c2["close"] - c2["open"])
    body_entry = abs(entry["close"] - entry["open"])

    if body_entry < atr * MIN_REACTION_BODY_ATR:
        return reject_strategy(
            "LVN_FVG_RECLAIM",
            "reaction_body_too_small",
            body_entry=round(body_entry, 2),
            required=round(atr * MIN_REACTION_BODY_ATR, 2),
        )

    sl_buffer = _sl_buffer(atr)

    # =========================================================
    # Bullish FVG inside/near LVN + reclaim
    # =========================================================
    bullish_fvg_exists = c1["high"] < entry["low"]
    bullish_fvg_bottom = c1["high"]
    bullish_fvg_top = entry["low"]
    bullish_fvg_size = bullish_fvg_top - bullish_fvg_bottom

    bullish_displacement = (
        c2["close"] > c2["open"]
        and body_c2 > atr * 0.30
    )

    bullish_reaction = (
        entry["close"] > entry["open"]
        and entry["close"] > bullish_fvg_top
        and price > ema
    )

    if (
        bullish_fvg_exists
        and bullish_fvg_size > atr * FVG_MIN_SIZE_ATR
        and bullish_displacement
        and bullish_reaction
    ):
        fvg_mid = (bullish_fvg_top + bullish_fvg_bottom) / 2

        nearest_lvn = find_nearest_lvn(
            price=fvg_mid,
            profile=profile,
            max_distance=atr * LVN_MAX_DISTANCE_ATR,
        )

        if nearest_lvn is None:
            return reject_strategy(
                "LVN_FVG_RECLAIM",
                "no_lvn_near_bullish_fvg",
                fvg_mid=round(fvg_mid, 2),
                max_distance=round(atr * LVN_MAX_DISTANCE_ATR, 2),
                poc=profile.get("poc"),
            )

        sl_reference = round(bullish_fvg_bottom - sl_buffer, 2)

        tp_reference, target_model = find_target_hvn_or_poc(
            signal="BUY",
            entry_price=entry["close"],
            profile=profile,
        )

        if tp_reference is None:
            tp_reference = entry["close"] + atr * FALLBACK_TARGET_ATR
            target_model = "FALLBACK_ATR_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference >= entry["close"] or tp_reference <= entry["close"]:
            return reject_strategy(
                "LVN_FVG_RECLAIM",
                "invalid_bullish_sl_tp",
                entry=round(entry["close"], 2),
                sl=sl_reference,
                tp=tp_reference,
            )

        score = _score_setup(
            base_score=92,
            body=body_entry,
            atr=atr,
            lvn_found=True,
            reclaim_quality=entry["close"] > c2["high"],
            target_quality=target_model in ["NEAREST_HVN_ABOVE", "POC_TARGET"],
        )

        return {
            "signal": "BUY",
            "score": score,
            "strategy": "LVN_FVG_RECLAIM",
            "entry_model": "BULLISH_LVN_FVG_RECLAIM",
            "pattern_height": abs(tp_reference - entry["close"]),
            "fvg_bottom": bullish_fvg_bottom,
            "fvg_top": bullish_fvg_top,
            "lvn_price": nearest_lvn["price"],
            "poc": profile["poc"],
            "value_area_low": profile["value_area_low"],
            "value_area_high": profile["value_area_high"],
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bullish_fvg_reclaim_from_lvn",
            "direction_context": "lvn_fvg_imbalance_reclaim",
            "reason": (
                f"LVN FVG BUY -> bullish FVG "
                f"{round(bullish_fvg_bottom, 2)}-{round(bullish_fvg_top, 2)} "
                f"near LVN {nearest_lvn['price']} -> reclaim confirmed -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
            ),
        }

    # =========================================================
    # Bearish FVG inside/near LVN + reclaim
    # =========================================================
    bearish_fvg_exists = c1["low"] > entry["high"]
    bearish_fvg_top = c1["low"]
    bearish_fvg_bottom = entry["high"]
    bearish_fvg_size = bearish_fvg_top - bearish_fvg_bottom

    bearish_displacement = (
        c2["close"] < c2["open"]
        and body_c2 > atr * 0.30
    )

    bearish_reaction = (
        entry["close"] < entry["open"]
        and entry["close"] < bearish_fvg_bottom
        and price < ema
    )

    if (
        bearish_fvg_exists
        and bearish_fvg_size > atr * FVG_MIN_SIZE_ATR
        and bearish_displacement
        and bearish_reaction
    ):
        fvg_mid = (bearish_fvg_top + bearish_fvg_bottom) / 2

        nearest_lvn = find_nearest_lvn(
            price=fvg_mid,
            profile=profile,
            max_distance=atr * LVN_MAX_DISTANCE_ATR,
        )

        if nearest_lvn is None:
            return reject_strategy(
                "LVN_FVG_RECLAIM",
                "no_lvn_near_bearish_fvg",
                fvg_mid=round(fvg_mid, 2),
                max_distance=round(atr * LVN_MAX_DISTANCE_ATR, 2),
                poc=profile.get("poc"),
            )

        sl_reference = round(bearish_fvg_top + sl_buffer, 2)

        tp_reference, target_model = find_target_hvn_or_poc(
            signal="SELL",
            entry_price=entry["close"],
            profile=profile,
        )

        if tp_reference is None:
            tp_reference = entry["close"] - atr * FALLBACK_TARGET_ATR
            target_model = "FALLBACK_ATR_EXTENSION"

        tp_reference = round(tp_reference, 2)

        if sl_reference <= entry["close"] or tp_reference >= entry["close"]:
            return reject_strategy(
                "LVN_FVG_RECLAIM",
                "invalid_bearish_sl_tp",
                entry=round(entry["close"], 2),
                sl=sl_reference,
                tp=tp_reference,
            )

        score = _score_setup(
            base_score=92,
            body=body_entry,
            atr=atr,
            lvn_found=True,
            reclaim_quality=entry["close"] < c2["low"],
            target_quality=target_model in ["NEAREST_HVN_BELOW", "POC_TARGET"],
        )

        return {
            "signal": "SELL",
            "score": score,
            "strategy": "LVN_FVG_RECLAIM",
            "entry_model": "BEARISH_LVN_FVG_RECLAIM",
            "pattern_height": abs(entry["close"] - tp_reference),
            "fvg_bottom": bearish_fvg_bottom,
            "fvg_top": bearish_fvg_top,
            "lvn_price": nearest_lvn["price"],
            "poc": profile["poc"],
            "value_area_low": profile["value_area_low"],
            "value_area_high": profile["value_area_high"],
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": target_model,
            "momentum": "bearish_fvg_reclaim_from_lvn",
            "direction_context": "lvn_fvg_imbalance_reclaim",
            "reason": (
                f"LVN FVG SELL -> bearish FVG "
                f"{round(bearish_fvg_bottom, 2)}-{round(bearish_fvg_top, 2)} "
                f"near LVN {nearest_lvn['price']} -> reclaim confirmed -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
            ),
        }

    return reject_strategy(
        "LVN_FVG_RECLAIM",
        "no_valid_lvn_fvg_setup",
        bullish_fvg_exists=bullish_fvg_exists,
        bullish_fvg_size=round(bullish_fvg_size, 2),
        bullish_displacement=bullish_displacement,
        bullish_reaction=bullish_reaction,
        bearish_fvg_exists=bearish_fvg_exists,
        bearish_fvg_size=round(bearish_fvg_size, 2),
        bearish_displacement=bearish_displacement,
        bearish_reaction=bearish_reaction,
        poc=profile.get("poc"),
        value_area_low=profile.get("value_area_low"),
        value_area_high=profile.get("value_area_high"),
    )