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

    tree = ast.parse(
        source
    )

    helper_name = (
        "_rithmic_setup_verdict_telegram_fail_open"
    )

    calls = [
        node
        for node in ast.walk(
            tree
        )
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
            == helper_name
        )
    ]

    assert calls, (
        "Rithmic setup-verdict helper "
        "has no runtime call sites"
    )

    function_nodes = [
        node
        for node in ast.walk(
            tree
        )
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
    ]

    def enclosing_function_name(
        call,
    ):
        candidates = [
            node
            for node
            in function_nodes
            if (
                node.lineno
                <= call.lineno
                <= node.end_lineno
            )
        ]

        if not candidates:
            return None

        owner = min(
            candidates,
            key=lambda node: (
                node.end_lineno
                - node.lineno
            ),
        )

        return owner.name

    setup_plan_calls = []

    for call in calls:
        keywords = {
            keyword.arg
            for keyword
            in call.keywords
            if keyword.arg
            is not None
        }

        assert (
            "signal"
            in keywords
        ), (
            "every Rithmic helper call "
            "must pass signal"
        )

        assert (
            "context"
            in keywords
        ), (
            "every Rithmic helper call "
            "must pass context"
        )

        bot_plan_keywords = [
            keyword
            for keyword
            in call.keywords
            if keyword.arg
            == "bot_trade_plan"
        ]

        assert (
            len(
                bot_plan_keywords
            )
            <= 1
        )

        if not bot_plan_keywords:
            # Qualitative-only helper call.
            # It cannot create a trade-plan advisory
            # because bot_trade_plan defaults to None.
            continue

        setup_plan_calls.append(
            (
                call,
                bot_plan_keywords[0],
                enclosing_function_name(
                    call
                ),
            )
        )

    assert (
        len(
            setup_plan_calls
        )
        == 1
    ), (
        "exactly one runtime helper call "
        "may receive bot_trade_plan"
    )

    (
        setup_call,
        bot_plan_keyword,
        owner_name,
    ) = setup_plan_calls[0]

    assert (
        owner_name
        == "process_cycle"
    ), (
        "bot_trade_plan advisory wiring "
        "must remain inside process_cycle"
    )

    assert isinstance(
        bot_plan_keyword.value,
        ast.Name,
    )

    assert (
        bot_plan_keyword.value.id
        == "detected_trade_plan"
    ), (
        "process_cycle must pass the "
        "authoritative detected_trade_plan "
        "as observation input"
    )

    setup_keywords = {
        keyword.arg
        for keyword
        in setup_call.keywords
        if keyword.arg
        is not None
    }

    assert {
        "signal",
        "context",
        "bot_trade_plan",
    }.issubset(
        setup_keywords
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
        "PASS: exactly one setup-detection "
        "runtime call passes bot trade plan "
        "as observation input only"
    )

    qualitative_count = (
        len(calls)
        - len(
            setup_plan_calls
        )
    )

    print(
        "PASS: "
        f"{qualitative_count} additional "
        "Rithmic helper call(s) remain "
        "qualitative-only"
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
