from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import ast
import sys


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from src.order_flow_features.rithmic_trade_plan_advisory import (  # noqa: E402
    build_rithmic_trade_plan_advisory,
    format_rithmic_trade_plan_advisory_telegram_block,
)


BOT_PLAN = {
    "entry_price": 4300.0,
    "stop_loss": 4290.0,
    "take_profit": 4320.0,
    "tp_ladder": [
        {
            "price": 4310.0,
            "rr": 1.0,
        },
        {
            "price": 4320.0,
            "rr": 2.0,
        },
    ],
}


BASIS = {
    "sample_count": 60,
    "valid_pair_count": 58,
    "valid_pair_rate": 0.9667,
    "avg_basis": 11.1,
    "basis_std": 0.25,
    "basis_ready_observe_only": True,
}


VERDICT = {
    "verdict": "SUPPORTS_SETUP",
    "alignment": "SUPPORTS_SETUP",
    "setup_direction": "BUY",
    "support_score": 3,
    "against_score": 1,
    "evidence_family_coverage": "5/6",
    "evidence_order_flow_regime": (
        "BUY_FLOW_EFFECTIVE"
    ),
    "evidence_feed_status": "HEALTHY",
}


NUMERIC_PLAN = {
    "model": (
        "RITHMIC_NUMERIC_SHADOW_PLAN_V1"
    ),
    "mode": "SHADOW_ONLY",
    "status": "NUMERIC_SHADOW_PLAN",
    "numeric_plan_available": True,
    "signal": "BUY",

    "suggested_entry": 4224.5,
    "suggested_sl": 4220.9,
    "suggested_tp": 4225.5,

    "suggested_tp_ladder": [
        {
            "label": "TP1",
            "price": 4225.5,
            "rr": 0.2778,
            "anchor_id": "ASK_DEPTH_2",
        },
        {
            "label": "TP2",
            "price": 4227.1,
            "rr": 0.7222,
            "anchor_id": "ASK_DEPTH_3",
        },
    ],

    "entry_anchor": {
        "anchor_id": "TOP_VAP_1",
        "family": "VOLUME_AT_PRICE",
        "price": 4224.5,
    },

    "sl_anchor": {
        "anchor_id": "ROLLING_LOW",
        "family": "TRADE_RANGE",
        "price": 4220.9,
    },

    "tp_anchors": [
        {
            "anchor_id": "ASK_DEPTH_2",
            "family": "ORDER_BOOK_DEPTH",
            "price": 4225.5,
        },
        {
            "anchor_id": "ASK_DEPTH_3",
            "family": "ORDER_BOOK_DEPTH",
            "price": 4227.1,
        },
    ],

    "rr_tp1": 0.2778,
    "rr_tp2": 0.7222,

    "decision_impact": "NONE",
    "can_influence_decision": False,
    "safe_for_execution": False,
    "execution_allowed": False,
    "trade_action": "NO_AUTO_TRADE",
    "can_modify_entry": False,
    "can_modify_sl": False,
    "can_modify_tp": False,
    "can_modify_size": False,
}


def build(
    *,
    enabled=False,
    plan=None,
    verdict=None,
):
    return (
        build_rithmic_trade_plan_advisory(
            signal="BUY",
            bot_trade_plan=BOT_PLAN,
            rithmic_verdict=(
                verdict
                or VERDICT
            ),
            basis_summary=BASIS,
            numeric_shadow_enabled=enabled,
            numeric_shadow_plan=plan,
        )
    )


