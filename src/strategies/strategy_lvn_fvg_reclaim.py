import hashlib
from config.settings import ATR_MIN, ATR_MAX
from src.volume_profile_context import (
    build_volume_profile,
    find_nearest_lvn,
    find_target_hvn_or_poc,
)



PHASE6P3B_SMC_LIQUIDITY_STANDARDIZATION = True
PHASE6P3B_STRATEGY_NAME = "LVN_FVG_RECLAIM"
PHASE6P3B_FALLBACK_PHASE_NAME = "PHASE_6P3B_LVN_FVG_RECLAIM_STANDARDIZED_COMPLETION"
PHASE6P3B_SETUP_PREFIX = "LVN"
PHASE6P3B_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

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


def _phase6p3b_generate_signal_raw(df):
    if len(df) < LVN_FVG_LOOKBACK:
        return None

    profile = build_volume_profile(df, lookback=LVN_FVG_LOOKBACK)

    if profile is None:
        return None

    c1 = df.iloc[-4]
    c2 = df.iloc[-3]
    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body_c2 = abs(c2["close"] - c2["open"])
    body_entry = abs(entry["close"] - entry["open"])

    if body_entry < atr * MIN_REACTION_BODY_ATR:
        return None

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
            return None

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
            return None

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
                f"LVN FVG BUY -> bullish FVG {round(bullish_fvg_bottom, 2)}-{round(bullish_fvg_top, 2)} "
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
            return None

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
            return None

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
                f"LVN FVG SELL -> bearish FVG {round(bearish_fvg_bottom, 2)}-{round(bearish_fvg_top, 2)} "
                f"near LVN {nearest_lvn['price']} -> reclaim confirmed -> "
                f"SL {sl_reference} -> TP {target_model} {tp_reference}"
            ),
        }

    return None


def _phase6p3b_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _phase6p3b_entry_reference(df, payload):
    for key in ("entry_reference", "entry_price", "entry", "price"):
        value = _phase6p3b_float(payload.get(key))

        if value is not None:
            return value

    try:
        if df is not None and len(df) >= 2:
            return float(df.iloc[-2]["close"])
    except Exception:
        pass

    try:
        if df is not None and len(df) >= 1:
            return float(df.iloc[-1]["close"])
    except Exception:
        pass

    return None


def _phase6p3b_risk_reward(signal, entry_reference, sl_reference, tp_reference):
    entry_reference = _phase6p3b_float(entry_reference)
    sl_reference = _phase6p3b_float(sl_reference)
    tp_reference = _phase6p3b_float(tp_reference)

    if entry_reference is None or sl_reference is None or tp_reference is None:
        return None

    if signal == "BUY":
        risk = entry_reference - sl_reference
        reward = tp_reference - entry_reference
    else:
        risk = sl_reference - entry_reference
        reward = entry_reference - tp_reference

    if risk <= 0:
        return None

    return round(reward / risk, 2)


def _phase6p3b_setup_id(payload, entry_reference):
    signal = payload.get("signal", "NA")
    entry_model = payload.get("entry_model", payload.get("type", "NA"))
    sl_reference = payload.get("sl_reference", payload.get("stop_loss", ""))
    tp_reference = payload.get("tp_reference", payload.get("take_profit", ""))

    raw = (
        f"{PHASE6P3B_STRATEGY_NAME}:{signal}:{entry_model}:"
        f"{round(float(entry_reference), 2)}:{sl_reference}:{tp_reference}"
    )
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]

    return f"{PHASE6P3B_SETUP_PREFIX}-{signal}-{digest}"


def _phase6p3b_standardize_signal(payload, df):
    if not payload:
        return payload

    signal = payload.get("signal")
    entry_reference = _phase6p3b_entry_reference(df, payload)

    if entry_reference is None:
        return payload

    existing_rr = _phase6p3b_float(payload.get("rr"))
    existing_risk_reward = _phase6p3b_float(payload.get("risk_reward"))

    computed_rr = _phase6p3b_risk_reward(
        signal=signal,
        entry_reference=entry_reference,
        sl_reference=payload.get("sl_reference", payload.get("stop_loss")),
        tp_reference=payload.get("tp_reference", payload.get("take_profit")),
    )

    final_rr = existing_rr if existing_rr is not None else existing_risk_reward
    final_rr = final_rr if final_rr is not None else computed_rr

    payload.setdefault("strategy", PHASE6P3B_STRATEGY_NAME)
    payload.setdefault("phase", PHASE6P3B_FALLBACK_PHASE_NAME)
    payload.setdefault("setup_id", _phase6p3b_setup_id(payload, entry_reference))
    payload.setdefault("entry_reference", round(float(entry_reference), 2))

    if final_rr is not None:
        payload.setdefault("rr", final_rr)
        payload.setdefault("risk_reward", final_rr)

    payload.setdefault("auto_trade_allowed", True)
    payload.setdefault("decision_impact", "MAIN_BOT_RUNTIME_CONTROLLED")
    payload.setdefault("duplicate_policy", PHASE6P3B_DUPLICATE_POLICY)

    return payload


def generate_signal(df):
    return _phase6p3b_standardize_signal(_phase6p3b_generate_signal_raw(df), df)

