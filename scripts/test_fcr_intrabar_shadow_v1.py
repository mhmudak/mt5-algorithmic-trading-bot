from __future__ import annotations

import ast
from pathlib import Path
import re
from types import SimpleNamespace

import pandas as pd

from src import fcr_intrabar_shadow as shadow
from src.strategies import strategy_fcr_m1_fvg as fcr


ROOT = Path(__file__).resolve().parents[1]


def _build_frames():
    m5_rows = []
    for i in range(11):
        m5_rows.append(
            {
                "time": i * 300,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 99.5,
                "atr_14": 1.0,
                "ema_20": 100.0,
            }
        )

    m1_rows = []
    for i in range(10):
        m1_rows.append(
            {
                "time": 600 + i * 60,
                "open": 99.5,
                "high": 99.7,
                "low": 99.2,
                "close": 99.4,
                "atr_14": 1.0,
                "ema_20": 99.5,
            }
        )

    m1_rows[-3].update(
        {
            "open": 99.0,
            "high": 99.2,
            "low": 98.7,
            "close": 98.8,
        }
    )
    m1_rows[-2].update(
        {
            "open": 98.9,
            "high": 99.0,
            "low": 98.4,
            "close": 98.6,
        }
    )
    m1_rows[-1].update(
        {
            "open": 98.7,
            "high": 98.9,
            "low": 98.0,
            "close": 98.2,
            "ema_20": 99.5,
        }
    )

    return pd.DataFrame(m5_rows), pd.DataFrame(m1_rows)


def test_forming_sell_candidate():
    m5_df, m1_df = _build_frames()

    old = {
        "FCR_MIN_RANGE_ATR": fcr.FCR_MIN_RANGE_ATR,
        "FCR_MIN_BODY_ATR": fcr.FCR_MIN_BODY_ATR,
        "ATR_MIN": fcr.ATR_MIN,
        "ATR_MAX": fcr.ATR_MAX,
        "MIN_M1_BODY_ATR": fcr.MIN_M1_BODY_ATR,
        "MAX_EXTENSION_ATR": fcr.MAX_EXTENSION_ATR,
        "TARGET_R_MULTIPLIER": fcr.TARGET_R_MULTIPLIER,
        "detect_bearish": fcr._detect_bearish_fvg,
        "detect_bullish": fcr._detect_bullish_fvg,
        "sl_buffer": fcr._sl_buffer,
        "score": fcr._score_setup,
    }

    try:
        fcr.FCR_MIN_RANGE_ATR = 0.1
        fcr.FCR_MIN_BODY_ATR = 0.1
        fcr.ATR_MIN = 0.1
        fcr.ATR_MAX = 10.0
        fcr.MIN_M1_BODY_ATR = 0.1
        fcr.MAX_EXTENSION_ATR = 10.0
        fcr.TARGET_R_MULTIPLIER = 3.0
        fcr._detect_bearish_fvg = lambda c1, c3, atr: (
            98.5,
            99.0,
            0.5,
        )
        fcr._detect_bullish_fvg = lambda c1, c3, atr: None
        fcr._sl_buffer = lambda atr: 0.2
        fcr._score_setup = lambda **kwargs: 100

        candidate = shadow.evaluate_forming_m1_candidate(
            m5_df,
            m1_df,
        )

        assert candidate is not None
        assert candidate["signal"] == "SELL"
        assert candidate["entry_reference"] == 98.2
        assert candidate["sl_reference"] == 99.2
        assert candidate["tp_reference"] == 95.2
        assert candidate["execution_authority"] is False
        assert candidate["decision_impact"] == "OBSERVE_ONLY"

    finally:
        fcr.FCR_MIN_RANGE_ATR = old["FCR_MIN_RANGE_ATR"]
        fcr.FCR_MIN_BODY_ATR = old["FCR_MIN_BODY_ATR"]
        fcr.ATR_MIN = old["ATR_MIN"]
        fcr.ATR_MAX = old["ATR_MAX"]
        fcr.MIN_M1_BODY_ATR = old["MIN_M1_BODY_ATR"]
        fcr.MAX_EXTENSION_ATR = old["MAX_EXTENSION_ATR"]
        fcr.TARGET_R_MULTIPLIER = old["TARGET_R_MULTIPLIER"]
        fcr._detect_bearish_fvg = old["detect_bearish"]
        fcr._detect_bullish_fvg = old["detect_bullish"]
        fcr._sl_buffer = old["sl_buffer"]
        fcr._score_setup = old["score"]