def test_legacy_display_unchanged():
    result = build()

    block = (
        format_rithmic_trade_plan_advisory_telegram_block(
            result
        )
    )

    required = (
        "RITHMIC PLAN ? SHADOW ADVISORY",
        "Status: QUALITATIVE ONLY",
        "Posture: SETUP SUPPORTED",
        "Entry Context: KEEP ORIGINAL OR BETTER ENTRY ONLY",
        "SL Context: ORIGINAL SL CONTEXT SUPPORTED",
        "TP Context: EXTENSION PRESSURE SUPPORTED BUT KEEP ORIGINAL TP",
        (
            "Basis: STATISTICALLY READY ? "
            "LIVE NUMERIC TRANSLATION WITHHELD"
        ),
        "Numeric XAUUSD Entry / SL / TP: WITHHELD",
        (
            "Authority: SHADOW ONLY ? "
            "NO EXECUTION AUTHORITY"
        ),
    )

    for token in required:
        assert token in block, token

    print(
        "PASS: legacy Phase-2 display "
        "tokens remain unchanged"
    )


def test_default_disabled():
    result = build(
        plan=NUMERIC_PLAN,
    )

    assert (
        result["status"]
        == "QUALITATIVE_ONLY"
    )

    assert (
        result["numeric_shadow"]
        ["enabled"]
        is False
    )

    assert (
        result["rithmic_plan"]
        ["numeric_plan_available"]
        is False
    )

    print(
        "PASS: numeric shadow remains "
        "disabled by default"
    )


def test_valid_numeric_display():
    result = build(
        enabled=True,
        plan=NUMERIC_PLAN,
    )

    assert (
        result["status"]
        == "NUMERIC_SHADOW_PLAN"
    )

    assert (
        result["numeric_shadow"]
        ["attached"]
        is True
    )

    assert (
        result["rithmic_plan"]
        ["numeric_translation_allowed"]
        is True
    )

    block = (
        format_rithmic_trade_plan_advisory_telegram_block(
            result
        )
    )

    required = (
        "RITHMIC PLAN ? SHADOW ADVISORY",
        "Status: NUMERIC SHADOW PLAN",
        "Suggested Entry: 4224.50",
        "Suggested SL: 4220.90",
        "Suggested TP1: 4225.50",
        "Suggested TP2: 4227.10",
        "Entry Anchor: TOP VAP 1",
        "SL Anchor: ROLLING LOW",
        "TP Anchors: ASK_DEPTH_2 / ASK_DEPTH_3",
        (
            "Authority: SHADOW ONLY ? "
            "NO EXECUTION AUTHORITY"
        ),
    )

    for token in required:
        assert token in block, token

    assert (
        "Numeric XAUUSD Entry / SL / TP: WITHHELD"
        not in block
    )

    print(
        "PASS: valid Phase-3B plan "
        "renders numeric shadow levels"
    )


def test_authority_tamper_blocks():
    plan = deepcopy(
        NUMERIC_PLAN
    )

    plan[
        "execution_allowed"
    ] = True

    result = build(
        enabled=True,
        plan=plan,
    )

    assert (
        result["status"]
        == "QUALITATIVE_ONLY"
    )

    assert (
        result["numeric_shadow"]
        ["attached"]
        is False
    )

    assert (
        result["numeric_shadow"]
        ["reason"]
        == "numeric_shadow_plan_authority_invalid"
    )

    print(
        "PASS: authority escalation fails closed"
    )


def test_invalid_geometry_blocks():
    plan = deepcopy(
        NUMERIC_PLAN
    )

    plan[
        "suggested_sl"
    ] = 4226.0

    result = build(
        enabled=True,
        plan=plan,
    )

    assert (
        result["status"]
        == "QUALITATIVE_ONLY"
    )

    assert (
        result["numeric_shadow"]
        ["reason"]
        == "numeric_shadow_plan_geometry_invalid"
    )

    print(
        "PASS: malformed geometry fails closed"
    )


