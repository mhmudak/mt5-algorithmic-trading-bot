from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.key_level_smc_override import (
    evaluate_key_level_strong_smc_override,
)


def base_setup():
    return {
        "strategy": "KEY_LEVEL_BREAK_HOLD",
        "signal": "BUY",
        "score": 100,
        "entry_model": "KEY_LEVEL_BREAK_HOLD_BUY",
        "entry_reference": 4138.61,
        "sl_reference": 4125.86,
        "tp_reference": 4161.56,
        "rr": 1.80,
        "smc": ["ema_bullish"],
        "reason": (
            "KEY_LEVEL_BREAK_HOLD BUY -> "
            "resistance 4136.68 broken and held -> "
            "touches 3 -> SL 4125.86 -> TP 4161.56 "
            "| SMC: ema_bullish "
            "| MACRO: dxy_inverse_confirms_sell,"
            "usdjpy_inverse_confirms_sell"
        ),
    }


positive = evaluate_key_level_strong_smc_override(
    base_setup(),
    "BUY",
)

assert positive["allowed"] is True
assert (
    positive["reason"]
    == "key_level_strong_smc_override_allowed"
)
assert positive["snapshot"]["touches"] == 3
assert positive["snapshot"]["orders_sent"] == 0


low_score = base_setup()
low_score["score"] = 99

assert (
    evaluate_key_level_strong_smc_override(
        low_score,
        "BUY",
    )["allowed"]
    is False
)


low_rr = base_setup()
low_rr["rr"] = 1.79

assert (
    evaluate_key_level_strong_smc_override(
        low_rr,
        "BUY",
    )["reason"]
    == "key_level_override_rr_too_low"
)


low_touches = base_setup()
low_touches["reason"] = (
    low_touches["reason"]
    .replace("touches 3", "touches 2")
)

assert (
    evaluate_key_level_strong_smc_override(
        low_touches,
        "BUY",
    )["reason"]
    == "key_level_override_touches_too_low"
)


wrong_ema = base_setup()
wrong_ema["smc"] = ["ema_bearish"]
wrong_ema["reason"] = (
    wrong_ema["reason"]
    .replace("ema_bullish", "ema_bearish")
)

assert (
    evaluate_key_level_strong_smc_override(
        wrong_ema,
        "BUY",
    )["reason"]
    == "key_level_ema_alignment_missing"
)


opposite_htf = base_setup()
opposite_htf["mtf_bias"] = "SELL"

assert (
    evaluate_key_level_strong_smc_override(
        opposite_htf,
        "BUY",
    )["reason"]
    == "key_level_opposite_htf_context"
)


overextended = base_setup()
overextended["extension_atr_ratio"] = 0.80

assert (
    evaluate_key_level_strong_smc_override(
        overextended,
        "BUY",
    )["reason"]
    == "key_level_setup_overextended"
)


other_strategy = base_setup()
other_strategy["strategy"] = "ORDER_BLOCK"

assert (
    evaluate_key_level_strong_smc_override(
        other_strategy,
        "BUY",
    )["reason"]
    == "key_level_strategy_not_applicable"
)


live_source = Path("src/live_bot.py").read_text(
    encoding="utf-8",
)

assert (
    "evaluate_key_level_strong_smc_override"
    in live_source
)
assert "smc_override_allowed" in live_source
assert (
    "KEY_LEVEL_STRONG_SMC_OVERRIDE"
    in live_source
)


settings_source = Path(
    "config/settings.py"
).read_text(encoding="utf-8")

match = re.search(
    r"SOFT_SMC_STRATEGIES\s*=\s*\[(.*?)\]",
    settings_source,
    flags=re.DOTALL,
)

assert match is not None
assert (
    '"KEY_LEVEL_BREAK_HOLD"'
    not in match.group(1)
)

print(
    "[PASS] Conditional KEY_LEVEL_BREAK_HOLD "
    "strong-SMC override passed."
)
