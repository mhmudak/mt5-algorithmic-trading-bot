from src.structure_liquidity_context import analyze_structure_liquidity


def generate_signal(df):
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