def test_mixed_verdict_blocks():
    verdict = deepcopy(
        VERDICT
    )

    verdict["verdict"] = "NEUTRAL"
    verdict["alignment"] = "NEUTRAL"
    verdict["support_score"] = 2
    verdict["against_score"] = 2

    result = build(
        enabled=True,
        plan=NUMERIC_PLAN,
        verdict=verdict,
    )

    assert (
        result["status"]
        == "QUALITATIVE_ONLY"
    )

    assert (
        result["numeric_shadow"]
        ["reason"]
        == "rithmic_alignment_not_supportive"
    )

    print(
        "PASS: mixed verdict cannot expose "
        "numeric levels"
    )


def test_runtime_gate_compatibility():
    """
    Phase-3C / Phase-3D compatibility contract.

    Before Phase 3D:
        numeric runtime may be completely unwired.

    After Phase 3D:
        wiring is allowed only when controlled by the explicit
        hard-OFF settings flag.

    This test therefore supports both safe lifecycle states.
    """

    live_path = (
        ROOT
        / "src"
        / "live_bot.py"
    )

    live_source = live_path.read_text(
        encoding="utf-8-sig",
    )

    live_tree = ast.parse(
        live_source
    )

    calls = []

    for node in ast.walk(
        live_tree
    ):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        if (
            isinstance(
                node.func,
                ast.Name,
            )
            and node.func.id
            == "build_rithmic_trade_plan_advisory"
        ):
            calls.append(
                node
            )

    assert calls

    keyword_sets = []

    for call in calls:
        keyword_sets.append(
            {
                keyword.arg
                for keyword in call.keywords
                if keyword.arg
            }
        )

    has_enabled_keyword = any(
        "numeric_shadow_enabled"
        in keywords
        for keywords in keyword_sets
    )

    has_plan_keyword = any(
        "numeric_shadow_plan"
        in keywords
        for keywords in keyword_sets
    )

    # Partial wiring is never acceptable.
    assert (
        has_enabled_keyword
        == has_plan_keyword
    )

    if not has_enabled_keyword:
        print(
            "PASS: pre-Phase3D runtime remains "
            "unwired and default-disabled"
        )
        return

    # Once Phase 3D wiring exists, both inputs must be present.
    for keywords in keyword_sets:
        assert (
            "numeric_shadow_enabled"
            in keywords
        )

        assert (
            "numeric_shadow_plan"
            in keywords
        )

    assert (
        "build_rithmic_numeric_shadow_runtime_context"
        in live_source
    )

    settings_path = (
        ROOT
        / "config"
        / "settings.py"
    )

    settings_source = settings_path.read_text(
        encoding="utf-8-sig",
    )

    settings_tree = ast.parse(
        settings_source
    )

    flag_found = False
    flag_value = None

    for node in settings_tree.body:
        if not isinstance(
            node,
            ast.Assign,
        ):
            continue

        if len(node.targets) != 1:
            continue

        target = node.targets[0]

        if not isinstance(
            target,
            ast.Name,
        ):
            continue

        if (
            target.id
            != "ENABLE_RITHMIC_NUMERIC_SHADOW_ADVISORY"
        ):
            continue

        flag_found = True

        try:
            flag_value = ast.literal_eval(
                node.value
            )
        except Exception:
            flag_value = "NON_LITERAL"

        break

    assert flag_found

    assert (
        flag_value is False
    )

    print(
        "PASS: Phase3D runtime wiring is "
        "present but hard-OFF by default"
    )


def test_no_execution_coupling():
    path = (
        ROOT
        / "src"
        / "order_flow_features"
        / "rithmic_trade_plan_advisory.py"
    )

    source = path.read_text(
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
        assert token not in source, token

    print(
        "PASS: advisory/display layer "
        "has zero execution coupling"
    )


def main():
    test_legacy_display_unchanged()
    test_default_disabled()
    test_valid_numeric_display()
    test_authority_tamper_blocks()
    test_invalid_geometry_blocks()
    test_mixed_verdict_blocks()
    test_runtime_gate_compatibility()
    test_no_execution_coupling()

    print("")
    print(
        "[PASS] Phase 3C corrected integration verified."
    )


if __name__ == "__main__":
    main()
