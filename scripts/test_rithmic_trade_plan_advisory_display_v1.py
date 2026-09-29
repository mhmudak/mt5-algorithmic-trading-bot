from __future__ import annotations

from pathlib import Path
import ast
import json
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from src.order_flow_features.rithmic_trade_plan_advisory import (
    build_rithmic_trade_plan_advisory,
    format_rithmic_trade_plan_advisory_telegram_block,
    load_rithmic_basis_summary,
)


BOT_PLAN = {
    "entry_price": 4300.0,
    "stop_loss": 4290.0,
    "take_profit": 4320.0,
}


READY_BASIS = {
    "sample_count": 45,
    "valid_pair_count": 44,
    "valid_pair_rate": 44 / 45,
    "avg_basis": 11.1025,
    "basis_std": 0.208742,
    "max_abs_basis_jump": 0.45,
    "basis_ready_observe_only": True,
}


def verdict():
    return {
        "alignment": "SUPPORTS_SETUP",
        "verdict": "SUPPORTS_SETUP",
        "support_score": 2,
        "against_score": 0,
        "evidence_family_coverage": "5/6",
        "evidence_order_flow_regime": (
            "BUY_FLOW_EFFECTIVE"
        ),
        "evidence_feed_status": "HEALTHY",
        "legacy_v1_mode": "SHADOW_ONLY",
    }


def test_formatter():
    advisory = (
        build_rithmic_trade_plan_advisory(
            signal="BUY",
            bot_trade_plan=BOT_PLAN,
            rithmic_verdict=verdict(),
            basis_summary=READY_BASIS,
        )
    )

    block = (
        format_rithmic_trade_plan_advisory_telegram_block(
            advisory
        )
    )

    required = (
        "RITHMIC PLAN ? SHADOW ADVISORY",
        "Status: QUALITATIVE ONLY",
        "Posture: SETUP SUPPORTED",
        "Entry Context:",
        "SL Context:",
        "TP Context:",
        "STATISTICALLY READY",
        (
            "Numeric XAUUSD Entry / SL / TP: "
            "WITHHELD"
        ),
        "NO EXECUTION AUTHORITY",
    )

    for token in required:
        assert token in block, token

    print(
        "PASS: qualitative advisory block "
        "formats correctly"
    )


def test_basis_loader():
    with tempfile.TemporaryDirectory() as tmp:
        path = (
            Path(tmp)
            / "basis.json"
        )

        payload = {
            "summary": READY_BASIS,
        }

        path.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

        assert (
            load_rithmic_basis_summary(
                path
            )
            == payload
        )

    assert (
        load_rithmic_basis_summary(
            ROOT
            / "missing_rithmic_basis_test.json"
        )
        is None
    )

    print(
        "PASS: basis loader fails open"
    )


def test_runtime_wiring():
    path = (
        ROOT
        / "src"
        / "live_bot.py"
    )

    source = path.read_text(
        encoding="utf-8-sig",
    )

    tree = ast.parse(source)

    calls = [
        node
        for node in ast.walk(tree)
        if (
            isinstance(
                node,
                ast.Call,
            )
            and isinstance(
                node.func,
                ast.Name,
            )
            and node.func.id
            == "_rithmic_setup_verdict_telegram_fail_open"
        )
    ]

    assert len(calls) == 1

    keywords = {
        keyword.arg
        for keyword
        in calls[0].keywords
        if keyword.arg is not None
    }

    assert (
        "bot_trade_plan"
        in keywords
    )

    forbidden = (
        'trade_plan["entry_price"] = advisory',
        'trade_plan["stop_loss"] = advisory',
        'trade_plan["take_profit"] = advisory',
        (
            'detected_trade_plan'
            '["entry_price"] = advisory'
        ),
        (
            'detected_trade_plan'
            '["stop_loss"] = advisory'
        ),
        (
            'detected_trade_plan'
            '["take_profit"] = advisory'
        ),
    )

    for token in forbidden:
        assert token not in source

    print(
        "PASS: bot trade plan is passed "
        "as observation input only"
    )


def test_no_execution_coupling():
    source = (
        ROOT
        / "src"
        / "order_flow_features"
        / "rithmic_trade_plan_advisory.py"
    ).read_text(
        encoding="utf-8-sig",
    )

    forbidden = (
        "MetaTrader5",
        "mt5.order_send",
        "order_send(",
        "execute_trade(",
        "place_order(",
        "modify_position(",
        "position_modify(",
    )

    for token in forbidden:
        assert token not in source

    print(
        "PASS: advisory module has zero "
        "execution coupling"
    )


def main():
    test_formatter()
    test_basis_loader()
    test_runtime_wiring()
    test_no_execution_coupling()

    print("")
    print(
        "[PASS] Rithmic Trade-Plan Advisory "
        "Phase-2 display integration verified."
    )


if __name__ == "__main__":
    main()
