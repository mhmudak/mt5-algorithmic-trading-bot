from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.mtf_conflict_confirmation_execution_v2 import (
    evaluate_mtf_confirmation_execution_authority_v2,
)


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def make_report(
    *,
    confidence,
    score_delta,
    fail=0,
    error=0,
    approved=True,
):
    results = [
        {"module": "SETUP_SCHEMA", "status": "PASS"},
        {"module": "MARKET_REGIME", "status": "NEUTRAL"},
        {"module": "SESSION_CONTEXT", "status": "NEUTRAL"},
        {"module": "PRICE_ACTION_STRUCTURE", "status": "NEUTRAL"},
        {"module": "ENTRY_QUALITY", "status": "PASS"},
        {"module": "MT5_VOLUME_PROXY", "status": "PASS"},
    ]
    results += [
        {"module": f"FAIL_{i}", "status": "FAIL"}
        for i in range(fail)
    ]
    results += [
        {"module": f"ERROR_{i}", "status": "ERROR"}
        for i in range(error)
    ]
    return {
        "approved": approved,
        "confidence": confidence,
        "score_delta": score_delta,
        "required_failed": [],
        "results": results,
    }


def decision(
    *,
    strategy,
    confidence,
    delta,
    rr=2.73,
    required_rr=1.80,
    reason="m5_confirmation_failed bearish_m5",
    fail=0,
):
    return evaluate_mtf_confirmation_execution_authority_v2(
        report=make_report(
            confidence=confidence,
            score_delta=delta,
            fail=fail,
        ),
        candidate={
            "strategy": strategy,
            "signal": "BUY",
            "score": 101,
        },
        shadow_trade_plan={
            "entry_price": 4280.24,
            "stop_loss": 4274.09,
            "take_profit": 4297.02,
        },
        shadow_rr=rr,
        required_rr=required_rr,
        execution_mode="COUNTER_MTF_CALCULATED",
        original_allowed=False,
        original_reason=reason,
    )


def main():
    print("[MTF CONFIRMATION EXECUTION AUTHORITY V2 TEST]")

    pro = decision(
        strategy="PRO_TRADER_REPLICATION",
        confidence=76,
        delta=5.0,
    )
    print("\n[PRO TRADER ALERT CASE]")
    print(pro)
    assert_true(pro["allowed"] is True, pro)
    assert_true(pro["promoted"] is True, pro)

    pro_low_conf = decision(
        strategy="PRO_TRADER_REPLICATION",
        confidence=74,
        delta=5.0,
    )
    print("\n[PRO TRADER LOW CONFIDENCE]")
    print(pro_low_conf)
    assert_true(pro_low_conf["allowed"] is False, pro_low_conf)

    structure = decision(
        strategy="STRUCTURE_LIQUIDITY",
        confidence=88,
        delta=8.0,
        required_rr=1.30,
    )
    print("\n[STRUCTURE LIQUIDITY STRONG CASE]")
    print(structure)
    assert_true(structure["allowed"] is True, structure)

    structure_support_only = decision(
        strategy="STRUCTURE_LIQUIDITY",
        confidence=76,
        delta=5.0,
        required_rr=1.30,
    )
    print("\n[STRUCTURE LIQUIDITY SUPPORT ONLY]")
    print(structure_support_only)
    assert_true(structure_support_only["allowed"] is False, structure_support_only)

    low_rr = decision(
        strategy="PRO_TRADER_REPLICATION",
        confidence=90,
        delta=8.0,
        rr=1.20,
        required_rr=1.80,
    )
    print("\n[LOW RR CANNOT BE OVERRIDDEN]")
    print(low_rr)
    assert_true(low_rr["allowed"] is False, low_rr)

    wrong_reason = decision(
        strategy="PRO_TRADER_REPLICATION",
        confidence=90,
        delta=8.0,
        reason="strategy_not_allowed",
    )
    print("\n[NON-M5 REASON CANNOT BE OVERRIDDEN]")
    print(wrong_reason)
    assert_true(wrong_reason["allowed"] is False, wrong_reason)

    failed = decision(
        strategy="PRO_TRADER_REPLICATION",
        confidence=90,
        delta=8.0,
        fail=1,
    )
    print("\n[FAIL MODULE BLOCKS]")
    print(failed)
    assert_true(failed["allowed"] is False, failed)

    settings_text = (ROOT / "config" / "settings.py").read_text(
        encoding="utf-8"
    )
    live_text = (ROOT / "src" / "live_bot.py").read_text(
        encoding="utf-8"
    )

    print("\n[STATIC WIRING]")
    assert_true(
        '"PRO_TRADER_REPLICATION"' in settings_text[
            settings_text.index("MTF_CONFLICT_SOFT_EXECUTION_STRATEGIES"):
            settings_text.index(
                "MTF_CONFLICT_RETRACE_FIRST_STRATEGIES"
            )
        ],
        "PRO_TRADER_REPLICATION not added to MTF soft execution allowlist",
    )
    assert_true(
        "ENABLE_MTF_CONFLICT_CONFIRMATION_EXECUTION_AUTHORITY_V2 = True"
        in settings_text,
        "V2 authority flag missing",
    )
    assert_true(
        '"PRO_TRADER_REPLICATION": {' in settings_text,
        "PRO_TRADER_REPLICATION confirmation profile missing",
    )
    assert_true(
        "maybe_apply_mtf_confirmation_execution_authority_v2("
        in live_text,
        "V2 live bridge hook missing",
    )
    assert_true(
        "MTF_CONFLICT_CONFIRMATION_AUTHORITY_V2_PROMOTED"
        in live_text,
        "V2 promotion audit event missing",
    )

    for required in (
        "check_trade_guard(signal, tick)",
        "is_news_blackout_active()",
        "is_trading_blackout_active()",
        "is_trade_blocked_by_execution_memory(",
        "run_tracked_setup_confirmation_gate(",
        "execute_trade(signal, mtf_trade_plan, SYMBOL)",
    ):
        assert_true(required in live_text, f"missing live guard/path: {required}")

    print(
        "\nPASS: PRO_TRADER_REPLICATION can enter the existing MTF live path "
        "at confidence>=75/delta>=3 only after normal MTF score/geometry/RR "
        "checks, with zero confirmation FAIL/ERROR and no bypass of hard live "
        "guards. STRUCTURE_LIQUIDITY retains its stricter 80/3 profile."
    )


if __name__ == "__main__":
    main()