def test_finalize_survival_and_path_metrics():
    active = {
        "signal": "SELL",
        "entry_model": "M5_FCR_LOW_BREAK_M1_FVG_ENGULF",
        "m1_candle_epoch": 1000,
        "first_trigger_epoch": 1020,
        "intrabar_signal_entry": 100.0,
        "market_price_at_trigger": 99.8,
        "min_price_after_trigger": 98.8,
        "max_price_after_trigger": 100.3,
        "execution_authority": False,
        "decision_impact": "OBSERVE_ONLY",
    }

    closed = {
        "strategy": "FCR_M1_FVG",
        "signal": "SELL",
        "entry_model": "M5_FCR_LOW_BREAK_M1_FVG_ENGULF",
        "entry_reference": 99.4,
        "sl_reference": 101.0,
        "tp_reference": 94.6,
    }

    record = shadow.finalize_observation(
        active,
        closed,
        close_epoch=1060,
    )

    assert record["survived_close"] is True
    assert record["false_positive"] is False
    assert record["lead_seconds"] == 40
    assert record["mfe_to_close"] == 1.0
    assert record["mae_to_close"] == 0.5
    assert record["entry_improvement_vs_close"] == 0.6
    assert record["execution_authority"] is False


def test_false_positive_label():
    active = {
        "signal": "BUY",
        "entry_model": "M5_FCR_HIGH_BREAK_M1_FVG_ENGULF",
        "m1_candle_epoch": 1000,
        "first_trigger_epoch": 1030,
        "intrabar_signal_entry": 100.0,
        "market_price_at_trigger": 100.1,
        "min_price_after_trigger": 99.8,
        "max_price_after_trigger": 100.5,
    }

    record = shadow.finalize_observation(
        active,
        None,
        close_epoch=1060,
    )

    assert record["survived_close"] is False
    assert record["false_positive"] is True
    assert record["lead_seconds"] == 30


def test_live_wiring_observe_only():
    live = (
        ROOT / "src" / "live_bot.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )
    observer_text = (
        ROOT / "src" / "fcr_intrabar_shadow.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )
    wrapper_text = (
        ROOT
        / "scripts"
        / "run_live_bot_research_shadow_fcr_intrabar.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "observe_fcr_intrabar_shadow(" in live
    assert "ENABLE_FCR_M1_FVG_INTRABAR_SHADOW" in live
    assert "execute_trade(" not in observer_text
    assert "order_send(" not in observer_text
    assert "execution_engine" not in observer_text
    assert "calculate_trade_plan" not in observer_text
    assert "ENABLE_FCR_M1_FVG_INTRABAR_SHADOW = True" in wrapper_text


def test_settings_safe_defaults_and_allowlist():
    settings_path = ROOT / "config" / "settings.py"
    text = settings_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert re.search(
        r"(?m)^ENABLE_FCR_M1_FVG_INTRABAR_SHADOW\s*=\s*False\s*$",
        text,
    )

    tree = ast.parse(text)
    allowlist = None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name)
            and target.id == "INTRABAR_STRATEGY_ALLOWLIST"
            for target in node.targets
        ):
            continue

        allowlist = ast.literal_eval(node.value)
        break

    assert allowlist is not None
    assert "FCR_M1_FVG" not in {
        str(item).upper()
        for item in allowlist
    }


def test_fixed_lot_unchanged():
    text = (
        ROOT / "config" / "settings.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    match = re.search(
        r"(?m)^FIXED_LOT\s*=\s*([0-9.]+)\s*$",
        text,
    )

    assert match
    assert float(match.group(1)) == 0.25


def main():
    test_forming_sell_candidate()
    test_finalize_survival_and_path_metrics()
    test_false_positive_label()
    test_live_wiring_observe_only()
    test_settings_safe_defaults_and_allowlist()
    test_fixed_lot_unchanged()

    print("PASS: forming-M1 FCR shadow candidate mirrors native SELL geometry")
    print("PASS: close reconciliation records survival/false-positive labels")
    print("PASS: lead time and pre-close MAE/MFE metrics are recorded")
    print("PASS: FCR is NOT added to live intrabar allowlist")
    print("PASS: observer has no execution/trade-plan authority")
    print("PASS: committed intrabar-shadow toggle remains False")
    print("PASS: research wrapper enables shadow for runtime only")
    print("PASS: FIXED_LOT remains exactly 0.25")


if __name__ == "__main__":
    main()
