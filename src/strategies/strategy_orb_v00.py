import hashlib
from config.settings import ATR_MIN, ATR_MAX

ORB_WINDOW = 15


PHASE6P3D_ORB_V00_STANDARDIZATION = True
PHASE6P3D_STRATEGY_NAME = "ORB_V00"
PHASE6P3D_FALLBACK_PHASE_NAME = "PHASE_6P3D_ORB_V00_STANDARDIZED_COMPLETION"
PHASE6P3D_SETUP_PREFIX = "ORBV00"
PHASE6P3D_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"


def _phase6p3d_generate_signal_raw(df):
    if len(df) < ORB_WINDOW + 5:
        return None

    data = df.iloc[-(ORB_WINDOW + 5):-2]

    orb_high = data["high"].max()
    orb_low = data["low"].min()
    orb_width = orb_high - orb_low

    entry = df.iloc[-2]

    atr = entry["atr_14"]
    ema = entry["ema_20"]
    price = entry["close"]

    if atr < ATR_MIN or atr > ATR_MAX:
        return None

    body = abs(entry["close"] - entry["open"])

    # =========================
    # BUY
    # =========================
    if price > orb_high and body > atr * 0.3 and price > ema:

        breakout_distance = price - orb_high

        max_immediate = min(atr * 0.35, orb_width * 0.20)
        max_retest = min(atr * 0.80, orb_width * 0.45)

        if breakout_distance <= max_immediate:
            entry_model = "BREAKOUT"
        elif breakout_distance <= max_retest:
            entry_model = "WAIT_RETEST"
        else:
            return None  # ❌ too extended → skip
        
        sl_reference = round(orb_high - max(atr * 0.25, 1.5), 2) # may delete this
        tp_reference = round(price + orb_width, 2)

        return {
            "signal": "BUY",
            "score": 92,
            "strategy": "ORB_V00",
            "entry_model": entry_model,
            "pattern_height": orb_width,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "breakout_distance": breakout_distance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "ORB_V00_RANGE_EXTENSION",
            "reason": f"ORB_V00 BUY ({entry_model}) -> range {round(orb_low,2)}-{round(orb_high,2)}",
        }

    # =========================
    # SELL
    # =========================
    if price < orb_low and body > atr * 0.3 and price < ema:

        breakout_distance = orb_low - price

        max_immediate = min(atr * 0.35, orb_width * 0.20)
        max_retest = min(atr * 0.80, orb_width * 0.45)

        if breakout_distance <= max_immediate:
            entry_model = "BREAKOUT"
        elif breakout_distance <= max_retest:
            entry_model = "WAIT_RETEST"
        else:
            return None  # ❌ too extended → skip
        
        sl_reference = round(orb_low + max(atr * 0.25, 1.5), 2)
        tp_reference = round(price - orb_width, 2)

        return {
            "signal": "SELL",
            "score": 92,
            "strategy": "ORB_V00",
            "entry_model": entry_model,
            "pattern_height": orb_width,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "breakout_distance": breakout_distance,
            "sl_reference": sl_reference,
            "tp_reference": tp_reference,
            "target_model": "ORB_V00_RANGE_EXTENSION",
            "reason": f"ORB_V00 SELL ({entry_model}) -> range {round(orb_low,2)}-{round(orb_high,2)}",
        }

    return None


def _phase6p3d_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _phase6p3d_entry_reference(df, payload):
    for key in ("entry_reference", "entry_price", "entry", "price"):
        value = _phase6p3d_float(payload.get(key))

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


def _phase6p3d_risk_reward(signal, entry_reference, sl_reference, tp_reference):
    entry_reference = _phase6p3d_float(entry_reference)
    sl_reference = _phase6p3d_float(sl_reference)
    tp_reference = _phase6p3d_float(tp_reference)

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


def _phase6p3d_setup_id(payload, entry_reference):
    signal = payload.get("signal", "NA")
    entry_model = payload.get("entry_model", payload.get("type", "NA"))
    sl_reference = payload.get("sl_reference", payload.get("stop_loss", ""))
    tp_reference = payload.get("tp_reference", payload.get("take_profit", ""))

    raw = (
        f"{PHASE6P3D_STRATEGY_NAME}:{signal}:{entry_model}:"
        f"{round(float(entry_reference), 2)}:{sl_reference}:{tp_reference}"
    )
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]

    return f"{PHASE6P3D_SETUP_PREFIX}-{signal}-{digest}"


def _phase6p3d_standardize_signal(payload, df):
    if not payload:
        return payload

    signal = payload.get("signal")
    entry_reference = _phase6p3d_entry_reference(df, payload)

    if entry_reference is None:
        return payload

    existing_rr = _phase6p3d_float(payload.get("rr"))
    existing_risk_reward = _phase6p3d_float(payload.get("risk_reward"))

    computed_rr = _phase6p3d_risk_reward(
        signal=signal,
        entry_reference=entry_reference,
        sl_reference=payload.get("sl_reference", payload.get("stop_loss")),
        tp_reference=payload.get("tp_reference", payload.get("take_profit")),
    )

    final_rr = existing_rr if existing_rr is not None else existing_risk_reward
    final_rr = final_rr if final_rr is not None else computed_rr

    payload.setdefault("strategy", PHASE6P3D_STRATEGY_NAME)
    payload.setdefault("phase", PHASE6P3D_FALLBACK_PHASE_NAME)
    payload.setdefault("setup_id", _phase6p3d_setup_id(payload, entry_reference))
    payload.setdefault("entry_reference", round(float(entry_reference), 2))

    if final_rr is not None:
        payload.setdefault("rr", final_rr)
        payload.setdefault("risk_reward", final_rr)

    payload.setdefault("auto_trade_allowed", True)
    payload.setdefault("decision_impact", "MAIN_BOT_RUNTIME_CONTROLLED")
    payload.setdefault("duplicate_policy", PHASE6P3D_DUPLICATE_POLICY)

    return payload


def generate_signal(df):
    return _phase6p3d_standardize_signal(_phase6p3d_generate_signal_raw(df), df)

