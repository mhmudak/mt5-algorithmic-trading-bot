import hashlib
from src.structure_liquidity_context import analyze_structure_liquidity



PHASE6P3C_REMAINING_LEGACY_STANDARDIZATION = True
PHASE6P3C_STRATEGY_NAME = "STRUCTURE_LIQUIDITY"
PHASE6P3C_FALLBACK_PHASE_NAME = "PHASE_6P3C_STRUCTURE_LIQUIDITY_STANDARDIZED_COMPLETION"
PHASE6P3C_SETUP_PREFIX = "SLQ"
PHASE6P3C_DUPLICATE_POLICY = "setup_id_by_strategy_signal_entry_model_entry_sl_tp"

def _phase6p3c_generate_signal_raw(df):
    context = analyze_structure_liquidity(df)

    if context is None:
        return None

    signal = context["bias"]

    return {
        "signal": signal,
        "score": context["score"],
        "strategy": "STRUCTURE_LIQUIDITY",
        "entry_model": "SR_LIQUIDITY_STRUCTURE_CONFLUENCE",
        "pattern_height": abs(context["tp_reference"] - context["sl_reference"]),
        "support": context["support"],
        "resistance": context["resistance"],
        "sweep_level": context["sweep_level"],
        "sl_reference": context["sl_reference"],
        "tp_reference": context["tp_reference"],
        "target_model": context["target_model"],
        "momentum": context["momentum"],
        "direction_context": context["direction_context"],
        "reason": (
            f"Structure/Liquidity {signal} -> "
            f"support={round(context['support'], 2)} "
            f"resistance={round(context['resistance'], 2)} -> "
            f"sweep level={round(context['sweep_level'], 2)} -> "
            f"reasons={','.join(context['reasons'])} -> "
            f"SL {context['sl_reference']} -> "
            f"TP {context['target_model']} {context['tp_reference']}"
        ),
    }


def _phase6p3c_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _phase6p3c_entry_reference(df, payload):
    for key in ("entry_reference", "entry_price", "entry", "price"):
        value = _phase6p3c_float(payload.get(key))

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


def _phase6p3c_risk_reward(signal, entry_reference, sl_reference, tp_reference):
    entry_reference = _phase6p3c_float(entry_reference)
    sl_reference = _phase6p3c_float(sl_reference)
    tp_reference = _phase6p3c_float(tp_reference)

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


def _phase6p3c_setup_id(payload, entry_reference):
    signal = payload.get("signal", "NA")
    entry_model = payload.get("entry_model", payload.get("type", "NA"))
    sl_reference = payload.get("sl_reference", payload.get("stop_loss", ""))
    tp_reference = payload.get("tp_reference", payload.get("take_profit", ""))

    raw = (
        f"{PHASE6P3C_STRATEGY_NAME}:{signal}:{entry_model}:"
        f"{round(float(entry_reference), 2)}:{sl_reference}:{tp_reference}"
    )
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]

    return f"{PHASE6P3C_SETUP_PREFIX}-{signal}-{digest}"


def _phase6p3c_standardize_signal(payload, df):
    if not payload:
        return payload

    signal = payload.get("signal")
    entry_reference = _phase6p3c_entry_reference(df, payload)

    if entry_reference is None:
        return payload

    existing_rr = _phase6p3c_float(payload.get("rr"))
    existing_risk_reward = _phase6p3c_float(payload.get("risk_reward"))

    computed_rr = _phase6p3c_risk_reward(
        signal=signal,
        entry_reference=entry_reference,
        sl_reference=payload.get("sl_reference", payload.get("stop_loss")),
        tp_reference=payload.get("tp_reference", payload.get("take_profit")),
    )

    final_rr = existing_rr if existing_rr is not None else existing_risk_reward
    final_rr = final_rr if final_rr is not None else computed_rr

    payload.setdefault("strategy", PHASE6P3C_STRATEGY_NAME)
    payload.setdefault("phase", PHASE6P3C_FALLBACK_PHASE_NAME)
    payload.setdefault("setup_id", _phase6p3c_setup_id(payload, entry_reference))
    payload.setdefault("entry_reference", round(float(entry_reference), 2))

    if final_rr is not None:
        payload.setdefault("rr", final_rr)
        payload.setdefault("risk_reward", final_rr)

    payload.setdefault("auto_trade_allowed", True)
    payload.setdefault("decision_impact", "MAIN_BOT_RUNTIME_CONTROLLED")
    payload.setdefault("duplicate_policy", PHASE6P3C_DUPLICATE_POLICY)

    return payload


def generate_signal(df):
    return _phase6p3c_standardize_signal(_phase6p3c_generate_signal_raw(df), df)

